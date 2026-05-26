"""
Lesson 09 - Background Jobs and Batch APIs
Phase 06: Shipping

Demonstrates two async LLM patterns:
1. In-memory job queue with FastAPI BackgroundTasks (POST job, poll GET /jobs/{id})
2. Anthropic Batch API for bulk requests at 50% cost discount

Run:
    uv pip install fastapi uvicorn anthropic httpx
    ANTHROPIC_API_KEY=sk-... uvicorn main:app --reload
"""
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

import anthropic
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Background Jobs Demo", version="1.0.0")
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# In-memory store.
# In production, replace with Redis (job queue) or Postgres (job records).
jobs: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class GenerateRequest(BaseModel):
    text: str
    instruction: str = "Summarize the following in one paragraph."


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    result: str | None = None
    error: str | None = None
    created_at: str
    completed_at: str | None = None


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


def run_generation(job_id: str, text: str, instruction: str) -> None:
    """
    Blocking Anthropic call. FastAPI BackgroundTasks runs this in a thread pool
    so it does not block the event loop.
    Updates the jobs store when complete.
    """
    jobs[job_id]["status"] = JobStatus.running
    try:
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": f"{instruction}\n\n{text}",
                }
            ],
        )
        jobs[job_id]["status"] = JobStatus.done
        jobs[job_id]["result"] = message.content[0].text
        jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()
    except Exception as exc:
        jobs[job_id]["status"] = JobStatus.failed
        jobs[job_id]["error"] = str(exc)
        jobs[job_id]["completed_at"] = datetime.utcnow().isoformat()


# ---------------------------------------------------------------------------
# Job queue endpoints
# ---------------------------------------------------------------------------


@app.post("/jobs", response_model=JobResponse, status_code=202)
async def create_job(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """
    Accept work, return job_id immediately (HTTP 202), start worker in background.
    The client must poll GET /jobs/{job_id} to retrieve the result.
    """
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.pending,
        "result": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": None,
    }
    background_tasks.add_task(run_generation, job_id, request.text, request.instruction)
    return JobResponse(**jobs[job_id])


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """
    Poll this endpoint to check job status and retrieve the result.

    Status transitions: pending -> running -> done | failed
    Poll every 2-5 seconds. Stop when status is 'done' or 'failed'.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return JobResponse(**jobs[job_id])


@app.get("/jobs", response_model=list[JobResponse])
async def list_jobs() -> list[JobResponse]:
    """List all jobs. Useful for debugging; paginate in production."""
    return [JobResponse(**job) for job in jobs.values()]


# ---------------------------------------------------------------------------
# Anthropic Batch API endpoints
# ---------------------------------------------------------------------------


@app.post("/batch", status_code=202)
async def create_batch(texts: list[str]) -> dict[str, Any]:
    """
    Submit up to 10,000 texts to the Anthropic Batch API.
    Returns a batch_id. Results arrive within 24 hours at 50% cost discount.

    Request body: ["text1", "text2", ...]
    """
    if not texts:
        raise HTTPException(status_code=400, detail="texts list must not be empty")
    if len(texts) > 10_000:
        raise HTTPException(status_code=400, detail="Batch API limit is 10,000 requests")

    requests_list = [
        {
            "custom_id": f"item-{i}",
            "params": {
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 256,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Summarize in one sentence: {text}",
                    }
                ],
            },
        }
        for i, text in enumerate(texts)
    ]

    batch = client.messages.batches.create(requests=requests_list)
    return {
        "batch_id": batch.id,
        "status": batch.processing_status,
        "request_count": len(texts),
    }


@app.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str) -> dict[str, Any]:
    """
    Poll for batch completion. When status is 'ended', results are included.

    processing_status values: 'in_progress' | 'canceling' | 'ended'
    Poll every 30-60 seconds. Batches typically complete within a few minutes
    for small batches, up to 24 hours for very large ones.
    """
    batch = client.messages.batches.retrieve(batch_id)

    if batch.processing_status != "ended":
        return {
            "batch_id": batch_id,
            "status": batch.processing_status,
            "request_counts": batch.request_counts.model_dump(),
        }

    # Batch ended. Stream results and collect.
    results: dict[str, str] = {}
    errors: dict[str, str] = {}

    for result in client.messages.batches.results(batch_id):
        if result.result.type == "succeeded":
            results[result.custom_id] = result.result.message.content[0].text
        else:
            errors[result.custom_id] = (
                result.result.error.type
                if hasattr(result.result, "error")
                else "unknown_error"
            )

    return {
        "batch_id": batch_id,
        "status": "ended",
        "succeeded": len(results),
        "errored": len(errors),
        "results": results,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Demo client (run as a script to test without a real server)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import time

    import httpx

    BASE = "http://localhost:8000"

    print("=== Demo: Job Pattern ===")
    resp = httpx.post(f"{BASE}/jobs", json={"text": "FastAPI is a modern Python web framework."})
    print(f"POST /jobs -> {resp.status_code}")
    data = resp.json()
    job_id = data["job_id"]
    print(f"Job ID: {job_id}, Status: {data['status']}")

    for attempt in range(15):
        time.sleep(3)
        r = httpx.get(f"{BASE}/jobs/{job_id}")
        status = r.json()["status"]
        print(f"  Poll {attempt + 1}: {status}")
        if status in ("done", "failed"):
            print(f"  Result: {r.json().get('result') or r.json().get('error')}")
            break

    print("\n=== Demo: Batch API ===")
    texts = [
        "Python is a high-level programming language.",
        "FastAPI is built on Starlette and Pydantic.",
        "Anthropic builds AI safety research.",
    ]
    resp = httpx.post(f"{BASE}/batch", json=texts)
    print(f"POST /batch -> {resp.status_code}")
    batch_data = resp.json()
    batch_id = batch_data["batch_id"]
    print(f"Batch ID: {batch_id}")

    for attempt in range(10):
        time.sleep(30)
        r = httpx.get(f"{BASE}/batch/{batch_id}")
        data = r.json()
        print(f"  Poll {attempt + 1}: {data['status']}")
        if data["status"] == "ended":
            for cid, result in data["results"].items():
                print(f"  {cid}: {result[:80]}...")
            break
