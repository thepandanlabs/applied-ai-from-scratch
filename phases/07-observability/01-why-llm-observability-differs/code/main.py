"""
Why LLM Observability Differs -- Phase 07 Lesson 01
appliedaifromscratch.com

Demonstrates: minimal structured logging for LLM API calls.
Captures the 8 essential fields every LLM request log must include:
    model, prompt_version, input_tokens, output_tokens, cost_usd,
    latency_ms, cache_hit, error

Run:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
    python main.py
"""

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Optional

import anthropic


# ---------------------------------------------------------------------------
# PRICING: token costs per million tokens (as of 2026)
# Update this table when Anthropic releases new pricing.
# ---------------------------------------------------------------------------

MODEL_COSTS: dict[str, dict[str, float]] = {
    "claude-3-5-haiku-20241022": {
        "input_per_m": 0.80,
        "output_per_m": 4.00,
        "cache_read_per_m": 0.08,
    },
    "claude-3-5-sonnet-20241022": {
        "input_per_m": 3.00,
        "output_per_m": 15.00,
        "cache_read_per_m": 0.30,
    },
}


# ---------------------------------------------------------------------------
# DATA MODEL: the 8 required fields
# ---------------------------------------------------------------------------


@dataclass
class LLMLogRecord:
    """
    The 8 essential fields every LLM request log must capture.

    Why each field matters:
    - model: detect model drift when provider silently updates weights
    - prompt_version: bisect prompt regressions to the exact template change
    - input_tokens: track context window usage; alert on unexpectedly long prompts
    - output_tokens: track generation cost; alert on runaway completions
    - cost_usd: budget alerts; per-user cost attribution
    - latency_ms: SLA tracking; P95/P99 alerting
    - cache_hit: measure prompt cache effectiveness; optimize cache hit rate
    - error: classify failures (auth, rate limit, timeout, context length)
    """

    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    cache_hit: bool
    error: Optional[str]  # None on success; exception class name on failure


# ---------------------------------------------------------------------------
# COST CALCULATION
# ---------------------------------------------------------------------------


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
) -> float:
    """Calculate USD cost for an API call from token counts."""
    pricing = MODEL_COSTS.get(model, MODEL_COSTS["claude-3-5-haiku-20241022"])
    input_cost = (input_tokens / 1_000_000) * pricing["input_per_m"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_per_m"]
    cache_cost = (cache_read_tokens / 1_000_000) * pricing["cache_read_per_m"]
    return round(input_cost + output_cost + cache_cost, 8)


# ---------------------------------------------------------------------------
# LOGGER
# ---------------------------------------------------------------------------


class LLMLogger:
    """
    Minimal structured logger for LLM API calls.

    Wraps Anthropic API calls and emits a JSON log record per request.
    Records are written to stdout (for log aggregators) and optionally to
    a JSONL file (for local analysis).

    Usage:
        logger = LLMLogger(output_file="llm_requests.jsonl")
        text, record = logger.call("What is RAG?", prompt_version="support-v1")
    """

    def __init__(self, output_file: Optional[str] = None):
        self.client = anthropic.Anthropic()
        self.output_file = output_file

    def call(
        self,
        prompt: str,
        prompt_version: str,
        model: str = "claude-3-5-haiku-20241022",
        system: str = "You are a helpful assistant.",
        max_tokens: int = 512,
    ) -> tuple[str, LLMLogRecord]:
        """
        Call the Anthropic API and return (response_text, log_record).

        Always emits a structured log record, even on failure.
        On failure: error field is set, token counts are 0, response_text is "".
        """
        start = time.monotonic()
        error: Optional[str] = None
        response_text = ""
        input_tokens = 0
        output_tokens = 0
        cache_read_tokens = 0
        cache_hit = False

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            # Prompt cache: present when Anthropic returns cached tokens
            cache_read_tokens = (
                getattr(response.usage, "cache_read_input_tokens", 0) or 0
            )
            cache_hit = cache_read_tokens > 0

        except anthropic.APIError as exc:
            error = type(exc).__name__

        latency_ms = (time.monotonic() - start) * 1000

        record = LLMLogRecord(
            model=model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=calculate_cost(model, input_tokens, output_tokens, cache_read_tokens),
            latency_ms=round(latency_ms, 2),
            cache_hit=cache_hit,
            error=error,
        )

        self._emit(record)
        return response_text, record

    def _emit(self, record: LLMLogRecord) -> None:
        """Write the log record as a JSON line to stdout and optionally to file."""
        line = json.dumps(asdict(record))
        print(line)
        if self.output_file:
            with open(self.output_file, "a") as f:
                f.write(line + "\n")


# ---------------------------------------------------------------------------
# SCHEMA VALIDATION
# ---------------------------------------------------------------------------


def validate_records(path: str) -> None:
    """
    Read a JSONL log file and verify all 8 required fields are present.
    Run this after capturing a batch of requests to confirm logging integrity.
    """
    required_fields = [
        "model",
        "prompt_version",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "latency_ms",
        "cache_hit",
        "error",
    ]

    with open(path) as f:
        records = [json.loads(line) for line in f if line.strip()]

    for i, record in enumerate(records):
        for field in required_fields:
            assert field in record, f"Record {i} missing field: {field}"

    error_records = [r for r in records if r["error"] is not None]
    for r in error_records:
        assert r["input_tokens"] == 0, "Token counts must be 0 on API failure"
        assert r["cost_usd"] == 0.0, "Cost must be 0 on API failure"

    print(f"Validation passed: {len(records)} records, {len(error_records)} errors captured")


# ---------------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------------


def main() -> None:
    log_path = "llm_requests.jsonl"

    # Clear any previous run
    if os.path.exists(log_path):
        os.remove(log_path)

    logger = LLMLogger(output_file=log_path)

    print("=== LLM Structured Logger Demo ===\n")

    # Simulate requests from two different prompt templates
    requests = [
        ("What is the capital of France?", "general-qa-v1"),
        ("Summarize quantum computing in one sentence.", "summary-v2"),
        ("List three debugging strategies for distributed systems.", "support-v3"),
    ]

    for prompt, version in requests:
        text, record = logger.call(prompt=prompt, prompt_version=version)
        print(f"  Response: {text[:80].strip()}...")
        print(
            f"  Cost: ${record.cost_usd:.6f} | "
            f"Tokens: {record.input_tokens}in / {record.output_tokens}out | "
            f"Latency: {record.latency_ms:.0f}ms"
        )
        print()

    # Validate the captured log file
    print("=== Validating log file ===")
    validate_records(log_path)
    print(f"Log written to: {log_path}")
    print("\nKey insight: every record carries model + prompt_version.")
    print("When a prompt regression happens, you can filter by prompt_version")
    print("to find exactly when quality changed -- no guessing required.")


if __name__ == "__main__":
    main()
