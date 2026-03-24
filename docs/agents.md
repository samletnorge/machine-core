# Agents

## BaseAgent

`BaseAgent` is the abstract base class for all agents. It extends `AgentCore` with execution patterns and requires you to implement `run()`.

```python
from machine_core.core.agent_base import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            model_name=None,              # Override model (or None for env default)
            system_prompt="You are ...",  # System instructions
            mcp_config_path="mcp.json",   # MCP server config file
            agent_config=None,            # AgentConfig (or None for env default)
        )

    async def run(self, query: str):
        """Required: implement your execution logic."""
        return await self.run_query(query)
```

### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | `str \| None` | `None` | Override model name. If `None`, uses `LLM_MODEL` env var. |
| `tools_urls` | `list \| None` | `None` | MCP server configs. If `None`, loads from `mcp_config_path`. |
| `tools` | `List[Tool] \| None` | `None` | Dynamic pydantic-ai Tool objects. |
| `mcp_config_path` | `str` | `"mcp.json"` | Path to MCP config file. |
| `system_prompt` | `str` | `""` | System prompt for the LLM. |
| `agent_config` | `AgentConfig \| None` | `None` | Runtime config. If `None`, loads from env. |

### Execution Methods

#### `run_query(query, image_paths=None)`

Non-streaming single query with retry logic. Returns the complete response.

```python
result = await agent.run_query("What is the capital of France?")
print(result.output)  # "The capital of France is Paris."
```

With images (vision models):

```python
result = await agent.run_query(
    "What's in this image?",
    image_paths=["/path/to/photo.jpg"]
)
```

Returns `AgentRunResult` on success, or `{"output": "Error: ..."}` on failure.

#### `run_query_stream(query, image_paths=None)`

Async generator yielding streaming events. Use for real-time UIs.

```python
async for event in agent.run_query_stream("Explain quantum computing"):
    match event["type"]:
        case "text_delta":
            print(event["content"], end="", flush=True)
        case "thinking_delta":
            print(f"[thinking: {event['content']}]")
        case "tool_call":
            print(f"\n> Calling {event['tool_name']}({event['tool_args']})")
        case "tool_result":
            print(f"< {event['tool_name']}: {event['content'][:100]}")
        case "final":
            print(f"\n\nDone. Tokens: {event['usage']}")
        case "error":
            print(f"Error: {event['content']}")
```

#### `run_query_iter(query)`

Step-by-step async generator yielding `(node, step_num)` tuples. Use for fine-grained control over the agent loop.

```python
async for node, step_num in agent.run_query_iter("Research this topic"):
    print(f"Step {step_num}: {type(node).__name__}")
```

#### `get_server_info()`

Returns info about connected MCP servers and their tools.

```python
servers = await agent.get_server_info()
for server in servers:
    print(f"{server['server_type']} ({server['server_id']})")
    for tool in server["tools"]:
        print(f"  - {tool['name']}: {tool['description']}")
```

## Built-in Agents

Machine Core ships with six ready-to-use agents.

### ChatAgent

Streaming chat agent. Ideal for web UIs and real-time interfaces.

```python
from machine_core.agents import ChatAgent

agent = ChatAgent(
    model_name=None,              # optional model override
    mcp_config_path="mcp.json",   # MCP config
    agent_config=None,            # optional AgentConfig
)

# run() is an async generator
async for event in agent.run("Tell me about Norway"):
    if event["type"] == "text_delta":
        print(event["content"], end="")
```

**System prompt:** "You are a helpful AI assistant with access to various tools and a knowledge base."

### CLIAgent

Non-streaming agent. Returns complete responses. Good for scripts, cron jobs, and CLI tools.

```python
from machine_core.agents import CLIAgent

agent = CLIAgent()
result = await agent.run("Summarize this article", image_paths=["/path/to/doc.pdf"])
print(result.output)
```

**System prompt:** "You are a helpful AI assistant."

### ReceiptProcessorAgent

Vision-based receipt processor that loops over a queue. Uses the `SORTIFY_PROMPT` system prompt to extract structured JSON from receipt images.

```python
from machine_core.agents import ReceiptProcessorAgent

agent = ReceiptProcessorAgent()
# run() loops over a queue (override _get_next_receipt and _save_to_db)
await agent.run()
```

**Note:** `_get_next_receipt()` and `_save_to_db()` are stubs. Override them for your storage backend.

### TwitterBotAgent

Scheduled tweet generation with daily limits.

```python
from machine_core.agents import TwitterBotAgent

agent = TwitterBotAgent()
await agent.run()  # Loops with 1-2 hour delays between tweets
```

### RAGChatAgent

Chat agent with Neo4j knowledge graph integration.

```python
from machine_core.agents import RAGChatAgent

agent = RAGChatAgent()
async for event in agent.run("What do we know about customer X?"):
    ...
```

Uses `mcp_neo4j.json` for Neo4j MCP server connection.

### MemoryMasterAgent

Continuous background agent that extracts entities, relationships, and facts from conversations and stores them in a knowledge graph.

```python
from machine_core.agents import MemoryMasterAgent

agent = MemoryMasterAgent()
await agent.run()  # Infinite loop: process conversations, sleep 5 min
```

## Creating Custom Agents

### Subclassing BaseAgent (Recommended)

For agents that use MCP tools or need streaming:

```python
from machine_core.core.agent_base import BaseAgent

class ResearchAgent(BaseAgent):
    def __init__(self, model_name=None):
        super().__init__(
            model_name=model_name,
            system_prompt=(
                "You are a research assistant. Use available tools to find "
                "information, then synthesize a comprehensive answer."
            ),
            mcp_config_path="mcp_research.json",
        )

    async def run(self, query: str):
        """Run a research query and return structured results."""
        result = await self.run_query(query)
        return {
            "answer": result.output,
            "usage": {
                "request_tokens": self.usage.request_tokens,
                "response_tokens": self.usage.response_tokens,
            },
        }
```

### Using AgentCore Directly

For dynamic tool scenarios where you need `rebuild_agent()` per request:

```python
from machine_core import AgentCore, AgentConfig

config = AgentConfig(max_tool_retries=30, timeout=300)
agent_core = AgentCore(
    tools=[],                     # Start empty, populate per request
    system_prompt="You are ...",
    agent_config=config,
)

# Per request: swap tools and run
agent_core.rebuild_agent(tools=new_tools)
result = await agent_core.agent.run("Do the thing")
```

See [Examples](examples.md) for the full ai-accounting-agent pattern.

### Using Multiple Agents Together

```python
class PlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__(system_prompt="You create research plans.")

    async def run(self, query):
        return await self.run_query(f"Create a plan to research: {query}")

class WriterAgent(BaseAgent):
    def __init__(self):
        super().__init__(system_prompt="You write reports from research data.")

    async def run(self, research_data):
        return await self.run_query(f"Write a report: {research_data}")

# Orchestrate
planner = PlannerAgent()
writer = WriterAgent()

plan = await planner.run("AI safety")
report = await writer.run(plan.output)
```

## Image / Vision Support

Any agent can process images through `run_query()` or `run_query_stream()`:

```python
result = await agent.run_query(
    "Describe what you see",
    image_paths=[
        "/path/to/local/image.jpg",         # Local file
        "https://example.com/photo.png",     # URL
        "data:image/png;base64,iVBOR...",    # Data URL
    ]
)
```

Images are processed by `FileProcessor.prepare_for_vlm()` which converts all sources to base64 data URLs suitable for pydantic-ai's `ImageUrl` type. Requires a vision-capable model.

## System Prompts

Machine Core includes several built-in system prompts in `core/config.py`:

| Constant | Lines | Purpose |
|----------|-------|---------|
| `SYSTEM_PROMPT` | 18 | General multi-modal agent |
| `DRIVSTOFF_PROMPT` | 68 | Fuel price extraction from gas station images |
| `ALTLOKALT_PROMPT` | 58 | Company info extraction from flyers |
| `SORTIFY_PROMPT` | 59 | Receipt data extraction (JSON) |
| `PHONECTRL_PROMPT` | 83 | Visual object localization |

Import and use:

```python
from machine_core import SYSTEM_PROMPT  # or import from config directly
from machine_core.core.config import SORTIFY_PROMPT
```
