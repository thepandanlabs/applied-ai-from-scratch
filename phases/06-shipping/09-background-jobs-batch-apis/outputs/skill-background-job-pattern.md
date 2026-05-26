---
name: skill-background-job-pattern
description: drop-in FastAPI module for async job queue and Anthropic Batch API submit and poll loops
version: "1.0"
phase: "06"
lesson: "09"
tags: [async, background-jobs, batch-api, fastapi, anthropic]
---

# Background Job Pattern Reference

## Decision Guide: Which pattern to use?

```
Is the user waiting for the response in the UI right now?
  YES -> sync endpoint (standard Messages API, return response directly)
  NO  -> is this a bulk task with 10+ items?
           YES -> Anthropic Batch API (50% cost, up to 10,000 items, 24h SLA)
           NO  -> FastAPI BackgroundTasks job queue (seconds to minutes, your infra)
```

## Pattern 1: FastAPI BackgroundTasks Job Queue

### Drop-in module (copy into your FastAPI app)

```python
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

# Replace dict with Redis hash or Postgres table in production.
_jobs: dict[str, dict[str, Any]] = {}


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    result: str | None = None
    error: str | None = None
    created_at: str
    completed_at: str | None = None


def _create_job_record() -> dict[str, Any]:
    return {
        "job_id": str(uuid.uuid4())[:8],
        "status": JobStatus.pending,
        "result": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat(),
        "completed_at": None,
    }


def register_job_routes(app: FastAPI, worker_fn: Any) -> None:
    """
    Register POST /jobs and GET /jobs/{id} on an existing FastAPI app.
    worker_fn signature: (job_id: str, **kwargs) -> None
    Updates _jobs[job_id] with status, result, error.
    """

    @app.post("/jobs", response_model=JobResponse, status_code=202)
    async def create_job(payload: dict, background_tasks: BackgroundTasks) -> JobResponse:
        record = _create_job_record()
        _jobs[record["job_id"]] = record
        background_tasks.add_task(worker_fn, record["job_id"], **payload)
        return JobResponse(**record)

    @app.get("/jobs/{job_id}", response_model=JobResponse)
    async def get_job(job_id: str) -> JobResponse:
        if job_id not in _jobs:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
        return JobResponse(**_jobs[job_id])
```

### Poll loop (client side)

```python
import time
import httpx

def poll_job(base_url: str, job_id: str, interval: float = 2.0, timeout: float = 120.0) -> str:
    """Poll until done or failed. Returns result text. Raises on failure or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(interval)
        resp = httpx.get(f"{base_url}/jobs/{job_id}")
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "done":
            return data["result"]
        if data["status"] == "failed":
            raise RuntimeError(f"Job failed: {data['error']}")
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")
```

## Pattern 2: Anthropic Batch API

### Submit a batch

```python
import anthropic

client = anthropic.Anthropic()

def submit_batch(texts: list[str], instruction: str = "Summarize in one sentence:") -> str:
    """Submit texts to Batch API. Returns batch_id."""
    requests_list = [
        {
            "custom_id": f"item-{i}",
            "params": {
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 256,
                "messages": [{"role": "user", "content": f"{instruction} {text}"}],
            },
        }
        for i, text in enumerate(texts)
    ]
    batch = client.messages.batches.create(requests=requests_list)
    return batch.id
```

### Poll and retrieve results

```python
import time

def retrieve_batch(batch_id: str, poll_interval: float = 30.0) -> dict[str, str]:
    """
    Poll until batch ends. Returns {custom_id: result_text}.
    Batches complete in minutes for small sizes, hours for large.
    """
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        counts = batch.request_counts
        print(
            f"Batch {batch_id}: in_progress={counts.in_progress} "
            f"succeeded={counts.succeeded} errored={counts.errored}"
        )
        time.sleep(poll_interval)

    results = {}
    for result in client.messages.batches.results(batch_id):
        if result.result.type == "succeeded":
            results[result.custom_id] = result.result.message.content[0].text
        else:
            results[result.custom_id] = f"ERROR: {result.result.error.type}"
    return results
```

## Cost comparison

| Scenario | Requests | Standard cost (est.) | Batch cost (est.) | Savings |
|---|---|---|---|---|
| 100 summaries | 100 | $0.10 | $0.05 | 50% |
| 1,000 enrichments | 1,000 | $1.00 | $0.50 | 50% |
| 10,000 eval cases | 10,000 | $10.00 | $5.00 | 50% |

Batch API limits: max 10,000 requests per batch, 256 MB total request size.

## Production upgrades for the job queue

| What to change | Why |
|---|---|
| Replace `dict` store with Redis | Survives process restarts; supports TTL for old jobs |
| Replace BackgroundTasks with Celery/ARQ | Handles retries, dead-letter queues, worker scaling |
| Add job TTL and cleanup endpoint | Prevent unbounded memory growth |
| Emit job events to OpenTelemetry | Trace job latency, failure rate, queue depth |
