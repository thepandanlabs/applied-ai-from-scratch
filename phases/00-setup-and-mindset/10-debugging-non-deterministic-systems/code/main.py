"""
Lesson 10 - Debugging Non-Deterministic Systems
A DebugLogger that captures every AI call to JSONL for analysis.

Run:
    python main.py

This makes 3 calls and writes ai_calls.jsonl, then prints a summary.
"""

import anthropic
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────
# Cost estimates per 1K tokens (input / output)
# ─────────────────────────────────────────────

COST_PER_1K: dict[str, dict[str, float]] = {
    "claude-3-5-haiku-20241022": {"input": 0.001, "output": 0.005},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    "claude-opus-4-5": {"input": 0.015, "output": 0.075},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = COST_PER_1K.get(model, {"input": 0.003, "output": 0.015})
    return (input_tokens / 1000) * rates["input"] + (output_tokens / 1000) * rates["output"]


# ─────────────────────────────────────────────
# Data record
# ─────────────────────────────────────────────

@dataclass
class CallRecord:
    timestamp: str
    model: str
    prompt: str
    response: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    temperature: float
    error: Optional[str] = None

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self))


# ─────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────

class DebugLogger:
    """
    Wraps the Anthropic client and logs every call to a JSONL file.

    Each line in the file is a JSON record with:
      timestamp, model, prompt, response, latency_ms,
      input_tokens, output_tokens, cost_usd, temperature, error
    """

    def __init__(self, log_path: str = "ai_calls.jsonl"):
        self.log_path = Path(log_path)
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("Error: ANTHROPIC_API_KEY not set", file=sys.stderr)
            sys.exit(1)
        self.client = anthropic.Anthropic(api_key=api_key)

    def call(
        self,
        prompt: str,
        model: str = "claude-3-5-haiku-20241022",
        max_tokens: int = 256,
        temperature: float = 1.0,
    ) -> str:
        """Make an API call, log everything, and return the response text."""
        start = time.monotonic()
        error: Optional[str] = None
        response_text = ""
        input_tokens = 0
        output_tokens = 0

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
        except Exception as e:
            error = str(e)

        latency_ms = int((time.monotonic() - start) * 1000)

        record = CallRecord(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            model=model,
            prompt=prompt,
            response=response_text,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(model, input_tokens, output_tokens),
            temperature=temperature,
            error=error,
        )

        with open(self.log_path, "a") as f:
            f.write(record.to_jsonl() + "\n")

        if error:
            raise RuntimeError(f"API call failed: {error}")

        return response_text


# ─────────────────────────────────────────────
# Log analysis
# ─────────────────────────────────────────────

def load_log(log_path: str = "ai_calls.jsonl") -> list[dict]:
    path = Path(log_path)
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def failure_rate(records: list[dict]) -> float:
    if not records:
        return 0.0
    failures = sum(1 for r in records if r.get("error") is not None)
    return failures / len(records)


def slow_calls(records: list[dict], threshold_ms: int = 3000) -> list[dict]:
    return [r for r in records if r["latency_ms"] > threshold_ms]


def total_cost(records: list[dict]) -> float:
    return sum(r["cost_usd"] for r in records)


def classify_failures(records: list[dict]) -> dict[str, list[dict]]:
    """
    Separate failures into model failures vs. integration failures.
    Integration: rate limits, network errors, auth problems.
    Model: refusals, short/empty responses, wrong format.
    """
    categories: dict[str, list[dict]] = {
        "integration_rate_limit": [],
        "integration_auth": [],
        "integration_network": [],
        "model_refusal": [],
        "model_short_response": [],
        "unknown": [],
    }

    for r in records:
        error = (r.get("error") or "").lower()
        response = r.get("response", "")

        if "rate_limit" in error or "rate limit" in error:
            categories["integration_rate_limit"].append(r)
        elif "authentication" in error or "api_key" in error or "401" in error:
            categories["integration_auth"].append(r)
        elif "connection" in error or "timeout" in error or "network" in error:
            categories["integration_network"].append(r)
        elif response and any(p in response.lower() for p in ["i cannot", "i can't", "i'm unable", "i am unable"]):
            categories["model_refusal"].append(r)
        elif r.get("error") is None and len(response) < 10:
            categories["model_short_response"].append(r)
        elif r.get("error") is not None:
            categories["unknown"].append(r)

    return {k: v for k, v in categories.items() if v}


def print_summary(log_path: str = "ai_calls.jsonl") -> None:
    records = load_log(log_path)
    if not records:
        print("No records found.")
        return

    latencies = [r["latency_ms"] for r in records]
    print(f"Total calls:     {len(records)}")
    print(f"Failure rate:    {failure_rate(records):.1%}")
    print(f"Avg latency:     {sum(latencies) / len(latencies):.0f} ms")
    print(f"Max latency:     {max(latencies)} ms")
    print(f"Slow calls:      {len(slow_calls(records))} (>3000ms)")
    print(f"Total cost:      ${total_cost(records):.4f}")

    categories = classify_failures(records)
    if categories:
        print(f"\nFailure breakdown:")
        for category, items in categories.items():
            print(f"  {category}: {len(items)}")
    else:
        print("\nNo failures recorded.")


# ─────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────

DEMO_PROMPTS = [
    "Summarize in one sentence: The transformer uses self-attention instead of recurrence.",
    "List three benefits of containerization for AI apps. Be concise.",
    "What is the primary difference between a Python script and a FastAPI service?",
]


def main() -> None:
    log_path = "ai_calls.jsonl"
    logger = DebugLogger(log_path=log_path)

    print("Making 3 calls with DebugLogger...\n")

    for i, prompt in enumerate(DEMO_PROMPTS, 1):
        print(f"Call {i}: {prompt[:70]}")
        try:
            response = logger.call(prompt, temperature=1.0)
            print(f"  -> {response[:100].strip()}")
        except RuntimeError as e:
            print(f"  -> ERROR: {e}")
        print()

    print("=" * 55)
    print_summary(log_path)
    print()
    print(f"Full log: {log_path}")
    print("Each line is a complete JSON record.")
    print()
    print("To reproduce a specific call at temperature=0:")
    print('  logger.call(records[0]["prompt"], temperature=0.0)')


if __name__ == "__main__":
    main()
