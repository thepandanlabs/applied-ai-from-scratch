---
name: skill-chunking-strategy-picker
description: >
  Expert advisor for choosing a chunking strategy given document type and
  retrieval use case. Includes a decision table, failure mode checklist,
  and diagnostic questions for identifying whether retrieval failures are
  caused by chunking. Use when a user needs to chunk a new document type
  or debug poor RAG retrieval quality.
version: "1.0"
phase: "02"
lesson: "04"
tags:
  - chunking
  - rag
  - retrieval
  - text-splitting
  - document-processing
---

# Skill: Chunking Strategy Picker

## Purpose

You are an applied AI engineering advisor specializing in document chunking for RAG systems. When a user needs to choose a chunking strategy or debug retrieval quality, use this skill to guide them to the right approach.

---

## Step 1: Gather Requirements

Ask about (or infer from context):

1. **Document type**: What is the structure and typical length?
   - Markdown/HTML with clear headers (docs, wikis, READMEs)
   - Prose without headers (articles, books, reports)
   - Structured forms (contracts, policies, specifications)
   - Short items (support tickets, product reviews, Q&A pairs)
   - Code (source files: see Lesson 14 for AST-aware chunking)

2. **Query type**: What are users asking?
   - Specific fact lookups ("what is the refund policy?") → precision matters
   - Broad conceptual questions ("explain the architecture") → more context per chunk
   - Comparison queries ("compare plan A vs B") → may span multiple sections

3. **Document length**: Typical document length in tokens
   - Short (< 512 tokens): may not need chunking
   - Medium (512–4K tokens): most strategies apply
   - Long (> 4K tokens): semantic or late chunking gains importance

4. **Embedding model context window**: Does your model support long context?
   - Most: 512 tokens (all-MiniLM, mpnet, etc.)
   - Long-context: 8K+ (jina-embeddings-v2, voyage-4)

5. **Has there been a retrieval failure?**: If so, what does it look like?
   - "Answer spans a chunk boundary" → smaller chunks + overlap OR sentence-window
   - "Retrieved chunks have the right topic but wrong content" → semantic chunking
   - "Early chunks in a long doc retrieve poorly" → late chunking
   - "Header context lost in sub-sections" → markdown-aware

---

## Decision Table

| Document Type | Query Type | Length | Recommended Strategy |
|---|---|---|---|
| Markdown docs, wikis, READMEs | Fact lookup per section | Any | Markdown-aware |
| Prose (articles, blog posts) | General questions | Short–medium | Recursive char split |
| Prose with multiple distinct topics | Topic-based questions | Medium–long | Semantic chunking |
| Contracts, policies, legal | Clause-level lookups | Long | Fixed-size + overlap (wide) OR Sentence-window |
| Technical manuals, books | Conceptual questions | Very long | Late chunking |
| Q&A datasets, support tickets | Short, specific | Short | Sentence-window |
| Mixed content type | Unknown | Any | Recursive (baseline), then evaluate |
| Code files | Function/class lookup | Medium | AST-aware (Lesson 14) |

---

## Strategy Reference

### Strategy 1: Fixed-Size with Overlap
```
chunk_size=200 tokens, overlap=40 tokens (20%)
```
- Simple, deterministic, fast
- Always use as a baseline for comparison
- **Fails when:** sentence boundaries matter (legal, medical, technical precision)

### Strategy 2: Recursive Character Splitter
```
separators=["\n\n", "\n", ". ", "! ", "? ", " "], max_chars=800, overlap=100
```
- Default choice for unknown document types
- Respects natural language breaks in priority order
- **Fails when:** document has meaningful structure (headers) that it ignores

### Strategy 3: Markdown-Aware
```
split on H1/H2/H3, include header in each chunk
```
- Preserves document structure; each chunk is self-contained with its header
- **Fails when:** sections are very long (combine with recursive split for the body)
- **Key property:** the header is included in every chunk from that section → embedding knows the section topic

### Strategy 4: Sentence-Window
```
window_size=2 (2 sentences before + 2 after as context)
```
- Embed individual sentences for high precision retrieval
- Return the surrounding window to the LLM for context
- **Fails when:** sentences are very short (< 20 tokens): not enough signal
- **Best for:** Q&A systems where precision matters more than coverage

### Strategy 5: Semantic Chunking
```
threshold=0.75 (split when adjacent sentence similarity drops below 0.75)
```
- Detects topic boundaries using embedding similarity
- Produces variable-size chunks that align with conceptual boundaries
- **Fails when:** document is thematically consistent throughout (single-topic docs)
- **Cost:** embeds every sentence once during chunking; ~2x indexing time

### Strategy 6: Late Chunking
```
Requires: long-context model (jina-embeddings-v2 or similar)
Base boundaries: any strategy (typically sentence or recursive)
```
- Each chunk's embedding is computed from full-document token representations
- Early chunks carry context from later parts of the document
- **Fails when:** model's context window is smaller than the document (truncation loses context)
- **Best for:** long documents where early sections reference later content

---

## Diagnostic: Is My Retrieval Failure a Chunking Problem?

Run through this checklist before changing embedding models or retrieval logic:

**Step 1: Retrieve and inspect**
For 5 queries where you know the correct answer, retrieve top-3 chunks and read them.
- Do any chunks contain a complete, self-contained answer? → If NO: chunking is wrong
- Do chunks end mid-sentence? → Fixed-size with too-small chunk size
- Do chunks contain multiple unrelated topics? → Fixed-size with too-large chunk size

**Step 2: Check answer span coverage**
```python
def answer_in_top_k(answer_text, retrieved_chunks):
    return any(answer_text.lower() in chunk.lower() for chunk in retrieved_chunks)

coverage = sum(answer_in_top_k(ans, get_top_k(q)) for q, ans in pairs) / len(pairs)
# < 70%: chunking is splitting answers across boundaries
```

**Step 3: Check chunk size distribution**
```python
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
lengths = [len(enc.encode(c)) for c in all_chunks]
# Healthy: roughly bell-shaped around your target size
# Red flags:
#   - Many chunks at 1-10 tokens: over-splitting bug
#   - All chunks at exactly max_size: separator never triggered
#   - Bimodal (tiny + huge): inconsistent document formatting
```

**Step 4: Check header preservation**
For Markdown docs: do retrieved chunks include the section header?
If not, the LLM may not know which section the answer came from.
→ Use markdown-aware chunking that includes headers in each chunk.

---

## Common Chunking Mistakes

**Mistake 1: Using character count when you should use token count**

Character count is inconsistent across languages and tokenizers. A 400-character chunk in English is ~100 tokens; in Chinese it might be 200 tokens. Use `tiktoken` or your model's tokenizer for accurate chunk sizing.

**Mistake 2: Using zero overlap**

Without overlap, the last sentence of chunk K and the first sentence of chunk K+1 share no content. Queries that reference information near the boundary return incomplete chunks. Use at least 10-20% overlap.

**Mistake 3: Not including document context in chunks**

A chunk that just says "See section 3 for details" has no meaningful embedding. Include enough context in each chunk so it can be understood independently. Markdown-aware chunking solves this by including the header.

**Mistake 4: Chunking before cleaning**

If your documents contain HTML tags, boilerplate headers/footers, navigation menus, or copyright notices, these pollute your chunks and degrade embedding quality. Clean first, then chunk.

**Mistake 5: Same strategy for all document types**

A support ticket corpus and a legal contract corpus need different strategies. Evaluate per document type.

---

## Quick Recommendation Script

When a user describes their use case, map it to a strategy recommendation:

```python
def recommend_strategy(
    has_headers: bool,
    doc_length_tokens: int,
    query_type: str,  # "fact_lookup", "conceptual", "comparison"
    has_retrieval_failures: bool,
    failure_type: str = "",  # "boundary_split", "topic_mix", "early_chunk_poor"
) -> str:
    if has_retrieval_failures:
        if failure_type == "boundary_split":
            return "sentence_window (overlap=2) OR fixed_size with larger overlap (40%)"
        if failure_type == "topic_mix":
            return "semantic_chunking (threshold=0.7-0.8)"
        if failure_type == "early_chunk_poor":
            return "late_chunking (requires long-context embedding model)"

    if has_headers:
        return "markdown_aware"

    if doc_length_tokens > 4000:
        return "semantic_chunking OR late_chunking"

    if query_type == "fact_lookup":
        return "sentence_window (window_size=2)"

    # Default
    return "recursive_char_split (max_chars=600-800, overlap=10-15%)"
```
