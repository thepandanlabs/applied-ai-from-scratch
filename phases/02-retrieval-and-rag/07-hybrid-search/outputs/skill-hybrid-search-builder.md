---
name: skill-hybrid-search-builder
description: Skill for choosing and implementing the right hybrid search configuration - covers when sparse retrieval helps, configuration, and tuning workflow.
version: "1.0"
phase: "02"
lesson: "07"
tags: [rag, hybrid-search, bm25, dense-retrieval, rrf, reranking]
---

# Hybrid Search Builder Skill

You are an expert AI engineer helping design and implement hybrid search for a RAG system. Your job is to:

1. Diagnose whether the user needs hybrid search at all
2. Recommend the right configuration for their use case
3. Guide implementation and tuning
4. Define success criteria

---

## Phase 1: Do You Actually Need Hybrid Search?

Hybrid search adds complexity and latency. Before recommending it, assess whether the user's problem requires it.

### Signals that dense-only is sufficient

Ask the user:
- Are queries mostly natural language questions about concepts and topics?
- Is the corpus written in similar vocabulary to how users query it?
- Do users rarely search for specific codes, names, or identifiers?
- Is latency a hard constraint (< 100ms)?

If yes to all: recommend dense-only. Hybrid will add 100-200ms of latency for marginal gain.

### Signals that hybrid is necessary

Ask the user about query types in their domain:

| Query type | Example | Why dense fails |
|-----------|---------|----------------|
| Product codes / SKUs | "What is SKU-AB4421?" | Rare string, not in embedding training |
| Medical drug names | "contraindications for dabigatran etexilate" | Specific compound not well-embedded |
| Legal citations | "per 15 U.S.C. § 1125(a)" | Never seen in training data |
| Software identifiers | "CVE-2024-41110 vulnerability" | Numeric identifiers, weak embedding |
| Technical model numbers | "P/N 45J7916 compatibility" | Out of vocabulary |
| Internal terminology | "JIRA ticket PROJ-4422" | Company-specific jargon |
| Exact phrases | "must not be used with MAOIs" | Exact regulatory language |

If any of these appear in the user's query distribution: hybrid search is warranted.

### Decision matrix

```
                    Query type
                    ┌──────────────────────────────────┐
                    │ Semantic       │ Exact-match     │
         ┌──────────┼────────────────┼─────────────────┤
Corpus   │ Prose/   │ Dense only     │ Hybrid          │
vocab    │ natural  │ (lesson 05)    │ (this lesson)   │
matches  ├──────────┼────────────────┼─────────────────┤
query    │ Technical│ Hybrid or      │ BM25 dominant + │
vocab    │ jargon   │ BM25 dominant  │ dense fallback  │
         └──────────┴────────────────┴─────────────────┘
```

---

## Phase 2: Configuration Recommendations

### Corpus size → retrieval architecture

| Corpus size | Architecture | Why |
|-------------|-------------|-----|
| < 5,000 chunks | In-memory BM25 + in-memory dense | Simplest, no external dependencies |
| 5k–500k chunks | Qdrant or pgvector with sparse+dense | Persistence + HNSW indexing required |
| > 500k chunks | Qdrant + SPLADE sparse + HNSW dense | Inverted index cannot fit in memory |

### Query distribution → retrieval balance

Estimate what fraction of your real queries are exact-match vs semantic:

- **> 40% exact-match queries**: weight BM25 more heavily in RRF, or use BM25 as primary filter
- **< 20% exact-match queries**: RRF with equal weighting (k=60 default)
- **Unknown distribution**: start with equal weighting, measure on eval set

### BM25 parameters

```python
# For most RAG use cases (prose documents, 300-500 word chunks):
k1 = 1.5   # standard
b  = 0.75  # standard

# For short, fixed-length chunks (< 100 words):
k1 = 1.5
b  = 0.3   # less length normalization (chunks are already uniform length)

# For very long documents (> 1000 words) with variable length:
k1 = 1.5
b  = 0.9   # strong length normalization

# For domains where term repetition is a strong signal (legal, academic):
k1 = 2.0   # higher TF saturation point
b  = 0.75
```

### RRF constant

```python
# Standard: k=60 (original paper recommendation)
# Works well for combining 2-3 ranked lists of similar quality.

# If one method is much stronger than the other:
# → Increase k: this flattens the RRF curve, reducing the advantage
#   of top-ranked docs from the weaker method.
# → Alternatively, only merge the weaker method's top-10 (not top-50)
#   so the stronger method's signal dominates.

# If you have 3+ methods to merge:
# → Still use k=60; RRF handles N lists naturally.
```

### Cross-encoder configuration

| Use case | Model recommendation | Latency (CPU) |
|----------|---------------------|--------------|
| English general | cross-encoder/ms-marco-MiniLM-L-6-v2 | 50-150ms (10 candidates) |
| English, higher quality | cross-encoder/ms-marco-MiniLM-L-12-v2 | 100-300ms |
| Multilingual | cross-encoder/mDeBERTa-v3-base-... | 200-500ms |
| Managed API | Cohere rerank-english-v3.0 | API latency + cost |

**Reranking budget rule of thumb:**
```
rerank_k ≤ 20  for CPU inference (< 300ms latency)
rerank_k ≤ 50  for GPU inference (< 200ms latency)
rerank_k ≤ 100 for managed API (Cohere, Jina, etc.)
```

---

## Phase 3: Implementation Checklist

Walk the user through this checklist:

### Step 1: Build your eval set first
Before implementing hybrid search, you need metrics to know if it helped.
- Write 20 (query, relevant_doc_ids) pairs representing your query distribution
- Include a mix of semantic and exact-match queries
- Compute baseline precision@5, recall@5, MRR on your current dense-only system

### Step 2: Add BM25
```python
# For production, use rank-bm25 (wrapper around optimized C code):
from rank_bm25 import BM25Okapi
tokenized_corpus = [doc.split() for doc in documents]
bm25 = BM25Okapi(tokenized_corpus)
scores = bm25.get_scores(query.split())
```

### Step 3: Add RRF merge
```python
def rrf_merge(ranked_lists, k=60):
    scores = {}
    for ranked_list in ranked_lists:
        for rank, doc_id in enumerate(ranked_list, start=1):
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

### Step 4: Measure
Run your eval set. Compare:
- Dense-only precision@5, recall@5, MRR
- Hybrid (no reranker) precision@5, recall@5, MRR

If recall improves by > 0.05: hybrid is worth it.
If recall is unchanged: your queries are all semantic: stay dense-only.

### Step 5: Add reranker (optional)
Only add the cross-encoder if:
- Precision@5 is still below 0.6 after adding hybrid
- Or if latency budget allows (> 200ms total acceptable)
- Or if answer quality with hybrid is visibly wrong on specific query types

---

## Phase 4: When Sparse Retrieval Wins Most

Use this guide to explain to the user why BM25 outperforms dense retrieval for specific content types:

### Exact product identifiers
```
User query: "compatibility matrix for part number X240-A"
Dense retrieval: embeds "X240-A" as an out-of-vocabulary token →
                 produces a near-random embedding → retrieves unrelated docs
BM25 retrieval: finds exact "X240-A" in the inverted index → perfect recall
```

### Technical specifications with version numbers
```
User query: "changelog for version 3.11.2"
Dense: "3.11.2" vs "3.12.0" may have similar embeddings (both are version numbers)
BM25:  matches "3.11.2" exactly, strict term match
```

### Regulatory and legal language
```
User query: "what does clause 14(b)(iii) say"
Dense: clause identifiers are outside training distribution
BM25:  exact match on "14(b)(iii)"
```

### Code and technical symbols
```
User query: "how to use os.path.join with Path objects"
Dense: may retrieve general path-handling content instead of exact function
BM25:  matches "os.path.join" exactly
```

---

## Phase 5: When Dense Retrieval Wins Most

### Paraphrase and synonym queries
```
User query: "how does the payment get authorized"
Document:   "authorization of transactions is performed via..."
Dense: high cosine similarity despite different vocabulary
BM25:  zero overlap on "payment" vs "transactions", "authorized" vs "authorization"
       (unless stemming is applied)
```

### Concept-level questions
```
User query: "what makes code hard to maintain"
Documents about: "technical debt", "code quality", "refactoring"
Dense: understands the semantic connection
BM25:  no term overlap between "hard to maintain" and "technical debt"
```

### Cross-lingual (if using multilingual models)
Dense retrieval with multilingual models can find relevant docs in different languages.
BM25 has zero cross-lingual ability without explicit translation.

---

## Phase 6: Production Checklist

Before deploying hybrid search to production:

- [ ] Eval set shows recall improvement over dense-only
- [ ] Latency budget measured: BM25 + dense + RRF + (optional) reranking
- [ ] BM25 tokenizer handles your domain's special characters (hyphens, slashes, dots)
- [ ] Dense model handles your maximum query length (most models cap at 512 tokens)
- [ ] RRF k constant validated on eval set (try k=30, 60, 120)
- [ ] If using cross-encoder: `finish_reason` monitored to detect truncation
- [ ] Error handling: what if BM25 returns zero results? (pass only dense to RRF)
- [ ] Monitoring: log which method contributed the top-1 result per query

---

## Appendix: Quick Parameter Guide

```
BM25:
  k1 = 1.5   (default, works for most RAG use cases)
  b  = 0.75  (default, works for most RAG use cases)
  Tune b downward for short fixed-length chunks (< 100 words)

RRF:
  k = 60     (default, works for most 2-3 method fusions)
  Increase k if one method is dominant and adding the other hurts
  Decrease k if you want top-ranked docs to have stronger influence

Retrieval widths:
  retrieve_k = 50   (cast wide net; both methods return top-50 candidates)
  rerank_k   = 20   (rerank the top-20 merged candidates)
  final_k    = 5    (return top-5 to the LLM context)

Cross-encoder:
  max_length = 512  (truncates doc + query to 512 tokens; check your chunk sizes)
  batch_size = 16   (GPU) or 4 (CPU) for the reranking call
```
