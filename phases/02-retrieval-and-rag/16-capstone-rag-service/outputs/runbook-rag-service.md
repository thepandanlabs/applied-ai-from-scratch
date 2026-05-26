---
name: runbook-rag-service
description: Deployment and operations runbook for the Phase 02 production RAG service with FastAPI, hybrid retrieval, and the RAG Triad eval
version: "1.0"
phase: "02"
lesson: "16"
tags: [rag, production, runbook, fastapi, docker, eval]
---

# RAG Service: Operations Runbook

See `service-template/README.md` for the full deployment guide. This runbook covers the operational checklist, key configuration, eval thresholds, and failure modes.

## Pre-launch checklist

- [ ] `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` set in environment
- [ ] At least one document ingested via `POST /ingest`
- [ ] Health check passes: `GET /health` returns `{"status": "healthy"}`
- [ ] RAG Triad eval run on 10+ question golden set (see thresholds below)
- [ ] Logging output verified: each log line is valid JSON

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (none) | Required for OpenAI embeddings and generation |
| `CHAT_MODEL` | `gpt-4o-mini` | LLM for generation |
| `EMBED_MODEL` | `text-embedding-3-small` | Embedding model |
| `USE_LOCAL_EMBEDDINGS` | `false` | Use sentence-transformers instead of OpenAI |
| `TOP_K` | `5` | Chunks retrieved per query |
| `CHUNK_SIZE` | `400` | Words per chunk |
| `CHUNK_OVERLAP` | `50` | Overlap words between chunks |

## Quick start

```bash
docker build -t rag-service .
docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... rag-service
```

API docs at `http://localhost:8000/docs`. Demo mode (no API key needed):

```bash
python code/main.py
```

## Eval thresholds (go/no-go)

Run `POST /eval` against your golden question set before deploying.

| Metric | Minimum | Target |
|--------|---------|--------|
| Faithfulness | 0.85 | 0.92+ |
| Answer relevance | 0.80 | 0.88+ |
| Context relevance | 0.70 | 0.80+ |

If any metric is below minimum, investigate: low faithfulness means hallucination, low context relevance means chunking or retrieval is wrong.

## Key API endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Deep health check (200=healthy, 207=degraded, 503=unhealthy) |
| `/ingest` | POST | Add a document to the vector store (idempotent) |
| `/query` | POST | Ask a question, get a grounded answer with citations |
| `/eval` | POST | RAG Triad evaluation on a single question |

## Monitoring signals

| Signal | Alert condition |
|--------|----------------|
| Query latency P95 | > 5000ms |
| Top chunk score | < 0.5 consistently |
| Generation errors | > 1% of queries |
| Rate limit events | > 5/min |

## Known failure modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| All answers low faithfulness | Context not relevant to questions | Re-check chunking strategy, increase `TOP_K` |
| Slow queries > 3s | OpenAI embedding latency | Switch to `USE_LOCAL_EMBEDDINGS=true` |
| `503 /health` | Empty index or missing API key | Ingest documents, check env vars |
| Answers lose context after restart | In-memory store not persistent | Replace with Qdrant or pgvector |

## Upgrading the vector store

The in-memory store does not survive restarts. For production, replace `InMemoryVectorStore` with the `QdrantVectorStore` adapter in `service-template/README.md`. No other code changes required.
