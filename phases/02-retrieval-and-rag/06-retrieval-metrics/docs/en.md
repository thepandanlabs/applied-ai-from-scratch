# Retrieval Metrics

> "The results look relevant" is not an evaluation. Metrics are.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lesson 05 (naive RAG)
**Time:** ~45 minutes
**Phase:** 02 · Retrieval & RAG

---

## Learning Objectives

- Implement precision@K, recall@K, MRR, nDCG@K, and hit rate from scratch in pure Python
- Explain what each metric measures and when each one matters for a production RAG system
- Implement the two RAG-specific metrics: context precision and context recall
- Build a minimal golden dataset (5 queries) and run all metrics against it
- Interpret metric output to diagnose which part of retrieval to improve

---

## The Problem

Your RAG system retrieves five chunks. They look related to the query. The answer seems right. You ship it. Three weeks later a customer reports that it keeps citing the wrong sections and occasionally misses the key fact entirely. You have no numbers. You have no way to tell whether the change you made last Tuesday helped or hurt. You have no baseline to compare against.

"Looks relevant" is a feeling. It is not a metric. Feelings do not survive a codebase change, a team handoff, a new document corpus, or a model upgrade. Every production system eventually needs a number it can track over time.

The reason most teams skip this step is that building a proper eval dataset feels expensive. It is not. Twenty query/relevant-doc pairs written by a human who knows the corpus takes two hours. That two hours buys you a repeatable measurement you can run in under a second. Without it, every tuning decision: chunk size, K value, embedding model, hybrid search, reranking: is a guess. With it, tuning decisions become experiments with outcomes.

---

## The Concept

### What These Metrics Actually Measure

Retrieval evaluation assumes you have a golden dataset: for each query, a human has labeled which document IDs are relevant. You then run your retrieval system and compare what it returned against the ground truth.

```
Golden dataset:
  query_1 → relevant_docs = {doc_A, doc_B, doc_C}

Your retrieval at K=5:
  query_1 → retrieved_docs = [doc_A, doc_X, doc_B, doc_Y, doc_Z]
                               ✓       ✗       ✓      ✗      ✗
```

| Metric | Question it answers | Best for |
|--------|-------------------|---------|
| **Precision@K** | Of the K chunks I retrieved, how many were relevant? | Minimizing noise in the context |
| **Recall@K** | Of all relevant chunks, how many did I retrieve in top K? | Maximizing coverage (don't miss the answer) |
| **Hit Rate** | Was at least one relevant chunk in the top K? | Minimum viability: is the system usable at all? |
| **MRR** | How high up is the first relevant result? | Q&A systems where the top result drives the answer |
| **nDCG@K** | How good is the full ranking, weighted toward top positions? | Re-ranking quality, multi-answer queries |
| **Context Precision** | Of the retrieved chunks, what fraction is actually useful? | Controlling context window bloat |
| **Context Recall** | Can the retrieved context ground the full expected answer? | Detecting partial/incomplete answers |

### Precision vs Recall Tradeoff

Raising K always increases recall (more chunks = more chances to hit relevant ones) but usually decreases precision (more irrelevant chunks dilute the context). Finding your operating point is the core retrieval tuning problem.

```
K=1:  High precision (1 chunk, probably relevant), Low recall (might miss most relevant docs)
K=20: Low precision (lots of noise), High recall (probably found them all)
K=5:  Typical operating point: balance noise vs coverage
```

### nDCG: Why Position Matters

Both of these retrieval results have precision@3 = 0.67 (2 out of 3 relevant), but they are not equally good:

```
Result A: [relevant, relevant, irrelevant]   nDCG is higher
Result B: [irrelevant, relevant, relevant]   nDCG is lower
```

nDCG penalizes putting relevant documents lower in the ranked list. For a RAG system, this matters because LLMs pay more attention to content near the top of the context window. Relevant content at position 1 contributes more than relevant content at position 5.

### Context Precision and Recall (RAG-Specific)

Standard IR metrics measure whether the retrieved docs match a relevance label. RAG needs two additional metrics that connect retrieval to answer quality:

**Context Precision**: Given the retrieved chunks, what fraction is actually needed to answer the question? High context precision means your context window is efficient: no filler. Low context precision means you are paying for tokens that confuse the model.

**Context Recall**: Can the retrieved chunks fully support the expected answer? Low context recall means the model will have to hallucinate or give a partial answer, not because it's a bad model, but because you didn't give it enough material.

```
Expected answer: "The product was launched in March 2024 in the US market"
                  ─────────────────────────┬────────────────────────────
                                           │
Retrieved chunk A: "The product launched in March 2024"     → covers part 1
Retrieved chunk B: "The US rollout began first"             → covers part 2
Retrieved chunk C: "Revenue doubled year-over-year"         → irrelevant

Context Precision = 2/3 (2 of 3 retrieved chunks are useful)
Context Recall    = 1.0 (both required facts are present)
```

---

## Build It

### Step 1: The Golden Dataset

```python
# No dependencies needed: pure Python.
# Usage: python main.py

# A minimal golden dataset.
# In production, this is written by a domain expert who reads the corpus
# and writes query/relevant_doc_id pairs. Start with 20 pairs minimum.
#
# Format: each query has a set of relevant doc IDs (ground truth)
# and a ranked list of retrieved doc IDs (system output to evaluate).

GOLDEN_DATASET = [
    {
        "query": "What is the recommended dosage for adults?",
        "relevant_ids": {"doc_3", "doc_7"},         # ground truth
        "retrieved_ids": ["doc_3", "doc_1", "doc_7", "doc_9", "doc_2"],  # system output
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
```

### Step 2: Precision@K and Recall@K

```python
def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Of the top K retrieved documents, what fraction is relevant?
    Measures noise: a low value means you're filling the context window
    with irrelevant chunks.

    Range: 0.0 to 1.0
    """
    if k == 0:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return hits / k


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Of all relevant documents, what fraction was retrieved in the top K?
    Measures coverage: a low value means the model won't have the answer
    because retrieval missed it.

    Range: 0.0 to 1.0
    If there are no relevant documents, recall is defined as 1.0 (vacuously true).
    """
    if not relevant_ids:
        return 1.0
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & relevant_ids)
    return hits / len(relevant_ids)
```

### Step 3: Hit Rate

```python
def hit_rate_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Was at least one relevant document in the top K? Returns 1.0 or 0.0.

    This is the minimum useful metric for a RAG system.
    If hit_rate@5 is below 0.7, your system is broken for 30% of queries -
    the model literally cannot answer because retrieval returned nothing relevant.
    """
    top_k = set(retrieved_ids[:k])
    return 1.0 if top_k & relevant_ids else 0.0
```

### Step 4: MRR: Mean Reciprocal Rank

```python
def reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    Reciprocal rank for a single query: 1/rank of the first relevant result.
    rank is 1-based.

    If the first result is relevant: RR = 1/1 = 1.0
    If the second result is first relevant: RR = 1/2 = 0.5
    If no relevant result in list: RR = 0.0

    Heavily penalizes putting the key document anywhere but position 1.
    Use MRR when you want the model to have the best single answer at the top.
    """
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(dataset: list[dict]) -> float:
    """
    MRR: average reciprocal rank across all queries.
    Interpretation:
      MRR = 1.0 → every query's first result is relevant
      MRR = 0.5 → on average, the first relevant result is at position 2
      MRR < 0.3 → retrieval is unreliable for production Q&A
    """
    if not dataset:
        return 0.0
    rr_scores = [
        reciprocal_rank(q["retrieved_ids"], q["relevant_ids"])
        for q in dataset
    ]
    return sum(rr_scores) / len(rr_scores)
```

### Step 5: nDCG@K: Normalized Discounted Cumulative Gain

```python
import math


def dcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Discounted Cumulative Gain at K.

    DCG rewards:
      - Finding relevant documents (adds to the gain)
      - Finding them early (divides by log2(rank + 1), so earlier = higher weight)

    For binary relevance (relevant=1, irrelevant=0):
      DCG@K = sum_{i=1}^{K} rel_i / log2(i + 1)
    """
    dcg = 0.0
    for rank, doc_id in enumerate(retrieved_ids[:k], start=1):
        if doc_id in relevant_ids:
            dcg += 1.0 / math.log2(rank + 1)
    return dcg


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Normalized DCG@K: DCG divided by the ideal DCG.

    Ideal DCG assumes all relevant documents are ranked first.
    Normalizing to [0, 1] makes scores comparable across queries
    with different numbers of relevant documents.

    nDCG@K = 1.0 → perfect ranking (all relevant docs at the top)
    nDCG@K = 0.0 → no relevant documents retrieved
    """
    actual_dcg = dcg_at_k(retrieved_ids, relevant_ids, k)
    # Ideal: rank all relevant docs first, up to K
    n_relevant = min(len(relevant_ids), k)
    ideal_retrieved = list(relevant_ids)[:n_relevant]
    ideal_dcg = dcg_at_k(ideal_retrieved, relevant_ids, n_relevant)
    if ideal_dcg == 0.0:
        return 0.0
    return actual_dcg / ideal_dcg
```

### Step 6: Context Precision and Context Recall (RAG-Specific)

```python
def context_precision(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    RAG-specific: of all retrieved chunks, what fraction is relevant?

    This is precision over the full retrieved list (not just top K).
    Low context precision means your prompt is bloated with noise.
    The LLM has to "find" the answer in a haystack of irrelevant chunks.

    Rule of thumb: context_precision below 0.5 → reduce K or add a
    minimum similarity score threshold to filter low-quality retrievals.
    """
    if not retrieved_ids:
        return 0.0
    hits = sum(1 for doc_id in retrieved_ids if doc_id in relevant_ids)
    return hits / len(retrieved_ids)


def context_recall(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    RAG-specific: what fraction of relevant documents was retrieved?

    This is recall over the full retrieved list.
    Low context recall means the model cannot fully answer the question -
    not because it's hallucinating, but because you didn't give it enough.

    Rule of thumb: context_recall below 0.8 → increase K, re-chunk,
    or add hybrid search to catch what dense retrieval misses.
    """
    if not relevant_ids:
        return 1.0
    hits = sum(1 for doc_id in relevant_ids if doc_id in retrieved_ids)
    return hits / len(relevant_ids)
```

### Step 7: Running All Metrics Together

```python
def evaluate_retrieval(dataset: list[dict], k: int = 5) -> dict:
    """
    Compute all retrieval metrics for a dataset of (query, relevant_ids, retrieved_ids) triples.
    Returns aggregate scores (averages across all queries) and per-query breakdowns.
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

    # Aggregate metrics (mean across queries)
    metric_keys = [key for key in per_query[0] if key != "query"]
    aggregates = {}
    for key in metric_keys:
        aggregates[key] = sum(q[key] for q in per_query) / len(per_query)

    return {
        "aggregate": aggregates,
        "per_query": per_query,
        "k": k,
        "n_queries": len(dataset),
    }


def print_report(results: dict) -> None:
    """
    Print a readable metrics report with interpretation guidance.
    """
    k = results["k"]
    agg = results["aggregate"]

    print("\n" + "=" * 60)
    print(f"RETRIEVAL METRICS REPORT  (K={k}, N={results['n_queries']} queries)")
    print("=" * 60)

    print(f"\n  Precision@{k}      : {agg[f'precision@{k}']:.3f}   (of retrieved, fraction relevant)")
    print(f"  Recall@{k}         : {agg[f'recall@{k}']:.3f}   (of relevant, fraction retrieved)")
    print(f"  Hit Rate@{k}       : {agg[f'hit_rate@{k}']:.3f}   (queries with ≥1 relevant result)")
    print(f"  MRR              : {agg['reciprocal_rank']:.3f}   (how high up is first relevant result)")
    print(f"  nDCG@{k}          : {agg[f'ndcg@{k}']:.3f}   (ranking quality, position-weighted)")
    print(f"  Context Precision: {agg['context_precision']:.3f}   (retrieved chunks that are useful)")
    print(f"  Context Recall   : {agg['context_recall']:.3f}   (answer supportable by retrieved chunks)")

    print("\n--- Per-Query Breakdown ---")
    for q in results["per_query"]:
        print(f"\n  Query: {q['query'][:60]}...")
        print(f"    P@{k}={q[f'precision@{k}']:.2f}  R@{k}={q[f'recall@{k}']:.2f}  "
              f"HR={q[f'hit_rate@{k}']:.0f}  RR={q['reciprocal_rank']:.2f}  "
              f"nDCG={q[f'ndcg@{k}']:.2f}  CP={q['context_precision']:.2f}  CR={q['context_recall']:.2f}")

    print("\n--- Interpretation Guide ---")
    _interpret(agg, k)


def _interpret(agg: dict, k: int) -> None:
    """Print actionable interpretation based on metric values."""
    issues = []

    hit_rate = agg[f"hit_rate@{k}"]
    recall = agg[f"recall@{k}"]
    precision = agg[f"precision@{k}"]
    mrr = agg["reciprocal_rank"]
    cp = agg["context_precision"]
    cr = agg["context_recall"]
    ndcg = agg[f"ndcg@{k}"]

    if hit_rate < 0.7:
        issues.append(f"  [CRITICAL] Hit Rate@{k}={hit_rate:.2f}: retrieval is missing relevant docs "
                      f"for {(1-hit_rate)*100:.0f}% of queries. Fix: increase K, re-chunk, "
                      f"or switch embedding model.")

    if recall < 0.6:
        issues.append(f"  [HIGH] Recall@{k}={recall:.2f}: missing relevant docs too often. "
                      f"Fix: increase K, or add hybrid search (Lesson 07).")

    if precision < 0.4:
        issues.append(f"  [MEDIUM] Precision@{k}={precision:.2f}: too much noise in context. "
                      f"Fix: reduce K, add min_score threshold, or add reranker (Lesson 07).")

    if mrr < 0.4:
        issues.append(f"  [MEDIUM] MRR={mrr:.2f}: first relevant result is not near position 1. "
                      f"Fix: reranking or query transformation (Lesson 08).")

    if cp < 0.5:
        issues.append(f"  [MEDIUM] Context Precision={cp:.2f}: LLM context is more than half noise. "
                      f"Fix: add similarity threshold, reduce K, or add cross-encoder reranker.")

    if cr < 0.8:
        issues.append(f"  [HIGH] Context Recall={cr:.2f}: retrieved context cannot support full answers. "
                      f"Fix: increase K, fix chunking (splits key facts), or add multi-query (Lesson 08).")

    if ndcg < 0.5:
        issues.append(f"  [MEDIUM] nDCG@{k}={ndcg:.2f}: ranking quality is weak. "
                      f"Fix: add cross-encoder reranker or tune retrieval scoring.")

    if not issues:
        print("  All metrics look healthy. Consider tightening thresholds or expanding your eval set.")
    else:
        for issue in issues:
            print(issue)
```

### Step 8: Main Entry Point

```python
if __name__ == "__main__":
    print("Running retrieval metrics on sample golden dataset...")
    print(f"Dataset size: {len(GOLDEN_DATASET)} queries")

    results = evaluate_retrieval(GOLDEN_DATASET, k=5)
    print_report(results)

    # Show how metrics change with different K values
    print("\n\n--- Metrics at Different K Values ---")
    print(f"{'K':>4}  {'P@K':>8}  {'R@K':>8}  {'HR@K':>8}  {'MRR':>8}  {'nDCG@K':>8}")
    for k in [1, 3, 5, 10]:
        r = evaluate_retrieval(GOLDEN_DATASET, k=k)["aggregate"]
        print(f"{k:>4}  "
              f"{r[f'precision@{k}']:>8.3f}  "
              f"{r[f'recall@{k}']:>8.3f}  "
              f"{r[f'hit_rate@{k}']:>8.3f}  "
              f"{r['reciprocal_rank']:>8.3f}  "
              f"{r[f'ndcg@{k}']:>8.3f}")

    print("\nNote: Precision typically decreases as K increases.")
    print("      Recall typically increases as K increases.")
    print("      MRR is K-independent (based on full ranked list).")
```

> **Real-world check:** Your product manager reviews the output and says: "the results look relevant to me when I browse them, why do we need all these numbers? What does a metric tell us that a human spot-check doesn't?" How do you explain what metrics catch that eyeballing a few results misses, especially as the system or corpus changes over time?

---

## Use It

In production, you would not write these functions by hand. The standard library is `ranx`:

```python
from ranx import Qrels, Run, evaluate

# qrels: ground truth relevance judgments
qrels = Qrels({"q1": {"doc_3": 1, "doc_7": 1}, "q2": {"doc_12": 1}})

# run: your system's ranked retrieval results
run = Run({"q1": {"doc_3": 0.95, "doc_1": 0.82, "doc_7": 0.78}, "q2": {"doc_5": 0.91, "doc_12": 0.85}})

results = evaluate(qrels, run, ["precision@5", "recall@5", "mrr", "ndcg@5"])
```

RAGAS (Lesson 10) adds the RAG-specific metrics with LLM-as-judge scoring for context precision and context recall: useful when you cannot hand-label relevance for every chunk.

The pytrec_eval library wraps the C TREC evaluation toolkit and is the standard in information retrieval research. Use it if you need exact reproducibility with published benchmarks.

> **Perspective shift:** Your founder says: "users seem happy with the answers we're shipping. Building a golden dataset and running eval infrastructure takes real time. How do we decide whether that investment is worth it right now, versus just shipping features?" What is the argument for doing this before you have a visible problem, and what does it cost you if you skip it and add it later?

---

## Ship It

The output for this lesson is the skill in `outputs/skill-retrieval-evaluator.md`. It guides the process of computing and interpreting metrics for any RAG system: what to measure, how to read the output, and what to fix.

The runnable artifact is `code/main.py`. Run it with no dependencies:

```bash
python main.py
```

It will print the full metrics report on the sample dataset and show how metrics change across K values.

---

## Evaluate It

**Check 1: Start with hit rate.**
If hit rate at your chosen K is below 0.7, nothing else matters: your system is failing to retrieve anything relevant for 30% of queries. Debug retrieval (embedding model quality, K size, chunk boundaries) before measuring anything else.

**Check 2: Build your golden dataset on your actual corpus, not a toy.**
The metrics from the sample dataset in `main.py` are illustrative. The metrics that matter are on your domain. A financial document corpus will have different operating characteristics than a customer support knowledge base. Write 20 query/relevant-doc pairs for your specific data. Even 20 is enough to detect major regressions.

**Check 3: Run the metrics before and after every retrieval change.**
Changing K, switching the embedding model, adjusting chunk size, adding hybrid search: each change must be validated by the metrics, not by "I tried a few queries and they looked better." Record the numbers. Build a simple comparison table: change → delta precision@5 → delta recall@5 → delta context_recall. Changes that improve recall@5 by 10% at a 5% cost in precision@5 are usually worth it. Changes that improve precision while dropping recall are usually not.

---

## Exercises

1. **[Easy]** Add `average_precision` (area under the precision-recall curve for a single query) to the per-query metrics. Plot precision vs recall for one query as you vary K from 1 to 10.

2. **[Medium]** The golden dataset in `main.py` has relevance as binary (0 or 1). Extend nDCG to support graded relevance (0=irrelevant, 1=somewhat relevant, 2=highly relevant). How does the nDCG formula change? Use `2^rel - 1` as the gain instead of binary 0/1.

3. **[Hard]** Build a script that reads your naive RAG output from Lesson 05 (the `retrieved_chunks` field in the result dict) and evaluates it against a golden dataset. You will need to: (a) assign stable IDs to chunks during ingest, (b) write 10 query/relevant-chunk-id pairs by hand, (c) run the pipeline and collect retrieved IDs, (d) compute all six metrics. This is the real eval loop.

---

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Golden dataset | "Eval set," "ground truth labels," "test set" | A human-curated set of (query, relevant_doc_ids) pairs used to measure retrieval quality objectively |
| Precision@K | "P@5" | Fraction of the top K retrieved documents that are actually relevant |
| Recall@K | "R@5" | Fraction of all relevant documents that appear in the top K retrieved |
| Hit Rate | "HR@K," "success rate" | Whether at least one relevant document was retrieved in the top K; the minimum viable metric |
| MRR | "Mean Reciprocal Rank" | Average of 1/rank-of-first-relevant-result across queries; penalizes relevant docs buried in the list |
| nDCG | "Normalized Discounted Cumulative Gain" | Position-weighted ranking quality; a score of 1.0 means every relevant doc was found and ranked first |
| Context Precision | "Precision in RAG," "chunk precision" | Fraction of retrieved chunks that actually contribute to answering the query |
| Context Recall | "Groundedness coverage" | Whether the retrieved context contains all the information needed to answer the question |

---

## Further Reading

- [BEIR Benchmark](https://arxiv.org/abs/2104.08663): standard benchmark for comparing retrieval systems across 18 heterogeneous datasets; the reference point for embedding model evaluation
- [ranx Documentation](https://amenra.github.io/ranx/): the fastest Python library for IR evaluation metrics; direct replacement for the code in this lesson
- [RAGAS Paper](https://arxiv.org/abs/2309.15217): the canonical paper for LLM-as-judge context precision/recall metrics; read this before building automated RAG evaluation
- [Evaluating RAG Pipelines](https://www.pinecone.io/learn/series/rag/rag-evaluation/): Pinecone's practitioner walkthrough connecting IR metrics to RAG system quality
- [MS MARCO Dataset](https://microsoft.github.io/msmarco/): the standard passage retrieval benchmark; the training data source for most commercial embedding models
