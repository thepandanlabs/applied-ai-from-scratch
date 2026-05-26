# Instrument an App: Raw OTel to Langfuse/Phoenix

> Langfuse and Phoenix both speak OTLP. Change one env var to switch backends. Never rewrite your instrumentation.

**Type:** Build
**Languages:** Python
**Prerequisites:** 07-02 (OpenTelemetry GenAI Conventions), FastAPI basics
**Time:** ~75 min
**Learning Objectives:**
- Add OTel tracing to a FastAPI service with Anthropic calls
- Route traces to Langfuse (cloud) and Phoenix (local) via OTLP
- Understand the two instrumentation paths: raw OTel vs. auto-instrumentation
- Propagate trace context through background tasks

---

## The Problem

You have a working FastAPI service that calls the Anthropic API. You have learned the gen_ai.* conventions. Now you need to actually get traces into a backend where you can query them, build dashboards, and debug production failures.

The challenge is that there are two instrumentation paths that serve different needs: raw OTel spans (maximum control, correct gen_ai.* attributes) and the Langfuse Python SDK (simpler integration, LLM-specific features, but less portable). Choosing the wrong path means either over-engineering a simple service or under-instrumenting a complex one. And both paths require understanding how trace context propagates through async FastAPI routes, background tasks, and multi-step pipelines.

---

## The Concept

### Two Instrumentation Paths

```
Your FastAPI App + Anthropic Calls
          |
          +----------- Path A: Raw OTel SDK -----------------+
          |            opentelemetry-sdk                      |
          |            manual span creation                   |
          |            gen_ai.* attributes                    |
          |            OTLP export                           |
          |                                                    v
          |                                         Any OTLP Backend
          |                                         (Langfuse / Phoenix /
          |                                          Jaeger / Grafana Tempo)
          |
          +----------- Path B: Langfuse Python SDK ----------+
                       langfuse.Langfuse()                   |
                       trace / generation / span             |
                       decorator or context manager          |
                                                              v
                                                     Langfuse only
                                                     (cloud or self-hosted)
```

**Path A (Raw OTel):** Write gen_ai.* spans manually using the OTel SDK. Use `OTLPSpanExporter` to route to any OTel-compatible backend. Maximum portability. You control every attribute. More code.

**Path B (Langfuse SDK):** Use Langfuse's Python SDK directly. Simpler API, native LLM concepts (trace, generation, span). Works only with Langfuse. Less portable but faster to set up.

**Rule of thumb:** Use raw OTel if your platform team owns the observability infrastructure, or if you might switch backends. Use Langfuse SDK directly if you are a small team and Langfuse is your chosen backend.

Both paths send data to the same backends. Langfuse accepts raw OTel via OTLP and also its own SDK format.

### Trace Context in an Async FastAPI App

```
HTTP Request arrives at FastAPI
         |
         v
+------------------+          OTel injects trace_id here
| @app.post("/ask")| -------> root span: "POST /ask"
|  async def ask() |
+------------------+
         |
         | (awaits)
         v
+------------------+
| call_claude()    | -------> child span: "claude-3-5-haiku-20241022 chat"
|                  |          parent_id = root span's span_id
+------------------+
         |
         | (background task)
         v
+------------------+
| log_interaction()| -------> child span: "log-interaction"
|  BackgroundTask  |          MUST explicitly propagate context
+------------------+          (background tasks break automatic propagation)
```

Background tasks in FastAPI do not automatically inherit the parent trace context because they run after the HTTP response is sent. You must capture the context before dispatching and attach it in the background task.

---

## Build It

We will add OTel tracing to a FastAPI service that calls the Anthropic API, with traces routing to the console first, then to Langfuse.

### Step 1: Install dependencies

```bash
pip install fastapi uvicorn anthropic opentelemetry-sdk \
    opentelemetry-instrumentation-fastapi \
    opentelemetry-exporter-otlp-proto-grpc \
    python-dotenv
```

### Step 2: Configure the tracer for OTLP export

This setup reads the OTLP endpoint from an environment variable, so you can switch between Langfuse, Phoenix, and local Jaeger without code changes.

```python
import os
from opentelemetry import trace, context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def setup_tracer() -> trace.Tracer:
    """
    Configure OTel tracer.
    Uses OTLP export if OTEL_EXPORTER_OTLP_ENDPOINT is set, else console.
    """
    provider = TracerProvider()

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        headers_str = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers: dict[str, str] = {}
        if headers_str:
            for pair in headers_str.split(","):
                k, _, v = pair.partition("=")
                headers[k.strip()] = v.strip()

        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        print(f"OTel: exporting to {endpoint}")
    else:
        provider.add_span_processor(
            BatchSpanProcessor(ConsoleSpanExporter())
        )
        print("OTel: exporting to console (set OTEL_EXPORTER_OTLP_ENDPOINT to use a backend)")

    trace.set_tracer_provider(provider)
    return trace.get_tracer("appliedai.phase07.lesson03", "1.0.0")
```

### Step 3: Build the FastAPI service with instrumented LLM calls

```python
import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

import anthropic
from fastapi import BackgroundTasks, FastAPI
from opentelemetry.trace import SpanKind, Status, StatusCode
from pydantic import BaseModel

# --- Request / Response models ---

class AskRequest(BaseModel):
    question: str
    prompt_version: str = "default-v1"
    max_tokens: int = 512

class AskResponse(BaseModel):
    answer: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    trace_id: str  # return the trace ID so clients can look up the span

# --- App setup ---

_tracer: Optional[trace.Tracer] = None
_anthropic_client: Optional[anthropic.Anthropic] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tracer, _anthropic_client
    _tracer = setup_tracer()
    _anthropic_client = anthropic.Anthropic()
    yield

app = FastAPI(lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)  # auto-instruments HTTP spans

# --- LLM call with gen_ai.* spans ---

async def call_claude(
    tracer: trace.Tracer,
    client: anthropic.Anthropic,
    question: str,
    prompt_version: str,
    max_tokens: int,
) -> tuple[str, int, int]:
    """
    Call Anthropic API inside a gen_ai.* span.
    Returns (answer, input_tokens, output_tokens).
    """
    model = "claude-3-5-haiku-20241022"
    span_name = f"{model} chat"

    with tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("gen_ai.request.max_tokens", max_tokens)
        span.set_attribute("gen_ai.operation.name", "chat")
        # Custom extension: track prompt version alongside standard attrs
        span.set_attribute("ai.prompt_version", prompt_version)

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": question}],
            ),
        )

        span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)
        span.set_attribute("gen_ai.response.model", response.model)
        span.set_status(Status(StatusCode.OK))

        return (
            response.content[0].text,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
```

### Step 4: Background task with explicit context propagation

Background tasks in FastAPI run after the HTTP response is sent. OTel's automatic context propagation does not cross this boundary. Capture the context explicitly before dispatching.

```python
from opentelemetry.propagate import inject
from opentelemetry.context import attach, detach

def log_interaction_background(
    question: str,
    answer: str,
    tracer: trace.Tracer,
    parent_context,  # captured before response was sent
) -> None:
    """
    Background task that logs interaction details.
    Must attach parent_context to continue the trace tree.
    """
    token = attach(parent_context)
    try:
        with tracer.start_as_current_span("log-interaction") as span:
            span.set_attribute("interaction.question_len", len(question))
            span.set_attribute("interaction.answer_len", len(answer))
            # In production: write to database, push to eval queue, etc.
    finally:
        detach(token)

# --- FastAPI route ---

@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, background_tasks: BackgroundTasks):
    start = time.monotonic()

    # Capture the current trace context BEFORE the response is sent
    # (background tasks run after; context would otherwise be lost)
    current_context = context.get_current()

    answer, input_tokens, output_tokens = await call_claude(
        _tracer, _anthropic_client, req.question, req.prompt_version, req.max_tokens
    )

    latency_ms = (time.monotonic() - start) * 1000

    # Get the current trace ID to return to the client
    current_span = trace.get_current_span()
    trace_id = format(current_span.get_span_context().trace_id, "032x")

    background_tasks.add_task(
        log_interaction_background,
        req.question,
        answer,
        _tracer,
        current_context,
    )

    return AskResponse(
        answer=answer,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=round(latency_ms, 2),
        trace_id=trace_id,
    )
```

> **Real-world check:** A user submits a complex question. Three seconds later, the background task that logs the interaction fails. The user got a correct answer. Looking at the trace in Langfuse, the background task span is missing. Your colleague says: "It's fine, the user got their answer." What is the problem with missing background task spans in production, and when does it become critical?

---

## Use It

The Langfuse Python SDK is the simpler path when Langfuse is your chosen backend. It abstracts OTel span management into LLM-native concepts.

```python
# pip install langfuse anthropic
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context
import anthropic

langfuse = Langfuse()  # reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
client = anthropic.Anthropic()

@observe(as_type="generation")
def call_claude_langfuse(question: str, prompt_version: str) -> str:
    """
    The @observe decorator automatically creates a Langfuse generation record.
    LangFuse captures: input, output, token usage, latency, and model.
    """
    langfuse_context.update_current_observation(
        model="claude-3-5-haiku-20241022",
        metadata={"prompt_version": prompt_version},
    )
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text

@observe()
def handle_request(question: str, prompt_version: str) -> str:
    """The outer @observe creates a trace. The inner creates a generation."""
    return call_claude_langfuse(question, prompt_version)
```

**Langfuse SDK vs. raw OTel for this use case:**

```
+-------------------------------+-----------------+--------------------+
| Capability                    | Raw OTel        | Langfuse SDK       |
+-------------------------------+-----------------+--------------------+
| Backend portability           | Any OTLP        | Langfuse only      |
| gen_ai.* compliance           | You control it  | Automatic          |
| LLM-native concepts           | DIY             | trace/generation   |
| Setup complexity              | Higher          | Lower              |
| Custom attributes             | Full control    | Via metadata dict  |
| Platform team integration     | Straightforward | Requires Langfuse  |
+-------------------------------+-----------------+--------------------+
```

> **Perspective shift:** A startup engineer says: "The Langfuse SDK is so much simpler. Why would anyone use raw OTel for LLM tracing?" When is the Langfuse SDK the right choice, and when does raw OTel become worth the extra complexity?

---

## Ship It

This lesson produces a reusable Langfuse instrumentation skill for AI services.

**Artifact:** `outputs/skill-langfuse-instrumentation.md`

The `code/main.py` in this lesson is a complete FastAPI service with two instrumentation paths. To use it in a real project: copy the `setup_tracer()` function and the `call_claude()` span wrapper into your service, set environment variables for your chosen backend, and use `FastAPIInstrumentor.instrument_app(app)` to auto-instrument HTTP routes. Context propagation for background tasks requires the explicit `attach(current_context)` pattern shown in `log_interaction_background`.

---

## Evaluate It

Instrumentation that silently drops spans is the most dangerous kind: it makes your dashboards look complete when they are not.

**Check 1: Trace completeness**

For every HTTP request to `/ask`, verify that the trace contains all expected spans:

```bash
# With traces going to Langfuse, query the Langfuse API
# or check the Langfuse UI: each trace should show:
# - root span from FastAPI auto-instrumentation (HTTP layer)
# - "claude-3-5-haiku-20241022 chat" span (LLM call)
# - "log-interaction" span (background task)
# Missing any of these = context propagation failure
```

**Check 2: gen_ai.* attributes are populated**

Verify that every LLM call span in your backend has non-null values for the 4 required attributes:

```python
# Langfuse API check (pseudocode -- replace with actual Langfuse SDK calls)
from langfuse import Langfuse

lf = Langfuse()
traces = lf.fetch_traces(limit=10).data

for t in traces:
    for obs in lf.fetch_observations(trace_id=t.id).data:
        if obs.type == "GENERATION":
            assert obs.model is not None, f"Model missing on trace {t.id}"
            assert obs.usage.input is not None, "input_tokens missing"
            assert obs.usage.output is not None, "output_tokens missing"

print("All recent generation spans have required fields")
```

**Check 3: Background task spans are present**

Force a background task to run and verify its span appears in the trace:

```python
import httpx

async def test_background_task_traced():
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/ask", json={
            "question": "Test question",
            "prompt_version": "test-v1"
        })
        assert resp.status_code == 200
        trace_id = resp.json()["trace_id"]
        print(f"Trace ID: {trace_id}")
        # In Langfuse UI: verify trace contains log-interaction span
        # It may take 1-2 seconds for the background task to complete
```

**Check 4: Latency accounts for all work**

The total trace duration (root span) should be approximately equal to the sum of child span durations. A large gap indicates untraced work, like middleware or serialization overhead that should be measured:

```python
# Compare HTTP response latency_ms (from AskResponse)
# to the span duration visible in Langfuse
# If they differ by more than 20%, some work is not being traced
print("Check: root span duration matches HTTP response latency_ms within 20%")
```
