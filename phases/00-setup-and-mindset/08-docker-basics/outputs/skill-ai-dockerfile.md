---
name: skill-ai-dockerfile
description: Minimal Dockerfile template for a Python AI app with annotated best practices for layer caching and secret injection
version: "1.0"
phase: "00"
lesson: "08"
tags: [docker, deployment, python, secrets]
---

# Skill: AI App Dockerfile

A production-ready Dockerfile template for any Python AI app that calls an external model API. Annotated with the reasoning behind each decision.

---

## The Template

```dockerfile
FROM python:3.12-slim

# WORKDIR creates the directory and sets it as the default for all subsequent
# RUN, COPY, and CMD instructions. Use /app by convention.
WORKDIR /app

# COPY requirements BEFORE application code.
# Docker builds in layers. If requirements.txt hasn't changed, Docker reuses
# the cached layer including the pip install. Putting COPY main.py first
# would invalidate the cache on every code change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code last (changes most often).
COPY . .

# NEVER set API keys here. They become part of the image layer history.
# Use runtime injection: docker run -e KEY=$KEY image-name
# Or for orchestration: Kubernetes secrets, AWS Secrets Manager, etc.

CMD ["python", "main.py"]
```

---

## How to Use This Template

**1. Customize the base image** if you need a different Python version:

```dockerfile
FROM python:3.11-slim   # older deps that haven't tested 3.12
FROM python:3.12        # full image if slim fails during pip install
```

**2. Add a non-root user** for production security (optional but recommended):

```dockerfile
RUN useradd -m appuser
USER appuser
```

**3. Add health check** for services (not batch scripts):

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
```

**4. For FastAPI services**, change CMD to:

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Build and Run Commands

```bash
# Build
docker build -t my-ai-app .

# Run with API key injected from host shell
docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY my-ai-app

# Run a service with port mapping
docker run -d -p 8000:8000 -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY my-ai-app

# Debug: enter a shell inside the container
docker run -it --entrypoint /bin/bash my-ai-app

# Check running containers
docker ps

# View logs
docker logs <container_id>
docker logs $(docker ps -lq)   # last container

# Stop a container
docker stop <container_id>
```

---

## Layer Caching Rules

| Change made | Layers rebuilt |
|-------------|---------------|
| Edit `main.py` only | Only the final `COPY . .` layer |
| Add a dependency to `requirements.txt` | pip install and all layers after it |
| Change the base image | All layers |

Keep the layers that change least at the top. Keep the layers that change most at the bottom.

---

## Secret Injection Hierarchy

From least to most secure. Use the highest level your infrastructure supports.

```
Level 1: docker run -e KEY=$KEY              (fine for local dev)
Level 2: docker run --env-file .env          (never commit .env to git)
Level 3: Kubernetes Secrets mounted as env   (staging/prod)
Level 4: AWS/GCP Secrets Manager at runtime  (production)
Level 5: Vault dynamic secrets               (high-security production)
```

Never bake secrets into a Docker image. Every layer is permanent and readable with `docker history --no-trunc`.

---

## Common Failures and Fixes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError` inside container | Package not in `requirements.txt` | Add it and rebuild |
| `KeyError: ANTHROPIC_API_KEY` | Key not passed at `docker run` | Add `-e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY` |
| Slow rebuild on every code change | `COPY . .` before `RUN pip install` | Move pip install before `COPY . .` |
| Image is 2GB+ | Using full `python:3.12` base | Switch to `python:3.12-slim` |
| `pip install` fails with missing headers | Slim image lacks build tools | Add `RUN apt-get install -y build-essential` before pip |
