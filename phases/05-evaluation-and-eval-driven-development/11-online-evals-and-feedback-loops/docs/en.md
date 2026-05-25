**Type:** Build
**Languages:** Python
**Prerequisites:** 06-llm-as-judge, 08-eval-harnesses, 09-ci-for-prompts
**Time:** ~60 min
**Learning Objectives:**
- Build an async online eval pipeline that scores production traffic without adding user-facing latency
- Capture implicit feedback signals (thumbs up/down) and correlate them with LLM judge scores
- Implement a summary view that surfaces quality trends, failure rates, and flagged cases

---

## MOTTO

**Online evals are your production smoke detector: they don't prevent fires, but they tell you the building is burning before users start calling.**

---

## THE PROBLEM

You've built a golden set, wired up a CI eval, and you're confident your assistant passes before every deploy. Then a model provider silently updates their model at 2am on a Tuesday. Or your user base shifts from technical questions to customer service questions. Or a new type of input starts generating hallucinations you never anticipated.

Your offline evals miss all of this. They only know what you put in the golden set. Production is different: it's messy, unpredictable, and alive. You need a continuous signal on real traffic, not just a gating check on known cases.

The trap engineers fall into: they treat eval as a deployment gate instead of an ongoing instrument. Gate-only eval means your quality degrades silently for days or weeks before anyone notices. By the time the support tickets pile up, the damage is done.

Online evals run continuously against sampled production traffic, score it asynchronously (zero added latency for users), and feed that signal back into your improvement process. This is how production AI systems stay healthy.

---

## THE CONCEPT

### Offline vs Online Evals

```
OFFLINE EVAL                          ONLINE EVAL
--------------------                  --------------------
Runs on golden set                    Runs on real traffic
Runs before deploy (CI)               Runs continuously in prod
Synchronous (blocks deploy)           Asynchronous (no user latency)
Catches known failure modes           Catches unknown failure modes
You control the inputs                Users control the inputs
```

### The Async Eval Pipeline

```mermaid
flowchart LR
    U[User Request] --> API[FastAPI Handler]
    API --> R[Response to User]
    API --> Q[Eval Queue]
    Q --> W[Eval Worker]
    W --> J[LLM Judge]
    J --> L[Score Log]
    U2[User Feedback] --> F[/feedback endpoint]
    F --> L
    L --> S[Summary View]
```

The key architectural decision: the eval queue is fire-and-forget. The API handler enqueues the interaction and immediately returns the response to the user. The eval worker picks it up in the background. Users never wait for the eval.

### Sampling Strategy

Don't eval everything. A production system handling 10,000 requests per day at $0.02 per eval = $200/day just for eval. Instead:

```
SAMPLING STRATEGY
-----------------
Random sample:      5-10% of all traffic (baseline signal)
Edge case triggers: 100% of inputs matching risky patterns
                    (long inputs, unusual topics, low-confidence outputs)
Feedback-triggered: 100% of interactions with explicit thumbs-down
```

Target: 100+ scored evals per day minimum to detect a 10% quality drop within 24 hours.

### The Feedback Loop

Online evals are only useful if they close the loop:

```
score drops below threshold
        |
        v
    alert fires
        |
        v
  error analysis on flagged cases
        |
        v
  identify failure category
        |
        v
  add cases to golden set
        |
        v
  fix prompt or model config
        |
        v
  offline eval verifies fix
        |
        v
  deploy
        |
        v
  online eval confirms production improvement
```

### Implicit Signals

Even without an LLM judge, users give you signals:
- Thumbs up/down (explicit)
- Copy-paste rate (implicit: if they copy the answer, it was useful)
- Follow-up question immediately after (implicit: the first answer didn't work)
- Session abandon rate (implicit: left after a bad answer)

These are cheap to capture and correlate well with LLM judge scores when aggregated.

---

## BUILD IT

### Setup

```bash
uv init online-evals
cd online-evals
uv add fastapi uvicorn anthropic python-dotenv
```

Create `main.py`:

```python
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, date
from typing import Optional
from collections import defaultdict

import anthropic
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

app = FastAPI()
client = anthropic.Anthropic()

# In-memory queue (replace with Redis or SQS in production)
eval_queue: asyncio.Queue = asyncio.Queue()
score_log: list[dict] = []
```

### Step 1: The Request Handler

The handler returns the response first, then enqueues for eval. The user never waits for scoring.

```python
class QuestionRequest(BaseModel):
    question: str
    user_id: Optional[str] = None

class QuestionResponse(BaseModel):
    trace_id: str
    answer: str

async def call_model(question: str) -> str:
    """Call the model and return the answer."""
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": f"Answer this question concisely and accurately: {question}"
            }
        ]
    )
    return response.content[0].text

@app.post("/ask", response_model=QuestionResponse)
async def ask(request: QuestionRequest, background_tasks: BackgroundTasks):
    trace_id = str(uuid.uuid4())[:8]
    
    # Get the model response
    answer = await call_model(request.question)
    
    # Fire-and-forget: enqueue for background eval
    background_tasks.add_task(
        enqueue_for_eval,
        trace_id=trace_id,
        question=request.question,
        answer=answer,
    )
    
    # Return immediately -- user never waits for eval
    return QuestionResponse(trace_id=trace_id, answer=answer)
```

### Step 2: The Eval Worker

The eval worker picks up interactions from the queue and scores them with an LLM judge.

```python
JUDGE_PROMPT = """You are an eval judge. Score this AI response on a scale of 0.0 to 1.0.

Question: {question}
Answer: {answer}

Score on:
- Accuracy: is the answer factually correct?
- Completeness: does it address the full question?
- Conciseness: is it appropriately brief without losing content?

Return ONLY a JSON object: {{"score": 0.85, "rationale": "one sentence"}}"""

async def enqueue_for_eval(trace_id: str, question: str, answer: str):
    """Put an interaction on the eval queue."""
    await eval_queue.put({
        "trace_id": trace_id,
        "question": question,
        "answer": answer,
        "timestamp": datetime.utcnow().isoformat(),
    })

async def eval_worker():
    """Background worker: scores queued interactions."""
    print("Eval worker started")
    while True:
        try:
            interaction = await asyncio.wait_for(eval_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        
        # Score with LLM judge
        try:
            judge_response = client.messages.create(
                model="claude-haiku-4-5",  # cheaper model for judging
                max_tokens=128,
                messages=[
                    {
                        "role": "user",
                        "content": JUDGE_PROMPT.format(
                            question=interaction["question"],
                            answer=interaction["answer"],
                        )
                    }
                ]
            )
            result = json.loads(judge_response.content[0].text)
            score = float(result.get("score", 0.5))
            rationale = result.get("rationale", "")
        except Exception as e:
            print(f"Judge error for {interaction['trace_id']}: {e}")
            score = -1.0  # sentinel: eval failed
            rationale = str(e)
        
        # Write to score log
        log_entry = {
            "trace_id": interaction["trace_id"],
            "score": score,
            "rationale": rationale,
            "timestamp": interaction["timestamp"],
            "input": interaction["question"],
            "output": interaction["answer"],
            "source": "judge",
        }
        score_log.append(log_entry)
        
        # Also persist to file
        with open("score_log.jsonl", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        eval_queue.task_done()
        print(f"Scored {interaction['trace_id']}: {score:.2f}")

@app.on_event("startup")
async def startup_event():
    """Start the eval worker on app startup."""
    asyncio.create_task(eval_worker())
```

### Step 3: The Feedback Signal Endpoint

```python
class FeedbackRequest(BaseModel):
    trace_id: str
    thumbs_up: bool

@app.post("/feedback")
async def feedback(request: FeedbackRequest):
    """Capture explicit user feedback and append to the score log."""
    log_entry = {
        "trace_id": request.trace_id,
        "score": 1.0 if request.thumbs_up else 0.0,
        "rationale": "user feedback",
        "timestamp": datetime.utcnow().isoformat(),
        "input": None,
        "output": None,
        "source": "user_feedback",
    }
    score_log.append(log_entry)
    
    with open("score_log.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    return {"status": "recorded", "trace_id": request.trace_id}
```

### Step 4: The Summary View

```python
@app.get("/summary")
async def summary():
    """Read the score log and return today's quality summary."""
    today = date.today().isoformat()
    
    # Separate judge scores from user feedback
    judge_scores = [
        e["score"] for e in score_log
        if e["source"] == "judge" and e["score"] >= 0 and e["timestamp"].startswith(today)
    ]
    feedback_entries = [
        e for e in score_log
        if e["source"] == "user_feedback" and e["timestamp"].startswith(today)
    ]
    
    # Flag low-scoring cases for review
    flagged = [
        {"trace_id": e["trace_id"], "score": e["score"], "input": e["input"]}
        for e in score_log
        if e["source"] == "judge" and e["score"] < 0.5 and e["timestamp"].startswith(today)
    ]
    
    avg_score = sum(judge_scores) / len(judge_scores) if judge_scores else None
    thumbs_up_count = sum(1 for e in feedback_entries if e["score"] == 1.0)
    thumbs_up_rate = thumbs_up_count / len(feedback_entries) if feedback_entries else None
    
    return {
        "date": today,
        "judge_evals_today": len(judge_scores),
        "average_score": round(avg_score, 3) if avg_score else None,
        "thumbs_up_rate": round(thumbs_up_rate, 3) if thumbs_up_rate is not None else None,
        "flagged_cases": flagged,
        "alert": avg_score is not None and avg_score < 0.7,
    }
```

### Running It

```bash
uvicorn main:app --reload
```

Send a request:
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of France?"}'
# Returns immediately with trace_id and answer
# Background: eval worker scores it in ~2 seconds

# Give feedback
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{"trace_id": "abc12345", "thumbs_up": true}'

# Check summary
curl http://localhost:8000/summary
```

> **Real-world check:** Your online eval shows your LLM judge is scoring 200 production interactions per day at $0.02 each. That's $4/day or $1,460/year just for eval. What's your strategy to get the same signal at 10x lower cost?

The answer has three parts: (1) Sample more aggressively: 10% random sample instead of 100% = 20 evals/day for routine monitoring. (2) Use a cheaper judge model (Claude Haiku instead of Opus) for routine scoring, reserving the strong model for flagged cases. (3) Leverage implicit signals first: capture thumbs up/down and only trigger LLM-judge evals on thumbs-down or on statistically sampled traffic. You can get 80% of the signal at 5% of the cost.

---

## USE IT

The homegrown pipeline works but it has friction: no dashboard, no alerting, no aggregation across deployments. Langfuse solves all of this.

### Setup

```bash
uv add langfuse
```

```python
import os
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context

langfuse = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)
```

### Tracing with Langfuse

```python
@observe()  # automatically creates a trace
async def ask_with_langfuse(question: str) -> dict:
    trace_id = langfuse_context.get_current_trace_id()
    
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        messages=[{"role": "user", "content": question}]
    )
    answer = response.content[0].text
    
    return {"trace_id": trace_id, "answer": answer}
```

### Background Scoring with Langfuse

```python
async def score_with_langfuse(trace_id: str, question: str, answer: str):
    """Background task: run LLM judge and post score to Langfuse."""
    # Run your judge (same as before)
    judge_response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=128,
        messages=[{
            "role": "user",
            "content": JUDGE_PROMPT.format(question=question, answer=answer)
        }]
    )
    result = json.loads(judge_response.content[0].text)
    
    # Post score to Langfuse -- appears in dashboard immediately
    langfuse.score(
        trace_id=trace_id,
        name="llm-judge-quality",
        value=float(result["score"]),
        comment=result.get("rationale", ""),
    )
```

### Feedback Capture with Langfuse

```python
@app.post("/feedback")
async def feedback_langfuse(request: FeedbackRequest):
    """User feedback goes directly to Langfuse as a score."""
    langfuse.score(
        trace_id=request.trace_id,
        name="user-thumbs",
        value=1.0 if request.thumbs_up else 0.0,
        comment="explicit user feedback",
    )
    return {"status": "recorded"}
```

### What the Langfuse Dashboard Adds

The Langfuse UI gives you what the homegrown JSONL log can't:
- Time-series chart of average score by day, with percentile bands
- Score breakdown by model, prompt version, or user segment
- Drill-down from a trend drop to the individual traces that caused it
- Alerting rules (score < 0.7 for 3 hours = send Slack notification)
- Side-by-side trace comparison: what did the failing traces have in common?

### Homegrown vs Langfuse

```
HOMEGROWN PIPELINE          LANGFUSE
--------------------------  --------------------------
asyncio Queue               Managed queue, no infra
JSONL file                  Postgres-backed, queryable
Manual summary endpoint     Built-in dashboard + alerts
No drill-down               Trace viewer with full context
Works offline/air-gap       Requires network (or self-host)
Zero vendor dependency      Vendor dependency (open-source)
```

When to use homegrown: early prototypes, air-gapped environments, when you want full control over the eval logic.

When Langfuse earns its complexity: when you have multiple engineers, multiple models, multiple prompt versions, and you need shared visibility into production quality without building a monitoring platform.

> **Perspective shift:** You show your online eval dashboard to a product manager. They ask "why is the score 0.87 today but 0.79 on weekends?" What would cause this pattern, and what does it tell you about where to focus your improvements?

Weekend users are a different population. They might be less technical, more exploratory, or asking questions outside the core use case the system was trained for. The pattern tells you: your golden set is probably heavy on weekday-style queries. The fix isn't to make the model smarter in general: it's to analyze weekend failure traces, identify the failure category (out-of-scope questions? informal language? different topic distribution?), and add representative weekend cases to your golden set.

---

## SHIP IT

The artifact for this lesson is `outputs/skill-online-eval-pipeline.md`. See the outputs folder.

**What you built:**
- A FastAPI service with fire-and-forget background eval (zero user-facing latency)
- An LLM judge worker that scores interactions asynchronously
- A feedback signal endpoint that captures explicit user thumbs up/down
- A summary view that surfaces average score, thumbs-up rate, and flagged cases
- The same pipeline using Langfuse for production-grade monitoring

---

## EVALUATE IT

### Coverage

Is your sample rate high enough to detect a 10% quality drop within 24 hours?

Rule of thumb: 100 sampled evals per day is the minimum for reliable drift detection. If your traffic is 1,000 requests/day, a 10% sample rate hits that threshold. If traffic is lower, increase sample rate or use all traffic.

Verify: inject a synthetic quality drop (make your mock model return low-quality answers for 10% of requests), confirm the summary view shows a score drop within 24 hours.

### Latency Impact

The entire value proposition of async eval is zero user latency. Verify it:

```python
import time
import httpx

start = time.time()
response = httpx.post("http://localhost:8000/ask", json={"question": "test"})
latency = time.time() - start

# The eval should NOT add latency -- this should match your model call time only
print(f"User-facing latency: {latency:.3f}s")
```

The eval worker running in the background should not appear in this measurement.

### Judge Consistency

Run the same 20 cases through both your online judge and your offline CI judge. Score agreement within 10% is the target.

```python
def check_judge_consistency(cases: list[dict]) -> float:
    online_scores = [online_judge(c) for c in cases]
    offline_scores = [offline_judge(c) for c in cases]
    
    deltas = [abs(o - f) for o, f in zip(online_scores, offline_scores)]
    avg_delta = sum(deltas) / len(deltas)
    
    print(f"Average score delta: {avg_delta:.3f}")
    print(f"Max delta: {max(deltas):.3f}")
    return avg_delta

# Target: avg_delta < 0.10
```

If consistency is poor, your judge prompt is underspecified. Add a rubric with explicit criteria and score anchors (what does 0.5 look like? what does 0.9 look like?).
