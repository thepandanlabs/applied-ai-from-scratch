---
name: skill-ai-frontend-template
description: vanilla TypeScript and HTML template for calling FastAPI sync and streaming AI endpoints
version: "1.0"
phase: "06"
lesson: "10"
tags: [frontend, typescript, sse, eventsource, streaming, fastapi]
---

# AI Frontend Template

## When to use this template

- Internal tools, demos, and prototypes that need a UI
- No framework required: React/Vue add complexity without value at this scale
- Vanilla TypeScript is debuggable directly in browser DevTools

## Project layout

```
frontend/
├── index.html        # HTML shell
├── client.ts         # TypeScript source (edit this)
├── client.js         # Compiled output (tsc produces this, commit it or .gitignore)
└── tsconfig.json     # Minimal TS config
```

## index.html (minimal shell)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>AI App</title>
</head>
<body>
  <textarea id="prompt" placeholder="Enter prompt..."></textarea>
  <button id="btn-generate">Generate</button>
  <button id="btn-stream">Stream</button>
  <div id="error"></div>
  <div id="output"></div>
  <script src="client.js"></script>
</body>
</html>
```

## client.ts (copy-paste ready)

```typescript
const API_BASE = "http://localhost:8000";

const promptEl = document.getElementById("prompt") as HTMLTextAreaElement;
const outputEl = document.getElementById("output") as HTMLDivElement;
const errorEl  = document.getElementById("error")  as HTMLDivElement;

// --- Sync: fetch ---
async function generate(): Promise<void> {
  clearError();
  outputEl.textContent = "";
  const response = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt: promptEl.value.trim() }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = (await response.json()) as { text: string };
  outputEl.textContent = data.text;
}

// --- Streaming: EventSource ---
function streamGenerate(): void {
  clearError();
  outputEl.textContent = "";
  const url = `${API_BASE}/stream?prompt=${encodeURIComponent(promptEl.value.trim())}`;
  const source = new EventSource(url);
  source.onmessage = (e: MessageEvent<string>) => {
    if (e.data === "[DONE]") { source.close(); return; }
    outputEl.textContent += e.data;
  };
  source.onerror = () => { source.close(); setError("Stream error."); };
}

function setError(msg: string): void { errorEl.textContent = msg; }
function clearError(): void         { errorEl.textContent = ""; }

document.getElementById("btn-generate")!
  .addEventListener("click", () => { void generate(); });
document.getElementById("btn-stream")!
  .addEventListener("click", streamGenerate);
```

## tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM"],
    "strict": true,
    "outDir": ".",
    "rootDir": ".",
    "module": "None"
  },
  "include": ["client.ts"]
}
```

Compile: `tsc --project tsconfig.json`

## FastAPI endpoints the client expects

### POST /generate (sync)

```python
from pydantic import BaseModel
import anthropic, os

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

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
```

### GET /stream (SSE)

```python
from fastapi.responses import StreamingResponse

@app.get("/stream")
async def stream(prompt: str) -> StreamingResponse:
    def generate_stream():
        with client.messages.stream(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ) as s:
            for text in s.text_stream:
                yield f"data: {text.replace(chr(10), ' ')}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### CORS (required for cross-origin dev)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # or ["*"] for dev
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

## Serving options

| Method | Command | When to use |
|---|---|---|
| Python http.server | `python -m http.server 3000 --directory frontend/` | Local dev, no FastAPI change |
| FastAPI static files | `app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")` | Single-port deploy |
| nginx | `location /ui { root /srv/frontend; }` | Production |

## fetch vs EventSource decision

| Requirement | Use |
|---|---|
| Need full response as JSON | `fetch` POST |
| Tokens appear as they arrive | `EventSource` GET |
| Streaming but need POST body | `fetch` + `response.body.getReader()` |
| Bidirectional real-time | WebSocket |
