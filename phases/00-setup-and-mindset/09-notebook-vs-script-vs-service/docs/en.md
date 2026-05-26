# Notebook vs. Script vs. Service

> The format you use to build an AI feature determines how hard it is to ship it.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Lesson 03 (first API call), Lesson 08 (Docker basics)
**Time:** ~30 min
**Learning Objectives:**
- Name the three delivery formats for AI work and their primary use case
- Identify the trigger conditions that should cause a promotion from one format to the next
- Implement the same AI task in all three formats and feel the difference in structure
- Avoid the notebook trap: staying in exploration mode past the point it is useful

---

## The Problem

A data scientist spends two weeks building a document summarizer in a Jupyter notebook. The notebook works. It calls the API, processes PDFs, and produces clean summaries. The VP of Engineering asks: "Can we put this in the product?"

The answer takes four more weeks. The notebook has to be rewritten as a service. Half of the logic is in random cells that were run in a non-linear order. There are no tests. Error handling was never added because re-running a cell was easier. The API key is hardcoded. There is no way to call it without opening Jupyter.

This is the notebook-to-production gap, and it kills AI demos regularly. The problem is not that notebooks are bad. It is that the team used a notebook past its natural expiration date.

The three formats each have a home: notebooks for exploration, scripts for repeatability, services for production. Knowing when to graduate from one to the next is a core applied AI engineering skill.

---

## The Concept

### The Three Formats

```
FORMAT        PRIMARY USE             EXPIRES WHEN...
-----------   ---------------------   ----------------------------------
Notebook      Exploration, demos,     You need to run it on a schedule,
              stakeholder review      share it as an API, or run it
                                      more than once without opening
                                      Jupyter

Script        Repeatable pipeline,    More than one user needs to call
              scheduled jobs,         it simultaneously, or it needs to
              CLI tools               stay alive between requests

Service       Persistent endpoint,    Never expires (this is the final
              multi-user, production  form for production AI features)
```

### The Decision Tree

```
Start here: What are you actually building?
         │
         ▼
Is this for exploration, one-off analysis, or a stakeholder demo?
    │
    ├── YES → Notebook
    │         Trigger to upgrade: "I need to run this again"
    │         or "I need to share this as an API"
    │
    └── NO
         │
         ▼
    Does a single person need to run it on demand, on a schedule,
    or from the command line?
         │
         ├── YES → Script
         │         Trigger to upgrade: "Multiple users need to call this"
         │         or "It needs to be always available"
         │
         └── NO
              │
              ▼
         Multiple users, persistent availability, or
         integration into another system → Service
```

### What Changes at Each Promotion

```
Notebook → Script        Script → Service
------------------       ------------------
Remove notebook cells    Add HTTP interface
Add main() function      Add async handling
Add error handling        Add concurrency
Add CLI args or config   Add health check
Move hardcoded values    Add logging to stdout
  to env vars            Add Docker container
```

---

## Build It

### The Task: Summarize a Document in All Three Formats

Use the same AI task across all three implementations: summarize a short text passage. The task is identical. The delivery format changes everything else.

**Format 1: Notebook cell**

In a Jupyter notebook, this is typically a few cells:

```python
# Cell 1: Imports and client setup
import anthropic
import os

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
```

```python
# Cell 2: The text to summarize (often copy-pasted in directly)
text = """
The transformer architecture, introduced in 2017, replaced recurrence
with self-attention. This enabled parallel training across tokens,
which unlocked much larger models and datasets. By 2020, these models
generalized across tasks without task-specific fine-tuning.
"""
```

```python
# Cell 3: The API call
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=128,
    messages=[{"role": "user", "content": f"Summarize in one sentence:\n\n{text}"}]
)
print(response.content[0].text)
```

This works. You can show it in a meeting. You can re-run Cell 3. But if you close Jupyter and come back tomorrow, you need to remember which cells to run in which order.

**Format 2: Script (`main.py`)**

```python
import anthropic
import os
import sys

def summarize(text: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        messages=[{"role": "user", "content": f"Summarize in one sentence:\n\n{text}"}]
    )
    return response.content[0].text

def main() -> None:
    text = sys.stdin.read().strip()
    if not text:
        print("Usage: echo 'your text' | python main.py", file=sys.stderr)
        sys.exit(1)
    print(summarize(text))

if __name__ == "__main__":
    main()
```

Run it:
```bash
echo "The transformer architecture..." | python main.py
```

Now it is a tool. Repeatable. Anyone on the team can run it. You can put it in a cron job. You can pipe text into it from another script. It is still one function away from a test.

**Format 3: Service (`main.py` with FastAPI)**

```python
import anthropic
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

class SummarizeRequest(BaseModel):
    text: str

class SummarizeResponse(BaseModel):
    summary: str

@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(req: SummarizeRequest) -> SummarizeResponse:
    if not req.text.strip():
        raise HTTPException(status_code=422, detail="text cannot be empty")
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        messages=[{"role": "user", "content": f"Summarize in one sentence:\n\n{req.text}"}]
    )
    return SummarizeResponse(summary=response.content[0].text)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

Run it:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Call it:
```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"text": "The transformer architecture..."}'
```

Now it is always-on. Any system can call it over HTTP. Multiple users can hit it simultaneously. You can containerize it (Lesson 08) and deploy it to any cloud.

> **Real-world check:** A product manager asks: "Can't we just run the notebook for now and migrate later?" Sometimes yes. But "migrate later" reliably takes 4x longer than "write it as a script from the start." The notebook form accumulates technical debt that is invisible until someone tries to run it headlessly. If there is any chance you will run it more than twice, write a script.

---

## Use It

The production graduation criteria are simple. Bookmark this table.

| You need this... | Use this format |
|-----------------|----------------|
| Explore, prototype, explain to stakeholders | Notebook |
| Run it on a schedule, pipe it in a bash script, share with one engineer | Script |
| HTTP API, multiple concurrent users, always-on, containerized | Service |

The progression is one-way in practice. You never go from a service back to a notebook for a production feature. The code for the lesson (`code/main.py`) shows all three patterns in a single file you can run to compare them directly.

> **Perspective shift:** A backend engineer asks: "Why use a notebook at all? I would just write a script from the start." For well-specified problems, that is correct. Notebooks earn their place when you are genuinely unsure what the right approach is. They let you try five embedding models in five cells and compare results visually, without the discipline of a clean function boundary. The cost is that the exploration mindset sticks around longer than it should. The best applied AI engineers know when to close the notebook and open `main.py`.

---

## Ship It

The reusable artifact for this lesson is `outputs/prompt-delivery-format-decision.md`: a decision guide you can paste into any project to determine the right format for an AI feature.

See `outputs/prompt-delivery-format-decision.md`.

---

## Evaluate It

**Can the script run without Jupyter?**

```bash
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY echo "Test text" | python code/main.py
```

If it exits 0 and prints a summary, the script format is working.

**Does the service handle concurrent requests?**

```bash
# Start the service
uvicorn code.main:app --port 8000 &

# Fire 5 concurrent requests
for i in {1..5}; do
  curl -s -X POST http://localhost:8000/summarize \
    -H "Content-Type: application/json" \
    -d '{"text": "Short test text number '"$i"'."}' &
done
wait
```

All 5 should return successfully. If any hang or error, concurrency handling needs work.

**Is the service format truly more ops-ready?**

Measure the time to answer "is the service healthy?" for each format:

- Notebook: open Jupyter, run cells, observe output - minutes
- Script: `python main.py --health-check` - seconds
- Service: `curl http://localhost:8000/health` - milliseconds, automatable

The service format wins on observability. The health endpoint is a first-class signal that load balancers, CI pipelines, and on-call tools all understand.
