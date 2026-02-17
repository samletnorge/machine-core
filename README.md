[![Open in Coder](https://coder.valiantlynx.com/open-in-coder.svg)](https://coder.valiantlynx.com/templates/docker/workspace?param.git_repo=git@github.com:samletnorge/machine-core.git)

# machine-core

**A flexible agent framework for building AI agents with MCP (Model Context Protocol) integration.**

## Features

- 🎯 **Clean Architecture** - Separation of infrastructure (AgentCore) and execution patterns (BaseAgent)
- 🔧 **Flexible Configuration** - Environment variables, direct parameters, or runtime overrides
- 🔌 **MCP Integration** - Easy integration with MCP servers and tools
- 🚀 **Multiple Agent Types** - Chat, CLI, Receipt Processor, Twitter Bot, Memory Master, RAG Chat, etc
- 📦 **Reusable Package** - Install once, use in multiple projects
- 🌐 **API & Documentation** - FastAPI service with comprehensive docs and SEO-optimized frontend

## Installation

### As a Package

```bash
# From the machine-core directory
uv add git+https://github.com/samletnorge/machine-core.git

# Or with
uv sync
```

### As a Service (with API & Frontend)

```bash
# Using Docker Compose
export GITHUB_TOKEN=your_token
docker-compose up -d

# Or run locally
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Then access:
- Frontend: http://localhost:8000/
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

## Quick Start

### Basic Usage (Environment Config)

```python
from machine_core.agents import ChatAgent

# Loads config from environment variables
agent = ChatAgent()

# Run streaming query
async for event in agent.run("What is quantum computing?"):
    if event['type'] == 'text_delta':
        print(event['content'], end='', flush=True)
```

### Custom Configuration

```python
from machine_core import AgentConfig
from machine_core.agents import CLIAgent

# Create custom config
config = AgentConfig(
    max_iterations=20,
    timeout=3600.0,
    max_tool_retries=10
)

# Pass to agent
agent = CLIAgent(
    model_name="llama3.2:latest",
    agent_config=config
)

result = await agent.run("Analyze this data")
```

## Configuration

Machine Core supports three configuration methods:

1. **Environment Variables** (`.env` file)
2. **Direct Parameters** (runtime override)
3. **Partial Overrides** (mix and match)

See [CONFIGURATION.md](./CONFIGURATION.md) for detailed examples.

### Environment Variables

```bash
# Agent Config
AGENT_MAX_ITERATIONS=10
AGENT_TIMEOUT=604800.0
AGENT_MAX_TOOL_RETRIES=15
AGENT_ALLOW_SAMPLING=true

# LLM Config
LLM_PROVIDER=ollama
LLM_MODEL=gpt-oss:latest

# Embedding Config
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
```

## Available Agents

| Agent | Description | Use Case | Live Demo |
|-------|-------------|----------|-----------|
| `ChatAgent` | Streaming chat | Streamlit UI, web chat | [Demo](https://mcp-client-chat.valiantlynx.com) |
| `CLIAgent` | Non-streaming | Terminal, cron jobs | - |
| `ReceiptProcessorAgent` | Vision + queue | Document analysis | [Demo](https://receipt-ocr.valiantlynx.com) |
| `TwitterBotAgent` | Scheduled posting | Social media automation | - |
| `RAGChatAgent` | Knowledge graph | Q&A, support | - |
| `MemoryMasterAgent` | Knowledge extraction | Graph maintenance | - |

## Creating Custom Agents

```python
from machine_core.core.agent_base import BaseAgent

class MyCustomAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            system_prompt="Your custom prompt",
            mcp_config_path="mcp_custom.json"
        )
    
    async def run(self, task: str):
        """Your custom execution logic."""
        result = await self.run_query(task)
        return result
```

## Architecture

```
AgentCore (infrastructure)
  ├─ MCP toolset loading/validation
  ├─ Model/provider configuration
  ├─ Embedding backend setup
  └─ Agent instance creation

BaseAgent (execution patterns)
  ├─ run() [abstract - implement per agent]
  ├─ run_query() [sync execution]
  ├─ run_query_stream() [streaming execution]
  └─ Helper methods

ConcreteAgent (implementations)
  └─ Implements run() using base patterns
```

## API Documentation

Machine Core includes a FastAPI service that provides:
- RESTful API endpoints
- Interactive API documentation (Swagger UI)
- SEO-optimized frontend for documentation
- Prometheus metrics for monitoring

See [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed deployment instructions.

## License
[LICENSE](./LICENSE.md)
