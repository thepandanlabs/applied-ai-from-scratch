---
name: prompt-rag-framework-chooser
description: Decision prompt for evaluating whether to use a RAG framework and which one fits your use case - covers LlamaIndex vs LangChain tradeoffs.
version: "1.0"
phase: "02"
lesson: "15"
tags: [llamaindex, langchain, framework-selection, decision-matrix]
---

# Prompt: RAG Framework Decision Tool

Use this prompt to evaluate whether to use a framework and which one fits your RAG use case. Paste it into any LLM and answer the questions.

---

## The Decision Prompt

```
You are a senior AI engineer helping me decide whether to use a RAG framework (LlamaIndex or LangChain/LCEL) or implement my pipeline in raw Python.

I will describe my use case. Ask me clarifying questions if needed, then give me a specific recommendation with justification.

My use case: [DESCRIBE YOUR USE CASE HERE]

Evaluate me on these dimensions:

1. CORPUS SCALE
   - How many documents? How many chunks (estimated)?
   - Static or frequently updated?
   - One document type or many?

2. QUERY COMPLEXITY
   - Simple Q&A (retrieve → answer)?
   - Conditional routing (route based on query type)?
   - Multi-step reasoning (chain of retrievals)?
   - Conversational (needs message history)?

3. INTEGRATION NEEDS
   - Does RAG need to live inside a larger agent?
   - Does it need tool calling, memory, or multi-agent coordination?
   - Streaming required?

4. TEAM + MAINTENANCE
   - Will non-ML engineers maintain this?
   - How often will the pipeline logic change?
   - Can you tolerate framework version updates?

5. DEBUGGING REQUIREMENTS
   - Do you need full visibility into retrieved chunks and prompts?
   - Is production debugging a priority?

Based on my answers, recommend ONE of:
  A) Raw Python (numpy + openai)
  B) LlamaIndex
  C) LangChain/LCEL
  D) LangGraph (if agent orchestration is needed)

Justify your recommendation by citing which specific features the framework provides that I cannot easily build raw. If raw is recommended, say explicitly what the framework would add that I don't need.
```

---

## Decision Matrix (Reference)

| Dimension | Raw | LlamaIndex | LangChain/LCEL | LangGraph |
|-----------|-----|------------|----------------|-----------|
| Corpus < 10k docs | Best | Overkill | Overkill | Overkill |
| Corpus > 100k docs | Possible | Good | Possible | N/A |
| Multiple document types | Manual | Built-in loaders | Many loaders | N/A |
| Hierarchical indexing | Manual | Native | Manual | N/A |
| Knowledge graph | Manual | `KnowledgeGraphIndex` | LangGraph needed | N/A |
| Simple Q&A | Best | OK | OK | N/A |
| Conditional routing | Manual if/else | Limited | `RunnableBranch` | `StateGraph` |
| Conversational RAG | Manual history | Chat mode | `ConversationChain` | Full state |
| RAG inside agent | Wrap as tool | Wrap as tool | `Tool` integration | Native |
| Streaming | Manual | Supported | Native | Native |
| Debugging ease | Best | Medium | Hard | Hard |
| Version stability | N/A (you own it) | Monthly changes | Weekly changes | Weekly changes |

---

## Framework-Specific Earning Conditions

### LlamaIndex earns its complexity when:

- You need to ingest 5+ document types (PDFs, HTML, Notion, GitHub, Slack)
- You need `SummaryIndex` for long document summarization
- You need `KnowledgeGraphIndex` for entity relationship queries
- You need managed chunk metadata (source, page number, section, relationships between chunks)
- You need multi-index queries (query one index, filter by metadata, fall back to another)

**LlamaIndex does NOT earn its complexity when:**
- Your data is plain text or JSON you already parse
- You only need semantic search + LLM call
- You need conversational routing or agent orchestration

### LangChain/LCEL earns its complexity when:

- You need to compose multiple LLM calls conditionally (`if retrieved docs match condition X, do Y else Z`)
- You're building a conversational system with message history and session management
- RAG is one tool in a larger agent alongside web search, code execution, etc.
- You need streaming responses with delta tokens piped to a frontend
- Your pipeline has 3+ stages with conditional branching between them

**LangChain does NOT earn its complexity when:**
- You just need retrieve-then-generate with no branching
- Your team doesn't know LangChain and would spend days learning the abstraction model
- Your pipeline is stable and doesn't need the flexibility LCEL provides

### Raw Python earns its position when:

- You need deterministic, debuggable behavior and full visibility into every step
- The corpus is under 50k chunks and doesn't require complex metadata
- You're building a prototype, eval harness, or proof-of-concept
- You want zero framework version risk
- Your team knows Python better than they know LlamaIndex/LangChain

---

## Anti-Pattern Checklist

Before importing any framework, check that you're NOT doing this:

- [ ] Importing the framework on day 1 before knowing what will break in the raw version
- [ ] Using the framework as a shortcut to avoid understanding the pipeline
- [ ] Assuming the framework's defaults are right for your use case
- [ ] Not verifying the escape hatch (can you get raw chunks out of the framework?)
- [ ] Skipping an eval set: frameworks do not improve retrieval quality automatically
- [ ] Pinning to "latest" instead of a specific version

---

## Migration Path

If you start raw and need to migrate:

```
Raw → LlamaIndex:
  1. Wrap your existing chunks as LlamaIndex Document objects
  2. Load into VectorStoreIndex with a pre-existing vector store (qdrant, pgvector)
  3. Keep your existing embedding function: LlamaIndex accepts custom embedders

Raw → LangChain:
  1. Wrap your existing vector store as a LangChain VectorStore
  2. Use .as_retriever() to get a LangChain Retriever
  3. Build an LCEL chain around your existing retriever

You do NOT have to re-embed or re-index when migrating -
the embeddings are the same regardless of framework.
```
