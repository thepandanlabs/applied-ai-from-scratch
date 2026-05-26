---
name: skill-cost-latency-tracker
description: Drop-in CostTracker class and instrumentation pattern for measuring token cost and latency on every Anthropic API call
version: "1.0"
phase: "00"
lesson: "06"
tags: [cost, latency, instrumentation, tokens, ttft]
---

# Cost and Latency Tracker

A drop-in implementation guide for instrumenting token cost and API latency from the first line of any AI application.

---

## What This Gives You

- Per-request cost in USD from the SDK's `response.usage` object
- Wall-clock latency for every call
- Time-to-first-token (TTFT) for streaming requests
- Running totals and monthly projections
- Output/input token ratio flagging (verbose preamble detection)

---

## The Pricing Table

Keep this updated against the Anthropic pricing page before shipping:

```python
PRICING = {
    "input_per_million":       0.80,   # claude-3-5-haiku-20241022
    "output_per_million":      4.00,
    "cache_read_per_million":  0.08,
    "cache_write_per_million": 1.00,
}
```

Output tokens cost 5x more than input tokens. This is structural, not a pricing choice: the model generates output one token at a time (sequential), while input tokens are processed in parallel.

---

## Minimal Drop-In (no class needed)

For scripts and one-off calls, inline the cost calculation directly from the response:

```python
import time
import anthropic

client = anthropic.Anthropic()
start = time.perf_counter()

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": your_prompt}],
)

elapsed = time.perf_counter() - start

# Cost from usage (always use response.usage, not estimates)
input_cost  = response.usage.input_tokens  * 0.80 / 1_000_000
output_cost = response.usage.output_tokens * 4.00 / 1_000_000
total_cost  = input_cost + output_cost

print(f"in={response.usage.input_tokens} out={response.usage.output_tokens} "
      f"cost=${total_cost:.6f} wall={elapsed:.2f}s")
```

---

## CostTracker Class

Copy `code/main.py` from Lesson 06 into your project. Usage:

```python
tracker = CostTracker()

# Non-streaming
response, record = tracker.call(messages=[...])
print(response.content[0].text)    # use response normally
print(record.display())            # see cost + latency for this call

# Streaming (measures TTFT)
full_text, record = tracker.call_streaming(messages=[...], print_output=True)
print(record.ttft_seconds)         # time to first token

# Summary after multiple calls
print(tracker.summary())
```

---

## What to Log in Production

Minimum instrumentation for every AI call:

| Field | Source | Why |
|---|---|---|
| `input_tokens` | `response.usage.input_tokens` | Cost driver |
| `output_tokens` | `response.usage.output_tokens` | Cost driver (5x weight) |
| `cache_read_tokens` | `response.usage.cache_read_input_tokens` | Cache hit rate |
| `wall_clock_ms` | `time.perf_counter()` delta | User-facing latency |
| `ttft_ms` | First token in stream | Chat UX quality |
| `model` | Request parameter | Cost varies by model |
| `request_id` | `response.id` | Debugging + support tickets |

---

## Latency Components and Control

```
Wall-clock = network + queue + TTFT + generation + your processing

You control:         input size, output length, model choice, streaming
You cannot control:  network geography, API queue depth, TTFT variance
```

- Streaming reduces perceived latency without reducing actual latency.
- Smaller models have lower TTFT (haiku vs sonnet vs opus).
- Long outputs take proportionally longer to generate.
- Caching does not reduce latency for cache writes but speeds up cache reads.

---

## Common Patterns and Costs

| Use case | Typical input | Typical output | Cost at 10k req/month |
|---|---|---|---|
| Single-turn Q&A | 500 tokens | 200 tokens | ~$1.20 |
| Document summary | 5,000 tokens | 500 tokens | ~$6.00 |
| Document summary (80% cache) | 5,000 tokens | 500 tokens | ~$2.16 |
| Multi-turn chat (10 turns) | 3,000 tokens | 300 tokens | ~$3.60 |
| Structured extraction | 2,000 tokens | 400 tokens | ~$3.20 |

Verify against current pricing before budgeting.

---

## Red Flags

| Signal | Likely cause | Fix |
|---|---|---|
| Output/input ratio > 0.5 | Verbose model preambles | Add "respond directly, no introduction" |
| TTFT > 2s consistently | Model overload or wrong region | Check status page, try different endpoint |
| Cost jumps 10x after a deploy | Prompt template added long context | Diff the prompt, check token counts |
| output_tokens near max_tokens | Response being truncated | Increase max_tokens or split the task |

---

## Integration with Observability Platforms

The data model from `response.usage` maps directly to Langfuse, Braintrust, and Phoenix:

```python
# Langfuse example (after pip install langfuse)
from langfuse import Langfuse
langfuse = Langfuse()

generation = langfuse.generation(
    name="my-feature",
    model="claude-3-5-haiku-20241022",
    input=messages,
    output=response.content[0].text,
    usage={"input": response.usage.input_tokens,
           "output": response.usage.output_tokens},
)
```

Build your own tracker first (this lesson) so you understand the data. Then swap in a platform when you need dashboards, alerts, and team visibility.
