# MCP Toolsets

MCP (Model Context Protocol) is the primary tool integration mechanism. Machine Core loads MCP servers from a JSON config, creates toolsets, validates their schemas, and passes them to the pydantic-ai Agent.

## Configuration File

Create an `mcp.json` file in your project root:

```json
{
  "servers": {
    "web-search": {
      "type": "http",
      "url": "https://search.example.com/mcp"
    },
    "chart-generator": {
      "type": "sse",
      "url": "https://charts.example.com/sse"
    },
    "local-tools": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "python", "my_server.py"],
      "env": {
        "DATABASE_URL": "postgresql://localhost/mydb"
      }
    }
  }
}
```

### Transport Types

| Type | Class | Use Case |
|------|-------|----------|
| `http` | `MCPServerStreamableHTTP` | Remote servers with HTTP Streamable transport |
| `sse` | `MCPServerSSE` | Remote servers with Server-Sent Events transport |
| `stdio` | `MCPServerStdio` | Local processes communicating via stdin/stdout |

### stdio Servers

For `stdio` type, the `command` and `args` fields are joined into a command line. Environment variables in `env` are merged with `os.environ`:

```json
{
  "servers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/data"],
      "env": {
        "NODE_ENV": "production"
      }
    }
  }
}
```

## Loading MCP Servers

Machine Core loads MCP configs automatically in `AgentCore.__init__()`. You can also load them manually:

```python
from machine_core.core.mcp_setup import (
    load_mcp_servers_from_config,
    setup_mcp_toolsets,
    validate_and_fix_toolsets,
)

# Load server definitions from mcp.json
server_configs = load_mcp_servers_from_config("mcp.json")

# Create toolset objects
toolsets = setup_mcp_toolsets(
    server_configs,
    timeout=604800.0,      # 1 week
    max_retries=15,
    allow_sampling=True,
)

# Validate schemas and wrap problematic tools
validated_toolsets, warnings = await validate_and_fix_toolsets(toolsets)
```

## Schema Validation

Some MCP servers have tools with malformed JSON schemas (e.g., empty `type` arrays from Optional parameters). Machine Core validates every tool's `inputSchema` and wraps problematic toolsets with `ToolFilterWrapper` to exclude broken tools while keeping valid ones operational.

Validation checks:
- Missing or empty `type` field in property definitions
- Empty type arrays (`"type": []`)

If issues are found, the toolset is wrapped (not removed), so valid tools from the same server still work.

## ToolFilterWrapper

`ToolFilterWrapper` wraps an MCP toolset and filters out specific tools by name. It implements `AbstractToolset` from pydantic-ai.

```python
from machine_core.core.mcp_setup import ToolFilterWrapper

# Hide specific tools from the LLM
wrapper = ToolFilterWrapper(
    wrapped_toolset=original_toolset,
    problematic_tool_names={"broken_tool_1", "broken_tool_2"},
)

# get_tools() returns only non-filtered tools
tools = await wrapper.get_tools(ctx)

# call_tool() raises ValueError for filtered tools
await wrapper.call_tool("broken_tool_1", {}, ctx, tool)  # raises ValueError
```

The wrapper delegates all other attributes to the wrapped toolset via `__getattr__`.

### Two Uses of ToolFilterWrapper

1. **Schema validation** (automatic): Wraps toolsets that have tools with malformed schemas. Applied during `validate_and_fix_toolsets()`.

2. **RAG-based filtering** (via `filter_mcp_toolsets()`): Wraps toolsets to hide tools that aren't relevant to the current query. See [Tool Filtering](tool-filtering.md).

## Passing Toolsets to Agents

### Via config file (typical):

```python
class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            system_prompt="...",
            mcp_config_path="mcp_custom.json",  # loads from this file
        )
```

### Via tools_urls parameter:

```python
from machine_core import MCPServerModel

servers = [
    MCPServerModel(url="https://server1.example.com/mcp", type="http"),
    MCPServerModel(url="https://server2.example.com/sse", type="sse"),
]

agent = MyAgent(tools_urls=servers)
```

### Programmatically (full control):

```python
from machine_core import AgentCore

agent_core = AgentCore(
    tools_urls=servers,
    system_prompt="...",
)

# Access toolsets
print(f"Loaded {len(agent_core.toolsets)} MCP toolset(s)")
print(f"Warnings: {agent_core.get_validation_warnings()}")
```

## Inspecting Connected Servers

```python
servers = await agent.get_server_info()
for server in servers:
    print(f"Server: {server['server_type']} ({server['server_id']})")
    for tool in server["tools"]:
        print(f"  {tool['name']}: {tool['description']}")
```

Output:

```
Server: MCPServerStreamableHTTP (https://search.example.com/mcp)
  web_search: Search the web for information
  get_page: Fetch and extract content from a URL
Server: MCPServerStdio (npx -y @modelcontextprotocol/server-filesystem)
  read_file: Read a file from the filesystem
  write_file: Write content to a file
```

## Timeouts and Retries

All MCP toolsets inherit timeout and retry settings from `AgentConfig`:

| Setting | Default | Source |
|---------|---------|--------|
| Connection timeout | 604,800s (1 week) | `AGENT_TIMEOUT` |
| Read timeout | 604,800s | Same as timeout |
| Max retries | 15 | `AGENT_MAX_TOOL_RETRIES` |
| Allow sampling | `true` | `AGENT_ALLOW_SAMPLING` |

Override via `AgentConfig`:

```python
from machine_core import AgentConfig

config = AgentConfig(timeout=60.0, max_tool_retries=3)
agent = ChatAgent(agent_config=config)
```

## Real-World Example: deep-research

deep-research uses separate MCP configs for different agent roles:

```python
# mcp_researcher.json - research tools
class SubAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            model_name=os.getenv("LLM_MODEL"),
            system_prompt=SUBAGENT_PROMPT_TEMPLATE.format(task=task),
            mcp_config_path="mcp_researcher.json",
        )
```

The coordinator agent runs multiple sub-agents in parallel, each with their own MCP connections:

```python
tasks = [sub_agent.run_query(task["task"]) for sub_agent in sub_agents]
results = await asyncio.gather(*tasks)
```
