---
name: skill-robust-tool-design
description: RobustTool base class template with idempotency, timeout, and validation patterns for agent-callable tools
version: "1.0"
phase: "03"
lesson: "05"
tags: [tools, idempotency, timeouts, validation, agents]
---

# Skill: Robust Tool Design

Every tool an agent can retry must satisfy three properties:
idempotency, timeout handling, and input validation.

---

## The RobustTool Template

```python
import hashlib
import json
import concurrent.futures
from abc import ABC, abstractmethod
from typing import Any


class RobustTool(ABC):
    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds
        self._cache: dict[str, Any] = {}

    def idempotency_key(self, args: dict) -> str:
        payload = json.dumps(
            {"tool": self.__class__.__name__, "args": args},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    @abstractmethod
    def validate(self, args: dict) -> list[str]:
        ...

    @abstractmethod
    def _execute(self, args: dict) -> dict:
        ...

    def run(self, args: dict) -> dict:
        errors = self.validate(args)
        if errors:
            return {"ok": False, "error": "validation_failed", "details": errors}

        key = self.idempotency_key(args)
        if key in self._cache:
            return {**self._cache[key], "idempotent_replay": True}

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(self._execute, args)
            try:
                result = future.result(timeout=self.timeout_seconds)
                if result.get("ok"):
                    self._cache[key] = result
                return result
            except concurrent.futures.TimeoutError:
                return {
                    "ok": False,
                    "error": "timeout",
                    "timeout_seconds": self.timeout_seconds,
                    "retry_hint": (
                        "The operation may have completed on the backend. "
                        "Check status before retrying to avoid duplicates."
                    ),
                }
```

---

## Per-Tool Implementation Checklist

For each new tool that subclasses `RobustTool`:

- [ ] **validate():** Check every required field is present and the right type
- [ ] **validate():** Check every value is within acceptable range
- [ ] **validate():** Return clear, actionable error strings (the LLM reads these)
- [ ] **_execute():** Never mutate state before you can return a result
- [ ] **_execute():** Return `{"ok": True, ...}` on success so the cache stores it
- [ ] **_execute():** Return `{"ok": False, "error": "...", ...}` on known failures
- [ ] **timeout_seconds:** Set to P95 latency of the external call, not P50
- [ ] **Idempotency key scope:** Include all args that affect the operation's outcome
- [ ] **Idempotency key scope:** Exclude args that are cosmetic (e.g. `verbose=True`)

---

## Idempotency Pattern

Same args = same key = cache hit = no side effect on retry.

Only cache successful results. A timed-out call leaves no cache entry,
allowing the retry to fire the real call again.

```
Scenario A: network drop after success
  Call 1: charge fires, succeeds, cache stores result
  Call 2: (retry) cache hit, returns stored result, no second charge

Scenario B: timeout before completion
  Call 1: times out, no cache entry written
  Call 2: (retry) cache miss, real call fires again (correct behavior)

Scenario C: backend accepted but response lost
  Call 1: times out, no cache entry written
  Call 2: retry fires real call, backend sees duplicate -> use backend idempotency key
```

For Scenario C: propagate an idempotency key to the external API alongside your
local cache. The backend deduplicates; your cache provides the fast path.

---

## Timeout Decision Guide

| External System | Recommended timeout |
|-----------------|-------------------|
| Internal service (same region) | 2-5s |
| Third-party API (payment, email) | 10-30s |
| LLM inference | 60-120s |
| Batch job / async operation | Do not timeout - use polling |

Set timeout to P95 response time from your observability data, not a round number.
A timeout set below P95 causes retries on healthy calls.

---

## Error Classification for LLM Recovery

Return structured errors the LLM can act on:

```python
# Transient - tell LLM to retry
{"ok": False, "error": "timeout", "retry_hint": "..."}
{"ok": False, "error": "rate_limited", "retry_after_seconds": 30}

# Permanent - tell LLM not to retry
{"ok": False, "error": "validation_failed", "details": [...]}
{"ok": False, "error": "not_found", "resource": "customer_id cust_99"}
{"ok": False, "error": "insufficient_funds", "message": "Card declined"}
```

---

## Composing with Tenacity

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result

class MyToolWithRetry(MyTool):
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_result(lambda r: r.get("error") in {"timeout", "rate_limited"}),
    )
    def run(self, args: dict) -> dict:
        return super().run(args)
```

Tenacity retries on transient errors. The idempotency cache prevents duplicate
side effects when the retry reaches the tool after a prior success.
