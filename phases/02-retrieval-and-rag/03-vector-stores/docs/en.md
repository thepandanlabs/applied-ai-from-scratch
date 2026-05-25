# Vector Stores

> A vector store is indexed cosine similarity at scale. Build one in 50 lines, then understand what Qdrant actually adds.

**Type:** Build
**Languages:** Python
**Prerequisites:** 02-01 Embeddings Intuition, 02-02 Embedding Models
**Time:** ~75 minutes
**Phase:** 02 · Retrieval & RAG

## Learning Objectives

- Implement a minimal in-memory vector store from scratch with add, search, filter, and delete
- Explain the difference between a flat index and HNSW and when each is appropriate
- Use Qdrant in local mode (no Docker, no server) and compare its API to your hand-rolled version
- Describe the tradeoffs between pgvector, dedicated vector databases, and in-memory stores
- Build a verification suite that catches the most common vector store bugs before they reach production

---

## The Problem

A team building a knowledge base RAG system hit a confusing bug six weeks after launch: users reported that recently uploaded documents weren't appearing in search results, but the upload endpoint returned 200 OK. After two days of debugging, they found the root cause: they were inserting documents with duplicate IDs. The vector store silently appended a second entry for each duplicate ID rather than updating the existing one, so the old (stale) version was being returned. The new document was there: but it was ranked second by a negligible margin, and the stale version at the same ID won on tie-breaking rules.

This is a vector store correctness bug, not a machine learning problem. The team had built their stack on embeddings and retrieval logic without understanding the primitives underneath. They didn't know that update semantics, deduplication behavior, and filtering operate differently across vector store implementations: and they didn't write any verification tests to catch these differences.

Vector stores look simple from the outside: put things in, get similar things out. But production systems fail on exactly the edges that look simple: stale entries after updates, filter bugs that silently return zero results, index drift when you change embedding models, and count mismatches between your source system and what's actually indexed. Understanding the internals takes 30 minutes and prevents days of debugging.

---

## The Concept

### What a Vector Index Actually Is

At its core, a vector store holds two things:
1. A matrix of embedding vectors: shape `(N, D)` where N is document count and D is embedding dimension
2. Metadata for each vector: the original text, document ID, and any filterable fields

A search operation computes similarity between the query vector and every stored vector, then returns the top K.

**Flat index (brute force):** Compute similarity against every vector. Exact results. O(N) per query.
- Works fine up to ~100K vectors on a single machine (milliseconds per query)
- Above that, latency becomes a problem

**HNSW (Hierarchical Navigable Small World):** An approximate nearest neighbor algorithm. Builds a layered graph where each node is connected to its nearest neighbors at multiple scales. Search traverses the graph rather than scanning everything.
- O(log N) per query instead of O(N)
- Returns approximate results: the true nearest neighbor might not be in the result set
- "Recall" of 95–99% is typical (95% of queries return the true nearest neighbor)
- Used by Qdrant, Weaviate, Pinecone, pgvector (optional)

```
Flat Index: check every point             HNSW: navigate the graph
                                                      
  Query ──► [doc1] sim=0.72               Query ──► Layer 2 (coarse)
            [doc2] sim=0.45                         │
            [doc3] sim=0.91  ← top      ──► Layer 1 (medium)
            [doc4] sim=0.38                         │
            ...every doc...             ──► Layer 0 (fine) ──► top-K
                                                      
  Exact. Slow at scale.                 Approximate. Fast at scale.
```

### The CRUD Operations

A production vector store needs more than just search:

```
add(id, vector, metadata)     → insert a new document
search(query_vector, top_k, filter)  → retrieve similar documents
get(id)                       → retrieve a document by ID
delete(id)                    → remove a document
update(id, new_vector, new_metadata) → replace a document (delete + add)
count()                       → how many documents are indexed
```

Update is almost always implemented as delete + add, because modifying a vector in a graph index is expensive. This means your application must handle the case where a document is in the process of being updated (briefly absent from the index).

### Metadata Filtering

Metadata filtering lets you restrict search to a subset of documents before (or after) comparing vectors.

```
Pre-filter: reduce the candidate set first, then search within it
  → Example: filter to user_id = "alice", then search her documents only
  → Risk: if the filtered set is small, HNSW accuracy drops (fewer neighbors)

Post-filter: search broadly, then remove results that fail the filter
  → Example: search top-100, then drop any that aren't status="published"
  → Risk: you may not get K results if many are filtered out
```

Most production vector stores (Qdrant, Weaviate, Pinecone) use a hybrid approach: pre-filter for selective filters (eliminate > 90% of docs), post-filter for loose filters. Qdrant explicitly exposes this as `filter` in its search API.

Common filterable fields in production RAG systems:
- `tenant_id` / `user_id`: multi-tenant data isolation
- `doc_type`: restrict to articles vs. code snippets vs. FAQs
- `created_at`: recency filtering
- `language`: monolingual retrieval from a multilingual corpus
- `status`: only search published/approved content

### The Storage Spectrum

```
           Speed       Cost      Persistence   Scale     Ops Complexity
In-memory   ████████    Free      None          Small     Zero
────────────────────────────────────────────────────────────────────────
pgvector    █████       Cheap     Postgres      Medium    Low (in existing DB)
────────────────────────────────────────────────────────────────────────
Qdrant      ████████    Medium    File/Cloud    Large     Medium
────────────────────────────────────────────────────────────────────────
Pinecone    ████████    $$$$      Cloud         Very large Zero (managed)
Weaviate    ███████     Medium    File/Cloud    Large     Medium
────────────────────────────────────────────────────────────────────────
```

**Decision rule:**

- Development / prototyping → in-memory (your custom class or `qdrant-client` local mode)
- You already use Postgres → pgvector first. Seriously.
- You need ANN at > 1M vectors without running your own infra → Pinecone or Qdrant Cloud
- You need hybrid search (dense + sparse in one query) → Qdrant or Weaviate (both support it natively)
- You need full-text + vector in one query → pgvector + pg_bm25 (ParadeDB), or Elasticsearch with vector fields

**When pgvector is enough:**

pgvector is underrated. If your corpus is under 5M vectors, your team already runs Postgres, and your query latency target is < 100ms, pgvector covers the use case. A single Postgres instance with pgvector and an HNSW index handles 5M vectors at 30–50ms per query. Don't add operational complexity you don't need.

---

## Build It

### Step 1: Define the Interface

Start with the interface, not the implementation. A vector store is a contract:

```python
# pip install numpy qdrant-client sentence-transformers

import numpy as np
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SearchResult:
    id: str
    score: float
    text: str
    metadata: dict[str, Any]
```

### Step 2: Build the In-Memory Vector Store

```python
import math

class InMemoryVectorStore:
    """
    Minimal vector store backed by a Python dict and NumPy matrix operations.
    
    Designed to be fully transparent: you can read every line and understand
    exactly what a vector store does. Not for production at scale (no ANN index),
    but correct and useful up to ~100K vectors.
    """

    def __init__(self) -> None:
        # Store vectors and metadata separately for O(1) ID lookup
        self._vectors: dict[str, np.ndarray] = {}
        self._texts: dict[str, str] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(
        self,
        doc_id: str,
        text: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Add a document to the store.
        If doc_id already exists, this raises an error to prevent silent duplicates.
        Use upsert() if you want update semantics.
        """
        if doc_id in self._vectors:
            raise ValueError(
                f"Document '{doc_id}' already exists. Use upsert() to overwrite."
            )
        self._vectors[doc_id] = vector / (np.linalg.norm(vector) or 1.0)  # normalize on insert
        self._texts[doc_id] = text
        self._metadata[doc_id] = metadata or {}

    def upsert(
        self,
        doc_id: str,
        text: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or replace. Safe for update workflows."""
        self._vectors[doc_id] = vector / (np.linalg.norm(vector) or 1.0)
        self._texts[doc_id] = text
        self._metadata[doc_id] = metadata or {}

    def delete(self, doc_id: str) -> bool:
        """Remove a document. Returns True if it existed, False if not found."""
        if doc_id not in self._vectors:
            return False
        del self._vectors[doc_id]
        del self._texts[doc_id]
        del self._metadata[doc_id]
        return True

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, doc_id: str) -> SearchResult | None:
        """Retrieve a document by ID."""
        if doc_id not in self._vectors:
            return None
        return SearchResult(
            id=doc_id,
            score=1.0,
            text=self._texts[doc_id],
            metadata=self._metadata[doc_id],
        )

    def count(self) -> int:
        return len(self._vectors)

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Find the top_k most similar documents.
        
        filter_metadata: optional dict of {field: value}: only documents
        where ALL fields match are included in the search.
        
        Implementation: brute-force cosine similarity (exact results).
        For N > 100K, use an ANN index instead.
        """
        if not self._vectors:
            return []

        query_norm = query_vector / (np.linalg.norm(query_vector) or 1.0)

        # Determine candidate IDs (apply pre-filter)
        candidates = list(self._vectors.keys())
        if filter_metadata:
            candidates = [
                doc_id for doc_id in candidates
                if all(
                    self._metadata[doc_id].get(k) == v
                    for k, v in filter_metadata.items()
                )
            ]

        if not candidates:
            return []

        # Stack candidate vectors into a matrix for batch dot product
        ids = candidates
        matrix = np.stack([self._vectors[i] for i in ids])  # (N, D)
        scores = matrix @ query_norm  # (N,)

        # Top-K selection
        k = min(top_k, len(ids))
        top_indices = np.argpartition(scores, -k)[-k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        return [
            SearchResult(
                id=ids[i],
                score=float(scores[i]),
                text=self._texts[ids[i]],
                metadata=self._metadata[ids[i]],
            )
            for i in top_indices
        ]
```

### Step 3: Test All the Edge Cases

Before trusting a vector store in production, exercise every operation:

```python
def test_vector_store(store: InMemoryVectorStore) -> None:
    """Verify all store operations work correctly."""
    
    # Setup: create some test vectors
    v1 = np.array([1.0, 0.0, 0.0])
    v2 = np.array([0.9, 0.1, 0.0])   # very similar to v1
    v3 = np.array([0.0, 0.0, 1.0])   # unrelated

    # Test 1: basic add and count
    store.add("doc_1", "first document", v1, {"type": "article", "user": "alice"})
    store.add("doc_2", "second document", v2, {"type": "article", "user": "bob"})
    store.add("doc_3", "third document", v3, {"type": "faq", "user": "alice"})
    assert store.count() == 3, "count should be 3 after 3 adds"

    # Test 2: search returns most similar first
    results = store.search(v1, top_k=2)
    assert results[0].id == "doc_1", f"expected doc_1 first, got {results[0].id}"
    assert results[1].id == "doc_2", f"expected doc_2 second, got {results[1].id}"
    assert results[0].score > results[1].score, "scores should be descending"

    # Test 3: metadata filter
    alice_results = store.search(v1, top_k=5, filter_metadata={"user": "alice"})
    assert all(r.metadata["user"] == "alice" for r in alice_results), \
        "filter should only return alice's documents"
    assert len(alice_results) == 2, f"alice has 2 docs, got {len(alice_results)}"

    # Test 4: delete
    deleted = store.delete("doc_2")
    assert deleted is True, "delete should return True for existing doc"
    assert store.count() == 2, "count should decrease after delete"
    assert store.get("doc_2") is None, "deleted doc should not be retrievable"

    # Test 5: delete nonexistent returns False
    deleted = store.delete("does_not_exist")
    assert deleted is False, "deleting a nonexistent doc should return False"

    # Test 6: upsert (update)
    store.upsert("doc_1", "updated text", v3, {"type": "article", "user": "alice"})
    updated = store.get("doc_1")
    assert updated.text == "updated text", "upsert should update text"
    # After update, doc_1 now has v3's direction: should be similar to doc_3
    results = store.search(v3, top_k=2)
    assert any(r.id == "doc_1" for r in results), \
        "after upsert, doc_1 should appear in search results for its new vector"

    # Test 7: duplicate add raises error
    try:
        store.add("doc_1", "duplicate", v1)
        assert False, "duplicate add should raise ValueError"
    except ValueError:
        pass  # expected

    # Test 8: empty filter returns zero results gracefully
    no_results = store.search(v1, top_k=5, filter_metadata={"user": "nobody"})
    assert no_results == [], "filter with no matches should return empty list"

    print("[PASS] All vector store tests passed")
```

> **Real-world check:** Your startup CTO sees this and says: "This is 50 lines of Python. Why would we ever pay $70 a month for Pinecone when we can just use this?" What's the honest answer: what does this implementation handle well, and what specific things would break in production that Pinecone handles for you?

### Step 4: Use Qdrant in Local Mode

Qdrant supports running entirely in-process with no server, no Docker, no network calls. The library persists data to a local directory (or keeps it in memory).

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
)

def build_qdrant_store(documents: list[dict]) -> QdrantClient:
    """
    Build a Qdrant collection in local mode.
    
    ':memory:' → in-process, no persistence (like our InMemoryVectorStore)
    path='/tmp/qdrant_db' → file-backed persistence (survives restarts)
    """
    client = QdrantClient(":memory:")

    dim = len(documents[0]["vector"])
    collection_name = "docs"

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

    # Batch upsert: Qdrant uses integer IDs or UUIDs by default
    # We pass our string IDs as payload metadata
    points = [
        PointStruct(
            id=idx,
            vector=doc["vector"].tolist(),
            payload={
                "doc_id": doc["id"],
                "text": doc["text"],
                **doc.get("metadata", {}),
            },
        )
        for idx, doc in enumerate(documents)
    ]

    client.upsert(collection_name=collection_name, points=points)
    return client, collection_name


def qdrant_search(
    client: QdrantClient,
    collection_name: str,
    query_vector: np.ndarray,
    top_k: int = 5,
    filter_field: str | None = None,
    filter_value: Any | None = None,
) -> list[SearchResult]:
    """Search a Qdrant collection with optional metadata filtering."""
    query_filter = None
    if filter_field and filter_value is not None:
        query_filter = Filter(
            must=[FieldCondition(key=filter_field, match=MatchValue(value=filter_value))]
        )

    hits = client.search(
        collection_name=collection_name,
        query_vector=query_vector.tolist(),
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    return [
        SearchResult(
            id=hit.payload.get("doc_id", str(hit.id)),
            score=hit.score,
            text=hit.payload.get("text", ""),
            metadata={k: v for k, v in hit.payload.items() if k not in ("doc_id", "text")},
        )
        for hit in hits
    ]
```

---

## Use It

Qdrant's API is more expressive than our hand-rolled store in four key ways:

| Feature | InMemoryVectorStore | Qdrant |
|---|---|---|
| Index type | Flat (exact) | HNSW (approximate, tunable) |
| Filter support | Basic equality | Rich: range, geo, nested |
| Persistence | Memory only | Memory or file-backed |
| Named vectors | No | Yes (multiple vectors per document) |
| Payload indexing | No | Yes (filter-only fields indexed for speed) |
| Scroll/pagination | No | Yes |
| Collections | One | Many |

Named vectors are particularly useful for hybrid search (Lesson 07): store a dense vector and a sparse vector for the same document in one Qdrant point, then query both in a single operation.

The full Qdrant local setup for a production prototype looks like this:

```python
# Persistent local storage: no Docker, no server
client = QdrantClient(path="./qdrant_data")

# With named vectors for future hybrid search
from qdrant_client.models import NamedVector

client.create_collection(
    "my_docs",
    vectors_config={
        "dense": VectorParams(size=1536, distance=Distance.COSINE),
    }
)

# When you're ready for a server, just change the client init:
# client = QdrantClient(url="http://localhost:6333")
# client = QdrantClient(url="https://xyz.cloud.qdrant.io", api_key="...")
# The rest of your code is unchanged.
```

This is the production migration path: develop with `:memory:`, switch to `path=` for persistent local dev, then flip to the hosted URL for production: one line change.

> **Perspective shift:** Your ops engineer says: "We already run Postgres for everything else. Why are you spinning up another service with Qdrant instead of just using pgvector?" What's the real tradeoff here, and under what conditions would you tell them they're right?

---

## Ship It

This lesson produces a self-contained vector store you can use for any project that doesn't yet need a dedicated vector database.

**Artifact:** `03-vector-stores/outputs/skill-vector-store-setup.md`

The skill file guides choosing and configuring a vector store for a given use case, covering the full path from local dev through hosted Qdrant to pgvector.

The `code/main.py` provides both implementations side by side with a comparison test that runs both against the same data and verifies they return equivalent results.

---

## Evaluate It

Vector store bugs are insidious because the system appears to work: you get results back, they look plausible, and only careful measurement reveals they're wrong or stale.

**Check 1: Count Parity**

The document count in your vector store should match your source system. If you indexed 50,000 documents, the store should contain 50,000 vectors. Mismatch = silent indexing failure.

```python
# Run this after every bulk indexing job
expected_count = len(source_documents)
actual_count = store.count()  # or: client.count(collection_name).count
if actual_count != expected_count:
    print(f"WARNING: count mismatch! expected {expected_count}, got {actual_count}")
    # Investigate: look for failed upserts, duplicate IDs, or skipped documents
```

**Check 2: Stale Entry Detection**

If your documents update (wiki pages, product docs, knowledge base articles), verify that searches return current content, not old versions:

```python
def check_for_stale_entries(store, source_docs: dict[str, str]) -> list[str]:
    """
    For each document in source_docs, retrieve it from the store
    and check whether the stored text matches the current source.
    Returns a list of stale document IDs.
    """
    stale_ids = []
    for doc_id, current_text in source_docs.items():
        stored = store.get(doc_id)
        if stored is None:
            print(f"MISSING: {doc_id} not in store")
        elif stored.text != current_text:
            stale_ids.append(doc_id)
    return stale_ids
```

**Check 3: Filter Correctness**

Metadata filters are a frequent source of silent bugs: a typo in a field name returns zero results, which looks like "no documents matched" rather than "the filter is broken."

```python
def verify_filter(store, filter_field: str, expected_value, expected_min_count: int) -> None:
    """
    Verify that a metadata filter returns at least expected_min_count results.
    If it returns zero, the filter is likely misconfigured.
    """
    # Use a random query vector (just checking filter, not relevance)
    dummy_query = np.random.randn(384)
    results = store.search(dummy_query, top_k=10, filter_metadata={filter_field: expected_value})
    if len(results) < expected_min_count:
        print(
            f"WARNING: filter {filter_field}={expected_value!r} "
            f"returned {len(results)} results, expected >= {expected_min_count}. "
            f"Check field name spelling and value type."
        )
    else:
        print(f"[OK] filter {filter_field}={expected_value!r} → {len(results)} results")
```

---

## Exercises

1. **Easy:** Add a `list_all(limit=100)` method to `InMemoryVectorStore` that returns the most recently added documents. Test it with a corpus of 20 documents.

2. **Medium:** Implement a `rebuild_index(documents)` method that atomically replaces all vectors in the store: useful for re-indexing after changing embedding models. It should be safe: if the rebuild fails partway through, the old index should remain intact. Hint: build the new index in a temporary store, then swap references.

3. **Hard:** Extend the `InMemoryVectorStore` to support AND/OR filter expressions, not just flat equality: `filter={"AND": [{"user": "alice"}, {"type": "article"}]}`. Write a filter parser that handles AND, OR, and NOT logic. Benchmark whether the filter implementation is fast enough for 50K documents (target: < 20ms for a typical query with filter).

---

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| HNSW | "The graph index vector databases use" | Hierarchical Navigable Small World: an approximate nearest neighbor graph that enables O(log N) search; trades a small fraction of recall for orders-of-magnitude better latency at scale |
| Flat index | "Brute-force search" | Exact cosine similarity against every vector; correct but O(N); appropriate for < 100K vectors |
| Metadata filter | "Restrict search to a subset" | A condition applied before or after vector similarity search to limit results to documents matching specific field values |
| Collection | "A vector namespace" | A named group of vectors with a consistent dimension and distance metric; equivalent to a table in a relational database |
| Payload | "Metadata stored with a vector" | In Qdrant's terminology: the JSON object stored alongside each vector, containing the original text and any filterable fields |

---

## Further Reading

- [Qdrant Documentation: Quick Start](https://qdrant.tech/documentation/quick-start/): The official guide to local and server-based Qdrant; covers collections, upsert, search, and filtering
- [pgvector GitHub](https://github.com/pgvector/pgvector): The Postgres extension for vector storage; includes setup, HNSW index creation, and performance benchmarks
- [Approximate Nearest Neighbor Search in High Dimensions (Andoni et al.)](https://arxiv.org/abs/1806.09823): A readable survey of ANN algorithms; explains why brute force stops working and what HNSW, LSH, and IVF do differently
- [When to NOT Use a Vector Database](https://qdrant.tech/blog/vector-search-production-spikes/): Practical guidance on staying with Postgres+pgvector versus moving to a dedicated store
- [Pinecone: Vector Databases Explained](https://www.pinecone.io/learn/vector-database/): A concise explanation of filtering, CRUD semantics, and namespace isolation patterns in production vector stores
