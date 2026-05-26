---
name: skill-model-fallback-chain
description: FallbackChain template for AI services - tries primary model, secondary model, cache, and degradation message in order with per-model timeouts
version: "1.0"
phase: "06"
lesson: "08"
tags: [fallback, failover, reliability, multi-provider, degradation]
---

# Skill: Model Fallback Chain

Use this when building an AI service that must remain available even when the primary model provider is unavailable.

## The Four-Tier Pattern

```
Primary (Claude, 10s timeout)
  -> on failure or timeout:
Secondary (GPT-4o-mini, 15s timeout)
  -> on failure or timeout:
Cache (in-memory, 5min TTL)
  -> on cache miss:
Degradation (static message; always succeeds)
```

## Quick Start

```python
from fallback_chain import FallbackChain, ModelConfig

chain = FallbackChain(
    models=[
        ModelConfig(provider="anthropic", model="claude-3-5-haiku-20241022", timeout=10.0),
        ModelConfig(provider="openai", model="gpt-4o-mini", timeout=15.0),
    ],
    degradation_message="AI is temporarily unavailable. Please try again shortly.",
    cache_ttl=300.0,  # 5 minutes
)

result = chain.generate("Your prompt here")
print(result["text"])   # the response
print(result["tier"])   # primary / fallback / cache / degraded
```

## Response Shape

```python
{
    "text": str,             # the response text
    "tier": str,             # "primary" | "fallback" | "cache" | "degraded"
    "model": str,            # model ID or "cache" / "none"
    "latency_seconds": float # 0.0 for cache and degraded tiers
}
```

## Operational Metrics to Track

| Metric | Alert threshold | What it means |
|--------|-----------------|---------------|
| `primary_rate` | < 98% | Primary model unreliable; investigate |
| `fallback_rate` | > 2% | Primary failing frequently |
| `cache_rate` | > 1% | Both models failing; check both providers |
| `degraded_rate` | > 0.1% | All tiers failing; page on-call |

```python
# Log tier on every request
stats = chain.stats
total = sum(stats.values()) or 1
print({k: f"{v/total:.1%}" for k, v in stats.items()})
```

## Timeout Tuning Guide

| Use case | Primary timeout | Secondary timeout |
|----------|----------------|-------------------|
| Chatbot (interactive) | 8-10s | 12-15s |
| Background processing | 30s | 60s |
| Streaming (first token) | 3-5s | 5-8s |
| Batch (offline) | 120s | 180s |

Set timeouts based on what your users will tolerate, not what the API can handle.

## When NOT to Fail Over

| Error | Action |
|-------|--------|
| 400 Bad Request | Fix the request; don't fall back (secondary will also return 400) |
| 401 Unauthorized | Fix the API key; don't fall back (secondary likely has same key issue) |
| 429 Rate Limited | Respect Retry-After; fall back to secondary only if wait is too long |
| 500 Internal Server Error | Fall back to secondary |
| Timeout | Fall back to secondary |
| Network error | Fall back to secondary |
