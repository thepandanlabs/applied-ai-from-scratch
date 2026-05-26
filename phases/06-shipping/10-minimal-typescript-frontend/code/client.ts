/**
 * Lesson 10 - A Minimal TypeScript Frontend
 * Phase 06: Shipping
 *
 * Vanilla TypeScript client. No framework, no bundler, no node_modules.
 * Compile with: tsc --project tsconfig.json
 * Output: client.js (loaded by index.html)
 *
 * Calls two FastAPI endpoints:
 *   POST /generate  - sync, via fetch()
 *   GET  /stream    - SSE streaming, via EventSource
 */

const API_BASE = "http://localhost:8000";

// ---------------------------------------------------------------------------
// DOM references
// ---------------------------------------------------------------------------

const promptEl = document.getElementById("prompt") as HTMLTextAreaElement;
const outputEl = document.getElementById("output") as HTMLDivElement;
const errorEl = document.getElementById("error") as HTMLDivElement;
const btnGenerate = document.getElementById("btn-generate") as HTMLButtonElement;
const btnStream = document.getElementById("btn-stream") as HTMLButtonElement;
const btnClear = document.getElementById("btn-clear") as HTMLButtonElement;

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Sync Generate: uses fetch()
// fetch() waits for the FULL response body before resolving.
// Use this for short prompts where you want a clean JSON response.
// ---------------------------------------------------------------------------

interface GenerateResponse {
  text: string;
}

async function handleGenerate(): Promise<void> {
  const prompt = promptEl.value.trim();
  if (!prompt) {
    setError("Enter a prompt first.");
    return;
  }
  clearError();
  setOutput("Generating...");
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

    const data = (await response.json()) as GenerateResponse;
    setOutput(data.text);
  } catch (err: unknown) {
    setOutput("");
    setError(err instanceof Error ? err.message : String(err));
  } finally {
    setLoading(false);
  }
}

// ---------------------------------------------------------------------------
// Streaming Generate: uses EventSource
// EventSource maintains a persistent GET connection and fires onmessage
// for each "data: " line the server sends. Tokens appear as they arrive.
//
// Important: EventSource is GET-only. The prompt is a query parameter.
// For POST streaming, use fetch() + response.body.getReader() instead.
// ---------------------------------------------------------------------------

function handleStream(): void {
  const prompt = promptEl.value.trim();
  if (!prompt) {
    setError("Enter a prompt first.");
    return;
  }
  clearError();
  setOutput("");
  setLoading(true);

  const url = `${API_BASE}/stream?prompt=${encodeURIComponent(prompt)}`;
  const source = new EventSource(url);

  source.onmessage = (event: MessageEvent<string>) => {
    const data = event.data;

    // Server sends "data: [DONE]" to signal stream end
    if (data === "[DONE]") {
      source.close();
      setLoading(false);
      return;
    }

    // Append each token to the output div as it arrives
    appendOutput(data);
  };

  source.onerror = (_event: Event) => {
    source.close();
    setLoading(false);
    if (outputEl.textContent === "") {
      setError(`Stream error. Is the server running at ${API_BASE}?`);
    }
    // If some content arrived before the error, do not overwrite it.
    // The stream may have ended cleanly but the EventSource re-tries.
  };
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------

btnGenerate.addEventListener("click", () => {
  void handleGenerate();
});

btnStream.addEventListener("click", handleStream);

btnClear.addEventListener("click", () => {
  setOutput("");
  clearError();
  promptEl.value = "";
});
