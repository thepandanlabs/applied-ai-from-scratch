"""
Lesson 09 - Notebook vs. Script vs. Service
All three delivery formats for the same AI task in one file.

Run as a script:
    echo "Your text here" | python main.py

Run as a service:
    uvicorn main:app --port 8000
    curl -X POST http://localhost:8000/summarize -H "Content-Type: application/json" -d '{"text": "..."}'
"""

import anthropic
import os
import sys

# ─────────────────────────────────────────────
# SHARED: Core logic (same in all three formats)
# ─────────────────────────────────────────────

def get_client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set")
    return anthropic.Anthropic(api_key=key)


def summarize_text(client: anthropic.Anthropic, text: str) -> str:
    """Call the model and return a one-sentence summary."""
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        messages=[
            {
                "role": "user",
                "content": f"Summarize the following in one sentence:\n\n{text.strip()}"
            }
        ]
    )
    return response.content[0].text


# ─────────────────────────────────────────────
# FORMAT 2: Script (run directly, stdin input)
# ─────────────────────────────────────────────

def run_as_script() -> None:
    """Entry point when running: echo 'text' | python main.py"""
    text = sys.stdin.read().strip()
    if not text:
        print("Usage: echo 'your text' | python main.py", file=sys.stderr)
        sys.exit(1)

    client = get_client()
    summary = summarize_text(client, text)
    print(summary)


# ─────────────────────────────────────────────
# FORMAT 3: Service (FastAPI HTTP endpoint)
# Only loaded when running with uvicorn
# ─────────────────────────────────────────────

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    app = FastAPI(title="Summarizer Service")
    _client = get_client() if os.environ.get("ANTHROPIC_API_KEY") else None

    class SummarizeRequest(BaseModel):
        text: str

    class SummarizeResponse(BaseModel):
        summary: str

    @app.post("/summarize", response_model=SummarizeResponse)
    async def summarize_endpoint(req: SummarizeRequest) -> SummarizeResponse:
        if not req.text.strip():
            raise HTTPException(status_code=422, detail="text cannot be empty")
        if _client is None:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
        summary = summarize_text(_client, req.text)
        return SummarizeResponse(summary=summary)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

except ImportError:
    # FastAPI not installed; that is fine if running as a script
    app = None  # type: ignore


# ─────────────────────────────────────────────
# FORMAT 1: Notebook equivalent (inline demo)
# Shows what the notebook cells look like flattened
# ─────────────────────────────────────────────

def run_notebook_demo() -> None:
    """Simulate what a notebook session looks like, inline."""
    print("=== Notebook-style execution ===")
    print("(In a real notebook, each block below is a separate cell)")
    print()

    # Cell 1: Setup
    print("[Cell 1] Imports and client")
    client = get_client()
    print("  client ready")
    print()

    # Cell 2: Data
    print("[Cell 2] Input text")
    text = (
        "The transformer architecture, introduced in 2017, replaced recurrence "
        "with self-attention. This enabled parallel training across tokens, "
        "which unlocked much larger models and datasets. By 2020, these models "
        "generalized across tasks without task-specific fine-tuning."
    )
    print(f"  {text[:80]}...")
    print()

    # Cell 3: API call
    print("[Cell 3] Call the model")
    summary = summarize_text(client, text)
    print(f"  Summary: {summary}")
    print()
    print("Problem: to run this 'again tomorrow', you reopen Jupyter and")
    print("re-run cells in the right order. There is no main(), no CLI, no HTTP.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Summarizer in 3 formats")
    parser.add_argument(
        "--demo",
        choices=["notebook", "script"],
        default="script",
        help="notebook: inline demo of notebook-style execution; script: read from stdin"
    )
    args = parser.parse_args()

    if args.demo == "notebook":
        run_notebook_demo()
    else:
        run_as_script()
