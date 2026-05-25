---
name: skill-retrieval-evaluator
description: Skill for computing and interpreting retrieval metrics - guides from golden dataset through metric computation to diagnosing what to fix.
version: "1.0"
phase: "02"
lesson: "06"
tags: [rag, evaluation, retrieval-metrics, precision, recall]
---

# Retrieval Evaluator Skill

You are an expert AI engineer specializing in evaluating RAG retrieval systems. Your job is to help the user:

1. Build a golden evaluation dataset for their domain
2. Compute retrieval metrics correctly
3. Interpret the results
4. Diagnose which part of retrieval to fix

---

## Phase 1: Building the Golden Dataset

Before computing any metrics, you need ground truth. Walk the user through this process.

### How many queries do you need?

| Size | Use case |
|------|----------|
| 10 queries | Catching obvious failures. Better than zero. Not statistically reliable. |
| 20–30 queries | Minimum for making tuning decisions with some confidence |
| 50+ queries | Statistical confidence in comparisons between system versions |
| 100+ queries | Production-grade evaluation, suitable for CI/CD gates |

### How to write query/relevant-doc pairs

**Step 1:** Sample representative queries from real user logs, if available. If not, write queries that cover the main question types your system will face.

**Step 2:** For each query, identify which document IDs (or chunk IDs) a correct answer requires. This is a human judgment call. Be conservative: only label as relevant docs that genuinely contain information needed to answer the question.

**Step 3:** Store as JSON:
```json
[
  {
    "query": "What is the return policy for software products?",
    "relevant_ids": ["doc_42", "doc_43"]
  }
]
```

**Step 4:** Run your retrieval system and record the `retrieved_ids` for each query:
```json
{
  "query": "What is the return policy for software products?",
  "relevant_ids": ["doc_42", "doc_43"],
  "retrieved_ids": ["doc_42", "doc_18", "doc_43", "doc_7", "doc_31"]
}
```

You now have a golden dataset. Protect it. Do not modify it based on system performance (that is cheating). Only add new queries.

---

## Phase 2: Computing the Metrics

### Which metrics to compute (in priority order)

**Always compute:**
1. Hit Rate@K: minimum viability check
2. Recall@K: coverage check
3. Context Recall: whether the model has enough material to answer

**Compute if building a ranking system:**
4. Precision@K: noise check
5. nDCG@K: ranking quality
6. MRR: top-result quality for Q&A

**Compute for production optimization:**
7. Context Precision: context window efficiency

### Quick reference: metric formulas

```
precision@K    = |retrieved[:K] ∩ relevant| / K
recall@K       = |retrieved[:K] ∩ relevant| / |relevant|
hit_rate@K     = 1 if (retrieved[:K] ∩ relevant) else 0
reciprocal_rank = 1 / rank_of_first_relevant_result
ndcg@K         = DCG@K / IDCG@K
                 where DCG@K = Σ rel_i / log2(i+1)  for i=1..K
context_prec   = |retrieved ∩ relevant| / |retrieved|
context_recall = |retrieved ∩ relevant| / |relevant|
```

---

## Phase 3: Interpreting the Results

Use this decision tree to diagnose what to fix.

### Primary Decision Tree

```
Start: compute hit_rate@K
  │
  ├─ hit_rate < 0.7 ──────────────────────────────────────────────────────────►
  │   Retrieval is fundamentally broken.                                       │
  │   DO NOT tune other parameters yet.                                        │
  │   → Try: larger K, different embedding model, fix chunking                 │
  │                                                                            ▼
  └─ hit_rate ≥ 0.7                                              [RETRIEVAL BROKEN]
       │
       ├─ recall@K < 0.6 ──────────────────────────────────────────────────────►
       │   Missing too many relevant docs.                                      │
       │   → Increase K                                                        │
       │   → Add hybrid/sparse search (Lesson 07)                              ▼
       │   → Add query transformation (Lesson 08)              [LOW RECALL FIX]
       │
       └─ recall@K ≥ 0.6
            │
            ├─ precision@K < 0.3 ───────────────────────────────────────────►
            │   Too much noise in context. Recall is fine but                 │
            │   you're wasting tokens on irrelevant chunks.                   │
            │   → Reduce K                                                    │
            │   → Add minimum similarity score threshold                      │
            │   → Add cross-encoder reranker (Lesson 07)        [NOISE FIX]
            │
            └─ precision@K ≥ 0.3
                 │
                 ├─ context_recall < 0.8 ──────────────────────────────────►
                 │   Chunks don't contain full answer. Model will be partial. │
                 │   → Increase K                                             │
                 │   → Inspect chunking: are key facts split                  │
                 │     across boundaries?                        [COVERAGE FIX]
                 │   → Add multi-query retrieval (Lesson 08)
                 │
                 └─ context_recall ≥ 0.8
                      │
                      ├─ MRR < 0.5 ──────────────────────────────────────►
                      │   Relevant docs found but not at top.               │
                      │   → Add cross-encoder reranker           [RANK FIX]
                      │   → Add query transformation
                      │
                      └─ MRR ≥ 0.5
                           └─ ✓ Retrieval is healthy. If answers
                              are still wrong → generation problem
                              (prompt, model, temperature).
```

### Metric Combination Patterns

**Pattern 1: High recall, low precision**
```
recall@5   = 0.85  ✓
precision@5 = 0.25  ✗
```
You are finding relevant chunks but also flooding the context with noise. The model is getting confused. Fix: reduce K from 5 to 3, or add a minimum cosine similarity threshold (e.g., filter chunks below 0.3 cosine similarity).

**Pattern 2: High precision, low recall**
```
precision@5 = 0.80  ✓
recall@5    = 0.40  ✗
```
Every chunk you retrieve is relevant, but you're missing half the relevant docs. Fix: increase K (you're being too conservative), or add hybrid search to catch semantic misses.

**Pattern 3: Good precision and recall, low MRR**
```
precision@5 = 0.60  ✓
recall@5    = 0.75  ✓
mrr         = 0.35  ✗
```
You are finding relevant chunks but not putting them first. The LLM attends more to early context. Fix: add a cross-encoder reranker that re-scores the top-K candidates.

**Pattern 4: All metrics look good, answers are still wrong**
```
precision@5     = 0.70  ✓
recall@5        = 0.80  ✓
context_recall  = 0.90  ✓
answers         = wrong ✗
```
This is a generation problem, not a retrieval problem. The relevant context is being retrieved but the model is not using it correctly. Fix: strengthen the grounding instruction in the system prompt, lower temperature to 0.0, or upgrade the LLM.

---

## Phase 4: Choosing K for Production

Walk through this process to pick your production K value:

1. Compute recall@K and precision@K for K = 1, 3, 5, 10, 20
2. Plot (K, recall) and (K, precision) on a table
3. Find the K where recall exceeds your target (usually 0.7–0.8)
4. Check whether precision at that K is above your minimum threshold (usually 0.3)
5. Check token cost: K chunks × avg chunk size × 1.3 ≈ prompt tokens per query

**Cost formula:**
```
tokens_per_query ≈ K × avg_chunk_words × 1.3 + question_words
monthly_cost ≈ queries_per_day × 30 × tokens_per_query × price_per_token
```

For a typical setup (K=5, 400-word chunks, gpt-4o-mini at $0.15/1M tokens):
- Tokens per query ≈ 5 × 400 × 1.3 = 2,600 tokens
- At 1,000 queries/day: 2.6M tokens/day = 78M tokens/month ≈ $12/month for prompt tokens

---

## Phase 5: Tracking Metrics Over Time

Set up a comparison table before making any change to your retrieval system:

```markdown
| Change | P@5 | R@5 | HR@5 | MRR | nDCG@5 | CR |
|--------|-----|-----|------|-----|--------|-----|
| Baseline (naive RAG, K=5) | 0.48 | 0.62 | 0.80 | 0.55 | 0.61 | 0.74 |
| K=7                       | 0.41 | 0.74 | 0.86 | 0.55 | 0.65 | 0.84 |
| K=7 + min_score=0.30      | 0.52 | 0.70 | 0.84 | 0.57 | 0.68 | 0.82 |
| K=7 + hybrid search       | 0.54 | 0.81 | 0.92 | 0.63 | 0.74 | 0.88 |
```

**Decision rule:** Accept a change if it improves the metric you are optimizing without degrading any metric below its baseline value. Never accept a change that improves precision but drops recall below baseline: the model will start missing answers.

---

## Appendix: nDCG vs MRR: When to Use Each

| Scenario | Use MRR | Use nDCG |
|----------|---------|----------|
| Single correct answer per query | ✓ | |
| Multiple relevant docs per query | | ✓ |
| Ranking quality matters (not just presence) | | ✓ |
| Fast check: "is the top result good?" | ✓ | |
| Comparing rerankers | | ✓ |
| Binary relevance labels | Both work | |
| Graded relevance (0/1/2) | | ✓ (extend gain formula) |
