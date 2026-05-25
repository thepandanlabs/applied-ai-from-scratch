# Embedding Models

> The embedding model you pick sets your retrieval ceiling. Every other optimization is bounded by it.

**Type:** Build
**Languages:** Python
**Prerequisites:** 02-01 Embeddings Intuition
**Time:** ~75 minutes
**Phase:** 02 · Retrieval & RAG

## Learning Objectives

- Compare the 2026 embedding model landscape across cost, quality, latency, and domain fit
- Implement a repeatable MRR-based benchmark to measure embedding model quality on your own data
- Explain Matryoshka embeddings and when truncation is a valid cost optimization
- Call OpenAI, Voyage, and a local sentence-transformer model with the same interface and compare results
- Build a domain-specific retrieval evaluation that surfaces the model quality gap before production

---

## The Problem

An engineering team at a fintech company spent three weeks tuning their RAG pipeline: prompt engineering, chunk size experiments, reranking: and couldn't get above 60% answer accuracy. When they finally ran a proper retrieval evaluation, they discovered their top-1 retrieval precision was 47%. They were using `all-MiniLM-L6-v2`: a model built for general-purpose semantic search: to retrieve financial regulation documents full of acronyms, legal terms, and numerical references that the model had never been trained to understand.

The LLM can't generate a correct answer from irrelevant context. No amount of prompt tuning fixes a retrieval problem. Three weeks of work was wasted because the wrong embedding model was chosen at the start.

This is the decision that matters most in RAG system design, and it's the one engineers most often make carelessly: picking whatever model is in the first tutorial they read, or defaulting to the largest available option without evaluating whether it's the right fit. Embedding models vary by a factor of 10x on cost, 5x on latency, and 30+ percentage points on retrieval quality for specialized domains. Getting this decision right before you write the rest of your pipeline saves weeks.

---

## The Concept

### The Landscape in 2026

The embedding model market has matured into three tiers:

**API-hosted, general-purpose**: best balance of quality and convenience:

| Model | Provider | Dims | Context | Notes |
|---|---|---|---|---|
| text-embedding-3-small | OpenAI | 1536 | 8,192 tok | Best cost/quality ratio for English |
| text-embedding-3-large | OpenAI | 3072 | 8,192 tok | Top English quality; 5x cost of small |
| embed-v4 | Cohere | 1024 | 128K tok | Strong multilingual; long context |
| voyage-4 | Voyage AI | 1024 | 32K tok | RAG-optimized, strong on retrieval tasks |
| Gemini Embedding 2 | Google | 3072 | 32K tok | Strong cross-lingual; native Google infra |

**Open-weight, self-hosted**: full control, no per-token cost:

| Model | Dims | Notes |
|---|---|---|
| BGE-M3 | 1024 | Dense + sparse + ColBERT in one model; multilingual |
| Qwen3-Embedding | 1536 | Strong open-weight option; multilingual |
| all-MiniLM-L6-v2 | 384 | Prototyping baseline: fast, small, not production quality |
| all-mpnet-base-v2 | 768 | Better quality baseline; still general-purpose |

**Domain-specialized**: fine-tuned for specific content types:

| Domain | Model |
|---|---|
| Code | voyage-code-3, CodeBERT |
| Legal | legal-bert-base-uncased (older but still useful baseline) |
| Biomedical | BioBERT, PubMedBERT |
| Multilingual | BGE-M3, paraphrase-multilingual-MiniLM-L12-v2 |

### Matryoshka Embeddings

OpenAI's `text-embedding-3-small` and `text-embedding-3-large` support Matryoshka Representation Learning (MRL). This means the model is trained so that the first N dimensions of a 1536-dim vector contain the most important information, and you can truncate to a smaller size without catastrophic quality loss.

```
Full 1536-dim:   [d1, d2, d3, ..., d768, ..., d1536]   ← max quality
Truncate to 768: [d1, d2, d3, ..., d768]                ← ~95% quality at half the storage
Truncate to 256: [d1, d2, d3, ..., d256]                ← ~88% quality at 1/6 the storage
```

This matters because vector storage and similarity computation scale with dimension. A 50M-document index at 1536 dims uses 300GB. At 256 dims, it's 50GB. If 88% quality is acceptable, Matryoshka truncation is a free win.

Traditional models don't support this: truncating `all-MiniLM-L6-v2` arbitrarily would destroy quality because the later dimensions carry meaningful signal not captured by the first N.

### Dimensions vs. Quality

Counterintuitively, more dimensions does not always mean better quality:

```
Model quality is determined by:
  1. Training data quality and quantity
  2. Training objective (contrastive learning setup)
  3. Model architecture (BERT vs. transformer encoder variants)
  4. Fine-tuning on domain-specific tasks

Dimension count is a capacity choice: more capacity helps only if
the training data can fill it with meaningful signal.
```

A 768-dim model trained on 1B sentence pairs often beats a 3072-dim model trained on 100M pairs for general retrieval tasks. Always evaluate; never assume.

### The Eval Loop: MTEB vs. Your Domain

MTEB (Massive Text Embedding Benchmark) is the go-to public leaderboard for comparing models across 56 tasks including retrieval, classification, and clustering. It's a good starting point but has a critical limitation: it evaluates on public datasets. Your production data is different.

```
Decision flow:

1. Start with MTEB retrieval leaderboard to identify top-5 candidates
2. Collect 50-100 (query, relevant_document) pairs from YOUR data
3. Run your benchmark: measure MRR@5 and Hit Rate@5
4. Pick the model that wins on YOUR data, not MTEB
5. Re-run when your data distribution shifts (new product lines, new languages)
```

Mean Reciprocal Rank (MRR) is the right metric for this evaluation:

```
For each query:
  find the rank of the first correct document in the results
  MRR contribution = 1 / rank

MRR = mean over all queries

MRR = 1.0   → first result is always correct
MRR = 0.5   → correct answer is at rank 1 or 2 on average
MRR = 0.2   → correct answer is buried; retrieval is failing
```

### When to Use Local vs. API

```
                   LOCAL (sentence-transformers / self-hosted)
                   ┌────────────────────────────────────────┐
                   │ Privacy: documents can't leave network  │
                   │ Cost: free at runtime, pay for compute  │
                   │ Latency: depends on hardware            │
                   │ Control: can fine-tune on your data     │
                   │ Ops: you manage model updates           │
                   └────────────────────────────────────────┘

                   API (OpenAI / Voyage / Cohere)
                   ┌────────────────────────────────────────┐
                   │ Privacy: data leaves your network       │
                   │ Cost: pay per token (scales with volume)│
                   │ Latency: 50-200ms per batch API call    │
                   │ Control: no fine-tuning (usually)       │
                   │ Ops: zero; provider handles updates     │
                   └────────────────────────────────────────┘

Decision rule of thumb:
  < 10M docs AND non-sensitive: start with API (text-embedding-3-small)
  > 10M docs: self-hosted to control costs
  Sensitive data (healthcare, finance, legal): self-hosted
  Need fine-tuning: self-hosted
```

---

## Build It

We'll build a benchmark harness that evaluates multiple embedding models on the same test set and computes MRR@5. This is the tool you run before committing to an embedding model for production.

### Step 1: Define the Test Set

A good benchmark test set has human-labeled query/document pairs. For demonstration, we'll build a small in-code test set. In practice, you'd load this from a CSV or JSONL file of labeled pairs from your domain.

```python
# pip install numpy sentence-transformers openai httpx

# Structure: a list of (query, list_of_relevant_doc_ids, all_documents)
# We represent documents as (doc_id, text) tuples

DOCUMENTS = [
    ("doc_0", "How to configure multi-factor authentication for your account"),
    ("doc_1", "Understanding your monthly invoice and billing cycle"),
    ("doc_2", "Troubleshooting application startup failures and crash reports"),
    ("doc_3", "API rate limits: requests per second and daily quota"),
    ("doc_4", "Data retention policies and automated backup schedules"),
    ("doc_5", "Setting up SSO with SAML 2.0 and identity providers"),
    ("doc_6", "Network timeout errors and connection refused troubleshooting"),
    ("doc_7", "Exporting account data for GDPR compliance requests"),
    ("doc_8", "Password reset flow and recovery email configuration"),
    ("doc_9", "Webhook event types and payload schema reference"),
]

# Each entry: (query_text, [list of relevant doc_ids])
LABELED_QUERIES = [
    ("my login isn't working with the authenticator app", ["doc_0"]),
    ("I can't see my latest charge on the bill", ["doc_1"]),
    ("the app crashes immediately when I try to open it", ["doc_2"]),
    ("how do I avoid hitting API limits in production", ["doc_3"]),
    ("where are my files backed up", ["doc_4"]),
    ("set up enterprise single sign-on", ["doc_5"]),
    ("connection keeps timing out", ["doc_6"]),
    ("I need to download all my data for legal reasons", ["doc_7"]),
    ("forgot password and can't get into my account", ["doc_8"]),
    ("what data format do webhooks send", ["doc_9"]),
]
```

### Step 2: Implement MRR@K

```python
import numpy as np

def cosine_similarity_matrix(query_vecs: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """
    Compute pairwise cosine similarity between query and doc vectors.
    Assumes vectors are already normalized (unit length).
    Returns shape (num_queries, num_docs).
    """
    return query_vecs @ doc_vecs.T


def compute_mrr(
    query_vecs: np.ndarray,
    doc_vecs: np.ndarray,
    labeled_queries: list[tuple[str, list[str]]],
    doc_ids: list[str],
    k: int = 5,
) -> dict:
    """
    Compute MRR@K and Hit Rate@K for a set of labeled queries.

    labeled_queries: list of (query_text, [relevant_doc_ids])
    doc_ids: ordered list of document IDs matching doc_vecs rows
    """
    id_to_idx = {doc_id: i for i, doc_id in enumerate(doc_ids)}
    sim_matrix = cosine_similarity_matrix(query_vecs, doc_vecs)

    reciprocal_ranks = []
    hits = []

    for q_idx, (query_text, relevant_ids) in enumerate(labeled_queries):
        scores = sim_matrix[q_idx]
        # argsort descending: highest score first
        ranked_indices = np.argsort(scores)[::-1][:k]
        ranked_doc_ids = [doc_ids[i] for i in ranked_indices]

        # MRR: find rank of first relevant document
        rr = 0.0
        hit = False
        for rank, doc_id in enumerate(ranked_doc_ids, start=1):
            if doc_id in relevant_ids:
                rr = 1.0 / rank
                hit = True
                break

        reciprocal_ranks.append(rr)
        hits.append(1 if hit else 0)

    mrr = float(np.mean(reciprocal_ranks))
    hit_rate = float(np.mean(hits))
    return {"mrr": mrr, "hit_rate": hit_rate, "k": k}
```

### Step 3: Build the Evaluation Harness

```python
import time
from dataclasses import dataclass

@dataclass
class ModelResult:
    model_name: str
    mrr: float
    hit_rate: float
    latency_ms: float  # time to encode all queries, in ms
    dim: int


def evaluate_sentence_transformer(
    model_name: str,
    documents: list[tuple[str, str]],
    labeled_queries: list[tuple[str, list[str]]],
    k: int = 5,
) -> ModelResult:
    """Evaluate a sentence-transformer model."""
    from sentence_transformers import SentenceTransformer

    doc_ids = [d[0] for d in documents]
    doc_texts = [d[1] for d in documents]
    query_texts = [q[0] for q in labeled_queries]

    model = SentenceTransformer(model_name)

    # Encode documents (index time: we don't time this)
    doc_vecs = model.encode(
        doc_texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    )

    # Encode queries and time it (query time: this is what matters for latency)
    t0 = time.perf_counter()
    query_vecs = model.encode(
        query_texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    metrics = compute_mrr(query_vecs, doc_vecs, labeled_queries, doc_ids, k=k)

    return ModelResult(
        model_name=model_name,
        mrr=metrics["mrr"],
        hit_rate=metrics["hit_rate"],
        latency_ms=latency_ms,
        dim=doc_vecs.shape[1],
    )
```

### Step 4: Add an OpenAI Embedding Call

```python
def evaluate_openai(
    model_name: str,
    documents: list[tuple[str, str]],
    labeled_queries: list[tuple[str, list[str]]],
    dimensions: int | None = None,
    k: int = 5,
) -> ModelResult:
    """
    Evaluate an OpenAI embedding model.
    Set OPENAI_API_KEY in your environment.

    `dimensions` enables Matryoshka truncation for text-embedding-3-* models.
    Pass dimensions=256 to test a truncated version.
    """
    import openai

    client = openai.OpenAI()
    doc_ids = [d[0] for d in documents]
    doc_texts = [d[1] for d in documents]
    query_texts = [q[0] for q in labeled_queries]

    def embed_batch(texts: list[str]) -> np.ndarray:
        kwargs = {"model": model_name, "input": texts}
        if dimensions:
            kwargs["dimensions"] = dimensions
        response = client.embeddings.create(**kwargs)
        vecs = np.array([item.embedding for item in response.data])
        # Normalize
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / norms

    doc_vecs = embed_batch(doc_texts)

    t0 = time.perf_counter()
    query_vecs = embed_batch(query_texts)
    latency_ms = (time.perf_counter() - t0) * 1000

    metrics = compute_mrr(query_vecs, doc_vecs, labeled_queries, doc_ids, k=k)
    actual_dim = dimensions if dimensions else doc_vecs.shape[1]

    return ModelResult(
        model_name=f"{model_name}@{actual_dim}d" if dimensions else model_name,
        mrr=metrics["mrr"],
        hit_rate=metrics["hit_rate"],
        latency_ms=latency_ms,
        dim=actual_dim,
    )
```

### Step 5: Print the Results Table

```python
def print_benchmark_table(results: list[ModelResult]) -> None:
    print(f"\n{'Model':<45} {'Dims':>5} {'MRR@5':>7} {'Hit@5':>7} {'Q-Lat ms':>10}")
    print("-" * 80)
    for r in sorted(results, key=lambda x: x.mrr, reverse=True):
        print(
            f"{r.model_name:<45} {r.dim:>5} {r.mrr:>7.3f} "
            f"{r.hit_rate:>7.1%} {r.latency_ms:>10.1f}"
        )
    print()
    best = max(results, key=lambda x: x.mrr)
    print(f"Best model: {best.model_name}  (MRR@5={best.mrr:.3f})")
```

> **Real-world check:** Your product manager looks at this benchmark and says: "Can't we just pick the cheapest model and move on? Our users seem fine with the current search." How do you explain why model choice matters in terms of outcomes they actually care about, without getting into MRR scores?

---

## Use It

In production, you call embedding APIs through their official clients. Here's the minimal interface for each major provider: note the pattern is identical across all of them, only the client and model name changes:

```python
# OpenAI
import openai
client = openai.OpenAI()
response = client.embeddings.create(
    model="text-embedding-3-small",
    input=["text one", "text two"],
    dimensions=1536,  # optional: Matryoshka truncation
)
vectors = [item.embedding for item in response.data]

# Voyage AI
import voyageai
client = voyageai.Client()
result = client.embed(
    ["text one", "text two"],
    model="voyage-4",
    input_type="document",  # or "query" for query embedding
)
vectors = result.embeddings

# Cohere
import cohere
co = cohere.Client()
response = co.embed(
    texts=["text one", "text two"],
    model="embed-english-v3.0",
    input_type="search_document",  # or "search_query"
)
vectors = response.embeddings
```

**Why use an API over a local model?**

- Zero infrastructure: no GPU allocation, no model loading overhead
- Model updates are transparent (the provider handles quality improvements)
- Better quality on English text for most use cases (text-embedding-3-small beats all-MiniLM by 15-20 points on retrieval benchmarks)
- Cohere and Voyage provide `input_type` which fine-tunes the embedding for query vs. document asymmetry: a meaningful quality improvement for RAG

**The asymmetric embedding trick:**

When your query is short ("what is a refund policy?") and your documents are long (full policy pages), asymmetric embeddings help: the query and document are embedded with slightly different functions, both trained together to maximize retrieval. Voyage's `input_type="query"` / `"document"` implements this. Using the same function for query and document (as sentence-transformers does by default) is called symmetric embedding.

> **Perspective shift:** A sceptical senior engineer says: "We already pay for OpenAI. Why are we evaluating Voyage and Cohere? Isn't this just adding vendor complexity for marginal gains?" What would you say to take that concern seriously, and what concrete conditions would actually justify sticking with one provider?

---

## Ship It

This lesson produces a reusable benchmark script you can run on your own data.

**Artifact:** `02-embedding-models/outputs/prompt-embedding-model-selector.md`

This prompt file is a decision-tree advisor you can use with any LLM to get a structured recommendation for your specific constraints. Feed it your use case details and get a ranked shortlist of models to test.

The `code/main.py` provides a ready-to-run benchmark harness. Swap in your own documents and labeled queries (even 20 pairs is enough for a meaningful signal) and run it before committing to a model.

---

## Evaluate It

**Check 1: MRR@5 on Your Domain Data**

Run the benchmark harness in `code/main.py` with 30–50 labeled pairs from your actual corpus. Interpret:
- MRR@5 > 0.85: strong retrieval: model fits your domain
- MRR@5 0.65–0.85: acceptable for most use cases, but test alternatives
- MRR@5 < 0.65: model-domain mismatch; evaluate specialized options

**Check 2: Long-Document Truncation Test**

If your documents exceed the model's context window (most models: 512 tokens), the tail of the document is silently ignored. Test this:

```python
long_doc = "short intro... " + ("filler content " * 200) + "the answer is here at the end"
short_query = "what is the answer"
# If the model can't find it, your long docs need chunking (Lesson 04)
```

**Check 3: Cross-Model Compatibility**

Never mix embeddings from different models (or different model versions) in the same index. This produces nonsensical similarity scores:

```python
import numpy as np
from sentence_transformers import SentenceTransformer

m1 = SentenceTransformer("all-MiniLM-L6-v2")
m2 = SentenceTransformer("all-mpnet-base-v2")

v1 = m1.encode(["test query"], normalize_embeddings=True)
v2 = m2.encode(["test query"], normalize_embeddings=True)

# These vectors have different dimensions (384 vs 768): you can't compare them.
# Even if dimensions matched, different training = different coordinate systems.
print(f"m1 dim: {v1.shape[1]}, m2 dim: {v2.shape[1]}")
# Store model name and version alongside every indexed document.
```

---

## Exercises

1. **Easy:** Extend the benchmark harness to also report the *worst-performing query* for each model: the query with the lowest MRR contribution. This identifies the specific failure mode for each model.

2. **Medium:** Implement Matryoshka truncation evaluation for `text-embedding-3-small`. Benchmark MRR@5 at dimensions 256, 512, 768, and 1536. Plot the quality/cost tradeoff curve and find the knee point: the smallest dimension that preserves 95% of full-dimension quality.

3. **Hard:** Fine-tune a sentence-transformer on your own domain data using the `sentence-transformers` training API. Generate positive pairs (query, relevant_doc) from your labeled set and hard negatives (query, a document that scores high but is incorrect). Compare fine-tuned vs. base model MRR@5. This is the workflow you'd run to close the domain gap when no off-the-shelf model fits.

---

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Matryoshka embeddings | "Truncatable embeddings" | Vectors trained so the first N dimensions contain the highest-quality representation: you can discard later dimensions without losing proportionally much quality |
| MRR | "Mean Reciprocal Rank: measures retrieval quality" | The average of 1/rank across queries, where rank is the position of the first relevant result. MRR=1.0 means always ranked first. |
| MTEB | "The embedding model leaderboard" | A multi-task benchmark covering retrieval, classification, and clustering: useful for initial screening but not a substitute for domain-specific evaluation |
| Asymmetric embedding | "Different functions for queries vs. documents" | Embedding models trained to handle query/document asymmetry: short queries mapped to a space optimized to retrieve longer documents |
| Context window | "How long a text the model can handle" | Maximum input length (in tokens) the model processes; text beyond this is truncated silently: a frequent source of retrieval bugs on long documents |

---

## Further Reading

- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard): Filter by "Retrieval" task type; sort by your relevant language and use case before picking a model
- [OpenAI Embeddings Documentation](https://platform.openai.com/docs/guides/embeddings): Covers Matryoshka truncation, dimensions parameter, and batch limits for text-embedding-3-* models
- [Voyage AI Model Cards](https://docs.voyageai.com/docs/embeddings): Explains query vs. document input types and when asymmetric embedding improves retrieval
- [BGE-M3: Multi-Functionality, Multi-Linguality, Multi-Granularity](https://arxiv.org/abs/2402.03216): The paper behind BGE-M3; explains how dense + sparse + ColBERT-style embeddings can be combined from a single model
- [Matryoshka Representation Learning](https://arxiv.org/abs/2205.13147): The original paper; explains the training procedure that makes Matryoshka truncation work without quality collapse
