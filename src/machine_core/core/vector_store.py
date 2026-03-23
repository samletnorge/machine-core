"""Embedder wrapper and multi-table vector store backed by LanceDB.

Provides:
- Embedder: wraps any model-providers embedding provider for batch/single embedding
- VectorStore: LanceDB connection with multi-table support for different data types

Design:
- One LanceDB database directory, multiple tables (e.g., "tools", "companies", "web_scrapes")
- search() with no args searches ALL tables EXCEPT "tools" by default
- Tools are excluded from cross-table search because tool descriptions pollute document results
- Each search result carries a `table` field for provenance
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field

from loguru import logger

try:
    import lancedb
except ImportError:
    lancedb = None


@dataclass
class SearchResult:
    """A single search result from the vector store."""

    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    table: str = ""
    score: float = 0.0


class Embedder:
    """Wraps an embedding provider from model-providers for batch/single embedding.

    Accepts either a raw provider object (with an .embed() method) or a
    ResolvedEmbedding object (which has a .provider attribute).
    """

    def __init__(self, embedding_provider=None):
        """Initialize the embedder.

        Args:
            embedding_provider: Embedding provider from model-providers.
                Can be a ResolvedEmbedding (has .provider attr) or a raw provider.
                If None, embedding operations will return empty lists.
        """
        # Extract the actual provider if it's a ResolvedEmbedding wrapper
        if embedding_provider and hasattr(embedding_provider, "provider"):
            self.provider = embedding_provider.provider
        else:
            self.provider = embedding_provider

    async def embed_batch(
        self, texts: List[str], batch_size: int = 32
    ) -> List[List[float]]:
        """Embed multiple texts in batches.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per batch

        Returns:
            List of embedding vectors
        """
        if self.provider is None:
            logger.warning(
                "No embedding provider configured, returning empty embeddings"
            )
            return [[] for _ in texts]

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                embeddings = await asyncio.to_thread(self.provider.embed, batch)
                all_embeddings.extend(embeddings)
            except Exception as e:
                logger.warning(f"Failed to embed batch {i // batch_size + 1}: {e}")
                all_embeddings.extend([[] for _ in batch])

        return all_embeddings

    async def embed(self, text: str) -> List[float]:
        """Embed a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        if self.provider is None:
            logger.warning("No embedding provider configured")
            return []

        try:
            embeddings = await asyncio.to_thread(self.provider.embed, [text])
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            return []
        except Exception as e:
            logger.error(f"Failed to embed text: {e}")
            return []


class VectorStore:
    """Multi-table vector store backed by LanceDB.

    Supports multiple named tables in one database directory.
    Each table can have different schemas but all use vector search.

    Default behavior: search() excludes the "tools" table because tool
    descriptions pollute document search results. To include tools,
    pass exclude_tables=[] or tables=["tools", ...] explicitly.
    """

    def __init__(
        self, db_path: str = ".vector_store", embedder: Optional[Embedder] = None
    ):
        """Initialize the vector store.

        Args:
            db_path: Path to the LanceDB database directory
            embedder: Embedder instance for creating embeddings
        """
        if lancedb is None:
            raise ImportError(
                "lancedb is required for VectorStore. Install with: uv add lancedb"
            )

        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))
        self.embedder = embedder
        self._tables: Dict[str, Any] = {}

        # Load existing tables
        for table_name in self.db.table_names():
            try:
                self._tables[table_name] = self.db.open_table(table_name)
            except Exception as e:
                logger.warning(f"Failed to open table '{table_name}': {e}")

        if self._tables:
            logger.info(
                f"VectorStore loaded {len(self._tables)} existing table(s): "
                f"{list(self._tables.keys())}"
            )

    def add(
        self,
        table_name: str,
        items: List[Dict[str, Any]],
        mode: str = "overwrite",
    ) -> None:
        """Add items to a table.

        Each item dict must contain an "embedding" key with the vector,
        and can contain any other metadata fields.

        Args:
            table_name: Name of the table
            items: List of dicts, each with "embedding" + metadata
            mode: "overwrite" to replace table, "append" to add to existing
        """
        if not items:
            logger.warning(f"No items to add to table '{table_name}'")
            return

        try:
            if table_name in self._tables and mode == "append":
                self._tables[table_name].add(items)
            else:
                # Create or overwrite
                if table_name in self._tables:
                    self.db.drop_table(table_name)
                self._tables[table_name] = self.db.create_table(
                    table_name, data=items, mode="overwrite"
                )

            logger.info(
                f"Added {len(items)} items to table '{table_name}' (mode={mode})"
            )
        except Exception as e:
            logger.error(f"Failed to add items to table '{table_name}': {e}")
            raise

    def search_table(
        self,
        table_name: str,
        query_embedding: List[float],
        top_k: int = 10,
    ) -> List[SearchResult]:
        """Search a single table by vector similarity.

        Args:
            table_name: Name of the table to search
            query_embedding: Query embedding vector
            top_k: Number of top results to return

        Returns:
            List of SearchResult objects sorted by relevance
        """
        if not query_embedding:
            logger.warning("Empty query embedding")
            return []

        if table_name not in self._tables:
            logger.warning(f"Table '{table_name}' not found")
            return []

        try:
            results = (
                self._tables[table_name].search(query_embedding).limit(top_k).to_list()
            )

            search_results = []
            for r in results:
                distance = r.get("_distance", 0.0)
                score = 1.0 / (1.0 + distance)

                # Build metadata from all non-internal fields
                metadata = {
                    k: v
                    for k, v in r.items()
                    if k not in ("_distance", "embedding", "vector")
                }

                text = r.get("text", r.get("name", r.get("description", "")))

                search_results.append(
                    SearchResult(
                        text=str(text),
                        metadata=metadata,
                        table=table_name,
                        score=score,
                    )
                )

            return search_results
        except Exception as e:
            logger.error(f"Search failed on table '{table_name}': {e}")
            return []

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        tables: Optional[List[str]] = None,
        exclude_tables: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        """Cross-table search by vector similarity.

        Default behavior: searches ALL tables EXCEPT "tools".
        Pass exclude_tables=[] to include tools, or tables=["tools"] to search only tools.

        Args:
            query_embedding: Query embedding vector
            top_k: Number of top results to return (across all searched tables)
            tables: Explicit list of tables to search (overrides exclude_tables)
            exclude_tables: Tables to exclude (default: ["tools"])

        Returns:
            List of SearchResult objects sorted by relevance (best first)
        """
        if tables is not None:
            search_tables = [t for t in tables if t in self._tables]
        else:
            if exclude_tables is None:
                exclude_tables = ["tools"]
            search_tables = [t for t in self._tables if t not in exclude_tables]

        if not search_tables:
            logger.warning("No tables to search")
            return []

        all_results = []
        for table_name in search_tables:
            results = self.search_table(table_name, query_embedding, top_k=top_k)
            all_results.extend(results)

        # Sort by score descending, take top_k
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results[:top_k]

    def get_all(self, table_name: str) -> List[Dict[str, Any]]:
        """Get all records from a table.

        Args:
            table_name: Name of the table

        Returns:
            List of record dicts
        """
        if table_name not in self._tables:
            logger.warning(f"Table '{table_name}' not found")
            return []

        try:
            return self._tables[table_name].search().limit(100000).to_list()
        except Exception as e:
            logger.error(f"Failed to get all from '{table_name}': {e}")
            return []

    def delete_table(self, table_name: str) -> None:
        """Delete a table.

        Args:
            table_name: Name of the table to delete
        """
        try:
            if table_name in self._tables:
                self.db.drop_table(table_name)
                del self._tables[table_name]
                logger.info(f"Deleted table '{table_name}'")
            else:
                logger.warning(f"Table '{table_name}' not found")
        except Exception as e:
            logger.error(f"Failed to delete table '{table_name}': {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store.

        Returns:
            Dict with table names, record counts, and total stats
        """
        stats = {
            "db_path": str(self.db_path),
            "tables": {},
            "total_records": 0,
        }

        for table_name, table in self._tables.items():
            try:
                records = table.search().limit(100000).to_list()
                count = len(records)
                stats["tables"][table_name] = {"record_count": count}
                stats["total_records"] += count
            except Exception as e:
                stats["tables"][table_name] = {"error": str(e)}

        return stats

    @property
    def table_names(self) -> List[str]:
        """Get list of table names."""
        return list(self._tables.keys())
