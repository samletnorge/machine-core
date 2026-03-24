"""the machine_core package

Core abstractions for LLM and Embedding models using mcp architecture. to specifically make AI agents easier to build.

Supports two tool modes:
- MCP toolsets: loaded from mcp.json (original pattern for tool servers)
- Dynamic tools: pydantic-ai Tool objects passed directly (for OpenAPI tools, per-request tools, etc.)
- Both: combine MCP toolsets + dynamic tools in the same agent

v0.4.0 adds:
- FileProcessor: unified file handling (PDF/OCR/VLM preparation)
- OpenAPI tools: generate pydantic-ai Tools from OpenAPI specs
- VectorStore + Embedder: multi-table LanceDB vector search
- ToolFilterManager: RAG-based tool filtering for OpenAPI + MCP
- DocumentStore: convenience facade for single-table document RAG

v0.4.1 adds:
- filter_mcp_toolsets(): wraps MCP toolsets to hide irrelevant tools after RAG filtering
- rebuild_agent() now accepts toolsets= parameter for mixed-mode (OpenAPI + MCP) filtering
"""

from .core.config import AgentConfig, MCPServerModel, SYSTEM_PROMPT
from .core.agent_core import AgentCore
from .core.agent_base import BaseAgent
from .core.file_processor import FileProcessor, ProcessedFile
from .core.openapi_tools import generate_tools_from_openapi, fetch_openapi_spec
from .core.vector_store import VectorStore, Embedder, SearchResult
from .core.tool_filter import ToolFilterManager, ToolFilterResult, filter_mcp_toolsets
from .core.document_store import DocumentStore

__all__ = [
    # Core (v0.1.0+)
    "AgentConfig",
    "MCPServerModel",
    "SYSTEM_PROMPT",
    "AgentCore",
    "BaseAgent",
    # File processing (v0.4.0)
    "FileProcessor",
    "ProcessedFile",
    # OpenAPI tools (v0.4.0)
    "generate_tools_from_openapi",
    "fetch_openapi_spec",
    # Vector store (v0.4.0)
    "VectorStore",
    "Embedder",
    "SearchResult",
    # Tool filtering (v0.4.0)
    "ToolFilterManager",
    "ToolFilterResult",
    "filter_mcp_toolsets",
    # Document store (v0.4.0)
    "DocumentStore",
]
