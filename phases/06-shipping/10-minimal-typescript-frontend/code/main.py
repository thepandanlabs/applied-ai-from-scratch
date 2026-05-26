"""
Lesson 10 - A Minimal TypeScript Frontend
Phase 06: Shipping

FastAPI backend that serves the two endpoints the TypeScript client expects:
  POST /generate  - sync generation, returns JSON {text: str}
  GET  /stream    - SSE streaming, yields data: <token> lines

Also mounts the frontend/ directory as static files at /ui.

Run:
    uv pip install fastapi uvicorn anthropic
    ANTHROPIC_API_KEY=sk-... uvicorn main:app --reload

Then open http://localhost:8000/ui/ in your browser.
Or serve the frontend separately:
    python -m http.server 3000 --directory frontend/
"""
import os

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="AI Frontend Backend", version="1.0.0")

# CORS: required when frontend is on a different port (e.g., localhost:3000)
# In production, replace "*" with your actual frontend domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


class GenerateResponse(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# Sync endpoint (called via fetch)
# ---------------------------------------------------------------------------


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """
    Synchronous generation. Returns the full response as JSON.
    The TypeScript client calls this with fetch() and waits for the response.
    """
    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": request.prompt}],
    )
    return GenerateResponse(text=message.content[0].text)


# ---------------------------------------------------------------------------
# Streaming endpoint (called via EventSource)
# ---------------------------------------------------------------------------


@app.get("/stream")
async def stream(prompt: str) -> StreamingResponse:
    """
    Streaming generation via Server-Sent Events.
    The TypeScript client uses EventSource (GET only).
    Sends: data: <token>\\n\\n for each token.
    Sends: data: [DONE]\\n\\n when the stream ends.

    Note: prompt passed as query parameter because EventSource is GET-only.
    """

    def generate_stream():
        with client.messages.stream(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ) as stream_ctx:
            for text in stream_ctx.text_stream:
                # SSE format: "data: <content>\n\n"
                # Replace newlines in content to avoid breaking SSE framing
                safe_text = text.replace("\n", " ")
                yield f"data: {safe_text}\n\n"
        # Signal to the client that the stream is complete
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            # Prevent buffering in nginx/proxies
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static files (mount last so API routes take precedence)
# ---------------------------------------------------------------------------

# Uncomment when you have a frontend/ directory next to main.py:
# app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")


# ---------------------------------------------------------------------------
# Quick test without a browser
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import httpx

    BASE = "http://localhost:8000"

    print("=== Test: sync /generate ===")
    resp = httpx.post(f"{BASE}/generate", json={"prompt": "Say hello in one sentence."})
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()['text']}")

    print("\n=== Test: streaming /stream ===")
    print("Tokens: ", end="", flush=True)
    with httpx.stream("GET", f"{BASE}/stream", params={"prompt": "Count from 1 to 5."}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                token = line[6:]
                if token == "[DONE]":
                    break
                print(token, end="", flush=True)
    print()
