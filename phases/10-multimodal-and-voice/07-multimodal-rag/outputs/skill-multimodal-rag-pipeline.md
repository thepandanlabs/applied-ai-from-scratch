---
name: skill-multimodal-rag-pipeline
description: Architecture comparison and implementation reference for multimodal RAG pipelines combining text and image retrieval with vision language models.
version: "1.0"
phase: "10"
lesson: "07"
tags: [rag, multimodal, vision, retrieval, embedding, early-fusion]
---

# Skill: Multimodal RAG Pipeline

## Architecture Comparison

| Approach | How it works | Index cost | Query quality | Best fit |
|----------|-------------|------------|---------------|----------|
| Late Fusion | Embed text and image captions separately, retrieve from both indexes, combine results | Low (caption-only embeddings) | Medium - depends on caption quality | Large corpora with existing captions |
| Early Fusion | VLM describes images at index time, embed descriptions as text; pass original images at query time | Medium - one VLM call per image | High - rich descriptions plus grounding images | Most production cases |
| Native Multimodal Embedding | CLIP/ColPali embeds images directly into shared text-image space | Low - one embedding per image | High for visual similarity queries | Scanned docs, image-first retrieval |

### Decision Guide

```
Start here:
  Is your corpus scanned (unreliable OCR)?
    YES -> Native multimodal embedding (ColPali)
    NO ->
      Do you have good existing image captions?
        YES -> Late fusion (cheap, fast to implement)
        NO ->
          Do you have < 50,000 images?
            YES -> Early fusion (recommended default)
            NO -> Consider late fusion with VLM-generated captions batched offline
```

---

## Indexing Cost Estimates

### Early Fusion (Claude Haiku image description)

Assumptions:
- Claude 3.5 Haiku: $0.80/M input tokens, $4.00/M output tokens
- Average image: ~1,600 input tokens (image + prompt)
- Average description: ~300 output tokens

Cost per image: (1600 * $0.00000080) + (300 * $0.000004) = $0.00128 + $0.00120 = **~$0.0025/image**

| Corpus size | Est. indexing cost |
|-------------|-------------------|
| 1,000 images | ~$2.50 |
| 10,000 images | ~$25 |
| 100,000 images | ~$250 |

With prompt caching on the system/instruction text, reduce input token cost by ~70%: ~$0.0015/image.

### Re-indexing (incremental updates)

Only re-index changed pages. Track page content hash to detect changes:

```python
import hashlib

def page_hash(image_b64: str, text: str) -> str:
    content = image_b64[:100] + text[:200]
    return hashlib.sha256(content.encode()).hexdigest()[:16]
```

---

## Implementation Pattern: Early Fusion

### Index-time pipeline

```python
# 1. Extract pages from PDF
pages = extract_pdf_pages("manual.pdf")  # returns list of {text, image_b64, page_num}

# 2. For each page with an image, generate a rich description
for page in pages:
    if page["image_b64"]:
        page["image_description"] = describe_image(
            image_b64=page["image_b64"],
            context_text=page["text"][:300],
        )

# 3. Create chunks from text and image descriptions
chunks = []
for page in pages:
    # Text chunk
    chunks.append({
        "id": f"p{page['page_num']}-text",
        "text": page["text"],
        "image_b64": None,
        "source": f"page {page['page_num']}",
    })
    # Image chunk (description as text, original image stored separately)
    if page.get("image_description"):
        chunks.append({
            "id": f"p{page['page_num']}-image",
            "text": page["image_description"],
            "image_b64": page["image_b64"],  # stored for context assembly
            "source": f"page {page['page_num']} - diagram",
        })

# 4. Embed all chunks
texts = [c["text"] for c in chunks]
embeddings = embed_batch(texts)  # your embedding model
for chunk, emb in zip(chunks, embeddings):
    chunk["embedding"] = emb
```

### Query-time pipeline

```python
# 1. Embed query (text embedding - same model as index)
query_embedding = embed(query)

# 2. Retrieve top-K chunks by cosine similarity
results = vector_search(query_embedding, index, top_k=5)

# 3. Assemble interleaved text + image context
content = []
for chunk in sorted(results, key=lambda c: c["source"]):
    content.append({"type": "text", "text": f"[{chunk['source']}]\n{chunk['text']}"})
    if chunk["image_b64"]:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": chunk["image_b64"]}
        })

# 4. Add question
content.append({"type": "text", "text": f"Question: {query}"})

# 5. Call Claude with multimodal context
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=512,
    messages=[{"role": "user", "content": content}]
)
```

---

## Storage Design for Image Assets

### Recommended layout

```
{storage_bucket}/
  documents/
    {doc_id}/
      pages/
        {page_num}/
          text.txt          # extracted text
          image.png         # page image or extracted diagram
          description.txt   # VLM-generated description (cached)
          embedding.npy     # precomputed embedding vector
          metadata.json     # {doc_id, page_num, hash, indexed_at}
```

### Metadata schema

```json
{
  "doc_id": "manual-pressure-system-v3",
  "page_num": 12,
  "content_hash": "a3f7c2d1",
  "indexed_at": "2025-05-26T10:00:00Z",
  "has_image": true,
  "image_description_tokens": 287,
  "embedding_model": "text-embedding-3-small"
}
```

---

## Retrieval Quality Metrics

### Visual golden set construction

1. Select 20-30 pages with important diagrams or images
2. Write 1-2 queries per page that a real user might ask
3. Label each query with the expected page(s) (ground truth)
4. Run retrieval and measure:

| Metric | Definition | Target |
|--------|-----------|--------|
| Hit@1 | Correct page in top 1 result | > 60% |
| Hit@3 | Correct page in top 3 results | > 80% |
| Hit@5 | Correct page in top 5 results | > 90% |
| MRR | Mean reciprocal rank of first correct result | > 0.70 |

### Text-only vs multimodal comparison

Run both pipelines on the same visual golden set. A well-implemented early fusion pipeline typically shows:

- Visual queries (diagram/image specific): +20-40% hit@3 improvement
- Text-only queries (no visual component): similar or slight decrease (-2-5%)
- Overall: +10-20% hit@3 improvement on mixed corpus

---

## Context Window Budget for Images

Each image passed to Claude consumes tokens. Plan accordingly:

| Image size | Approximate token cost |
|-----------|----------------------|
| 200x150px | ~800 tokens |
| 512x512px | ~1,600 tokens |
| 1024x768px | ~3,200 tokens |
| Full page (A4 scan) | ~5,000-8,000 tokens |

For a Claude model with 200K context window:
- At 3,200 tokens/image: budget for ~60 images per query
- Practical limit: 3-5 images per query for reliable reasoning quality
- Resize large images before passing to Claude: max 1024px on the long edge is sufficient

---

## Common Failure Modes

| Failure | Cause | Fix |
|---------|-------|-----|
| Visual queries not retrieving diagrams | Image descriptions are too short/generic | Improve description prompt: ask for component names, spatial relationships, part numbers |
| Retrieved images are irrelevant | Description embeds poorly in text space | Use a domain-specific embedding model or add keyword anchors to descriptions |
| Context window overflow with images | Too many images retrieved | Reduce top_k, resize images, or filter to highest-scoring image chunk only |
| Descriptions miss key information | VLM does not have context | Always pass surrounding page text when generating descriptions |
| Index drift over time | Re-indexing skips updated pages | Use content hash to detect changes at page level |
