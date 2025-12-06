"""the machine_core package

Core abstractions for LLM and Embedding models using mcp architecture. to specifically make AI agents easier to build.
"""

from .core.config import AgentConfig, MCPServerModel, SYSTEM_PROMPT
from .core.agent_core import AgentCore

__all__ = [
    "AgentConfig",
    "MCPServerModel", 
    "SYSTEM_PROMPT",
    "AgentCore",
]
