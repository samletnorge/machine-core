# Vector Store

Machine Core includes a multi-table LanceDB vector store with an embedding wrapper and a convenience document store facade.

## Components

| Class | Purpose |
|-------|---------|
| `Embedder` | Wraps any `model-providers` embedding provider with `embed()` and `embed_batch()` |
| `VectorStore` | Multi-table LanceDB database with add, search, and cross-table queries |
| `SearchResult` | Dataclass for search results with text, metadata, table, and score |
| `DocumentStore` | Single-table convenience facade for document RAG |

## Embedder

Wraps any embedding provider from `model-providers` into a consistent async interface.

```python
from machine_core import Embedder
from model_providers import get_embedding_provider

embedder = Embedder(get_embedding_provider())

# Single text
embedding = await embedder.embed("Hello world")
# [0.012, -0.034, 0.056, ...]  (list of floats)

# Batch (auto-chunked for efficiency)
embeddings = await embedder.embed_batch(
    ["text one", "text two", "text three"],
    batch_size=32,
)
```

The `Embedder` constructor accepts either a `ResolvedEmbedding` object or a raw embedding provider. If you pass `ResolvedEmbedding`, it extracts `.provider` automatically.

Embedding calls use `asyncio.to_thread()` internally since most embedding providers are synchronous.

## VectorStore

Multi-table LanceDB vector database. Each table is an independent vector index.

### Initialization

```python
from machine_core import VectorStore

store = VectorStore(
    db_path=".vector_store",    # directory for LanceDB files
    embedder=embedder,          # optional, for future use
)
```

The `db_path` directory is created automatically. Existing tables are discovered on init.

### Adding Data

```python
records = [
    {
        "text": "Machine learning is a subset of AI",
        "embedding": [0.01, -0.02, ...],  # required
        "category": "technology",          # any extra fields = metadata
    },
    {
        "text": "Paris is the capital of France",
        "embedding": [0.05, 0.03, ...],
        "category": "geography",
    },
]

store.add("documents", records, mode="overwrite")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `table_name` | `str` | -- | Table to add records to |
| `items` | `list[dict]` | -- | Records (each must have `"embedding"` key) |
| `mode` | `str` | `"overwrite"` | `"overwrite"` (drop + recreate) or `"append"` |

### Searching

#### Single-Table Search

```python
query_embedding = await embedder.embed("What is AI?")

results = store.search_table(
    "documents",
    query_embedding,
    top_k=10,
)

for r in results:
    print(f"[{r.score:.3f}] {r.text}")
    print(f"  Table: {r.table}, Metadata: {r.metadata}")
```

#### Cross-Table Search

```python
results = store.search(
    query_embedding,
    top_k=10,
    tables=None,            # None = search all tables
    exclude_tables=None,    # defaults to excluding "tools" table
)
```

By default, `search()` queries all tables **except** the `"tools"` table (used by `ToolFilterManager`). This prevents tool descriptions from polluting document search results.

To search specific tables:

```python
# Only search these tables
results = store.search(query_embedding, tables=["companies", "products"])

# Search all tables including "tools"
results = store.search(query_embedding, exclude_tables=[])
```

Results from multiple tables are merged and sorted by score (descending).

### SearchResult

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | Result text content |
| `metadata` | `dict` | All non-internal fields from the record |
| `table` | `str` | Source table name |
| `score` | `float` | Relevance score: `1 / (1 + distance)`. Range: 0-1, higher is better. |

### Other Operations

```python
# Get all records from a table
all_records = store.get_all("documents")  # list of dicts (limit 100K)

# Delete a table
store.delete_table("old_data")

# List tables
print(store.table_names)  # ["documents", "tools", "companies"]

# Statistics
stats = store.get_stats()
# {"db_path": ".vector_store", "documents": 150, "tools": 800, "companies": 25}
```

## DocumentStore

A convenience facade for single-table document RAG. Wraps `VectorStore` and `Embedder` with automatic embedding.

```python
from machine_core import DocumentStore, VectorStore, Embedder

store = VectorStore(db_path=".vector_store")
embedder = Embedder(get_embedding_provider())

docs = DocumentStore(
    vector_store=store,
    embedder=embedder,
    table_name="knowledge_base",  # default: "documents"
)
```

### Adding Documents

```python
documents = [
    {"text": "Machine Core is an AI agent framework.", "source": "docs", "page": 1},
    {"text": "It supports MCP tools and OpenAPI integration.", "source": "docs", "page": 2},
]

count = await docs.add_documents(
    documents,
    mode="overwrite",   # or "append"
    batch_size=32,
)
print(f"Added {count} documents")
```

Each document must have a `"text"` key. All other keys are stored as metadata. Embeddings are computed automatically using the provided `Embedder`.

### Searching

```python
results = await docs.search("How do tools work?", top_k=5)

for r in results:
    print(f"[{r.score:.3f}] {r.text}")
    print(f"  Source: {r.metadata.get('source')}, Page: {r.metadata.get('page')}")
```

The query is embedded automatically before searching.

### Management

```python
print(docs.exists)  # True
print(docs.count)   # 150

docs.delete()       # Drops the entire table

stats = docs.get_stats()
# {"table_name": "knowledge_base", "exists": True, "count": 150}
```

## Storage Layout

LanceDB stores data as a directory of files:

```
.vector_store/
  documents.lance/         # one directory per table
  tools.lance/
  knowledge_base.lance/
```

Data persists across restarts. The `VectorStore` constructor discovers existing tables automatically.

## Usage Patterns

### Pattern 1: Document RAG

```python
# Index documents once
docs = DocumentStore(vector_store, embedder, "docs")
await docs.add_documents(my_documents)

# Search per query
results = await docs.search(user_query, top_k=5)
context = "\n".join(r.text for r in results)
prompt = f"Based on these documents:\n{context}\n\nAnswer: {user_query}"
```

### Pattern 2: Multi-Table Search

```python
# Store different content types in different tables
store.add("faq", faq_records)
store.add("manuals", manual_records)
store.add("tickets", ticket_records)

# Search across all content types
query_emb = await embedder.embed(question)
results = store.search(query_emb, top_k=10)
# Results come from all tables, sorted by relevance
```

### Pattern 3: Tool Filtering (internal)

`ToolFilterManager` uses the VectorStore internally with a `"tools"` table:

```python
# This is what ToolFilterManager does internally:
store.add("tools", tool_records, mode="overwrite")
results = store.search_table("tools", query_embedding, top_k=200)
```

The `"tools"` table is excluded from `search()` by default so tool descriptions don't appear in document search results.
