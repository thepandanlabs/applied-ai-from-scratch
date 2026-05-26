# Background Jobs and Batch APIs

> If the user does not need the answer in the next 500ms, do not make them wait for it.

**Type:** Build
**Languages:** Python
**Prerequisites:** 02-wrapping-model-in-fastapi, 03-streaming-sse-async
**Time:** ~45 min
**Learning Objectives:**
- Implement an in-memory async job queue with FastAPI BackgroundTasks
- Return a job_id immediately and expose a poll endpoint
- Send 100+ requests to the Anthropic Batch API in one call and retrieve results
- Decide when async job pattern is required vs when sync is fine

---

## MOTTO

**Every LLM request that does not need a real-time answer is a candidate for the async job pattern.**

---

## THE PROBLEM

You built a FastAPI endpoint that calls the Anthropic API and returns the response. It works perfectly for single requests. Then your product team asks for a bulk enrichment feature: given a CSV of 500 company descriptions, generate a one-paragraph summary for each.

You do what feels natural: loop over the CSV, call your `/generate` endpoint 500 times. Three minutes later your load balancer times out. The user sees an error. Your API logs are full of 30-second request durations. Your Anthropic rate limit alarm fires.

The root problem is a mismatch between what the user needs (results, eventually) and what your endpoint does (blocks the connection until done). For bulk or long-running LLM tasks, synchronous HTTP is the wrong tool. You need two things:

1. An async job pattern: accept the work, return an ID, let the client poll for results.
2. The Anthropic Batch API: send up to 10,000 requests in one call, get results within 24 hours at 50% cost discount.

The job pattern fixes the latency problem. The Batch API fixes the cost and throughput problem. Together they are the correct architecture for any non-realtime bulk LLM workload.

---

## THE CONCEPT

### Sync vs Async: The Core Trade-off

```
SYNCHRONOUS (blocks until done)
                                                  
  Client        FastAPI        Anthropic API      
    |               |               |             
    |---POST /gen-->|               |             
    |               |---API call--->|             
    |               |  (5-30 sec)   |             
    |               |<--response----|             
    |<---200 OK-----|               |             
    |  (client waits entire time)   |             
                                                  
  Problem: 30-second connections, load balancer   
  timeouts, poor UX, no retry-on-failure path     


ASYNC JOB PATTERN (returns immediately)
                                                  
  Client        FastAPI        Worker     Anthropic
    |               |               |         |   
    |---POST /jobs->|               |         |   
    |<--202 {job_id}|               |         |   
    |  (instant)    |               |         |   
    |               |--enqueue----->|         |   
    |               |               |-API---->|   
    |---GET /jobs/id|               |  call   |   
    |<--{status:pnd}|               |         |   
    |               |               |<-result-|   
    |---GET /jobs/id|               |         |   
    |<--{status:done, result:...}   |         |   
                                                  
  Benefit: client never blocks, worker retries    
  independently, scales to 1000s of requests      
```

### The Anthropic Batch API

The Batch API is a separate surface from the standard Messages API. Key differences:

| Property | Standard API | Batch API |
|---|---|---|
| Latency | 1-30 seconds | Up to 24 hours |
| Cost | 1x | 0.5x (50% discount) |
| Max requests per batch | 1 | 10,000 |
| Retrieval | Streaming or sync | Poll for completion, then download |
| Best for | Realtime user-facing | Bulk enrichment, nightly jobs, evals |

The lifecycle has three steps: create batch, poll status, retrieve results. Results arrive as a JSONL file where each line maps a `custom_id` back to the response.

### When to Use Each Pattern

```
Request arrives
       |
       v
Is the user waiting for the response in the UI?
       |
      YES --> use sync endpoint (Phase 06 lessons 2-3)
       |
       NO --> is it a one-off background task (< 5 items)?
               |
              YES --> FastAPI BackgroundTasks (simple, no queue)
               |
               NO --> is it a bulk job (10s-1000s of items)?
                       |
                      YES --> Anthropic Batch API
                       |
                       NO --> async job queue with worker pool
```

---

## BUILD IT

### Step 1: In-Memory Job Queue with FastAPI BackgroundTasks

```python
# code/main.py
import asyncio
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

import anthropic
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Background Jobs Demo")
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# In-memory store. Replace with Redis or a DB in production.
jobs: dict[str, dict[str, Any]] = {}


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
```

### Step 2: The Background Worker Function

```python
def run_generation(job_id: str, text: str, instruction: str) -> None:
    """Runs in the background. Updates job store when complete."""
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
```

### Step 3: The POST and GET Endpoints

```python
@app.post("/jobs", response_model=JobResponse, status_code=202)
async def create_job(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """Accept work, return job_id immediately, start worker in background."""
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
    """Poll this endpoint to check job status and retrieve result."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**jobs[job_id])


@app.get("/jobs")
async def list_jobs() -> list[JobResponse]:
    """List all jobs (useful for debugging)."""
    return [JobResponse(**job) for job in jobs.values()]
```

> **Real-world check:** Why does the POST endpoint return HTTP 202 instead of 200? In HTTP semantics, 200 means "done," and 202 means "accepted for processing." Returning 202 tells the client explicitly that the request was received but the work is not finished. API gateways, load balancers, and client SDKs often treat 200 and 202 differently for retry logic. Always use 202 for async job creation.

### Step 4: The Anthropic Batch API Pattern

```python
@app.post("/batch", status_code=202)
async def create_batch(texts: list[str]) -> dict[str, str]:
    """Submit a batch of texts to the Anthropic Batch API."""
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
    return {"batch_id": batch.id, "status": batch.processing_status}


@app.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str) -> dict[str, Any]:
    """Poll for batch completion status."""
    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        return {
            "batch_id": batch_id,
            "status": batch.processing_status,
            "request_counts": batch.request_counts.model_dump(),
        }
    # Batch is done, retrieve results
    results = {}
    for result in client.messages.batches.results(batch_id):
        if result.result.type == "succeeded":
            results[result.custom_id] = result.result.message.content[0].text
        else:
            results[result.custom_id] = f"error: {result.result.error}"
    return {
        "batch_id": batch_id,
        "status": "ended",
        "results": results,
    }
```

---

## USE IT

Compare the two patterns on a concrete task: generating summaries for 20 product descriptions.

```python
import httpx
import time

BASE = "http://localhost:8000"

# Pattern 1: Async job queue (submit then poll)
def demo_job_pattern(description: str) -> str:
    # Submit
    resp = httpx.post(f"{BASE}/jobs", json={"text": description})
    job_id = resp.json()["job_id"]
    print(f"Job created: {job_id}")

    # Poll with backoff
    for _ in range(30):
        time.sleep(2)
        status_resp = httpx.get(f"{BASE}/jobs/{job_id}")
        data = status_resp.json()
        if data["status"] == "done":
            return data["result"]
        if data["status"] == "failed":
            raise RuntimeError(data["error"])
    raise TimeoutError("Job did not complete in 60 seconds")


# Pattern 2: Batch API (submit batch, poll until ended)
def demo_batch_pattern(descriptions: list[str]) -> dict[str, str]:
    # Submit
    resp = httpx.post(f"{BASE}/batch", json=descriptions)
    batch_id = resp.json()["batch_id"]
    print(f"Batch created: {batch_id}")

    # Poll
    for _ in range(20):
        time.sleep(30)
        status_resp = httpx.get(f"{BASE}/batch/{batch_id}")
        data = status_resp.json()
        if data["status"] == "ended":
            return data["results"]
        print(f"Batch status: {data['status']}, counts: {data.get('request_counts')}")
    raise TimeoutError("Batch did not complete in 10 minutes")
```

> **Perspective shift:** The job queue and the Batch API look similar on the surface (submit, get id, poll), but they serve different scales. The job queue is for tasks your service owns: each job is a few seconds of work, and you want results in under a minute. The Batch API is for sending 100-10,000 LLM calls to Anthropic at once, with results arriving hours later. Think of it like same-day delivery vs overnight freight. One is for when your customer is watching; the other is for nightly pipelines where cost-per-unit is the only metric that matters.

---

## SHIP IT

The reusable artifact is `outputs/skill-background-job-pattern.md`. It contains:
- The POST / GET job pattern as a drop-in FastAPI module
- The Anthropic Batch API submit and retrieve loop
- Decision criteria for choosing each pattern

---

## EVALUATE IT

**Test 1: Job lifecycle.** Start the server, POST a job, immediately GET it back. Verify the response is `status: pending` or `status: running`. Wait 10 seconds, GET again. Verify `status: done` and `result` is non-null.

**Test 2: 202 status code.** Confirm POST `/jobs` returns HTTP 202, not 200. Use `curl -v` or `httpx` and check the status line.

**Test 3: Missing job 404.** GET `/jobs/nonexistent-id`. Verify HTTP 404 with a `detail` field.

**Test 4: Concurrent jobs.** POST 10 jobs in rapid succession. Verify all 10 return unique `job_id` values. After 30 seconds, GET each one and confirm all are `done`.

**Test 5: Batch cost estimate.** Submit a batch of 100 requests to the Batch API. Compare the token cost (at 50% discount) against 100 synchronous Messages API calls. The batch should cost roughly half.

**Test 6: Poll loop termination.** Write a poll loop that checks job status every 2 seconds and raises `TimeoutError` after 30 attempts. Verify it terminates cleanly on both `done` and `failed` outcomes without hanging.
