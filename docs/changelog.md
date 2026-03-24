# Changelog

All notable changes to `machine-core`.

---

## v0.4.1 (2025)

**Mixed-mode tool filtering**

- Added `filter_mcp_toolsets()` standalone function — wraps MCP toolsets with `ToolFilterWrapper` to hide irrelevant tools based on a set of relevant names
- Added `toolsets=` parameter to `AgentCore.rebuild_agent()` — allows swapping MCP toolsets alongside dynamic tools in a single call
- Exported `filter_mcp_toolsets` from the top-level package

This enables a "mixed mode" where both OpenAPI tools and MCP toolsets can be RAG-filtered per request.

**Commit:** `57a2eaa`

---

## v0.4.0 (2025)

**Shared infrastructure migration from ai-accounting-agent**

Migrated reusable components from `ai-accounting-agent` into machine-core as shared infrastructure:

- **FileProcessor** (`core/file_processor.py`) — static utility for PDF text extraction (pdfplumber + PyPDF2 fallback), image OCR (pytesseract), VLM data URL preparation, and batch file upload processing
- **ProcessedFile** — dataclass for file processing results (text, data_url, mime_type, pages, error)
- **generate_tools_from_openapi** (`core/openapi_tools.py`) — generates pydantic-ai `Tool` objects from OpenAPI 3.x specs with automatic `$ref` resolution, schema depth limiting (3 levels for Gemini), and auth header injection
- **fetch_openapi_spec** — async function to fetch OpenAPI specs from API endpoints
- **VectorStore** (`core/vector_store.py`) — LanceDB-backed vector database with table management, single-table and cross-table similarity search
- **Embedder** — wrapper around embedding providers (supports `ResolvedEmbedding` and raw providers)
- **SearchResult** — dataclass for vector search results
- **ToolFilterManager** (`core/tool_filter.py`) — RAG-based tool filtering that indexes OpenAPI and MCP tool descriptions, then filters by task prompt relevance
- **ToolFilterResult** — dataclass for filter results with tool names grouped by source
- **DocumentStore** (`core/document_store.py`) — high-level facade for document storage with automatic embedding and natural language search

Additional changes:
- `BaseAgent._process_image()` now delegates to `FileProcessor.prepare_for_vlm()`
- Updated `__init__.py` to export all 16 public symbols
- New dependencies: `lancedb>=0.20.0`, `pdfplumber`, `PyPDF2`, `Pillow`, `pytesseract`, `httpx`

**Commit:** `6d70e4a`

---

## v0.3.0 (2025)

**Dynamic tools support**

- Added `rebuild_agent(tools=, system_prompt=, retries=)` method to `AgentCore` — allows recreating the agent with new tools per request without re-initializing MCP connections or model providers
- Extracted `_build_agent()` from `__init__()` to make agent creation reusable
- Added `run_query_iter()` to `BaseAgent` — async generator yielding `(node, step_num)` tuples for step-by-step execution control
- Added `_validate_agent_tools()` for schema validation on dynamically-created tools

This enables the "dynamic tools mode" where tools can be swapped per request, used by `ai-accounting-agent` for per-prompt OpenAPI tool generation.

**Commit:** `fc8721a`

---

## v0.2.0 (2025)

**Provider-agnostic model objects**

- Simplified `AgentCore.__init__()` to use `ResolvedProvider.model` directly — AgentCore no longer imports `OpenAIChatModel`, `GoogleModel`, or `AnthropicModel`
- All model construction logic now lives entirely in `model-providers`
- `AgentCore` stores `self.provider_type` for downstream logic that needs to know (e.g., schema depth limiting for Gemini)

**Commit:** `5a1f772`

---

## v0.1.8 (2025)

- Updated version in pyproject.toml and uv.lock
- Updated model-providers dependency to v0.0.8

**Commits:** `d286ea9`, `12f4fca`

---

## v0.1.7 (2025)

- Bumped dependencies
- `ToolFilterWrapper` extended to inherit from `AbstractToolset` and implement all abstract methods (`get_tools`, `id`, `call_tool`)
- Fixed `ToolFilterWrapper.id` property to handle missing wrapped toolset ID gracefully
- Fixed `BaseAgent.run_query()` to let pydantic-ai handle tool errors properly instead of interfering with retry logic

**Commits:** `d4e4685`, `a43fbb0`, `df35141`, `6661e7e`, `a55cbcc`

---

## v0.1.3 (2025)

- Updated Dockerfile for Python 3.13
- Enhanced deployment documentation
- Refactored code structure for readability

**Commits:** `ce758dd`, `1700581`, `835ce34`

---

## v0.1.1 (2025)

- Added support for Google model in AgentCore
- Updated model-providers Git source URL
- Various improvements for Google/Vertex provider support

**Commits:** `5480123`, `6b236ab`, `e5c0357`, `c80e0f6`

---

## v0.1.0 (2024)

**Initial release**

- `AgentCore` — core infrastructure for model/embedding resolution and MCP toolset loading
- `BaseAgent` — abstract base class with `run_query()` and `run_query_stream()`
- MCP toolset integration with `ToolFilterWrapper` for schema validation
- Configuration via `AgentConfig` and environment variables
- 6 built-in agents: ChatAgent, CLIAgent, ReceiptProcessorAgent, TwitterBotAgent, RAGChatAgent, MemoryMasterAgent
- FastAPI service with Prometheus metrics (`/metrics`), health check, and static frontend
- Docker and Docker Compose deployment support
- Integration with `model-providers` for 7 LLM + 3 embedding backends

**Commits:** `2c4749d` through `027aeed`
