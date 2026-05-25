# RAG Service: Deployment Guide

A production-ready Retrieval Augmented Generation service built with FastAPI. Supports document ingestion, hybrid retrieval, LLM generation, evaluation, and health monitoring.

---

## Quick Start

```bash
# Install dependencies
pip install fastapi uvicorn openai sentence-transformers numpy pydantic

# Configure
export OPENAI_API_KEY=sk-...

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Or run the standalone demo (no server, no browser needed)
python main.py
```

Open the API docs at `http://localhost:8000/docs`.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (none) | OpenAI API key. Required unless `USE_LOCAL_EMBEDDINGS=true` |
| `CHAT_MODEL` | `gpt-4o-mini` | OpenAI chat model for generation |
| `EMBED_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `LOCAL_EMBED_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model (used when `USE_LOCAL_EMBEDDINGS=true`) |
| `USE_LOCAL_EMBEDDINGS` | `false` | Set to `true` to use sentence-transformers instead of OpenAI embeddings |
| `TOP_K` | `5` | Number of chunks retrieved per query |
| `CHUNK_SIZE` | `400` | Words per chunk |
| `CHUNK_OVERLAP` | `50` | Overlap words between consecutive chunks |
| `MAX_RETRIES` | `3` | LLM API retry limit on rate errors |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `PORT` | `8000` | Port to listen on (used with `--server` flag or Docker) |

---

## API Reference

### `GET /health`

Deep health check. Returns `200` (healthy), `207` (degraded), or `503` (unhealthy).

```json
{
  "status": "healthy",
  "request_id": "abc123",
  "checks": {
    "vector_store": {"status": "ok", "chunk_count": 142},
    "llm": {"status": "configured", "model": "gpt-4o-mini"},
    "embeddings": {"status": "ok", "mode": "openai", "model": "text-embedding-3-small"}
  }
}
```

A `degraded` status means the service is running but a dependency is not fully functional (e.g., empty index, no LLM key).

---

### `POST /ingest`

Ingest a document into the vector store. Idempotent: same content can be ingested multiple times without creating duplicates.

**Request:**
```json
{
  "content": "Your document text here...",
  "doc_id": "my-doc-001",
  "metadata": {"source": "knowledge-base", "author": "alice"},
  "chunk_size": 400,
  "chunk_overlap": 50
}
```

`doc_id` is optional (auto-generated UUID if omitted). `chunk_size` and `chunk_overlap` override environment defaults for this document.

**Response:**
```json
{
  "doc_id": "my-doc-001",
  "chunks_added": 8,
  "was_duplicate": false,
  "doc_hash": "a1b2c3d4e5f6a7b8",
  "request_id": "xyz789"
}
```

If `was_duplicate: true`, `chunks_added` will be 0: the document was already indexed.

---

### `POST /query`

Ask a question. Returns an LLM-generated answer grounded in the indexed documents.

**Request:**
```json
{
  "query": "What is the refund policy?",
  "top_k": 5
}
```

`top_k` is optional; defaults to the `TOP_K` environment variable.

**Response:**
```json
{
  "answer": "According to [Source 1: policy-doc], refunds are processed within 30 days...",
  "sources": ["policy-doc", "faq-doc"],
  "retrieved_chunks": [
    {"text": "Refunds are processed within...", "score": 0.891, "source": "policy-doc"}
  ],
  "latency_breakdown": {
    "embed_ms": 48,
    "retrieve_ms": 5,
    "generate_ms": 723,
    "total_ms": 776
  },
  "tokens": {
    "prompt_tokens": 847,
    "completion_tokens": 121
  },
  "request_id": "def456"
}
```

---

### `POST /eval`

Run the RAG Triad evaluation on a question. Scores faithfulness, answer relevance, and context relevance.

**Request:**
```json
{
  "question": "What is the refund policy?",
  "expected_answer": "Refunds within 30 days"
}
```

`expected_answer` and `context` are optional. If `context` is omitted, the service retrieves context automatically.

**Response:**
```json
{
  "question": "What is the refund policy?",
  "answer": "Refunds are processed within 30 days according to [Source 1]...",
  "scores": {
    "faithfulness": 0.95,
    "answer_relevance": 0.90,
    "context_relevance": 0.85
  },
  "retrieved_chunks": [...],
  "request_id": "ghi789"
}
```

---

## Ingesting Documents

### Single document
```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Our refund policy: customers can return items within 30 days for a full refund.",
    "doc_id": "policy-refund",
    "metadata": {"section": "policies", "version": "v2"}
  }'
```

### Bulk ingestion (Python script)
```python
import requests
import os

DOCS_DIR = "./documents"
API = "http://localhost:8000"

for filename in os.listdir(DOCS_DIR):
    if filename.endswith(".txt"):
        with open(os.path.join(DOCS_DIR, filename)) as f:
            content = f.read()
        resp = requests.post(f"{API}/ingest", json={
            "content": content,
            "doc_id": filename.replace(".txt", ""),
            "metadata": {"filename": filename},
        })
        data = resp.json()
        print(f"{filename}: +{data['chunks_added']} chunks (duplicate: {data['was_duplicate']})")
```

---

## Running Evaluations

Run the full eval harness against the live service:

```python
import requests

API = "http://localhost:8000"

eval_set = [
    {"question": "What is the refund policy?", "expected": "30 days"},
    {"question": "How do I contact support?", "expected": "email support@..."},
    # Add 10+ pairs before going to production
]

results = []
for item in eval_set:
    resp = requests.post(f"{API}/eval", json={"question": item["question"]})
    scores = resp.json()["scores"]
    results.append(scores)
    print(f"Q: {item['question'][:50]}")
    print(f"  Faithfulness: {scores['faithfulness']:.2f}")
    print(f"  Answer Rel:   {scores['answer_relevance']:.2f}")
    print(f"  Context Rel:  {scores['context_relevance']:.2f}")

# Aggregate
avg = {
    k: sum(r[k] for r in results) / len(results)
    for k in ["faithfulness", "answer_relevance", "context_relevance"]
}
print("\nAverage scores:")
for k, v in avg.items():
    print(f"  {k}: {v:.2f}")

# Production acceptance thresholds:
# faithfulness > 0.85
# answer_relevance > 0.80
# context_relevance > 0.70
```

---

## Running with Docker

### Build the image
```bash
docker build -t rag-service .
```

### Run locally
```bash
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -e TOP_K=5 \
  -e CHAT_MODEL=gpt-4o-mini \
  rag-service
```

### Run without an OpenAI API key (local embeddings only)
```bash
docker run -p 8000:8000 \
  -e USE_LOCAL_EMBEDDINGS=true \
  rag-service
# Note: generation requires OPENAI_API_KEY; local mode supports retrieval only
```

### Docker Compose (recommended for local dev)
```yaml
version: "3.9"
services:
  rag-service:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - TOP_K=5
      - CHAT_MODEL=gpt-4o-mini
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## Deploying to Cloud Platforms

### Railway
```bash
railway init
railway up
railway env set OPENAI_API_KEY=sk-...
```

### Render
1. Connect your GitHub repo
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add `OPENAI_API_KEY` as an environment variable

### Fly.io
```bash
fly launch --name rag-service
fly secrets set OPENAI_API_KEY=sk-...
fly deploy
```

### Google Cloud Run
```bash
gcloud builds submit --tag gcr.io/PROJECT/rag-service
gcloud run deploy rag-service \
  --image gcr.io/PROJECT/rag-service \
  --set-env-vars OPENAI_API_KEY=sk-... \
  --allow-unauthenticated \
  --region us-central1
```

Note: The in-memory vector store does not survive container restarts. For persistent production deployment, replace it with Qdrant Cloud or pgvector.

---

## Observability

The service emits structured JSON logs to stdout. Every log line is valid JSON with a consistent schema:

```json
{"ts": "2024-12-01T09:23:45Z", "event": "query", "request_id": "abc123",
 "query": "what is RAG?", "retrieved_chunks": 5, "top_chunk_score": 0.847,
 "latency_breakdown": {"embed_ms": 48, "retrieve_ms": 12, "generate_ms": 891, "total_ms": 951},
 "tokens": {"prompt_tokens": 892, "completion_tokens": 143}, "answer_length": 512, "model": "gpt-4o-mini"}
```

Parse these logs with any JSON-aware log aggregation tool (Datadog, Grafana Loki, CloudWatch Insights).

### Key metrics to track

| Metric | Log field | Alert if |
|--------|-----------|----------|
| Query latency P95 | `latency_breakdown.total_ms` | > 5000ms |
| Embedding latency | `latency_breakdown.embed_ms` | > 500ms |
| Generation latency | `latency_breakdown.generate_ms` | > 3000ms |
| Retrieval score | `top_chunk_score` | < 0.5 consistently |
| Rate limit events | `event == "rate_limit_backoff"` | > 5/min |
| Error rate | `event == "query_error"` | > 1% of queries |

---

## Upgrading the Vector Store

The `InMemoryVectorStore` class exposes three methods: `add()`, `search()`, `count()`. Replace with Qdrant:

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

class QdrantVectorStore:
    def __init__(self, collection: str = "rag", host: str = "localhost", port: int = 6333):
        self.client = QdrantClient(host=host, port=port)
        self.collection = collection
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            self.client.get_collection(self.collection)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )

    def add(self, text: str, vector, metadata: dict) -> str:
        point_id = str(uuid.uuid4())
        self.client.upsert(self.collection, points=[
            PointStruct(id=point_id, vector=vector.tolist(), payload={"text": text, **metadata})
        ])
        return point_id

    def search(self, query_vec, top_k: int) -> list[dict]:
        hits = self.client.search(self.collection, query_vector=query_vec.tolist(), limit=top_k)
        return [{"text": h.payload["text"], "metadata": h.payload, "score": h.score} for h in hits]

    def count(self) -> int:
        return self.client.count(self.collection).count
```

Swap `vector_store = InMemoryVectorStore()` for `vector_store = QdrantVectorStore()` and nothing else changes.
