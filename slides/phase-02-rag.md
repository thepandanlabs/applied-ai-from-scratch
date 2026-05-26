---
marp: true
theme: applied-ai
class: title
paginate: true
footer: 'Applied AI From Scratch · Phase 02: Retrieval & RAG'
---

# Phase 02: Retrieval & RAG

### From raw vectors to a production-grade RAG service

**Applied AI From Scratch**
16 lessons · ~16 hours · Python

<!-- SPEAKER: Welcome to Phase 02. This phase is the most widely deployed AI pattern in production today. Engineers who understand RAG properly can debug any system that builds on top of it, including agents. Time: ~5 min -->

---

## Who this is for

You are a **working software engineer** who:

- Can write Python and make an API call
- Wants to understand RAG well enough to **debug it at 2 a.m.**
- Is tired of tutorials that stop before the system breaks

**What you will not get:**
- "Just use LangChain" without understanding what it does
- Vibes-based retrieval quality assessment
- Math derivations

<!-- SPEAKER: Set expectations. This is practitioner-focused. We build raw first, then use frameworks, so every framework call is debuggable. Time: ~2 min -->

---

## What you will build

By the end of this phase you will have shipped:

- A **semantic search service** with dense + sparse hybrid retrieval
- A **text-to-SQL pipeline** for natural language over structured data
- A **codebase Q&A system** using AST-aware chunking
- A **retrieval evaluation harness** (the RAG Triad)
- A **production FastAPI service** with eval endpoint and Dockerfile

Every lesson adds one thing and shows you when it breaks.

<!-- SPEAKER: Concrete deliverables. Each item maps to specific lessons. Time: ~2 min -->

---
<!-- _class: section -->

## The Through-Line

### Why does this phase exist?

---

## The core problem

**RAG gives models access to knowledge they were not trained on.**

But naive RAG:

- Works around **60% of the time**
- Breaks **silently** the other 40%
- Is almost impossible to debug without the right mental model

This phase builds the **diagnostic tools and advanced patterns** to get from 60% to 95%+.

The path: build naive, measure what breaks, fix systematically.

<!-- SPEAKER: This is the most important framing slide. Silent failures are what make RAG hard. Without metrics, every fix is a guess. Time: ~3 min -->

---

## The RAG pipeline at 30,000 feet

```
┌──────────────────────────────────────────────────────────┐
│  INGEST (done once, offline)                              │
│  documents → chunk → embed each chunk → store in vector DB│
└──────────────────────────────────┬───────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────┐
│  QUERY (happens per user request, in real time)           │
│  user question → embed query → find similar chunks        │
│  → stuff chunks into prompt → LLM generates answer        │
└──────────────────────────────────────────────────────────┘
```

**Two different failure modes. Two different fixes.**

Retrieval failure: right chunk never retrieved.
Generation failure: right chunk retrieved but answer still wrong.

<!-- SPEAKER: Draw the line between ingest and query time. This mental model is reused throughout the entire phase. Time: ~3 min -->

---
<!-- _class: section -->

## Foundations
### L01-L04: Primitives

---
<!-- _class: section -->

## L01: Embeddings Intuition

---

## What an embedding actually is

Text is a point in space. Similar meaning lives nearby.

```
"my app won't start"         → [0.12, -0.43, 0.88, ..., 0.21]  (384 numbers)
"application launch failure" → [0.11, -0.41, 0.85, ..., 0.19]  (very close!)
"best pizza in Brooklyn"     → [-0.67, 0.92, -0.14, ..., 0.55]  (far away)
```

The model was trained to pull similar sentences together and push dissimilar ones apart.

**Why this matters:** "my app won't start" and "Application Launch Failure Troubleshooting" share zero words. Keyword search returns nothing. Semantic search returns the right document.

<!-- SPEAKER: The business case: $12 per avoidable support call, 400/day. Embeddings solve the vocabulary mismatch that keyword search cannot. Time: ~4 min -->

---

## Cosine similarity: angle, not distance

We care about **direction**, not magnitude. A long document and a short one about the same topic should score high.

```
                      A · B
cosine_sim(A, B) = ---------
                   |A| × |B|

cosine_sim("app won't start", "application launch failure") = 0.91  (similar)
cosine_sim("app won't start", "best pizza in Brooklyn")     = 0.04  (unrelated)
```

Range: -1 to +1. In practice, similar text pairs score 0.85-0.99.

**Key insight:** Normalize vectors to unit length and dot product equals cosine similarity. That is the fast path in every production vector store.

<!-- SPEAKER: No calculus needed. Just: angle between vectors tells you how similar the directions are, magnitude doesn't matter. Time: ~3 min -->

---

## The coordinate space constraint

```
                   API-HOSTED               OPEN-WEIGHT
                 text-embedding-3-small    all-MiniLM-L6-v2
                 1536 dimensions           384 dimensions
                        │                        │
                        ▼                        ▼
                 coordinate system A      coordinate system B

  NEVER mix vectors from different models in the same index.
  Different models = different coordinate systems.
  Cross-model similarity scores are meaningless.
```

**Every chunk must be embedded with the same model version.**

Store the model name alongside the index. Re-embed everything when you upgrade.

<!-- SPEAKER: This is the most common "it stopped working" bug after a model upgrade. Stress this. Time: ~2 min -->

---
<!-- _class: section -->

## L02: Choosing an Embedding Model

---

## The 2025 model lineup

| Model | Provider | Dims | Best for |
|---|---|---|---|
| text-embedding-3-small | OpenAI | 1536 | Best cost/quality for English |
| voyage-4 | Voyage AI | 1024 | RAG-optimized retrieval tasks |
| BGE-M3 | Open weight | 1024 | Dense + sparse + multilingual |
| all-MiniLM-L6-v2 | sentence-transformers | 384 | Dev/prototype only |

**Matryoshka embeddings (OpenAI 3-small/large):** Truncate to 256 dims for ~88% quality at 1/6 storage. A free optimization for large indices.

**Decision rule:** Start with MTEB leaderboard. Then benchmark on YOUR data with 50 labeled pairs. The model that wins on your domain beats any MTEB ranking.

<!-- SPEAKER: Three weeks of prompt tuning wasted because the team picked the wrong embedding model. Retrieval ceiling is set at model selection time. Time: ~4 min -->

---

## What MTEB tells you (and doesn't)

**MTEB (Massive Text Embedding Benchmark):** 56 tasks, retrieval, classification, clustering.

Good for: initial shortlist of candidates.

**Not good for:** your production data.

```
Decision flow:
  1. Filter MTEB leaderboard by Retrieval task type
  2. Pick top-5 candidates for your language
  3. Collect 50 labeled (query, relevant_doc) pairs from YOUR corpus
  4. Measure MRR@5 for each candidate on YOUR data
  5. Pick the winner on YOUR data

MRR > 0.85: model fits your domain
MRR 0.65-0.85: acceptable, test alternatives
MRR < 0.65: domain mismatch, look for specialized models
```

A fintech team used `all-MiniLM-L6-v2` on financial regulation documents. MRR: 0.47. Three weeks wasted.

<!-- SPEAKER: Real cost of wrong model choice. Run the benchmark first, not after. Time: ~3 min -->

---
<!-- _class: section -->

## L03: Vector Stores

---

## Flat index vs. HNSW

**Flat index (brute force):**
- Check every vector. Exact results. O(N) per query.
- Fine up to ~100K vectors on a single machine.

**HNSW (Hierarchical Navigable Small World):**
- Navigate a layered graph. O(log N) per query.
- ~95-99% recall (true nearest neighbor not always returned).
- Used by Qdrant, Weaviate, Pinecone, pgvector.

```
Flat:  Query → [doc1 0.72] [doc2 0.45] [doc3 0.91] [doc4 0.38] ... every doc
                 Exact. Slow above 100K.

HNSW:  Query → Layer2 coarse → Layer1 medium → Layer0 fine → top-K
                 Approximate. Fast at any scale.
```

**The rule:** Under 100K vectors, flat is fine. Above 100K, use HNSW.

<!-- SPEAKER: The tradeoff is always precision vs. speed. HNSW's ~1% miss rate is almost never the bottleneck in real RAG failures. Time: ~3 min -->

---

## pgvector vs. dedicated vector databases

```
           Speed    Cost     Persistence  Scale    Ops
In-memory  HIGH     Free     None         Small    Zero
pgvector   HIGH     Cheap    Postgres     Medium   Low (in your existing DB)
Qdrant     HIGH     Medium   File/Cloud   Large    Medium
Pinecone   HIGH     $$$$     Cloud        Huge     Zero (managed)
```

**The underrated option: pgvector**

If your corpus is under 5M vectors and your team already runs Postgres: use pgvector. A single Postgres instance with an HNSW index handles 5M vectors at 30-50ms per query.

Do not add operational complexity you do not need.

**When to move to Qdrant/Pinecone:** > 1M vectors, need hybrid search natively, or no existing Postgres infrastructure.

<!-- SPEAKER: Most teams reach for a dedicated vector DB before they need one. Save the migration for when you actually hit the ceiling. Time: ~3 min -->

---
<!-- _class: section -->

## L04: Chunking Strategies

---

## The six chunking strategies

| Strategy | Best for | Key property |
|---|---|---|
| Fixed-size + overlap | Homogeneous docs | Simple, fast, controllable |
| Recursive splitter | General prose | Respects natural boundaries |
| Markdown-aware | Docs, wikis, READMEs | Preserves headers/structure |
| Sentence-window | Precision Q&A | Embeds context, returns sentence |
| Semantic | Varied long-form | Topic-boundary aware |
| Late chunking | Long docs, cross-references | Full-doc context in vectors |

**The legal tech case:** Fixed-size at 256 tokens split "Either party may terminate this agreement upon 30 days written notice" across two chunks. Lawyers got word salad. Neither half-sentence was usable.

Chunking failures look like embedding failures. Always check chunk boundaries first.

<!-- SPEAKER: The most skipped step in RAG tutorials. A 20-minute manual chunk inspection saves days of chasing phantom embedding problems. Time: ~4 min -->

---

## The chunking heuristic

```
Too small: lose context → low faithfulness
  Chunk: "...terminate upon 30 days..."
  Problem: no operative sentence, no usable meaning

Too large: dilute signal → low context relevance
  Chunk: [entire 50-page contract section]
  Problem: vector averages hundreds of topics, matches everything vaguely

Rule of thumb:
  256-512 tokens, 10-15% overlap
  Adjust for your document type and query type
```

**Check your chunking before blaming the model:**

```python
def answer_in_chunk(answer: str, chunks: list[str]) -> bool:
    return any(answer.lower() in chunk.lower() for chunk in chunks)

coverage = sum(answer_in_chunk(ans, chunks) for q, ans in pairs) / len(pairs)
# Below 70%: chunking is splitting answers across boundaries
```

<!-- SPEAKER: The heuristic is a starting point, not a law. Measure coverage on your eval set to confirm. Time: ~3 min -->

---
<!-- _class: section -->

## Core RAG
### L05-L09: Build it, measure it, fix it

---
<!-- _class: section -->

## L05: Naive RAG

---

## The 5-step naive RAG pipeline

```
1. Load documents
2. Chunk text (fixed-size, overlap)
3. Embed each chunk
4. Store in vector DB (even a dict works)
5. At query time:
      embed query
   → find top-K similar chunks (cosine similarity)
   → stuff into LLM context
   → generate answer
```

That is all of RAG. Four functions and an LLM call.

**Build naive first. Profile what is slow or wrong. Then reach for a framework.**

This order matters. Starting with a framework means optimizing the wrong thing and debugging six abstraction layers when something fails.

<!-- SPEAKER: The entire Lesson 05 is about demystification. When you can read every line, you can debug every failure. Time: ~3 min -->

---
<!-- _class: code -->

## The 5-step loop in raw Python

```python
# The 5-step loop (raw, no framework)
chunks = chunk(documents)                    # step 2
vectors = [embed(c) for c in chunks]         # step 3
store = VectorStore(vectors, chunks)         # step 4

def query(q: str) -> str:                    # step 5
    results = store.search(embed(q), top_k=5)
    context = "\n".join(r.text for r in results)
    return llm(f"Answer using context:\n{context}\n\nQ: {q}")
```

**Two failure modes to keep separate:**

| Failure | Symptom | Root cause |
|---|---|---|
| Retrieval failure | Right chunk never in context | Chunking, embedding model, K too small |
| Generation failure | Right chunk retrieved, wrong answer | LLM ignored context, hallucinated |

**Diagnostic:** Log retrieved chunks for every bad query. If the right chunk is there, it is a generation problem. If it is not, it is a retrieval problem. Never fix the wrong one.

<!-- SPEAKER: This diagnostic split is the highest-value mental model in the entire phase. Drill it. Time: ~4 min -->

---

## What naive RAG skips (and why that is fine at first)

| Feature | What it does | When you actually need it |
|---|---|---|
| Metadata filtering | Restrict by date, source, tag | Multi-tenant or multi-domain corpora |
| Batched embedding | Embed hundreds at once | API cost at scale |
| Async retrieval | Non-blocking fetch | High-throughput services |
| Re-ranking | Second-pass scoring | When precision matters more than recall |
| Persistent storage | Survive restarts | Any production deployment |

**Build naive. Ship it. Measure the failures. Add exactly what the measurements say you need.**

Token cost check: log `prompt_tokens` per query. 3,000+ tokens per query = chunks too large or K too high. That compounds fast at scale.

<!-- SPEAKER: The point is not "skip everything" -- it's "add only what you need." Each addition has a measurement that justifies it. Time: ~2 min -->

---
<!-- _class: section -->

## L06: Retrieval Metrics

---

## The metrics that matter

| Metric | Question | When to use |
|---|---|---|
| Precision@K | Of K retrieved, what fraction is relevant? | Minimize context window noise |
| Recall@K | Of all relevant docs, what fraction retrieved? | Catch the right chunk at all |
| Hit Rate@K | Was any relevant doc in top-K? | Minimum viability check |
| MRR | How high up is the first relevant result? | Q&A systems, top result drives answer |
| nDCG@K | Quality of full ranking, position-weighted? | Re-ranking quality |

**Start with hit rate.** If hit rate at K=5 is below 70%, your system fails for 30% of queries. Nothing else matters until you fix that.

**"Looks relevant" is a feeling. Feelings do not survive a codebase change, a model upgrade, or a new document corpus.**

<!-- SPEAKER: The persuasion move here: 20 labeled pairs takes 2 hours. That 2 hours buys you a measurement you can run in under a second on every future change. Time: ~3 min -->

---

## Precision vs. recall tradeoff

Raising K always increases recall, usually decreases precision.

```
K=1:  High precision (1 chunk, probably relevant), Low recall (may miss most)
K=5:  Typical operating point, balance of noise vs. coverage
K=20: Low precision (lots of noise), High recall (probably found all)
```

**Context-specific metrics for RAG:**

- **Context Precision:** Of retrieved chunks, what fraction is actually useful to the LLM?
- **Context Recall:** Can the retrieved context support the full expected answer?

Context recall below 0.8: the LLM cannot fully answer. It is not hallucinating, you just did not give it the material. Fix: increase K, fix chunking, or add hybrid search.

Context precision below 0.5: more than half the context window is noise. Fix: reduce K, add similarity threshold, add reranker.

<!-- SPEAKER: The two RAG-specific metrics are the bridge from IR metrics to answer quality. Time: ~3 min -->

---
<!-- _class: section -->

## L07: Hybrid Search

---

## Why each method fails alone

**Dense search fails when:**
- Query contains rare terms, product codes, proper names
- Exact word in the document differs from the word in the query
- Very short, specific queries (little semantic context to embed)

**BM25 fails when:**
- User describes a concept rather than using the domain term
- Paraphrase without lexical overlap
- "What makes bread rise?" vs "yeast produces carbon dioxide"

**Hybrid wins consistently on benchmarks.**

The failure modes complement each other. Neither alone is best for a real corpus.

RFC 2616 is a real example: dense retrieval misses it entirely because the embedding model has no training signal for that exact identifier. BM25 finds it immediately.

<!-- SPEAKER: This is where dense-only pipelines fail silently for a whole class of queries. Product codes, legal case numbers, medical drug identifiers -- all BM25 territory. Time: ~3 min -->

---

## BM25 + dense + RRF fusion

```
Stage 1: Retrieve top-50 from BM25 (keyword matching)
Stage 1: Retrieve top-50 from dense (semantic matching)

Stage 2: Merge with Reciprocal Rank Fusion (RRF)
   RRF score = Σ  1 / (60 + rank_i)
   Only uses ranks, not scores -- scale-agnostic
   doc ranked 1 in both: RRF = 1/61 + 1/61 = 0.0328
   doc ranked 3 in BM25, 5 in dense: RRF = 1/63 + 1/65 = 0.0312

Stage 3 (optional): Cross-encoder reranker on top-20 candidates
   Sees (query, document) together in one forward pass
   More accurate, adds 50-200ms latency
   Use only on top candidates, not the full corpus
```

**In production:** Qdrant supports BM25 + dense + RRF server-side. Cohere Rerank for the cross-encoder step.

<!-- SPEAKER: Why RRF instead of score normalization: BM25 scores are unbounded, cosine similarities are 0-1. You cannot add them without normalization that changes per query. RRF sidesteps this entirely. Time: ~4 min -->

---
<!-- _class: section -->

## L08: Query Transformation

---

## The user's query is rarely the best retrieval query

| Problem | Example | Fix |
|---|---|---|
| Too short | "authentication timeout" | Query rewriting |
| Vocabulary mismatch | "is it safe" vs "contraindicated" | HyDE |
| Over-specified | "CVE-2024-41110 in libssl 3.2.1" | Step-back |
| Ambiguous | "Python environment setup" | Multi-query |

**HyDE (Hypothetical Document Embeddings):**
Instead of embedding the question, ask the LLM to generate a hypothetical answer and embed that. Questions and answers occupy different regions of embedding space. The hypothetical answer embeds near real answers.

Example: "is aspirin safe after a bleed?" generates a hypothetical excerpt about "salicylates contraindicated following hemorrhagic events," which embeds near the actual clinical text.

**Cost:** Each transformation adds one LLM call (~200-400ms). Apply selectively, not to every query.

<!-- SPEAKER: The medical example from the lesson is striking. Same information need, completely different vocabulary, low cosine similarity without transformation. Time: ~3 min -->

---
<!-- _class: section -->

## L09: Citation Grounding

---

## Why LLMs hallucinate citations

When you ask an LLM to "cite your sources," it uses parametric knowledge to generate the answer and then invents citation markers that feel right given the retrieved chunk text.

The citations are decoration, not attribution.

**The fix is architectural, not prompt-based:**

1. Every chunk carries metadata through the entire pipeline (source, page, chunk_id)
2. The prompt numbers each chunk and exposes numbers to the LLM
3. Every `[N]` in the response is verified against the retrieved set before shipping

**Two distinct failure modes:**

| Failure | Definition | Automated check? |
|---|---|---|
| Attribution failure | Cited source not in retrieved set | Yes: check cited IDs vs. retrieved IDs |
| Faithfulness failure | Source exists but does not support the claim | Requires LLM-as-judge (Lesson 10) |

Track `citation_hallucination_rate` as a production metric. Target: under 2%.

<!-- SPEAKER: The drug interaction case from the lesson: the AI cited a paper, the doctor caught it. The paper didn't say what the answer claimed. This is the worst class of failure: authoritative-looking but wrong. Time: ~3 min -->

---
<!-- _class: section -->

## Evaluation and Advanced Patterns
### L10-L13: Measure, then fix

---
<!-- _class: section -->

## L10: RAG Evaluation

---

## The RAG Triad: three numbers that don't lie

```
                    Context Relevance
                    (Are retrieved chunks relevant to the question?)
                           │
                           │ measures RETRIEVER quality
                           ▼
              User Query → Retriever → LLM → Answer
                                          │
                         ┌────────────────┤
                         │                │
                    Faithfulness     Answer Relevance
                    (Is answer        (Does answer address
                    supported by       the actual question?)
                    context?)
                    measures GENERATOR  measures GENERATOR
```

**Read the matrix right to left: if Context Relevance is low, fix the retriever before touching anything else. A good generator cannot win with bad context.**

<!-- SPEAKER: The RAG Triad is from RAGAS (the library). The key insight: three independent dimensions, three different root causes, three different fixes. Time: ~4 min -->

---

## What each score diagnoses

| Faithfulness | Answer Relevance | Context Relevance | Diagnosis |
|---|---|---|---|
| High | High | High | System is working |
| Low | High | High | Generator hallucinating |
| High | Low | High | Adjacent-answer failure |
| Low | Low | Low | Retriever broken first |
| Any | Any | Low | Fix retrieval, full stop |

**Faithfulness < 0.8:** Generator adds 1 in 5 claims from training memory. Too high for any production use.

**Context Relevance < 0.7:** Retriever is returning noise. No amount of prompt engineering fixes retrieval.

**The most important thing in RAG evaluation is the eval set, not the metrics.** 20 real queries from your domain, hand-labeled. Do this before measuring anything.

<!-- SPEAKER: Error analysis first: read 20-50 traces before running automated metrics. Your failure taxonomy is specific to your use case. Time: ~3 min -->

---

## LLM-as-judge: using an AI to evaluate an AI

```python
# Faithfulness judge: is each claim in the answer supported by the context?
FAITHFULNESS_SYSTEM = """Identify each factual claim in the ANSWER.
For each claim, check if the CONTEXT directly supports it.
Return JSON: {"claims": [...], "faithfulness_score": 0.0-1.0}"""

# Calibrate before you trust
def calibrate_judge(human_scores, judge_scores):
    agreement = sum(1 for h, j in zip(human_scores, judge_scores)
                   if (h >= 0.5) == (j >= 0.5)) / len(human_scores)
    return {"agreement_rate": agreement, "trustworthy": agreement >= 0.85}
```

**LLM judges have known biases:** verbosity bias, self-consistency bias, position bias.

**Calibrate before you trust:** score 20 examples with both judge and human. If agreement is under 85%, your judge prompt needs work. No calibration = no trust.

**Production library:** `ragas` (pip install ragas) implements the full RAG Triad with production-ready judge prompts.

<!-- SPEAKER: "We're using an AI to evaluate another AI -- isn't that circular?" No: the evaluation task is semantic understanding. The judge's job is different from the generator's job. But calibration is not optional. Time: ~3 min -->

---
<!-- _class: section -->

## L11: Advanced RAG

---

## Three structural failure modes of naive RAG

**1. Context fragmentation**
Complete thought spans multiple chunks. Each chunk is individually uninformative.
"the board assessed the following risks" + "none exceeded the materiality threshold" = two useless chunks. One parent chunk = complete picture.

**2. Size mismatch**
Optimal chunk size for retrieval precision (small) is different from the optimal chunk size for generation (large with context).

**3. Missing context**
Chunk contains "As noted above, the methodology changed in Q3." Stripped from document, it answers nothing.

Each failure maps to a pattern:

| Failure | Pattern | Mechanism |
|---|---|---|
| Context fragmentation | Parent-Document Retrieval | Index small, return large parent |
| Size mismatch | Parent-Document Retrieval | Precision in retrieval, richness in generation |
| Missing context | Contextual Retrieval | Prepend context before indexing |

<!-- SPEAKER: These are the failures that appear after naive RAG is "working." The system seems fine on demo queries. Production reveals the structural gaps. Time: ~3 min -->

---

## Three advanced patterns

**Parent-Document Retrieval (small-to-big):**
Index small child chunks. When one matches, return its large parent to the LLM. Zero added retrieval latency: pure index lookup.

**Multi-Vector Indexing:**
Generate summaries, keywords, or hypothetical questions per document. Index all representations. Return the full document when any representation matches. One-time LLM cost at index time.

**Contextual Retrieval (Anthropic, Sept 2024):**
Before indexing, prepend 1-2 sentences of context to each chunk describing its location and topic in the document. Reduced retrieval failures by 49% in Anthropic's benchmark.

For a 10,000-chunk corpus: ~$5-10 to contextualize with gpt-4o-mini. Recompute only when the corpus changes.

**Measure before and after using the RAG Triad from Lesson 10.**

<!-- SPEAKER: The Anthropic benchmark number (49% reduction) is a strong hook. Note that the cost amortizes over all future queries against that corpus. Time: ~3 min -->

---
<!-- _class: section -->

## L12: Agentic RAG

---

## When single-pass retrieval fails

**Multi-hop questions:** The second query depends on the result of the first.

"What are the side effects of metformin, and do any of them interact with the blood pressure medications mentioned in the Johnson et al. 2023 study?"

Steps required:
1. Retrieve: metformin side effects
2. Retrieve: Johnson et al. 2023 blood pressure medications
3. Retrieve: interactions between the two

No fixed retrieval strategy handles this. The second query cannot be written until you know the answer to the first.

**The architectural move:** Give the LLM a `search` tool. Let it decide when and how to call retrieval. Observe results. Decide whether to retrieve again. Generate when it has enough.

Static retrieval always runs once. Agentic RAG retrieves as many times as needed.

<!-- SPEAKER: This is the bridge to Phase 04 (Agents). A ReAct agent that calls a search tool is doing agentic RAG. Understanding RAG is understanding the core tool every agent uses. Time: ~3 min -->

---

## The agent loop with cost governors

```
User Question
    │
    ▼
LLM decides:
    ├── Call search_documents(query) → observe results → back to LLM
    ├── Call search_documents(query) → observe results → back to LLM
    │   [repeat until LLM decides it has enough]
    └── Generate final answer
         OR
         Return partial answer + warning (max iterations reached)
```

**Always add cost governors:**

- Max iterations (e.g., 5 retrieval calls)
- Token budget (stop if context window filling up)
- Deduplication (do not retrieve the same document twice)

Without governors, a poorly-stated question can trigger cascading retrieval calls. At $0.002 per 1K tokens, runaway retrieval is a real production cost.

**When NOT to use agentic RAG:** Single-fact queries, latency under 500ms required, simple Q&A where one retrieval always suffices.

<!-- SPEAKER: The key practical concern is the cost governor. Every agentic pattern needs one. Time: ~2 min -->

---
<!-- _class: section -->

## L13: Structured Retrieval (Text-to-SQL)

---

## When RAG is the wrong tool

**RAG retrieves semantically similar text. It does not aggregate, join, filter by date, or count rows.**

```
USE TEXT-TO-SQL WHEN                 USE RAG WHEN
  Data lives in tables                 Data is unstructured
  Query needs aggregation              Query needs fuzzy matching
  You need exact counts/totals         You need passages, not rows
  Schema is stable                     Schema does not exist

USE HYBRID WHEN
  Step 1: SQL finds the entity (customer ID, order number)
  Step 2: RAG answers a question about that entity's documents
```

**The three hard problems:**
1. LLM must know your schema (serialize it intelligently, include sample rows)
2. LLMs make SQL mistakes (build a self-correction loop: generate SQL → execute → feed error back → retry up to 2 times)
3. LLM-generated SQL runs against your real database (enforce read-only at connection level, always)

<!-- SPEAKER: Read-only enforcement is not optional. A write-capable LLM-generated SQL in production is a career-ending event. Time: ~3 min -->

---
<!-- _class: section -->

## Production Variants
### L14-L16: Code, Frameworks, and the Capstone

---
<!-- _class: section -->

## L14: RAG Over a Codebase

---

## The chunking challenge for code

**Line-based chunking on code destroys semantics:**

```python
# Source: auth.py
def authenticate(username: str, password: str) -> bool:
    """Verify user credentials against the database."""
    user = db.find_user(username)
    return hash(password) == user.password_hash
```

**Fixed-size chunks at 200 chars:**

- Chunk A: `def authenticate(username:` -- cut mid-signature
- Chunk B: `str, password: str) -> bool:` -- no function name visible
- Chunk C: `user = db.find_user(username)` -- no context

**AST-based chunking:** Parse with Python's `ast` module. One chunk per function or class. Each chunk carries: function name, docstring, full source, file path, line numbers.

Query "how does authentication work?" retrieves the `authenticate` chunk: complete, usable.

<!-- SPEAKER: The failure is immediate and obvious once you see the chunks. The fix is also obvious: treat the function as the unit of meaning, because it is. Time: ~3 min -->

---

## The rich text representation for code chunks

Do not embed raw source code. Embed a representation that bridges code and natural language:

```
Function `authenticate` in auth.py (lines 3-8):
Verify user credentials against the database.

def authenticate(username: str, password: str) -> bool:
    """Verify user credentials against the database."""
    user = db.find_user(username)
    return hash(password) == user.password_hash
```

This representation makes the chunk retrievable by:
- Natural language: "authentication", "password validation", "verify credentials"
- Code terms: "authenticate", "username", "password_hash"
- File-level: "auth.py", "lines 3-8"

**Bonus: AST-based incremental re-indexing.** Only re-embed modified functions. Use file modification times and a hash of each function's source. Large codebases reindex in seconds, not hours.

<!-- SPEAKER: The bridge between natural language queries and code is the docstring + function name. Both are in the rich representation. Time: ~3 min -->

---
<!-- _class: section -->

## L15: RAG Frameworks

---

## What frameworks add (and cost)

```
RAW (no framework)                     LLAMAINDEX
  You write: chunk, embed, store,        You get: managed nodes, loaders,
  retrieve, prompt                       multi-index, KG support
  You see: every decision, every         Cost: abstraction over ingestion
  failure                                When: complex ingestion, multi-index
  When: under 10k docs, early
  exploration

LANGCHAIN / LCEL
  You get: chain orchestration, routing,
  conditional logic, agent state
  Cost: deep abstraction stack
  When: multi-step pipelines, RAG inside
  an agent with memory
```

**Concept map (so framework calls are debuggable):**

| Raw operation | LlamaIndex | LangChain |
|---|---|---|
| `chunk_text()` | `SentenceSplitter` | `RecursiveCharacterTextSplitter` |
| `{text, vector}` dict | `Node` with relationships | `Document` with metadata |
| `embed()` + store | `VectorStoreIndex` | `FAISS.from_documents()` |
| `retrieve()` | `QueryEngine` | `as_retriever()` chain |

<!-- SPEAKER: The escape hatch principle: before adopting any framework, confirm it lets you drop to raw API calls when needed. If it doesn't, you cannot debug it when it fails. Time: ~3 min -->

---

## When raw is the right answer

Five lines of LlamaIndex replace 100 lines of raw:

```python
documents = SimpleDirectoryReader("./docs").load_data()
index = VectorStoreIndex.from_documents(documents)
query_engine = index.as_query_engine()
response = query_engine.query("What is the main argument?")
```

**What the framework buys you:** persistent storage, async loading, metadata extraction, batched embedding with retries, configurable chunking, a dozen retrieval modes.

**What it costs you:** visibility into every step. When it returns a wrong answer, you need to know the naive version to debug it.

**When to use raw:**
- Under 10K documents
- Simple Q&A, no multi-index
- Early exploration and prototyping

**When to import a framework:**
- Complex ingestion (many document types, loaders)
- Multi-index or knowledge graph retrieval
- RAG inside an agent pipeline with memory and state

<!-- SPEAKER: The engineers who do it backwards import the framework first and spend weeks debugging opaque failures. Time: ~2 min -->

---
<!-- _class: section -->

## L16: Capstone RAG Service

---

## The production service architecture

```
Client
  │
  ├── POST /ingest  → content hash → chunk → embed → vector store
  │                   (idempotent: same doc twice = no duplicate)
  │
  ├── POST /query   → embed query → hybrid retrieval → rerank
  │                   → LLM + citation grounding → structured log
  │
  ├── GET  /health  → vector store reachable?
  │                   LLM API reachable?
  │                   Index non-empty?
  │
  └── POST /eval    → RAG Triad scorer on one test case
                      → returns {faithfulness, answer_relevance, context_relevance}
```

**Health does not equal alive.** Returning 200 when the index is empty is a lie. A healthy RAG service has a non-empty index and reachable dependencies.

Built with FastAPI, Pydantic, Qdrant (local mode), and OpenAI.

<!-- SPEAKER: The eval endpoint is the differentiator. Most teams don't ship their evaluation harness inside the service. This design means you can call /eval from a CI pipeline against a staging deployment. Time: ~3 min -->

---

## What to log on every query

```json
{
  "request_id": "uuid",
  "timestamp": "2025-03-15T09:23:45Z",
  "query": "what is the refund policy?",
  "retrieved_chunks": 5,
  "top_chunk_score": 0.847,
  "latency_breakdown": {
    "embed_ms": 48,
    "retrieve_ms": 12,
    "rerank_ms": 145,
    "generate_ms": 891,
    "total_ms": 1096
  },
  "prompt_tokens": 892,
  "completion_tokens": 143
}
```

**Without this breakdown:** "the query was slow."

**With this breakdown:** "embed_ms spiked to 400ms -- the embedding API is degraded."

Structured logs with request IDs are how you root-cause failures at 3 a.m.

<!-- SPEAKER: This is the minimum viable observability for a RAG service. Later phases (P07 Observability) add traces and metrics dashboards. This gets you started. Time: ~2 min -->

---

## Rate limit handling and the Dockerfile

**Exponential backoff with jitter:**

```
Attempt 1: immediate
Attempt 2: wait 1s + random(0-0.5s)
Attempt 3: wait 2s + random(0-0.5s)
Max retries: 3, max wait: 8s
```

Jitter prevents the thundering herd: 10 requests hitting rate limit simultaneously all retrying at the same fixed interval will rate-limit again together.

**Config management principle:** Everything you tune goes in environment variables. Never hardcode model names.

```
EMBED_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini
TOP_K=5
CHUNK_SIZE=400
```

`gpt-4o-mini` will be replaced by a better/cheaper model. If it is in the code, you need a deploy. If it is in an env var, you need a config update.

**The Dockerfile** uses multi-stage build: build stage installs all deps, final stage copies only what runs. Produces a small, secure production image.

<!-- SPEAKER: The config management principle is from production experience. Model names change every quarter. Time: ~2 min -->

---
<!-- _class: section -->

## Discussion

---

## Facilitator prompts (group of 5-15 engineers)

> **Facilitator prompt:** When would you NOT use RAG? What are the two or three conditions that make a different pattern (fine-tuning, retrieval-free prompting, text-to-SQL) clearly the better choice?

> **Facilitator prompt:** Your team has shipped naive RAG and users are mostly happy, but you are running 60% hit rate on your retrieval eval. What do you fix first and how do you decide between the options: better embedding model, smaller chunks, hybrid search, or query transformation?

> **Facilitator prompt:** How do you know when your chunks are too small? What does a retrieval trace look like when the problem is chunking versus when the problem is the embedding model?

> **Facilitator prompt:** What is your go-to eval for RAG in production? If you had to ship one metric to your monitoring dashboard today, which of the three RAG Triad components would you start with and why?

<!-- SPEAKER: Allow 10-15 minutes for discussion. The first prompt is the most generative: engineers often default to RAG for everything and benefit from thinking about the boundaries. Time: ~15 min -->

---

## Common traps and how to avoid them

**Trap 1: Debugging the prompt when retrieval is broken.**
Diagnostic: log retrieved chunks. If the right chunk is not there, it is a retrieval problem. Prompt changes cannot fix it.

**Trap 2: Picking an embedding model from a tutorial without benchmarking on your domain.**
Cost: weeks of downstream failures. Fix: run MRR@5 on 50 labeled pairs from YOUR corpus before committing.

**Trap 3: Treating "looks relevant" as an evaluation.**
Cost: cannot measure regressions, cannot justify improvements. Fix: 20 labeled pairs, run the metrics on every change.

**Trap 4: Importing a framework before understanding the raw version.**
Cost: 2 a.m. failures you cannot locate. Fix: build naive once, then choose a framework deliberately.

**Trap 5: Skipping structured logging.**
Cost: cannot root-cause production failures. Fix: log the latency breakdown per query from day one.

<!-- SPEAKER: These are all real failure patterns from production teams. Each one has a concrete cost and a concrete fix. Time: ~5 min -->

---
<!-- _class: section -->

## Exercises

---

## Three exercises to consolidate the phase

**Exercise 1: Build and break naive RAG (L05)**
Build the 5-step pipeline on a document you own (a PDF, a wiki, a set of support articles). Write 10 question/answer pairs. Run them. For each wrong answer, classify: retrieval failure or generation failure. Fix the top retrieval failure.

**Exercise 2: Measure hybrid search improvement (L06, L07)**
Add BM25 + RRF fusion to your pipeline from Exercise 1. Run your 10 eval pairs before and after. Compute Precision@5 and Recall@5 for dense-only vs. hybrid. Write two sentences: what got better and what did not change.

**Exercise 3: Run the RAG Triad (L10)**
Take 5 of your 10 eval pairs. Run the RAG Triad evaluator from Lesson 10. For each of the three metrics, identify the single lowest-scoring example. Hypothesize the root cause (retriever? chunking? prompt?). Fix one of them and re-run.

<!-- SPEAKER: These exercises build on each other in sequence. Exercise 1 output is input to Exercise 2. Exercise 2 output is input to Exercise 3. Suggest doing all three before starting Phase 03. Time: ~5 min -->

---

## What is next: Phase 03 (Tools and MCP)

**RAG is retrieval as a lookup.** You have a static corpus. You retrieve the most relevant chunk.

**Tools are retrieval as an action.** The model decides what to call, when to call it, and what to do with the result.

**Phase 03 teaches:**
- Function calling: giving models structured access to APIs and code
- MCP (Model Context Protocol): the 2025/2026 standard for tool integration
- Building tools that are safe, observable, and debuggable
- Connecting tools to agents (which build directly on the RAG patterns from this phase)

**The connection:** A ReAct agent that calls a "search" tool is doing agentic RAG (Lesson 12). An agent with memory is doing retrieval over past interactions. Everything in this phase is load-bearing for Phase 03 and beyond.

<!-- SPEAKER: Close the loop: why did we build all of this? Because agents depend on retrieval. The tool call in an agent is the naive RAG pipeline from Lesson 05. Time: ~3 min -->

---
<!-- _class: title -->

# Phase 02 complete.

**You can now build, evaluate, and ship production RAG.**

The skills that transfer to every phase that follows:
- The retrieval/generation failure split
- The RAG Triad as your measurement framework
- Structured logging from day one
- Build naive, measure, fix deliberately

**Phase 03: Tools and MCP**
*RAG is retrieval as a lookup. Tools are retrieval as an action.*

<!-- SPEAKER: Final summary. The four transferable skills are the durable takeaways regardless of which specific patterns they use. Time: ~2 min -->
