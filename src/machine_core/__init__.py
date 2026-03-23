"""the machine_core package

Core abstractions for LLM and Embedding models using mcp architecture. to specifically make AI agents easier to build.

Supports two tool modes:
- MCP toolsets: loaded from mcp.json (original pattern for tool servers)
- Dynamic tools: pydantic-ai Tool objects passed directly (for OpenAPI tools, per-request tools, etc.)
- Both: combine MCP toolsets + dynamic tools in the same agent
"""

from .core.config import AgentConfig, MCPServerModel, SYSTEM_PROMPT
from .core.agent_core import AgentCore
from .core.agent_base import BaseAgent

__all__ = [
    "AgentConfig",
    "MCPServerModel",
    "SYSTEM_PROMPT",
    "AgentCore",
    "BaseAgent",
]
