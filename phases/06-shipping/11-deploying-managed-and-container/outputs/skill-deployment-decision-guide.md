---
name: skill-deployment-decision-guide
description: decision framework and deployment checklists for managed platforms and container services
version: "1.0"
phase: "06"
lesson: "11"
tags: [deployment, railway, render, cloud-run, ecs, docker, devops]
---

# Deployment Decision Guide

## Decision tree

```
Traffic > 10k req/day OR dedicated DevOps team?
  NO  -> Managed platform (Railway / Render / Fly.io)
  YES -> Need custom VPC, compliance, or multi-region?
           NO  -> GCP Cloud Run or AWS App Runner
           YES -> AWS ECS/Fargate or GCP GKE
```

## Platform quick reference

| Platform | CLI | Time to URL | Scale to zero | Best for |
|---|---|---|---|---|
| Railway | `railway up` | 10 min | YES | demos, internal tools |
| Render | `render deploy` | 15 min | YES | APIs, background workers |
| Fly.io | `flyctl deploy` | 20 min | NO | latency-sensitive, global |
| GCP Cloud Run | `gcloud run deploy` | 30 min | YES | GCP-native stacks |
| AWS ECS | console / CDK | 2-4 hours | NO | enterprise, compliance |

## What every deployment needs

- [ ] Dockerfile that starts your service (EXPOSE the correct port)
- [ ] `GET /health` endpoint returning HTTP 200
- [ ] `PORT` env var read at startup (platforms set this)
- [ ] All secrets in platform env vars, never in code or image

## Railway deployment checklist

```bash
# 1. Install CLI
curl -fsSL https://railway.app/install.sh | sh

# 2. Log in
railway login

# 3. Initialize (run once per project)
railway init

# 4. Set secrets
railway variables set ANTHROPIC_API_KEY=sk-ant-...
railway variables set OTHER_SECRET=value

# 5. Deploy
railway up

# 6. Get your URL
railway domain

# 7. Verify health check
curl https://your-project.railway.app/health

# 8. Stream logs
railway logs
```

## Render deployment checklist

```yaml
# render.yaml (commit to project root)
services:
  - type: web
    name: ai-service
    runtime: docker
    healthCheckPath: /health
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: PORT
        value: 8000
```

```bash
# Deploy
render login
render deploy

# Logs
render logs --service ai-service --tail
```

## Dockerfile for managed platforms

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
```

## Health check endpoint (required)

```python
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

Rule: health check must return 200 within 30 seconds of container start. Do not call external services in the health check.

## Environment variables for AI services

| Variable | Where to set | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Platform dashboard (secret) | Never in code or Dockerfile |
| `PORT` | Set by platform automatically | Read with os.environ.get("PORT", "8000") |
| `ENVIRONMENT` | Platform dashboard | "production" or "staging" |
| `LOG_LEVEL` | Platform dashboard | "info" for production |

## Log patterns to watch

| Pattern | Meaning | Action |
|---|---|---|
| `Application startup complete` | Service is running | None |
| `GET /health 200` | Health check passing | None |
| `POST /generate 200` | Successful requests | None |
| `POST /generate 422` | Invalid request body | Check Pydantic schema |
| `POST /generate 500` | Unhandled exception | Check logs for traceback |
| `anthropic.AuthenticationError` | Invalid API key | Rotate key in platform secrets |
| `anthropic.RateLimitError` | Rate limit hit | Add retry with backoff (lesson 07) |

## When to move from managed to ECS/Cloud Run

Move when you need:
- VPC peering to a private database
- SOC 2 / HIPAA compliance controls
- Dedicated compute (no noisy neighbors)
- Multi-region active-active deployment
- GPU instances (Fly.io and some managed platforms now offer this)
- Custom autoscaling beyond platform presets

Do NOT move because:
- "Managed platforms are not enterprise"
- "We will need it eventually"
- "AWS is what real companies use"

Move based on a specific technical requirement you cannot meet, not reputation or anticipation.

## Post-deployment verification script

```bash
# Set BASE_URL to your deployed service URL
BASE_URL=https://your-service.railway.app python main.py
```

This runs three checks: health, generate, stream. Exits 0 on success, 1 on failure.
