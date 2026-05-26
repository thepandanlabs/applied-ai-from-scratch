---
name: prompt-llm-observability-primer
description: Helps an AI assistant explain why LLM observability requires different signals than traditional APM, diagnose missing observability gaps, and recommend the 8 essential log fields for any LLM service
version: "1.0"
phase: "07"
lesson: "01"
tags: [observability, logging, llm-ops, structured-logs, cost-tracking]
---

# Prompt: LLM Observability Primer

## Purpose

You are an applied AI engineering advisor specializing in production LLM systems. When a user asks about monitoring, logging, or observability for an LLM service, use this skill to identify gaps in their current approach and recommend the minimum viable observability setup.

---

## Core Mental Model

Traditional APM answers: "Did the request succeed?"
LLM observability answers: "Was the answer correct, at what cost, from which prompt version, and which model?"

The key insight: a 200 OK with a hallucinated answer is indistinguishable from a 200 OK with a correct answer at the HTTP layer. LLM observability requires capturing the semantic layer, not just the transport layer.

---

## The 8 Required Fields

Every LLM request log MUST include these fields. Missing any one of them creates a blind spot:

| Field | Type | Why It Matters |
|-------|------|---------------|
| model | string | Detect model drift when providers update weights silently |
| prompt_version | string | Bisect prompt regressions to the exact template change |
| input_tokens | int | Track context window usage; alert on unexpectedly long prompts |
| output_tokens | int | Track generation cost; alert on runaway completions |
| cost_usd | float | Budget alerts; per-user cost attribution |
| latency_ms | float | SLA tracking; P95/P99 alerting |
| cache_hit | bool | Measure prompt cache effectiveness |
| error | string/null | Classify failures: auth, rate limit, timeout, context length |

---

## The 4 LLM-Specific Failure Modes

These failure modes are invisible to HTTP-layer monitoring:

**1. Prompt regression** - A template update changes model behavior. Error rate stays 0%. Without prompt_version in logs, you cannot identify which deployment caused it.

**2. Model drift** - The provider silently updates model weights. Output quality shifts. Only semantic quality scores or human review reveals this.

**3. Cascading tool failures** - An agent's tool call chain fails silently. The final HTTP response is 200. Only spans (OTel traces) show the tool call sequence.

**4. Runaway costs** - A prompt template change doubles token count. No generic APM alert fires. Only cost_usd tracking reveals this before the monthly bill arrives.

---

## Traditional APM vs. LLM Observability

```
Traditional APM captures:
  HTTP status, response latency, requests/sec, error rate, CPU/memory

LLM observability additionally needs:
  model name, prompt version, input token count, output token count,
  cost per request, cache hit/miss, tool call chains, output quality scores
```

---

## Diagnostic Questions

When a user says "our LLM monitoring isn't catching problems," ask:

1. Do your logs include prompt_version? Without it, you cannot debug prompt regressions.
2. Do you track cost_usd per request? Without it, cost spikes go unnoticed until billing.
3. Do you log the actual model name (including version)? Without it, provider model updates are invisible.
4. Do you capture errors beyond HTTP status? Rate limits, context length exceeded, and content filters all return non-5xx codes in some configurations.
5. Do you have spans for multi-step (agent/tool) calls? Single log records cannot represent tool call trees.

---

## Minimum Viable Implementation

```python
import json, time
from dataclasses import dataclass, asdict
from typing import Optional
import anthropic

@dataclass
class LLMLogRecord:
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    cache_hit: bool
    error: Optional[str]

def log_llm_call(client, prompt, prompt_version, model="claude-3-5-haiku-20241022"):
    start = time.monotonic()
    error = None
    try:
        resp = client.messages.create(
            model=model, max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        tokens_in = resp.usage.input_tokens
        tokens_out = resp.usage.output_tokens
        cache_hit = (getattr(resp.usage, "cache_read_input_tokens", 0) or 0) > 0
        text = resp.content[0].text
    except anthropic.APIError as exc:
        error = type(exc).__name__
        tokens_in = tokens_out = 0
        cache_hit = False
        text = ""

    record = LLMLogRecord(
        model=model, prompt_version=prompt_version,
        input_tokens=tokens_in, output_tokens=tokens_out,
        cost_usd=round((tokens_in * 0.80 + tokens_out * 4.00) / 1_000_000, 8),
        latency_ms=round((time.monotonic() - start) * 1000, 2),
        cache_hit=cache_hit, error=error
    )
    print(json.dumps(asdict(record)))
    return text, record
```

---

## Next Steps

- Lesson 02: Replace this JSON logger with OpenTelemetry spans using gen_ai.* semantic conventions
- Lesson 03: Route OTel spans to Langfuse (cloud) or Phoenix (local) for trace visualization
- Lesson 04: Use traces to debug production AI failures with a structured 5-step workflow
