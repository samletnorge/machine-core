# Machine Core Documentation

## Overview

Machine Core is a flexible agent framework for building AI agents with MCP (Model Context Protocol) integration.

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Configuration](#configuration)
5. [Available Agents](#available-agents)
6. [Creating Custom Agents](#creating-custom-agents)
7. [Architecture](#architecture)
8. [API Reference](#api-reference)

## Introduction

Machine Core provides a clean, flexible architecture for building AI agents with:

- **Clean Architecture** - Separation of infrastructure (AgentCore) and execution patterns (BaseAgent)
- **Flexible Configuration** - Environment variables, direct parameters, or runtime overrides
- **MCP Integration** - Easy integration with MCP servers and tools
- **Multiple Agent Types** - Chat, CLI, Receipt Processor, Twitter Bot, Memory Master, RAG Chat
- **Reusable Package** - Install once, use in multiple projects

## Installation

### From Git Repository

```bash
uv add git+https://github.com/samletnorge/machine-core.git
```

### Local Development

```bash
# Clone the repository
git clone https://github.com/samletnorge/machine-core.git
cd machine-core

# Install dependencies
uv sync
```

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

### Environment Variables

Create a `.env` file:

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

### Direct Parameters

```python
from machine_core import AgentConfig

config = AgentConfig(
    max_iterations=20,
    timeout=3600.0,
    max_tool_retries=10
)
```

## Available Agents

| Agent | Description | Use Case |
|-------|-------------|----------|
| `ChatAgent` | Streaming chat | Streamlit UI, web chat |
| `CLIAgent` | Non-streaming | Terminal, cron jobs |
| `ReceiptProcessorAgent` | Vision + queue | Document analysis |
| `TwitterBotAgent` | Scheduled posting | Social media automation |
| `RAGChatAgent` | Knowledge graph | Q&A, support |
| `MemoryMasterAgent` | Knowledge extraction | Graph maintenance |

### ChatAgent

The ChatAgent provides streaming responses, ideal for real-time chat interfaces.

```python
from machine_core.agents import ChatAgent

agent = ChatAgent()

async for event in agent.run("Tell me about AI"):
    if event['type'] == 'text_delta':
        print(event['content'], end='')
```

### CLIAgent

The CLIAgent provides non-streaming responses, perfect for command-line tools.

```python
from machine_core.agents import CLIAgent

agent = CLIAgent()
result = await agent.run("What is machine learning?")
print(result)
```

### RAGChatAgent

The RAGChatAgent integrates with knowledge graphs for context-aware responses.

```python
from machine_core.agents import RAGChatAgent

agent = RAGChatAgent()
result = await agent.run("Search our documentation for API examples")
```

## Creating Custom Agents

Extend the `BaseAgent` class to create custom agents:

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

### AgentCore

The `AgentCore` class handles infrastructure concerns:
- Loading and validating MCP toolsets
- Configuring model providers
- Setting up embedding backends
- Creating agent instances

### BaseAgent

The `BaseAgent` class provides execution patterns:
- Abstract `run()` method for implementations
- `run_query()` for synchronous execution
- `run_query_stream()` for streaming execution
- Helper methods for common tasks

### ConcreteAgent

Concrete agent implementations extend `BaseAgent` and implement the `run()` method with specific logic.

## API Reference

### AgentConfig

Configuration for agent behavior.

**Parameters:**
- `max_iterations` (int): Maximum number of tool iterations (default: 10)
- `timeout` (float): Timeout in seconds (default: 604800.0)
- `max_tool_retries` (int): Maximum tool retry attempts (default: 15)
- `allow_sampling` (bool): Allow response sampling (default: True)

### AgentCore

Core infrastructure for agent creation.

**Methods:**
- `create_agent(system_prompt, mcp_config_path)`: Create an agent instance

### BaseAgent

Base class for all agents.

**Abstract Methods:**
- `run(task)`: Execute agent logic (must be implemented)

**Methods:**
- `run_query(task)`: Execute synchronous query
- `run_query_stream(task)`: Execute streaming query

## License

See [LICENSE.md](../LICENSE.md) for details.
