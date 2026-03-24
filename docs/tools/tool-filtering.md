# Tool Filtering

When you have hundreds of tools (from large OpenAPI specs and/or multiple MCP servers), sending them all to the LLM wastes context and confuses the model. `ToolFilterManager` uses RAG (Retrieval-Augmented Generation) to select only the most relevant tools for each query.

## How It Works

1. **Index phase** (once at startup): Tool names and descriptions are embedded and stored in a LanceDB vector table.
2. **Filter phase** (per request): The user's query is embedded, vector search finds the most similar tools, and you get back a set of relevant tool names.
3. **Apply phase** (per request): Use the filtered names to generate only relevant OpenAPI tools and/or wrap MCP toolsets to hide irrelevant tools.

## Quick Start

```python
from machine_core import (
    Embedder, VectorStore, ToolFilterManager,
    generate_tools_from_openapi, fetch_openapi_spec,
    filter_mcp_toolsets,
)
from model_providers import get_embedding_provider

# Setup
embedder = Embedder(get_embedding_provider())
vector_store = VectorStore(db_path=".vector_store", embedder=embedder)
manager = ToolFilterManager(embedder=embedder, vector_store=vector_store)

# Index tools (once)
spec = await fetch_openapi_spec("https://api.example.com")
await manager.index_openapi(spec)
# await manager.index_mcp_toolsets(toolsets)  # if also using MCP

# Filter per query
result = await manager.filter(
    "Create an invoice for customer ABC",
    top_k=20,
    essential_tools={"getCompanyInfo", "getAuthToken"},
)

print(result.names)      # {"createInvoice", "getCustomer", "getCompanyInfo", "getAuthToken", ...}
print(result.by_source)  # {"openapi": {"createInvoice", "getCustomer", ...}}
```

## ToolFilterResult

The return type of `manager.filter()`:

| Field | Type | Description |
|-------|------|-------------|
| `names` | `Set[str]` | All relevant tool names (union across all sources) |
| `by_source` | `Dict[str, Set[str]]` | Tool names grouped by source: `"openapi"`, `"mcp"` |

## Indexing

### OpenAPI Specs

```python
count = await manager.index_openapi(spec, batch_size=32)
print(f"Indexed {count} tools from OpenAPI spec")
```

Extracts from each operation:
- `operationId` (sanitized to match tool naming rules)
- `summary` or `description`
- Parameter names (path, query, body)

Embeds a text representation: `"Tool: {name}\nDescription: {desc}\nParameters: {params}"`.

### MCP Toolsets

```python
count = await manager.index_mcp_toolsets(toolsets, batch_size=32)
print(f"Indexed {count} tools from MCP toolsets")
```

Calls `list_tools()` on each toolset, extracts:
- Tool name
- Description
- Input schema parameter names

### Re-indexing

If you index the same source again (e.g., re-indexing OpenAPI after a spec update), the manager overwrites records for that source while preserving records from other sources. You can safely call `index_openapi()` multiple times.

## Filtering

```python
result = await manager.filter(
    task_prompt="Create an invoice for customer ABC",
    top_k=200,
    essential_tools={"getCompanyInfo", "listCurrencies"},
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task_prompt` | `str` | -- | Natural language description of the task |
| `top_k` | `int` | `200` | Maximum tools to return from vector search |
| `essential_tools` | `Set[str] \| None` | `None` | Tool names that must always be included |

`essential_tools` are added to the result regardless of RAG relevance. Use for tools that should always be available (e.g., auth endpoints, company info lookups).

### Fallback Behavior

- If no tools are indexed: returns empty result (or just essential tools).
- If embedding fails: falls back to returning ALL indexed tools.
- If search fails: falls back to returning ALL indexed tools + essential tools.

## Applying Filters

### OpenAPI Tools Only

```python
# Generate only relevant tools
tools = generate_tools_from_openapi(
    spec, base_url, auth_headers,
    tool_filter=result.by_source.get("openapi"),
)
agent_core.rebuild_agent(tools=tools)
```

### MCP Tools Only

```python
# Wrap toolsets to hide irrelevant tools
filtered_toolsets = await filter_mcp_toolsets(
    toolsets,
    relevant_names=result.by_source.get("mcp", set()),
)
agent_core.rebuild_agent(toolsets=filtered_toolsets)
```

`filter_mcp_toolsets()` discovers all tool names from each toolset (via `list_tools()`), computes which names to hide (all_names - relevant_names), and wraps each toolset with `ToolFilterWrapper` to exclude hidden tools from the LLM's context.

### Mixed Mode (OpenAPI + MCP)

The full pattern for agents that use both OpenAPI and MCP tools:

```python
# Index both sources (once)
await manager.index_openapi(spec)
await manager.index_mcp_toolsets(toolsets)

# Per request: filter, apply, rebuild
result = await manager.filter(prompt, essential_tools=ESSENTIAL_TOOLS)

# OpenAPI side
openapi_tools = generate_tools_from_openapi(
    spec, base_url, auth_headers,
    tool_filter=result.by_source.get("openapi"),
)

# MCP side
filtered_toolsets = await filter_mcp_toolsets(
    toolsets,
    relevant_names=result.by_source.get("mcp", set()),
)

# Rebuild with both
agent_core.rebuild_agent(tools=openapi_tools, toolsets=filtered_toolsets)
```

## Statistics and Inspection

```python
# Check if indexed
print(manager.is_indexed)    # True
print(manager.tool_count)    # 823

# Detailed stats
stats = manager.get_statistics()
# {
#     "total_tools": 823,
#     "by_source": {"openapi": 800, "mcp": 23},
#     "initialized": True,
#     "tools_table_exists": True,
# }
```

## Storage

Tool embeddings are stored in the VectorStore's `"tools"` table. This table is automatically excluded from `VectorStore.search()` cross-table queries (so tool descriptions don't pollute document search results).

The VectorStore persists to disk at the configured `db_path`, so tool embeddings survive restarts. Re-indexing only re-embeds if you explicitly call `index_openapi()` or `index_mcp_toolsets()` again.

## How top_k Works

`top_k` is a **global cap** across all sources. With `top_k=20` on an index of 800 OpenAPI + 20 MCP tools, the top 20 results could theoretically all be from one source. There is no per-source minimum guarantee.

If you need guaranteed coverage of both sources, increase `top_k` or use `essential_tools` to ensure specific tools are always included.

## filter_mcp_toolsets() Reference

```python
async def filter_mcp_toolsets(
    toolsets: list,
    relevant_names: Set[str],
) -> list:
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `toolsets` | `list` | MCP toolset objects |
| `relevant_names` | `Set[str]` | Tool names to KEEP visible |

Returns a list of toolsets. Each toolset with tools to hide is wrapped with `ToolFilterWrapper`. Toolsets where all tools are relevant are returned unwrapped. Toolsets that can't be inspected (no `list_tools()`) are passed through as-is.

## Real-World Pattern: ai-accounting-agent

```python
ESSENTIAL_TOOLS = {
    "Token__ConsumerByToken_get",
    "Invoice__search",
    "Product__search",
    "Customer__search",
    "Supplier__search",
    "Account__search",
    # ... ~88 tools that must always be available
}

async def handle_request(prompt: str, files: list):
    # RAG filter: 800 tools -> ~10 relevant + ~88 essential
    result = await manager.filter(
        prompt,
        top_k=10,
        essential_tools=ESSENTIAL_TOOLS,
    )

    tools = generate_tools_from_openapi(
        spec, base_url,
        auth_headers=_make_auth_headers(),
        tool_filter=result.by_source.get("openapi"),
    )

    agent_core.rebuild_agent(tools=tools, retries=30)
    response = await agent_core.agent.run(prompt)
    return response.output
```
