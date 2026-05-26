---
name: skill-fastapi-ai-service
description: Minimal FastAPI service template wrapping an LLM with correct lifespan initialization, Pydantic models, health check, and structured error handling
version: "1.0"
phase: "06"
lesson: "02"
tags: [fastapi, shipping, service, api, pydantic]
---

# FastAPI AI Service Template

Copy this template as the starting point for any new AI microservice. Replace the placeholder endpoint logic with your specific feature.

---

## Project structure

```
my-ai-service/
├── main.py           # FastAPI app (this file)
├── requirements.txt  # or pyproject.toml with uv
└── .env.example      # document required env vars
```

**requirements.txt:**
```
fastapi>=0.115
uvicorn[standard]>=0.30
anthropic>=0.40
pydantic>=2.0
```

**.env.example:**
```
ANTHROPIC_API_KEY=sk-ant-...        # required
MODEL=claude-3-5-haiku-20241022     # optional, default shown
TIMEOUT_SECONDS=30.0                # optional, default shown
```

---

## main.py

```python
"""
AI Service -- FastAPI template for wrapping an Anthropic model.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    uvicorn main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import anthropic
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ---------------------------------------------------------------------------
# Request / Response models -- define your API contract here
# ---------------------------------------------------------------------------

class MyRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    system: str | None = Field(default=None, max_length=2000)

class MyResponse(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int
    model: str

class HealthResponse(BaseModel):
    status: str
    model: str
    timestamp: str


# ---------------------------------------------------------------------------
# Lifespan -- initialize the client ONCE at startup, not per-request
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

    app.state.client = anthropic.Anthropic(
        api_key=api_key,
        timeout=float(os.environ.get("TIMEOUT_SECONDS", "30.0")),
        max_retries=2,
    )
    app.state.model = os.environ.get("MODEL", "claude-3-5-haiku-20241022")
    log.info("Startup: model=%s", app.state.model)

    yield

    log.info("Shutdown")


app = FastAPI(title="AI Service", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Health check -- fast, cheap, no model call
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health(req: Request):
    return HealthResponse(
        status="ok",
        model=req.app.state.model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Model endpoint -- replace with your feature logic
# ---------------------------------------------------------------------------

@app.post("/generate", response_model=MyResponse)
async def generate(req: Request, body: MyRequest):
    client: anthropic.Anthropic = req.app.state.client
    model: str = req.app.state.model

    log.info("POST /generate prompt_chars=%d", len(body.prompt))

    kwargs = {
        "model": model,
        "max_tokens": body.max_tokens,
        "messages": [{"role": "user", "content": body.prompt}],
    }
    if body.system:
        kwargs["system"] = body.system

    try:
        response = client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        log.error("API error: status=%d", e.status_code)
        if e.status_code == 429:
            raise HTTPException(status_code=429, detail="Rate limit reached.")
        raise HTTPException(status_code=502, detail="Upstream model error.")
    except anthropic.APITimeoutError:
        raise HTTPException(status_code=504, detail="Model request timed out.")
    except Exception as e:
        log.error("Unexpected error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error.")

    return MyResponse(
        text=response.content[0].text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        model=response.model,
    )
```

---

## Key patterns

### 1. One client per process

The `lifespan` event creates `anthropic.Anthropic()` once and stores it in `app.state`. Route handlers read from `req.app.state.client`. Never create a new client inside a route handler.

### 2. Pydantic validation is automatic

Field constraints (`min_length`, `max_length`, `ge`, `le`) produce 422 responses automatically. You do not need to write validation logic for basic type and range checks.

### 3. HTTP status code mapping

| Error | Status |
|-------|--------|
| Pydantic validation fails | 422 (automatic) |
| Anthropic rate limit (429) | 429 (forward it) |
| Anthropic HTTP error | 502 (upstream error) |
| Request timeout | 504 |
| Unexpected exception | 500 |

### 4. Health check contract

- Must return 200 when the service is running
- Must return in under 5ms
- Must NOT call the model
- Load balancers and uptime monitors depend on this

### 5. Logging minimum

Log these fields on every request:
- endpoint + HTTP method
- input size (character or token count)
- output size on success
- error type on failure

---

## Testing the service

```bash
# Start
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --reload --port 8000

# Health check
curl http://localhost:8000/health

# Generate
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Summarize the benefits of FastAPI in 2 sentences."}'

# Trigger 422 (empty prompt)
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": ""}'

# Interactive docs
open http://localhost:8000/docs
```

---

## Customization points

| What to change | Where |
|----------------|-------|
| Request fields | `MyRequest` model |
| Response fields | `MyResponse` model |
| System prompt | `kwargs["system"]` in the route handler |
| Add a second endpoint | Copy the `/generate` route, change path and logic |
| Add auth (API key header) | FastAPI `Depends` + `Header` parameter |
| Add rate limiting | `slowapi` library or an API gateway |
| Add streaming | See Lesson 06-03 |
