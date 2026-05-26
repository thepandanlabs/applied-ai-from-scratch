"""
Vector Stores - Phase 02 Lesson 03
appliedaifromscratch.com

Part 1: Build a minimal in-memory vector store from scratch (NumPy only)
Part 2: Do the same with Qdrant in local mode (no Docker, no server)
Part 3: Run both against the same data and compare results

pip install numpy qdrant-client sentence-transformers
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Shared data structure
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    id: str
    score: float
    text: str
    metadata: dict[str, Any]

    def __repr__(self) -> str:
        meta_str = ", ".join(f"{k}={v!r}" for k, v in self.metadata.items())
        return f"SearchResult(id={self.id!r}, score={self.score:.4f}, meta=({meta_str}))"


# ---------------------------------------------------------------------------
# PART 1: In-memory vector store from scratch
# ---------------------------------------------------------------------------

class InMemoryVectorStore:
    """
    Minimal vector store using Python dicts and NumPy for similarity search.

    Design decisions:
    - Normalize vectors on insert: dot product == cosine similarity (faster search)
    - add() raises on duplicate: prevents silent data corruption
    - upsert() for update semantics: explicit about overwrite intent
    - Pre-filter for metadata: simplest correct implementation; scales to ~100K docs
    """

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._vectors: dict[str, np.ndarray] = {}
        self._texts: dict[str, str] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(
        self,
        doc_id: str,
        text: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a new document. Raises ValueError if doc_id already exists."""
        if doc_id in self._vectors:
            raise ValueError(
                f"Document '{doc_id}' already exists. "
                "Use upsert() if you intend to update it."
            )
        self._store(doc_id, text, vector, metadata or {})

    def upsert(
        self,
        doc_id: str,
        text: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or replace a document (safe for update workflows)."""
        self._store(doc_id, text, vector, metadata or {})

    def _store(
        self,
        doc_id: str,
        text: str,
        vector: np.ndarray,
        metadata: dict[str, Any],
    ) -> None:
        norm = np.linalg.norm(vector)
        self._vectors[doc_id] = vector / norm if norm > 0 else vector.copy()
        self._texts[doc_id] = text
        self._metadata[doc_id] = metadata

    def delete(self, doc_id: str) -> bool:
        """Remove a document. Returns True if found and removed, False otherwise."""
        if doc_id not in self._vectors:
            return False
        del self._vectors[doc_id]
        del self._texts[doc_id]
        del self._metadata[doc_id]
        return True

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, doc_id: str) -> SearchResult | None:
        """Retrieve a document by ID. Returns None if not found."""
        if doc_id not in self._vectors:
            return None
        return SearchResult(
            id=doc_id,
            score=1.0,
            text=self._texts[doc_id],
            metadata=self._metadata[doc_id],
        )

    def count(self) -> int:
        """Number of documents currently indexed."""
        return len(self._vectors)

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Return the top_k most similar documents to query_vector.

        filter_metadata: optional {field: value} dict - only documents
        matching ALL conditions are searched.

        Implementation: brute-force cosine similarity (exact nearest neighbor).
        For corpora > 100K vectors, use an ANN index (Qdrant, pgvector+HNSW).
        """
        if not self._vectors:
            return []

        norm = np.linalg.norm(query_vector)
        q = query_vector / norm if norm > 0 else query_vector

        # Apply pre-filter
        candidates = list(self._vectors.keys())
        if filter_metadata:
            candidates = [
                doc_id for doc_id in candidates
                if all(
                    self._metadata[doc_id].get(field) == value
                    for field, value in filter_metadata.items()
                )
            ]

        if not candidates:
            return []

        # Batch similarity: stack candidate vectors, compute all scores at once
        ids = candidates
        matrix = np.stack([self._vectors[i] for i in ids])  # (N, D)
        scores = matrix @ q  # dot product == cosine sim for unit vectors: (N,)

        k = min(top_k, len(ids))
        # np.argpartition is O(N) - faster than full sort for large N
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

    def __repr__(self) -> str:
        return f"InMemoryVectorStore(name={self.name!r}, docs={self.count()})"


# ---------------------------------------------------------------------------
# PART 2: Qdrant local-mode vector store
# ---------------------------------------------------------------------------

class QdrantVectorStore:
    """
    Vector store wrapper around Qdrant in local mode (no Docker, no server).

    Uses ':memory:' for in-process storage (like InMemoryVectorStore).
    Switch to path='./qdrant_data' for persistence across restarts.
    Switch to url='http://...' for a production server - zero code changes.
    """

    def __init__(
        self,
        collection_name: str,
        dim: int,
        storage: str = ":memory:",
    ) -> None:
        """
        storage options:
          ':memory:' - in-process, no persistence
          './qdrant_data' - file-backed persistence
          'http://localhost:6333' - server (use url= kwarg instead)
        """
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.collection_name = collection_name
        self.dim = dim
        self._id_map: dict[str, int] = {}  # str doc_id → int Qdrant point ID
        self._next_id = 0

        self.client = QdrantClient(storage)
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    def _get_or_create_int_id(self, doc_id: str) -> int:
        """Qdrant uses integer point IDs; we map string IDs to integers."""
        if doc_id not in self._id_map:
            self._id_map[doc_id] = self._next_id
            self._next_id += 1
        return self._id_map[doc_id]

    def upsert(
        self,
        doc_id: str,
        text: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        from qdrant_client.models import PointStruct

        point_id = self._get_or_create_int_id(doc_id)
        payload = {"doc_id": doc_id, "text": text, **(metadata or {})}

        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=point_id, vector=vector.tolist(), payload=payload)],
        )

    def add(
        self,
        doc_id: str,
        text: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Alias for upsert - Qdrant uses upsert semantics natively."""
        self.upsert(doc_id, text, vector, metadata)

    def delete(self, doc_id: str) -> bool:
        from qdrant_client.models import PointIdsList

        if doc_id not in self._id_map:
            return False
        point_id = self._id_map[doc_id]
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=[point_id]),
        )
        del self._id_map[doc_id]
        return True

    def get(self, doc_id: str) -> SearchResult | None:
        if doc_id not in self._id_map:
            return None
        point_id = self._id_map[doc_id]
        results = self.client.retrieve(
            collection_name=self.collection_name,
            ids=[point_id],
            with_payload=True,
        )
        if not results:
            return None
        p = results[0].payload
        return SearchResult(
            id=p.get("doc_id", doc_id),
            score=1.0,
            text=p.get("text", ""),
            metadata={k: v for k, v in p.items() if k not in ("doc_id", "text")},
        )

    def count(self) -> int:
        return self.client.count(collection_name=self.collection_name).count

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        query_filter = None
        if filter_metadata:
            query_filter = Filter(
                must=[
                    FieldCondition(key=field, match=MatchValue(value=value))
                    for field, value in filter_metadata.items()
                ]
            )

        hits = self.client.search(
            collection_name=self.collection_name,
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
                metadata={
                    k: v for k, v in hit.payload.items()
                    if k not in ("doc_id", "text")
                },
            )
            for hit in hits
        ]

    def __repr__(self) -> str:
        return (
            f"QdrantVectorStore(collection={self.collection_name!r}, "
            f"docs={self.count()})"
        )


# ---------------------------------------------------------------------------
# PART 3: Verification tests - run on both store implementations
# ---------------------------------------------------------------------------

def run_store_tests(store, label: str) -> None:
    """
    Comprehensive test suite for any vector store implementation.
    Both InMemoryVectorStore and QdrantVectorStore should pass all tests.
    """
    print(f"\n--- Testing: {label} ---")

    v1 = np.array([1.0, 0.0, 0.0])
    v2 = np.array([0.9, 0.1, 0.0])   # similar to v1
    v3 = np.array([0.0, 0.0, 1.0])   # orthogonal to v1

    # --- Test 1: add and count ---
    store.add("a", "alpha article", v1, {"user": "alice", "type": "article"})
    store.add("b", "beta article", v2, {"user": "bob", "type": "article"})
    store.add("c", "gamma faq", v3, {"user": "alice", "type": "faq"})
    assert store.count() == 3, f"[FAIL] count: expected 3, got {store.count()}"
    print("  [PASS] add + count")

    # --- Test 2: search order ---
    results = store.search(v1, top_k=2)
    assert len(results) == 2, f"[FAIL] expected 2 results, got {len(results)}"
    assert results[0].id == "a", f"[FAIL] expected 'a' first, got {results[0].id}"
    assert results[0].score >= results[1].score, "[FAIL] scores should be descending"
    print("  [PASS] search order")

    # --- Test 3: metadata filter ---
    alice_results = store.search(v1, top_k=10, filter_metadata={"user": "alice"})
    assert all(r.metadata.get("user") == "alice" for r in alice_results), \
        "[FAIL] filter should only return alice's docs"
    assert len(alice_results) == 2, f"[FAIL] alice has 2 docs, got {len(alice_results)}"
    print("  [PASS] metadata filter")

    # --- Test 4: delete ---
    deleted = store.delete("b")
    assert deleted is True, "[FAIL] delete existing should return True"
    assert store.count() == 2, f"[FAIL] count after delete: expected 2, got {store.count()}"
    assert store.get("b") is None, "[FAIL] deleted doc should return None on get"
    print("  [PASS] delete")

    # --- Test 5: delete nonexistent ---
    assert store.delete("does_not_exist") is False, \
        "[FAIL] deleting nonexistent should return False"
    print("  [PASS] delete nonexistent")

    # --- Test 6: upsert (update) ---
    new_v = np.array([0.5, 0.5, 0.0])
    store.upsert("a", "updated alpha text", new_v, {"user": "alice", "type": "article"})
    updated = store.get("a")
    assert updated is not None, "[FAIL] get after upsert should not return None"
    assert updated.text == "updated alpha text", "[FAIL] upsert should update text"
    print("  [PASS] upsert")

    # --- Test 7: filter returns empty gracefully ---
    no_results = store.search(v1, top_k=5, filter_metadata={"user": "nobody"})
    assert no_results == [], f"[FAIL] nonexistent filter should return [], got {no_results}"
    print("  [PASS] empty filter result")

    print(f"  All tests passed for {label}")


# ---------------------------------------------------------------------------
# PART 4: Side-by-side comparison with real embeddings
# ---------------------------------------------------------------------------

def run_comparison(documents: list[dict], queries: list[str]) -> None:
    """
    Embed a document set with sentence-transformers.
    Index into both InMemoryVectorStore and QdrantVectorStore.
    Run the same queries against both and print a comparison.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("\n  [SKIP] sentence-transformers not installed. pip install sentence-transformers")
        return

    print("\n--- Side-by-Side Comparison: Custom vs Qdrant ---")

    model = SentenceTransformer("all-MiniLM-L6-v2")
    doc_texts = [d["text"] for d in documents]

    # Encode all documents
    doc_vecs = model.encode(doc_texts, normalize_embeddings=True, convert_to_numpy=True)
    dim = doc_vecs.shape[1]

    # Build both stores
    custom_store = InMemoryVectorStore("custom")
    try:
        qdrant_store = QdrantVectorStore("docs", dim=dim)
        has_qdrant = True
    except ImportError:
        print("  [SKIP] qdrant-client not installed. pip install qdrant-client")
        has_qdrant = False

    for doc, vec in zip(documents, doc_vecs):
        custom_store.upsert(doc["id"], doc["text"], vec, doc.get("metadata", {}))
        if has_qdrant:
            qdrant_store.upsert(doc["id"], doc["text"], vec, doc.get("metadata", {}))

    # Run queries
    for query in queries:
        q_vec = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
        custom_results = custom_store.search(q_vec, top_k=2)
        qdrant_results = qdrant_store.search(q_vec, top_k=2) if has_qdrant else []

        print(f"\n  Query: '{query}'")
        print(f"    Custom  → {custom_results[0].id} ({custom_results[0].score:.4f}): {custom_results[0].text[:50]}")
        if has_qdrant and qdrant_results:
            print(f"    Qdrant  → {qdrant_results[0].id} ({qdrant_results[0].score:.4f}): {qdrant_results[0].text[:50]}")

        # Verify both return the same top-1
        if has_qdrant and qdrant_results:
            match = custom_results[0].id == qdrant_results[0].id
            print(f"    Agreement: {'YES' if match else 'NO (investigate!)'}")


# ---------------------------------------------------------------------------
# PART 5: Production verification helpers
# ---------------------------------------------------------------------------

def check_count_parity(store, expected_count: int, label: str = "") -> None:
    """Verify the store contains exactly expected_count documents."""
    actual = store.count()
    status = "OK" if actual == expected_count else "MISMATCH"
    print(f"  [{status}] {label} count: expected {expected_count}, actual {actual}")
    if actual != expected_count:
        print(f"         → Check for failed upserts, duplicate IDs, or skipped docs")


def check_filter_health(
    store,
    filter_field: str,
    filter_value: Any,
    expected_min: int,
    dim: int,
) -> None:
    """Verify a metadata filter returns at least expected_min results."""
    dummy_query = np.random.randn(dim)
    dummy_query = dummy_query / np.linalg.norm(dummy_query)
    results = store.search(dummy_query, top_k=100, filter_metadata={filter_field: filter_value})
    status = "OK" if len(results) >= expected_min else "WARN"
    print(
        f"  [{status}] filter {filter_field}={filter_value!r}: "
        f"{len(results)} results (min expected: {expected_min})"
    )
    if len(results) < expected_min:
        print(
            f"         → If you expect {expected_min}+ docs with this value, "
            f"check field name spelling and value type."
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

DEMO_DOCUMENTS = [
    {"id": "doc_0", "text": "Application launch failure troubleshooting guide", "metadata": {"type": "troubleshooting", "lang": "en"}},
    {"id": "doc_1", "text": "How to reset your password and recover account access", "metadata": {"type": "howto", "lang": "en"}},
    {"id": "doc_2", "text": "Billing and subscription management overview", "metadata": {"type": "billing", "lang": "en"}},
    {"id": "doc_3", "text": "Network connectivity issues and VPN configuration steps", "metadata": {"type": "troubleshooting", "lang": "en"}},
    {"id": "doc_4", "text": "Data export, backup, and restore procedures", "metadata": {"type": "howto", "lang": "en"}},
    {"id": "doc_5", "text": "Two-factor authentication setup and recovery codes", "metadata": {"type": "howto", "lang": "en"}},
    {"id": "doc_6", "text": "Crash report submission and diagnostic log collection", "metadata": {"type": "troubleshooting", "lang": "en"}},
    {"id": "doc_7", "text": "API rate limits and quota management for developers", "metadata": {"type": "developer", "lang": "en"}},
    {"id": "doc_8", "text": "Mobile app push notification settings and permissions", "metadata": {"type": "howto", "lang": "en"}},
    {"id": "doc_9", "text": "Account deletion and GDPR data removal requests", "metadata": {"type": "billing", "lang": "en"}},
]

DEMO_QUERIES = [
    "my app won't start",
    "I forgot my password",
    "how do I export my data",
]


def main():
    print("=" * 60)
    print("Phase 02 · Lesson 03 - Vector Stores")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Step 1: Unit tests with synthetic vectors
    # ------------------------------------------------------------------
    print("\n=== Step 1: Unit Tests (Synthetic Vectors) ===")

    custom_store = InMemoryVectorStore("test")
    run_store_tests(custom_store, "InMemoryVectorStore")

    try:
        qdrant_store = QdrantVectorStore("test_collection", dim=3)
        run_store_tests(qdrant_store, "QdrantVectorStore")
    except ImportError:
        print("\n  [SKIP] qdrant-client not installed. pip install qdrant-client")

    # ------------------------------------------------------------------
    # Step 2: Side-by-side comparison with real embeddings
    # ------------------------------------------------------------------
    print("\n=== Step 2: Side-by-Side Comparison (Real Embeddings) ===")
    run_comparison(DEMO_DOCUMENTS, DEMO_QUERIES)

    # ------------------------------------------------------------------
    # Step 3: Production verification helpers
    # ------------------------------------------------------------------
    print("\n=== Step 3: Production Verification Checks ===")

    # Build a fresh store for verification demo
    demo_store = InMemoryVectorStore("demo")
    rng = np.random.default_rng(42)
    for doc in DEMO_DOCUMENTS:
        v = rng.standard_normal(384)
        demo_store.upsert(doc["id"], doc["text"], v, doc["metadata"])

    check_count_parity(demo_store, expected_count=len(DEMO_DOCUMENTS), label="demo_store")
    check_filter_health(demo_store, "type", "troubleshooting", expected_min=3, dim=384)
    check_filter_health(demo_store, "type", "nonexistent_type", expected_min=1, dim=384)

    # ------------------------------------------------------------------
    # Step 4: Performance comparison
    # ------------------------------------------------------------------
    print("\n=== Step 4: Performance Comparison ===")

    sizes = [100, 1_000, 10_000]
    dim = 384

    for n in sizes:
        rng = np.random.default_rng(0)
        docs = rng.standard_normal((n, dim))
        docs = docs / np.linalg.norm(docs, axis=1, keepdims=True)
        query = rng.standard_normal(dim)
        query = query / np.linalg.norm(query)

        store = InMemoryVectorStore(f"perf_{n}")
        for i in range(n):
            store.add(f"doc_{i}", f"text {i}", docs[i], {})

        t0 = time.perf_counter()
        NUM_QUERIES = 10
        for _ in range(NUM_QUERIES):
            store.search(query, top_k=5)
        elapsed_ms = (time.perf_counter() - t0) / NUM_QUERIES * 1000

        print(f"  n={n:>6} docs, dim={dim}: {elapsed_ms:.2f}ms per query (brute force)")

    print(
        "\n  Rule: brute force is fast enough up to ~100K docs on modern hardware."
        "\n  Above that, switch to Qdrant (HNSW) or pgvector with an HNSW index."
    )

    print("\n" + "=" * 60)
    print("Done. Next: Lesson 04 - Chunking Strategies")
    print("=" * 60)


if __name__ == "__main__":
    main()
