---
name: skill-langfuse-instrumentation
description: Guide for instrumenting a FastAPI + Anthropic service with OTel spans routed to Langfuse or Phoenix; covers both raw OTel and Langfuse SDK paths, with context propagation patterns for background tasks
version: "1.0"
phase: "07"
lesson: "03"
tags: [langfuse, phoenix, opentelemetry, fastapi, instrumentation, tracing]
---

# Skill: Langfuse Instrumentation

## Purpose

You are an applied AI engineering advisor. When a user needs to instrument a FastAPI + LLM service with OTel tracing and route traces to Langfuse or Phoenix, use this skill to recommend the correct approach and patterns.

---

## Two Instrumentation Paths

**Path A: Raw OTel SDK (portable)**
- Write gen_ai.* spans manually
- Use OTLPSpanExporter with endpoint set by env var
- Works with Langfuse, Phoenix, Jaeger, Grafana Tempo
- More code, maximum control and portability

**Path B: Langfuse Python SDK (simple)**
- Use `@observe` decorators
- Works only with Langfuse
- Less code, native LLM concepts (trace/generation/span)
- Faster to set up for teams that have chosen Langfuse

---

## Path A: Raw OTel Setup

```python
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

def setup_tracer() -> trace.Tracer:
    provider = TracerProvider()
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("your-service", "1.0.0")
```

### Backend endpoints

| Backend | OTLP endpoint |
|---------|--------------|
| Langfuse cloud | `https://cloud.langfuse.com/api/public/otel/v1/traces` |
| Langfuse self-hosted | `http://your-host:3000/api/public/otel/v1/traces` |
| Phoenix local | `http://localhost:4317` |
| Jaeger | `http://localhost:4317` |

Set auth header:
```bash
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer your-api-key"
```

---

## Path B: Langfuse SDK Setup

```python
# pip install langfuse
# env: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

from langfuse.decorators import observe, langfuse_context
import anthropic

client = anthropic.Anthropic()

@observe(as_type="generation")
def call_claude(question: str) -> str:
    langfuse_context.update_current_observation(
        model="claude-3-5-haiku-20241022",
        metadata={"prompt_version": "v1"},
    )
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text

@observe()
def handle_request(question: str) -> str:
    return call_claude(question)  # nested @observe = trace > generation hierarchy
```

---

## FastAPI Integration

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)  # auto-instruments all HTTP routes
```

---

## Background Task Context Propagation

Background tasks in FastAPI run AFTER the HTTP response is sent. OTel context does not automatically propagate across this boundary. Always capture and pass context explicitly:

```python
from opentelemetry import context
from opentelemetry.context import attach, detach

# In the route handler (BEFORE sending response):
current_context = context.get_current()
background_tasks.add_task(my_background_fn, ..., parent_context=current_context)

# In the background task:
def my_background_fn(..., parent_context):
    token = attach(parent_context)
    try:
        with tracer.start_as_current_span("background-work") as span:
            # This span is now a child of the route's span
            pass
    finally:
        detach(token)
```

Forgetting this pattern causes background task spans to appear as disconnected orphan spans in your trace backend.

---

## Diagnostic Checklist

When a user reports "traces are missing spans" or "background task work is not appearing in traces":

1. Are background tasks using `attach(parent_context)` before creating spans?
2. Is `FastAPIInstrumentor.instrument_app(app)` called after the app is created?
3. Is `BatchSpanProcessor` used (not `SimpleSpanProcessor`) to avoid blocking the event loop?
4. Are OTLP headers correct? Check with `curl -H "Authorization: Bearer your-key" your-endpoint`
5. Is the OTLP endpoint using the correct protocol (grpc vs. http/protobuf)?

---

## Common Mistakes

**Blocking the async event loop:** The Anthropic Python SDK is synchronous. Wrap calls in `asyncio.get_event_loop().run_in_executor(None, lambda: ...)` inside async FastAPI routes.

**Using SimpleSpanProcessor in production:** It blocks on every span export. Use `BatchSpanProcessor` for all production deployments.

**Missing context in threads:** Any code that runs in a thread pool (including `run_in_executor`) must propagate context manually using `attach/detach`.

**Not returning trace_id to clients:** Return the trace_id in API responses so that users can reference a specific trace when reporting issues.
