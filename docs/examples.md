# Examples

Real-world usage examples from production projects that use `machine-core`.

## Overview

`machine-core` supports two tool modes that are demonstrated across four downstream projects:

| Project | Mode | Pattern | Description |
|---------|------|---------|-------------|
| deep-research | MCP toolsets | `BaseAgent` subclass | Multi-agent research with divide-and-conquer |
| mcp-client-chat | MCP toolsets | `BaseAgent` subclass | Streamlit chat with dynamic provider selection |
| multi-agent-dev | MCP toolsets | `BaseAgent` subclass | GitHub-integrated coding + review agents |
| ai-accounting-agent | Dynamic tools | `AgentCore` direct | Per-request OpenAPI tool generation with RAG filtering |

---

## MCP Toolsets Mode: BaseAgent Subclass

### Example 1: Simple Streaming Agent (mcp-client-chat)

The simplest pattern — a `BaseAgent` subclass with streaming output.

```python
# mcp-client-chat/src/mcp_client_chat/agents/chat_agent.py

from machine_core.core.agent_base import BaseAgent
from machine_core.core.config import AgentConfig

class ChatAgent(BaseAgent):
    def __init__(
        self,
        model_name=None,
        system_prompt="You are a helpful AI assistant.",
        mcp_config_path="mcp.json",
        agent_config=None,
    ):
        if agent_config is None:
            agent_config = AgentConfig(
                max_iterations=3,
                timeout=60000,
                max_tool_retries=3,
                allow_sampling=True,
            )
        super().__init__(
            model_name=model_name,
            system_prompt=system_prompt,
            mcp_config_path=mcp_config_path,
            agent_config=agent_config,
        )

    async def run(self, query: str, image_paths=None):
        async for event in self.run_query_stream(query, image_paths):
            yield event
```

**Consumer (Streamlit):**

```python
async for event in agent.run(prompt, image_paths=image_paths):
    if event["type"] == "text_delta":
        response_placeholder.markdown(accumulated_text)
    elif event["type"] == "tool_call":
        st.write(f"Calling: {event['tool_name']}")
    elif event["type"] == "final":
        final_text = event["content"]
```

---

### Example 2: Multi-Agent Research (deep-research)

Multiple agents coordinate to break down a research task, execute sub-tasks in parallel, then synthesize results.

```python
# deep-research/src/deep_research/coordinator.py

from machine_core.core.agent_base import BaseAgent

class SubAgent(BaseAgent):
    """Researches a single subtask using MCP tools."""

    def __init__(self, subtask_id, subtask_title, subtask_description,
                 original_query, research_plan):
        # Build a detailed prompt from template
        prompt = SUBAGENT_PROMPT_TEMPLATE.format(
            subtask_id=subtask_id,
            subtask_title=subtask_title,
            subtask_description=subtask_description,
            original_query=original_query,
            research_plan=research_plan,
        )
        super().__init__(
            model_name=os.getenv("LLM_MODEL"),
            system_prompt=prompt,
            mcp_config_path="mcp_researcher.json",
        )
        self.subtask_id = subtask_id

    async def run(self, query: str) -> str:
        result = await self.run_query(query)
        if isinstance(result, dict) and "error" in result:
            return f"Error: {result['error']}"
        return result.output if hasattr(result, "output") else str(result)


class CoordinatorAgent(BaseAgent):
    """Spawns SubAgents in parallel, then synthesizes their reports."""

    def __init__(self, subtasks, original_query, research_plan):
        self.subtasks = subtasks
        self.original_query = original_query
        self.research_plan = research_plan
        super().__init__(
            model_name=os.getenv("LLM_MODEL"),
            system_prompt="You are a research coordinator...",
            mcp_config_path="mcp_researcher.json",
        )

    async def run(self) -> str:
        # Launch all sub-agents in parallel
        sub_agents = []
        for st in self.subtasks:
            agent = SubAgent(
                subtask_id=st["id"],
                subtask_title=st["title"],
                subtask_description=st["description"],
                original_query=self.original_query,
                research_plan=self.research_plan,
            )
            sub_agents.append(agent.run(st["description"]))

        results = await asyncio.gather(*sub_agents, return_exceptions=True)

        # Synthesize results
        combined = "\n\n".join(str(r) for r in results)
        synthesis_prompt = COORDINATOR_PROMPT_TEMPLATE.format(
            original_query=self.original_query,
            combined_research=combined,
        )
        final = await self.run_query(synthesis_prompt)
        return final.output if hasattr(final, "output") else str(final)
```

---

### Example 3: GitHub Webhook Agents (multi-agent-dev)

Two specialized agents that respond to GitHub events.

```python
# multi-agent-dev/src/multi_agent_dev/agents/__init__.py

from machine_core.core.agent_base import BaseAgent
from machine_core.core.config import AgentConfig

class CodingAgent(BaseAgent):
    def __init__(self, model_name=None, mcp_config_path="mcp.json",
                 agent_config=None):
        super().__init__(
            model_name=model_name or os.getenv("LLM_MODEL"),
            system_prompt="You are an expert software developer...",
            mcp_config_path=mcp_config_path,
            agent_config=agent_config,
        )

    async def run(self, task: str):
        async for event in self.run_query_stream(task):
            yield event


class ReviewAgent(BaseAgent):
    def __init__(self, model_name=None, mcp_config_path="mcp.json",
                 agent_config=None):
        super().__init__(
            model_name=model_name or os.getenv("LLM_MODEL"),
            system_prompt="You are an expert code reviewer...",
            mcp_config_path=mcp_config_path,
            agent_config=agent_config,
        )

    async def run(self, task: str):
        async for event in self.run_query_stream(task):
            yield event
```

**Platform setup with custom config:**

```python
# multi-agent-dev/src/multi_agent_dev/main.py

config = AgentConfig(
    max_iterations=20,
    timeout=3600.0,
    max_tool_retries=5,
)

coding_agent = CodingAgent(
    model_name=os.getenv("LLM_MODEL"),
    mcp_config_path=mcp_config,
    agent_config=config,
)
review_agent = ReviewAgent(
    model_name=os.getenv("LLM_MODEL"),
    mcp_config_path=mcp_config,
    agent_config=config,
)
```

---

### Example 4: Dynamic Provider Selection (mcp-client-chat)

The Streamlit app dynamically discovers available providers from `model-providers` and configures them at runtime.

```python
# mcp-client-chat/src/mcp_client_chat/app.py

from model_providers import (
    get_available_llm_providers,
    get_available_llm_models,
    get_available_embedding_providers,
    get_available_embedding_models,
)

# Sidebar dropdowns auto-discover providers
available_providers = get_available_llm_providers()
selected_provider = st.sidebar.selectbox("LLM Provider", available_providers)

available_models = get_available_llm_models(selected_provider)
selected_model = st.sidebar.selectbox("Model", available_models)

# Set environment before agent creation
os.environ["LLM_PROVIDER"] = selected_provider
os.environ["LLM_MODEL"] = selected_model

# Conditional credential fields
if selected_provider in ["google", "vertex-gemini", "vertex-claude"]:
    api_key = st.sidebar.text_input("GCP API Key", type="password")
    if api_key:
        os.environ["GCP_API_KEY"] = api_key

# Agent picks up env vars automatically
agent = ChatAgent(mcp_config_path="mcp.json")
```

---

## Dynamic Tools Mode: AgentCore Direct

### Example 5: Per-Request Tool Generation (ai-accounting-agent)

The most advanced pattern — uses `AgentCore` directly with `rebuild_agent()` to swap tools per request based on RAG filtering.

```python
# ai-accounting-agent/src/ai_accounting_agent/coordinator.py

from machine_core import (
    AgentCore, AgentConfig,
    generate_tools_from_openapi, fetch_openapi_spec,
    Embedder, VectorStore, ToolFilterManager,
)
from model_providers import get_embedding_provider, EmbeddingProviderConfig

# Essential tools always included regardless of RAG relevance
ESSENTIAL_TOOLS = {
    "LedgerAccount_search", "Invoice_search", "Customer_search",
    "Voucher_search", "Product_search", "Order_search",
    # ... ~158 tools
}

# Lazy singletons with asyncio locks
_agent_core = None
_agent_core_lock = asyncio.Lock()

async def _get_agent_core():
    global _agent_core
    async with _agent_core_lock:
        if _agent_core is None:
            config = AgentConfig(max_iterations=30, timeout=300.0,
                                 max_tool_retries=30, allow_sampling=True)
            _agent_core = AgentCore(
                tools=[],  # No tools initially
                system_prompt=ACCOUNTING_SYSTEM_PROMPT,
                agent_config=config,
            )
        return _agent_core


async def _get_tool_filter_manager():
    global _tool_filter_manager
    async with _filter_lock:
        if _tool_filter_manager is None:
            emb_config = EmbeddingProviderConfig.from_env()
            emb_provider = get_embedding_provider(emb_config)
            embedder = Embedder(emb_provider)
            vs = VectorStore(db_path=".vector_store", embedder=embedder)
            _tool_filter_manager = ToolFilterManager(
                embedder=embedder, vector_store=vs,
            )
        return _tool_filter_manager


async def run_accounting_task(prompt: str, context: str = "") -> str:
    agent_core = await _get_agent_core()
    spec = await _get_openapi_spec()

    # 1. Index tools (once)
    manager = await _get_tool_filter_manager()
    if not manager.is_indexed:
        await manager.index_openapi(spec)

    # 2. RAG filter: find relevant tools for this prompt
    result = await manager.filter(
        task_prompt=prompt,
        top_k=200,
        essential_tools=ESSENTIAL_TOOLS,
    )

    # 3. Generate only relevant tools
    auth_headers = _make_auth_headers()
    tools = generate_tools_from_openapi(
        spec, base_url=TRIPLETEX_API_URL,
        auth_headers=auth_headers,
        tool_filter=result.names,
    )

    # 4. Rebuild agent with filtered tools
    agent_core.rebuild_agent(tools=tools, retries=30)

    # 5. Execute
    full_prompt = f"{context}\n\nTask: {prompt}" if context else prompt
    async with agent_core.agent.iter(full_prompt) as run:
        async for node in run:
            # Step-by-step logging
            pass

    return run.result.output
```

**File processing integration (HTTP server):**

```python
# ai-accounting-agent/src/ai_accounting_agent/http_server.py

from machine_core import FileProcessor

@app.post("/solve")
async def solve(request: SolveRequest):
    context_parts = []

    # Process uploaded files using machine-core's FileProcessor
    if request.files:
        file_dicts = [
            {"filename": f.filename, "content": f.content,
             "mime_type": f.mime_type}
            for f in request.files
        ]
        result = FileProcessor.process_files(file_dicts)
        for f in result["files"]:
            if f.get("text_content"):
                context_parts.append(
                    f"File '{f['filename']}':\n{f['text_content']}"
                )

    context = "\n\n".join(context_parts)
    answer = await asyncio.wait_for(
        run_accounting_task(request.prompt, context),
        timeout=300.0,
    )
    return SolveResponse(status="completed", answer=answer)
```

---

## MCP Configuration Examples

### HTTP-only servers (mcp-client-chat)

```json
{
    "servers": {
        "internet-mcp": {
            "url": "https://internet-mcp.valiantlynx.com/sse",
            "type": "http"
        },
        "playwright": {
            "url": "https://playwright.valiantlynx.com/sse",
            "type": "http"
        },
        "github": {
            "url": "https://github-mcp.valiantlynx.com/sse",
            "type": "http"
        }
    }
}
```

### Mixed HTTP + stdio servers (multi-agent-dev)

```json
{
    "servers": {
        "internet-mcp": {
            "url": "https://internet-mcp.valiantlynx.com/sse",
            "type": "http"
        },
        "server-github": {
            "url": "npx -y @modelcontextprotocol/server-github",
            "type": "stdio",
            "env": {
                "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
            }
        }
    }
}
```

### Empty config (deep-research)

Used when the agent doesn't need external tools:

```json
{
    "servers": {},
    "inputs": []
}
```

---

## Pattern Summary

### When to use `BaseAgent` subclass:

- Your agent has a fixed set of MCP tools
- You want streaming (`run_query_stream`) or single-shot (`run_query`) execution
- Your tool configuration doesn't change between requests

### When to use `AgentCore` directly:

- You need to swap tools per request (`rebuild_agent()`)
- You're generating tools dynamically (e.g., from OpenAPI specs)
- You need RAG-based tool filtering for large tool sets
- You want full control over the agent lifecycle

### Common patterns across all projects:

1. **Environment-driven provider selection** — all projects use `LLM_PROVIDER`/`LLM_MODEL` env vars
2. **No provider-specific code** — switching providers requires only env var changes
3. **AgentConfig customization** — each project tunes iteration limits and timeouts for its use case
4. **MCP config files** — JSON-based server configuration, loaded automatically
