---
name: runbook-multimodal-feature-deploy
description: Full deployment runbook for the Phase 10 capstone multimodal document support assistant - Docker build, environment variables, health checks, monitoring, and failure mode mitigations.
version: "1.0"
phase: "10"
lesson: "09"
tags: [deployment, docker, fastapi, multimodal, runbook, capstone]
---

# Runbook: Multimodal Feature Deployment

## Service Overview

The multimodal document support assistant provides two endpoints:
- `POST /upload` - accepts PDF files, extracts content, builds multimodal index
- `POST /query` - accepts doc_id + question, returns answer with page citations
- `GET /health` - health check for load balancer and monitoring

## Prerequisites

- Docker 24+ installed
- `ANTHROPIC_API_KEY` available (for live mode)
- Optional: `OPENAI_API_KEY` for production text embeddings

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes (live mode) | - | Claude API key for extraction and Q&A |
| `OPENAI_API_KEY` | No | - | For text-embedding-3-small; falls back to demo embedding if not set |
| `DEMO_MODE` | No | false | Set to `true` to run with synthetic data (no API keys needed) |
| `MAX_UPLOAD_MB` | No | 20 | Maximum PDF upload size in megabytes |
| `LOG_LEVEL` | No | INFO | Python logging level: DEBUG, INFO, WARNING, ERROR |

---

## Docker Build and Run

### Build

```bash
cd phases/10-multimodal-and-voice/09-capstone-multimodal-feature/code

docker build -t multimodal-assistant:1.0 .
```

### Run (demo mode, no API keys)

```bash
docker run -p 8000:8000 \
  -e DEMO_MODE=true \
  multimodal-assistant:1.0
```

### Run (live mode)

```bash
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e OPENAI_API_KEY=sk-... \
  -e DEMO_MODE=false \
  -e MAX_UPLOAD_MB=20 \
  -e LOG_LEVEL=INFO \
  multimodal-assistant:1.0
```

### Verify startup

```bash
curl http://localhost:8000/health
# Expected:
# {"status":"ok","version":"1.0.0","demo_mode":false,"documents_loaded":0}
```

---

## API Usage Examples

### Upload a document

```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@manual.pdf" \
  -H "Accept: application/json"

# Response:
# {
#   "doc_id": "a3f7c2d1e8b4",
#   "page_count": 24,
#   "doc_type": "digital",
#   "chunk_count": 51,
#   "message": "Indexed 24 pages (3847ms)"
# }
```

### Query a document

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "a3f7c2d1e8b4",
    "question": "What does the pressure relief valve assembly look like?"
  }'

# Response:
# {
#   "answer": "The pressure relief valve assembly is shown in Figure 2.1 on page 12...",
#   "citations": [
#     {"page": 12, "relevance_score": 0.847, "has_image": true, "text_preview": "PRV cross-section..."},
#     {"page": 11, "relevance_score": 0.712, "has_image": false, "text_preview": "The PRV assembly mounts..."}
#   ],
#   "policy_checked": true,
#   "latency_ms": 2340.5
# }
```

### Demo mode: query pre-loaded document

```bash
# In demo mode, the demo document is loaded at startup
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "demo-pressure-system-manual",
    "question": "What is the default relief pressure?"
  }'
```

---

## Deploy to Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project (run from repo root)
railway init

# Set the Dockerfile path (Railway detects this automatically)
# Ensure the Dockerfile is in the service directory

# Deploy
railway up

# Set environment variables
railway variables set ANTHROPIC_API_KEY=sk-ant-...
railway variables set OPENAI_API_KEY=sk-...
railway variables set DEMO_MODE=false
railway variables set MAX_UPLOAD_MB=20

# Get service URL
railway status
```

Railway auto-deploys on every `git push` to main after initial setup.

---

## Deploy to Render

Create `render.yaml` in the repository root:

```yaml
services:
  - type: web
    name: multimodal-doc-assistant
    env: docker
    dockerfilePath: ./phases/10-multimodal-and-voice/09-capstone-multimodal-feature/code/Dockerfile
    plan: starter
    healthCheckPath: /health
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: DEMO_MODE
        value: "false"
      - key: MAX_UPLOAD_MB
        value: "20"
```

Set `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` in the Render dashboard (Environment tab) after first deploy.

---

## Health Check Endpoint

The `/health` endpoint returns service status. Use for:
- Load balancer health check (configure on port 8000, path `/health`)
- Uptime monitoring (ping every 60 seconds)
- Deployment readiness probe

Expected healthy response:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "demo_mode": false,
  "documents_loaded": 3
}
```

Unhealthy indicators:
- HTTP 5xx response: service crashed
- `documents_loaded` unexpectedly 0 in demo mode: startup failed

---

## Monitoring Setup

### Minimum monitoring (any provider)

1. **Uptime check:** ping `/health` every 60 seconds. Alert on non-200 response.
2. **Response time:** track `latency_ms` from query responses. Alert if P95 > 10s.
3. **Error rate:** count HTTP 4xx vs 5xx in logs. Alert if 5xx rate > 1%.
4. **Content policy events:** count `Content policy violation` log lines. Spike may indicate attack.

### Langfuse integration (optional, recommended)

Add to `main.py` for per-request tracing:

```python
from langfuse import Langfuse

langfuse = Langfuse()

# In /query handler, wrap with trace:
trace = langfuse.trace(name="document-query", input={"question": req.question})
# ... processing ...
trace.update(output={"answer": answer, "citation_count": len(citations)})
```

Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` environment variables.

---

## Content Policy Configuration

The content policy uses a hardcoded injection pattern list. To customize:

1. Edit `INJECTION_PATTERNS` in `main.py` before building the Docker image
2. Or externalize patterns to an environment variable or config file

Current default patterns block:
- "ignore all previous"
- "ignore previous instructions"
- "disregard all"
- "you are now in"
- "output your system prompt"
- "reveal system prompt"
- "override instructions"
- "new instructions:"

False positive risk: legitimate queries containing "new instructions" or "override" will be blocked. Refine patterns based on your document corpus vocabulary.

---

## Known Failure Modes and Mitigations

### Upload fails on scanned PDFs

**Symptom:** POST /upload returns 422 "Could not extract content"
**Cause:** pdf2image not installed, or Poppler missing
**Fix:** Verify Dockerfile includes `poppler-utils` in apt-get install. Check container logs for import errors.

### Image descriptions missing from index

**Symptom:** Visual queries return low-relevance results
**Cause:** `describe_image_live` failed silently; falling back to empty descriptions
**Fix:** Check logs for `Image description failed` errors. Verify `ANTHROPIC_API_KEY` is set correctly.

### Memory growth with many uploads

**Symptom:** Container memory usage grows indefinitely
**Cause:** `DOCUMENT_INDEX` in-memory dict never evicts entries
**Fix:** Implement LRU eviction (max 50 documents) or migrate to pgvector/Qdrant for production.

### Content policy false positives

**Symptom:** Legitimate queries blocked with 400 error
**Cause:** Overly broad injection patterns
**Fix:** Review blocked queries in logs. Remove or narrow patterns that match normal user vocabulary.

### High query latency (> 10 seconds)

**Symptom:** `latency_ms` in query response exceeds 10,000ms
**Cause:** Large images in context, slow Claude response, or embedding bottleneck
**Fix:** Reduce retrieved `top_k` from 5 to 3. Resize images to max 1024px before indexing. Enable prompt caching for the system prompt.

---

## Rollback Procedure

1. Identify the last good Docker image tag (check CI artifact registry)
2. Deploy the previous image:

```bash
# Railway
railway rollback

# Docker (self-hosted)
docker stop multimodal-assistant
docker run -d -p 8000:8000 \
  -e ANTHROPIC_API_KEY=... \
  multimodal-assistant:PREVIOUS_TAG

# Render: use "Manual Deploy" with previous commit in Render dashboard
```

3. Verify health: `curl http://your-domain/health`
4. The in-memory index is not persistent: users must re-upload documents after rollback.

---

## Scaling Considerations

This capstone uses in-memory storage, suitable for development and small teams. For production scale:

| Concern | In-memory (capstone) | Production recommendation |
|---------|---------------------|--------------------------|
| Document storage | Python dict | pgvector (Phase 02 pattern) |
| Image storage | Base64 in dict | S3 or GCS |
| Embeddings | numpy arrays | pgvector or Qdrant |
| Concurrency | Single worker | Multiple uvicorn workers + Redis queue for uploads |
| Persistence | Lost on restart | pgvector + S3 (durable) |

See Phase 06 runbook-production-deploy.md for the full production scaling guide.
