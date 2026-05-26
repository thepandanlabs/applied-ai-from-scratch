"""
Embedding Models - Phase 02 Lesson 02
appliedaifromscratch.com

Benchmark multiple embedding models on a small labeled test set.
Computes MRR@5 and Hit Rate@5 to identify the best-fit model for your domain.

pip install numpy sentence-transformers openai httpx

To run OpenAI benchmarks: set OPENAI_API_KEY environment variable.
To run Voyage benchmarks: set VOYAGE_API_KEY environment variable (optional).
"""

import os
import time
from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# Test dataset - replace with your own (query, [relevant_doc_ids]) pairs
# ---------------------------------------------------------------------------

DOCUMENTS = [
    ("doc_0", "How to configure multi-factor authentication for your account"),
    ("doc_1", "Understanding your monthly invoice and billing cycle"),
    ("doc_2", "Troubleshooting application startup failures and crash reports"),
    ("doc_3", "API rate limits: requests per second and daily quota management"),
    ("doc_4", "Data retention policies and automated backup schedules"),
    ("doc_5", "Setting up SSO with SAML 2.0 and identity providers"),
    ("doc_6", "Network timeout errors and connection refused troubleshooting"),
    ("doc_7", "Exporting account data for GDPR compliance requests"),
    ("doc_8", "Password reset flow and recovery email configuration"),
    ("doc_9", "Webhook event types and payload schema reference for developers"),
]

LABELED_QUERIES = [
    ("my login isn't working with the authenticator app", ["doc_0"]),
    ("I can't see my latest charge on the bill", ["doc_1"]),
    ("the app crashes immediately when I try to open it", ["doc_2"]),
    ("how do I avoid hitting API limits in production", ["doc_3"]),
    ("where are my files backed up automatically", ["doc_4"]),
    ("set up enterprise single sign-on with SAML", ["doc_5"]),
    ("connection keeps timing out with refused error", ["doc_6"]),
    ("I need to download all my data for legal reasons", ["doc_7"]),
    ("forgot password and can't get into my account", ["doc_8"]),
    ("what data format do webhooks send to my endpoint", ["doc_9"]),
]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def cosine_similarity_matrix(query_vecs: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """
    Batch cosine similarity: shape (num_queries, num_docs).
    Assumes unit-normalized vectors (dot product == cosine similarity).
    """
    return query_vecs @ doc_vecs.T


def compute_mrr_at_k(
    query_vecs: np.ndarray,
    doc_vecs: np.ndarray,
    labeled_queries: list[tuple[str, list[str]]],
    doc_ids: list[str],
    k: int = 5,
) -> dict:
    """
    Compute MRR@K and Hit Rate@K.

    MRR@K: mean of 1/rank for each query, where rank is position of
    the first relevant doc in the top-K results. Queries where no relevant
    doc appears in top-K contribute 0.

    Hit Rate@K: fraction of queries where at least one relevant doc
    appears in top-K.
    """
    id_to_idx = {doc_id: i for i, doc_id in enumerate(doc_ids)}
    sim_matrix = cosine_similarity_matrix(query_vecs, doc_vecs)

    reciprocal_ranks = []
    hits = []
    per_query = []

    for q_idx, (query_text, relevant_ids) in enumerate(labeled_queries):
        scores = sim_matrix[q_idx]
        ranked_indices = np.argsort(scores)[::-1][:k]
        ranked_doc_ids = [doc_ids[i] for i in ranked_indices]

        rr = 0.0
        hit = False
        first_relevant_rank = None

        for rank, doc_id in enumerate(ranked_doc_ids, start=1):
            if doc_id in relevant_ids:
                rr = 1.0 / rank
                hit = True
                first_relevant_rank = rank
                break

        reciprocal_ranks.append(rr)
        hits.append(1 if hit else 0)
        per_query.append({
            "query": query_text,
            "rr": rr,
            "hit": hit,
            "first_relevant_rank": first_relevant_rank,
            "top1_doc": ranked_doc_ids[0] if ranked_doc_ids else None,
            "top1_score": float(scores[ranked_indices[0]]) if ranked_indices.size else 0.0,
        })

    return {
        "mrr": float(np.mean(reciprocal_ranks)),
        "hit_rate": float(np.mean(hits)),
        "k": k,
        "per_query": per_query,
    }


# ---------------------------------------------------------------------------
# Model evaluation wrappers
# ---------------------------------------------------------------------------

@dataclass
class ModelResult:
    model_name: str
    mrr: float
    hit_rate: float
    query_latency_ms: float   # time to encode all queries (not docs)
    dim: int
    per_query: list[dict]
    error: str | None = None


def evaluate_sentence_transformer(
    model_name: str,
    documents: list[tuple[str, str]],
    labeled_queries: list[tuple[str, list[str]]],
    k: int = 5,
) -> ModelResult:
    """Evaluate a HuggingFace sentence-transformer model (local inference)."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return ModelResult(
            model_name=model_name, mrr=0.0, hit_rate=0.0,
            query_latency_ms=0.0, dim=0, per_query=[],
            error="sentence-transformers not installed",
        )

    doc_ids = [d[0] for d in documents]
    doc_texts = [d[1] for d in documents]
    query_texts = [q[0] for q in labeled_queries]

    print(f"  Loading {model_name}...", end=" ", flush=True)
    model = SentenceTransformer(model_name)

    doc_vecs = model.encode(
        doc_texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    t0 = time.perf_counter()
    query_vecs = model.encode(
        query_texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    print(f"done ({latency_ms:.0f}ms for {len(query_texts)} queries)")

    metrics = compute_mrr_at_k(query_vecs, doc_vecs, labeled_queries, doc_ids, k=k)
    return ModelResult(
        model_name=model_name,
        mrr=metrics["mrr"],
        hit_rate=metrics["hit_rate"],
        query_latency_ms=latency_ms,
        dim=int(doc_vecs.shape[1]),
        per_query=metrics["per_query"],
    )


def evaluate_openai(
    model_name: str,
    documents: list[tuple[str, str]],
    labeled_queries: list[tuple[str, list[str]]],
    dimensions: int | None = None,
    k: int = 5,
) -> ModelResult:
    """
    Evaluate an OpenAI embedding model.
    Requires: OPENAI_API_KEY environment variable.
    `dimensions` enables Matryoshka truncation (text-embedding-3-* only).
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return ModelResult(
            model_name=model_name, mrr=0.0, hit_rate=0.0,
            query_latency_ms=0.0, dim=0, per_query=[],
            error="OPENAI_API_KEY not set - skipping",
        )

    try:
        import openai
    except ImportError:
        return ModelResult(
            model_name=model_name, mrr=0.0, hit_rate=0.0,
            query_latency_ms=0.0, dim=0, per_query=[],
            error="openai package not installed",
        )

    client = openai.OpenAI(api_key=api_key)
    doc_ids = [d[0] for d in documents]
    doc_texts = [d[1] for d in documents]
    query_texts = [q[0] for q in labeled_queries]

    def embed_batch(texts: list[str]) -> np.ndarray:
        kwargs: dict = {"model": model_name, "input": texts}
        if dimensions:
            kwargs["dimensions"] = dimensions
        response = client.embeddings.create(**kwargs)
        vecs = np.array([item.embedding for item in response.data])
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # avoid divide-by-zero
        return vecs / norms

    display_name = f"{model_name}@{dimensions}d" if dimensions else model_name
    print(f"  Calling OpenAI {display_name}...", end=" ", flush=True)

    try:
        doc_vecs = embed_batch(doc_texts)
        t0 = time.perf_counter()
        query_vecs = embed_batch(query_texts)
        latency_ms = (time.perf_counter() - t0) * 1000
        print(f"done ({latency_ms:.0f}ms for {len(query_texts)} queries)")
    except Exception as e:
        print(f"failed: {e}")
        return ModelResult(
            model_name=display_name, mrr=0.0, hit_rate=0.0,
            query_latency_ms=0.0, dim=0, per_query=[],
            error=str(e),
        )

    actual_dim = dimensions if dimensions else int(doc_vecs.shape[1])
    metrics = compute_mrr_at_k(query_vecs, doc_vecs, labeled_queries, doc_ids, k=k)
    return ModelResult(
        model_name=display_name,
        mrr=metrics["mrr"],
        hit_rate=metrics["hit_rate"],
        query_latency_ms=latency_ms,
        dim=actual_dim,
        per_query=metrics["per_query"],
    )


def evaluate_voyage(
    model_name: str,
    documents: list[tuple[str, str]],
    labeled_queries: list[tuple[str, list[str]]],
    k: int = 5,
) -> ModelResult:
    """
    Evaluate a Voyage AI embedding model.
    Requires: VOYAGE_API_KEY environment variable.
    pip install voyageai
    """
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        return ModelResult(
            model_name=model_name, mrr=0.0, hit_rate=0.0,
            query_latency_ms=0.0, dim=0, per_query=[],
            error="VOYAGE_API_KEY not set - skipping",
        )

    try:
        import voyageai
    except ImportError:
        return ModelResult(
            model_name=model_name, mrr=0.0, hit_rate=0.0,
            query_latency_ms=0.0, dim=0, per_query=[],
            error="voyageai package not installed (pip install voyageai)",
        )

    client = voyageai.Client(api_key=api_key)
    doc_ids = [d[0] for d in documents]
    doc_texts = [d[1] for d in documents]
    query_texts = [q[0] for q in labeled_queries]

    print(f"  Calling Voyage {model_name}...", end=" ", flush=True)

    try:
        doc_result = client.embed(doc_texts, model=model_name, input_type="document")
        doc_vecs = np.array(doc_result.embeddings)
        norms = np.linalg.norm(doc_vecs, axis=1, keepdims=True)
        doc_vecs = doc_vecs / np.where(norms == 0, 1, norms)

        t0 = time.perf_counter()
        q_result = client.embed(query_texts, model=model_name, input_type="query")
        latency_ms = (time.perf_counter() - t0) * 1000
        query_vecs = np.array(q_result.embeddings)
        norms = np.linalg.norm(query_vecs, axis=1, keepdims=True)
        query_vecs = query_vecs / np.where(norms == 0, 1, norms)
        print(f"done ({latency_ms:.0f}ms)")
    except Exception as e:
        print(f"failed: {e}")
        return ModelResult(
            model_name=model_name, mrr=0.0, hit_rate=0.0,
            query_latency_ms=0.0, dim=0, per_query=[],
            error=str(e),
        )

    metrics = compute_mrr_at_k(query_vecs, doc_vecs, labeled_queries, doc_ids, k=k)
    return ModelResult(
        model_name=model_name,
        mrr=metrics["mrr"],
        hit_rate=metrics["hit_rate"],
        query_latency_ms=latency_ms,
        dim=int(doc_vecs.shape[1]),
        per_query=metrics["per_query"],
    )


# ---------------------------------------------------------------------------
# Matryoshka truncation experiment
# ---------------------------------------------------------------------------

def matryoshka_truncation_experiment(
    documents: list[tuple[str, str]],
    labeled_queries: list[tuple[str, list[str]]],
) -> None:
    """
    Show how OpenAI text-embedding-3-small quality degrades (or doesn't)
    as we truncate to fewer dimensions using Matryoshka.
    Requires OPENAI_API_KEY.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        print("  [SKIP] OPENAI_API_KEY not set - Matryoshka experiment skipped")
        return

    print("\n--- Matryoshka Truncation Experiment ---")
    print("Model: text-embedding-3-small")
    print(f"{'Dims':>6}  {'MRR@5':>7}  {'Hit@5':>7}  {'Relative Quality':>18}")
    print("-" * 50)

    dims_to_test = [256, 512, 768, 1024, 1536]
    results = []
    baseline_mrr = None

    for dim in dims_to_test:
        r = evaluate_openai(
            "text-embedding-3-small", documents, labeled_queries, dimensions=dim
        )
        if r.error:
            print(f"  {dim:>6}  ERROR: {r.error}")
            continue
        results.append((dim, r.mrr, r.hit_rate))
        if baseline_mrr is None:
            baseline_mrr = r.mrr  # first (smallest) as reference... use last as baseline

    if results:
        # Re-baseline against the largest dimension tested
        baseline_mrr = results[-1][1]
        for dim, mrr, hit_rate in results:
            rel = (mrr / baseline_mrr * 100) if baseline_mrr > 0 else 0
            print(f"  {dim:>6}  {mrr:>7.3f}  {hit_rate:>7.1%}  {rel:>17.1f}%")

        print("\n  Note: Matryoshka lets you trade ~5-10% quality for 6x storage reduction.")
        print("  Find your knee point: the smallest dim that preserves >95% relative quality.")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_results_table(results: list[ModelResult]) -> None:
    """Print a sorted comparison table of all evaluated models."""
    valid = [r for r in results if not r.error]
    skipped = [r for r in results if r.error]

    if not valid:
        print("\n  No models successfully evaluated.")
        return

    print(f"\n{'Model':<48} {'Dims':>5} {'MRR@5':>7} {'Hit@5':>7} {'Q-Latency':>12}")
    print("-" * 85)
    for r in sorted(valid, key=lambda x: x.mrr, reverse=True):
        lat = f"{r.query_latency_ms:.0f}ms"
        print(
            f"{r.model_name:<48} {r.dim:>5} {r.mrr:>7.3f} "
            f"{r.hit_rate:>7.1%} {lat:>12}"
        )

    if skipped:
        print("\n  Skipped (configure API key or install package):")
        for r in skipped:
            print(f"    {r.model_name}: {r.error}")

    best = max(valid, key=lambda x: x.mrr)
    print(f"\n  Winner: {best.model_name}  (MRR@5={best.mrr:.3f}, Hit@5={best.hit_rate:.1%})")


def print_failure_analysis(results: list[ModelResult]) -> None:
    """For each model, show the worst-performing query (lowest RR)."""
    valid = [r for r in results if not r.error and r.per_query]
    if not valid:
        return

    print("\n--- Worst-Performing Query Per Model ---")
    for r in sorted(valid, key=lambda x: x.mrr, reverse=True):
        worst = min(r.per_query, key=lambda q: q["rr"])
        rank_str = f"rank {worst['first_relevant_rank']}" if worst["hit"] else "not in top-5"
        print(f"\n  {r.model_name}")
        print(f"    Query : '{worst['query'][:60]}'")
        print(f"    Result: {rank_str} | top-1 retrieved: '{worst['top1_doc']}' ({worst['top1_score']:.3f})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Phase 02 · Lesson 02 - Embedding Models Benchmark")
    print("=" * 60)
    print(f"\nTest set: {len(DOCUMENTS)} documents, {len(LABELED_QUERIES)} labeled queries")
    print("Metric: MRR@5 (Mean Reciprocal Rank at K=5)\n")

    results: list[ModelResult] = []

    # ------------------------------------------------------------------
    # Stage 1: Local sentence-transformer models
    # These require no API key and run on CPU.
    # ------------------------------------------------------------------
    print("--- Stage 1: Local Models (sentence-transformers) ---")
    local_models = [
        "all-MiniLM-L6-v2",      # 384d - prototyping baseline, very fast
        "all-mpnet-base-v2",      # 768d - better quality baseline
    ]
    for model_name in local_models:
        r = evaluate_sentence_transformer(model_name, DOCUMENTS, LABELED_QUERIES)
        results.append(r)

    # ------------------------------------------------------------------
    # Stage 2: OpenAI embedding models (requires OPENAI_API_KEY)
    # Comment out if you don't have an API key.
    # Cost: ~$0.001 for this test set at text-embedding-3-small rates.
    # ------------------------------------------------------------------
    print("\n--- Stage 2: OpenAI API Models ---")
    print("  (requires OPENAI_API_KEY; will skip if not set)")

    openai_models = [
        ("text-embedding-3-small", None),     # 1536d, full quality
        ("text-embedding-3-small", 256),      # 256d, Matryoshka truncated
        ("text-embedding-3-large", None),     # 3072d - highest quality, higher cost
    ]
    for model_name, dims in openai_models:
        r = evaluate_openai(model_name, DOCUMENTS, LABELED_QUERIES, dimensions=dims)
        results.append(r)

    # ------------------------------------------------------------------
    # Stage 3: Voyage AI (requires VOYAGE_API_KEY)
    # pip install voyageai
    # ------------------------------------------------------------------
    print("\n--- Stage 3: Voyage AI Models ---")
    print("  (requires VOYAGE_API_KEY + 'pip install voyageai'; will skip if not set)")

    r = evaluate_voyage("voyage-3-lite", DOCUMENTS, LABELED_QUERIES)
    results.append(r)

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print_results_table(results)
    print_failure_analysis(results)

    # ------------------------------------------------------------------
    # Matryoshka experiment (OpenAI only)
    # ------------------------------------------------------------------
    matryoshka_truncation_experiment(DOCUMENTS, LABELED_QUERIES)

    # ------------------------------------------------------------------
    # Interpretation guidance
    # ------------------------------------------------------------------
    print("\n--- How to Use These Results ---")
    print("""
  1. If all models score MRR@5 > 0.9 on your domain:
     → Use text-embedding-3-small (cost-efficient, fast)

  2. If general models score MRR@5 < 0.75:
     → Your domain is specialized (code, law, medical, etc.)
     → Evaluate domain-specific models (voyage-code-3, legal-bert)
     → Or fine-tune a local model on your labeled pairs

  3. If costs matter:
     → Test Matryoshka truncation to find your quality/cost knee
     → Consider self-hosting all-mpnet-base-v2 if volume > 10M docs/month

  4. Multilingual content:
     → Add BGE-M3 to your benchmark (pip install -U FlagEmbedding)
     → Or Cohere embed-multilingual-v3.0 for API convenience
    """)

    print("=" * 60)
    print("Done. Next: Lesson 03 - Vector Stores")
    print("=" * 60)


if __name__ == "__main__":
    main()
