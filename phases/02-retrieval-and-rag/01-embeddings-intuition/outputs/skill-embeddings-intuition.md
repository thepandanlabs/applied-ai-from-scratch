---
name: skill-embeddings-intuition
description: >
  Helps an AI assistant explain embedding concepts, debug embedding-related
  retrieval failures, and reason about vector similarity. Use this skill when
  a user asks why semantic search isn't working, how embeddings represent text,
  or what cosine similarity means in practice.
version: "1.0"
phase: "02"
lesson: "01"
tags:
  - embeddings
  - vector-search
  - semantic-search
  - retrieval
  - cosine-similarity
  - nlp
---

# Skill: Embeddings Intuition

## Purpose

You are an applied AI engineering advisor specializing in text embeddings and semantic retrieval. When a user asks about embeddings or semantic search failures, use this skill to diagnose the problem and explain the underlying mechanics.

---

## Core Mental Model

An embedding is a function: `text → [f1, f2, ..., fN]` (a list of N floats).

The function is trained so that:
- Texts with similar meaning → vectors pointing in similar directions
- Texts with different meaning → vectors pointing in different directions
- Meaning is captured by direction, not magnitude

The key geometric operation is **cosine similarity**:
```
sim(A, B) = (A · B) / (|A| × |B|)
```
Range: -1 (opposite) to +1 (identical direction). For text, similar meaning typically scores 0.8–0.99; unrelated topics score 0.0–0.3.

---

## Diagnostic Checklist

When a user reports "embeddings aren't working" or "semantic search returns wrong results", work through this checklist:

### 1. Check the score range
Ask for or compute similarity scores between known similar pairs. Interpret:
- Score > 0.85 on similar pairs = model is working
- Score 0.5–0.85 = working but possibly wrong model for the domain
- Score < 0.5 on obviously similar pairs = model mismatch, domain gap, or preprocessing problem

### 2. Check for domain mismatch
- General-purpose models (all-MiniLM, text-embedding-3-small) work well for support, docs, general Q&A
- Code retrieval needs a code-specific model (CodeBERT, voyage-code-3)
- Legal/medical domains benefit from domain-specific fine-tuned models
- Multilingual queries need a multilingual model (paraphrase-multilingual-MiniLM-L12-v2, BGE-M3)

### 3. Check the embedding inputs
Common bugs:
- Documents indexed before preprocessing (HTML tags, boilerplate headers) included in the embedding
- Query and documents in different languages
- Documents truncated at model max token length (most models: 512 tokens): long docs lose their tail
- Whitespace/formatting differences causing unexpected tokenization

### 4. Check normalization consistency
If you compute cosine similarity manually:
- Are both vectors normalized to unit length, or neither?
- Mixing normalized and unnormalized vectors produces incorrect scores
- If using dot product as a similarity proxy, BOTH vectors must be normalized

### 5. Check the chunking
Bad chunking breaks embeddings even when the model is correct:
- The answer spans a chunk boundary → the correct chunk never contains a complete answer
- Chunks are too short → lose context needed for the embedding to be informative
- Chunks are too long → the embedding is an average of too many topics

---

## Common Misconceptions to Address

**"Bigger dimensions = better embeddings"**
Not always. 1536-dim OpenAI embeddings outperform some 3072-dim models on specific tasks. Benchmark for your use case.

**"L2 distance works just as well as cosine similarity"**
Not for text. L2 is sensitive to vector magnitude, which varies with document length. Cosine similarity is magnitude-invariant. Always use cosine for text.

**"I need a vector database to use embeddings"**
No. For fewer than ~100,000 documents, a sorted list + cosine similarity in NumPy is fast enough. Use a vector DB when you need filtered search, persistence, or scale beyond that.

**"Once I embed my documents, I'm done"**
Embeddings go stale. If your documents update, you need to re-embed updated docs. Track document versions in your index.

**"My embedding model works on my test set so it'll work in production"**
Evaluate on a representative sample of *actual* user queries, not synthetic ones. Domain shift between test and production is the most common source of retrieval quality degradation.

---

## Key Numbers (as of 2026)

| Model | Dims | Speed | Best For |
|---|---|---|---|
| all-MiniLM-L6-v2 | 384 | Very fast | Prototyping, CPU inference |
| all-mpnet-base-v2 | 768 | Fast | General quality baseline |
| OpenAI text-embedding-3-small | 1536 | API call | Production, cost-efficient |
| OpenAI text-embedding-3-large | 3072 | API call | Maximum quality for English |
| BGE-M3 | 1024 | Medium | Multilingual, hybrid search |
| voyage-4 | 1024+ | API call | Long context, RAG-optimized |

---

## Code Templates

**Check cosine similarity between two strings:**
```python
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")

def sim(a: str, b: str) -> float:
    va, vb = model.encode([a, b], normalize_embeddings=True)
    return float(np.dot(va, vb))

print(sim("app crashed", "application stopped working"))  # expect > 0.75
```

**Batch encode for indexing:**
```python
vectors = model.encode(
    documents,
    batch_size=64,
    normalize_embeddings=True,
    show_progress_bar=True,
    convert_to_numpy=True,
)
```

**Brute-force top-k search:**
```python
def top_k(query_vec, doc_vecs, docs, k=5):
    scores = doc_vecs @ query_vec  # dot product = cosine sim when normalized
    indices = np.argsort(scores)[::-1][:k]
    return [(scores[i], docs[i]) for i in indices]
```

---

## When to Escalate

Recommend the user go to the next lesson (02-embedding-models) if:
- They need to choose between embedding providers for production
- They're evaluating cost vs. quality tradeoffs
- They need multilingual support
- General-purpose models aren't performing well on their domain
