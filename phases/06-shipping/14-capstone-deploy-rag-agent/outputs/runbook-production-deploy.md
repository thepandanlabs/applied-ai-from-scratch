---
name: runbook-production-deploy
description: Operational runbook for the Phase 06 RAG capstone service covering startup, config, health checking, log reading, and rollback
version: "1.0"
phase: "06"
lesson: "14"
tags: [runbook, deployment, production, rag, rollback, operations]
---

# Production Runbook: RAG Capstone Service

This runbook covers: startup, configuration, health checking, reading logs, and rollback. A new engineer should be able to follow this without help from the original author.

---

## Prerequisites

- Docker installed
- `ANTHROPIC_API_KEY` available (from Anthropic console)
- `manifests.yaml` registered (see Setup)
- Service deployed to Railway, Render, or local Docker

---

## Setup (First Deploy)

### 1. Register the initial manifest

```bash
# From the code/ directory
pip install -r requirements.txt
python main.py register

# Expected output:
# Manifest registered: v1.0.0
#   model_id:    claude-3-5-haiku-20241022
#   config_hash: <8 hex chars>
#   deployed_at: <ISO timestamp>
# Manifest written to: /path/to/manifests.yaml
```

`manifests.yaml` must exist before the service can start. Commit it to git.

### 2. Build the Docker image

```bash
cd code/
docker build -t rag-capstone:v1.0.0 .
```

### 3. Set environment variables

Required:
```bash
ANTHROPIC_API_KEY=sk-ant-...      # required
```

Optional:
```bash
OPENAI_API_KEY=sk-...              # fallback model
MODEL_ID=claude-3-5-haiku-20241022 # default: haiku
MAX_TOKENS=512                      # default: 512
TEMPERATURE=0.3                     # default: 0.3
TOP_K=5                             # default: 5
MAX_RETRIES=3                       # default: 3
CIRCUIT_BREAKER_THRESHOLD=5         # default: 5
CIRCUIT_BREAKER_TIMEOUT_SECONDS=60  # default: 60
LOG_LEVEL=INFO                      # default: INFO
```

### 4. Start the service

Local:
```bash
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  rag-capstone:v1.0.0
```

Railway:
```bash
railway up
railway variables set ANTHROPIC_API_KEY=sk-ant-...
```

---

## Startup Verification

After every deploy, run these checks in order:

### Check 1: Service is running

```bash
curl http://localhost:8000/health
```

Expected response (200):
```json
{
  "status": "ok",
  "manifest_id": "v1.0.0",
  "prompt_version": "v1.0",
  "model_id": "claude-3-5-haiku-20241022",
  "config_hash": "<8 hex chars>",
  "deployed_at": "<ISO timestamp>",
  "circuit_breaker": "closed",
  "store_size": 0
}
```

If response is 500 with "No active manifest": the `manifests.yaml` file is not present in the container. Run `python main.py register` and rebuild the image.

If response is 422: the `ANTHROPIC_API_KEY` environment variable is missing.

### Check 2: Startup logs contain manifest

```bash
docker logs <container_id> 2>&1 | grep "SERVICE STARTUP" -A 8
```

Expected output:
```
INFO: === SERVICE STARTUP ===
INFO: manifest_id:     v1.0.0
INFO: prompt_version:  v1.0
INFO: model_id:        claude-3-5-haiku-20241022
INFO: config_hash:     <hash>
INFO: deployed_at:     <timestamp>
INFO: deployed_by:     setup
INFO: flag:            prompt-v1.1-rollout mode=shadow pct=10%
INFO: === STARTUP COMPLETE ===
```

If you do not see this block, the lifespan hook did not run. Check for startup errors before the `STARTUP COMPLETE` line.

### Check 3: Ready probe

```bash
curl http://localhost:8000/ready
```

Expected: `{"status": "ready"}` (200)
If 503: circuit breaker is open. Check logs for API errors.

---

## Config Changes

### To update a config value

1. Update the environment variable in your platform (Railway dashboard, `.env` file, etc.)
2. Register a new manifest with the updated config hash:

```python
from main import ManifestRegistry, VersionManifest, hash_config
from pathlib import Path
from datetime import datetime, timezone

registry = ManifestRegistry(Path("manifests.yaml"))
new_config = {
    "temperature": 0.5,   # changed from 0.3
    "max_tokens": 512,
    "top_k": 5,
    "retries": 3,
}
manifest = VersionManifest(
    manifest_id="v1.1.0",
    prompt_version="v1.0",
    model_id="claude-3-5-haiku-20241022",
    config_hash=hash_config(new_config),
    deployed_at=datetime.now(timezone.utc).isoformat(),
    deployed_by="your-name",
    notes="Increased temperature to 0.5",
)
registry.register(manifest)
```

3. Commit `manifests.yaml` and redeploy.

### To change the model ID

Same process as config change, but update the `model_id` field in the manifest. Only use pinned IDs:

- `claude-3-5-haiku-20241022` (fast, cheap)
- `claude-3-5-sonnet-20241022` (balanced)
- `claude-opus-4-5` (most capable)

Never use aliases: `claude-haiku-latest`, `claude-sonnet-latest`.

---

## Reading Logs

### Find what was deployed at a specific time

```bash
# Search by startup block
docker logs <container_id> 2>&1 | grep "=== SERVICE STARTUP ===" -A 10
```

### Find circuit breaker events

```bash
docker logs <container_id> 2>&1 | grep -E "Circuit|circuit"
```

### Find shadow mode comparisons

```bash
docker logs <container_id> 2>&1 | grep "shadow_b"
```

### Find errors

```bash
docker logs <container_id> 2>&1 | grep "ERROR"
```

### Tail live logs

```bash
docker logs -f <container_id>
# Railway:
railway logs --tail
```

---

## Rollback Procedure

Use this when responses have degraded and you need to revert to a previous manifest.

### Step 1: Identify the target manifest

```bash
cat manifests.yaml | grep manifest_id
# Lists all registered manifests in order
```

### Step 2: Call the rollback endpoint

```bash
curl -X POST http://localhost:8000/rollback \
  -H "Content-Type: application/json" \
  -d '{"manifest_id": "v1.0.0"}'
```

Expected: `{"rolled_back_to": "v1.0.0", "note": "Restart the service..."}`

### Step 3: Restart the service

The rollback only updates `manifests.yaml`. The running service must restart to load the new current manifest.

```bash
# Docker restart
docker restart <container_id>

# Railway
railway up
```

### Step 4: Verify the rollback

```bash
curl http://localhost:8000/health | python -m json.tool
# Confirm: "manifest_id" matches the target you rolled back to
```

Expected startup log after restart:
```
INFO: manifest_id:     v1.0.0    <-- the rolled-back version
```

### Step 5: Notify your team

Post in your incident channel:
```
Rolled back to manifest v1.0.0 (prompt=v1.0, model=claude-3-5-haiku-20241022).
Reason: <brief description>
Health check confirmed at <time>.
```

---

## Ingest Documents

```bash
# Ingest a text passage
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your document content here",
    "source": "my-document.txt"
  }'

# Expected: {"status": "accepted", "source": "my-document.txt"}
# Embedding runs in the background. Check /health for updated store_size.
```

**Note:** The in-memory vector store is cleared on every service restart. For a persistent RAG store, replace the in-memory dict with pgvector or Qdrant (Phase 02, Lesson 03).

---

## Feature Flag Management

### Check current flag config

```bash
# Flag config is in main.py: ROLLOUT_FLAG definition
# There is no live update endpoint - change requires redeploy
grep "ROLLOUT_FLAG" main.py
```

### Promotion ladder

| Step | Config change | Signal to check before promoting |
|------|---------------|----------------------------------|
| Shadow | `mode=SHADOW, rollout_pct=0` | Shadow logs show no regressions |
| Canary 10% | `mode=CANARY, rollout_pct=10` | No increase in errors or escalations |
| Canary 50% | `mode=CANARY, rollout_pct=50` | Eval metrics stable or improving |
| Full | Remove flag, use variant_b directly | Stable for 48h at 50% |

---

## Emergency Contacts and Escalation

1. Check `/health` first - includes circuit breaker state and manifest info
2. Check `/ready` - returns 503 with detail if circuit breaker is open
3. Check startup logs for the manifest that was active when the incident started
4. Roll back to last known-good manifest if behavior changed after a deploy
5. If the circuit breaker is open and not recovering, check the Anthropic status page: https://status.anthropic.com

---

## Deployment History

Update this table after every deploy:

| Date | Manifest ID | Deployed By | Notes |
|------|-------------|-------------|-------|
| 2025-01-15 | v1.0.0 | setup | Initial production deploy |
