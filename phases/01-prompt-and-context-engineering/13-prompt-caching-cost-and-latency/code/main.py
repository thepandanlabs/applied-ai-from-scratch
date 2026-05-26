"""
Lesson 13: Prompt Caching - Cost and Latency
=============================================
Demonstrates:
- Placing cache_control breakpoints in system prompts and document context
- Measuring cache hit vs miss latency
- Verifying cache hits from usage metadata
- Estimating monthly cost savings

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python main.py
"""

import os
import time
import anthropic

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
# Haiku requires 2048 tokens minimum for caching;
# Sonnet and Opus require 1024 tokens minimum.

# ---------------------------------------------------------------------------
# A long system prompt (must be >= 2048 tokens for Haiku to cache)
# ---------------------------------------------------------------------------

LONG_SYSTEM_PROMPT = """
You are a senior software engineering assistant with deep expertise in Python,
distributed systems, and API design. You help engineers write production-quality
code and solve complex architectural problems.

When answering questions:
1. Start with the direct answer or implementation. No preamble.
2. Explain your technical choices inline as code comments, not as separate paragraphs.
3. Highlight trade-offs where they exist.
4. If a question has a better interpretation, answer the better version and note the reframe.
5. Use concrete examples. Avoid abstract descriptions without accompanying code.

You follow these engineering principles:
- Explicit over implicit: name variables clearly, avoid clever tricks
- Simple over clever: prefer readable code over micro-optimizations
- Composable over monolithic: small functions with single responsibilities
- Testable over tightly coupled: injectable dependencies, pure functions where possible
- Fail fast with clear error messages: validate inputs early, raise with context

When reviewing code, you check for:
- Security vulnerabilities (injection, insecure defaults, missing input validation)
- Performance issues (N+1 queries, unnecessary serialization, blocking I/O in async)
- Correctness bugs (off-by-one errors, race conditions, wrong assumptions about types)
- Maintainability issues (magic numbers, unclear names, missing error handling)

Your responses use Python 3.10+ syntax and follow PEP 8. When using type hints,
prefer the built-in types (list, dict, tuple) over typing module equivalents
where available in Python 3.10+.

Technical domain context: This assistant is deployed in a production engineering
environment where code will be reviewed, tested, and shipped to customers.
Answers must be complete and production-ready, not illustrative sketches. Always
include error handling, validation, and logging where appropriate.

For API design questions, you follow RESTful conventions by default, prefer
Pydantic v2 models for request and response validation, and recommend FastAPI
as the default web framework for new services.

For database questions, you prefer PostgreSQL. Use SQLAlchemy Core (not the ORM)
for complex queries requiring fine-grained control, and pgvector for vector
similarity search workloads in the same database.

For async Python, you prefer asyncio with async/await syntax throughout. Use
httpx for async HTTP clients and asyncpg for PostgreSQL in async contexts.
Avoid mixing sync and async code unless wrapping legacy libraries.

For testing, you prefer pytest with fixtures for unit tests, hypothesis for
property-based testing of pure functions, and testcontainers for integration
tests that require real database instances.

For observability, you use OpenTelemetry with the gen_ai.* semantic conventions
for AI/LLM instrumentation. Prefer structured logging with JSON output in
production over print statements or unstructured log lines.

For deployment, you use Docker with multi-stage builds to minimize image size.
Kubernetes for orchestration at scale; Docker Compose for local development
and small-scale deployments. Always include health check endpoints.
""" * 2  # Doubled to ensure sufficient token count for Haiku's 2048 minimum


# ---------------------------------------------------------------------------
# Uncached call (baseline)
# ---------------------------------------------------------------------------


def call_uncached(user_question: str) -> dict:
    """
    Standard API call with no cache_control.
    Full input price on every call regardless of repeated content.
    """
    start = time.time()
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=LONG_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_question}],
    )
    elapsed = time.time() - start
    usage = response.usage

    return {
        "mode": "uncached",
        "cache_status": "N/A",
        "latency_s": round(elapsed, 3),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "response_preview": response.content[0].text[:120],
    }


# ---------------------------------------------------------------------------
# Cached call with cache_control breakpoint
# ---------------------------------------------------------------------------


def call_cached(user_question: str) -> dict:
    """
    API call with cache_control on the system prompt.
    First call: cache write (slightly elevated cost, normal latency).
    Subsequent calls within 5 min: cache read (reduced cost and latency).
    """
    start = time.time()
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        # System must be a list of content blocks when using cache_control
        system=[
            {
                "type": "text",
                "text": LONG_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # The caching breakpoint
            }
        ],
        messages=[{"role": "user", "content": user_question}],
    )
    elapsed = time.time() - start
    usage = response.usage

    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_write = getattr(usage, "cache_creation_input_tokens", 0)

    if cache_read > 0:
        cache_status = "HIT"
    elif cache_write > 0:
        cache_status = "WRITE"
    else:
        cache_status = "MISS"

    return {
        "mode": "cached",
        "cache_status": cache_status,
        "latency_s": round(elapsed, 3),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "response_preview": response.content[0].text[:120],
    }


# ---------------------------------------------------------------------------
# Multi-breakpoint: system + document context
# ---------------------------------------------------------------------------


def call_with_document_cache(document: str, user_question: str) -> dict:
    """
    Cache both the system prompt AND a large document context.
    Uses two cache_control breakpoints.
    The question is not cached (changes per call).
    """
    start = time.time()
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=[
            {
                "type": "text",
                "text": "You are a document analysis assistant. Answer questions using only the provided document. If the answer is not in the document, say so.",
                "cache_control": {"type": "ephemeral"},  # Breakpoint 1: system
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Document:\n\n{document}",
                        "cache_control": {"type": "ephemeral"},  # Breakpoint 2: document
                    },
                    {
                        "type": "text",
                        "text": f"\nQuestion: {user_question}",
                        # No cache_control: this changes every call
                    },
                ],
            }
        ],
    )
    elapsed = time.time() - start
    usage = response.usage

    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_write = getattr(usage, "cache_creation_input_tokens", 0)

    return {
        "mode": "document_cache",
        "cache_status": "HIT" if cache_read > 0 else ("WRITE" if cache_write > 0 else "MISS"),
        "latency_s": round(elapsed, 3),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "response_preview": response.content[0].text[:120],
    }


# ---------------------------------------------------------------------------
# Cost calculator
# ---------------------------------------------------------------------------


def estimate_monthly_savings(
    system_tokens: int,
    requests_per_day: int,
    cache_hit_rate: float,
    # Haiku approximate pricing (verify current rates at anthropic.com/pricing)
    input_price_per_mtok: float = 0.80,
    cache_read_price_per_mtok: float = 0.08,
    cache_write_price_per_mtok: float = 1.00,
) -> dict:
    """
    Estimate monthly cost savings from prompt caching.
    Verify current pricing at https://www.anthropic.com/pricing before budgeting.
    """
    monthly_requests = requests_per_day * 30
    cache_misses = monthly_requests * (1 - cache_hit_rate)
    cache_hits = monthly_requests * cache_hit_rate

    uncached_cost = (system_tokens / 1_000_000) * input_price_per_mtok * monthly_requests
    cached_cost = (
        (system_tokens / 1_000_000) * cache_write_price_per_mtok * cache_misses
        + (system_tokens / 1_000_000) * cache_read_price_per_mtok * cache_hits
    )

    return {
        "system_tokens": system_tokens,
        "requests_per_day": requests_per_day,
        "cache_hit_rate_pct": f"{cache_hit_rate * 100:.0f}%",
        "uncached_monthly_usd": round(uncached_cost, 2),
        "cached_monthly_usd": round(cached_cost, 2),
        "monthly_savings_usd": round(uncached_cost - cached_cost, 2),
        "savings_pct": round((1 - cached_cost / uncached_cost) * 100, 1) if uncached_cost > 0 else 0,
    }


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------


def print_result(label: str, result: dict) -> None:
    status = result.get("cache_status", "N/A")
    print(f"  {label}: {result['latency_s']}s | status={status} | "
          f"in={result['input_tokens']} out={result['output_tokens']} "
          f"cache_read={result['cache_read_tokens']} cache_write={result['cache_write_tokens']}")


def main():
    question = "How should I handle database connection errors in a FastAPI endpoint?"

    print("=" * 70)
    print("PROMPT CACHING DEMO")
    print(f"Model: {MODEL}")
    print("=" * 70)

    # Part 1: Uncached baseline
    print("\n[PART 1] Uncached baseline")
    uncached = call_uncached(question)
    print_result("Uncached", uncached)

    # Part 2: Cached calls (first = write, subsequent = reads)
    print("\n[PART 2] Cached calls (first is WRITE, rest should be HIT)")
    for i in range(3):
        result = call_cached(question)
        print_result(f"  Call {i+1}", result)

    # Part 3: Cost estimates for different usage patterns
    print("\n[PART 3] Monthly cost savings estimates")
    print("  (Approximate Haiku pricing. Verify at anthropic.com/pricing)")
    print()
    for daily_vol in [100, 500, 2000]:
        est = estimate_monthly_savings(
            system_tokens=3000,  # ~3k token system prompt
            requests_per_day=daily_vol,
            cache_hit_rate=0.90,
        )
        print(
            f"  {daily_vol:5d} req/day: "
            f"${est['uncached_monthly_usd']:7.2f} uncached -> "
            f"${est['cached_monthly_usd']:6.2f} cached | "
            f"saves ${est['monthly_savings_usd']:6.2f} ({est['savings_pct']}%)"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
