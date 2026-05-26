"""
Lesson 06: Cost and Latency from Line One
Phase 00: Setup and Mindset

A CostTracker class that wraps the Anthropic API client to record:
  - Wall-clock latency per request
  - Time-to-first-token (TTFT) for streaming requests
  - Input and output token counts from response.usage
  - Per-request cost and running totals
  - Monthly cost projections

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python code/main.py
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-3-5-haiku-20241022"

# Pricing in USD per million tokens.
# Source: https://www.anthropic.com/pricing
# Verify before shipping - prices change.
PRICING = {
    "input_per_million": 0.80,
    "output_per_million": 4.00,
    "cache_read_per_million": 0.08,
    "cache_write_per_million": 1.00,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RequestRecord:
    """Immutable record of a single API request's cost and timing data."""
    prompt_preview: str           # first 80 chars of the first user message
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    input_cost_usd: float         # cost of fresh (non-cached) input tokens
    output_cost_usd: float
    cache_cost_usd: float
    total_cost_usd: float
    wall_clock_seconds: float     # total time from call start to last token
    ttft_seconds: float | None    # time to first token (streaming only)

    def display(self) -> str:
        ttft_str = f"  ttft={self.ttft_seconds:.2f}s" if self.ttft_seconds else ""
        return (
            f"  cost=${self.total_cost_usd:.6f}  "
            f"in={self.input_tokens} out={self.output_tokens}  "
            f"wall={self.wall_clock_seconds:.2f}s{ttft_str}\n"
            f"  prompt: \"{self.prompt_preview}...\""
        )


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------

@dataclass
class CostTracker:
    """
    Wraps the Anthropic API to record cost and latency for every call.

    All calls append a RequestRecord to self.records.
    Call summary() to see aggregate stats and monthly projections.
    """
    records: list[RequestRecord] = field(default_factory=list)
    _client: anthropic.Anthropic = field(
        default_factory=lambda: anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    )

    def _compute_cost(self, usage: Any) -> tuple[float, float, float]:
        """
        Compute (input_cost, output_cost, cache_cost) from a usage object.

        Separates fresh input tokens from cache-read tokens so each is
        priced at the correct rate.
        """
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0

        fresh_input = max(0, input_tokens - cache_read_tokens)

        input_cost = (fresh_input / 1_000_000) * PRICING["input_per_million"]
        output_cost = (output_tokens / 1_000_000) * PRICING["output_per_million"]
        cache_cost = (cache_read_tokens / 1_000_000) * PRICING["cache_read_per_million"]

        return input_cost, output_cost, cache_cost

    def call(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
        model: str = MODEL,
    ) -> tuple[anthropic.types.Message, RequestRecord]:
        """
        Non-streaming API call with cost and wall-clock latency tracking.

        Returns:
            (response, record) - use response normally, record for instrumentation.
        """
        prompt_preview = str(messages[0].get("content", ""))[:80]
        start = time.perf_counter()

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        elapsed = time.perf_counter() - start

        usage = response.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        input_cost, output_cost, cache_cost = self._compute_cost(usage)

        record = RequestRecord(
            prompt_preview=prompt_preview,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=cache_read,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            cache_cost_usd=cache_cost,
            total_cost_usd=input_cost + output_cost + cache_cost,
            wall_clock_seconds=elapsed,
            ttft_seconds=None,
        )
        self.records.append(record)
        return response, record

    def call_streaming(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
        model: str = MODEL,
        print_output: bool = True,
    ) -> tuple[str, RequestRecord]:
        """
        Streaming API call that measures time-to-first-token (TTFT).

        Returns:
            (full_text, record) - use full_text as the response content.
        """
        prompt_preview = str(messages[0].get("content", ""))[:80]
        start = time.perf_counter()
        ttft: float | None = None
        text_parts: list[str] = []

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                if ttft is None:
                    ttft = time.perf_counter() - start
                text_parts.append(text)
                if print_output:
                    print(text, end="", flush=True)
            if print_output:
                print()  # newline after streaming output
            final_message = stream.get_final_message()
            usage = final_message.usage

        elapsed = time.perf_counter() - start
        full_text = "".join(text_parts)

        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        input_cost, output_cost, cache_cost = self._compute_cost(usage)

        record = RequestRecord(
            prompt_preview=prompt_preview,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=cache_read,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            cache_cost_usd=cache_cost,
            total_cost_usd=input_cost + output_cost + cache_cost,
            wall_clock_seconds=elapsed,
            ttft_seconds=ttft,
        )
        self.records.append(record)
        return full_text, record

    def summary(self) -> str:
        """Return a formatted cost and latency summary with monthly projections."""
        if not self.records:
            return "No requests recorded."

        n = len(self.records)
        total_cost = sum(r.total_cost_usd for r in self.records)
        total_input = sum(r.input_tokens for r in self.records)
        total_output = sum(r.output_tokens for r in self.records)
        avg_latency = sum(r.wall_clock_seconds for r in self.records) / n

        ttft_records = [r for r in self.records if r.ttft_seconds is not None]
        avg_ttft_str = (
            f"{sum(r.ttft_seconds for r in ttft_records) / len(ttft_records):.2f}s"
            if ttft_records else "n/a (no streaming requests)"
        )

        output_input_ratio = total_output / max(total_input, 1)
        avg_cost = total_cost / n

        lines = [
            f"\n{'='*57}",
            f"  Cost + Latency Summary ({n} request{'s' if n != 1 else ''})",
            f"{'='*57}",
            f"  Total cost         : ${total_cost:.6f}",
            f"  Total input tokens : {total_input:,}",
            f"  Total output tokens: {total_output:,}",
            f"  Output/input ratio : {output_input_ratio:.2f}",
            f"  Avg wall-clock     : {avg_latency:.2f}s",
            f"  Avg TTFT (stream)  : {avg_ttft_str}",
            "",
            "  Per-request breakdown:",
        ]

        for i, r in enumerate(self.records, 1):
            lines.append(f"  [{i}] {r.display()}")

        lines.append("")
        lines.append(f"  Monthly projections (${avg_cost:.6f}/req average):")
        for volume in [1_000, 10_000, 100_000, 1_000_000]:
            projected = avg_cost * volume
            lines.append(f"    {volume:>10,} req/month = ${projected:>8.2f}/month")

        if output_input_ratio > 0.5:
            lines.append("")
            lines.append("  Note: output/input ratio > 0.5 - check for verbose preambles.")
            lines.append("  Output tokens cost 5x more than input. Cutting output saves fast.")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo() -> None:
    """Run three requests showing cost and latency patterns."""
    tracker = CostTracker()

    print("Request 1: Short prompt, short response")
    print("-" * 40)
    response, record = tracker.call(
        messages=[{"role": "user", "content": "What is 2 + 2?"}],
        max_tokens=50,
    )
    print(f"Response: {response.content[0].text}")
    print(record.display())

    print("\nRequest 2: Longer prompt with preamble instruction")
    print("-" * 40)
    response2, record2 = tracker.call(
        messages=[{
            "role": "user",
            "content": (
                "List three benefits of using type hints in Python. "
                "Respond with the numbered list only. No preamble or conclusion."
            ),
        }],
        max_tokens=200,
    )
    print(f"Response: {response2.content[0].text}")
    print(record2.display())

    print("\nRequest 3: Streaming with TTFT measurement")
    print("-" * 40)
    full_text, record3 = tracker.call_streaming(
        messages=[{
            "role": "user",
            "content": "Explain why output tokens cost more than input tokens in one paragraph.",
        }],
        max_tokens=150,
        print_output=True,
    )
    print(record3.display())

    print(tracker.summary())


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY environment variable before running.")
        print("Example: export ANTHROPIC_API_KEY=sk-ant-...")
        raise SystemExit(1)
    demo()
