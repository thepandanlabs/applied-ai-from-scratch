---
name: skill-ai-app-dockerfile
description: Production-ready multi-stage Dockerfile template for a Python FastAPI AI service with layer caching, non-root user, health check, and secret injection pattern
version: "1.0"
phase: "06"
lesson: "05"
tags: [docker, fastapi, multi-stage, production, packaging]
---

# Skill: Production Dockerfile for an AI App

Use this template when packaging any Python FastAPI AI service into a Docker image.

## Usage

1. Copy `Dockerfile`, `requirements.txt`, and `.dockerignore` into your service root.
2. Replace `main.py` with your application entry point (adjust `COPY main.py .` if needed).
3. Update `requirements.txt` with your exact pinned dependencies.
4. Adjust the `HEALTHCHECK` path to match your service's health endpoint.
5. Build and run:

```bash
docker build -t my-service:latest .
docker run -p 8000:8000 --env ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY my-service:latest
```

## Dockerfile Template

```dockerfile
# Multi-stage Dockerfile for a Python FastAPI AI service.

# ----- BUILD STAGE -----
FROM python:3.12-slim AS build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Layer order: requirements before code so pip install is cached on code-only changes
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# ----- RUNTIME STAGE -----
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/uvicorn /usr/local/bin/uvicorn

RUN useradd -m -u 1000 appuser

COPY main.py .

USER appuser

# Non-secret config only. Secrets injected at runtime via --env.
ENV PORT=8000 WORKERS=1 LOG_LEVEL=info MODEL=claude-3-5-haiku-20241022 MAX_TOKENS=1024

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --log-level ${LOG_LEVEL}
```

## Decision Checklist

| Decision | Rule |
|----------|------|
| `COPY requirements.txt` before `COPY . .` | Preserves pip install cache on code changes |
| Multi-stage (`AS build` + `AS runtime`) | Keeps build tools out of the final image |
| `USER appuser` | Never run the service as root |
| `HEALTHCHECK` | Required for orchestrators to detect readiness |
| `ENV` contains no secrets | Secrets injected at `docker run` with `--env` |
| `.dockerignore` excludes `.env` and `.git` | Prevents secrets and large files from entering the build context |

## Secret Injection Patterns

```bash
# Single key (dev/CI)
docker run --env ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY my-service:latest

# Env file (never commit this file)
docker run --env-file .env.local my-service:latest

# Docker secrets (Swarm/Kubernetes)
docker secret create anthropic_key ./api_key.txt
docker run --secret anthropic_key my-service:latest
```

## Verify No Secrets in Image

```bash
docker history my-service:latest
docker inspect my-service:latest | grep -i "api_key\|secret\|token"
# Both commands should return nothing sensitive
```
