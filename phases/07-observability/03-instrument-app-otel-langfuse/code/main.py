"""
Instrument an App: Raw OTel to Langfuse/Phoenix -- Phase 07 Lesson 03
appliedaifromscratch.com

Demonstrates: adding OTel tracing to a FastAPI + Anthropic service.
Two paths:
  Path A (default): raw OTel SDK with gen_ai.* attributes, OTLP export
  Path B (--langfuse): Langfuse Python SDK with @observe decorators

Run (Path A, console export):
    pip install fastapi uvicorn anthropic opentelemetry-sdk \
        opentelemetry-instrumentation-fastapi \
        opentelemetry-exporter-otlp-proto-grpc
    export ANTHROPIC_API_KEY=sk-...
    python main.py

Run (Path A, Langfuse OTLP):
    export OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel/v1/traces
    export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Bearer your-key"
    python main.py

Run (Path B, Langfuse SDK):
    pip install langfuse
    export LANGFUSE_PUBLIC_KEY=pk-lf-...
    export LANGFUSE_SECRET_KEY=sk-lf-...
    export LANGFUSE_HOST=https://cloud.langfuse.com
    python main.py --path b
"""

import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

import anthropic
import uvicorn
from fastapi import BackgroundTasks, FastAPI
from opentelemetry import context, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# TRACER SETUP
# ---------------------------------------------------------------------------


def setup_tracer() -> trace.Tracer:
    """
    Configure OTel tracer.
    Uses OTLP export if OTEL_EXPORTER_OTLP_ENDPOINT is set, else console.

    Key insight: change only the endpoint env var to switch between:
      - ConsoleSpanExporter (local debug)
      - Langfuse cloud OTLP
      - Phoenix local OTLP
      - Jaeger, Grafana Tempo, etc.
    """
    provider = TracerProvider()

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        # Import OTLP exporter only when needed
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

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
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        print("OTel: exporting to console (no OTEL_EXPORTER_OTLP_ENDPOINT set)")

    trace.set_tracer_provider(provider)
    return trace.get_tracer("appliedai.phase07.lesson03", "1.0.0")


# ---------------------------------------------------------------------------
# REQUEST / RESPONSE MODELS
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    question: str
    prompt_version: str = "default-v1"
    max_tokens: int = 512


class AskResponse(BaseModel):
    answer: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    trace_id: str


# ---------------------------------------------------------------------------
# PATH A: RAW OTEL SDK
# ---------------------------------------------------------------------------

_tracer: Optional[trace.Tracer] = None
_anthropic_client: Optional[anthropic.Anthropic] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tracer, _anthropic_client
    _tracer = setup_tracer()
    _anthropic_client = anthropic.Anthropic()
    yield


app = FastAPI(title="Phase 07 Lesson 03 -- LLM Tracing Demo", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)  # auto-instruments HTTP routes


async def call_claude_otel(
    tracer: trace.Tracer,
    client: anthropic.Anthropic,
    question: str,
    prompt_version: str,
    max_tokens: int,
) -> tuple[str, int, int]:
    """
    Call Anthropic API inside a gen_ai.* OTel span.
    Returns (answer, input_tokens, output_tokens).
    """
    model = "claude-3-5-haiku-20241022"

    with tracer.start_as_current_span(f"{model} chat", kind=SpanKind.CLIENT) as span:
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("gen_ai.request.max_tokens", max_tokens)
        span.set_attribute("gen_ai.operation.name", "chat")
        # Custom extension: prompt version is not a standard gen_ai.* attr
        # Use ai.* namespace for application-specific attributes
        span.set_attribute("ai.prompt_version", prompt_version)

        span.add_event(
            "gen_ai.content.prompt",
            attributes={"gen_ai.prompt": question},
        )

        try:
            # Run the synchronous Anthropic client in a thread executor
            # to avoid blocking the async FastAPI event loop
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": question}],
                ),
            )

            answer = response.content[0].text

            span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)
            span.set_attribute("gen_ai.response.model", response.model)
            span.set_attribute(
                "gen_ai.response.finish_reasons", [response.stop_reason or "unknown"]
            )
            span.add_event(
                "gen_ai.content.completion",
                attributes={"gen_ai.completion": answer},
            )
            span.set_status(Status(StatusCode.OK))

            return answer, response.usage.input_tokens, response.usage.output_tokens

        except anthropic.APIError as exc:
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            span.record_exception(exc)
            raise


def log_interaction_background(
    question: str,
    answer: str,
    tracer: trace.Tracer,
    parent_context,
) -> None:
    """
    Background task: logs interaction details in a child span.

    IMPORTANT: background tasks in FastAPI run AFTER the HTTP response is sent.
    OTel's automatic context propagation does not cross this boundary.
    We must capture the context before the response is sent and attach it here.
    """
    from opentelemetry.context import attach, detach

    token = attach(parent_context)
    try:
        with tracer.start_as_current_span("log-interaction") as span:
            span.set_attribute("interaction.question_len", len(question))
            span.set_attribute("interaction.answer_len", len(answer))
            # In production: write to evaluation queue, database, etc.
            time.sleep(0.01)  # Simulate I/O
    finally:
        detach(token)


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, background_tasks: BackgroundTasks):
    """FastAPI route: handles user question, calls Claude, logs in background."""
    start = time.monotonic()

    # Capture trace context BEFORE sending the response.
    # Background tasks run after the response is sent, so OTel context
    # would be lost without this explicit capture.
    current_context = context.get_current()

    answer, input_tokens, output_tokens = await call_claude_otel(
        _tracer, _anthropic_client, req.question, req.prompt_version, req.max_tokens
    )

    latency_ms = (time.monotonic() - start) * 1000

    # Return the trace ID so the client can look up this trace in Langfuse/Phoenix
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


# ---------------------------------------------------------------------------
# PATH B: LANGFUSE PYTHON SDK (alternative instrumentation)
# ---------------------------------------------------------------------------


def run_langfuse_path() -> None:
    """
    Demonstrate Path B: Langfuse Python SDK with @observe decorators.
    Run this when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set.
    """
    try:
        from langfuse.decorators import langfuse_context, observe
    except ImportError:
        print("Install langfuse: pip install langfuse")
        return

    lf_client = anthropic.Anthropic()

    @observe(as_type="generation")
    def call_claude_langfuse(question: str, prompt_version: str) -> str:
        langfuse_context.update_current_observation(
            model="claude-3-5-haiku-20241022",
            metadata={"prompt_version": prompt_version},
        )
        response = lf_client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            messages=[{"role": "user", "content": question}],
        )
        return response.content[0].text

    @observe()
    def handle_request_langfuse(question: str, prompt_version: str) -> str:
        """Outer @observe creates a trace. Inner @observe creates a generation."""
        return call_claude_langfuse(question, prompt_version)

    print("\n=== Path B: Langfuse SDK ===")
    answer = handle_request_langfuse(
        "What is distributed tracing?", "langfuse-demo-v1"
    )
    print(f"Answer: {answer[:200]}...")
    print("Check your Langfuse dashboard for the trace.")


# ---------------------------------------------------------------------------
# DEMO RUNNER
# ---------------------------------------------------------------------------


def main() -> None:
    if "--path" in sys.argv:
        idx = sys.argv.index("--path")
        if sys.argv[idx + 1] == "b":
            run_langfuse_path()
            return

    print("=== Path A: Raw OTel SDK ===")
    print("Starting FastAPI server on http://localhost:8000")
    print("POST http://localhost:8000/ask with JSON: {\"question\": \"your question\"}")
    print("Press Ctrl+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
