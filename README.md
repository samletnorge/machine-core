[![Open in Coder](https://coder.valiantlynx.com/open-in-coder.svg)](https://coder.valiantlynx.com/templates/docker/workspace?param.git_repo=git@github.com:samletnorge/machine-core.git)

# machine-core

**A flexible agent framework for building AI agents with MCP (Model Context Protocol) integration, dynamic OpenAPI tools, vector-based RAG filtering, and file processing.**

## Features

- **Clean Architecture** — separation of infrastructure (`AgentCore`) and execution patterns (`BaseAgent`)
- **7 LLM + 3 Embedding Providers** — Ollama, Azure, Grok, Groq, Google Gemini, Vertex Gemini, Vertex Claude
- **MCP Integration** — load and validate MCP toolsets from JSON config
- **Dynamic Tools** — generate pydantic-ai tools from OpenAPI specs, swap per request via `rebuild_agent()`
- **RAG Tool Filtering** — `ToolFilterManager` indexes and filters tools by task relevance using vector similarity
- **File Processing** — PDF extraction, image OCR, VLM preparation, batch upload handling
- **Vector Store** — LanceDB-backed storage with cross-table search and `DocumentStore` facade
- **6 Built-in Agents** — ChatAgent, CLIAgent, ReceiptProcessorAgent, TwitterBotAgent, RAGChatAgent, MemoryMasterAgent
- **FastAPI Service** — API docs, health check, Prometheus metrics at `/metrics`

## Installation

```bash
# As a dependency
uv add git+https://github.com/samletnorge/machine-core.git

# Local development
git clone https://github.com/samletnorge/machine-core.git
cd machine-core
uv sync
```

## Quick Start

### MCP Toolsets Mode (BaseAgent subclass)

```python
from machine_core.core.agent_base import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            system_prompt="You are a helpful assistant.",
            mcp_config_path="mcp.json",
        )

    async def run(self, query: str):
        async for event in self.run_query_stream(query):
            yield event
```

### Dynamic Tools Mode (AgentCore direct)

```python
from machine_core import (
    AgentCore, AgentConfig,
    generate_tools_from_openapi, fetch_openapi_spec,
    Embedder, VectorStore, ToolFilterManager,
)

# Create core once
core = AgentCore(tools=[], system_prompt="...", agent_config=AgentConfig())

# Per request: RAG filter + rebuild
spec = await fetch_openapi_spec("https://api.example.com")
manager = ToolFilterManager(embedder=embedder, vector_store=vs)
await manager.index_openapi(spec)
result = await manager.filter("find all invoices", essential_tools={"search"})
tools = generate_tools_from_openapi(spec, base_url, tool_filter=result.names)
core.rebuild_agent(tools=tools)
```

## Configuration

```bash
# LLM (any of 7 providers)
LLM_PROVIDER=google          # ollama, azure, grok, groq, google, vertex-gemini, vertex-claude
LLM_MODEL=gemini-2.5-flash

# Embedding (any of 3 providers)
EMBEDDING_PROVIDER=google
EMBEDDING_MODEL=gemini-embedding-001

# Agent behavior
AGENT_MAX_ITERATIONS=10
AGENT_TIMEOUT=604800.0
```

See [docs/configuration.md](docs/configuration.md) for the full reference.

## Available Agents

| Agent | Description | Use Case |
|-------|-------------|----------|
| `ChatAgent` | Streaming chat | Streamlit UI, web chat |
| `CLIAgent` | Non-streaming | Terminal, cron jobs |
| `ReceiptProcessorAgent` | Vision + queue | Document analysis |
| `TwitterBotAgent` | Scheduled posting | Social media automation |
| `RAGChatAgent` | Knowledge graph | Q&A, support |
| `MemoryMasterAgent` | Knowledge extraction | Graph maintenance |

## Running as a Service

```bash
# Docker
export GITHUB_TOKEN=your_token
docker-compose up -d

# Local
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Endpoints: `/` (frontend), `/docs` (Swagger), `/health`, `/api/info`, `/metrics` (Prometheus)

## Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](docs/getting-started.md) | Installation, first agent, project structure |
| [Architecture](docs/architecture.md) | Inheritance chain, tool modes, data flow |
| [Configuration](docs/configuration.md) | Environment variables, AgentConfig, MCP config |
| [Agents](docs/agents.md) | BaseAgent, built-in agents, streaming events |
| [Providers](docs/providers.md) | All 7 LLM + 3 embedding providers |
| [File Processing](docs/file-processing.md) | FileProcessor, OCR, VLM prep, batch uploads |
| [Vector Store](docs/vector-store.md) | Embedder, VectorStore, DocumentStore |
| [MCP Toolsets](docs/tools/mcp-toolsets.md) | MCP config, loading, validation |
| [OpenAPI Tools](docs/tools/openapi-tools.md) | Tool generation from OpenAPI specs |
| [Tool Filtering](docs/tools/tool-filtering.md) | RAG-based tool filtering |
| [API Reference](docs/api-reference.md) | Complete class/method reference |
| [Examples](docs/examples.md) | Real-world usage from 4 downstream projects |
| [Deployment](docs/deployment.md) | Docker, production, Prometheus |
| [Changelog](docs/changelog.md) | Version history |

## License

[LICENSE](./LICENSE.md)
