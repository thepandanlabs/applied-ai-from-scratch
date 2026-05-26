---
name: skill-otel-genai-spans
description: Reference for creating correct OpenTelemetry spans with gen_ai.* semantic convention attributes for LLM API calls; includes required attributes, span naming, span kind, event names, and backend routing patterns
version: "1.0"
phase: "07"
lesson: "02"
tags: [opentelemetry, otel, gen-ai, tracing, observability, llm-ops]
---

# Skill: OpenTelemetry GenAI Spans

## Purpose

You are an applied AI engineering advisor specializing in OpenTelemetry instrumentation for LLM systems. When a user asks about tracing LLM calls, adding OTel instrumentation to an AI service, or routing traces to a backend, use this skill to provide correct gen_ai.* attribute names and patterns.

---

## The gen_ai.* Semantic Conventions

The OpenTelemetry GenAI working group defines standard attribute names for AI/LLM operations. Use these names so your traces work in any OTel-compatible backend without adaptation.

### Required Attributes (every LLM call span must have these)

| Attribute | Type | Example |
|-----------|------|---------|
| `gen_ai.system` | string | `"anthropic"` |
| `gen_ai.request.model` | string | `"claude-3-5-haiku-20241022"` |
| `gen_ai.usage.input_tokens` | int | `42` |
| `gen_ai.usage.output_tokens` | int | `128` |

### Recommended Attributes

| Attribute | Type | Example |
|-----------|------|---------|
| `gen_ai.response.model` | string | `"claude-3-5-haiku-20241022"` |
| `gen_ai.request.max_tokens` | int | `512` |
| `gen_ai.response.finish_reasons` | string[] | `["end_turn"]` |
| `gen_ai.operation.name` | string | `"chat"` |

### Span Naming Convention

```
{gen_ai.request.model} {gen_ai.operation.name}
```
Example: `claude-3-5-haiku-20241022 chat`

### Span Kind

Always `SpanKind.CLIENT` for outbound LLM API calls.

### Content Events

| Event | When | Key Attribute |
|-------|------|---------------|
| `gen_ai.content.prompt` | After building prompt | `gen_ai.prompt` |
| `gen_ai.content.completion` | After receiving response | `gen_ai.completion` |

Note: disable content events in production if prompts/responses contain PII.

---

## Minimal Implementation

```python
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
import anthropic

def call_with_span(tracer, client, prompt, model="claude-3-5-haiku-20241022"):
    with tracer.start_as_current_span(
        f"{model} chat",
        kind=SpanKind.CLIENT
    ) as span:
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("gen_ai.operation.name", "chat")

        try:
            response = client.messages.create(
                model=model, max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
            span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)
            span.set_attribute("gen_ai.response.model", response.model)
            span.set_status(Status(StatusCode.OK))
            return response.content[0].text

        except anthropic.APIError as exc:
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            span.record_exception(exc)
            raise
```

---

## Exporter Patterns

### Console (development)

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
```

### OTLP/gRPC (production - any backend)

```python
# pip install opentelemetry-exporter-otlp-proto-grpc
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider = TracerProvider()
exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
```

### Backend endpoint reference

| Backend | OTLP endpoint |
|---------|--------------|
| Langfuse cloud | `https://cloud.langfuse.com/api/public/otel/v1/traces` |
| Langfuse self-hosted | `http://your-host:3000/api/public/otel/v1/traces` |
| Phoenix local | `http://localhost:4317` |
| Jaeger | `http://localhost:4317` |
| Grafana Tempo | `http://localhost:4317` |

Set authentication via environment variable:
```bash
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer your-token"
```

---

## Common Mistakes

**Wrong span kind:** Using `SpanKind.INTERNAL` instead of `SpanKind.CLIENT` breaks distributed trace topology in some backends.

**Setting usage attributes before the call:** `gen_ai.usage.input_tokens` can only be set after the API returns (the response contains the actual counts).

**Missing trace context propagation:** If you start background tasks or thread pools, you must propagate the trace context explicitly. Use `opentelemetry.context.attach()` or pass the parent context to child spans.

**Logging PII in events:** The `gen_ai.content.prompt` event captures the full prompt text. If your prompts contain user PII, disable content events in production. Use a sampling strategy to capture content only for debugging purposes.

---

## Checklist for Correct Instrumentation

- [ ] Span name follows `{model} {operation}` pattern
- [ ] Span kind is `SpanKind.CLIENT`
- [ ] `gen_ai.system` is set to the provider name
- [ ] `gen_ai.request.model` is set before the API call
- [ ] `gen_ai.usage.input_tokens` is set after the API returns
- [ ] `gen_ai.usage.output_tokens` is set after the API returns
- [ ] Errors are recorded with `span.record_exception()` and `Status(StatusCode.ERROR)`
- [ ] LLM span is a child of the request root span (trace context is propagated)
