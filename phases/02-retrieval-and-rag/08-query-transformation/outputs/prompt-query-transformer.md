---
name: prompt-query-transformer
description: Prompt for advising which query transformation to apply - recommends the right technique and provides the exact prompts to use.
version: "1.0"
phase: "02"
lesson: "08"
tags: [rag, query-transformation, hyde, step-back, sub-queries]
---

# Query Transformation Advisor

You are an expert in RAG system optimization specializing in query transformation.

Given a user query and retrieval system description, you will:
1. Diagnose why the raw query may underperform
2. Recommend the best transformation technique(s)
3. Provide the exact prompt(s) to use
4. Warn about any risks

---

## How to Use This Prompt

Share the following with an LLM (Claude, GPT-4, etc.):

```
I am building a RAG system. Here is my situation:

Query: [the user's actual query]
Retrieval type: [dense | sparse/BM25 | hybrid]
Domain: [medical | legal | software docs | customer support | general | other]
Corpus description: [briefly describe the document types and vocabulary level]
Current problem: [low recall | wrong results | missing exact matches | other]

Please advise which query transformation to apply and provide the implementation prompt.
```

---

## Transformation Decision Guide

The advisor uses this decision tree when analyzing your situation.

### Step 1: Identify the failure mode

| Symptom | Root cause | Best fix |
|---------|-----------|---------|
| Relevant doc has different vocabulary than query | Lexical gap / paraphrase mismatch | Rewrite or HyDE |
| Query contains informal language or pronouns | Poor query representation | Rewrite |
| Query is about a specific case, doc covers general principles | Over-specification | Step-back |
| Vague query, multiple valid interpretations | Ambiguity | Multi-query |
| Exact identifiers not being found (codes, names, numbers) | OOV terms | Switch to hybrid search (Lesson 07), not transformation |
| Long, well-formed query not being found | Embedding quality | Check embedding model (Lesson 02) |

### Step 2: Match technique to problem

```
Is the query ambiguous or vague?
├─ YES → Multi-query (covers multiple interpretations)
└─ NO
    Is the document vocabulary formal/technical and query vocabulary informal?
    ├─ YES → HyDE (generate answer-like text to bridge the vocabulary gap)
    └─ NO
        Is the query very specific but the relevant doc is at a higher abstraction level?
        ├─ YES → Step-back (retrieve background context + specific context)
        └─ NO
            Does the query contain pronouns, informal language, or missing context?
            ├─ YES → Rewrite (expand and formalize)
            └─ NO → No transformation needed (problem is likely elsewhere)
```

---

## Technique Prompts

Copy these prompts verbatim into your system. Adjust `{query}` substitution.

### Prompt 1: Query Rewriting

**When to use:** Informal queries, pronouns, abbreviated context, colloquial vocabulary.

**Latency cost:** ~200-400ms (1 LLM call)

```python
REWRITE_SYSTEM = """You are a retrieval query optimizer. Rewrite the user's question
into a more effective retrieval query that will better match relevant documents.

Rules:
- Expand abbreviations, acronyms, and pronouns with explicit nouns
- Replace informal language with technical vocabulary that would appear in documents
- Add synonyms or related terms that might appear in relevant passages
- Remove filler words and conversational phrasing
- Return ONLY the rewritten query: no explanation, no preamble"""

# Usage:
rewritten = llm.complete(
    system=REWRITE_SYSTEM,
    user=f"Original query: {query}",
    temperature=0.1,
)
results = retrieve(rewritten)
```

**Example:**
- Before: "how do I fix the auth error I kept getting?"
- After: "authentication error troubleshooting login failure token validation OAuth"

---

### Prompt 2: HyDE (Hypothetical Document Embeddings)

**When to use:** Documents are formal/technical, queries are casual; medical, legal, academic corpora.

**Latency cost:** ~300-500ms (1 LLM call + 1 embed call for the hypothetical doc)

**Risk:** If the LLM generates factually wrong content, retrieval goes in the wrong direction.

```python
HYDE_SYSTEM = """You are a technical writer. Write a short hypothetical passage (2-4 sentences)
that would directly answer the following question, written as if it appeared in the source documentation.

Requirements:
- Use technical vocabulary that would appear in the source documents
- Write as a confident factual excerpt: no hedging language
- Do not say "In this document": start with the content directly
- Be specific"""

# Usage:
hypothetical_doc = llm.complete(
    system=HYDE_SYSTEM,
    user=f"Question: {query}",
    temperature=0.2,
)
# Embed the hypothetical document, not the original query
hyde_embedding = embed(hypothetical_doc)
results = vector_search(hyde_embedding)
```

**Example:**
- Query: "is aspirin safe after a bleed?"
- HyDE doc: "Aspirin and other salicylates are generally contraindicated following hemorrhagic events due to their antiplatelet activity. In patients who have experienced intracranial hemorrhage, NSAIDs including aspirin should be avoided for a minimum of 6 weeks post-event."
- The HyDE doc embeds near the actual relevant passage.

---

### Prompt 3: Step-Back Prompting

**When to use:** Highly specific queries where the relevant context is at a higher abstraction level.

**Latency cost:** ~400-600ms (1 LLM call + 2 retrieval calls)

**Pattern:** Retrieve both step-back and original, merge results, pass both to LLM.

```python
STEPBACK_SYSTEM = """Given a specific question, generate a more general "step-back" question
that asks about the underlying principle or background concept needed to answer it.

The step-back question should:
- Ask about the broader category or principle
- Be general enough to retrieve foundational background
- NOT include the specific identifiers or values from the original question

Return ONLY the step-back question."""

# Usage:
step_back = llm.complete(
    system=STEPBACK_SYSTEM,
    user=f"Specific question: {query}",
    temperature=0.2,
)
# Retrieve with both queries, merge and deduplicate
background_chunks = retrieve(step_back, top_k=3)
specific_chunks = retrieve(query, top_k=3)
combined = deduplicate(background_chunks + specific_chunks)[:5]
```

**Example:**
- Query: "what is the renal dosing for vancomycin in a patient with CrCl 25 mL/min?"
- Step-back: "How is vancomycin dosing adjusted based on renal function?"
- Step-back retrieves the dosing guidelines table; original query retrieves the specific row.

---

### Prompt 4: Multi-Query

**When to use:** Ambiguous queries, vague queries, situations where you do not know the right vocabulary.

**Latency cost:** ~500-800ms (1 LLM call + n extra retrieval calls)

**When NOT to use:** Latency-sensitive (<200ms) or precise queries where extra phrasings add noise.

```python
MULTIQUERY_SYSTEM = """Generate {n} different phrasings of the following question.
Each phrasing should:
- Preserve the same core information need
- Use different vocabulary, emphasis, or framing
- Approach the question from a different angle

Return exactly {n} numbered queries (1. 2. etc.), one per line. No explanations."""

# Usage:
raw = llm.complete(
    system=MULTIQUERY_SYSTEM.format(n=3),
    user=f"Question: {query}",
    temperature=0.6,
)
queries = parse_numbered_list(raw)
queries.insert(0, query)  # always include original

all_chunks = []
for q in queries:
    all_chunks.extend(retrieve(q, top_k=5))

# Deduplicate by content hash
final_chunks = deduplicate_by_hash(all_chunks)[:10]
```

**Example queries generated:**
- Original: "connection issues with the API"
- Generated 1: "API client connection error troubleshooting"
- Generated 2: "network connectivity problems REST API requests"
- Generated 3: "API request timeout authentication connection refused"

---

## Combination Patterns

Some situations call for combining techniques:

### Step-back + Rewrite (for highly specialized domains)
```python
# 1. Rewrite to fix vocabulary and formality
rewritten = rewrite(query)
# 2. Apply step-back to the rewritten version
step_back = stepback(rewritten)
# 3. Retrieve all three: original, rewritten, step-back
```

### Multi-query + Rewrite (for vague queries)
```python
# 1. Rewrite the original first (improves all generated variants)
rewritten = rewrite(query)
# 2. Generate N phrasings of the rewritten version
variants = multi_query(rewritten, n=3)
```

Do not stack HyDE on top of another technique: the hypothetical document provides enough of a transformation on its own.

---

## Choosing Based on Retrieval System Type

| Retrieval type | Best transformations | Avoid |
|----------------|---------------------|-------|
| Dense only | HyDE, Rewrite |: |
| BM25 only | Rewrite (adds synonyms) | HyDE (BM25 cares about terms, not embeddings) |
| Hybrid (dense + BM25) | Rewrite, Step-back | HyDE alone (loses BM25 benefit) |
| Hybrid + reranker | All techniques |: |

---

## Latency Budget Planning

```
                    Latency added
No transformation:  0ms
Query rewrite:      +200-400ms  (1 LLM call)
HyDE:               +300-500ms  (1 LLM call + 1 embed)
Step-back:          +300-600ms  (1 LLM call + 1 extra retrieve)
Multi-query (3x):   +400-800ms  (1 LLM call + 3 retrieves)
```

For a real-time Q&A UI where users expect < 2 seconds total:
- If baseline (retrieve + generate) is ~1.2s: budget ~500ms for transformation
- Choose: rewrite or HyDE
- Avoid: multi-query unless you can parallelize the N retrieval calls

For an async research assistant where latency < 10s is fine:
- All techniques are available
- Multi-query with deduplication gives the highest recall

---

## Measuring Success

After implementing a transformation, validate with your eval set (Lesson 06):

```python
# Before
baseline = evaluate_retrieval(dataset, k=5)
# recall@5 = 0.62

# After adding rewrite
transformed = evaluate_retrieval(transformed_dataset, k=5)
# recall@5 = 0.74  → +12 percentage points
```

A transformation is worth keeping if:
1. Recall@5 improves by at least 5 percentage points
2. Precision@5 does not drop by more than the recall gain
3. The latency cost is within budget

A transformation should be dropped if:
1. Recall improvement is < 3 percentage points (noise, not signal)
2. Precision drops significantly (transformation introducing hallucinated terms)
3. The LLM calls fail or time out frequently in production
