# No dependencies required — pure Python standard library only.
# Usage: python main.py
#
# Implements from scratch:
#   precision@K, recall@K, hit rate, MRR, nDCG@K,
#   context precision, context recall
# Then demonstrates how metrics change with K on a sample golden dataset.

import math


# ---------------------------------------------------------------------------
# Sample golden dataset
# ---------------------------------------------------------------------------
# In production: replace this with your own (query, relevant_ids) pairs,
# and populate retrieved_ids from your actual RAG pipeline output.
#
# minimum viable eval set: 20 pairs
# statistical confidence: 50+ pairs
# production benchmark: 100+ pairs with multiple annotators

GOLDEN_DATASET = [
    {
        "query": "What is the recommended dosage for adults?",
        "relevant_ids": {"doc_3", "doc_7"},
        "retrieved_ids": ["doc_3", "doc_1", "doc_7", "doc_9", "doc_2"],
    },
    {
        "query": "How do I configure the authentication timeout?",
        "relevant_ids": {"doc_12"},
        "retrieved_ids": ["doc_5", "doc_12", "doc_8", "doc_3", "doc_14"],
    },
    {
        "query": "What are the contraindications for patients with liver disease?",
        "relevant_ids": {"doc_3", "doc_5", "doc_9"},
        "retrieved_ids": ["doc_3", "doc_9", "doc_2", "doc_5", "doc_11"],
    },
    {
        "query": "What version introduced the rate limiting feature?",
        "relevant_ids": {"doc_22"},
        "retrieved_ids": ["doc_1", "doc_4", "doc_6", "doc_22", "doc_9"],
    },
    {
        "query": "Explain the refund policy for digital products",
        "relevant_ids": {"doc_8", "doc_15"},
        "retrieved_ids": ["doc_15", "doc_8", "doc_3", "doc_1", "doc_7"],
    },
]


# ---------------------------------------------------------------------------
# Metric 1: Precision@K
# ---------------------------------------------------------------------------

def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Of the top K retrieved documents, what fraction is relevant?

    Measures: noise in the retrieved context.
    Low precision → LLM gets irrelevant chunks → higher hallucination risk.
    High precision → every chunk in context is useful → efficient token use.

    Range: 0.0 (all retrieved are irrelevant) to 1.0 (all retrieved are relevant).

    Example:
      retrieved = [doc_A, doc_X, doc_B, doc_Y, doc_Z]
      relevant  = {doc_A, doc_B, doc_C}
      precision@5 = 2/5 = 0.40
      precision@2 = 1/2 = 0.50  (only looked at first 2)
    """
    if k <= 0:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return hits / k


# ---------------------------------------------------------------------------
# Metric 2: Recall@K
# ---------------------------------------------------------------------------

def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Of all relevant documents, what fraction was retrieved in the top K?

    Measures: coverage — did we find the answer?
    Low recall → the model will miss key facts even if it follows the context perfectly.
    High recall → the model has everything it needs to give a complete answer.

    Range: 0.0 to 1.0.
    If no relevant documents exist, recall is defined as 1.0 (nothing to miss).

    Example:
      retrieved = [doc_A, doc_X, doc_B, doc_Y, doc_Z]
      relevant  = {doc_A, doc_B, doc_C}
      recall@5 = 2/3 = 0.67  (found doc_A and doc_B, missed doc_C)
    """
    if not relevant_ids:
        return 1.0
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & relevant_ids)
    return hits / len(relevant_ids)


# ---------------------------------------------------------------------------
# Metric 3: Hit Rate@K
# ---------------------------------------------------------------------------

def hit_rate_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Was at least one relevant document in the top K? Returns 1.0 or 0.0.

    This is the minimum viable metric. If your hit_rate@5 is below 0.7,
    the system is simply broken for 30% of queries — the model has nothing
    to work with regardless of how good the prompt or LLM is.

    It is a binary metric, so it is easy to track on a dashboard:
    "% of queries where retrieval found something useful."
    """
    top_k = set(retrieved_ids[:k])
    return 1.0 if (top_k & relevant_ids) else 0.0


# ---------------------------------------------------------------------------
# Metric 4: MRR — Mean Reciprocal Rank
# ---------------------------------------------------------------------------

def reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    Reciprocal rank for a single query.
    Returns 1/rank where rank is the position (1-based) of the first relevant result.
    Returns 0.0 if no relevant document was retrieved.

    Why it matters: LLMs pay more attention to content near the top of the context.
    A relevant document at position 5 is less useful than at position 1.

    1st result relevant:  RR = 1.0
    2nd result relevant:  RR = 0.5
    3rd result relevant:  RR = 0.33
    Not found:            RR = 0.0
    """
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(dataset: list[dict]) -> float:
    """
    MRR: mean reciprocal rank across all queries.

    Interpretation guide:
      MRR > 0.8 → the top result is almost always relevant
      MRR 0.5–0.8 → first relevant result is usually in positions 1-2
      MRR < 0.3 → retrieval is unreliable for Q&A use cases

    Unlike precision/recall, MRR is not parameterized by K.
    It considers the full ranked list.
    """
    if not dataset:
        return 0.0
    rr_scores = [
        reciprocal_rank(q["retrieved_ids"], q["relevant_ids"])
        for q in dataset
    ]
    return sum(rr_scores) / len(rr_scores)


# ---------------------------------------------------------------------------
# Metric 5: nDCG@K — Normalized Discounted Cumulative Gain
# ---------------------------------------------------------------------------

def dcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Discounted Cumulative Gain at K.

    The discount function is 1/log2(rank+1):
      rank 1 → weight 1.0
      rank 2 → weight 0.63
      rank 3 → weight 0.5
      rank 5 → weight 0.39

    For binary relevance (relevant = 1, irrelevant = 0):
      DCG@K = Σ rel_i / log2(i + 1)  for i = 1..K
    """
    dcg = 0.0
    for rank, doc_id in enumerate(retrieved_ids[:k], start=1):
        if doc_id in relevant_ids:
            dcg += 1.0 / math.log2(rank + 1)
    return dcg


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Normalized DCG@K: actual DCG divided by ideal DCG.

    The ideal DCG is computed assuming all relevant documents are ranked
    at the top positions (best possible ranking).
    Dividing by the ideal normalizes the score to [0.0, 1.0].

    nDCG = 1.0 → perfect ranking (all relevant docs first, in any order)
    nDCG = 0.5 → about half the theoretical maximum quality
    nDCG = 0.0 → no relevant documents retrieved

    When to use nDCG over MRR:
      - Multiple relevant documents per query (MRR only cares about the first)
      - You want to reward systems that rank ALL relevant docs high, not just one
      - You are comparing systems with different numbers of relevant docs per query
    """
    actual_dcg = dcg_at_k(retrieved_ids, relevant_ids, k)

    # Ideal DCG: rank relevant docs first
    n_relevant_in_k = min(len(relevant_ids), k)
    # Create a fake "perfect" retrieved list: put n relevant docs first
    ideal_retrieved = list(relevant_ids)[:n_relevant_in_k]
    ideal_dcg = dcg_at_k(ideal_retrieved, relevant_ids, n_relevant_in_k)

    if ideal_dcg == 0.0:
        return 0.0
    return actual_dcg / ideal_dcg


# ---------------------------------------------------------------------------
# Metric 6 & 7: RAG-Specific Metrics
# ---------------------------------------------------------------------------

def context_precision(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    RAG-specific: of all retrieved chunks, what fraction is relevant to the query?

    Differs from precision@K: measured over the full retrieved list,
    not just the top K. Directly measures context window efficiency.

    Low context_precision → LLM context is mostly noise.
    Rule of thumb:
      < 0.3: significant noise, consider adding a reranker or min_score threshold
      0.3–0.6: acceptable for many use cases
      > 0.7: efficient, clean context

    Context precision does not tell you if you have enough relevant chunks —
    that is context recall's job.
    """
    if not retrieved_ids:
        return 0.0
    hits = sum(1 for doc_id in retrieved_ids if doc_id in relevant_ids)
    return hits / len(retrieved_ids)


def context_recall(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    RAG-specific: what fraction of relevant documents was retrieved?

    Measured over the full retrieved set (not top K).
    If context_recall is 0.6 for a query, the model has only 60% of the
    material it needs — it will give partial or incomplete answers.

    Rule of thumb:
      < 0.5: retrieval is failing badly on this query type
      0.5–0.8: partial coverage; model may give incomplete answers
      > 0.8: good coverage; model failures are likely generation-side

    When context_recall is high but answers are still wrong:
    → The problem is generation (prompt, model), not retrieval.
    """
    if not relevant_ids:
        return 1.0
    hits = sum(1 for doc_id in relevant_ids if doc_id in retrieved_ids)
    return hits / len(relevant_ids)


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------

def evaluate_retrieval(dataset: list[dict], k: int = 5) -> dict:
    """
    Compute all retrieval metrics for a golden dataset.

    Args:
        dataset: list of {"query": str, "relevant_ids": set, "retrieved_ids": list}
        k: cutoff for K-parameterized metrics

    Returns:
        {
            "aggregate": {metric_name: float, ...},  # mean across queries
            "per_query": [{metric_name: float, ...}, ...],
            "k": int,
            "n_queries": int,
        }
    """
    per_query = []

    for item in dataset:
        retrieved = item["retrieved_ids"]
        relevant = item["relevant_ids"]

        scores = {
            "query": item["query"],
            f"precision@{k}": precision_at_k(retrieved, relevant, k),
            f"recall@{k}": recall_at_k(retrieved, relevant, k),
            f"hit_rate@{k}": hit_rate_at_k(retrieved, relevant, k),
            "reciprocal_rank": reciprocal_rank(retrieved, relevant),
            f"ndcg@{k}": ndcg_at_k(retrieved, relevant, k),
            "context_precision": context_precision(retrieved, relevant),
            "context_recall": context_recall(retrieved, relevant),
        }
        per_query.append(scores)

    # Aggregate: mean across all queries
    metric_keys = [key for key in per_query[0] if key != "query"]
    aggregates = {
        key: sum(q[key] for q in per_query) / len(per_query)
        for key in metric_keys
    }

    return {
        "aggregate": aggregates,
        "per_query": per_query,
        "k": k,
        "n_queries": len(dataset),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _interpret(agg: dict, k: int) -> None:
    """Print actionable diagnosis based on metric values."""
    issues = []

    hit_rate = agg[f"hit_rate@{k}"]
    recall = agg[f"recall@{k}"]
    precision = agg[f"precision@{k}"]
    mrr = agg["reciprocal_rank"]
    cp = agg["context_precision"]
    cr = agg["context_recall"]
    ndcg = agg[f"ndcg@{k}"]

    if hit_rate < 0.7:
        issues.append(
            f"  [CRITICAL] Hit Rate@{k} = {hit_rate:.2f} — retrieval finds nothing useful "
            f"for {(1-hit_rate)*100:.0f}% of queries.\n"
            f"             Fix: increase K, re-chunk corpus, or switch embedding model."
        )

    if recall < 0.6:
        issues.append(
            f"  [HIGH] Recall@{k} = {recall:.2f} — regularly missing relevant documents.\n"
            f"         Fix: increase K, or add hybrid/sparse search (Lesson 07)."
        )

    if precision < 0.4:
        issues.append(
            f"  [MEDIUM] Precision@{k} = {precision:.2f} — too much noise in context.\n"
            f"           Fix: reduce K, add min_score filter, or add a reranker."
        )

    if mrr < 0.4:
        issues.append(
            f"  [MEDIUM] MRR = {mrr:.2f} — first relevant result is often below position 2.\n"
            f"           Fix: add cross-encoder reranker or query transformation (Lesson 08)."
        )

    if cp < 0.5:
        issues.append(
            f"  [MEDIUM] Context Precision = {cp:.2f} — more than half the context is noise.\n"
            f"           Fix: add similarity score threshold or reranker."
        )

    if cr < 0.8:
        issues.append(
            f"  [HIGH] Context Recall = {cr:.2f} — context cannot fully support answers.\n"
            f"         Fix: increase K, check chunking (key facts split across chunks?),\n"
            f"         or add multi-query retrieval (Lesson 08)."
        )

    if ndcg < 0.5:
        issues.append(
            f"  [MEDIUM] nDCG@{k} = {ndcg:.2f} — relevant docs are ranked too low.\n"
            f"           Fix: add cross-encoder reranker or tune retrieval scoring."
        )

    if not issues:
        print("  All metrics are in healthy ranges.")
        print("  Consider expanding eval set to 50+ queries for higher confidence.")
    else:
        for issue in issues:
            print(issue)


def print_report(results: dict) -> None:
    """Print the full metrics report with per-query breakdown and interpretation."""
    k = results["k"]
    agg = results["aggregate"]

    print("\n" + "=" * 65)
    print(f"  RETRIEVAL METRICS REPORT  (K={k}, N={results['n_queries']} queries)")
    print("=" * 65)

    print(f"\n  Precision@{k:<3}        {agg[f'precision@{k}']:.3f}   "
          f"(of retrieved, fraction relevant)")
    print(f"  Recall@{k:<6}         {agg[f'recall@{k}']:.3f}   "
          f"(of relevant, fraction retrieved)")
    print(f"  Hit Rate@{k:<4}        {agg[f'hit_rate@{k}']:.3f}   "
          f"(queries with ≥1 relevant result)")
    print(f"  MRR                 {agg['reciprocal_rank']:.3f}   "
          f"(how high is first relevant result)")
    print(f"  nDCG@{k:<7}         {agg[f'ndcg@{k}']:.3f}   "
          f"(position-weighted ranking quality)")
    print(f"  Context Precision   {agg['context_precision']:.3f}   "
          f"(retrieved chunks that are useful)")
    print(f"  Context Recall      {agg['context_recall']:.3f}   "
          f"(answer supportable by retrieved context)")

    print(f"\n{'─'*65}")
    print(f"  {'Query':<48} {'P':>4} {'R':>4} {'HR':>4} {'RR':>5} {'nDCG':>5}")
    print(f"{'─'*65}")
    for q in results["per_query"]:
        label = q["query"][:46] + ".." if len(q["query"]) > 46 else q["query"]
        print(
            f"  {label:<48} "
            f"{q[f'precision@{k}']:>4.2f} "
            f"{q[f'recall@{k}']:>4.2f} "
            f"{q[f'hit_rate@{k}']:>4.0f} "
            f"{q['reciprocal_rank']:>5.2f} "
            f"{q[f'ndcg@{k}']:>5.2f}"
        )

    print(f"\n{'─'*65}")
    print("  DIAGNOSIS")
    print(f"{'─'*65}")
    _interpret(agg, k)


def print_k_sweep(dataset: list[dict], k_values: list[int] = None) -> None:
    """
    Show how precision, recall, hit rate, and nDCG change across K values.
    This helps you pick the right K for your production system.
    """
    if k_values is None:
        k_values = [1, 3, 5, 10]

    print("\n" + "=" * 65)
    print("  METRICS vs K  (precision ↓ as K rises, recall ↑ as K rises)")
    print("=" * 65)
    print(f"{'K':>4}  {'P@K':>8}  {'R@K':>8}  {'HR@K':>8}  {'MRR':>8}  {'nDCG@K':>8}")
    print(f"{'─'*4}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*8}")

    for k in k_values:
        r = evaluate_retrieval(dataset, k=k)["aggregate"]
        print(
            f"{k:>4}  "
            f"{r[f'precision@{k}']:>8.3f}  "
            f"{r[f'recall@{k}']:>8.3f}  "
            f"{r[f'hit_rate@{k}']:>8.3f}  "
            f"{r['reciprocal_rank']:>8.3f}  "
            f"{r[f'ndcg@{k}']:>8.3f}"
        )

    print(f"\n  Note: MRR does not change with K — it evaluates the full ranked list.")
    print(f"  Finding: pick K where recall is acceptable (≥0.7) and precision is not too low (≥0.3).")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Retrieval Metrics Demo")
    print(f"Golden dataset: {len(GOLDEN_DATASET)} queries\n")

    # Show one example worked out by hand
    example = GOLDEN_DATASET[0]
    print(f"Example query: '{example['query']}'")
    print(f"  Relevant docs : {example['relevant_ids']}")
    print(f"  Retrieved docs: {example['retrieved_ids']}")
    print(f"  precision@5   = {precision_at_k(example['retrieved_ids'], example['relevant_ids'], 5):.3f}")
    print(f"  recall@5      = {recall_at_k(example['retrieved_ids'], example['relevant_ids'], 5):.3f}")
    print(f"  hit_rate@5    = {hit_rate_at_k(example['retrieved_ids'], example['relevant_ids'], 5):.1f}")
    print(f"  recip_rank    = {reciprocal_rank(example['retrieved_ids'], example['relevant_ids']):.3f}")
    print(f"  ndcg@5        = {ndcg_at_k(example['retrieved_ids'], example['relevant_ids'], 5):.3f}")
    print(f"  ctx_precision = {context_precision(example['retrieved_ids'], example['relevant_ids']):.3f}")
    print(f"  ctx_recall    = {context_recall(example['retrieved_ids'], example['relevant_ids']):.3f}")

    # Full report at K=5
    results = evaluate_retrieval(GOLDEN_DATASET, k=5)
    print_report(results)

    # K sweep
    print_k_sweep(GOLDEN_DATASET, k_values=[1, 3, 5, 10])
