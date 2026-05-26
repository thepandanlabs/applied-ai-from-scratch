"""
OpenTelemetry GenAI Conventions -- Phase 07 Lesson 02
appliedaifromscratch.com

Demonstrates: creating OTel spans with correct gen_ai.* semantic convention
attributes for Anthropic API calls. Exports to console for local verification.

Run:
    pip install opentelemetry-sdk anthropic
    export ANTHROPIC_API_KEY=sk-...
    python main.py
"""

import anthropic
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode


# ---------------------------------------------------------------------------
# TRACER SETUP
# ---------------------------------------------------------------------------


def setup_console_tracer() -> trace.Tracer:
    """Configure OTel with console export for local development and debugging."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer("appliedai.phase07.lesson02", "1.0.0")


def setup_test_tracer() -> tuple[trace.Tracer, InMemorySpanExporter]:
    """Configure OTel with in-memory export for unit testing."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("appliedai.phase07.lesson02.test", "1.0.0")
    return tracer, exporter


# ---------------------------------------------------------------------------
# LLM CALL WITH OTel SPAN
# ---------------------------------------------------------------------------


def call_with_span(
    tracer: trace.Tracer,
    client: anthropic.Anthropic,
    prompt: str,
    model: str = "claude-3-5-haiku-20241022",
    max_tokens: int = 512,
    capture_content: bool = True,
) -> str:
    """
    Make an Anthropic API call wrapped in an OTel span with gen_ai.* attributes.

    Span name: "{model} chat"  (gen_ai.* naming convention)
    Span kind: SpanKind.CLIENT (outbound API call)

    Required attributes set:
        gen_ai.system              -- "anthropic"
        gen_ai.request.model       -- the requested model
        gen_ai.usage.input_tokens  -- set after API returns
        gen_ai.usage.output_tokens -- set after API returns

    Optional attributes set:
        gen_ai.request.max_tokens
        gen_ai.response.model
        gen_ai.response.finish_reasons
        gen_ai.operation.name

    Events emitted (if capture_content=True):
        gen_ai.content.prompt      -- the prompt text
        gen_ai.content.completion  -- the response text

    Set capture_content=False in production if prompts/responses contain PII.
    """
    span_name = f"{model} chat"

    with tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
        # --- Required attributes (set before API call) ---
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("gen_ai.request.max_tokens", max_tokens)
        span.set_attribute("gen_ai.operation.name", "chat")

        # --- Prompt event (optional, disable for PII) ---
        if capture_content:
            span.add_event(
                "gen_ai.content.prompt",
                attributes={"gen_ai.prompt": prompt},
            )

        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            # --- Required usage attributes (set after API returns) ---
            span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)

            # --- Recommended response attributes ---
            span.set_attribute("gen_ai.response.model", response.model)
            span.set_attribute(
                "gen_ai.response.finish_reasons",
                [response.stop_reason or "unknown"],
            )

            # --- Completion event (optional, disable for PII) ---
            if capture_content:
                span.add_event(
                    "gen_ai.content.completion",
                    attributes={"gen_ai.completion": response_text},
                )

            span.set_status(Status(StatusCode.OK))
            return response_text

        except anthropic.APIError as exc:
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            span.record_exception(exc)
            raise


# ---------------------------------------------------------------------------
# ROOT SPAN: simulates an HTTP request handler
# ---------------------------------------------------------------------------


def handle_user_request(
    tracer: trace.Tracer,
    client: anthropic.Anthropic,
    user_question: str,
    capture_content: bool = True,
) -> str:
    """
    Simulates an HTTP request handler.
    Root span represents the incoming user request.
    The LLM call span is a child of this span.

    The parent-child relationship is what makes traces navigable as trees.
    """
    with tracer.start_as_current_span("user-request") as root:
        root.set_attribute("http.method", "POST")
        root.set_attribute("http.route", "/ask")
        root.set_attribute("user.question_length", len(user_question))

        answer = call_with_span(
            tracer, client, user_question, capture_content=capture_content
        )

        root.set_attribute("response.length", len(answer))
        return answer


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------


def validate_spans(spans: list) -> None:
    """
    Validate that spans have correct gen_ai.* attributes and structure.
    Call this with spans from InMemorySpanExporter in tests.
    """
    required_llm_attrs = [
        "gen_ai.system",
        "gen_ai.request.model",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
    ]

    llm_spans = [s for s in spans if "chat" in s.name]
    assert llm_spans, "No LLM call spans found"

    for span in llm_spans:
        # Check required attributes
        for attr in required_llm_attrs:
            assert attr in span.attributes, f"Missing required attribute: {attr}"

        # Check span kind
        assert span.kind == SpanKind.CLIENT, \
            f"LLM call span must be SpanKind.CLIENT, got {span.kind}"

        # Check token counts are non-zero on success
        if span.status.status_code == StatusCode.OK:
            assert span.attributes["gen_ai.usage.input_tokens"] > 0, \
                "input_tokens must be > 0 on successful call"
            assert span.attributes["gen_ai.usage.output_tokens"] > 0, \
                "output_tokens must be > 0 on successful call"

    # Check parent-child relationship if root span exists
    root_spans = [s for s in spans if s.name == "user-request"]
    if root_spans:
        root = root_spans[0]
        for llm_span in llm_spans:
            assert llm_span.parent is not None, "LLM span must have a parent"
            assert llm_span.parent.span_id == root.context.span_id, \
                "LLM span parent must be the root span"

    print(f"Validation passed: {len(spans)} spans, {len(llm_spans)} LLM call span(s)")
    for span in llm_spans:
        attrs = span.attributes
        print(f"  gen_ai.system = {attrs.get('gen_ai.system')}")
        print(f"  gen_ai.request.model = {attrs.get('gen_ai.request.model')}")
        print(f"  gen_ai.usage.input_tokens = {attrs.get('gen_ai.usage.input_tokens')}")
        print(f"  gen_ai.usage.output_tokens = {attrs.get('gen_ai.usage.output_tokens')}")


# ---------------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== OTel GenAI Conventions Demo ===")
    print("Spans will be printed to console below.\n")

    # Setup: console exporter so we can see spans
    tracer = setup_console_tracer()
    client = anthropic.Anthropic()

    answer = handle_user_request(
        tracer,
        client,
        "What is the difference between a trace and a log in observability?",
    )

    print("\n=== Answer ===")
    print(answer[:300] + "...")

    print("\n=== What to look for in the span output above ===")
    print("  span.name contains 'chat'  (e.g. 'claude-3-5-haiku-20241022 chat')")
    print("  span.kind = SpanKind.CLIENT")
    print("  gen_ai.system = 'anthropic'")
    print("  gen_ai.request.model = 'claude-3-5-haiku-20241022'")
    print("  gen_ai.usage.input_tokens > 0")
    print("  gen_ai.usage.output_tokens > 0")
    print("  events: gen_ai.content.prompt, gen_ai.content.completion")
    print("  parent span: user-request (same trace_id, parent_id = root span_id)")

    # Unit test using in-memory exporter
    print("\n=== Running span validation ===")
    test_tracer, exporter = setup_test_tracer()
    handle_user_request(test_tracer, client, "Hello", capture_content=False)
    validate_spans(exporter.get_finished_spans())

    print("\nKey insight: change setup_console_tracer() to setup_otlp_tracer()")
    print("and the same spans go to Langfuse, Phoenix, Jaeger, or Grafana Tempo.")
    print("The gen_ai.* attribute names are identical across all backends.")


if __name__ == "__main__":
    main()
