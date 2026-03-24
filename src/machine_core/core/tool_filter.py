"""RAG-based tool filtering for OpenAPI and MCP toolsets.

Indexes tool descriptions into a VectorStore "tools" table, then uses
semantic search to find the most relevant tools for a given task prompt.

Two sources:
- OpenAPI specs: walks paths[path][method] to extract operationId + description
- MCP toolsets: calls toolset.list_tools() to get tool names + descriptions

Returns a ToolFilterResult with:
- .names: Set[str] of all relevant tool names (union of all sources)
- .by_source: Dict[str, Set[str]] e.g. {"openapi": {...}, "mcp": {...}}

Usage:
    from machine_core import ToolFilterManager, ToolFilterResult

    manager = ToolFilterManager(embedder=embedder, vector_store=vector_store)
    await manager.index_openapi(spec)
    await manager.index_mcp_toolsets(toolsets)

    result = await manager.filter("Create an invoice for customer X")
    # result.names -> {"createInvoice", "getCustomer", ...}
    # result.by_source -> {"openapi": {"createInvoice", ...}, "mcp": {"search_docs", ...}}
"""

import json
import re
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field

from loguru import logger

from .vector_store import Embedder, VectorStore, SearchResult
from .mcp_setup import ToolFilterWrapper


@dataclass
class ToolFilterResult:
    """Result of filtering tools by relevance to a task.

    Attributes:
        names: Set of all relevant tool names across all sources.
        by_source: Dict mapping source type to set of tool names.
            e.g. {"openapi": {"op1", "op2"}, "mcp": {"tool1"}}
    """

    names: Set[str] = field(default_factory=set)
    by_source: Dict[str, Set[str]] = field(default_factory=dict)


class ToolFilterManager:
    """Indexes tools from OpenAPI specs and MCP toolsets, then filters by RAG.

    Uses a VectorStore "tools" table to store tool embeddings.
    Query with a task prompt to get the most relevant tool names.

    The manager tracks which tools came from which source (openapi vs mcp)
    so callers can apply filtering differently per source:
    - OpenAPI tools: pass result.by_source["openapi"] to generate_tools_from_openapi(tool_filter=...)
    - MCP tools: pass irrelevant names to ToolFilterWrapper to hide from LLM context
    """

    TOOLS_TABLE = "tools"

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
    ):
        """Initialize the tool filter manager.

        Args:
            embedder: Embedder instance for creating tool embeddings
            vector_store: VectorStore instance (tools will be stored in "tools" table)
        """
        self.embedder = embedder
        self.vector_store = vector_store
        self._tool_sources: Dict[str, str] = {}  # tool_name -> source ("openapi"/"mcp")
        self._initialized = False

        # Load existing source metadata if tools table exists
        self._load_source_metadata()

    def _load_source_metadata(self) -> None:
        """Load tool source metadata from existing vector store data."""
        if self.TOOLS_TABLE not in self.vector_store.table_names:
            return

        try:
            records = self.vector_store.get_all(self.TOOLS_TABLE)
            for record in records:
                name = record.get("name", "")
                source = record.get("source", "unknown")
                if name:
                    self._tool_sources[name] = source

            if self._tool_sources:
                self._initialized = True
                logger.info(
                    f"Loaded {len(self._tool_sources)} tool source mappings from existing index"
                )
        except Exception as e:
            logger.warning(f"Failed to load tool source metadata: {e}")

    @property
    def is_indexed(self) -> bool:
        """Check if any tools have been indexed."""
        return self._initialized and len(self._tool_sources) > 0

    @property
    def tool_count(self) -> int:
        """Get the number of indexed tools."""
        return len(self._tool_sources)

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the indexed tools.

        Returns:
            Dict with total_tools, by_source counts, and initialized status.
        """
        source_counts: Dict[str, int] = {}
        for source in self._tool_sources.values():
            source_counts[source] = source_counts.get(source, 0) + 1

        return {
            "total_tools": len(self._tool_sources),
            "by_source": source_counts,
            "initialized": self._initialized,
            "tools_table_exists": self.TOOLS_TABLE in self.vector_store.table_names,
        }

    # ========================================================================
    # Indexing
    # ========================================================================

    async def index_openapi(
        self,
        spec: Dict[str, Any],
        batch_size: int = 32,
    ) -> int:
        """Index tools from an OpenAPI spec.

        Walks paths[path][method] to extract operationId, summary/description,
        and parameter names. Embeds each tool and stores in the vector store.

        Args:
            spec: Parsed OpenAPI spec dict
            batch_size: Number of tools to embed at once

        Returns:
            Number of tools indexed
        """
        tools_data = self._extract_openapi_tools(spec)
        if not tools_data:
            logger.warning("No tools found in OpenAPI spec")
            return 0

        return await self._embed_and_store(
            tools_data, source="openapi", batch_size=batch_size
        )

    async def index_mcp_toolsets(
        self,
        toolsets: list,
        batch_size: int = 32,
    ) -> int:
        """Index tools from MCP toolsets.

        Calls list_tools() on each toolset, extracts tool names and descriptions,
        embeds them, and stores in the vector store.

        Args:
            toolsets: List of MCP toolset objects (MCPServerStdio, MCPServerSSE, etc.)
            batch_size: Number of tools to embed at once

        Returns:
            Number of tools indexed
        """
        tools_data = []

        for toolset in toolsets:
            try:
                if not hasattr(toolset, "list_tools"):
                    logger.debug(
                        f"Toolset {type(toolset).__name__} has no list_tools(), skipping"
                    )
                    continue

                tools_response = await toolset.list_tools()

                # Handle different response formats
                if hasattr(tools_response, "tools"):
                    tools = tools_response.tools
                elif isinstance(tools_response, list):
                    tools = tools_response
                else:
                    tools = []

                for tool in tools:
                    name = getattr(tool, "name", "")
                    description = getattr(tool, "description", "") or ""

                    if not name:
                        continue

                    # Build text representation for embedding
                    text = f"Tool: {name}\nDescription: {description}"

                    # Include parameter info if available
                    input_schema = getattr(tool, "inputSchema", None)
                    if input_schema and isinstance(input_schema, dict):
                        params = list(input_schema.get("properties", {}).keys())
                        if params:
                            text += f"\nParameters: {', '.join(params)}"

                    tools_data.append(
                        {
                            "name": name,
                            "description": description,
                            "text": text,
                        }
                    )

                logger.info(
                    f"Extracted {len(tools)} tools from {type(toolset).__name__}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to extract tools from {type(toolset).__name__}: {e}"
                )

        if not tools_data:
            logger.warning("No tools found in MCP toolsets")
            return 0

        return await self._embed_and_store(
            tools_data, source="mcp", batch_size=batch_size
        )

    # ========================================================================
    # Filtering
    # ========================================================================

    async def filter(
        self,
        task_prompt: str,
        top_k: int = 200,
        essential_tools: Optional[Set[str]] = None,
    ) -> ToolFilterResult:
        """Filter tools by relevance to a task prompt using RAG.

        Embeds the task prompt and searches the tools table for the most
        semantically similar tools.

        Args:
            task_prompt: Natural language description of the task
            top_k: Maximum number of tools to return from RAG
            essential_tools: Set of tool names that must always be included
                regardless of RAG results. These are added to the result
                even if they weren't in the top_k RAG results.

        Returns:
            ToolFilterResult with .names and .by_source
        """
        result = ToolFilterResult()

        if not self.is_indexed:
            logger.warning("No tools indexed, returning empty result")
            # If essential tools provided, return those
            if essential_tools:
                result.names = set(essential_tools)
                # Assign essential tools to their known sources
                for name in essential_tools:
                    source = self._tool_sources.get(name, "unknown")
                    result.by_source.setdefault(source, set()).add(name)
            return result

        try:
            # Embed the task prompt
            query_embedding = await self.embedder.embed(task_prompt)
            if not query_embedding:
                logger.warning("Failed to embed task prompt, falling back to all tools")
                return self._all_tools_result()

            # Search the tools table
            search_results = self.vector_store.search_table(
                self.TOOLS_TABLE, query_embedding, top_k=top_k
            )

            # Build result from search hits
            for sr in search_results:
                name = sr.metadata.get("name", "")
                if not name:
                    continue

                source = sr.metadata.get(
                    "source", self._tool_sources.get(name, "unknown")
                )
                result.names.add(name)
                result.by_source.setdefault(source, set()).add(name)

            logger.info(
                f"RAG filtered {len(result.names)} tools from {len(self._tool_sources)} total "
                f"(sources: {{{', '.join(f'{k}: {len(v)}' for k, v in result.by_source.items())}}})"
            )

            # Add essential tools
            if essential_tools:
                for name in essential_tools:
                    if name not in result.names:
                        result.names.add(name)
                        source = self._tool_sources.get(name, "unknown")
                        result.by_source.setdefault(source, set()).add(name)

                logger.info(f"After adding essential tools: {len(result.names)} total")

            return result

        except Exception as e:
            logger.error(f"Tool filtering failed: {e}", exc_info=True)
            # Fall back to all tools on error
            all_result = self._all_tools_result()
            if essential_tools:
                for name in essential_tools:
                    all_result.names.add(name)
                    source = self._tool_sources.get(name, "unknown")
                    all_result.by_source.setdefault(source, set()).add(name)
            return all_result

    # ========================================================================
    # Private helpers
    # ========================================================================

    def _extract_openapi_tools(self, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract tool metadata from an OpenAPI spec.

        Returns list of dicts with name, description, text keys.
        """
        tools_data = []
        paths = spec.get("paths", {})

        for path, path_item in paths.items():
            for method in ["get", "post", "put", "delete", "patch"]:
                operation = path_item.get(method)
                if not operation:
                    continue

                operation_id = operation.get("operationId", "")
                if not operation_id:
                    continue

                # Sanitize name same way as openapi_tools.py
                name = operation_id.strip("[]").replace(" ", "_")
                name = re.sub(r"[^a-zA-Z0-9_.:\-]", "_", name)
                if name and not re.match(r"^[a-zA-Z_]", name):
                    name = f"t_{name}"
                if len(name) > 64:
                    name = name[:64]

                description = operation.get("summary", "") or operation.get(
                    "description", ""
                )
                if not description:
                    description = f"{method.upper()} {path}"

                # Build text representation for embedding
                text = f"Tool: {name}\nDescription: {description}"

                # Include parameter names
                params = []
                for param in operation.get("parameters", []):
                    param_name = param.get("name", "")
                    if param_name:
                        params.append(param_name)

                # Include body properties
                request_body = operation.get("requestBody", {})
                if request_body:
                    content = request_body.get("content", {})
                    for ct_key, ct_val in content.items():
                        body_schema = ct_val.get("schema", {})
                        body_props = list(body_schema.get("properties", {}).keys())
                        params.extend(body_props)
                        break  # Only use first content type

                if params:
                    params_str = json.dumps(
                        params[:50], default=str
                    )  # Limit param count
                    if len(params_str) > 2000:
                        params_str = params_str[:2000]
                    text += f"\nParameters: {params_str}"

                tools_data.append(
                    {
                        "name": name,
                        "description": description,
                        "text": text,
                    }
                )

        logger.info(
            f"Extracted {len(tools_data)} tools from OpenAPI spec ({len(paths)} paths)"
        )
        return tools_data

    async def _embed_and_store(
        self,
        tools_data: List[Dict[str, Any]],
        source: str,
        batch_size: int = 32,
    ) -> int:
        """Embed tool descriptions and store in the vector store.

        Args:
            tools_data: List of dicts with name, description, text keys
            source: Source identifier ("openapi" or "mcp")
            batch_size: Number of tools to embed at once

        Returns:
            Number of tools stored
        """
        texts = [t["text"] for t in tools_data]
        embeddings = await self.embedder.embed_batch(texts, batch_size=batch_size)

        # Build LanceDB records
        records = []
        for tool_data, embedding in zip(tools_data, embeddings):
            if not embedding:
                logger.debug(f"Skipping tool '{tool_data['name']}' — empty embedding")
                continue

            records.append(
                {
                    "name": tool_data["name"],
                    "description": tool_data.get("description", ""),
                    "text": tool_data["text"],
                    "source": source,
                    "embedding": embedding,
                }
            )

            self._tool_sources[tool_data["name"]] = source

        if not records:
            logger.warning(f"No tools with valid embeddings to store (source={source})")
            return 0

        # Determine write mode: append if tools table already exists with data from another source,
        # overwrite if this is a re-index of the same source or first write
        existing_sources = set()
        if self.TOOLS_TABLE in self.vector_store.table_names:
            existing_records = self.vector_store.get_all(self.TOOLS_TABLE)
            for r in existing_records:
                existing_sources.add(r.get("source", ""))

        if existing_sources and source not in existing_sources:
            # Another source already indexed, append
            mode = "append"
        else:
            # First index or re-indexing same source — if other sources exist,
            # we need to preserve them. For simplicity, always overwrite the
            # full table when re-indexing.
            if existing_sources - {source}:
                # Other sources exist — fetch their records and merge
                other_records = [
                    r
                    for r in self.vector_store.get_all(self.TOOLS_TABLE)
                    if r.get("source", "") != source
                ]
                # Remove internal LanceDB fields
                for r in other_records:
                    r.pop("_distance", None)
                    r.pop("_rowid", None)
                records = other_records + records
            mode = "overwrite"

        self.vector_store.add(self.TOOLS_TABLE, records, mode=mode)
        self._initialized = True

        logger.info(
            f"Indexed {len(records)} tools from {source} "
            f"(total indexed: {len(self._tool_sources)})"
        )
        return len(records)

    def _all_tools_result(self) -> ToolFilterResult:
        """Return a ToolFilterResult containing ALL indexed tools (fallback)."""
        result = ToolFilterResult()
        for name, source in self._tool_sources.items():
            result.names.add(name)
            result.by_source.setdefault(source, set()).add(name)
        return result


async def filter_mcp_toolsets(
    toolsets: list,
    relevant_names: Set[str],
) -> list:
    """Wrap MCP toolsets to hide irrelevant tools from the LLM context.

    Takes MCP toolsets and a set of relevant tool names (typically from
    ToolFilterResult.by_source["mcp"]) and returns toolsets wrapped with
    ToolFilterWrapper to exclude everything NOT in relevant_names.

    This is the MCP counterpart to passing tool_filter= to
    generate_tools_from_openapi() for OpenAPI tools.

    Usage:
        result = await manager.filter("Create an invoice")

        # OpenAPI side:
        openapi_tools = generate_tools_from_openapi(
            spec, base_url, auth_headers,
            tool_filter=result.by_source.get("openapi"),
        )

        # MCP side:
        filtered_toolsets = await filter_mcp_toolsets(
            toolsets,
            relevant_names=result.by_source.get("mcp", set()),
        )

        agent_core.rebuild_agent(tools=openapi_tools, toolsets=filtered_toolsets)

    Args:
        toolsets: List of MCP toolset objects (MCPServerStdio, MCPServerSSE, etc.)
        relevant_names: Set of MCP tool names to KEEP visible. All other
            tools discovered in the toolsets will be hidden from the LLM.

    Returns:
        List of toolsets, each wrapped with ToolFilterWrapper if it has
        tools to hide. Toolsets with no discoverable tools or where all
        tools are relevant are returned unwrapped.
    """
    filtered_toolsets = []

    for toolset in toolsets:
        try:
            if not hasattr(toolset, "list_tools"):
                # Can't discover tools — pass through as-is
                filtered_toolsets.append(toolset)
                continue

            # Discover all tool names from this toolset
            tools_response = await toolset.list_tools()
            if hasattr(tools_response, "tools"):
                tools = tools_response.tools
            elif isinstance(tools_response, list):
                tools = tools_response
            else:
                tools = []

            all_names = {
                getattr(t, "name", "") for t in tools if getattr(t, "name", "")
            }

            # Compute names to hide: everything NOT in relevant_names
            names_to_hide = all_names - relevant_names

            if names_to_hide:
                wrapped = ToolFilterWrapper(
                    toolset, problematic_tool_names=names_to_hide
                )
                filtered_toolsets.append(wrapped)
                logger.info(
                    f"Filtered MCP toolset {type(toolset).__name__}: "
                    f"keeping {len(all_names - names_to_hide)}/{len(all_names)} tools, "
                    f"hiding {len(names_to_hide)}"
                )
            else:
                # All tools are relevant — no wrapping needed
                filtered_toolsets.append(toolset)
                logger.debug(
                    f"MCP toolset {type(toolset).__name__}: "
                    f"all {len(all_names)} tools are relevant, no filtering"
                )

        except Exception as e:
            logger.warning(
                f"Failed to filter MCP toolset {type(toolset).__name__}: {e}. "
                f"Passing through unfiltered."
            )
            filtered_toolsets.append(toolset)

    total_kept = sum(
        1 for ts in filtered_toolsets if not isinstance(ts, ToolFilterWrapper)
    )
    total_wrapped = len(filtered_toolsets) - total_kept
    logger.info(
        f"filter_mcp_toolsets: {len(filtered_toolsets)} toolset(s) "
        f"({total_wrapped} filtered, {total_kept} unfiltered)"
    )

    return filtered_toolsets
