"""
Embeddings Intuition — Phase 02 Lesson 01
appliedaifromscratch.com

Demonstrates: text as vectors, cosine similarity, semantic search.
Stage 1: Bag-of-words vectors (shows why lexical matching fails)
Stage 2: Neural embeddings with sentence-transformers (shows semantic matching)

pip install numpy sentence-transformers
"""

import re
from collections import Counter

import numpy as np

# ---------------------------------------------------------------------------
# PART 1: Core math — cosine similarity
# ---------------------------------------------------------------------------

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two 1-D vectors.
    Range: [-1.0, 1.0]. Higher means more similar direction.

    Why cosine and not Euclidean distance?
    Euclidean distance is sensitive to vector magnitude — a longer document
    produces a larger raw vector even if the content is the same topic as a
    shorter one. Cosine similarity measures only the angle, ignoring magnitude,
    which makes it robust for text of different lengths.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        # Zero vector has no direction — similarity is undefined, return 0
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _test_cosine_similarity():
    """Sanity checks for cosine_similarity."""
    # Identical vectors → 1.0
    v1 = np.array([1.0, 0.0, 0.0])
    assert abs(cosine_similarity(v1, v1) - 1.0) < 1e-9, "identical should be 1.0"

    # Perpendicular → 0.0
    v2 = np.array([0.0, 1.0, 0.0])
    assert abs(cosine_similarity(v1, v2)) < 1e-9, "perpendicular should be 0.0"

    # Opposite → -1.0
    v3 = np.array([-1.0, 0.0, 0.0])
    assert abs(cosine_similarity(v1, v3) + 1.0) < 1e-9, "opposite should be -1.0"

    # Zero vector → 0.0 (no division error)
    v_zero = np.zeros(3)
    assert cosine_similarity(v1, v_zero) == 0.0, "zero vector should return 0.0"

    print("[PASS] cosine_similarity: all assertions passed")


# ---------------------------------------------------------------------------
# PART 2: Bag-of-words embedding (lexical, not semantic)
# ---------------------------------------------------------------------------

def build_vocabulary(docs: list[str]) -> list[str]:
    """
    Collect all unique words across documents.
    Returns a sorted list (deterministic ordering = stable vector dimensions).
    """
    words: set[str] = set()
    for doc in docs:
        tokens = re.findall(r'\b[a-z]+\b', doc.lower())
        words.update(tokens)
    return sorted(words)


def bow_embed(text: str, vocab: list[str]) -> np.ndarray:
    """
    Bag-of-words embedding.
    Each dimension = one vocabulary word; value = how many times that word
    appears in `text`. Completely ignores word meaning and context.
    """
    tokens = re.findall(r'\b[a-z]+\b', text.lower())
    counts = Counter(tokens)
    return np.array([float(counts.get(word, 0)) for word in vocab])


class LexicalSearchEngine:
    """
    Keyword-based semantic search using bag-of-words vectors.
    Demonstrates why lexical matching fails for paraphrases.
    """

    def __init__(self, docs: list[str]) -> None:
        self.docs = docs
        self.vocab = build_vocabulary(docs)
        # Index: embed every document once at startup
        self.doc_vectors = [bow_embed(doc, self.vocab) for doc in docs]
        print(f"[LexicalSearchEngine] Indexed {len(docs)} docs | vocab size: {len(self.vocab)}")

    def search(self, query: str, top_k: int = 3) -> list[tuple[float, str]]:
        """Return top_k documents most similar to query, with scores."""
        query_vec = bow_embed(query, self.vocab)
        scored = [
            (cosine_similarity(query_vec, dv), doc)
            for dv, doc in zip(self.doc_vectors, self.docs)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]


# ---------------------------------------------------------------------------
# PART 3: Neural semantic search with sentence-transformers
# ---------------------------------------------------------------------------

class SemanticSearchEngine:
    """
    Neural semantic search using a pretrained sentence-transformer model.
    Replaces vocabulary lookup with contextual neural embeddings that capture
    meaning rather than surface form.

    The search() logic is identical to LexicalSearchEngine — only the
    embedding function changes. This is the whole point: the retrieval
    primitive is the same; the representation is what improves.
    """

    def __init__(
        self,
        docs: list[str],
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.docs = docs
        self.model = SentenceTransformer(model_name)

        # normalize_embeddings=True scales each vector to unit length.
        # This makes cosine_sim(a, b) == dot(a, b) — faster and numerically
        # stable. It does NOT change which documents rank highest.
        self.doc_vectors = self.model.encode(
            docs,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        dim = self.doc_vectors.shape[1]
        print(
            f"[SemanticSearchEngine] Indexed {len(docs)} docs | "
            f"model: {model_name} | dim: {dim}"
        )

    def search(self, query: str, top_k: int = 3) -> list[tuple[float, str]]:
        """Return top_k documents most similar to query, with scores."""
        query_vec = self.model.encode(
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )[0]
        scored = [
            (cosine_similarity(query_vec, dv), doc)
            for dv, doc in zip(self.doc_vectors, self.docs)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]


# ---------------------------------------------------------------------------
# PART 4: Sanity-check suite for production validation
# ---------------------------------------------------------------------------

def run_sanity_checks(engine: SemanticSearchEngine) -> None:
    """
    Verify that the embedding model captures basic semantic relationships.
    Run this every time you swap embedding models.
    """
    print("\n=== Sanity Checks ===")
    pairs = [
        # (text_a, text_b, expected_similar, threshold)
        ("The application crashed", "App stopped working unexpectedly", True, 0.70),
        ("How do I cancel my subscription", "Unsubscribe from my plan", True, 0.70),
        ("Invoice payment is overdue", "How to reset my password", False, 0.40),
        ("Network connection refused", "The VPN won't connect", True, 0.60),
        ("Best practices for data backup", "Billing renewal date", False, 0.35),
    ]
    passed = 0
    for a, b, should_be_similar, threshold in pairs:
        va, vb = engine.model.encode(
            [a, b], normalize_embeddings=True, convert_to_numpy=True
        )
        score = cosine_similarity(va, vb)
        if should_be_similar:
            ok = score >= threshold
        else:
            ok = score <= threshold
        status = "PASS" if ok else "FAIL"
        direction = "similar" if should_be_similar else "dissimilar"
        print(f"  [{status}] ({score:.3f}) [{direction}] '{a[:40]}' vs '{b[:40]}'")
        if ok:
            passed += 1
    print(f"\n  Result: {passed}/{len(pairs)} checks passed")


# ---------------------------------------------------------------------------
# PART 5: Main demo
# ---------------------------------------------------------------------------

DOCUMENTS = [
    "Application launch failure troubleshooting guide",
    "How to reset your password and recover account access",
    "Billing and subscription management overview",
    "Network connectivity issues and VPN configuration steps",
    "Data export, backup, and restore procedures",
    "Two-factor authentication setup and recovery codes",
    "Crash report submission and diagnostic log collection",
    "API rate limits and quota management for developers",
    "Mobile app push notification settings and permissions",
    "Account deletion and GDPR data removal requests",
]

QUERIES = [
    "my app won't start",
    "I forgot my login credentials",
    "how do I export my data to CSV",
    "the program keeps crashing with an error",
    "I want to close my account permanently",
]


def print_results(label: str, results: list[tuple[float, str]]) -> None:
    print(f"\n  Results [{label}]:")
    for rank, (score, doc) in enumerate(results, 1):
        print(f"    {rank}. ({score:.3f}) {doc}")


def main():
    print("=" * 60)
    print("Phase 02 · Lesson 01 — Embeddings Intuition")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # Step 1: Verify cosine similarity implementation
    # -----------------------------------------------------------------------
    print("\n--- Step 1: Cosine Similarity Verification ---")
    _test_cosine_similarity()

    # Manual example to build intuition
    a = np.array([1.0, 0.5, 0.2])
    b = np.array([0.9, 0.6, 0.1])   # similar direction
    c = np.array([-0.8, 0.1, 0.9])  # very different direction
    print(f"\n  cosine_sim(a, b) = {cosine_similarity(a, b):.4f}  (similar, expect ~0.98)")
    print(f"  cosine_sim(a, c) = {cosine_similarity(a, c):.4f}  (different, expect ~-0.5)")

    # -----------------------------------------------------------------------
    # Step 2: Lexical search (bag-of-words) — shows the failure mode
    # -----------------------------------------------------------------------
    print("\n--- Step 2: Lexical Search (Bag-of-Words) ---")
    print("Watch how queries with no word overlap score 0.0\n")
    lexical = LexicalSearchEngine(DOCUMENTS)

    for query in QUERIES[:3]:
        results = lexical.search(query, top_k=2)
        print(f"\n  Query: '{query}'")
        print_results("lexical", results)

    print(
        "\n  Notice: 'my app won't start' scores 0.0 against every document "
        "because none of the words overlap with 'Application launch failure'."
        "\n  This is the problem semantic search solves."
    )

    # -----------------------------------------------------------------------
    # Step 3: Semantic search — show the improvement
    # -----------------------------------------------------------------------
    print("\n--- Step 3: Semantic Search (Neural Embeddings) ---")
    print("Loading all-MiniLM-L6-v2 (downloads ~90MB on first run)...\n")

    try:
        semantic = SemanticSearchEngine(DOCUMENTS)

        print("\nFull comparison: lexical vs. semantic\n")
        for query in QUERIES:
            lex_results = lexical.search(query, top_k=1)
            sem_results = semantic.search(query, top_k=1)

            print(f"  Query: '{query}'")
            print(f"    Lexical  ({lex_results[0][0]:.3f}): {lex_results[0][1]}")
            print(f"    Semantic ({sem_results[0][0]:.3f}): {sem_results[0][1]}")
            print()

        # -----------------------------------------------------------------------
        # Step 4: Production sanity checks
        # -----------------------------------------------------------------------
        print("\n--- Step 4: Production Sanity Checks ---")
        run_sanity_checks(semantic)

        # -----------------------------------------------------------------------
        # Step 5: Score distribution analysis
        # -----------------------------------------------------------------------
        print("\n--- Step 5: Score Distribution (Production Debugging) ---")
        example_query = "my app won't start"
        all_results = semantic.search(example_query, top_k=len(DOCUMENTS))
        scores = [s for s, _ in all_results]
        print(f"\n  Query: '{example_query}'")
        print(f"  Top-1 score : {scores[0]:.3f}  {'(good, >0.7)' if scores[0] > 0.7 else '(low — may need a better model)'}")
        print(f"  Top-5 mean  : {sum(scores[:5])/5:.3f}")
        print(f"  Top-10 mean : {sum(scores)/len(scores):.3f}")
        print(
            "\n  Rule of thumb: if top-1 < 0.5 on queries you know should match,\n"
            "  the model is wrong for your domain. See Lesson 02 for model selection."
        )

    except ImportError:
        print(
            "\n  [SKIP] sentence-transformers not installed.\n"
            "  Run: pip install sentence-transformers\n"
            "  Then re-run this script to see the semantic search results."
        )

    print("\n" + "=" * 60)
    print("Done. Next: Lesson 02 — Embedding Models (model selection at scale)")
    print("=" * 60)


if __name__ == "__main__":
    main()
