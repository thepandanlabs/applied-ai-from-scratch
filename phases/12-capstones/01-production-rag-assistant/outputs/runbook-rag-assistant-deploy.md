---
name: runbook-rag-assistant-deploy
description: Deployment and operations runbook for the production RAG assistant capstone
version: "1.0"
phase: "12"
lesson: "01"
tags: [rag, deployment, runbook, hybrid-search, fastapi, sse]
---

# Runbook: Production RAG Assistant

## Build and Run

### Local (uv)

```bash
# Create environment
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Set required environment variables
export ANTHROPIC_API_KEY=sk-ant-...
export CORPUS_ROOT=/path/to/repo/root   # default: 4 levels above main.py

# Start service (indexes corpus at startup, typically 5-30s for full repo)
uvicorn main:app --reload --port 8000
```

### Docker

```bash
# Build
docker build -t rag-assistant ./code

# Run with corpus mounted from host
docker run \
  -p 8000:8000 \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v /path/to/repo:/corpus:ro \
  rag-assistant
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | - | Anthropic API key |
| `CORPUS_ROOT` | No | repo root (auto-detected) | Path to directory containing .md files |

## Health Check

```bash
curl http://localhost:8000/health
# {"status": "ok", "docs_indexed": 847, "index_ready": true}
```

## Querying the Service

### Streaming (SSE)

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What phases cover evaluation?", "top_k": 5}' \
  --no-buffer
```

Response events:
- `{"type": "citations", "data": [...]}` - retrieved source list
- `{"type": "chunk", "text": "..."}` - streaming text token
- `{"type": "done", "latency_ms": 1200, "input_tokens": 2100, "output_tokens": 180}` - completion stats

### Off-topic query (rejected)

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the best sourdough recipe?"}'
# HTTP 400: Query is outside curriculum scope
```

## Corpus Re-indexing

Re-index when:
- New phases or lessons are added to the curriculum
- Existing lesson content is substantially updated
- The service is restarted (indexing is automatic at startup)

```bash
# Trigger re-index without restarting
curl -X POST http://localhost:8000/reindex
# {"docs_indexed": 891}
```

Expected re-indexing time: 5-60s depending on corpus size and machine.

## RAG Triad Evaluation

Run the 20-query golden set against the live service:

```bash
pip install ragas datasets

python - <<'EOF'
import json
import requests
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_precision, faithfulness

GOLDEN_QUERIES = [
    "What phases cover evaluation?",
    "Which lesson teaches BM25 retrieval?",
    "What is the difference between Phase 04 agents and Phase 05 evaluation?",
    "What tools are covered in Phase 03?",
    "What does the FDE skillset phase cover?",
    # ... add 15 more with known reference answers
]

questions, answers, contexts = [], [], []
for q in GOLDEN_QUERIES:
    resp = requests.post("http://localhost:8000/query",
                         json={"question": q, "top_k": 5},
                         stream=True)
    answer_text = ""
    ctx_list = []
    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode()
        if line.startswith("data: ") and line != "data: [DONE]":
            event = json.loads(line[6:])
            if event["type"] == "chunk":
                answer_text += event["text"]
            elif event["type"] == "citations":
                ctx_list = [c["source"] for c in event["data"]]
    questions.append(q)
    answers.append(answer_text)
    contexts.append(ctx_list)

dataset = Dataset.from_dict({
    "question": questions,
    "answer": answers,
    "contexts": contexts,
})
results = evaluate(dataset, metrics=[answer_relevancy, context_precision, faithfulness])
print(results)
EOF
```

Target scores: answer_relevancy >= 0.85, context_precision >= 0.75, faithfulness >= 0.90.

## Monitoring Setup

Key metrics to track per query (logged to stdout in JSON-structured format):

- `latency_ms` - total response latency. Alert if p95 > 5000ms
- `input_tokens` - cost driver. Alert if average > 3000 tokens
- `output_tokens` - secondary cost driver
- Guardrail rejection rate: count HTTP 400 responses to `/query`

Cost estimate at Haiku pricing (as of mid-2025):
- Average query: ~2000 input tokens + ~150 output tokens = ~$0.0012
- 1000 queries/day = ~$1.20/day

## Known Failure Modes

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| Empty index at startup | `/health` returns `docs_indexed: 0` | Check `CORPUS_ROOT` path and file permissions |
| Citations do not match claims | High faithfulness score but user complaints | Reduce `CHUNK_SIZE` to 256, reduce `top_k` to 3 |
| Slow first response | >10s latency on first query | Index build is synchronous; add readiness probe that waits for `index_ready: true` |
| Off-topic queries bypass guardrail | Unrelated answers | Expand `CURRICULUM_KEYWORDS` set; lower cosine similarity threshold from 0.85 to 0.80 |
| Retrieval misses obvious chunks | Correct answer is in corpus but not retrieved | Increase `top_k` to 8; review chunking size (may be too large) |

## Rollback Procedure

The service is stateless. To roll back:
1. `docker stop rag-assistant`
2. `docker run` with previous image tag
3. The corpus is mounted read-only; no corpus state to roll back
