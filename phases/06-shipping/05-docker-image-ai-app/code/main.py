"""
Production FastAPI AI service for Docker packaging.

Reads config from environment variables (non-secret values only).
Expects ANTHROPIC_API_KEY to be injected at runtime via docker run --env.

Usage:
    docker build -t ai-app:latest -f Dockerfile .
    docker run -p 8000:8000 --env ANTHROPIC_API_KEY=sk-... ai-app:latest

    # Local dev (without Docker):
    ANTHROPIC_API_KEY=sk-... uvicorn main:app --reload
"""

import os

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="AI App", version="1.0")

# API key is required; fail fast at startup if missing
_api_key = os.environ.get("ANTHROPIC_API_KEY")
if not _api_key:
    raise RuntimeError(
        "ANTHROPIC_API_KEY environment variable is required. "
        "Inject it at runtime: docker run --env ANTHROPIC_API_KEY=sk-..."
    )

client = anthropic.Anthropic(api_key=_api_key)

# Non-secret config from environment variables (set in Dockerfile or overridden at runtime)
MODEL = os.environ.get("MODEL", "claude-3-5-haiku-20241022")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    prompt: str


class GenerateResponse(BaseModel):
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class HealthResponse(BaseModel):
    status: str
    model: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
def health():
    """
    Health check endpoint used by Docker HEALTHCHECK and load balancers.
    Returns 200 when the service is ready to handle requests.
    Does NOT make an API call -- health checks must be cheap and fast.
    """
    return HealthResponse(status="ok", model=MODEL)


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    """
    Send a prompt to Claude and return the generated text with token counts.

    Example:
        curl -X POST http://localhost:8000/generate \\
          -H "Content-Type: application/json" \\
          -d '{"prompt": "Explain Docker layers in one sentence."}'
    """
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


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
