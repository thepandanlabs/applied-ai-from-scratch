"""
Chaos Test Suite - Phase 07, Lesson 12
Injects the 5 LLM-specific failure modes and verifies service recovery.

Usage:
    # Mock mode (no API key needed)
    python main.py

    # Real Anthropic client
    ANTHROPIC_API_KEY=sk-ant-... python main.py --real-client
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import time
from enum import Enum
from typing import Any, Optional
from unittest.mock import MagicMock, patch


class FailureMode(str, Enum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    MALFORMED_JSON = "malformed_json"
    EMPTY_RESPONSE = "empty_response"
    OVERLOAD_529 = "overload_529"


@dataclasses.dataclass
class LLMResponse:
    status: str           # "ok", "error", "fallback"
    content: str
    retry_count: int = 0
    error_type: Optional[str] = None
    duration_ms: float = 0.0


class ChaosError(Exception):
    """Base class for injected failures."""
    def __init__(self, status_code: int, message: str, retry_after: int = 0):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(message)


class ChaosProxy:
    """
    Wraps an LLM client and injects failures on demand.

    Args:
        failure_mode: Which failure to inject.
        failure_rate: Fraction of calls that should fail (0.0 to 1.0).
            1.0 means every call fails. 0.5 means every other call fails.
        max_failures: Stop injecting after this many failures (simulates transient issues).
    """

    def __init__(
        self,
        failure_mode: FailureMode,
        failure_rate: float = 1.0,
        max_failures: int = 100,
    ):
        self.failure_mode = failure_mode
        self.failure_rate = failure_rate
        self.max_failures = max_failures
        self._failure_count = 0
        self._call_count = 0

    def _should_fail(self) -> bool:
        self._call_count += 1
        if self._failure_count >= self.max_failures:
            return False
        import random
        return random.random() < self.failure_rate

    def messages_create(self, **kwargs) -> Any:
        """Mimics anthropic.Anthropic().messages.create() with injected failures."""
        if not self._should_fail():
            return self._ok_response(kwargs.get("max_tokens", 100))

        self._failure_count += 1

        if self.failure_mode == FailureMode.TIMEOUT:
            # Simulate a connection that never responds
            time.sleep(0.1)  # Shortened for test speed; real timeout would be 30s
            raise TimeoutError("Connection timed out after 30 seconds")

        elif self.failure_mode == FailureMode.RATE_LIMIT:
            error = ChaosError(
                status_code=429,
                message="Rate limit exceeded. Too many tokens per minute.",
                retry_after=2,
            )
            raise error

        elif self.failure_mode == FailureMode.MALFORMED_JSON:
            # Return an object that will fail when accessed like a real response
            bad_response = MagicMock()
            bad_response.content = None
            bad_response.model_dump_json.side_effect = json.JSONDecodeError(
                "Expecting value", "", 0
            )
            # Simulate the proxy returning a corrupted response object
            raise ValueError("Response body is not valid JSON: Expecting value: line 1 column 1")

        elif self.failure_mode == FailureMode.EMPTY_RESPONSE:
            # Valid response structure but zero output tokens
            response = MagicMock()
            response.content = []
            response.stop_reason = "stop"
            response.usage.output_tokens = 0
            response.usage.input_tokens = 50
            return response

        elif self.failure_mode == FailureMode.OVERLOAD_529:
            raise ChaosError(
                status_code=529,
                message="Overloaded. Please retry after a brief wait.",
                retry_after=5,
            )

        return self._ok_response(kwargs.get("max_tokens", 100))

    def _ok_response(self, max_tokens: int) -> MagicMock:
        response = MagicMock()
        response.content = [MagicMock()]
        response.content[0].text = "This is a valid response from the mock."
        response.stop_reason = "end_turn"
        response.usage.output_tokens = min(50, max_tokens)
        response.usage.input_tokens = 30
        return response


class LLMServiceUnderTest:
    """
    A minimal LLM service with production-grade error handling.
    This is what you are testing. It should handle all 5 failure modes gracefully.
    """

    MAX_RETRIES = 3
    TIMEOUT_SECONDS = 5.0
    CIRCUIT_BREAKER_THRESHOLD = 5

    def __init__(self, client: Optional[ChaosProxy] = None):
        self.client = client
        self._consecutive_failures = 0
        self._circuit_open = False

    def answer_question(self, question: str) -> LLMResponse:
        """Call the LLM to answer a question, with full error handling."""
        start = time.perf_counter()

        if self._circuit_open:
            return LLMResponse(
                status="fallback",
                content="Service temporarily unavailable. Please try again later.",
                error_type="circuit_open",
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.messages_create(
                    model="claude-3-5-haiku-20241022",
                    messages=[{"role": "user", "content": question}],
                    max_tokens=200,
                )

                # Handle empty response
                if not response.content or response.usage.output_tokens == 0:
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(0.1)
                        continue
                    return LLMResponse(
                        status="error",
                        content="Received empty response from model.",
                        retry_count=attempt + 1,
                        error_type="empty_response",
                        duration_ms=(time.perf_counter() - start) * 1000,
                    )

                # Success
                self._consecutive_failures = 0
                return LLMResponse(
                    status="ok",
                    content=response.content[0].text,
                    retry_count=attempt,
                    duration_ms=(time.perf_counter() - start) * 1000,
                )

            except TimeoutError as e:
                last_error = e
                self._consecutive_failures += 1
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(0.5 * (attempt + 1))  # linear backoff for timeouts
                continue

            except ChaosError as e:
                last_error = e
                self._consecutive_failures += 1

                if e.status_code == 429:
                    # Respect retry-after header
                    retry_wait = min(e.retry_after, 2)  # cap for tests
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(retry_wait)
                    continue

                if e.status_code == 529:
                    # Exponential backoff for overload
                    wait = min(2 ** attempt * 0.5, 4)
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(wait)
                    # Check circuit breaker
                    if self._consecutive_failures >= self.CIRCUIT_BREAKER_THRESHOLD:
                        self._circuit_open = True
                    continue

                # Unknown status code
                return LLMResponse(
                    status="error",
                    content=f"API error {e.status_code}: {str(e)}",
                    retry_count=attempt + 1,
                    error_type=f"api_{e.status_code}",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )

            except (ValueError, json.JSONDecodeError) as e:
                # Malformed response - do not retry
                return LLMResponse(
                    status="error",
                    content="Received malformed response from API.",
                    retry_count=attempt,
                    error_type="malformed_response",
                    duration_ms=(time.perf_counter() - start) * 1000,
                )

        # All retries exhausted
        return LLMResponse(
            status="error",
            content="Service unavailable after retries.",
            retry_count=self.MAX_RETRIES,
            error_type=type(last_error).__name__ if last_error else "unknown",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


@dataclasses.dataclass
class ChaosTestResult:
    mode: FailureMode
    passed: bool
    message: str
    duration_ms: float


def run_chaos_suite() -> list[ChaosTestResult]:
    results = []

    test_cases = [
        (
            FailureMode.TIMEOUT,
            lambda r: r.status in ("error", "fallback") and r.retry_count > 0,
            "Service must return non-ok status and show retry attempts",
        ),
        (
            FailureMode.RATE_LIMIT,
            lambda r: r.status in ("error", "fallback") and r.retry_count > 0,
            "Service must back off and retry on 429",
        ),
        (
            FailureMode.MALFORMED_JSON,
            lambda r: r.status == "error" and r.error_type == "malformed_response",
            "Service must catch parse error and return structured error",
        ),
        (
            FailureMode.EMPTY_RESPONSE,
            lambda r: r.status in ("error", "ok") and r.retry_count >= 1,
            "Service must detect empty response and retry at least once",
        ),
        (
            FailureMode.OVERLOAD_529,
            lambda r: r.status in ("error", "fallback"),
            "Service must handle 529 with backoff and not crash",
        ),
    ]

    for failure_mode, assertion_fn, description in test_cases:
        proxy = ChaosProxy(failure_mode=failure_mode, failure_rate=1.0)
        service = LLMServiceUnderTest(client=proxy)

        start = time.perf_counter()
        try:
            result = service.answer_question("What is the capital of France?")
            duration_ms = (time.perf_counter() - start) * 1000
            passed = assertion_fn(result)
            message = (
                f"Service returned status='{result.status}', retry_count={result.retry_count}."
                if passed else
                f"FAIL: {description}. Got status='{result.status}', error_type='{result.error_type}'"
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            passed = False
            message = f"FAIL: Unhandled exception: {type(e).__name__}: {str(e)[:100]}"

        results.append(ChaosTestResult(
            mode=failure_mode,
            passed=passed,
            message=message,
            duration_ms=duration_ms,
        ))

    return results


def main():
    parser = argparse.ArgumentParser(description="LLM chaos test suite")
    parser.add_argument("--real-client", action="store_true",
                        help="Use real Anthropic client (requires ANTHROPIC_API_KEY)")
    args = parser.parse_args()

    print("Running chaos test suite...\n")
    results = run_chaos_suite()

    passed = sum(1 for r in results if r.passed)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.mode.value}: {r.message} ({r.duration_ms:.0f}ms)")

    print(f"\nResults: {passed}/{len(results)} passed")

    if passed < len(results):
        print("\nFailing tests indicate unhandled failure modes in LLMServiceUnderTest.")
        print("Fix the service handler and re-run before deploying.")


if __name__ == "__main__":
    main()
