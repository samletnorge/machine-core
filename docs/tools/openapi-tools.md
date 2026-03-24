# OpenAPI Tools

Machine Core can generate pydantic-ai `Tool` objects from any OpenAPI specification. Each endpoint becomes a callable tool that the LLM can invoke, with the actual HTTP call handled automatically.

## Basic Usage

```python
from machine_core import generate_tools_from_openapi, fetch_openapi_spec

# Fetch the spec
spec = await fetch_openapi_spec("https://api.example.com")

# Generate tools (one per endpoint)
tools = generate_tools_from_openapi(
    spec=spec,
    base_url="https://api.example.com",
    auth_headers={"Authorization": "Bearer my-token"},
)

print(f"Generated {len(tools)} tools")
# Generated 47 tools

# Use with AgentCore
from machine_core import AgentCore
agent_core = AgentCore(tools=tools, system_prompt="You can call the API.")
```

## How It Works

`generate_tools_from_openapi()` walks every path and method in the OpenAPI spec:

1. **Extracts metadata** from each operation: `operationId`, `summary`/`description`, parameters, request body.
2. **Sanitizes tool names** for LLM compatibility (Gemini requires `[a-zA-Z_][a-zA-Z0-9_.:-]{0,63}`).
3. **Builds a JSON schema** merging path parameters, query parameters, and request body properties.
4. **Creates a closure** for each tool that makes the actual HTTP request via httpx.
5. **Returns `Tool.from_schema()`** objects ready for pydantic-ai.

When the LLM calls a tool:
- Path parameters are substituted in the URL (`/users/{id}` -> `/users/123`).
- Query parameters go to the URL query string (for GET/DELETE).
- Body parameters go to JSON body (for POST/PUT/PATCH).
- Auth headers are included in every request.
- The raw JSON response is returned to the LLM (including error responses, so the LLM can react to failures).

## Parameters

### `generate_tools_from_openapi(spec, base_url, auth_headers, tool_filter)`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `spec` | `dict` | Yes | Parsed OpenAPI spec (from `fetch_openapi_spec()` or `json.load()`) |
| `base_url` | `str` | Yes | Base URL for API requests |
| `auth_headers` | `dict[str, str]` | Yes | Headers included in every request (e.g., `{"Authorization": "Bearer ..."}`) |
| `tool_filter` | `set[str] \| None` | No | If provided, only generate tools whose name is in this set. Used with `ToolFilterManager` for RAG-based filtering. |

Returns `List[Tool]`.

### `fetch_openapi_spec(api_url, auth_headers)`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `api_url` | `str` | Yes | Base URL of the API (appends `/openapi.json`) |
| `auth_headers` | `dict[str, str] \| None` | No | Optional auth headers for fetching the spec |

Returns parsed JSON `dict`.

## Auth Headers

The `auth_headers` parameter is completely pluggable. Machine Core has no opinion on auth schemes -- you construct whatever headers your API needs:

```python
# Bearer token
auth_headers = {"Authorization": "Bearer eyJhbG..."}

# Basic auth
import base64
encoded = base64.b64encode(b"user:pass").decode()
auth_headers = {"Authorization": f"Basic {encoded}"}

# API key
auth_headers = {"X-API-Key": "my-secret-key"}

# Multiple headers
auth_headers = {
    "Authorization": "Bearer token",
    "X-Tenant-ID": "company-123",
}
```

## Tool Filtering

For APIs with hundreds of endpoints, you don't want to send all tools to the LLM (context window waste, confusion). Use `tool_filter` to select a subset:

```python
# Only generate these specific tools
tools = generate_tools_from_openapi(
    spec=spec,
    base_url=base_url,
    auth_headers=auth_headers,
    tool_filter={"createInvoice", "getCustomer", "listProducts"},
)
```

Typically combined with `ToolFilterManager` for automatic RAG-based selection. See [Tool Filtering](tool-filtering.md).

## Schema Simplification

OpenAPI specs often have deeply nested `$ref` references and complex schemas. `generate_tools_from_openapi()` automatically:

1. **Resolves `$ref` inline** -- All references are expanded to their definitions.
2. **Limits depth to 3 levels** -- Gemini and some models struggle with deeply nested schemas.
3. **Strips `$defs`/`definitions`** -- Removes the definition block after inlining.
4. **Handles circular references** -- Detected and broken with placeholder types.
5. **Deduplicates names** -- Appends `_2`, `_3`, etc. for `operationId` collisions.

## Error Handling

Tool functions handle errors gracefully and return them as strings (so the LLM can see what went wrong):

- **HTTP errors:** Returns `"Error: HTTP {status}: {response_text}"` -- the LLM can react (e.g., try different parameters).
- **Timeouts:** Returns `"Error: Request timed out after 30s"`.
- **Connection errors:** Returns `"Error: {exception_message}"`.

This is intentional: the LLM should see errors to decide on next steps, rather than crashing the tool chain.

## Real-World Example: ai-accounting-agent

The ai-accounting-agent generates tools from the Tripletex API (~800 endpoints):

```python
from machine_core import (
    AgentCore, AgentConfig,
    generate_tools_from_openapi, fetch_openapi_spec,
    Embedder, VectorStore, ToolFilterManager,
)
from model_providers import get_embedding_provider, EmbeddingProviderConfig

# 1. Fetch the spec once at startup
spec = await fetch_openapi_spec(TRIPLETEX_API_URL, auth_headers=auth)

# 2. Index all tools for RAG
embedder = Embedder(get_embedding_provider(EmbeddingProviderConfig.from_env()))
vector_store = VectorStore(db_path=".vector_store", embedder=embedder)
manager = ToolFilterManager(embedder=embedder, vector_store=vector_store)
await manager.index_openapi(spec)

# 3. Create agent once (empty tools -- populated per request)
agent_core = AgentCore(tools=[], system_prompt=SYSTEM_PROMPT, agent_config=config)

# 4. Per request: RAG filter + generate + rebuild
result = await manager.filter(user_prompt, essential_tools=ESSENTIAL_TOOLS)
tools = generate_tools_from_openapi(
    spec, base_url, auth_headers,
    tool_filter=result.by_source.get("openapi"),
)
agent_core.rebuild_agent(tools=tools, retries=30)

# 5. Run
response = await agent_core.agent.run(user_prompt)
```

This pattern ensures only the ~10-20 most relevant tools (out of 800+) are included per request.

## Supported HTTP Methods

| Method | Parameters | Body |
|--------|-----------|------|
| GET | Path + query | None |
| POST | Path | JSON body |
| PUT | Path | JSON body |
| PATCH | Path | JSON body |
| DELETE | Path + query | None |

For GET and DELETE, all non-path parameters are sent as query parameters. For POST, PUT, and PATCH, non-path parameters go to the JSON body.

## Content Types

The tool generator handles:
- `application/json` -- Primary, properties are merged into the tool schema.
- `application/x-www-form-urlencoded` -- Properties are merged similarly.
- Other content types -- A single `body` parameter is created.

If the request body has a schema with properties, those properties are merged directly into the tool's parameter schema. Otherwise, the entire body is wrapped in a single `body` parameter.
