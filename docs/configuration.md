# Configuration

## Overview

Machine Core reads configuration from three sources, in order of precedence:

1. **Direct parameters** -- Passed to constructors at runtime (highest priority).
2. **Environment variables** -- Read from the process environment or a `.env` file.
3. **Defaults** -- Hardcoded sensible defaults (lowest priority).

`model-providers` calls `load_dotenv()` at import time, so any `.env` file in the working directory is automatically loaded.

## AgentConfig

Controls agent behavior. Defined in `core/config.py`.

```python
from machine_core import AgentConfig

# Load from environment
config = AgentConfig.from_env()

# Or construct directly (overrides env)
config = AgentConfig(
    max_iterations=20,
    timeout=3600.0,
    max_tool_retries=10,
    allow_sampling=True,
)
```

| Field | Type | Default | Env Variable | Description |
|-------|------|---------|-------------|-------------|
| `max_iterations` | `int` | `10` | `AGENT_MAX_ITERATIONS` | Max tool call iterations per query |
| `timeout` | `float` | `604800.0` | `AGENT_TIMEOUT` | Request timeout in seconds (default: 1 week) |
| `max_tool_retries` | `int` | `15` | `AGENT_MAX_TOOL_RETRIES` | Max retries for failed tool calls |
| `allow_sampling` | `bool` | `True` | `AGENT_ALLOW_SAMPLING` | Allow MCP response sampling |

`AgentConfig` is mutable (`frozen = False`) so you can modify fields at runtime.

## MCPServerModel

Defines an MCP server connection. Used internally by `load_mcp_servers_from_config()`.

```python
from machine_core import MCPServerModel

server = MCPServerModel(
    url="https://my-server.example.com/mcp",
    type="http",
)

stdio_server = MCPServerModel(
    url="uv run python server.py",
    type="stdio",
    env={"API_KEY": "secret"},
)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | -- | Server URL (http/sse) or command string (stdio) |
| `type` | `str` | `"http"` | Transport: `"http"`, `"sse"`, or `"stdio"` |
| `env` | `dict[str, str] \| None` | `None` | Environment variables for stdio servers |

## LLM Provider Configuration

Controlled by `model-providers`. See [Providers](providers.md) for provider-specific details.

### Core Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | Provider backend. One of: `ollama`, `azure`, `grok`, `groq`, `google`, `vertex-gemini`, `vertex-claude` |
| `LLM_MODEL` | Per-provider | Model name override |
| `LLM_MAX_TOKENS` | Per-provider | Max output tokens |
| `LLM_CONTEXT_WINDOW` | Per-provider | Context window size |
| `LLM_TIMEOUT` | `604800` | Request timeout in seconds |

### Default Limits by Provider

| Provider | Default Model | Max Tokens | Context Window |
|----------|--------------|------------|----------------|
| `ollama` | `gpt-oss:latest` | 131,072 | 131,072 |
| `azure` | `gpt-4o-2` | 8,192 | 8,192 |
| `grok` | `grok-2-latest` | 8,192 | 8,192 |
| `groq` | `llama-3.3-70b-versatile` | 32,768 | 32,768 |
| `google` | `gemini-2.5-flash` | 65,536 | 1,000,000 |
| `vertex-gemini` | `gemini-2.5-flash` | 65,536 | 1,000,000 |
| `vertex-claude` | `claude-sonnet-4-20250514` | 8,192 | 200,000 |

### Provider-Specific Variables

#### Ollama

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `https://ollama.valiantlynx.com/v1` | Ollama API endpoint |

Ollama provider automatically sets `think: true` (chain-of-thought) and `keep_alive: 0` (release GPU after request).

#### Azure OpenAI

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | -- | Azure OpenAI resource URL (required) |
| `AZURE_OPENAI_API_VERSION` | `2024-08-01-preview` | API version |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o-2` | Chat deployment name |
| `AZURE_USE_TOKEN_AUTH` | `true` | Use `DefaultAzureCredential` (set `false` for API key) |
| `AZURE_OPENAI_API_KEY` | -- | API key (when `AZURE_USE_TOKEN_AUTH=false`) |
| `AZURE_OPENAI_KEYVAULT_URL` | -- | Key Vault URL for API key retrieval |
| `AZURE_OPENAI_SECRET_NAME` | `azure-openai-api-key` | Key Vault secret name |
| `AZURE_COGNITIVE_SERVICE_SCOPE` | `https://cognitiveservices.azure.com/.default` | OAuth scope |

#### Grok (x.ai)

| Variable | Default | Description |
|----------|---------|-------------|
| `GROK_API_KEY` | -- | x.ai API key (required) |

#### Groq

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | -- | Groq API key (required) |

#### Google Gemini

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_API_KEY` | -- | Google Gemini API key (required) |

#### Vertex AI (Gemini)

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT` | -- | Google Cloud project ID (required) |
| `GCP_LOCATION` | `us-central1` | GCP region |

#### Vertex AI (Claude)

| Variable | Default | Description |
|----------|---------|-------------|
| `GCP_PROJECT` | -- | Google Cloud project ID (required) |
| `GCP_LOCATION` | `us-east5` | GCP region |

## Embedding Provider Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_PROVIDER` | `ollama` | Embedding backend: `ollama`, `azure`, `google` |
| `EMBEDDING_MODEL` | Per-provider | Embedding model name |
| `EMBEDDING_DIMENSIONS` | -- | Output dimension override |
| `EMBED_TIMEOUT` | `60` | Embedding request timeout in seconds |

### Embedding Defaults by Provider

| Provider | Default Model | Notes |
|----------|--------------|-------|
| `ollama` | `nomic-embed-text` | Uses `/v1/embeddings` endpoint |
| `azure` | `text-embedding-3-large` | Requires `AZURE_OPENAI_EMBED_DEPLOYMENT` |
| `google` | `gemini-embedding-001` | Default 3072 dimensions |

### Azure Embedding Extras

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_OPENAI_EMBED_DEPLOYMENT` | `text-embedding-3-large` | Embedding deployment name |
| `AZURE_OPENAI_EMBED_DIMENSIONS` | -- | Dimension override |

## CORS Configuration (FastAPI Service)

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:8000,http://localhost:3000` | Comma-separated allowed origins |

## MCP Server Configuration File

MCP servers are configured in a JSON file (default: `mcp.json` in the working directory). The format follows VS Code's MCP configuration style:

```json
{
  "servers": {
    "web-search": {
      "type": "http",
      "url": "https://search-server.example.com/mcp"
    },
    "file-tools": {
      "type": "sse",
      "url": "https://file-server.example.com/sse"
    },
    "local-tools": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "python", "my_mcp_server.py"],
      "env": {
        "API_KEY": "secret-value"
      }
    }
  }
}
```

### Server Types

| Type | Transport | Config Fields |
|------|-----------|---------------|
| `http` | HTTP Streamable | `url` |
| `sse` | Server-Sent Events | `url` |
| `stdio` | Standard I/O (local process) | `command`, `args`, `env` |

See [MCP Toolsets](tools/mcp-toolsets.md) for detailed usage.

## Example .env File

```bash
# === Agent Behavior ===
AGENT_MAX_ITERATIONS=10
AGENT_TIMEOUT=604800.0
AGENT_MAX_TOOL_RETRIES=15
AGENT_ALLOW_SAMPLING=true

# === LLM Provider ===
LLM_PROVIDER=google
LLM_MODEL=gemini-2.5-flash
# LLM_MAX_TOKENS=65536
# LLM_CONTEXT_WINDOW=1000000

# === Embedding Provider ===
EMBEDDING_PROVIDER=google
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=3072

# === Provider Credentials ===
GCP_API_KEY=your-google-api-key

# For Azure:
# AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
# AZURE_USE_TOKEN_AUTH=true

# For Ollama (local):
# OLLAMA_BASE_URL=http://localhost:11434/v1

# === CORS (FastAPI service only) ===
# ALLOWED_ORIGINS=http://localhost:3000,https://myapp.example.com
```
