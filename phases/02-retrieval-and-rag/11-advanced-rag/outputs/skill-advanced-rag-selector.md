---
name: skill-advanced-rag-selector
description: Decision guide mapping RAG symptoms to the right advanced pattern - parent-doc, multi-vector, contextual retrieval, and more.
version: "1.0"
phase: "02"
lesson: "11"
tags: [rag, advanced-rag, parent-doc, multi-vector, contextual-retrieval]
---

# Skill: Advanced RAG Pattern Selector

A decision guide: given a symptom your RAG system is exhibiting, find the right advanced RAG pattern to apply and get implementation guidance.

---

## Quick Lookup: Symptom → Pattern

| Symptom | Root Cause | Pattern |
|---|---|---|
| Answers are truncated or miss context | Size mismatch: chunks too small for generation | Parent-Document Retrieval |
| Answer references "part 1" when asking about "part 2" | Context fragmentation: answer spans chunks | Parent-Document Retrieval |
| Poor recall on synonym or paraphrase queries | Dense embeddings not capturing conceptual match | Multi-Vector (summary indexing) |
| Searches for a concept but retrieves only literal matches | Vocabulary mismatch | Multi-Vector (summary + keywords) |
| Chunks start with "As noted above…" or "The previous method…" | Missing context: orphaned references | Contextual Retrieval |
| Tables/figures retrieved without their caption | Structural orphaning | Contextual Retrieval |
| All three above | Complex document structure | Contextual Retrieval + Parent-Doc |
| Queries need both precision and breadth | Hybrid use case | All three combined |

---

## Pattern 1: Parent-Document Retrieval

### When to use
- Answers require more context than a single chunk provides
- Documents have natural section boundaries (reports, chapters, specs)
- Retrieval precision is fine but answers are incomplete

### How it works
Index small child chunks (100-200 words) for precise vector matching.
Store larger parent chunks (500-1000 words) for generation.
When a child is retrieved, return its parent.

### Implementation

```python
# 1. Split documents into parent/child hierarchy at index time
def index_with_parents(documents, vectorstore, docstore, child_size=200, parent_size=800):
    """
    documents: list of Document objects (with page_content and metadata)
    vectorstore: your vector store (Chroma, Pinecone, etc.)
    docstore: InMemoryStore or persistent store for parents
    """
    parent_splitter = RecursiveCharacterTextSplitter(chunk_size=parent_size, chunk_overlap=50)
    child_splitter = RecursiveCharacterTextSplitter(chunk_size=child_size, chunk_overlap=20)

    parents = parent_splitter.split_documents(documents)
    # Assign parent IDs and split each parent into children
    for parent in parents:
        parent_id = str(uuid.uuid4())
        parent.metadata["doc_id"] = parent_id
        docstore.mset([(parent_id, parent)])

        children = child_splitter.split_documents([parent])
        for child in children:
            child.metadata["doc_id"] = parent_id  # FK to parent
        vectorstore.add_documents(children)

# 2. At retrieval: fetch child from vector store, look up parent
def retrieve_parent(query, vectorstore, docstore, top_k=3):
    child_matches = vectorstore.similarity_search(query, k=top_k * 2)
    seen_parents = set()
    parents = []
    for child in child_matches:
        parent_id = child.metadata.get("doc_id")
        if parent_id and parent_id not in seen_parents:
            parent = docstore.mget([parent_id])[0]
            if parent:
                parents.append(parent)
                seen_parents.add(parent_id)
        if len(parents) >= top_k:
            break
    return parents
```

### Parameters to tune
- `child_size`: 100-200 words. Smaller = more precise retrieval, more children per parent.
- `parent_size`: 400-1000 words. Larger = more context for generation, but increases token usage.
- `overlap`: 10-20% of chunk size. Prevents hard breaks at sentence midpoints.

### Latency impact
Zero added latency at retrieval time. Parent lookup is a key-value store read, O(1). The only cost is at index time (extra storage).

---

## Pattern 2: Multi-Vector Indexing

### When to use
- Poor recall on conceptual or paraphrase queries
- Long documents where raw dense chunks are too literal
- Multi-domain corpora where terminology varies across documents

### How it works
For each document, generate one or more additional text representations:
- **Summary**: 2-3 sentences capturing the main claim
- **Keywords**: key noun phrases and entities
- **Hypothetical questions**: questions the document would answer (HyDE variant)

Index all representations. When any representation matches, return the original document.

### Implementation

```python
def generate_representations(text: str, client: OpenAI) -> dict:
    """Generate summary and keywords for a document chunk."""
    summary_resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Summarize in 2-3 sentences:\n\n{text}"}],
        temperature=0.0, max_tokens=100,
    )
    summary = summary_resp.choices[0].message.content.strip()

    keyword_resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"List 5-8 key terms and entities (comma-separated):\n\n{text}"}],
        temperature=0.0, max_tokens=60,
    )
    keywords = keyword_resp.choices[0].message.content.strip()

    return {"summary": summary, "keywords": keywords}


def index_multi_vector(docs, embed_model, vectorstore):
    """
    Index each document with multiple representations.
    All representations point to the same doc_id.
    """
    for doc in docs:
        doc_id = str(uuid.uuid4())
        reps = generate_representations(doc.page_content)

        texts_to_index = [
            (doc.page_content, "full_text"),
            (reps["summary"], "summary"),
            (reps["keywords"], "keywords"),
        ]

        for text, rep_type in texts_to_index:
            metadata = {**doc.metadata, "doc_id": doc_id, "rep_type": rep_type}
            vectorstore.add_texts([text], metadatas=[metadata])

        # Store the full document for retrieval
        docstore.mset([(doc_id, doc)])
```

### Cost estimate
With gpt-4o-mini at $0.15/1M input tokens:
- 10,000 chunks × 300 tokens/chunk × 2 LLM calls (summary + keywords) = 6M tokens
- Cost: ~$0.90 for the indexing pass
- Recompute only when documents change

### Latency impact
Zero added retrieval latency. All representations are pre-computed at index time.

---

## Pattern 3: Contextual Retrieval

### When to use
- Chunks contain coreference ("as described above," "the previous approach," "this method")
- Hierarchical documents where chunk meaning depends on section context
- Tables, lists, or figures that are meaningless without their headings
- You want a simple, high-impact improvement with minimal architecture changes

### How it works
Before computing embeddings, run each chunk through a cheap LLM to generate a 1-2 sentence context describing where the chunk appears in the document. Prepend this context to the chunk text, then compute the embedding.

The resulting embedding captures both the chunk's meaning AND its location/context. Orphaned references become retrievable.

### The prompt

```
Here is the document:
<document>
{full_document}
</document>

Here is a chunk from this document:
<chunk>
{chunk_text}
</chunk>

Write 1-2 sentences that:
1. Describe where this chunk appears in the document (section, position, topic)
2. State what broader concept or argument it belongs to

Write only the context sentences. Do not repeat the chunk text.
```

### Implementation

```python
def contextualize_chunks(
    full_document: str,
    chunks: list[str],
    client: OpenAI,
    model: str = "gpt-4o-mini",
) -> list[str]:
    """
    Run each chunk through the context prompt and prepend the result.
    Returns enriched chunks ready for embedding.
    """
    enriched = []
    for chunk in chunks:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": CONTEXT_PROMPT.format(
                full_document=full_document[:3000],
                chunk_text=chunk,
            )}],
            temperature=0.0,
            max_tokens=80,
        )
        context = resp.choices[0].message.content.strip()
        enriched.append(f"{context}\n\n{chunk}")
    return enriched
```

### Cost estimate
With gpt-4o-mini at $0.15/1M input tokens:
- 10,000 chunks × (3,000 tokens document context + 200 tokens chunk) = 32M tokens
- Cost: ~$4.80 for the contextualization pass
- Use Claude Haiku instead (~$0.25/1M tokens) to reduce cost to ~$0.80

**Optimization:** Use prompt caching for the `<document>` section. If multiple chunks come from the same document, you pay for the document tokens only once. Anthropic's prompt caching reduces cost by ~90% for this pattern.

### Latency impact
Zero added retrieval latency. All contextualizing is done at index time.

---

## Combining Patterns

For complex documents (long, hierarchical, with cross-references):

1. Apply **Contextual Retrieval** to each chunk at index time
2. Use **Parent-Document Retrieval** on top: small contextualized children → return large parents

This combination addresses all three failure modes simultaneously:
- Size mismatch (parent-doc)
- Context fragmentation (parent-doc)
- Missing context / orphaned references (contextual retrieval)

```python
# Combined pipeline
def index_combined(full_document, chunks, parent_groups, source):
    # Step 1: contextualize chunks
    enriched_chunks = contextualize_chunks(full_document, chunks, client)

    # Step 2: assign each enriched chunk a parent_id based on grouping
    for enriched_chunk, parent_id in zip(enriched_chunks, parent_groups):
        embed_and_store(enriched_chunk, parent_id)

    # Step 3: store parents
    for parent_id, parent_text in parent_groups.items():
        docstore.mset([(parent_id, parent_text)])
```

---

## Measuring Improvement

Always measure before and after using the RAG Triad (Lesson 10):

| Pattern | Primary metric to watch | Expected improvement |
|---|---|---|
| Parent-Document | Faithfulness (more complete answers) | +10-25% |
| Multi-Vector | Context Relevance (better recall on paraphrases) | +15-30% |
| Contextual Retrieval | Context Relevance (fewer orphaned chunk misses) | +20-49% per Anthropic benchmark |

Run on the same 20-query eval set before and after. Check for regressions on the other two metrics. A change that improves faithfulness but hurts context relevance is a net loss if context relevance was already your bottleneck.

---

## Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Applying contextual retrieval but truncating the full document too aggressively | Context sentences are generic ("this chunk is from a document") | Keep at least 3,000 tokens of document context in the prompt |
| Setting child_size too large in parent-doc | Children overlap too much in meaning; retrieval precision doesn't improve | Keep children ≤ 200 words; parents 4-8x larger |
| Generating summaries at query time (not index time) | Adds 500ms+ to every query | Always pre-compute at index time |
| Not deduplicating by parent_id | Same parent returned multiple times, wasting context window | Always deduplicate on parent_id after scoring children |
