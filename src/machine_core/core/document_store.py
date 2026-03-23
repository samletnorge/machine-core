"""Convenience facade for single-table document RAG.

Wraps VectorStore + Embedder to provide a simple interface for storing
and searching documents in a single named table.

Use cases:
- Company research agent: scrape company data into a "companies" table
- Web scraping: store web pages in a "web_scrapes" table
- Knowledge base: store documents in a "knowledge" table

For multi-table search across all document tables, use VectorStore.search() directly.
DocumentStore is for when you want a simple API for one table.

Usage:
    from machine_core import DocumentStore, Embedder, VectorStore

    embedder = Embedder(embedding_provider)
    vector_store = VectorStore(db_path=".vector_store", embedder=embedder)
    docs = DocumentStore(vector_store=vector_store, embedder=embedder, table_name="companies")

    await docs.add_documents([
        {"text": "Acme Corp is a ...", "url": "https://acme.com", "name": "Acme Corp"},
    ])

    results = await docs.search("renewable energy companies in Norway")
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from loguru import logger

from .vector_store import Embedder, VectorStore, SearchResult


class DocumentStore:
    """Convenience facade for document RAG on a single VectorStore table.

    Handles embedding generation and storage for a named table.
    Supports adding documents (with automatic embedding), searching by
    natural language query, and basic CRUD operations.

    Each document is a dict with at minimum a "text" field. Additional
    metadata fields (url, name, category, etc.) are stored alongside.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Embedder,
        table_name: str = "documents",
    ):
        """Initialize the document store.

        Args:
            vector_store: VectorStore instance for storage
            embedder: Embedder instance for creating document embeddings
            table_name: Name of the table in the vector store
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.table_name = table_name

    @property
    def count(self) -> int:
        """Get the number of documents in the store."""
        if self.table_name not in self.vector_store.table_names:
            return 0
        try:
            records = self.vector_store.get_all(self.table_name)
            return len(records)
        except Exception:
            return 0

    @property
    def exists(self) -> bool:
        """Check if the table exists and has data."""
        return self.table_name in self.vector_store.table_names

    async def add_documents(
        self,
        documents: List[Dict[str, Any]],
        mode: str = "overwrite",
        batch_size: int = 32,
    ) -> int:
        """Add documents to the store with automatic embedding.

        Each document dict must have a "text" field. Other fields are stored
        as metadata.

        Args:
            documents: List of document dicts, each with at least a "text" key.
                Additional keys (url, name, category, etc.) are stored as metadata.
            mode: "overwrite" to replace all documents, "append" to add to existing
            batch_size: Number of documents to embed at once

        Returns:
            Number of documents successfully stored
        """
        if not documents:
            logger.warning(f"No documents to add to '{self.table_name}'")
            return 0

        # Validate all documents have text
        valid_docs = []
        for doc in documents:
            text = doc.get("text", "")
            if not text:
                logger.debug(
                    f"Skipping document without text: {doc.get('name', 'unknown')}"
                )
                continue
            valid_docs.append(doc)

        if not valid_docs:
            logger.warning(f"No valid documents (all missing 'text' field)")
            return 0

        # Embed all texts
        texts = [doc["text"] for doc in valid_docs]
        embeddings = await self.embedder.embed_batch(texts, batch_size=batch_size)

        # Build records
        records = []
        for doc, embedding in zip(valid_docs, embeddings):
            if not embedding:
                logger.debug(
                    f"Skipping document with empty embedding: {doc.get('name', 'unknown')}"
                )
                continue

            record = {**doc, "embedding": embedding}
            records.append(record)

        if not records:
            logger.warning(f"No documents with valid embeddings to store")
            return 0

        self.vector_store.add(self.table_name, records, mode=mode)
        logger.info(
            f"Stored {len(records)} documents in '{self.table_name}' (mode={mode})"
        )
        return len(records)

    async def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[SearchResult]:
        """Search documents by natural language query.

        Embeds the query and performs vector similarity search.

        Args:
            query: Natural language search query
            top_k: Maximum number of results to return

        Returns:
            List of SearchResult objects sorted by relevance (best first)
        """
        if not self.exists:
            logger.warning(f"Table '{self.table_name}' does not exist")
            return []

        try:
            query_embedding = await self.embedder.embed(query)
            if not query_embedding:
                logger.warning("Failed to embed search query")
                return []

            return self.vector_store.search_table(
                self.table_name, query_embedding, top_k=top_k
            )
        except Exception as e:
            logger.error(f"Search failed in '{self.table_name}': {e}")
            return []

    def get_all(self) -> List[Dict[str, Any]]:
        """Get all documents from the store.

        Returns:
            List of document dicts (including embeddings and metadata)
        """
        return self.vector_store.get_all(self.table_name)

    def delete(self) -> None:
        """Delete the entire document table."""
        self.vector_store.delete_table(self.table_name)
        logger.info(f"Deleted document store '{self.table_name}'")

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the document store.

        Returns:
            Dict with table name, document count, and existence status
        """
        return {
            "table_name": self.table_name,
            "exists": self.exists,
            "document_count": self.count,
        }
