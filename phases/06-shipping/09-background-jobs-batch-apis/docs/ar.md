# المهام الخلفية (Background Jobs) وواجهات الدُّفعات (Batch APIs)

> إن لم يكن المستخدم بحاجة إلى الإجابة خلال الـ500ms القادمة، فلا تجعله ينتظرها.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 02-wrapping-model-in-fastapi، 03-streaming-sse-async
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- تنفيذ طابور مهام (job queue) غير متزامن في الذاكرة باستخدام FastAPI BackgroundTasks
- إرجاع job_id فورًا وكشف نقطة استعلام (poll endpoint)
- إرسال أكثر من 100 طلب إلى Anthropic Batch API في استدعاء واحد واسترجاع النتائج
- تحديد متى يكون نمط المهام غير المتزامنة (async job) مطلوبًا ومتى يكون المتزامن (sync) كافيًا

---

## الشعار

**كل طلب LLM لا يحتاج إلى إجابة آنية (real-time) هو مرشّح لنمط المهام غير المتزامنة (async job).**

---

## المشكلة

بنيت نقطة FastAPI تستدعي Anthropic API وتُرجِع الاستجابة. تعمل بشكل مثالي للطلبات المفردة. ثم يطلب فريق المنتج ميزة إثراء جماعي (bulk enrichment): إعطاء ملف CSV فيه 500 وصف شركة، وتوليد ملخّص بفقرة واحدة لكل منها.

تفعل ما يبدو طبيعيًا: تمرّ على CSV بحلقة، وتستدعي نقطة `/generate` لديك 500 مرة. بعد ثلاث دقائق يبلغ موازن الحِمل (load balancer) لديك مهلته الزمنية. يرى المستخدم خطأً. سجلات الـAPI لديك مليئة بمدد طلبات تبلغ 30 ثانية. ويُطلَق إنذار حدّ المعدّل (rate limit) لدى Anthropic.

المشكلة الجذرية هي عدم تطابق بين ما يحتاجه المستخدم (النتائج، في نهاية المطاف) وما تفعله نقطتك (تحجز الاتصال حتى الانتهاء). لمهام LLM الجماعية أو طويلة الأمد، يكون HTTP المتزامن (synchronous) الأداة الخطأ. تحتاج إلى شيئين:

1. نمط مهام غير متزامنة (async job): اقبل العمل، أرجِع معرّفًا (ID)، ودع العميل يستعلم عن النتائج.
2. واجهة Anthropic Batch API: أرسل حتى 10,000 طلب في استدعاء واحد، واحصل على النتائج خلال 24 ساعة بخصم 50% على التكلفة.

نمط المهام يحلّ مشكلة زمن الاستجابة (latency). وواجهة Batch API تحلّ مشكلة التكلفة والإنتاجية (throughput). معًا هما المعمارية الصحيحة لأي عبء عمل LLM جماعي غير آني.

---

## المفهوم

### المتزامن مقابل غير المتزامن: المفاضلة الجوهرية

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

### واجهة Anthropic Batch API

واجهة Batch API سطح منفصل عن واجهة Messages API القياسية. الفروق الرئيسية:

| الخاصية | الواجهة القياسية (Standard API) | واجهة الدُّفعات (Batch API) |
|---|---|---|
| زمن الاستجابة | 1-30 ثانية | حتى 24 ساعة |
| التكلفة | 1x | 0.5x (خصم 50%) |
| أقصى عدد طلبات لكل دُفعة | 1 | 10,000 |
| الاسترجاع | بثّ (streaming) أو متزامن | استعلم عن الاكتمال ثم نزّل |
| الأنسب لـ | الاستخدام الآني الموجّه للمستخدم | الإثراء الجماعي، المهام الليلية، التقييمات (evals) |

تتكوّن دورة الحياة من ثلاث خطوات: إنشاء الدُّفعة، الاستعلام عن الحالة، استرجاع النتائج. تصل النتائج كملف JSONL يربط كل سطر فيه `custom_id` بالاستجابة المقابلة.

### متى تستخدم كل نمط

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

## البناء

### الخطوة 1: طابور مهام في الذاكرة باستخدام FastAPI BackgroundTasks

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

### الخطوة 2: دالة العامل الخلفي (Background Worker)

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

### الخطوة 3: نقطتا POST وGET

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

> **اختبار من الواقع:** لماذا تُرجِع نقطة POST رمز HTTP 202 بدلًا من 200؟ في دلالات HTTP، يعني 200 "تم"، ويعني 202 "قُبِل للمعالجة". إرجاع 202 يخبر العميل صراحةً بأن الطلب استُلم لكن العمل لم ينتهِ. غالبًا ما تتعامل بوابات الـAPI وموازنات الحِمل (load balancers) وأطقم تطوير العملاء (client SDKs) مع 200 و202 بشكل مختلف في منطق إعادة المحاولة (retry). استخدم 202 دائمًا لإنشاء المهام غير المتزامنة.

### الخطوة 4: نمط Anthropic Batch API

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

## الاستخدام

قارن النمطين على مهمة محسوسة: توليد ملخّصات لـ20 وصف منتج.

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

> **نقلة في المنظور:** يبدو طابور المهام (job queue) وواجهة Batch API متشابهين سطحيًا (تقديم، أخذ معرّف، استعلام)، لكنهما يخدمان مقاييس مختلفة. طابور المهام لمهام تملكها خدمتك: كل مهمة بضع ثوانٍ من العمل، وتريد النتائج خلال أقل من دقيقة. وواجهة Batch API لإرسال 100 إلى 10,000 استدعاء LLM إلى Anthropic دفعة واحدة، مع وصول النتائج بعد ساعات. فكّر فيه كالفرق بين التوصيل في اليوم نفسه والشحن الليلي. أحدهما حين يكون عميلك يراقب؛ والآخر لخطوط الأنابيب الليلية حيث تكون التكلفة لكل وحدة هي المقياس الوحيد المهم.

---

## التسليم

المنتَج القابل لإعادة الاستخدام هو `outputs/skill-background-job-pattern.md`. يحتوي على:
- نمط مهمة POST / GET كوحدة FastAPI جاهزة للإسقاط
- حلقة تقديم واسترجاع Anthropic Batch API
- معايير القرار لاختيار كل نمط

---

## التقييم

**الاختبار 1: دورة حياة المهمة.** شغّل الخادم، أرسل مهمة بـPOST، ثم استرجعها فورًا بـGET. تحقّق من أن الاستجابة `status: pending` أو `status: running`. انتظر 10 ثوانٍ، ثم نفّذ GET مجددًا. تحقّق من أن `status: done` ومن أن `result` ليست فارغة.

**الاختبار 2: رمز الحالة 202.** أكّد أن POST على `/jobs` يُرجِع HTTP 202 لا 200. استخدم `curl -v` أو `httpx` وافحص سطر الحالة.

**الاختبار 3: مهمة مفقودة 404.** نفّذ GET على `/jobs/nonexistent-id`. تحقّق من HTTP 404 مع حقل `detail`.

**الاختبار 4: مهام متزامنة.** أرسل 10 مهام بـPOST على التوالي بسرعة. تحقّق من أن العشرة كلها تُرجِع قيم `job_id` فريدة. بعد 30 ثانية، نفّذ GET على كلٍّ منها وأكّد أن جميعها `done`.

**الاختبار 5: تقدير تكلفة الدُّفعة.** أرسل دُفعة من 100 طلب إلى Batch API. قارن تكلفة الـtoken (بخصم 50%) بـ100 استدعاء متزامن لواجهة Messages API. ينبغي أن تكلّف الدُّفعة نحو النصف.

**الاختبار 6: إنهاء حلقة الاستعلام.** اكتب حلقة استعلام تفحص حالة المهمة كل ثانيتين وترفع `TimeoutError` بعد 30 محاولة. تحقّق من أنها تنتهي بنظافة في حالتي `done` و`failed` دون أن تتعلّق.
