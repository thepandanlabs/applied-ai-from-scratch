# Phase 02 · Retrieval & RAG

RAG is the most widely deployed AI pattern in production today. This phase teaches you to build it from the ground up: starting with raw vectors and ending with a FastAPI service you can deploy, debug, and improve. Every lesson adds one thing and shows you when it breaks.

---

## What you'll build

- A semantic search service backed by dense + sparse hybrid retrieval
- A text-to-SQL pipeline that lets users query structured data in natural language
- A codebase Q&A system that understands functions and classes, not just lines
- A retrieval evaluation harness (the RAG Triad: faithfulness, relevance, context quality)
- A production RAG API with structured logging, rate limit handling, and a Dockerfile

---

## Why RAG before agents?

Agents depend on retrieval. A ReAct agent that calls a "search" tool is calling a RAG system. An agent with memory is doing retrieval over past interactions. If you don't understand what makes retrieval fail: wrong chunking, mismatched embedding vocabulary, poor reranking: you cannot debug an agent that gives wrong answers. RAG is the foundation. Build it solidly before building on top of it.

---

## The 16 lessons

| # | Lesson | Reusable Artifact | Time |
|---|--------|-------------------|------|
| 01 | Embeddings Intuition | Visualization script: plot 2D PCA of word clusters | ~45 min |
| 02 | Embedding Models | Model comparison: OpenAI vs local sentence-transformers | ~50 min |
| 03 | Vector Stores | In-memory store → Qdrant migration walkthrough | ~55 min |
| 04 | Chunking Strategies | Chunking benchmark: fixed vs semantic vs AST | ~60 min |
| 05 | Naive RAG | 4-function RAG pipeline (no framework) | ~60 min |
| 06 | Retrieval Metrics | Retrieval evaluator: precision@k, recall@k, MRR | ~55 min |
| 07 | Hybrid Search | BM25 + dense hybrid retriever with RRF fusion | ~65 min |
| 08 | Query Transformation | Query expansion and HyDE pipeline | ~60 min |
| 09 | Citation Grounding | Span-level citation verifier | ~55 min |
| 10 | RAG Evaluation | RAG Triad scorer: faithfulness + relevance + context | ~70 min |
| 11 | Advanced RAG | Re-ranking + parent-document retrieval | ~75 min |
| 12 | Agentic RAG | Iterative retrieval with a reasoning loop | ~80 min |
| 13 | Structured Retrieval | Text-to-SQL pipeline: schema → SQL → answer | ~70 min |
| 14 | RAG Over Codebase | AST-based codebase indexer + symbol search | ~75 min |
| 15 | RAG Frameworks | Side-by-side: Raw vs LlamaIndex vs LangChain | ~80 min |
| 16 | Capstone RAG Service | Production FastAPI service with eval endpoint | ~120 min |

---

## Prerequisites

Before starting this phase, you need:

- Python 3.10+ and `pip`
- Basic fluency with Python (functions, dicts, list comprehensions)
- An OpenAI API key (or set `USE_LOCAL_EMBEDDINGS=true` in lessons 13–16 to run without one)
- Familiarity with making LLM API calls: covered in Phase 01, Lesson 04 (or spend 30 minutes on the [OpenAI quickstart](https://platform.openai.com/docs/quickstart))
- Lesson 01 of this phase introduces embeddings from scratch; no prior ML background is assumed

---

## The thread through this phase

The phase starts at the bottom of the stack and builds upward.

**Lessons 01–04: The primitives.** What is a vector? What model makes them? Where do you store them? How do you split text without destroying meaning? These are the four decisions that determine whether everything downstream works.

**Lessons 05–06: Build naive, then measure.** Lesson 05 is the complete RAG pipeline in ~80 lines. Lesson 06 is the eval harness that tells you when it's broken. The order matters: build it first, then measure what's wrong, then fix it.

**Lessons 07–09: Fix the common failures.** Hybrid search improves recall when keyword matching matters. Query transformation handles when users phrase queries differently from how documents were written. Citation grounding prevents the model from fabricating sources.

**Lessons 10–12: Evaluate, then advance.** Lesson 10 builds the RAG Triad eval. Lessons 11–12 implement the techniques (re-ranking, agentic retrieval) that the eval will show you to need.

**Lessons 13–15: The variants.** Not all data is documents. Lesson 13 handles structured data (SQL). Lesson 14 handles code. Lesson 15 shows what frameworks give you and what they cost: so you can choose deliberately rather than by default.

**Lesson 16: Production.** Everything connects. The capstone is a deployable service that includes the eval endpoint, structured logging, rate limit handling, and a Dockerfile.

---

## Setup

Install the core dependencies:

```bash
pip install openai sentence-transformers qdrant-client numpy fastapi uvicorn pydantic
```

For framework lessons (15 only):

```bash
pip install llama-index llama-index-llms-openai llama-index-embeddings-openai \
            langchain langchain-openai langchain-community faiss-cpu
```

Set your API key:

```bash
export OPENAI_API_KEY=sk-...
```

To run lessons 13–16 without an OpenAI API key (local embeddings, no LLM generation):

```bash
export USE_LOCAL_EMBEDDINGS=true
# Note: lessons that use LLM generation for answers will skip that step
```

---

## How each lesson is structured

Every lesson follows the same seven-beat format:

1. **Learning Objectives**: what you will know by the end
2. **The Problem**: the production failure that motivates this lesson
3. **The Concept**: the idea, with diagrams
4. **Build It**: step-by-step implementation with full code
5. **Use It**: how it connects to a larger system
6. **Ship It**: what artifact you have at the end
7. **Evaluate It**: how to know it's working in production (not just locally)

Each lesson also includes a `quiz.json`, runnable `code/main.py`, and a reusable artifact in `outputs/` (skill card, decision prompt, or service template).

---

## Where to start

If you're new to embeddings: start at **Lesson 01**.

If you already understand embeddings and want to build a RAG system: start at **Lesson 05** (naive RAG) and refer back to lessons 01–04 as needed.

If you want to understand how to evaluate a RAG system you already have: start at **Lesson 06** (retrieval metrics) and **Lesson 10** (RAG Triad).

If you need to query structured data: go directly to **Lesson 13** (text-to-SQL).

If you need to build a deployable service: go directly to **Lesson 16** (capstone) and work backwards to the components you need.
