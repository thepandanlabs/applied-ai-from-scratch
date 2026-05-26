"""
Lesson 06-02: Wrapping a Model in FastAPI

A production-ready FastAPI service wrapping the Anthropic API with:
- Lifespan event for single client initialization
- Pydantic request/response models with automatic validation
- Two model endpoints: /generate and /extract
- Health check endpoint
- Correct HTTP status codes and structured error responses

Usage:
    pip install fastapi uvicorn anthropic pydantic
    export ANTHROPIC_API_KEY=sk-ant-...
    uvicorn main:app --reload --port 8000

Test:
    curl http://localhost:8000/health
    curl -X POST http://localhost:8000/generate \
        -H "Content-Type: application/json" \
        -d '{"prompt": "What is the capital of France?"}'
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import anthropic
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="The user prompt to send to the model",
    )
    max_tokens: int = Field(
        default=512,
        ge=1,
        le=4096,
        description="Maximum tokens in the response",
    )
    system: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional system prompt to guide the model's behavior",
    )


class GenerateResponse(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class ExtractRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="The text to extract structured data from",
    )
    schema_hint: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Description of what to extract, e.g. 'name, email, company'",
    )


class ExtractResponse(BaseModel):
    raw_json: str
    parsed: dict | None  # None if the model output was not valid JSON
    input_tokens: int
    output_tokens: int


class HealthResponse(BaseModel):
    status: str
    model: str
    timestamp: str


# ---------------------------------------------------------------------------
# Lifespan: initialize the Anthropic client ONCE at startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan event handler.

    Everything before 'yield' runs at startup.
    Everything after 'yield' runs at shutdown.

    The Anthropic client is created here -- once per process -- and stored in
    app.state so route handlers can access it without creating new instances.
    """
    # STARTUP
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. "
            "Export it before starting the service: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    model = os.environ.get("MODEL", "claude-3-5-haiku-20241022")
    timeout = float(os.environ.get("TIMEOUT_SECONDS", "30.0"))

    app.state.client = anthropic.Anthropic(
        api_key=api_key,
        timeout=timeout,
        max_retries=2,
    )
    app.state.model = model

    log.info("Startup complete: model=%s timeout=%.1fs", model, timeout)

    yield  # the service is alive; requests are handled here

    # SHUTDOWN
    log.info("Shutdown: cleaning up resources")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Service",
    description="Production FastAPI wrapper around the Anthropic API",
    version="1.0.0",
    lifespan=lifespan,
)

EXTRACT_SYSTEM = (
    "You are a data extraction assistant. "
    "Extract the requested fields from the provided text and return them as a JSON object. "
    "Return ONLY the JSON object with no preamble, explanation, or markdown code fences."
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health(req: Request) -> HealthResponse:
    """
    Health check for load balancers and uptime monitors.

    Returns 200 when the service is running and configured.
    Does NOT call the model -- health checks must be fast and cheap.
    Load balancers call this every 10-30 seconds.
    """
    return HealthResponse(
        status="ok",
        model=req.app.state.model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/generate", response_model=GenerateResponse, tags=["model"])
async def generate(req: Request, body: GenerateRequest) -> GenerateResponse:
    """
    Generate a text response from the model.

    Returns 200 on success.
    Returns 422 automatically if the request body fails Pydantic validation.
    Returns 429 if the upstream API is rate-limited.
    Returns 500 on unexpected errors.
    Returns 502 on upstream API errors.
    """
    client: anthropic.Anthropic = req.app.state.client
    model: str = req.app.state.model

    log.info(
        "POST /generate model=%s prompt_chars=%d max_tokens=%d",
        model,
        len(body.prompt),
        body.max_tokens,
    )

    kwargs: dict = {
        "model": model,
        "max_tokens": body.max_tokens,
        "messages": [{"role": "user", "content": body.prompt}],
    }
    if body.system:
        kwargs["system"] = body.system

    try:
        response = client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        log.error("Anthropic API status error: status=%d message=%s", e.status_code, e)
        if e.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Rate limit reached. Wait a moment and retry.",
            )
        raise HTTPException(
            status_code=502,
            detail=f"Upstream model error (HTTP {e.status_code}).",
        )
    except anthropic.APITimeoutError as e:
        log.error("Anthropic API timeout: %s", e)
        raise HTTPException(
            status_code=504,
            detail="Model request timed out. Retry with a shorter prompt or higher timeout.",
        )
    except Exception as e:
        log.error("Unexpected error in /generate: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error.")

    result = GenerateResponse(
        text=response.content[0].text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        model=response.model,
    )
    log.info(
        "POST /generate success input_tokens=%d output_tokens=%d",
        result.input_tokens,
        result.output_tokens,
    )
    return result


@app.post("/extract", response_model=ExtractResponse, tags=["model"])
async def extract(req: Request, body: ExtractRequest) -> ExtractResponse:
    """
    Extract structured data from text using the model.

    Returns parsed JSON when the model output is valid JSON.
    Returns raw_json with parsed=null when the model output is not valid JSON.
    Stripes markdown code fences from model output before attempting to parse.
    """
    client: anthropic.Anthropic = req.app.state.client
    model: str = req.app.state.model

    log.info(
        "POST /extract model=%s text_chars=%d schema=%r",
        model,
        len(body.text),
        body.schema_hint,
    )

    user_message = (
        f"Text to extract from:\n{body.text}\n\n"
        f"Extract these fields: {body.schema_hint}\n\n"
        f"Return a JSON object with those fields and nothing else."
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIStatusError as e:
        log.error("Anthropic API status error in /extract: status=%d", e.status_code)
        raise HTTPException(
            status_code=502,
            detail=f"Upstream model error (HTTP {e.status_code}).",
        )
    except Exception as e:
        log.error("Unexpected error in /extract: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error.")

    raw = response.content[0].text.strip()

    # Strip markdown code fences if the model wrapped the JSON
    # e.g. ```json\n{...}\n``` or ```\n{...}\n```
    if raw.startswith("```"):
        lines = raw.split("\n")
        if len(lines) > 2:
            raw = "\n".join(lines[1:-1]).strip()

    parsed: dict | None = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        log.warning(
            "POST /extract model output was not valid JSON (first 200 chars): %r",
            raw[:200],
        )

    log.info(
        "POST /extract success parsed=%s input_tokens=%d output_tokens=%d",
        parsed is not None,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

    return ExtractResponse(
        raw_json=raw,
        parsed=parsed,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


# ---------------------------------------------------------------------------
# Entry point for direct execution (not required for uvicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
