---
name: skill-trace-debug-workflow
description: The 5-step trace review workflow for debugging production AI failures; includes the 4 anomaly classes to check, how to find the root cause span, and how to use trace data to answer user complaints with evidence
version: "1.0"
phase: "07"
lesson: "04"
tags: [debugging, tracing, langfuse, observability, production, llm-ops]
---

# Skill: Trace Debug Workflow

## Purpose

You are an applied AI engineering advisor specializing in production LLM debugging. When a user reports a failure in an AI service, use this skill to walk them through the 5-step trace review workflow and identify the root cause span.

---

## Core Principle

The trace is the single artifact that connects a user complaint ("the answer was wrong") to the exact prompt, response, and timing that caused it. Without traces, you are debugging with print() statements in production.

A failing trace has patterns. Four anomaly classes cover the majority of production LLM failures.

---

## The 4 Anomaly Classes

| Class | Signal | Root Cause |
|-------|--------|-----------|
| Error span | `error` field non-null | API failure, auth error, rate limit |
| High latency | `latency_ms` >> baseline | Slow tool, model timeout, large context |
| High cost | `cost_usd` >> baseline | Prompt bloat, runaway generation, missing cache |
| Low token efficiency | `output_tokens / input_tokens < 0.05` | Over-padded prompt, irrelevant RAG context |

---

## The 5-Step Debug Workflow

**Step 1: Find the failing trace**
- By error flag: filter traces where `error != null`
- By latency: filter where `latency_ms > P95 * 2`
- By cost: filter where `cost_usd > P95 * 2`
- By user report: look up by user ID + timestamp range
- By trace_id: if your API returns trace_id in responses, use it directly

**Step 2: Expand the span tree**
- Find the deepest span where `status = ERROR` or where latency spiked
- For tool-using agents: look at tool call spans for malformed results

**Step 3: Read prompt + response at the failing span**
- Check `gen_ai.content.prompt` event: was the context complete and correct?
- Check `gen_ai.content.completion` event: what did the model actually say?
- Compare to expected output -- was the failure in the prompt or the response?

**Step 4: Check token counts and timing**
- `input_tokens >> baseline`: prompt bloat (too much context injected)
- `output_tokens >> baseline`: runaway generation (missing max_tokens limit)
- `latency_ms >> baseline but tokens normal`: model provider latency, not your code
- `cache_hit = False` on a request that should have been cached: caching misconfiguration

**Step 5: Identify root cause category**

| Category | Evidence | Action |
|----------|---------- |--------|
| Prompt regression | prompt_version changed + quality dropped | Roll back prompt template |
| Model error | status=ERROR, error class is API error | Check provider status; add retry |
| Tool failure | tool span ERROR, downstream LLM answer wrong | Fix tool validation; add fallback |
| Cost spike | input_tokens 3x+ baseline | Review RAG context injection; check max_tokens |

---

## Minimum TraceAnalyzer Implementation

```python
import statistics
from dataclasses import dataclass
from typing import Optional

@dataclass
class Anomaly:
    trace_id: str
    anomaly_type: str
    severity: str
    detail: str

def analyze_traces(records: list[dict]) -> list[Anomaly]:
    """Quick anomaly scan for a batch of trace records."""
    successful = [r for r in records if not r.get("error") and r.get("input_tokens", 0) > 0]
    
    if len(successful) >= 10:
        latency_vals = sorted(r["latency_ms"] for r in successful)
        p95_latency = latency_vals[int(len(successful) * 0.95)]
        p95_cost = sorted(r["cost_usd"] for r in successful)[int(len(successful) * 0.95)]
    else:
        p95_latency = max((r["latency_ms"] for r in successful), default=1000)
        p95_cost = max((r["cost_usd"] for r in successful), default=0.001)

    anomalies = []
    for r in records:
        tid = r.get("trace_id", "unknown")
        if r.get("error"):
            anomalies.append(Anomaly(tid, "error", "critical", r["error"]))
        if r.get("latency_ms", 0) > p95_latency * 2:
            anomalies.append(Anomaly(tid, "high_latency", "warning", f"{r['latency_ms']:.0f}ms"))
        inp, out = r.get("input_tokens", 0), r.get("output_tokens", 0)
        if inp > 100 and out > 0 and out / inp < 0.05:
            anomalies.append(Anomaly(tid, "low_token_efficiency", "warning", f"{out/inp:.3f}"))
    return anomalies
```

---

## Langfuse API: Pulling Failing Traces Programmatically

```python
from langfuse import Langfuse

lf = Langfuse()

# Get recent traces with errors
traces = lf.fetch_traces(limit=100).data
for t in traces:
    observations = lf.fetch_observations(trace_id=t.id).data
    for obs in observations:
        if obs.level == "ERROR":
            print(f"Failing trace: {t.id} at {t.timestamp}")
            print(f"  Error: {obs.status_message}")
            print(f"  Model: {obs.model}")
            break
```

---

## Investigation Checklist

When a user says "the AI gave a wrong answer":

1. Do you have the trace_id? (check API response or support ticket)
2. Open the trace in Langfuse: what is the status of the LLM call span?
3. Expand gen_ai.content.prompt: was the correct context injected?
4. Expand gen_ai.content.completion: what did the model actually say?
5. Check token counts: was input_tokens unusually high? (RAG injecting irrelevant docs)
6. Check prompt_version: was there a recent template deployment?
7. Check latency: was the model slow? (may have returned truncated response)

If content events are not captured, you cannot complete steps 3-4 -- enable them.
