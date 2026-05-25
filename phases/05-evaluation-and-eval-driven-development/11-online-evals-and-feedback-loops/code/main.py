"""
Lesson 11: Online Evals & Production Feedback Loops
----------------------------------------------------
Async online eval pipeline:
- FastAPI endpoint that returns immediately while queuing eval in background
- LLM judge worker that scores interactions asynchronously
- Feedback signal endpoint for explicit user thumbs up/down
- Summary view: average score, thumbs-up rate, flagged cases

Run:
    uv run uvicorn main:app --reload

Test:
    curl -X POST http://localhost:8000/ask \
        -H "Content-Type: application/json" \
        -d '{"question": "What is the capital of France?"}'

    curl -X POST http://localhost:8000/feedback \
        -H "Content-Type: application/json" \
        -d '{"trace_id": "YOUR_TRACE_ID", "thumbs_up": true}'

    curl http://localhost:8000/summary
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, date
from typing import Optional

import anthropic
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

app = FastAPI(title="FAQ Assistant with Online Eval")
client = anthropic.Anthropic()

# In-memory queue and log (replace with Redis + DB in production)
eval_queue: asyncio.Queue = asyncio.Queue()
score_log: list[dict] = []

SCORE_LOG_FILE = "score_log.jsonl"

JUDGE_PROMPT = """You are an eval judge. Score this AI response on a scale of 0.0 to 1.0.

Question: {question}
Answer: {answer}

Score on:
- Accuracy: is the answer factually correct?
- Completeness: does it address the full question?
- Conciseness: is it appropriately brief without losing content?

Return ONLY a JSON object: {{"score": 0.85, "rationale": "one sentence"}}"""


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QuestionRequest(BaseModel):
    question: str
    user_id: Optional[str] = None


class QuestionResponse(BaseModel):
    trace_id: str
    answer: str


class FeedbackRequest(BaseModel):
    trace_id: str
    thumbs_up: bool


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------

async def call_model(question: str) -> str:
    """Call the primary model and return the answer."""
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": f"Answer this question concisely and accurately: {question}",
            }
        ],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Eval worker
# ---------------------------------------------------------------------------

async def enqueue_for_eval(trace_id: str, question: str, answer: str) -> None:
    """Put an interaction on the eval queue (fire-and-forget from the API handler)."""
    await eval_queue.put(
        {
            "trace_id": trace_id,
            "question": question,
            "answer": answer,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


async def eval_worker() -> None:
    """Background worker: picks up queued interactions and scores them."""
    print("[eval-worker] started")
    while True:
        try:
            interaction = await asyncio.wait_for(eval_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        try:
            judge_response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=128,
                messages=[
                    {
                        "role": "user",
                        "content": JUDGE_PROMPT.format(
                            question=interaction["question"],
                            answer=interaction["answer"],
                        ),
                    }
                ],
            )
            result = json.loads(judge_response.content[0].text)
            score = float(result.get("score", 0.5))
            rationale = result.get("rationale", "")
        except Exception as exc:
            print(f"[eval-worker] judge error for {interaction['trace_id']}: {exc}")
            score = -1.0  # sentinel: eval failed
            rationale = str(exc)

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

        with open(SCORE_LOG_FILE, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        eval_queue.task_done()
        print(f"[eval-worker] scored {interaction['trace_id']}: {score:.2f}")


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event() -> None:
    """Start the eval worker as a background task on app startup."""
    asyncio.create_task(eval_worker())


@app.post("/ask", response_model=QuestionResponse)
async def ask(request: QuestionRequest, background_tasks: BackgroundTasks):
    """
    Handle a user question. Returns immediately -- the eval runs in the background.
    The user never waits for the eval to complete.
    """
    trace_id = str(uuid.uuid4())[:8]
    answer = await call_model(request.question)

    # Fire-and-forget: enqueue for background eval
    background_tasks.add_task(
        enqueue_for_eval,
        trace_id=trace_id,
        question=request.question,
        answer=answer,
    )

    return QuestionResponse(trace_id=trace_id, answer=answer)


@app.post("/feedback")
async def feedback(request: FeedbackRequest):
    """
    Capture explicit user feedback (thumbs up/down).
    Appends to the score log as a user_feedback source.
    """
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

    with open(SCORE_LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    return {"status": "recorded", "trace_id": request.trace_id}


@app.get("/summary")
async def summary():
    """
    Daily quality summary: average score, thumbs-up rate, flagged cases.
    Reads from the in-memory score_log (or the persisted JSONL on startup).
    """
    # Load persisted logs on first call if in-memory is empty
    if not score_log and os.path.exists(SCORE_LOG_FILE):
        with open(SCORE_LOG_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    score_log.append(json.loads(line))

    today = date.today().isoformat()

    judge_scores = [
        e["score"]
        for e in score_log
        if e["source"] == "judge"
        and e["score"] >= 0
        and e["timestamp"].startswith(today)
    ]
    feedback_entries = [
        e
        for e in score_log
        if e["source"] == "user_feedback" and e["timestamp"].startswith(today)
    ]
    flagged = [
        {"trace_id": e["trace_id"], "score": e["score"], "input": e["input"]}
        for e in score_log
        if e["source"] == "judge"
        and 0 <= e["score"] < 0.5
        and e["timestamp"].startswith(today)
    ]

    avg_score = sum(judge_scores) / len(judge_scores) if judge_scores else None
    thumbs_up_count = sum(1 for e in feedback_entries if e["score"] == 1.0)
    thumbs_up_rate = (
        thumbs_up_count / len(feedback_entries) if feedback_entries else None
    )

    return {
        "date": today,
        "judge_evals_today": len(judge_scores),
        "average_score": round(avg_score, 3) if avg_score is not None else None,
        "thumbs_up_rate": (
            round(thumbs_up_rate, 3) if thumbs_up_rate is not None else None
        ),
        "flagged_cases": flagged,
        "alert": avg_score is not None and avg_score < 0.7,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "queue_size": eval_queue.qsize()}
