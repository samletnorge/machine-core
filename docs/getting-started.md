# Getting Started

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Access to at least one LLM provider (Ollama runs locally, others need API keys)

## Installation

### As a Dependency

Add machine-core to any Python project:

```bash
uv add git+https://github.com/samletnorge/machine-core.git
```

This pulls machine-core and its transitive dependency `model-providers` from Git.

### For Local Development

```bash
git clone https://github.com/samletnorge/machine-core.git
cd machine-core
uv sync
```

### Private Repository Access

If using Docker or CI, you need a GitHub token for the private `model-providers` dependency:

```bash
export GITHUB_TOKEN=your_token
uv sync  # or docker-compose up
```

## Your First Agent

### 1. Set Up a Provider

The simplest setup uses Ollama (local, no API key):

```bash
# .env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
```

Or use Google Gemini (cloud, free tier available):

```bash
# .env
LLM_PROVIDER=google
GCP_API_KEY=your-api-key
```

See [Providers](providers.md) for all 7 LLM backends.

### 2. Streaming Chat Agent

```python
import asyncio
from machine_core.agents import ChatAgent

async def main():
    agent = ChatAgent()

    async for event in agent.run("Explain how transformers work"):
        if event["type"] == "text_delta":
            print(event["content"], end="", flush=True)
        elif event["type"] == "tool_call":
            print(f"\n[Tool: {event['tool_name']}]")
        elif event["type"] == "final":
            print(f"\n\nTokens used: {event['usage']}")

asyncio.run(main())
```

### 3. Non-Streaming CLI Agent

```python
import asyncio
from machine_core.agents import CLIAgent

async def main():
    agent = CLIAgent()
    result = await agent.run("What is the capital of Norway?")
    print(result.output)

asyncio.run(main())
```

### 4. Custom Agent

```python
import asyncio
from machine_core.core.agent_base import BaseAgent

class SummaryAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            system_prompt="You are a concise summarizer. Respond in 2-3 sentences max.",
            mcp_config_path="mcp.json",
        )

    async def run(self, text: str):
        result = await self.run_query(f"Summarize: {text}")
        return result

async def main():
    agent = SummaryAgent()
    result = await agent.run("Long article text here...")
    print(result.output)

asyncio.run(main())
```

## Project Structure

A typical project using machine-core:

```
my-project/
  pyproject.toml          # depends on machine-core (git)
  mcp.json                # MCP server config (optional)
  .env                    # provider credentials
  src/
    my_project/
      agent.py            # subclass BaseAgent
      main.py             # entry point
```

Minimal `pyproject.toml`:

```toml
[project]
name = "my-project"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["machine-core"]

[tool.uv.sources]
machine-core = { git = "https://github.com/samletnorge/machine-core.git" }

[build-system]
requires = ["uv_build>=0.8.17,<0.9.0"]
build-backend = "uv_build"
```

Minimal `mcp.json`:

```json
{
  "servers": {
    "my-tools": {
      "type": "http",
      "url": "https://my-mcp-server.example.com/mcp"
    }
  }
}
```

## Next Steps

- [Architecture](architecture.md) -- Understand how AgentCore, BaseAgent, and tool modes work.
- [Configuration](configuration.md) -- Full environment variable reference.
- [MCP Toolsets](tools/mcp-toolsets.md) -- Connect to MCP tool servers.
- [Examples](examples.md) -- See how production projects use machine-core.
