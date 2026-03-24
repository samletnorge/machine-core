# Architecture

## Overview

Machine Core has a layered architecture with clear separation of concerns:

```
model-providers (external)     Provider abstraction: 7 LLM + 3 embedding backends
        |
        v
    AgentCore                  Infrastructure: model init, MCP loading, embedding setup
        |
        v
    BaseAgent                  Execution patterns: run_query, run_query_stream, run_query_iter
        |
        v
  Concrete Agents              Domain logic: ChatAgent, CLIAgent, your custom agents
```

Supporting modules operate alongside this chain:

```
FileProcessor                  PDF/OCR/VLM file handling
OpenAPI Tools                  Generate pydantic-ai Tools from OpenAPI specs
VectorStore + Embedder         Multi-table LanceDB vector search
ToolFilterManager              RAG-based tool selection (OpenAPI + MCP)
DocumentStore                  Single-table document RAG facade
```

## The Inheritance Chain

### AgentCore

`AgentCore` (`core/agent_core.py`) is the infrastructure layer. It handles everything that happens before an agent can answer a question:

1. **Tool setup** -- Loads MCP toolsets from config, validates schemas, and/or accepts dynamic `Tool` objects.
2. **Model setup** -- Calls `model_providers.get_llm_provider()` which returns a fully-constructed pydantic-ai model object (provider-agnostic).
3. **Embedding setup** -- Calls `model_providers.get_embedding_provider()` for vector operations.
4. **Agent creation** -- Creates a `pydantic_ai.Agent` with the model, tools, toolsets, and system prompt.

```python
# AgentCore sets these attributes:
self.agent_config    # AgentConfig instance
self.system_prompt   # System prompt string
self.tools           # List[Tool] - dynamic tools
self.toolsets        # List - MCP toolsets
self.model           # Fully-constructed pydantic-ai model (provider-agnostic)
self.provider_type   # "openai" | "google" | "anthropic"
self.embedding       # Embedding provider instance (or None)
self.agent           # pydantic_ai.Agent instance
self.usage           # RequestUsage tracker
self.message_history # Conversation history
```

`AgentCore` also provides `rebuild_agent()` for per-request tool changes:

```python
agent_core.rebuild_agent(
    tools=new_dynamic_tools,       # Replace dynamic tools
    toolsets=filtered_mcp_toolsets, # Replace MCP toolsets
    system_prompt="New prompt",    # Change system prompt
    retries=30,                    # Override retry count
)
```

### BaseAgent

`BaseAgent` (`core/agent_base.py`) extends `AgentCore` with execution patterns. It is an abstract class -- you must implement `run()`.

| Method | Returns | Use Case |
|--------|---------|----------|
| `run_query(query, image_paths)` | `AgentRunResult` or `{"output": "Error: ..."}` | Single complete response |
| `run_query_stream(query, image_paths)` | Async generator of event dicts | Real-time streaming |
| `run_query_iter(query)` | Async generator of `(node, step_num)` | Step-by-step control |
| `get_server_info()` | `list[dict]` | MCP server introspection |

Streaming events from `run_query_stream()`:

| Event Type | Fields | Description |
|------------|--------|-------------|
| `text_delta` | `content` | Text chunk |
| `thinking_delta` | `content` | Reasoning/thinking chunk |
| `tool_call` | `tool_name`, `tool_args` | Tool invocation |
| `tool_result` | `tool_name`, `content` | Tool response |
| `final` | `content`, `thinking`, `usage` | Complete response |
| `error` | `content` | Error message |

### Concrete Agents

Subclass `BaseAgent` and implement `run()`:

```python
class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            system_prompt="You are a helpful assistant.",
            mcp_config_path="mcp.json",
        )

    async def run(self, query: str):
        # Use any execution pattern
        return await self.run_query(query)
```

## Tool Modes

Machine Core supports three tool modes, chosen at initialization time.

### MCP Toolsets Mode

The original pattern. Tools come from MCP servers defined in `mcp.json`:

```python
agent = ChatAgent(mcp_config_path="mcp.json")
```

MCP servers are loaded, validated, and wrapped if they have schema issues. The agent's tools are determined at init and remain fixed.

**Used by:** deep-research, multi-agent-dev, mcp-client-chat.

### Dynamic Tools Mode

Tools are pydantic-ai `Tool` objects passed directly. MCP is skipped entirely:

```python
from pydantic_ai import Tool

tools = [
    Tool.from_schema(my_func, name="search", description="Search docs", json_schema={...}),
]
agent_core = AgentCore(tools=tools, system_prompt="...")
```

When only `tools=` is provided (no `tools_urls`), MCP loading is skipped completely.

**Used by:** ai-accounting-agent (OpenAPI-generated tools).

### Hybrid Mode

Both MCP toolsets and dynamic tools in the same agent:

```python
agent_core = AgentCore(
    tools=dynamic_tools,         # pydantic-ai Tool objects
    tools_urls=mcp_server_list,  # MCP server configs
    system_prompt="...",
)
```

The agent gets both MCP tools (from servers) and dynamic tools (from code). Use `rebuild_agent()` with both `tools=` and `toolsets=` to update them per request.

## Provider Abstraction

Machine Core is completely provider-agnostic. The integration point is a single function call in `AgentCore.__init__()`:

```python
from model_providers import get_llm_provider, LLMProviderConfig

cfg = LLMProviderConfig.from_env()   # Reads LLM_PROVIDER, LLM_MODEL, etc.
resolved = get_llm_provider(cfg)     # Returns ResolvedProvider

self.model = resolved.model          # OpenAIChatModel, GoogleModel, or AnthropicModel
self.provider_type = resolved.provider_type  # "openai", "google", or "anthropic"
```

`model-providers` returns a **fully-constructed** pydantic-ai model object with settings baked in. Machine Core never imports `OpenAIChatModel`, `GoogleModel`, or `AnthropicModel` -- it just passes `resolved.model` to `pydantic_ai.Agent()`.

Switching providers requires only environment variable changes:

```bash
# Switch from Ollama to Google Gemini
LLM_PROVIDER=google
GCP_API_KEY=your-key

# Switch to Azure OpenAI
LLM_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
```

See [Providers](providers.md) for full provider details.

## Module Map

```
machine_core/
  __init__.py              14 public exports
  core/
    config.py              AgentConfig, MCPServerModel, system prompts
    agent_core.py          AgentCore: init + rebuild_agent
    agent_base.py          BaseAgent: run_query, run_query_stream, run_query_iter
    mcp_setup.py           MCP config loading, ToolFilterWrapper, validation
    openapi_tools.py       generate_tools_from_openapi, fetch_openapi_spec
    tool_filter.py         ToolFilterManager, ToolFilterResult, filter_mcp_toolsets
    vector_store.py        Embedder, VectorStore, SearchResult
    document_store.py      DocumentStore
    file_processor.py      FileProcessor, ProcessedFile
  agents/
    chat_agent.py          ChatAgent (streaming)
    cli_agent.py           CLIAgent (non-streaming)
    receipt_processor_agent.py   Vision + queue loop
    twitter_bot_agent.py         Scheduled tweet generation
    rag_chat_agent.py            Neo4j knowledge graph chat
    memory_master_agent.py       Knowledge graph maintenance
```

## Data Flow

### MCP Toolsets Mode (e.g., deep-research)

```
Environment vars --> LLMProviderConfig.from_env()
                        |
                        v
                   get_llm_provider() --> ResolvedProvider(model=..., provider_type=...)
                        |
mcp.json --> load_mcp_servers_from_config() --> setup_mcp_toolsets() --> validate_and_fix_toolsets()
                        |                                                        |
                        v                                                        v
                   AgentCore.__init__()  <----- model + toolsets -------+
                        |
                        v
                   BaseAgent.run_query() --> Agent.run() --> LLM + Tool calls --> Response
```

### Dynamic Tools Mode (e.g., ai-accounting-agent)

```
Environment vars --> AgentCore(tools=[], system_prompt=...)   # init once
                        |
Per request:            |
  prompt --> ToolFilterManager.filter(prompt) --> ToolFilterResult
                                                       |
  OpenAPI spec --> generate_tools_from_openapi(spec, filter=result.by_source["openapi"])
                                                       |
                        +---------- tools ------------+
                        |
                   agent_core.rebuild_agent(tools=filtered_tools)
                        |
                   Agent.run(prompt) --> LLM + Tool calls --> Response
```

### Mixed Mode (OpenAPI + MCP)

```
Per request:
  prompt --> ToolFilterManager.filter(prompt) --> ToolFilterResult
                                                       |
                                              +--------+--------+
                                              |                 |
                                         by_source["openapi"]  by_source["mcp"]
                                              |                 |
                                              v                 v
            generate_tools_from_openapi(      filter_mcp_toolsets(
              spec, tool_filter=...)            toolsets, relevant_names=...)
                        |                             |
                        v                             v
                   agent_core.rebuild_agent(tools=..., toolsets=...)
```
