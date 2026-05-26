# A Minimal TypeScript Frontend

> Streaming from server to browser requires EventSource, not fetch. Fetch waits for the full response; EventSource processes chunks as they arrive.

**Type:** Build
**Languages:** Both
**Prerequisites:** 02-wrapping-model-in-fastapi, 03-streaming-sse-async
**Time:** ~60 min
**Learning Objectives:**
- Build a vanilla TypeScript + HTML frontend with no framework
- Call a FastAPI `/generate` endpoint using the Fetch API
- Consume a FastAPI `/stream` SSE endpoint using EventSource
- Display streamed tokens in the DOM as they arrive
- Serve the frontend from Python's `http.server` or FastAPI static files

---

## MOTTO

**The browser already knows how to stream. You just need to give it the right API: EventSource, not fetch.**

---

## THE PROBLEM

You built a FastAPI service that wraps Claude. It works perfectly in `curl`. Now you want a UI. You reach for React, Vite, a component library, a router, a state manager. Four hours later you are configuring a bundler and you have not written a single line of product code.

The real requirement is simpler: a text box, a submit button, and an area that fills with text. For an internal tool or a demo, vanilla TypeScript compiled with `tsc` is sufficient. No framework, no build pipeline beyond `tsc`, no `node_modules` folder with 400 packages.

There is one non-obvious problem: streaming. When you use `fetch()` for a POST request, the browser waits for the entire response before giving it to JavaScript. That is fine for the sync `/generate` endpoint. But for the streaming `/stream` endpoint, you want tokens to appear in the UI as they arrive, the way ChatGPT renders output. For that, you need `EventSource`, the browser's built-in API for Server-Sent Events.

Most developers learn this the hard way: they wire up `fetch` to the streaming endpoint, confused that nothing appears until the response is complete. The fix is one API swap.

---

## THE CONCEPT

### The Browser-FastAPI-Anthropic Call Chain

```
SYNC PATH (fetch -> /generate)
                                                         
  Browser          FastAPI             Anthropic API     
    |                  |                    |            
    |--fetch POST------>|                    |            
    |                  |--messages.create-->|            
    |                  |   (waits)          |            
    |                  |<--full response----|            
    |<--JSON response---|                    |            
    |  (entire text     |                    |            
    |   in one chunk)   |                    |            
                                                         
  DOM: set innerHTML once when fetch resolves            


STREAMING PATH (EventSource -> /stream)
                                                         
  Browser          FastAPI             Anthropic API     
    |                  |                    |            
    |--EventSource----->|                    |            
    |  (GET /stream?q=.)|                    |            
    |                  |--stream.create---->|            
    |<--data: token1----|<--chunk1---------- |            
    |  append to DOM    |                    |            
    |<--data: token2----|<--chunk2---------- |            
    |  append to DOM    |                    |            
    |<--data: [DONE]----|<--stream end------ |            
    |  stop listening   |                    |            
                                                         
  DOM: append each token as it arrives                   
```

### Why EventSource, Not fetch?

`fetch` is request-response: it collects the entire response body before resolving the Promise. You cannot get partial data from a `fetch` call until the server closes the connection.

`EventSource` is a persistent connection that processes `data:` lines as they arrive. It was designed exactly for Server-Sent Events. The browser handles reconnection, event parsing, and buffering automatically.

| | `fetch` | `EventSource` |
|---|---|---|
| Protocol | HTTP request-response | HTTP persistent connection |
| Partial data | No (waits for close) | Yes (each `data:` line fires an event) |
| Reconnection | Manual | Automatic |
| Method | POST or GET | GET only |
| Good for | `/generate` (full JSON response) | `/stream` (token-by-token SSE) |

Note: `EventSource` only supports GET requests. If your streaming endpoint requires POST (e.g., for a long request body), use the `fetch` Streams API instead (`response.body.getReader()`).

---

## BUILD IT

### Step 1: Project Structure

```
phases/06-shipping/10-minimal-typescript-frontend/code/
├── index.html      # HTML shell, imports compiled client.js
├── client.ts       # TypeScript source
├── client.js       # compiled output (tsc produces this)
└── tsconfig.json   # minimal TS config
```

No `package.json`. No `node_modules`. Just `tsc` to compile.

### Step 2: The HTML Shell

```html
<!-- code/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Frontend</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
    textarea { width: 100%; height: 80px; font-size: 1rem; padding: 0.5rem; box-sizing: border-box; }
    .btn-row { display: flex; gap: 0.5rem; margin: 0.5rem 0; }
    button { padding: 0.5rem 1rem; font-size: 1rem; cursor: pointer; }
    #output {
      white-space: pre-wrap;
      background: #f5f5f5;
      border-radius: 4px;
      padding: 1rem;
      min-height: 120px;
      margin-top: 1rem;
    }
    #error { color: #c00; margin-top: 0.5rem; font-size: 0.9rem; }
    .loading { opacity: 0.5; }
  </style>
</head>
<body>
  <h1>AI Frontend</h1>
  <textarea id="prompt" placeholder="Enter your prompt here..."></textarea>
  <div class="btn-row">
    <button id="btn-generate">Generate (sync)</button>
    <button id="btn-stream">Stream (SSE)</button>
    <button id="btn-clear">Clear</button>
  </div>
  <div id="error"></div>
  <div id="output">Output will appear here.</div>

  <!-- Import compiled TypeScript -->
  <script src="client.js"></script>
</body>
</html>
```

### Step 3: The TypeScript Client

```typescript
// code/client.ts

const API_BASE = "http://localhost:8000";

// DOM references
const promptEl = document.getElementById("prompt") as HTMLTextAreaElement;
const outputEl = document.getElementById("output") as HTMLDivElement;
const errorEl = document.getElementById("error") as HTMLDivElement;
const btnGenerate = document.getElementById("btn-generate") as HTMLButtonElement;
const btnStream = document.getElementById("btn-stream") as HTMLButtonElement;
const btnClear = document.getElementById("btn-clear") as HTMLButtonElement;

// --- Utilities ---

function setError(msg: string): void {
  errorEl.textContent = msg;
}

function clearError(): void {
  errorEl.textContent = "";
}

function setOutput(text: string): void {
  outputEl.textContent = text;
}

function appendOutput(text: string): void {
  outputEl.textContent += text;
}

function setLoading(loading: boolean): void {
  outputEl.classList.toggle("loading", loading);
  btnGenerate.disabled = loading;
  btnStream.disabled = loading;
}

// --- Sync Generate (fetch) ---

async function handleGenerate(): Promise<void> {
  const prompt = promptEl.value.trim();
  if (!prompt) {
    setError("Enter a prompt first.");
    return;
  }
  clearError();
  setOutput("");
  setLoading(true);

  try {
    const response = await fetch(`${API_BASE}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`HTTP ${response.status}: ${detail}`);
    }

    const data = await response.json() as { text: string };
    setOutput(data.text);
  } catch (err: unknown) {
    setError(err instanceof Error ? err.message : String(err));
  } finally {
    setLoading(false);
  }
}

// --- Streaming Generate (EventSource) ---

function handleStream(): void {
  const prompt = promptEl.value.trim();
  if (!prompt) {
    setError("Enter a prompt first.");
    return;
  }
  clearError();
  setOutput("");
  setLoading(true);

  // EventSource only supports GET. Pass prompt as query parameter.
  const url = `${API_BASE}/stream?prompt=${encodeURIComponent(prompt)}`;
  const source = new EventSource(url);

  source.onmessage = (event: MessageEvent) => {
    const data = event.data as string;
    if (data === "[DONE]") {
      source.close();
      setLoading(false);
      return;
    }
    appendOutput(data);
  };

  source.onerror = (_event: Event) => {
    source.close();
    setLoading(false);
    setError("Stream error. Check server is running at " + API_BASE);
  };
}

// --- Event listeners ---

btnGenerate.addEventListener("click", () => { void handleGenerate(); });
btnStream.addEventListener("click", handleStream);
btnClear.addEventListener("click", () => {
  setOutput("");
  clearError();
  promptEl.value = "";
});
```

> **Real-world check:** Why does `EventSource` require a GET request? The SSE specification in the browser uses a persistent GET connection. The server responds with `Content-Type: text/event-stream` and keeps the connection open, sending `data:` lines. POST is not supported by the native `EventSource` API. For streaming endpoints that need POST (long prompts, structured body), use `fetch` with `response.body.getReader()` and read the body as a stream manually.

### Step 4: tsconfig and compile

```json
// code/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM"],
    "strict": true,
    "outDir": ".",
    "rootDir": ".",
    "module": "None",
    "noEmit": false
  },
  "include": ["client.ts"]
}
```

Compile with:
```bash
tsc --project code/tsconfig.json
# Produces code/client.js
```

---

## USE IT

### Option A: Python http.server (no FastAPI change needed)

```bash
# From the code/ directory
python -m http.server 3000
# Open http://localhost:3000/index.html
```

This serves the static files. The TypeScript client calls FastAPI at `http://localhost:8000`. You need CORS enabled on your FastAPI app (see Phase 06 lesson 02).

### Option B: FastAPI static files mount

```python
# Add to your FastAPI app (main.py)
from fastapi.staticfiles import StaticFiles

# Mount after all API routes to avoid shadowing them
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")
# Access at http://localhost:8000/ui/
```

Copy `index.html` and `client.js` into a `frontend/` directory next to your `main.py`.

```python
# FastAPI /generate endpoint expected by the client
from pydantic import BaseModel

class GenerateRequest(BaseModel):
    prompt: str

@app.post("/generate")
async def generate(request: GenerateRequest) -> dict[str, str]:
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": request.prompt}],
    )
    return {"text": message.content[0].text}

# FastAPI /stream endpoint expected by the client
from fastapi.responses import StreamingResponse
import anthropic

@app.get("/stream")
async def stream(prompt: str) -> StreamingResponse:
    def generate_stream():
        with client.messages.stream(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {text}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
```

> **Perspective shift:** This entire frontend is 60 lines of TypeScript and 40 lines of HTML. For a prototype, internal tool, or demo, that is all you need. The value of vanilla TS is that every line is visible and debuggable in the browser DevTools Network tab. When streaming breaks, you open the Network inspector, click the `/stream` request, and watch the `data:` lines appear in real time. With a framework wrapping fetch and EventSource, that same debugging step requires knowing which abstraction swallowed the error.

---

## SHIP IT

The reusable artifact is `outputs/skill-ai-frontend-template.md`. It contains:
- The complete `index.html` and `client.ts` as copy-paste templates
- The FastAPI `/generate` and `/stream` endpoints they expect
- Notes on CORS and serving options

---

## EVALUATE IT

**Test 1: Compile cleanly.** Run `tsc --project code/tsconfig.json --noEmit`. Verify zero errors.

**Test 2: Sync generate.** Start the FastAPI backend. Open `index.html` in a browser, type a prompt, click "Generate (sync)." Verify the output div populates with the full response after a short delay.

**Test 3: Streaming.** Click "Stream (SSE)." Open DevTools Network tab, click the `/stream` request, observe the EventStream panel. Verify tokens appear one by one. Verify the DOM updates in real time.

**Test 4: Error display.** Stop the FastAPI server. Click "Generate." Verify the `#error` div shows a meaningful error message, not a blank screen or uncaught exception.

**Test 5: [DONE] sentinel.** Verify that after the stream ends, the loading state is cleared (buttons re-enabled, loading class removed) and no extra content appears after the final token.

**Test 6: CORS.** If serving the HTML from port 3000 and the API is on port 8000, verify the browser does not show CORS errors in the console. If it does, add `CORSMiddleware` to FastAPI with `allow_origins=["http://localhost:3000"]`.
