---
name: skill-prompt-cache
description: Reference card for Anthropic prompt caching - breakpoint placement, token minimums, cost model, and when caching helps versus when it has no effect.
version: "1.0"
phase: "01"
lesson: "13"
tags: [caching, cost, latency, prompt-engineering, anthropic]
---

# Prompt Caching Reference Card

## The Core Rule

Caching is opt-in. No `cache_control` breakpoint means no caching. Every token charges full input price on every call until you add explicit breakpoints.

---

## Token Minimums

| Model family | Min tokens to cache |
|---|---|
| Claude 3 Haiku | 2048 tokens |
| Claude 3 Sonnet, Opus | 1024 tokens |
| Claude 3.5 Haiku | 2048 tokens |
| Claude 3.5 Sonnet | 1024 tokens |

Prompts shorter than the minimum are never cached, even with `cache_control` set.

---

## Cache TTL

Cache entries expire after **5 minutes of non-use**. If no request reads a cache entry within 5 minutes, it is evicted. The next request triggers a new cache write.

---

## Cost Model

| Token type | Approximate price multiplier vs standard input |
|---|---|
| Standard input (uncached) | 1x (baseline) |
| Cache write | ~1.25x (slightly more expensive) |
| Cache read | ~0.1x (90% discount) |
| Output tokens | Same as standard, not affected by caching |

Source: Approximate rates. Always check current pricing at https://www.anthropic.com/pricing.

---

## Breakpoint Placement Rules

1. Place `cache_control` at the END of the content you want to cache (not the beginning).
2. Everything BEFORE the breakpoint is cached as a prefix.
3. Content AFTER the breakpoint is not cached; it is processed fresh each call.
4. Put STABLE content before the breakpoint, DYNAMIC content after it.

### System prompt caching (string -> list of blocks)

```python
# Without caching (string form)
system="Your long system prompt here..."

# With caching (must use list of content blocks)
system=[
    {
        "type": "text",
        "text": "Your long system prompt here...",
        "cache_control": {"type": "ephemeral"}
    }
]
```

### Document context caching (two breakpoints)

```python
messages=[
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": f"Reference document:\n\n{large_document}",
                "cache_control": {"type": "ephemeral"}  # Cache the document
            },
            {
                "type": "text",
                "text": f"Question: {user_question}"
                # No cache_control: question changes every call
            }
        ]
    }
]
```

---

## Verifying Cache Hits

Check `usage` in the API response:

```python
response = client.messages.create(...)
usage = response.usage

# These fields tell you what happened
cache_read = getattr(usage, "cache_read_input_tokens", 0)
cache_write = getattr(usage, "cache_creation_input_tokens", 0)

if cache_read > 0:
    status = "HIT"      # Cache read - discounted price
elif cache_write > 0:
    status = "WRITE"    # Cache created - slightly elevated price
else:
    status = "MISS"     # No caching occurred (check token minimum)
```

---

## When Caching Helps

| Use case | Cache benefit |
|---|---|
| Long system prompt (>2k tokens) + high request volume | High: 80-90% cost reduction on system tokens |
| Large reference document queried multiple times | High: document processed once per 5 min window |
| Few-shot prompts with 10+ examples | Medium: reduces per-call cost for repeated examples |
| Single one-off request | None: cache write cost not amortized |
| Low-volume endpoint (<10 req/5 min) | None or negative: cache expires before reads amortize write cost |
| Short system prompt (<1024 tokens) | None: below minimum threshold |

---

## Breakeven Calculation

Caching saves money when:

```
savings_per_hit > cache_write_premium_per_miss

Simplified: cache_hit_rate > ~15% for typical usage patterns
```

Rule of thumb: if you make more than 5 requests using the same prefix within a 5-minute window, caching is net positive.

---

## Common Mistakes

**Mistake 1: Changing content before the breakpoint.**
Any change to content before `cache_control` invalidates the entire cache entry. User-specific data, timestamps, or session IDs placed before the breakpoint guarantee cache misses.

**Mistake 2: Setting breakpoint but not meeting token minimum.**
If the prefix is 800 tokens and the model requires 1024, `cache_control` is silently ignored. Verify token counts.

**Mistake 3: Assuming caching is always beneficial.**
At low request volumes, you pay for cache writes but rarely get cache reads. Profile your actual request rate before adding breakpoints.

**Mistake 4: Not verifying cache hits in staging.**
Log `cache_read_input_tokens` in staging. If it is always 0, something is wrong: prefix too short, content changing, or TTL expiring between calls.
