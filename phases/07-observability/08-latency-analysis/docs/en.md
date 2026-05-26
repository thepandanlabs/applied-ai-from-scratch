# Latency: p50/p95/p99, TTFT, and Where Time Goes

> p50 tells you what most users experience. p99 tells you who churns.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 07 Lessons 01, 05 (Observability fundamentals, LLM request logging)
**Time:** ~60 min
**Learning Objectives:**
- Decompose LLM request latency into its constituent parts: network, TTFT, generation, post-processing
- Measure time-to-first-token (TTFT) separately from total latency for streaming endpoints
- Compute p50, p95, and p99 percentiles and explain why p99 matters for user retention
- Identify which latency component is the bottleneck from a percentile distribution
- Wire a `LatencyProfiler` into a streaming endpoint

---

## The Problem

Your AI feature has a p50 latency of 1.2 seconds. Feels fine in testing. You ship it.

Two months later, churn analysis shows that users who experience more than 4-second responses are 3x more likely to not come back. You look at your latency data for the first time. You have no percentiles. You have no TTFT. You have average latency: 1.4 seconds. Looks fine.

What you missed: p99 latency is 8.7 seconds. 1 in 100 requests takes nearly 9 seconds. At 10,000 daily users, that is 100 people per day experiencing an 8.7-second wait. Every day. For two months. That is 6,000 people who had a bad enough experience that your churn rate climbed.

The mean lied to you. Percentiles would not have.

---

## The Concept

### Where Time Goes in a Streaming LLM Request

```
Request timeline (wall clock):

[Client sends request]
     |
     |---- Network: client to API edge -----------| ~50-150ms (varies by region)
                                                  |
     |---- API queuing + scheduling -------| ~10-100ms (varies by load)
                                           |
     |---- Prompt processing (prefill) ---| ~50-500ms (scales with prompt length)
                                          |
                                          | FIRST TOKEN ARRIVES HERE  <-- TTFT
                                          |
     |--- Generation (decode) -------------------------| ms/token * output_tokens
                                                       |
     |--- Network: API to client (streaming chunks) --| per-chunk latency
                                                      |
     [Last token received]                            |
     |--- Post-processing (parse, validate, format) --| ~1-50ms
     [Response delivered to user]
```

**Key insight for streaming:** Users see the first token before generation is complete. TTFT is what determines whether the UI "feels" responsive. Total latency is what determines when the user can act on the full response. Both matter; they matter differently.

### Percentiles and Why Average Misleads

```
Example latency distribution (1000 requests):
  800 requests: 0.8 - 1.5 seconds   (fast, warm paths)
  150 requests: 2.0 - 3.5 seconds   (cold starts, longer prompts)
   40 requests: 4.0 - 6.0 seconds   (retry paths, peak load)
   10 requests: 7.0 - 12.0 seconds  (timeout edge cases, network issues)

Statistics:
  mean:   1.8 seconds   (pulled up by the tail - looks acceptable)
  median: 1.2 seconds   (p50 - what most users experience)
  p95:    4.2 seconds   (1 in 20 users waits this long)
  p99:    8.7 seconds   (1 in 100 users waits this long)
  p999:  11.5 seconds   (1 in 1000 users - may trigger client timeouts)

Mean: 1.8s looks fine. p99: 8.7s does not.
```

**User experience thresholds (AI features):**
```
Under 1s   : Feels instant, no perceived latency
1s - 3s    : Acceptable for complex AI tasks
3s - 5s    : Users notice the wait; some abandon
Over 5s    : Significant abandonment; clear UX damage
Over 10s   : Timeout territory; users assume it is broken
```

### The Streaming UX Equation

For non-streaming responses, total latency is what the user waits.
For streaming responses, the UX equation changes:

```
Perceived wait  =  TTFT   (until UI shows "thinking is done, here it comes")
Content quality  =  total response / generation time
User patience   =  f(TTFT)  -- users tolerate long generation if TTFT is low
```

This is why streaming matters. A 5-second total generation with a 300ms TTFT feels acceptable. A 5-second total generation with a 4-second TTFT feels broken.

---

## Build It

### Step 1: TTFT Measurement with Streaming

```python
import time
import anthropic
from typing import Optional, Iterator

client = anthropic.Anthropic()


def stream_with_ttft(
    prompt: str,
    model: str = "claude-3-5-haiku-20241022",
) -> tuple[str, float, float]:
    """
    Stream a response and measure TTFT and total latency separately.

    Returns:
        (full_response_text, ttft_ms, total_latency_ms)
    """
    start = time.monotonic()
    ttft_ms: Optional[float] = None
    chunks: list[str] = []

    with client.messages.stream(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text_chunk in stream.text_stream:
            if ttft_ms is None:
                ttft_ms = (time.monotonic() - start) * 1000
            chunks.append(text_chunk)

    total_ms = (time.monotonic() - start) * 1000
    return "".join(chunks), ttft_ms or total_ms, total_ms
```

### Step 2: Percentile Calculator

```python
import statistics
from dataclasses import dataclass


@dataclass
class PercentileReport:
    count: int
    p50_ms: float
    p75_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    mean_ms: float


def compute_percentiles(latencies_ms: list[float]) -> PercentileReport:
    """
    Compute latency percentiles from a list of measurements.
    Uses linear interpolation (the standard definition).
    """
    if not latencies_ms:
        raise ValueError("Cannot compute percentiles of empty list")

    sorted_vals = sorted(latencies_ms)
    n = len(sorted_vals)

    def percentile(p: float) -> float:
        """Linear interpolation percentile."""
        idx = (p / 100) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return round(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac, 2)

    return PercentileReport(
        count=n,
        p50_ms=percentile(50),
        p75_ms=percentile(75),
        p90_ms=percentile(90),
        p95_ms=percentile(95),
        p99_ms=percentile(99),
        min_ms=round(min(sorted_vals), 2),
        max_ms=round(max(sorted_vals), 2),
        mean_ms=round(statistics.mean(sorted_vals), 2),
    )
```

### Step 3: LatencyProfiler

```python
import json
from collections import defaultdict
from datetime import datetime, timezone


class LatencyProfiler:
    """
    Tracks TTFT and total latency across multiple calls.
    Computes percentiles and identifies the latency bottleneck.

    Usage:
        profiler = LatencyProfiler()

        response, ttft, total = stream_with_ttft(prompt)
        profiler.record(ttft_ms=ttft, total_ms=total, feature="search")

        report = profiler.report()
        print(report)
    """

    def __init__(self):
        self._ttft_records: list[float] = []
        self._total_records: list[float] = []
        self._by_feature: dict[str, list[tuple[float, float]]] = defaultdict(list)

    def record(
        self,
        ttft_ms: float,
        total_ms: float,
        feature: str = "default",
    ) -> None:
        """Record one latency measurement."""
        self._ttft_records.append(ttft_ms)
        self._total_records.append(total_ms)
        self._by_feature[feature].append((ttft_ms, total_ms))

    def report(self) -> str:
        """Render an ASCII latency report."""
        if not self._ttft_records:
            return "No data recorded."

        ttft_stats = compute_percentiles(self._ttft_records)
        total_stats = compute_percentiles(self._total_records)

        # Estimate generation time = total - TTFT (approximate)
        gen_times = [
            t - f for f, t in zip(self._ttft_records, self._total_records)
        ]
        gen_stats = compute_percentiles(gen_times)

        lines = []
        lines.append("=" * 60)
        lines.append("LATENCY REPORT")
        lines.append("=" * 60)
        lines.append(f"Total measurements : {ttft_stats.count}")

        lines.append("\n--- Time-to-First-Token (TTFT) ---")
        lines.append(_stats_table(ttft_stats))

        lines.append("\n--- Total Latency ---")
        lines.append(_stats_table(total_stats))

        lines.append("\n--- Generation Time (Total - TTFT) ---")
        lines.append(_stats_table(gen_stats))

        # Bottleneck analysis
        lines.append("\n--- Bottleneck Analysis ---")
        ttft_share = ttft_stats.p99_ms / total_stats.p99_ms * 100 if total_stats.p99_ms else 0
        gen_share = 100 - ttft_share
        lines.append(f"At p99: TTFT = {ttft_share:.0f}% of total, generation = {gen_share:.0f}%")
        if ttft_share > 60:
            lines.append("  -> Bottleneck: network + prefill (TTFT dominates)")
            lines.append("     Fix: prompt compression, CDN edge, or async prefill")
        else:
            lines.append("  -> Bottleneck: generation (output tokens dominate)")
            lines.append("     Fix: max_tokens limit, output length instructions, or streaming")

        # Per-feature breakdown
        if len(self._by_feature) > 1:
            lines.append("\n--- By Feature (p99 Total) ---")
            for feat, records in sorted(self._by_feature.items()):
                totals = [r[1] for r in records]
                stats = compute_percentiles(totals)
                lines.append(
                    f"  {feat:<25} n={stats.count:>4}  "
                    f"p50={stats.p50_ms:>7.0f}ms  p99={stats.p99_ms:>7.0f}ms"
                )

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    def alert_threshold_violations(
        self, p99_threshold_ms: float = 5000.0
    ) -> list[dict]:
        """
        Return records where total latency exceeded the threshold.
        Useful for feeding into alerting or SLO dashboards.
        """
        violations = []
        for i, (ttft, total) in enumerate(
            zip(self._ttft_records, self._total_records)
        ):
            if total > p99_threshold_ms:
                violations.append({"index": i, "ttft_ms": ttft, "total_ms": total})
        return violations


def _stats_table(s: PercentileReport) -> str:
    return (
        f"  min={s.min_ms:>7.0f}ms  "
        f"p50={s.p50_ms:>7.0f}ms  "
        f"p95={s.p95_ms:>7.0f}ms  "
        f"p99={s.p99_ms:>7.0f}ms  "
        f"max={s.max_ms:>7.0f}ms  "
        f"mean={s.mean_ms:>7.0f}ms"
    )
```

> **Real-world check:** Your product manager says "Our average latency is 1.4 seconds, which is well within the 3-second target. We don't need to track percentiles." You know from the data that p99 is 8.7 seconds. How do you explain, in terms the PM will act on, why the average is the wrong metric for a user retention conversation?

---

## Use It

The `LatencyProfiler` integrates into any code path that calls the model. For a FastAPI service, add it as middleware:

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()
profiler = LatencyProfiler()


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    prompt = body["message"]

    async def stream_response():
        import asyncio
        start = asyncio.get_event_loop().time()
        ttft = None
        full_text = []

        # Use the async streaming client in production
        for chunk in stream_with_ttft_sync(prompt):
            if ttft is None:
                ttft = (asyncio.get_event_loop().time() - start) * 1000
            full_text.append(chunk)
            yield chunk

        total = (asyncio.get_event_loop().time() - start) * 1000
        profiler.record(ttft_ms=ttft or total, total_ms=total, feature="chat")

    return StreamingResponse(stream_response(), media_type="text/plain")
```

**What the profiler adds over raw timing:**

| Approach | What you see | What you miss |
|---|---|---|
| `time.time()` before/after | Total latency, averaged | p95/p99 tail, TTFT, feature breakdown |
| `LatencyProfiler` | All percentiles, TTFT vs generation split, per-feature p99, bottleneck analysis | (nothing - this is the full picture) |

> **Perspective shift:** A backend engineer says: "We already have latency in our distributed tracing (Datadog APM). Why build a separate profiler?" When is the custom profiler worth maintaining alongside general-purpose APM, and what does it give you that APM does not?

---

## Ship It

**Artifact:** `outputs/skill-latency-profiler.md`

This lesson produces a `LatencyProfiler` class that measures TTFT and total latency separately, computes percentiles, and identifies the latency bottleneck. The profiler is stateful (accumulates measurements across calls) and intended to run in-process. For distributed systems, export percentile summaries to your observability backend (Langfuse, Datadog, OpenTelemetry) at regular intervals.

---

## Evaluate It

**Verification 1: TTFT is always less than or equal to total latency**

```python
_, ttft, total = stream_with_ttft("What is 2+2?")
assert ttft <= total, f"TTFT ({ttft}ms) cannot exceed total ({total}ms)"
```

**Verification 2: Percentiles are monotonically increasing**

```python
stats = compute_percentiles([random.uniform(100, 5000) for _ in range(100)])
assert stats.p50_ms <= stats.p95_ms <= stats.p99_ms <= stats.max_ms
```

**Verification 3: p99 is substantially higher than mean for realistic workloads**

After running 50+ real calls, compute the p99/mean ratio. For LLM endpoints, this ratio is typically 3-7x. If your p99 equals your mean, you likely have insufficient data or an unusually uniform workload.

**Verification 4: Bottleneck attribution is actionable**

From 50+ profiled calls, the bottleneck analysis should tell you one of:
- "TTFT dominates" - investigate prompt length, prefill time, network routing
- "Generation dominates" - investigate output token counts, max_tokens setting, model tier

If both are equal, you have balanced optimization headroom on both sides. That is an unusual and enviable position.
