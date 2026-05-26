# Cost and Latency from Line One

> If you cannot measure it, you cannot afford to ship it.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lesson 03 (first API call), Lesson 05 (reading model docs)
**Time:** ~45 min
**Phase:** 00 - Setup and Mindset

---

## Learning Objectives

- Calculate the exact cost of any API request from the response usage object
- Distinguish wall-clock latency from time-to-first-token (TTFT) and know which matters for which UX pattern
- Build a `CostTracker` class that records latency, token counts, and running cost totals
- Identify which latency components you control and which you cannot
- Explain why output tokens cost more than input tokens and what that means for prompt design

---

## The Problem

You ship your first AI feature. It works. Costs look fine in testing - each request is a few cents. Three weeks later, the team is using it heavily and your API bill is $800 for the month instead of the $80 you budgeted. You investigate and discover that a prompt template you wrote starts every response with "Of course! I'd be happy to help you with that. Here's what I found:". That preamble is 20 output tokens per request. At 50,000 requests a month, that is 1 million output tokens - $4 in extra cost every month just for the greeting. Multiplied across 10 prompt templates, you have accidentally purchased $40/month of filler text.

Meanwhile, a user-facing feature that felt "fast enough" in testing is getting complaints in production. You measure it: median response time is 4.2 seconds. Users abandon chatbots after about 3 seconds. But you have no logs showing whether the 4.2 seconds is network overhead, TTFT, or generation time. Without that breakdown, you cannot fix it.

Both problems have the same root cause: you did not instrument cost and latency from line one. These are not ops concerns you add later. They are engineering constraints you measure from the first request.

---

## The Concept

### Where Latency Comes From

```
Your Code                  Anthropic API
    |                           |
    |---[1. Network: ~30ms]---->|
    |                           |--[2. Queue: 0ms-2000ms]
    |                           |--[3. TTFT: 200ms-800ms]
    |<--[first token]-----------|
    |                           |--[4. Generation: 50ms per 100 tokens]
    |<--[last token]------------|
    |---[5. Your processing]--->
    |
    v
 Wall-clock latency = 1 + 2 + 3 + 4 + 5
```

**What you control:**
- Request size (fewer input tokens = less to process)
- Output length (fewer requested tokens = less to generate)
- Model choice (smaller models have lower TTFT and faster generation)
- Streaming (shows first token to user sooner, even if total time is the same)
- Your processing code (step 5)

**What you cannot control:**
- Network latency (geography, provider infrastructure)
- Queue time (when Anthropic's API is under load)
- TTFT (fundamental to how transformer inference works)

```mermaid
flowchart LR
    A[Your App] -->|request| B[Network]
    B -->|50-100ms| C[API Queue]
    C -->|0-2000ms| D[Model Load\nTTFT]
    D -->|200-800ms| E[Token Generation\n~50ms per 100 tokens]
    E -->|stream or batch| F[Your App]
    
    style C fill:#f5a623,color:#000
    style D fill:#f5a623,color:#000
```

### The Output Token Asymmetry

```
                  INPUT TOKENS          OUTPUT TOKENS
Cost:             $0.80 / 1M            $4.00 / 1M
Speed:            parallel              sequential (one at a time)
Control:          you write the prompt  you can cap with max_tokens
Ratio:            5x cheaper            5x more expensive

Example prompt:
  Input:  "Summarize this 500-word article in 3 bullet points"
          = ~20 tokens
  Output: "Sure! Here are 3 bullet points:\n• ..." + actual bullets
          = ~150 tokens

  The preamble ("Sure! Here are 3 bullet points:") = ~10 tokens
  Cost of that preamble = 10 * ($4.00 / 1,000,000) = $0.00004 per call
  At 100,000 calls/month = $4.00/month wasted on filler text

  Fix: instruct the model to skip the preamble. "Respond with the 3
  bullet points only. No introduction." Saves output tokens,
  reduces latency, improves UX.
```

---

## Build It

### Step 1: The CostTracker Class

```python
# code/main.py
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic

MODEL = "claude-3-5-haiku-20241022"
PRICING = {
    "input_per_million": 0.80,
    "output_per_million": 4.00,
    "cache_read_per_million": 0.08,
}


@dataclass
class RequestRecord:
    """A single recorded API request with timing and cost data."""
    prompt_preview: str           # first 80 chars of the prompt
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    cache_cost_usd: float
    total_cost_usd: float
    wall_clock_seconds: float     # total request duration
    ttft_seconds: float | None    # time to first token (streaming only)


@dataclass
class CostTracker:
    """
    Wraps the Anthropic client to record cost and latency for every call.

    Usage:
        tracker = CostTracker()
        response, record = tracker.call(messages=[...])
        print(tracker.summary())
    """
    records: list[RequestRecord] = field(default_factory=list)
    _client: anthropic.Anthropic = field(default_factory=anthropic.Anthropic)

    def _compute_cost(self, usage: Any) -> tuple[float, float, float]:
        """Return (input_cost, output_cost, cache_cost) in USD."""
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0

        # Fresh input = total input minus what came from cache
        fresh_input = max(0, input_tokens - cache_read_tokens)

        input_cost = (fresh_input / 1_000_000) * PRICING["input_per_million"]
        output_cost = (output_tokens / 1_000_000) * PRICING["output_per_million"]
        cache_cost = (cache_read_tokens / 1_000_000) * PRICING["cache_read_per_million"]

        return input_cost, output_cost, cache_cost
```

### Step 2: The Tracked API Call

```python
    def call(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
        model: str = MODEL,
    ) -> tuple[anthropic.types.Message, RequestRecord]:
        """
        Make an API call and record cost + latency.
        Returns (response, record) so you can use the response normally.
        """
        prompt_preview = str(messages[0].get("content", ""))[:80]

        start = time.perf_counter()

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)

        elapsed = time.perf_counter() - start

        usage = response.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        input_cost, output_cost, cache_cost = self._compute_cost(usage)
        total_cost = input_cost + output_cost + cache_cost

        record = RequestRecord(
            prompt_preview=prompt_preview,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            cache_cost_usd=cache_cost,
            total_cost_usd=total_cost,
            wall_clock_seconds=elapsed,
            ttft_seconds=None,  # not available in non-streaming mode
        )
        self.records.append(record)

        return response, record
```

### Step 3: Streaming with TTFT Measurement

```python
    def call_streaming(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
        model: str = MODEL,
    ) -> tuple[str, RequestRecord]:
        """
        Streaming call that measures time-to-first-token (TTFT).
        Returns (full_text, record).
        """
        prompt_preview = str(messages[0].get("content", ""))[:80]

        start = time.perf_counter()
        ttft = None
        text_parts = []
        final_usage = None

        kwargs = {
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
            final_message = stream.get_final_message()
            final_usage = final_message.usage

        elapsed = time.perf_counter() - start
        full_text = "".join(text_parts)

        input_tokens = final_usage.input_tokens
        output_tokens = final_usage.output_tokens
        cache_read = getattr(final_usage, "cache_read_input_tokens", 0) or 0

        input_cost, output_cost, cache_cost = self._compute_cost(final_usage)
        total_cost = input_cost + output_cost + cache_cost

        record = RequestRecord(
            prompt_preview=prompt_preview,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            cache_cost_usd=cache_cost,
            total_cost_usd=total_cost,
            wall_clock_seconds=elapsed,
            ttft_seconds=ttft,
        )
        self.records.append(record)

        return full_text, record
```

### Step 4: The Summary Report

```python
    def summary(self) -> str:
        """Return a formatted cost and latency summary."""
        if not self.records:
            return "No requests recorded."

        total_cost = sum(r.total_cost_usd for r in self.records)
        total_input = sum(r.input_tokens for r in self.records)
        total_output = sum(r.output_tokens for r in self.records)
        avg_latency = sum(r.wall_clock_seconds for r in self.records) / len(self.records)

        ttft_records = [r for r in self.records if r.ttft_seconds is not None]
        avg_ttft = (
            sum(r.ttft_seconds for r in ttft_records) / len(ttft_records)
            if ttft_records else None
        )

        lines = [
            f"{'='*55}",
            f"  Cost and Latency Summary ({len(self.records)} requests)",
            f"{'='*55}",
            f"  Total cost       : ${total_cost:.6f}",
            f"  Total input tok  : {total_input:,}",
            f"  Total output tok : {total_output:,}",
            f"  Output/input ratio: {total_output/max(total_input,1):.2f}",
            f"  Avg wall-clock   : {avg_latency:.2f}s",
        ]
        if avg_ttft is not None:
            lines.append(f"  Avg TTFT         : {avg_ttft:.2f}s")

        # Per-request breakdown
        lines.append(f"\n  Per-request breakdown:")
        for i, r in enumerate(self.records, 1):
            ttft_str = f"  ttft={r.ttft_seconds:.2f}s" if r.ttft_seconds else ""
            lines.append(
                f"  [{i}] ${r.total_cost_usd:.6f}  "
                f"in={r.input_tokens} out={r.output_tokens}  "
                f"wall={r.wall_clock_seconds:.2f}s{ttft_str}"
            )
            lines.append(f"      \"{r.prompt_preview}...\"")

        # Monthly projection
        if len(self.records) > 0:
            avg_cost = total_cost / len(self.records)
            lines.append(f"\n  Monthly projections (avg ${avg_cost:.6f}/req):")
            for volume in [1_000, 10_000, 100_000]:
                projected = avg_cost * volume
                lines.append(f"    {volume:>8,} req/month = ${projected:.2f}/month")

        return "\n".join(lines)
```

> **Real-world check:** Your tech lead reviews your CostTracker and says: "This is nice instrumentation, but production systems should use a dedicated observability platform like Langfuse or Datadog, not a homegrown class." They are right - but what does building this class first teach you that you would not get from dropping in a third-party SDK on day one?

---

## Use It

The `response.usage` object is the production-grade source of truth for token counts. The anthropic SDK surfaces it directly:

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Summarize AI in one sentence."}],
)

# These are your ground truth numbers - always log them.
print(f"Input tokens  : {response.usage.input_tokens}")
print(f"Output tokens : {response.usage.output_tokens}")

# Compute cost inline - no class needed for simple scripts
input_cost = response.usage.input_tokens * 0.80 / 1_000_000
output_cost = response.usage.output_tokens * 4.00 / 1_000_000
print(f"Request cost  : ${input_cost + output_cost:.6f}")

# For streaming, get usage from the final message
with client.messages.stream(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Count to 5."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
    final = stream.get_final_message()
    print(f"\nUsage: {final.usage}")
```

The SDK's usage data integrates with Langfuse, Braintrust, and other observability platforms via callbacks or manual logging. The data model is always the same: input tokens, output tokens, optional cache tokens.

> **Perspective shift:** A startup founder tells you they are not worrying about token costs right now because their monthly API bill is only $50 and "scale is a good problem to have." At what point does this framing become dangerous, and what specific cost pattern in AI applications makes this different from scaling a typical web API?

---

## Ship It

The output for this lesson is `outputs/skill-cost-latency-tracker.md`: a reusable implementation guide for instrumenting cost and latency in any AI application.

Run the cost tracker demo:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
cd phases/00-setup-and-mindset/06-cost-and-latency
python code/main.py
```

The script runs three requests (short, long, streaming) and prints a full cost and latency breakdown with monthly projections.

---

## Evaluate It

**Check 1: Run the tracker on your own prompts.**

Run the `CostTracker` on five prompts you are actually using in your work. Look at the output-to-input token ratio. If any prompt has an output/input ratio greater than 1.0 and the verbose preamble ("Sure! Here's what I found:") is contributing to that, rewrite the prompt with explicit instructions to skip the preamble. Measure the before/after token counts.

**Check 2: Measure TTFT on a streaming request.**

Use the `call_streaming` method and measure the TTFT. For a short simple request (under 100 input tokens), TTFT should be under 1 second. If it is consistently above 2 seconds, check whether you are on a congested region endpoint.

**Check 3: Build your monthly cost estimate.**

For the feature you are building, estimate: average input tokens per request, average output tokens per request, expected requests per month. Plug into the projection math in the tracker. If the monthly cost exceeds your budget, identify which component (input, output, or volume) is the driver and what your options are.
