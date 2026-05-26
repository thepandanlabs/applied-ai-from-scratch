---
name: skill-chaos-test-suite
description: Chaos test suite covering the 5 LLM-specific failure modes with assertion patterns for each, ready to add to any service test directory
version: "1.0"
phase: "07"
lesson: "12"
tags: [chaos-engineering, resilience, testing, failure-injection, circuit-breaker]
---

# LLM Chaos Test Suite

A `ChaosProxy` that wraps your LLM client and injects the 5 failure modes specific to LLM APIs. Use in CI to verify that fallback code actually works before a production failure triggers it.

## The 5 Failure Modes

| Mode | What it injects | Correct service behavior |
|------|----------------|--------------------------|
| `timeout` | Connection never responds | Raise after timeout, retry with linear backoff, return error |
| `rate_limit` | HTTP 429 with retry-after header | Respect retry-after, max 3 retries, return error if exhausted |
| `malformed_json` | HTTP 200 with unparseable body | Catch parse error, return structured error, do not retry |
| `empty_response` | HTTP 200, zero output tokens | Detect empty, retry once, return error if second attempt empty |
| `overload_529` | HTTP 529 service overloaded | Exponential backoff, open circuit after N consecutive failures |

## Usage

```python
from chaos_proxy import ChaosProxy, FailureMode, LLMServiceUnderTest

# Test a single failure mode
proxy = ChaosProxy(failure_mode=FailureMode.RATE_LIMIT, failure_rate=1.0)
service = YourLLMService(client=proxy)
result = service.your_llm_method("test prompt")

assert result.status in ("error", "fallback")  # must not raise
assert result.retry_count > 0                   # must have retried

# Run the full suite
from chaos_proxy import run_chaos_suite
results = run_chaos_suite()
assert all(r.passed for r in results), "Unhandled failure modes detected"
```

## pytest integration

```python
import pytest
from chaos_proxy import ChaosProxy, FailureMode

@pytest.fixture
def llm_service():
    return YourLLMService()

@pytest.mark.parametrize("mode", list(FailureMode))
@pytest.mark.timeout(10)  # chaos tests must complete within 10s
def test_handles_failure_mode(mode, llm_service):
    proxy = ChaosProxy(failure_mode=mode, failure_rate=1.0)
    llm_service.client = proxy

    result = llm_service.answer_question("test")

    assert result is not None, "Service must not return None"
    assert result.status in ("ok", "error", "fallback"), "Must return structured status"
    assert not result.status == "unhandled_exception", "Must not surface raw exceptions"
```

## CI gate

Add to your pre-deploy check:

```yaml
# .github/workflows/deploy.yml
- name: Run chaos tests
  run: python -m pytest tests/test_chaos.py -v --timeout=30
  # Fail the deploy if any chaos test fails
```

## Adding new failure modes

When a production incident reveals a new failure mode:

1. Add the mode to `FailureMode` enum.
2. Implement the injection in `ChaosProxy.messages_create()`.
3. Add the correct behavior assertion to `run_chaos_suite()`.
4. Add the handler in your `LLMServiceUnderTest` or production service.
5. Verify the test passes before closing the incident.

This converts every production failure into a permanent regression test.
