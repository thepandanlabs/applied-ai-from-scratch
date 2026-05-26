# Docker Image for an AI App

> Layer order is not style: it is the difference between a 2-second build and a 3-minute build.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 06 lessons 01-04 (FastAPI AI service), basic Docker familiarity
**Time:** ~60 min
**Learning Objectives:**
- Write a multi-stage Dockerfile that separates dependency installation from application code
- Explain why layer order determines cache hit rate and why it matters at CI scale
- Run a Dockerized FastAPI AI service passing secrets as environment variables at runtime
- Verify a health check using `docker inspect`
- Write a `.dockerignore` that prevents credentials and large files from entering the image

---

## The Problem

You have a working FastAPI AI service on your laptop. A colleague clones the repo and gets a different Python version, a missing system library, and an import error you have never seen. Your staging environment runs fine; production throws a segfault because the base image has a different glibc. The on-call engineer cannot reproduce the bug because they are on macOS and the server is Linux.

This is not a Python problem. It is a packaging problem. Every AI service that reaches production must answer one question with certainty: "Given this exact image, on any machine that can run Docker, does the service start and respond correctly?" If the answer is anything other than "yes," you have not shipped yet.

The failure mode that catches most teams: the Dockerfile works, but it rebuilds from scratch every time because `COPY . .` appears before `RUN pip install -r requirements.txt`. With 30 dependencies and an anthropic SDK, that install takes 90 seconds. On a CI pipeline with 20 commits a day, that is 30 minutes of wasted build time daily. The fix is a single line reorder. Knowing why it works requires understanding Docker layers.

---

## The Concept

### Docker Layers and the Build Cache

A Docker image is a stack of read-only layers. Each instruction in a Dockerfile (`FROM`, `RUN`, `COPY`, `ENV`) creates one layer. Docker caches every layer by its instruction and its inputs. When a layer's inputs change, Docker invalidates that layer and every layer after it.

```
┌─────────────────────────────────────────────────────────────┐
│  FROM python:3.12-slim                  layer 1 (base OS)   │
├─────────────────────────────────────────────────────────────┤
│  RUN apt-get install ...                layer 2 (sys deps)  │
├─────────────────────────────────────────────────────────────┤
│  COPY requirements.txt .                layer 3 (req file)  │
├─────────────────────────────────────────────────────────────┤
│  RUN pip install -r requirements.txt    layer 4 (packages)  │  <-- cache hit unless requirements.txt changed
├─────────────────────────────────────────────────────────────┤
│  COPY . .                               layer 5 (app code)  │  <-- always changes on code edit
├─────────────────────────────────────────────────────────────┤
│  CMD ["uvicorn", "app:app", ...]        layer 6 (entrypoint)│
└─────────────────────────────────────────────────────────────┘
```

If you put `COPY . .` before `RUN pip install`, changing a single line in `main.py` invalidates the pip install layer. All 90 seconds run again. With the correct order, a code change only re-runs layers 5 and 6. Layers 1-4 hit the cache.

### Multi-Stage Build

A multi-stage build uses two `FROM` statements. The first stage (build) installs compilers and dev tools needed to build wheels. The second stage (runtime) copies only the compiled packages into a minimal image, leaving the build tools behind.

```
┌─────────────────────────────┐    ┌─────────────────────────────┐
│  BUILD STAGE                │    │  RUNTIME STAGE              │
│  python:3.12                │    │  python:3.12-slim           │
│                             │    │                             │
│  apt-get install gcc        │    │  (no gcc, no build tools)   │
│  pip install -r reqs.txt    │ -> │  COPY --from=build ...      │
│  (builds C extensions)      │    │  non-root user              │
│                             │    │  HEALTHCHECK                │
│  ~600 MB                    │    │  ~150 MB                    │
└─────────────────────────────┘    └─────────────────────────────┘
```

The runtime image is 4x smaller, has fewer installed packages (smaller attack surface), and starts faster because there is less to load.

### What Goes Where

| Concern | Approach |
|---------|----------|
| Non-secret config (port, workers, log level) | `ENV` in Dockerfile or `--env` at run time |
| Secrets (API keys, tokens) | `--env` or `--env-file` at `docker run`; never in the image |
| Source code | `COPY . .` in the runtime stage |
| Compiled packages | `COPY --from=build /usr/local/lib/python3.12/site-packages` |
| Running user | Non-root (`RUN useradd -m appuser && USER appuser`) |
| Health signal | `HEALTHCHECK CMD curl -f http://localhost:8000/health` |

---

## Build It

### Step 1: The FastAPI Service

Create the minimal FastAPI app that the Dockerfile will package. It expects `ANTHROPIC_API_KEY` from the environment and exposes a `/generate` endpoint plus a `/health` endpoint.

```python
# code/main.py
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import anthropic

app = FastAPI(title="AI App", version="1.0")
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("MODEL", "claude-3-5-haiku-20241022")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))


class GenerateRequest(BaseModel):
    prompt: str


class GenerateResponse(BaseModel):
    text: str
    model: str
    input_tokens: int
    output_tokens: int


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be empty")
    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": req.prompt}],
    )
    return GenerateResponse(
        text=msg.content[0].text,
        model=msg.model,
        input_tokens=msg.usage.input_tokens,
        output_tokens=msg.usage.output_tokens,
    )
```

### Step 2: requirements.txt

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
anthropic==0.40.0
pydantic==2.9.2
```

Pin exact versions. Unpinned requirements mean the image built today may differ from the image built next month after a dependency releases a breaking change.

### Step 3: .dockerignore

```
.env
.env.*
__pycache__/
*.pyc
*.pyo
.git/
.github/
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
outputs/
docs/
*.md
```

The `.dockerignore` file prevents secrets (`.env`), large directories (`.git`), and irrelevant files from being sent to the Docker build context. Without it, `docker build` sends every file in the directory to the daemon. On a repo with a `.venv/`, that is gigabytes of files copied before the first layer runs.

### Step 4: The Dockerfile

```dockerfile
# code/Dockerfile

# ----- BUILD STAGE -----
FROM python:3.12-slim AS build

WORKDIR /app

# Install system dependencies needed to build wheels (e.g., gcc for some packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements FIRST so pip install layer is cached on code-only changes
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ----- RUNTIME STAGE -----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install only curl for the health check
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from build stage (leave build tools behind)
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# Create non-root user
RUN useradd -m -u 1000 appuser

# Copy application code
COPY main.py .

USER appuser

# Non-secret config only; secrets injected at runtime via --env
ENV PORT=8000 \
    WORKERS=1 \
    LOG_LEVEL=info \
    MODEL=claude-3-5-haiku-20241022 \
    MAX_TOKENS=1024

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --log-level ${LOG_LEVEL}
```

### Step 5: Build and Run

```bash
# Build the image
docker build -t ai-app:latest -f code/Dockerfile code/

# Run passing the API key at runtime (not baked into the image)
docker run -p 8000:8000 \
  --env ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  ai-app:latest

# Test
curl http://localhost:8000/health
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain Docker layers in one sentence."}'
```

> **Real-world check:** A security auditor asks you: "How do you guarantee that the `ANTHROPIC_API_KEY` is not baked into the Docker image and therefore visible to anyone who runs `docker history ai-app:latest`?" What is your answer, and what command would you run right now to prove it?

### Step 6: Verify the Health Check

```bash
# Inspect health check status
docker inspect --format='{{.State.Health.Status}}' $(docker ps -q --filter ancestor=ai-app:latest)
# Expected: healthy  (after ~40 seconds from start)

# View health check logs
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' \
  $(docker ps -q --filter ancestor=ai-app:latest)
```

The `HEALTHCHECK` instruction tells Docker's container runtime to periodically ping `/health`. Orchestrators like Kubernetes and ECS use this signal to decide when a container is ready to receive traffic and when to restart it. Without a health check, a container that starts but immediately errors on the first import appears healthy to the scheduler.

---

## Use It

With the image built, these three `docker` commands cover the full operational lifecycle:

```bash
# Build: creates image from Dockerfile
docker build -t ai-app:v1.0 -f code/Dockerfile code/

# Run: starts container from image
docker run -d -p 8000:8000 \
  --name ai-app \
  --env ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  --env MODEL=claude-3-5-haiku-20241022 \
  ai-app:v1.0

# Inspect: checks container state including health
docker inspect ai-app
```

In a real deployment pipeline, this Dockerfile slots directly into a CI/CD workflow. GitHub Actions, for example:

```yaml
# .github/workflows/build.yml
- name: Build and push
  uses: docker/build-push-action@v5
  with:
    context: ./code
    file: ./code/Dockerfile
    push: true
    tags: ghcr.io/org/ai-app:${{ github.sha }}
```

The key difference between local Docker and production: secrets come from the CI secret store (`secrets.ANTHROPIC_API_KEY`), never from the Dockerfile. The image itself is secret-free and can be stored in a public registry without exposure.

> **Perspective shift:** Your team proposes using `ENV ANTHROPIC_API_KEY=sk-...` in the Dockerfile to "simplify local development." Your manager says: "it is just for dev, the prod image is different." What is the concrete risk of that policy, and what safer alternative achieves the same convenience?

---

## Ship It

The reusable artifact for this lesson is `outputs/skill-ai-app-dockerfile.md`: a production-ready Dockerfile template with annotations explaining every decision. Drop it into any new Python AI service.

To use it:
1. Copy `code/Dockerfile`, `code/requirements.txt`, and `code/.dockerignore` into your service directory.
2. Replace `main.py` with your application entry point.
3. Adjust the `HEALTHCHECK` path to match your service's health endpoint.
4. Run `docker build -t your-service:latest .` and verify `docker inspect` shows `healthy`.

---

## Evaluate It

**Check 1: Layer cache efficiency.**
Make a trivial change to `main.py` (add a comment) and rebuild. The output should show `CACHED` for layers 1-4 and only rebuild layers 5-6. If you see pip reinstalling packages after a code-only change, the layer order is wrong.

```bash
docker build -t ai-app:test -f code/Dockerfile code/ 2>&1 | grep -E "CACHED|RUN pip"
```

**Check 2: No secrets in the image.**
Run `docker history ai-app:latest` and `docker inspect ai-app:latest`. Neither should contain any string that looks like an API key. Verify the `ENV` block in the image config contains only non-secret values.

```bash
docker history ai-app:latest
docker inspect ai-app:latest | grep -i "api_key\|secret\|token"
# Should return nothing
```

**Check 3: Non-root user.**
Verify the running process is not root.

```bash
docker exec ai-app whoami
# Expected: appuser
```

**Check 4: Image size.**
Compare the multi-stage build against a naive single-stage build (no `AS build`, everything in one stage). The multi-stage image should be at least 30% smaller.

```bash
docker images ai-app
```
