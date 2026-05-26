---
name: skill-streaming-sse
description: Drop-in SSE streaming pattern for FastAPI -- async generator, StreamingResponse, and browser HTML client
version: "1.0"
phase: "06"
lesson: "03"
tags: [streaming, sse, fastapi, async, concurrency]
---

# SSE Streaming Pattern for FastAPI

Drop these components into any FastAPI service to add Server-Sent Events streaming of model output.

---

## Requirements

```
fastapi>=0.115
uvicorn[standard]>=0.30
anthropic>=0.40
```

The `AsyncAnthropic` client (not the synchronous `Anthropic` client) is required for non-blocking streaming in async FastAPI routes.

---

## 1. Client initialization (lifespan)

```python
from contextlib import asynccontextmanager
import anthropic
import os

@asynccontextmanager
async def lifespan(app):
    app.state.client = anthropic.AsyncAnthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        timeout=60.0,
    )
    app.state.model = os.environ.get("MODEL", "claude-3-5-haiku-20241022")
    yield
```

---

## 2. Async generator

```python
import json
import anthropic

async def stream_tokens(
    client: anthropic.AsyncAnthropic,
    model: str,
    prompt: str,
    system: str | None = None,
    max_tokens: int = 1024,
):
    """
    Yields SSE-formatted events for each token from the model.

    Format of each event:
        data: {"token": "Hello"}\n\n

    Final event:
        data: {"done": true, "input_tokens": N, "output_tokens": N}\n\n

    Error event (if something goes wrong mid-stream):
        data: {"error": "description"}\n\n
    """
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    try:
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'token': text})}\n\n"

            final = await stream.get_final_message()
            yield f"data: {json.dumps({'done': True, 'input_tokens': final.usage.input_tokens, 'output_tokens': final.usage.output_tokens})}\n\n"

    except anthropic.APIStatusError as e:
        yield f"data: {json.dumps({'error': f'API error: HTTP {e.status_code}'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
```

---

## 3. FastAPI route

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

class StreamRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    max_tokens: int = Field(default=1024, ge=1, le=4096)
    system: str | None = None

@app.post("/stream")
async def stream_endpoint(req: Request, body: StreamRequest):
    return StreamingResponse(
        stream_tokens(
            client=req.app.state.client,
            model=req.app.state.model,
            prompt=body.prompt,
            system=body.system,
            max_tokens=body.max_tokens,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # prevents nginx buffering
        },
    )
```

---

## 4. curl test

```bash
curl -X POST http://localhost:8000/stream \
  --no-buffer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Count from 1 to 5."}'
```

Expected output (one event per line pair):
```
data: {"token": "1"}

data: {"token": "\n2"}

data: {"token": "\n3"}

data: {"token": "\n4"}

data: {"token": "\n5"}

data: {"done": true, "input_tokens": 12, "output_tokens": 9}

```

---

## 5. Browser JavaScript client

```javascript
async function streamToElement(prompt, outputElement) {
    const response = await fetch('/stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt})
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const {done, value} = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, {stream: true});
        const events = buffer.split('\n\n');
        buffer = events.pop();  // keep incomplete event in buffer

        for (const event of events) {
            if (!event.startsWith('data: ')) continue;
            const data = JSON.parse(event.slice(6));

            if (data.token) {
                outputElement.textContent += data.token;
            }
            if (data.done) {
                console.log('Stream complete:', data);
            }
            if (data.error) {
                outputElement.textContent += `\n[Error: ${data.error}]`;
            }
        }
    }
}
```

---

## Key rules

### SSE format
- Every event: `data: {json}\n\n` (exactly two trailing newlines)
- `Content-Type` must be `text/event-stream`
- `Cache-Control` must be `no-cache`

### Client choice
- Use `AsyncAnthropic` for async routes (non-blocking)
- Use `Anthropic` only in sync routes (will block the event loop during streaming)

### Concurrency
- Each streaming request holds an open HTTP connection
- The asyncio event loop multiplexes all active streams on one thread
- No shared state between streams -- each call to `stream_tokens` is independent

### Nginx deployment
The `X-Accel-Buffering: no` header tells nginx not to buffer the response.
Without this, nginx may hold all tokens until the stream ends, defeating the purpose.

Also set in nginx config if the header alone is not sufficient:
```nginx
proxy_buffering off;
proxy_cache off;
```

### Error handling
Always yield an error event on failure rather than raising an exception from the generator.
Raising inside a generator closes the stream abruptly with no signal to the client.
Yielding an error event lets the client display a message and close cleanly.
