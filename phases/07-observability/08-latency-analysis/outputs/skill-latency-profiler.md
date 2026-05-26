---
name: skill-latency-profiler
description: Latency profiler for LLM endpoints measuring TTFT, total latency percentiles, and bottleneck attribution
version: "1.0"
phase: "07"
lesson: "08"
tags: [latency, observability, p99, ttft, performance, streaming]
---

# Skill: LLM Latency Profiler

## Purpose

You are an applied AI engineering advisor. When a user needs to measure, diagnose, or reduce LLM latency, use this skill to guide measurement strategy and bottleneck analysis.

---

## The Two Latency Metrics That Matter

| Metric | What it measures | Why it matters |
|---|---|---|
| TTFT (time-to-first-token) | Time from request start to first streaming chunk | UX perception - determines if the app "feels" fast |
| Total latency | Time from request start to last token | When the user can act on the complete response |

For non-streaming: only total latency matters.
For streaming: TTFT is the primary UX metric; total latency is secondary.

---

## Where Time Goes

```
[Start] -> Network RTT -> Queuing -> Prefill -> [FIRST TOKEN] -> Generation -> Post-process -> [End]
            50-150ms      10-100ms  50-500ms                    ms/tok * N    1-50ms
```

Prefill scales with input token count.
Generation scales with output token count.
TTFT = network + queue + prefill.

---

## Percentile Reference

| Percentile | Meaning | Action threshold |
|---|---|---|
| p50 | Median: what most users experience | Target < 1.5s for interactive features |
| p95 | 1 in 20 users waits this long | Target < 4s |
| p99 | 1 in 100 users waits this long | Target < 8s; > 10s risks timeouts |
| p99/mean | Tail severity ratio | > 5x: investigate outlier causes |

---

## Bottleneck Diagnosis

**TTFT dominates (TTFT > 60% of total at p99):**
- Long prompt/system prompt (slow prefill)
- Network round-trip to API region
- API cold start or queuing under load
- Fix: prompt compression, prompt caching, CDN edge endpoint

**Generation dominates (generation > 60% of total at p99):**
- Output tokens are the primary cost
- No explicit length constraint in prompt
- Model generating unnecessarily verbose responses
- Fix: add output length instructions, reduce max_tokens, use streaming to improve perceived speed

---

## Quick Measurement Pattern

```python
import time
import anthropic

def measure_ttft(prompt: str) -> tuple[float, float]:
    """Returns (ttft_ms, total_ms)."""
    client = anthropic.Anthropic()
    start = time.monotonic()
    ttft = None

    with client.messages.stream(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            if ttft is None:
                ttft = (time.monotonic() - start) * 1000
            # consume remaining stream

    total = (time.monotonic() - start) * 1000
    return ttft or total, total
```

---

## SLO Design Recommendations

For AI-powered features in SaaS products:

| Feature type | TTFT SLO | Total latency SLO | Measurement window |
|---|---|---|---|
| Interactive chat | p99 < 1.5s | p99 < 8s | 5-minute rolling |
| Search/assist | p99 < 800ms | p99 < 5s | 5-minute rolling |
| Background processing | N/A | p99 < 30s | 1-hour rolling |
| Streaming generation | p99 < 1s | p95 < 12s | 5-minute rolling |

Track TTFT SLO compliance separately from total latency SLO. They have different root causes and different fixes.

---

## Exporting to Observability Backends

To export from `LatencyProfiler` to OpenTelemetry (Phase 07 L02-L03):

```python
from opentelemetry import metrics

meter = metrics.get_meter("llm.latency")
ttft_histogram = meter.create_histogram(
    "gen_ai.client.ttft",
    unit="ms",
    description="Time to first token for LLM streaming calls",
)
total_histogram = meter.create_histogram(
    "gen_ai.client.operation.duration",
    unit="ms",
    description="Total LLM request duration",
)

# In your call wrapper:
ttft_histogram.record(ttft_ms, {"gen_ai.system": "anthropic", "gen_ai.operation.name": "chat"})
total_histogram.record(total_ms, {"gen_ai.system": "anthropic", "gen_ai.operation.name": "chat"})
```

This follows the OpenTelemetry GenAI semantic conventions (`gen_ai.*`) from Phase 07 L02.
