---
name: skill-resilience-patterns
description: Reference card for handling API failures in production - exponential backoff with jitter, Retry-After header parsing, and circuit breaker state machine
version: "1.0"
phase: "06"
lesson: "07"
tags: [resilience, retry, circuit-breaker, rate-limits, backoff]
---

# Skill: Resilience Patterns for AI API Calls

Use this reference when a service makes external API calls that can fail.

## Three Failure Classes and Their Responses

| Class | HTTP signal | Correct response |
|-------|-------------|-----------------|
| Transient error | 500, 502, 503, 504, network timeout | Retry with exponential backoff + jitter |
| Rate limit | 429 + Retry-After header | Wait for Retry-After value, then retry |
| Persistent failure | 5xx for N minutes, 401, 404 | Circuit opens; stop calling; fast-fail |

**Do not retry 4xx errors** (except 429). A 400 or 401 will not succeed on retry -- the client sent a bad request or has invalid credentials.

## Backoff Formula

```python
import random

def backoff_with_jitter(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
    delay = min(base * (2 ** attempt), cap)
    return delay + random.uniform(0, 0.5 * delay)
```

Without jitter: all instances retry at the same moment (thundering herd).
With jitter: retries spread across time, reducing peak load on the API.

## Retry-After Header

When a 429 response includes `Retry-After: N`, wait exactly N seconds.
The API is telling you precisely when it will accept requests again.

```python
def parse_retry_after(headers: dict) -> float | None:
    value = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return float(value) if value else None
    except (ValueError, TypeError):
        return None
```

## Circuit Breaker States

```
CLOSED --[N consecutive failures]--> OPEN
OPEN   --[timeout elapsed]---------> HALF_OPEN
HALF_OPEN --[probe succeeds]-------> CLOSED
HALF_OPEN --[probe fails]----------> OPEN
```

In OPEN state: reject calls immediately (microseconds) instead of waiting for timeouts (seconds). Your service stays responsive while the dependency is broken.

## tenacity (for retry logic)

```python
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
import anthropic

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential_jitter(initial=1, max=60, jitter=5),
    retry=retry_if_exception_type((
        anthropic.RateLimitError,
        anthropic.APIStatusError,
        anthropic.APIConnectionError,
    )),
)
def call_api(prompt: str) -> str:
    ...
```

Combine tenacity (retry) with a circuit breaker (fast-fail) for full resilience coverage.

## What NOT to Do

| Anti-pattern | Problem |
|-------------|---------|
| Retry with fixed delay (no jitter) | Thundering herd: all instances hit the API simultaneously |
| Retry indefinitely | Starves threads; downstream users time out while waiting |
| Retry 4xx errors (except 429) | 400/401 will not succeed on retry; wastes quota |
| No circuit breaker | Service stays slow for all users while API is broken |
| Ignore Retry-After header | Violates API contract; may result in ban |
