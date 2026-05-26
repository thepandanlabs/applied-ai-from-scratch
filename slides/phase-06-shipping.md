---
marp: true
theme: applied-ai
class: title
paginate: true
footer: 'Applied AI From Scratch · Phase 06'
---

# Phase 06: Shipping It

## Notebook to Production Service

Phase 06 of 13 · 14 lessons · ~15 hours

<!-- SPEAKER: Welcome to Phase 06. Every engineer has demoed a model that worked perfectly on their laptop and then shipped something that silently failed on real users. This phase closes that gap: one production failure mode per lesson. Time: ~5 min -->

---

## Who this is for

You are a **working software engineer** who:

- Has a model integration that works in a notebook or script
- Has never wrapped it in a service that handles real traffic
- Wants a production path: API, Docker, deployment, versioning

**What you will NOT get:**
- Theory about "best practices" without code
- Framework magic that hides what breaks
- DevOps lectures: only the subset AI services need

<!-- SPEAKER: Anchor on the specific gap. They can write Python. They know models. The gap is packaging, failure handling, and deployment. -->

---

## What you will build

| Artifact | Lesson |
|----------|--------|
| FastAPI service wrapping Claude | 06-02 |
| Streaming SSE endpoint | 06-03 |
| Input/output validation layer | 06-04 |
| Docker image (non-root, no secrets) | 06-05 |
| Config and secrets loader | 06-06 |
| Retry + circuit breaker decorator | 06-07 |
| Fallback chain with model failover | 06-08 |
| Background jobs + batch processor | 06-09 |
| TypeScript streaming frontend | 06-10 |
| Version manifest logger | 06-12 |
| Feature flag + canary router | 06-13 |
| Capstone: full production RAG/agent app | 06-14 |

<!-- SPEAKER: Each artifact is a standalone reusable file. By the capstone, all 12 artifacts wire together into one deployable service. -->

---

## The through-line: demo vs. production

```ascii
Demo                     Production
──────────────────────   ──────────────────────────────────────
One user (you)           Thousands of concurrent users
Controlled input         Anything users type
Your internet            Flaky networks, API rate limits
Works in notebook        Needs packaging, config, secrets
No monitoring            Silent failures, cost runaway
Vibe check               Eval harness + CI
```

> **Key insight:** Demos work because the engineer controls everything. Production fails because users don't.

<!-- SPEAKER: This table is the entire phase in one view. Every lesson is one row of this table becoming solved code. -->

---

## Service architecture: what you ship

<div class="mermaid">
flowchart LR
    A[Client] --> B[FastAPI]
    B --> C[Input validator]
    C --> D[Model router]
    D --> E[Primary model]
    D --> F[Fallback model]
    E --> G[Output validator]
    F --> G
    G --> H[Response]
    B --> I[Version manifest logger]
    B --> J[Feature flag router]
</div>

<!-- SPEAKER: This is the target architecture. Each box is one or two lessons. Point to each box as you walk through the phase. -->

---
<!-- _class: section -->

## L01: The Demo-to-Production Gap

### Six things that fail in production

1. **Noisy inputs**: users send anything, including prompt injections
2. **Network failures**: upstream APIs go down mid-request
3. **Concurrent users**: your single-threaded script is not a server
4. **Evolving prompts**: changed in prod with no version control
5. **Secret management**: API keys hardcoded, then rotated, then broken
6. **No monitoring**: costs spike, errors are silent, you find out from billing

> **Key insight:** Each failure mode has a known fix. This phase is 14 fixes.

<!-- SPEAKER: Go through each item. Ask the room which ones they have personally shipped around. Usually all six. -->

---

## L01: The production readiness checklist

```ascii
Checklist                  Status in notebook   Status after Phase 06
─────────────────────────  ───────────────────  ─────────────────────
Input validated?           No                   Pydantic model
Output sanitized?          No                   Structured + stripped
API key in env?            Hardcoded            pydantic-settings
Retries on failure?        No                   tenacity backoff
Fallback if model down?    No                   Failover chain
Packaged + deployable?     No                   Docker image
```

<!-- SPEAKER: This checklist is the syllabus. Flip back to this at the end of the phase to show completeness. -->

---
<!-- _class: code -->

## L02: Wrapping a Model in FastAPI

```python
from fastapi import FastAPI
from pydantic import BaseModel
import anthropic
app = FastAPI()
client = anthropic.Anthropic()
class ChatRequest(BaseModel):
    message: str
    system: str = "You are a helpful assistant."
@app.post("/chat")
async def chat(req: ChatRequest):
    resp = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=req.system,
        messages=[{"role": "user", "content": req.message}]
    )
    return {"reply": resp.content[0].text}
@app.get("/health")
async def health():
    return {"status": "ok"}
```

<!-- SPEAKER: Three things to call out: async def, Pydantic request model, health endpoint. These three patterns appear in every service you will ever ship. -->

---

## L02: Why these three things matter

- **`async def`**: FastAPI can handle concurrent requests. A sync def blocks the event loop.
- **`BaseModel` for request**: Free validation, free docs at `/docs`, free error messages to callers.
- **`/health` endpoint**: Load balancers, Kubernetes, Railway all need this. Without it, your service appears dead.

> **Key insight:** The health endpoint is not optional. Every deploy target checks it. Add it first, before the feature routes.

<!-- SPEAKER: The async point often surprises engineers. Their notebook code is sync. Moving to async is one line change but has real throughput impact. -->

---

## L03: Why streaming matters

Without streaming: user waits 8 seconds, sees the full response appear.

With streaming: user sees text appear word by word. Perceived latency drops to under one second.

```ascii
Without streaming:   [========= 8s wait =========] RESPONSE
With streaming:      [1s] word by word by word by word...
```

> **Key insight:** Streaming is a UX decision, not a performance optimization. The model takes the same time either way.

<!-- SPEAKER: Ask the room: have you ever abandoned a ChatGPT response because it felt too slow? That is what streaming solves. -->

---

## L03: StreamingResponse with SSE

<!-- _class: code -->

```python
from fastapi.responses import StreamingResponse

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def generate():
        with client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=1024,
            messages=[{"role": "user", "content": req.message}]
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {text}\n\n"
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )
```

<!-- SPEAKER: The double newline in the yield is required by the SSE spec. One newline is not enough. The media_type triggers the browser's EventSource protocol. -->

---

## L04: The validation layers

<div class="mermaid">
flowchart LR
    A[Raw request] --> B[Pydantic model]
    B -->|invalid| C[422 error to caller]
    B -->|valid| D[Business logic check]
    D -->|blocked| E[400 with reason]
    D -->|ok| F[Model call]
    F --> G[Structured output parse]
    G -->|parse fails| H[Retry or 500]
    G -->|ok| I[Sanitize HTML]
    I --> J[Return to caller]
</div>

<!-- SPEAKER: The two most skipped steps are the business logic check (is this request actually in scope?) and the HTML sanitization on output. Both are exploited in production. -->

---

## L04: Input model with field constraints

<!-- _class: code -->

```python
from pydantic import BaseModel, Field, field_validator

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    system: str = Field(default="You are helpful.", max_length=1000)
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("message")
    @classmethod
    def no_injection_markers(cls, v: str) -> str:
        blocked = ["<|system|>", "[INST]", "###System"]
        for marker in blocked:
            if marker in v:
                raise ValueError(f"Blocked pattern: {marker}")
        return v
```

> **Key insight:** Pydantic is your first security layer. `max_length` on every string field is not paranoia, it is table stakes.

<!-- SPEAKER: The injection marker check is a starter list. In production you extend this with a classifier. But Pydantic field constraints stop the most common abuse before the model ever sees the input. -->

---

## L05: The Dockerfile

<!-- _class: code -->

```dockerfile
FROM python:3.12-slim AS base
RUN pip install uv
WORKDIR /app
COPY pyproject.toml .
RUN uv pip install --system --no-cache .
COPY . .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

<!-- SPEAKER: Walk through each line. The non-root user is the most commonly skipped step in AI service containers. Many container escapes exploit root processes. -->

---

## L05: The four rules for AI Docker images

1. **Non-root user**: add `RUN useradd` and `USER appuser`, always
2. **No secrets in layers**: use env vars at runtime, not `ENV API_KEY=...` in Dockerfile
3. **`.dockerignore`**: exclude `.env`, `*.pem`, `__pycache__`, model weights
4. **`uv` over pip**: `uv pip install` is 10-100x faster, keeps CI practical

```ascii
.dockerignore:
  .env
  .env.*
  *.pem
  __pycache__
  .pytest_cache
  *.egg-info
```

> **Key insight:** Secrets baked into image layers persist in the registry forever, even after you delete them from the file.

<!-- SPEAKER: The secrets-in-layers rule breaks teams. A dev adds ANTHROPIC_API_KEY to Dockerfile for convenience, pushes to a public registry, and the key is permanent in the layer history. -->

---

## L06: pydantic-settings

<!-- _class: code -->

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    anthropic_api_key: str
    model: str = "claude-opus-4-7"
    max_tokens: int = 1024
    environment: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()
```

<!-- SPEAKER: `anthropic_api_key` has no default, so it is required. If it is missing, the app fails at startup, not at the first request. Fail fast is the right behavior for secrets. -->

---

## L06: Config vs. secrets

```ascii
Config (safe to log)          Secrets (never log)
────────────────────────────  ──────────────────────────────
model="claude-opus-4-7"       ANTHROPIC_API_KEY
max_tokens=1024                DATABASE_URL (if has password)
environment="production"       JWT_SECRET
log_level="INFO"               STRIPE_SECRET_KEY
feature_flag_pct=5             SLACK_WEBHOOK_URL
```

> **Key insight:** Rotate secrets without restarting the app by reading from a secrets manager (AWS Secrets Manager, Vault) at request time, not at startup.

<!-- SPEAKER: The rotation-without-restart point is critical for production. Hardcoding secrets at startup means a rotation requires a redeploy, which means a window of downtime or broken requests. -->

---

## L07: tenacity retry decorator

<!-- _class: code -->

```python
from tenacity import (
    retry, stop_after_attempt,
    wait_exponential, retry_if_exception_type
)
import anthropic

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(anthropic.RateLimitError)
)
def call_model(prompt: str) -> str:
    return client.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    ).content[0].text
```

<!-- SPEAKER: Exponential backoff means: wait 2s, then 4s, then 8s, capped at 10s. Without this, your service hammers a rate-limited API and makes the outage worse. -->

---

## L07: The circuit breaker pattern

<div class="mermaid">
flowchart LR
    A[Request] --> B{Circuit state?}
    B -->|closed| C[Call API]
    C -->|success| D[Reset failure count]
    C -->|failure| E[Increment failures]
    E --> F{Over threshold?}
    F -->|yes| G[Open circuit for 30s]
    F -->|no| D
    B -->|open| H[Fast-fail: return 503]
    B -->|half-open| I[Allow one probe request]
    I -->|success| J[Close circuit]
    I -->|failure| G
</div>

<!-- SPEAKER: The circuit breaker protects your users from your upstream's instability. Without it, requests pile up, timeouts cascade, and your whole service degrades while you wait for an upstream that is not coming back. -->

---

## L08: The fallback chain

```ascii
Request
  |
  v
Primary model ──fail──► Fallback model ──fail──► Cache ──fail──► 503
  |                          |                     |
  v                          v                     v
Response               Response (slower)      Stale response
```

> **Key insight:** Decide in advance what degraded mode looks like. Silent fallback (user sees slower response) vs. explicit fallback (user sees "using backup model") depends on your product contract.

<!-- SPEAKER: The cache fallback is the most underused. For many queries, a 30-minute-old cached answer is better than a 503. The threshold is: would the user prefer a stale answer or an error? -->

---

## L08: Fallback chain implementation

<!-- _class: code -->

```python
MODELS = ["claude-opus-4-7", "claude-haiku-4-5-20251001"]

def call_with_fallback(prompt: str) -> str:
    for model in MODELS:
        try:
            return client.messages.create(
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            ).content[0].text
        except Exception as e:
            logger.warning(f"Model {model} failed: {e}")
    return "Service temporarily unavailable."
```

<!-- SPEAKER: The final return is deliberate: an explicit user-visible message instead of a 500. The caller can differentiate "we tried and degraded gracefully" from "something crashed." -->

---

## L09: When not to block

```ascii
Blocking (bad for slow AI work)    Non-blocking (right for AI)
─────────────────────────────────  ────────────────────────────────
POST /analyze → wait 30s → result  POST /analyze → 202 Accepted
                                   GET /status/{job_id} → progress
                                   GET /result/{job_id} → result
```

> **Key insight:** HTTP timeout is typically 30-60 seconds. AI processing often takes longer. Background jobs decouple request from response.

<!-- SPEAKER: Ask the room: has anyone gotten a 504 Gateway Timeout from an AI endpoint they built? This pattern prevents it. -->

---

## L09: FastAPI BackgroundTasks + Anthropic Batch API

<!-- _class: code -->

```python
from fastapi import BackgroundTasks

results: dict = {}

def process_in_background(job_id: str, prompt: str):
    results[job_id] = call_model(prompt)

@app.post("/analyze")
async def analyze(req: ChatRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    background_tasks.add_task(process_in_background, job_id, req.message)
    return {"job_id": job_id, "status": "queued"}

@app.get("/result/{job_id}")
async def get_result(job_id: str):
    return {"result": results.get(job_id), "ready": job_id in results}
```

<!-- SPEAKER: Anthropic Batch API is the right tool when you have 100+ requests to process. It cuts costs by 50% and processes asynchronously. BackgroundTasks is right for single requests that are just slow. -->

---

## L10: EventSource for streaming

<!-- _class: code -->

```typescript
async function streamChat(message: string): Promise<void> {
  const res = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) { showError(await res.text()); return; }
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value);
    const lines = chunk.split("\n\n").filter(Boolean);
    for (const line of lines) {
      if (line.startsWith("data: ")) appendText(line.slice(6));
    }
  }
}
```

<!-- SPEAKER: Three things the frontend must handle: loading state before first token, streaming state while tokens arrive, error state when the request fails. This code handles all three. -->

---

## L10: The frontend's three states

```ascii
State         UI behavior
────────────  ─────────────────────────────────
loading       Spinner or "thinking..." text
streaming     Append tokens to output element
error         Clear spinner, show error message
done          Enable submit button again
```

> **Key insight:** The frontend's job is exactly this: send request, show loading, stream response, handle errors. No framework required for this. Fetch + ReadableStream is 40 lines.

<!-- SPEAKER: React, Vue, and Next.js all work fine here. But knowing the raw fetch pattern means you understand what the framework is abstracting. Start raw, add framework when you need state management. -->

---

## L11: The deployment decision

```ascii
Need to ship this week?
  Yes ──► Managed (Railway/Render/Fly)   $5-20/mo, no ops
  No  ──► Need GPU? ──► Cloud GPU instance
          Need scale? ──► Kubernetes / ECS
          Simple?     ──► VPS + Docker Compose
```

> **Key insight:** Managed platforms run your Docker image. Container platforms run your Docker image. The image is the constant. The platform is the variable. Build the image first.

<!-- SPEAKER: Railway, Render, and Fly.io all accept a Dockerfile. If you built the image from L05, you can deploy to any of these in under 10 minutes. No Kubernetes knowledge required. -->

---

## L11: Managed vs. container path

<div class="mermaid">
flowchart LR
    A[Docker image] --> B{Which path?}
    B -->|ship fast| C[Managed: Railway / Render / Fly]
    B -->|need control| D{What constraint?}
    D -->|GPU needed| E[Cloud GPU: Lambda Labs / RunPod]
    D -->|scale needed| F[ECS / GKE / AKS]
    D -->|cost-sensitive| G[VPS + Docker Compose]
    C --> H[Live in 10 min]
    E --> H
    F --> H
    G --> H
</div>

<!-- SPEAKER: Every path ends at the same place: a running container. The choice is ops burden vs. control vs. cost. For most AI services in early production, managed is the right answer. -->

---

## L12: What changes in production and breaks things

```ascii
What changed?          How it breaks
─────────────────────  ──────────────────────────────────────────
Prompt wording         Output format changes, downstream parsing fails
Model version          Behavior shift, cost change, latency change
max_tokens             Truncated outputs, incomplete JSON
temperature            More/less creative, inconsistent evals
```

> **Key insight:** A prompt is a versioned artifact. A model name is a versioned artifact. If you can't answer "what was running at 2pm on Tuesday," you cannot debug production.

<!-- SPEAKER: This point lands hardest with engineers who have been burned. Ask: has anyone changed a prompt in production and had something break silently? That is the problem this lesson solves. -->

---

## L12: The version manifest pattern

<!-- _class: code -->

```python
import hashlib, json
from datetime import datetime

VERSION_MANIFEST = {
    "model": "claude-opus-4-7",
    "prompt_version": "2.3.1",
    "config_hash": hashlib.md5(
        json.dumps(settings.model_dump(), sort_keys=True)
        .encode()
    ).hexdigest()[:8],
}

@app.post("/chat")
async def chat(req: ChatRequest):
    response = call_model(req.message)
    return {
        "reply": response,
        "meta": {**VERSION_MANIFEST, "ts": datetime.utcnow().isoformat()}
    }
```

<!-- SPEAKER: The config_hash catches "I thought we changed that setting back" bugs. Log the manifest with every response. When an eval regresses, you can diff the manifests to find what changed. -->

---

## L13: Three rollout modes

<div class="mermaid">
flowchart LR
    A[Request] --> B{Flag state?}
    B -->|shadow| C[Run both: log new output, return old]
    B -->|canary 5%| D[Route 5% to new version]
    B -->|full| E[New version for all traffic]
    B -->|off| F[Old version]
</div>

<!-- SPEAKER: Shadow mode is the safest. You collect data on the new prompt's outputs without any user impact. Then you diff evals. Then you move to canary. Then full rollout. -->

---

## L13: Shadow mode implementation

<!-- _class: code -->

```python
import random

FEATURE_FLAGS = {"new_prompt_v2": "shadow"}  # shadow | canary | full | off

def route_request(prompt: str, flag: str) -> str:
    mode = FEATURE_FLAGS.get(flag, "off")
    if mode == "full":
        return call_new_version(prompt)
    if mode == "canary" and random.random() < 0.05:
        return call_new_version(prompt)
    if mode == "shadow":
        new_output = call_new_version(prompt)
        logger.info(f"shadow_output={new_output!r}")  # log, don't return
        return call_old_version(prompt)
    return call_old_version(prompt)
```

> **Key insight:** Shadow mode gives you production data on a new prompt before a single user sees it. Run it for 24 hours, compare evals, then promote to canary.

<!-- SPEAKER: The logger.info in shadow mode is the whole value. That log is your eval dataset. Connect it to your Phase 05 eval harness and you have a deployment gate. -->

---

## L14: What the capstone wires together

<div class="mermaid">
flowchart LR
    A[FastAPI service] --> B[Input validation]
    B --> C[Feature flag router]
    C --> D[Model router with fallback]
    D --> E[Retry + circuit breaker]
    E --> F[Claude API]
    F --> G[Output validation]
    G --> H[Version manifest log]
    H --> I[StreamingResponse]
    A --> J[Background job queue]
    A --> K[Health + readiness endpoints]
</div>

<!-- SPEAKER: Every box is a lesson in this phase. The capstone is not new material, it is integration. The challenge is wiring all 12 artifacts together without any of them fighting each other. -->

---

## L14: Capstone: the deployment checklist

```ascii
Before pushing to production:
  [ ] Input validated with field constraints
  [ ] Output sanitized, no raw HTML passthrough
  [ ] API key from env, not hardcoded
  [ ] Retry with exponential backoff
  [ ] Fallback model configured
  [ ] Docker image: non-root user, .dockerignore in place
  [ ] Health endpoint returns 200
  [ ] Version manifest logged with every response
  [ ] At least shadow mode on any prompt changes
  [ ] Load test: 50 concurrent users, no 500s
```

> **Key insight:** This checklist is your diff between "it works on my machine" and "it handles real users."

<!-- SPEAKER: Run through this checklist live. Ask for a show of hands: how many of these does their current AI service pass? The goal is all ten by end of capstone. -->

---

## Discussion: production failure modes

> **Facilitator prompt:** Think about the last AI feature you shipped or demoed. Which row of the demo-vs-production table was your biggest gap? Did you discover it before or after it hit users?

> **Facilitator prompt:** When is silent fallback the right choice vs. telling the user "I'm using a backup model"? What does your product contract say about this?

> **Facilitator prompt:** If you could only implement three items from the production checklist for a first deploy, which three would you pick? Why?

<!-- SPEAKER: The first question surfaces real war stories. The second question has no single right answer and drives good product vs. engineering tension. The third forces prioritization under constraint. -->

---

## Discussion: versioning and rollout

> **Facilitator prompt:** You change a prompt, run shadow mode for 24 hours, and see that 8% of shadow outputs are different from the current outputs. How do you decide whether "different" is "better"?

> **Facilitator prompt:** A feature flag is set to canary at 5%. A bug in the new prompt causes 3 errors in 1000 requests. How do you detect it before full rollout?

<!-- SPEAKER: The first question connects directly to Phase 05 Evaluation. The second question is about observability, previewing Phase 07. Both questions have engineering answers, not just process answers. -->

---

## Exercises

**Easy:** Take any existing Python script that calls an LLM. Wrap it in FastAPI with a Pydantic request model and a `/health` endpoint. Confirm it starts and responds.

**Medium:** Add streaming to the FastAPI service. Build the minimal TypeScript frontend that streams the response token by token. Add a loading state and an error state.

**Hard:** Wire the full production stack: input validation, retry with circuit breaker, fallback chain, version manifest, feature flag in shadow mode. Deploy to Railway or Fly.io. Run `wrk` or `locust` with 50 concurrent users and confirm zero 500s.

<!-- SPEAKER: The easy exercise is 30 minutes. The medium is 2-3 hours. The hard exercise is the capstone and should take a full day. Encourage pairs for the hard exercise. -->

---

## Further reading

- **[Anthropic API docs: Error handling](https://docs.anthropic.com/en/api/errors)**: official rate limit and error codes for building retry logic
- **[Tenacity docs](https://tenacity.readthedocs.io/)**: the retry library used in L07; the `wait_exponential` and `retry_if_exception_type` combinators are the 80% case
- **[FastAPI: Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)**: official docs for L09; pairs with the Anthropic Batch API reference
- **[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)**: config and secrets loading from env files; the `model_validator` pattern for cross-field secret validation
- **[The Twelve-Factor App](https://12factor.net/)**: the original source for config-in-env, stateless processes, and dev-prod parity; written for web apps but every factor applies to AI services

<!-- SPEAKER: The Twelve-Factor App is 12 years old and still the right mental model. Read factors III (config), VI (processes), and IX (disposability) in 20 minutes. They explain why this phase exists. -->

---

## What is next: Phase 07

**Observability: Knowing What Your Service Is Doing**

- Structured logging with request tracing
- OpenTelemetry `gen_ai.*` conventions for LLM spans
- Langfuse and Phoenix for prompt and eval tracking
- Cost attribution per request, per user, per feature
- Alerting: when to page, when to log, when to ignore

> **Key insight:** Shipping is not done when it deploys. It is done when you can answer "is it working?" without looking at logs by hand.

<!-- SPEAKER: Phase 07 picks up exactly where this phase leaves off. The version manifest we log in L12 becomes the trace context in Phase 07. The feature flag metrics become the dashboard. Connect the thread. -->

---

<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({
    startOnLoad: true,
    theme: 'dark',
    themeVariables: {
      primaryColor: '#7c6af5',
      primaryTextColor: '#e8e8e8',
      primaryBorderColor: '#2a2a2a',
      lineColor: '#8a8a8a',
      secondaryColor: '#252019',
      tertiaryColor: '#2e2820',
      background: '#1c1714',
      mainBkg: '#252019',
      nodeBorder: '#2a2a2a',
      clusterBkg: '#2e2820',
      titleColor: '#e8e8e8',
      edgeLabelBackground: '#2e2820',
      attributeBackgroundColorEven: '#252019',
      attributeBackgroundColorOdd: '#2e2820',
    }
  });
</script>
