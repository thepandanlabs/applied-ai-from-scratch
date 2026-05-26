"""
Lesson 11 - Deploying: Managed and Container Paths
Phase 06: Shipping

The complete Phase 06 FastAPI service, ready for deployment to Railway or Render.
Includes all required production endpoints:
  GET  /health    - health check (required by all platforms)
  POST /generate  - sync LLM generation
  GET  /stream    - SSE streaming generation

Deployment steps:
    Railway:  railway login && railway init && railway variables set ANTHROPIC_API_KEY=... && railway up
    Render:   render login && render deploy (requires render.yaml in project root)

Required environment variables:
    ANTHROPIC_API_KEY   - Your Anthropic API key (set via platform dashboard, never in code)
    PORT                - Set automatically by Railway/Render (default: 8000)
"""
import os

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Service",
    version="1.0.0",
    description="FastAPI service wrapping Claude. Deploy to Railway or Render.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your frontend domain in production
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 1024


class GenerateResponse(BaseModel):
    text: str
    model: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """
    Health check endpoint. Required by all deployment platforms.
    Railway, Render, Fly.io, Cloud Run all ping this to verify readiness.
    Must return HTTP 200. Should not call external services.
    """
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """Synchronous generation. Returns full response as JSON."""
    message = client.messages.create(
        model=MODEL,
        max_tokens=request.max_tokens,
        messages=[{"role": "user", "content": request.prompt}],
    )
    return GenerateResponse(text=message.content[0].text, model=MODEL)


@app.get("/stream")
async def stream(prompt: str, max_tokens: int = 1024) -> StreamingResponse:
    """
    Streaming generation via Server-Sent Events.
    Use EventSource in the browser or httpx.stream in a client script.
    Prompt passed as query parameter (EventSource is GET-only).
    """

    def generate_stream():
        with client.messages.stream(
            model=MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream_ctx:
            for text in stream_ctx.text_stream:
                # SSE format requires double newline after each data line
                safe_text = text.replace("\n", " ")
                yield f"data: {safe_text}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Prevent nginx buffering
        },
    )


# ---------------------------------------------------------------------------
# Deployment verification script
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Run this script after deploying to verify your service is live.
    Usage: BASE_URL=https://your-service.railway.app python main.py
    """
    import sys

    import httpx

    base_url = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
    print(f"Verifying deployment at: {base_url}")
    errors = []

    # Test 1: Health check
    try:
        resp = httpx.get(f"{base_url}/health", timeout=10)
        if resp.status_code == 200 and resp.json().get("status") == "ok":
            print(f"  [PASS] GET /health -> {resp.status_code}")
        else:
            errors.append(f"  [FAIL] GET /health -> {resp.status_code}: {resp.text}")
    except Exception as exc:
        errors.append(f"  [FAIL] GET /health -> {exc}")

    # Test 2: Generate
    try:
        resp = httpx.post(
            f"{base_url}/generate",
            json={"prompt": "Say 'deployment verified' and nothing else."},
            timeout=30,
        )
        if resp.status_code == 200 and "text" in resp.json():
            print(f"  [PASS] POST /generate -> {resp.status_code}")
            print(f"         Response: {resp.json()['text'][:60]}")
        else:
            errors.append(f"  [FAIL] POST /generate -> {resp.status_code}: {resp.text}")
    except Exception as exc:
        errors.append(f"  [FAIL] POST /generate -> {exc}")

    # Test 3: Streaming
    try:
        tokens_received = 0
        done_received = False
        with httpx.stream(
            "GET",
            f"{base_url}/stream",
            params={"prompt": "Count: 1, 2, 3"},
            timeout=30,
        ) as r:
            for line in r.iter_lines():
                if line.startswith("data: "):
                    token = line[6:]
                    if token == "[DONE]":
                        done_received = True
                        break
                    tokens_received += 1
        if tokens_received > 0 and done_received:
            print(f"  [PASS] GET /stream -> {tokens_received} tokens, [DONE] received")
        else:
            errors.append(
                f"  [FAIL] GET /stream -> tokens={tokens_received}, done={done_received}"
            )
    except Exception as exc:
        errors.append(f"  [FAIL] GET /stream -> {exc}")

    if errors:
        print("\nFailed checks:")
        for err in errors:
            print(err)
        sys.exit(1)
    else:
        print(f"\nAll checks passed. Service is live at {base_url}")
