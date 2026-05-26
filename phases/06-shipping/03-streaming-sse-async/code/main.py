"""
Lesson 06-03: Streaming Responses -- SSE, Async, Concurrency

A FastAPI service demonstrating Server-Sent Events (SSE) streaming of
Anthropic model output. Includes:
- AsyncAnthropic client (required for non-blocking streaming)
- Async generator producing SSE-formatted events
- StreamingResponse with correct headers
- A minimal HTML client served at /
- Concurrent stream handling via asyncio

Usage:
    pip install fastapi uvicorn anthropic pydantic
    export ANTHROPIC_API_KEY=sk-ant-...
    uvicorn main:app --reload --port 8000

Test with curl:
    curl -X POST http://localhost:8000/stream --no-buffer \
        -H "Content-Type: application/json" \
        -d '{"prompt": "Count from 1 to 10."}'

Test in browser:
    open http://localhost:8000
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class StreamRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    max_tokens: int = Field(default=1024, ge=1, le=4096)
    system: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Lifespan: initialize AsyncAnthropic client once at startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the async Anthropic client at startup."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. "
            "Export it before starting: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    model = os.environ.get("MODEL", "claude-3-5-haiku-20241022")
    timeout = float(os.environ.get("TIMEOUT_SECONDS", "60.0"))

    # AsyncAnthropic is required for streaming in async FastAPI routes.
    # The synchronous Anthropic client blocks the event loop and prevents
    # concurrent requests from being served.
    app.state.client = anthropic.AsyncAnthropic(
        api_key=api_key,
        timeout=timeout,
    )
    app.state.model = model

    log.info("Startup complete: model=%s timeout=%.1fs", model, timeout)

    yield

    log.info("Shutdown")


app = FastAPI(
    title="Streaming AI Service",
    description="Server-Sent Events streaming of Anthropic model output",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Async generator: produces SSE-formatted events
# ---------------------------------------------------------------------------


async def stream_tokens(
    client: anthropic.AsyncAnthropic,
    model: str,
    prompt: str,
    system: str | None = None,
    max_tokens: int = 1024,
):
    """
    Async generator that streams model output as SSE events.

    SSE format:
        data: {"token": "Hello"}\n\n
        data: {"token": " world"}\n\n
        data: {"done": true, "input_tokens": 10, "output_tokens": 5}\n\n

    Each yield is one SSE event. FastAPI's StreamingResponse sends each event
    to the client as soon as it is yielded -- no buffering.

    The async context manager keeps the connection open for the duration of
    the stream. The event loop can switch to other requests between yields.
    """
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    try:
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                # Each token is a separate SSE event.
                # json.dumps handles escaping of special characters.
                event_data = json.dumps({"token": text})
                yield f"data: {event_data}\n\n"

            # After all tokens, emit a final event with usage stats.
            # This is the signal the client uses to detect clean stream completion
            # vs. a dropped connection.
            final = await stream.get_final_message()
            done_data = json.dumps({
                "done": True,
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
                "model": final.model,
            })
            yield f"data: {done_data}\n\n"

    except anthropic.APIStatusError as e:
        log.error("Anthropic API error in stream: status=%d", e.status_code)
        error_data = json.dumps({"error": f"API error: HTTP {e.status_code}"})
        yield f"data: {error_data}\n\n"
    except anthropic.APITimeoutError:
        log.error("Anthropic API timeout in stream")
        error_data = json.dumps({"error": "Request timed out"})
        yield f"data: {error_data}\n\n"
    except Exception as e:
        log.error("Unexpected error in stream: %s", e, exc_info=True)
        error_data = json.dumps({"error": "Internal server error"})
        yield f"data: {error_data}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
async def health(req: Request):
    """Health check for load balancers. Fast and cheap -- no model call."""
    return {
        "status": "ok",
        "model": req.app.state.model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/stream", tags=["model"])
async def stream_endpoint(req: Request, body: StreamRequest):
    """
    Stream model output as Server-Sent Events.

    The response is a continuous text/event-stream body.
    Each event is a JSON object on a 'data:' line followed by two newlines.

    Headers:
    - Content-Type: text/event-stream
    - Cache-Control: no-cache (required for SSE)
    - X-Accel-Buffering: no (disables nginx response buffering)

    Use curl --no-buffer or EventSource in the browser to consume this endpoint.
    """
    client: anthropic.AsyncAnthropic = req.app.state.client
    model: str = req.app.state.model

    log.info(
        "POST /stream model=%s prompt_chars=%d max_tokens=%d",
        model,
        len(body.prompt),
        body.max_tokens,
    )

    return StreamingResponse(
        stream_tokens(
            client=client,
            model=model,
            prompt=body.prompt,
            system=body.system,
            max_tokens=body.max_tokens,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # prevents nginx from buffering the stream
        },
    )


@app.get("/", response_class=HTMLResponse, tags=["demo"])
async def demo_page():
    """
    Minimal HTML page that demonstrates consuming the /stream endpoint.
    Open http://localhost:8000 in a browser to try streaming interactively.
    """
    return """<!DOCTYPE html>
<html>
<head>
    <title>Streaming Demo</title>
    <style>
        body { font-family: monospace; max-width: 800px; margin: 40px auto; padding: 0 20px; }
        #output { white-space: pre-wrap; border: 1px solid #ccc; padding: 16px; min-height: 100px; }
        #stats { color: #666; font-size: 0.9em; margin-top: 8px; }
        button { padding: 8px 16px; margin: 8px 4px; cursor: pointer; }
        textarea { width: 100%; height: 80px; font-family: monospace; }
    </style>
</head>
<body>
    <h1>Streaming Demo</h1>
    <textarea id="prompt">Tell me a short story about a robot who learns to paint.</textarea>
    <br>
    <button onclick="startStream()">Stream</button>
    <button onclick="clearOutput()">Clear</button>
    <div id="output">Output will appear here...</div>
    <div id="stats"></div>

    <script>
    async function startStream() {
        const prompt = document.getElementById('prompt').value;
        const output = document.getElementById('output');
        const stats = document.getElementById('stats');
        output.textContent = '';
        stats.textContent = 'Streaming...';

        const startTime = Date.now();
        let firstTokenTime = null;
        let tokenCount = 0;

        const response = await fetch('/stream', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({prompt: prompt})
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, {stream: true});
            const events = buffer.split('\\n\\n');
            buffer = events.pop();  // keep incomplete event in buffer

            for (const event of events) {
                if (!event.startsWith('data: ')) continue;
                const data = JSON.parse(event.slice(6));

                if (data.token !== undefined) {
                    if (firstTokenTime === null) {
                        firstTokenTime = Date.now() - startTime;
                    }
                    output.textContent += data.token;
                    tokenCount++;
                }

                if (data.done) {
                    const totalTime = ((Date.now() - startTime) / 1000).toFixed(1);
                    stats.textContent = [
                        'Done.',
                        `First token: ${firstTokenTime}ms`,
                        `Total: ${totalTime}s`,
                        `Input tokens: ${data.input_tokens}`,
                        `Output tokens: ${data.output_tokens}`
                    ].join(' | ');
                }

                if (data.error) {
                    output.textContent += `\\n[Error: ${data.error}]`;
                    stats.textContent = 'Stream ended with error.';
                }
            }
        }
    }

    function clearOutput() {
        document.getElementById('output').textContent = '';
        document.getElementById('stats').textContent = '';
    }
    </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
