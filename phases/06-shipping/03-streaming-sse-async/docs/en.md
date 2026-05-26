# Streaming Responses: SSE, Async, Concurrency

> Users feel speed at the first token, not the last.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lesson 06-02 (FastAPI service), familiarity with async/await in Python
**Time:** ~60 min
**Learning Objectives:**
- Explain why streaming improves perceived performance for LLM responses
- Implement a `/stream` endpoint using FastAPI StreamingResponse and async generators
- Format Server-Sent Events (SSE) correctly so browsers and curl can consume them
- Understand how FastAPI handles multiple simultaneous streaming requests with asyncio
- Test a streaming endpoint with curl and a minimal HTML page

---

## The Problem

Your `/generate` endpoint works but users are unhappy. A typical Claude response takes 8-12 seconds to complete. The user clicks the button, sees nothing for 10 seconds, then the entire response appears at once. They think the page is broken. Many abandon before the response arrives.

The model is not slow -- it produces tokens continuously from the first millisecond. The problem is you are buffering all of them before sending anything. The fix is streaming: send each token to the client as soon as the model produces it. The user sees the first word in under a second and watches the response build in real time.

Streaming also solves a timeout problem. A 10-second HTTP request is close to many load balancer and client timeout defaults. A streaming response keeps the connection alive by continuously sending data.

---

## The Concept

### Buffered vs. Streaming Response

```
BUFFERED (current behavior):
User clicks        API call starts        Model finishes      User sees output
    |                    |                     |                    |
    |<---- 10 seconds ----------------------------------->|
    |                                          buffer fills -> response sent


STREAMING (what we want):
User clicks   API call starts   Token 1   Token 2   ...   Done
    |               |              |         |              |
    |               |<-- ~0.3s -->|<~0.05s>|<~0.05s>...   |
    |                             user sees first word      |
    |<--- 0.3s to first content --------- 10s total ------>|
```

The total time is the same. The perceived time to first content drops from 10s to under 1s.

### Server-Sent Events Format

SSE is a one-way HTTP protocol where the server pushes data to the client. Each event is text separated by `\n\n`:

```
data: {"token": "Hello"}\n\n
data: {"token": " world"}\n\n
data: {"token": "!"}\n\n
data: [DONE]\n\n
```

Rules:
- Each event starts with `data: `
- Each event ends with exactly `\n\n` (two newlines, not one)
- `[DONE]` is the conventional sentinel value to signal stream end
- The `Content-Type` header must be `text/event-stream`
- The `Cache-Control` header must be `no-cache`

### SSE vs. WebSocket

```
+--------------------+------------------+-------------------------+
| Feature            | SSE              | WebSocket               |
+--------------------+------------------+-------------------------+
| Direction          | Server to client | Bidirectional           |
| Protocol           | Plain HTTP       | WebSocket upgrade       |
| Reconnect          | Built-in         | Manual                  |
| Browser support    | All modern       | All modern              |
| Load balancer      | Works natively   | Requires upgrade config |
| Right choice for   | Model streaming  | Live chat, games        |
+--------------------+------------------+-------------------------+
```

Streaming model output is one-directional. SSE is the right choice. WebSockets add bidirectional complexity you do not need.

### Asyncio Concurrency With Streaming

```
Event Loop (single thread)

Request A: stream start
    |-- await client.messages.stream()  <-- suspends, loop runs other tasks
    |
Request B arrives during A's await:
    |-- Request B handler starts immediately
    |-- await client.messages.stream()  <-- suspends
    |
Event Loop schedules both:
    A: receives token, sends SSE event, suspends again
    B: receives token, sends SSE event, suspends again
    A: next token...
    B: next token...
```

`async def` and `await` allow the event loop to serve multiple streaming responses concurrently from a single thread. No threads, no locks, no shared state issues.

---

## Build It

### Step 1: Async Anthropic Client

Streaming requires the async Anthropic client. The sync client from Lesson 02 blocks the event loop.

```python
from anthropic import AsyncAnthropic
import os

# In the lifespan event:
app.state.client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
```

### Step 2: The Async Generator

The generator is the heart of SSE. It yields one formatted SSE event per token.

```python
import json
from anthropic import AsyncAnthropic

async def stream_tokens(
    client: AsyncAnthropic,
    model: str,
    prompt: str,
    system: str | None = None,
    max_tokens: int = 1024,
):
    """
    Async generator that yields SSE-formatted events for each token.

    Each yield produces a string like:
        data: {"token": "Hello"}\n\n

    A final [DONE] event signals end of stream.
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
                # Format as SSE event: "data: {json}\n\n"
                event_data = json.dumps({"token": text})
                yield f"data: {event_data}\n\n"

            # Send final event with usage stats
            final = await stream.get_final_message()
            done_data = json.dumps({
                "done": True,
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
            })
            yield f"data: {done_data}\n\n"

    except Exception as e:
        # Yield an error event so the client knows something went wrong
        error_data = json.dumps({"error": str(e)})
        yield f"data: {error_data}\n\n"
```

The `async with client.messages.stream()` context manager handles connection lifecycle. `stream.text_stream` is an async iterator that yields each text token as it arrives.

### Step 3: The StreamingResponse Endpoint

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

class StreamRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    max_tokens: int = Field(default=1024, ge=1, le=4096)
    system: str | None = None

@app.post("/stream")
async def stream_endpoint(req: Request, body: StreamRequest):
    """
    Stream model output as Server-Sent Events.
    The response body is a continuous stream of text/event-stream data.
    """
    client = req.app.state.client
    model = req.app.state.model

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
            "X-Accel-Buffering": "no",  # disables nginx buffering if deployed behind nginx
        },
    )
```

`StreamingResponse` accepts an async generator and streams its output to the client as each `yield` executes.

> **Real-world check:** Your frontend engineer asks: "Why do we need the `[DONE]` sentinel at the end? Can't the frontend just know the stream ended when the connection closes?" How do you explain the failure mode where a connection drops mid-stream versus a stream that completes cleanly?

---

## Use It

### Running the Service

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --reload --port 8000
```

### Testing With curl

```bash
# Stream a response -- the --no-buffer flag shows each event as it arrives
curl -X POST http://localhost:8000/stream \
  --no-buffer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Count from 1 to 10, one number per line."}'
```

Expected output (tokens arriving one at a time):
```
data: {"token": "1"}

data: {"token": "\n2"}

data: {"token": "\n3"}

...

data: {"done": true, "input_tokens": 15, "output_tokens": 24}
```

### Testing With a Browser (minimal HTML)

```html
<!DOCTYPE html>
<html>
<body>
<button onclick="startStream()">Generate</button>
<div id="output"></div>
<script>
async function startStream() {
    const output = document.getElementById('output');
    output.textContent = '';

    const response = await fetch('/stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt: 'Tell me a short story about a robot.'})
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const {done, value} = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n\n').filter(l => l.startsWith('data: '));

        for (const line of lines) {
            const data = JSON.parse(line.slice(6));  // remove "data: "
            if (data.token) output.textContent += data.token;
            if (data.done) console.log('Stream complete:', data);
        }
    }
}
</script>
</body>
</html>
```

### Concurrent Streaming

Start the server and open two terminal windows:

```bash
# Terminal 1
curl -X POST http://localhost:8000/stream --no-buffer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a 200-word essay on astronomy."}'

# Terminal 2 (at the same time)
curl -X POST http://localhost:8000/stream --no-buffer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a 200-word essay on biology."}'
```

Both streams run concurrently from a single uvicorn worker. The event loop interleaves them without threads or blocking.

> **Perspective shift:** A colleague suggests using WebSockets instead of SSE because "WebSockets are more modern and powerful." Knowing your current use case is one-way streaming of model output, how do you evaluate this suggestion? What would have to be true about your requirements for WebSockets to be the better choice?

---

## Ship It

The reusable artifact for this lesson is `outputs/skill-streaming-sse.md`. It contains the SSE streaming pattern as a self-contained code snippet with the async generator, the FastAPI route, and the HTML client, ready to drop into any FastAPI service.

---

## Evaluate It

**Check 1: Time to first token.**
Use curl with `--no-buffer` and measure visually. You should see the first token in the terminal in under 1 second. If you see nothing for several seconds followed by the entire response at once, the response is being buffered somewhere (nginx, a proxy, or the generator is not yielding incrementally).

**Check 2: Concurrent streams do not block each other.**
Open two terminals. Start a long stream in terminal 1 (ask for a 500-word essay). Immediately start a stream in terminal 2. Both terminals should show tokens arriving interleaved. If terminal 2 waits until terminal 1 finishes, the handlers are blocking (synchronous def instead of async def, or sync client instead of AsyncAnthropic).

**Check 3: SSE format is correct.**
Pipe the stream output to a file and inspect it. Every event line must start with `data: ` and end with `\n\n`. Any deviation will break EventSource in the browser. Check with: `curl ... | cat -A | grep -v "^data:" ` -- there should be no non-empty lines.

**Check 4: Error events are formatted correctly.**
Trigger an error by passing an invalid API key. Confirm the response stream contains a `data: {"error": "..."}` event followed by the stream closing cleanly. The connection should not hang.

**Check 5: Done event arrives.**
After a complete stream, confirm the final line in the output is `data: {"done": true, ...}`. If the client cannot detect clean stream completion, it cannot distinguish "stream finished" from "connection dropped mid-stream."
