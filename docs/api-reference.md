# API Reference

Complete reference for all public classes, methods, functions, and types exported by `machine-core`.

## Public Exports

All symbols listed here are importable from `machine_core`:

```python
from machine_core import (
    AgentConfig, MCPServerModel, SYSTEM_PROMPT,
    AgentCore, BaseAgent,
    FileProcessor, ProcessedFile,
    generate_tools_from_openapi, fetch_openapi_spec,
    VectorStore, Embedder, SearchResult,
    ToolFilterManager, ToolFilterResult, filter_mcp_toolsets,
    DocumentStore,
)
```

---

## Core Classes

### `AgentConfig`

Pydantic model for agent behavior configuration. Source: `core/config.py`.

```python
class AgentConfig(BaseModel):
    max_iterations: int = 10
    timeout: float = 604800.0
    max_tool_retries: int = 15
    allow_sampling: bool = True
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_iterations` | `int` | `10` | Maximum number of tool call iterations per query |
| `timeout` | `float` | `604800.0` | Request timeout in seconds (default: 1 week) |
| `max_tool_retries` | `int` | `15` | Maximum retries for failed tool calls |
| `allow_sampling` | `bool` | `True` | Whether to allow MCP sampling |

**Class method:**

```python
@classmethod
def from_env(cls) -> AgentConfig
```

Loads configuration from environment variables: `AGENT_MAX_ITERATIONS`, `AGENT_TIMEOUT`, `AGENT_MAX_TOOL_RETRIES`, `AGENT_ALLOW_SAMPLING`.

---

### `MCPServerModel`

Pydantic model representing an MCP server configuration entry. Source: `core/config.py`.

```python
class MCPServerModel(BaseModel):
    url: str
    type: str
    env: dict[str, str] | None = None
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | `str` | (required) | Server URL or command string |
| `type` | `str` | (required) | `"http"` or `"stdio"` |
| `env` | `dict[str, str] \| None` | `None` | Environment variables for stdio servers |

---

### `AgentCore`

Core infrastructure class. Handles model resolution, MCP toolset loading, embedding setup, and agent creation. Source: `core/agent_core.py`.

#### Constructor

```python
AgentCore(
    model_name: Optional[str] = None,
    tools_urls: Optional[list] = None,
    tools: Optional[List[Tool]] = None,
    mcp_config_path: str = "mcp.json",
    system_prompt: str = "",
    agent_config: Optional[AgentConfig] = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | `Optional[str]` | `None` | Override model name (falls back to `LLM_MODEL` env var) |
| `tools_urls` | `Optional[list]` | `None` | List of `MCPServerModel` configs (overrides `mcp_config_path`) |
| `tools` | `Optional[List[Tool]]` | `None` | Direct pydantic-ai `Tool` objects (dynamic tools mode) |
| `mcp_config_path` | `str` | `"mcp.json"` | Path to MCP config JSON file |
| `system_prompt` | `str` | `""` | System prompt for the agent |
| `agent_config` | `Optional[AgentConfig]` | `None` | Agent configuration (falls back to `AgentConfig.from_env()`) |

#### Instance Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `agent_config` | `AgentConfig` | Resolved configuration |
| `system_prompt` | `str` | Active system prompt |
| `tools` | `List[Tool]` | Direct tool objects |
| `toolsets` | `list` | MCP toolset objects |
| `validation_warnings` | `list` | Warnings from MCP validation |
| `model` | `object` | Fully-constructed pydantic-ai model (provider-agnostic) |
| `provider_type` | `str` | `"openai"`, `"google"`, or `"anthropic"` |
| `embedding` | `object \| None` | Embedding provider instance |
| `embedding_model_name` | `Optional[str]` | Resolved embedding model name |
| `agent` | `Agent` | The pydantic-ai `Agent` instance |
| `usage` | `RequestUsage` | Accumulated token usage |
| `message_history` | `list` | Conversation message history |

#### Methods

```python
def rebuild_agent(
    self,
    tools: Optional[List[Tool]] = None,
    toolsets: Optional[list] = None,
    system_prompt: Optional[str] = None,
    retries: Optional[int] = None,
) -> None
```

Recreates the internal `Agent` with new tools, toolsets, prompt, or retry count. Pass `None` for any parameter to keep the current value.

```python
def get_validation_warnings(self) -> list[str]
```

Returns any validation warnings from MCP server initialization.

---

### `BaseAgent`

Abstract base class for all agent implementations. Inherits from `AgentCore` and `ABC`. Source: `core/agent_base.py`.

#### Constructor

```python
BaseAgent(
    model_name: Optional[str] = None,
    tools_urls: Optional[list] = None,
    tools: Optional[List[Tool]] = None,
    mcp_config_path: str = "mcp.json",
    system_prompt: str = "",
    agent_config: Optional[AgentConfig] = None,
)
```

Same parameters as `AgentCore.__init__()`.

#### Abstract Methods

```python
async def run(self, *args, **kwargs) -> Any
```

Main execution loop. Must be implemented by subclasses.

#### Query Methods

```python
async def run_query(
    self,
    query: str,
    image_paths: Optional[Union[str, Path, list[Union[str, Path]]]] = None,
) -> Union[dict, AgentRunResult]
```

Execute a single query with automatic retry logic. Supports optional image attachments for vision models.

**Returns:** `AgentRunResult` on success, or `dict` with `{"error": str, "type": str}` on failure.

---

```python
async def run_query_stream(
    self,
    query: str,
    image_paths: Optional[Union[str, Path, list[Union[str, Path]]]] = None,
) -> AsyncGenerator[dict, None]
```

Async generator that yields streaming events during query execution.

**Event types yielded:**

| `type` | Additional Keys | Description |
|--------|----------------|-------------|
| `"text_delta"` | `content: str` | Incremental text output |
| `"thinking_delta"` | `content: str` | Model thinking/reasoning output |
| `"tool_call"` | `tool_name: str, tool_args: dict` | Tool invocation started |
| `"tool_result"` | `tool_name: str, content: str` | Tool returned a result |
| `"final"` | `content: str, thinking: str, usage: dict` | Final complete response |
| `"error"` | `content: str` | Error occurred |

---

```python
async def run_query_iter(
    self,
    query: str,
) -> AsyncGenerator[tuple, None]
```

Low-level async generator that yields `(node, step_num)` tuples for step-by-step control over agent execution.

---

#### Utility Methods

```python
async def cleanup(self) -> None
```

Override to clean up resources before shutdown. Default implementation is a no-op.

```python
async def get_server_info(self) -> list[dict]
```

Returns information about connected MCP servers and their available tools.

**Returns:** List of dicts, each with `name`, `tools` (list of tool dicts), and `error` (if any).

---

## File Processing

### `ProcessedFile`

Dataclass representing a processed file result. Source: `core/file_processor.py`.

```python
@dataclass
class ProcessedFile:
    text: str = ""
    data_url: Optional[str] = None
    mime_type: str = ""
    pages: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | `str` | `""` | Extracted text content |
| `data_url` | `Optional[str]` | `None` | Base64 data URL for VLM consumption |
| `mime_type` | `str` | `""` | Detected MIME type |
| `pages` | `List[Dict[str, Any]]` | `[]` | Per-page data for multi-page documents |
| `error` | `Optional[str]` | `None` | Error message if processing failed |

---

### `FileProcessor`

Static utility class for file processing, OCR, and VLM preparation. All methods are `@staticmethod`. Source: `core/file_processor.py`.

#### Text Extraction

```python
@staticmethod
def extract_text(file_path: Union[str, Path]) -> str
```

Extracts text from PDF, image, text, or CSV files. Uses pdfplumber for PDFs, pytesseract for images. Returns extracted text string.

#### VLM Preparation

```python
@staticmethod
async def prepare_for_vlm(image_source: Union[str, Path]) -> Optional[str]
```

Converts a file, URL, or data URL into a base64 data URL suitable for vision language models. Handles HTTP URLs (downloads image), local files (reads and encodes), and existing data URLs (passes through).

**Returns:** Data URL string (`data:image/png;base64,...`) or `None` on failure.

#### Full Processing

```python
@staticmethod
def process(file_path: Union[str, Path]) -> ProcessedFile
```

Returns both extracted text and data URL for a file.

#### Batch Upload Processing

```python
@staticmethod
def process_files(files: List[Dict[str, str]]) -> Dict[str, Any]
```

Processes a list of base64-encoded file uploads.

**Input format:** Each dict must have `filename`, `content` (base64), and `mime_type`.

**Returns:**
```python
{
    "files_processed": int,
    "total_text_length": int,
    "files": [
        {
            "filename": str,
            "content_type": str,
            "text_content": str,
            "page_count": int,      # PDFs only
            "pages": [...],         # PDFs only
            "error": str | None,
        }
    ]
}
```

#### Individual Attachment

```python
@staticmethod
def process_attachment(
    filename: str,
    content_base64: str,
    mime_type: str,
) -> Dict[str, Any]
```

Processes a single base64-encoded attachment. Returns dict with `filename`, `content_type`, `text_content`, `page_count`, `pages`, `error`.

#### Utility Methods

```python
@staticmethod
def decode_base64_file(content_base64: str) -> bytes
```

Decodes base64 content to bytes. Handles both raw base64 and data URL format.

```python
@staticmethod
def save_file(filename: str, file_bytes: bytes, temp_dir: str = "/tmp") -> str
```

Saves file bytes to disk. Returns the saved file path.

---

## OpenAPI Tools

### `generate_tools_from_openapi`

Source: `core/openapi_tools.py`.

```python
def generate_tools_from_openapi(
    spec: Dict[str, Any],
    base_url: str,
    auth_headers: Optional[Dict[str, str]] = None,
    tool_filter: Optional[set] = None,
) -> List[Tool]
```

Generates pydantic-ai `Tool` objects from an OpenAPI specification. Each endpoint becomes a tool that makes HTTP calls via httpx.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `spec` | `Dict[str, Any]` | (required) | Parsed OpenAPI 3.x specification |
| `base_url` | `str` | (required) | Base URL for API calls |
| `auth_headers` | `Optional[Dict[str, str]]` | `None` | Headers added to every request (e.g., `{"Authorization": "Bearer ..."}`) |
| `tool_filter` | `Optional[set]` | `None` | If provided, only generate tools whose `operationId` is in this set |

**Returns:** List of `Tool` objects. Each tool's name is the `operationId` from the spec.

**Schema handling:** Automatically resolves `$ref` references, strips `$defs`, and limits nesting depth to 3 levels for Gemini compatibility.

---

### `fetch_openapi_spec`

```python
async def fetch_openapi_spec(
    api_url: str,
    auth_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]
```

Fetches an OpenAPI spec from `{api_url}/openapi.json`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_url` | `str` | (required) | Base API URL (without `/openapi.json`) |
| `auth_headers` | `Optional[Dict[str, str]]` | `None` | Auth headers for the request |

**Returns:** Parsed OpenAPI spec dict.

**Raises:** `httpx.HTTPStatusError` on non-2xx response.

---

## Vector Store

### `SearchResult`

Dataclass for vector search results. Source: `core/vector_store.py`.

```python
@dataclass
class SearchResult:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    table: str = ""
    score: float = 0.0
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | `str` | (required) | The text content of the result |
| `metadata` | `Dict[str, Any]` | `{}` | Associated metadata |
| `table` | `str` | `""` | Name of the table the result came from |
| `score` | `float` | `0.0` | Similarity score (lower is more similar in LanceDB) |

---

### `Embedder`

Wrapper around embedding providers for vector generation. Source: `core/vector_store.py`.

#### Constructor

```python
Embedder(embedding_provider=None)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `embedding_provider` | `object \| None` | `None` | A `ResolvedEmbedding` (has `.provider`) or a raw embedding provider with an `embed()` method |

#### Methods

```python
async def embed_batch(
    self,
    texts: List[str],
    batch_size: int = 32,
) -> List[List[float]]
```

Embeds a list of texts in batches. Returns list of embedding vectors.

```python
async def embed(self, text: str) -> List[float]
```

Embeds a single text string. Returns embedding vector.

---

### `VectorStore`

LanceDB-backed vector database for similarity search. Source: `core/vector_store.py`.

#### Constructor

```python
VectorStore(
    db_path: str = ".vector_store",
    embedder: Optional[Embedder] = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str` | `".vector_store"` | Path to the LanceDB database directory |
| `embedder` | `Optional[Embedder]` | `None` | Embedder for generating vectors (required for search operations) |

#### Methods

```python
def add(
    self,
    table_name: str,
    items: List[Dict[str, Any]],
    mode: str = "overwrite",
) -> None
```

Add items to a table. Each item must have a `"vector"` key with the embedding.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `table_name` | `str` | (required) | Name of the table |
| `items` | `List[Dict[str, Any]]` | (required) | Items to store (must include `"vector"` key) |
| `mode` | `str` | `"overwrite"` | `"overwrite"` replaces table, `"append"` adds to existing |

---

```python
def search_table(
    self,
    table_name: str,
    query_embedding: List[float],
    top_k: int = 10,
) -> List[SearchResult]
```

Search a single table by vector similarity. Returns results sorted by relevance.

---

```python
def search(
    self,
    query_embedding: List[float],
    top_k: int = 10,
    tables: Optional[List[str]] = None,
    exclude_tables: Optional[List[str]] = None,
) -> List[SearchResult]
```

Cross-table vector search. By default, excludes the `"tools"` table (used internally by `ToolFilterManager`).

---

```python
def get_all(self, table_name: str) -> List[Dict[str, Any]]
```

Returns all records from a table.

```python
def delete_table(self, table_name: str) -> None
```

Deletes a table.

```python
def get_stats(self) -> Dict[str, Any]
```

Returns `{"db_path": str, "tables": {name: count, ...}, "total_records": int}`.

#### Properties

```python
@property
def table_names(self) -> List[str]
```

List of all table names in the database.

---

## Tool Filtering

### `ToolFilterResult`

Dataclass for RAG filtering results. Source: `core/tool_filter.py`.

```python
@dataclass
class ToolFilterResult:
    names: Set[str] = field(default_factory=set)
    by_source: Dict[str, Set[str]] = field(default_factory=dict)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `names` | `Set[str]` | `set()` | All relevant tool names across all sources |
| `by_source` | `Dict[str, Set[str]]` | `{}` | Tool names grouped by source type (e.g., `"openapi"`, `"mcp"`) |

---

### `ToolFilterManager`

RAG-based tool filtering using vector similarity. Indexes tool descriptions and filters by relevance to a task prompt. Source: `core/tool_filter.py`.

#### Class Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `TOOLS_TABLE` | `"tools"` | Name of the vector store table used for tool embeddings |

#### Constructor

```python
ToolFilterManager(
    embedder: Embedder,
    vector_store: VectorStore,
)
```

#### Properties

```python
@property
def is_indexed(self) -> bool
```

Whether any tools have been indexed.

```python
@property
def tool_count(self) -> int
```

Number of indexed tools.

#### Methods

```python
def get_statistics(self) -> Dict[str, Any]
```

Returns `{"total_tools": int, "by_source": {source: count}, "initialized": bool}`.

---

```python
async def index_openapi(
    self,
    spec: Dict[str, Any],
    batch_size: int = 32,
) -> int
```

Index tools from an OpenAPI specification. Extracts operation IDs, descriptions, parameters, and embeds them.

**Returns:** Number of tools indexed.

---

```python
async def index_mcp_toolsets(
    self,
    toolsets: list,
    batch_size: int = 32,
) -> int
```

Index tools from MCP toolsets. Connects to each toolset, extracts tool metadata, and embeds descriptions.

**Returns:** Number of tools indexed.

---

```python
async def filter(
    self,
    task_prompt: str,
    top_k: int = 200,
    essential_tools: Optional[Set[str]] = None,
) -> ToolFilterResult
```

RAG-filter indexed tools by relevance to a task prompt.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task_prompt` | `str` | (required) | The user's task description |
| `top_k` | `int` | `200` | Maximum number of tools to return |
| `essential_tools` | `Optional[Set[str]]` | `None` | Tool names always included regardless of relevance score |

**Returns:** `ToolFilterResult` with relevant tool names.

---

### `filter_mcp_toolsets`

Standalone function for filtering MCP toolsets by name. Source: `core/tool_filter.py`.

```python
async def filter_mcp_toolsets(
    toolsets: list,
    relevant_names: Set[str],
) -> list
```

Wraps MCP toolsets with `ToolFilterWrapper` to hide irrelevant tools. Tools whose names are NOT in `relevant_names` are filtered out.

| Parameter | Type | Description |
|-----------|------|-------------|
| `toolsets` | `list` | MCP toolset objects |
| `relevant_names` | `Set[str]` | Set of tool names to keep visible |

**Returns:** List of (possibly wrapped) toolsets. Toolsets with no matching tools are excluded entirely.

---

## Document Store

### `DocumentStore`

High-level facade for storing and searching documents with automatic embedding. Source: `core/document_store.py`.

#### Constructor

```python
DocumentStore(
    vector_store: VectorStore,
    embedder: Embedder,
    table_name: str = "documents",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `vector_store` | `VectorStore` | (required) | The vector store backend |
| `embedder` | `Embedder` | (required) | Embedder for generating document vectors |
| `table_name` | `str` | `"documents"` | Name of the table in the vector store |

#### Properties

```python
@property
def count(self) -> int
```

Number of documents in the store.

```python
@property
def exists(self) -> bool
```

Whether the document table exists.

#### Methods

```python
async def add_documents(
    self,
    documents: List[Dict[str, Any]],
    mode: str = "overwrite",
    batch_size: int = 32,
) -> int
```

Add documents with automatic embedding. Each document dict must have a `"text"` key. Additional keys are stored as metadata.

**Returns:** Number of documents stored.

---

```python
async def search(
    self,
    query: str,
    top_k: int = 10,
) -> List[SearchResult]
```

Natural language search across stored documents.

**Returns:** List of `SearchResult` sorted by relevance.

---

```python
def get_all(self) -> List[Dict[str, Any]]
```

Returns all documents from the store.

```python
def delete(self) -> None
```

Deletes the entire document table.

```python
def get_stats(self) -> Dict[str, Any]
```

Returns `{"table_name": str, "exists": bool, "document_count": int}`.

---

## MCP Setup Utilities

These are internal utilities in `core/mcp_setup.py`. Not exported from the top-level package but available via direct import.

### `ToolFilterWrapper`

Wraps an MCP toolset to filter out tools with problematic schemas. Inherits from `AbstractToolset`.

```python
from machine_core.core.mcp_setup import ToolFilterWrapper
```

#### Constructor

```python
ToolFilterWrapper(
    wrapped_toolset,
    problematic_tool_names: set | None = None,
)
```

#### Properties

```python
@property
def id(self) -> str  # Returns "filtered-{wrapped_id}"
```

#### Methods

```python
async def get_tools(self, ctx) -> dict    # Filtered tools dict
async def call_tool(self, name, tool_args, ctx, tool)  # Delegates or raises ValueError
```

---

### `validate_and_fix_toolsets`

```python
async def validate_and_fix_toolsets(
    toolsets: list,
) -> tuple[list, list[str]]
```

Validates MCP toolsets for schema issues. Wraps problematic ones with `ToolFilterWrapper`.

**Returns:** `(fixed_toolsets, warning_messages)`.

---

### `load_mcp_servers_from_config`

```python
def load_mcp_servers_from_config(
    config_path: str = "mcp.json",
) -> list
```

Loads MCP server configurations from a JSON file. Returns list of `MCPServerModel` instances.

---

### `setup_mcp_toolsets`

```python
def setup_mcp_toolsets(
    tools_urls: list,
    timeout: float = 604800.0,
    max_retries: int = 15,
    allow_sampling: bool = False,
) -> list
```

Creates MCP toolset objects from server configurations.

---

## Module Constants

### `SYSTEM_PROMPT`

Default system prompt used by built-in agents. Source: `core/config.py`.

```python
from machine_core import SYSTEM_PROMPT
```

A multi-line string defining a general-purpose multi-modal AI agent persona with structured output formatting rules.

### Additional Prompt Constants

Available via direct import from `machine_core.core.config`:

| Constant | Purpose |
|----------|---------|
| `DRIVSTOFF_PROMPT` | Fuel information extraction |
| `ALTLOKALT_PROMPT` | Company information extraction |
| `SORTIFY_PROMPT` | Receipt data extraction |
| `PHONECTRL_PROMPT` | Visual segmentation and object localization |

---

## Type Summary

| Type | Module | Kind | Description |
|------|--------|------|-------------|
| `AgentConfig` | `config` | Pydantic BaseModel | Agent behavior config |
| `MCPServerModel` | `config` | Pydantic BaseModel | MCP server definition |
| `AgentCore` | `agent_core` | Class | Core infrastructure |
| `BaseAgent` | `agent_base` | Abstract class | Agent base class |
| `ProcessedFile` | `file_processor` | Dataclass | File processing result |
| `FileProcessor` | `file_processor` | Static class | File processing utilities |
| `SearchResult` | `vector_store` | Dataclass | Vector search result |
| `Embedder` | `vector_store` | Class | Embedding wrapper |
| `VectorStore` | `vector_store` | Class | LanceDB vector database |
| `ToolFilterResult` | `tool_filter` | Dataclass | Filter result container |
| `ToolFilterManager` | `tool_filter` | Class | RAG-based tool filter |
| `DocumentStore` | `document_store` | Class | Document storage facade |
| `ToolFilterWrapper` | `mcp_setup` | Class | MCP toolset filter wrapper |
