"""
Rate Limits, Retries, Backoff, and Circuit Breakers for AI API calls.

Implements:
- exponential backoff with jitter (avoids thundering herd)
- Retry-After header parsing (respects API rate limit signals)
- circuit breaker (stops calling a broken dependency; fast-fails callers)
- ResilientClient wrapping the Anthropic SDK

Usage:
    ANTHROPIC_API_KEY=sk-... python main.py
"""

import os
import random
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import anthropic


# ---------------------------------------------------------------------------
# Exponential backoff with jitter
# ---------------------------------------------------------------------------


def backoff_with_jitter(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.5,
) -> float:
    """
    Compute a retry delay for the given attempt number (0-indexed).

    Formula: min(base * 2^attempt, max_delay) + uniform(0, jitter_factor * delay)

    Without jitter, all retrying service instances wake up at the same moment
    and create a thundering herd. Jitter spreads the wakeup times.

    attempt=0 -> ~1s, attempt=1 -> ~2s, attempt=2 -> ~4s, attempt=3 -> ~8s
    (all +/- up to 50% random jitter)
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter = random.uniform(0, jitter_factor * delay)
    return delay + jitter


def parse_retry_after(headers: dict) -> float | None:
    """
    Parse the Retry-After header from a 429 response.

    Returns the number of seconds to wait, or None if the header is absent.
    When present, this value takes priority over backoff calculations:
    the API is telling you exactly how long to wait.
    """
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitState(Enum):
    CLOSED = "closed"        # normal: calls pass through
    OPEN = "open"            # failing: calls rejected immediately (fast-fail)
    HALF_OPEN = "half_open"  # probing: one call allowed through to test recovery


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit breaker is OPEN."""
    pass


@dataclass
class CircuitBreaker:
    """
    Thread-safe circuit breaker for wrapping external API calls.

    States:
      CLOSED -> OPEN: after `failure_threshold` consecutive failures
      OPEN -> HALF_OPEN: after `recovery_timeout` seconds
      HALF_OPEN -> CLOSED: if the probe call succeeds
      HALF_OPEN -> OPEN: if the probe call fails

    In the OPEN state, calls are rejected immediately without reaching the API.
    This protects the API from a flood of failing requests and protects callers
    from long timeouts while the dependency is broken.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0  # seconds before attempting recovery

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def call(self, fn: Callable[[], Any]) -> Any:
        """
        Execute fn through the circuit breaker.
        Raises CircuitOpenError immediately if the circuit is OPEN.
        """
        with self._lock:
            current_state = self._compute_state()

        if current_state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            remaining = max(0.0, self.recovery_timeout - elapsed)
            raise CircuitOpenError(
                f"Circuit is OPEN (failures={self._failure_count}). "
                f"Recovery probe in {remaining:.1f}s."
            )

        try:
            result = fn()
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    def _compute_state(self) -> CircuitState:
        """Transitions OPEN -> HALF_OPEN if recovery timeout has elapsed."""
        if (
            self._state == CircuitState.OPEN
            and time.time() - self._last_failure_time >= self.recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
        return self._state

    def _record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def _record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if (
                self._state == CircuitState.HALF_OPEN
                or self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._compute_state()

    @property
    def failure_count(self) -> int:
        return self._failure_count


# ---------------------------------------------------------------------------
# ResilientClient
# ---------------------------------------------------------------------------


class ResilientClient:
    """
    Anthropic client with retry logic and circuit breaker.

    Failure handling:
      - 429 RateLimitError: wait for Retry-After header (or backoff), retry
      - 5xx APIStatusError: retry with exponential backoff + jitter
      - Non-retryable 4xx (except 429): raise immediately, no retry
      - After failure_threshold failures: circuit opens, calls fail fast
      - CircuitOpenError: propagated to caller immediately
    """

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        max_attempts: int = 4,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.circuit = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

    def create_message(self, **kwargs) -> anthropic.types.Message:
        """
        Call client.messages.create with retry + circuit breaker.

        All kwargs are forwarded to the Anthropic messages.create call.
        Raises CircuitOpenError if the circuit is open (fast-fail).
        Raises the last error after max_attempts are exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(self.max_attempts):
            try:
                return self.circuit.call(
                    lambda: self.client.messages.create(**kwargs)
                )

            except CircuitOpenError:
                # Fast-fail: do not retry when circuit is open
                raise

            except anthropic.RateLimitError as e:
                # 429: use Retry-After header if present; otherwise use backoff
                retry_after = None
                if hasattr(e, "response") and e.response is not None:
                    retry_after = parse_retry_after(dict(e.response.headers))

                wait = retry_after if retry_after is not None else backoff_with_jitter(
                    attempt, self.base_delay, self.max_delay
                )
                print(
                    f"[attempt {attempt+1}/{self.max_attempts}] Rate limited (429). "
                    f"Waiting {wait:.1f}s "
                    f"({'Retry-After header' if retry_after else 'backoff'})",
                    file=sys.stderr,
                )
                if attempt < self.max_attempts - 1:
                    time.sleep(wait)
                last_error = e

            except anthropic.APIStatusError as e:
                status = getattr(e, "status_code", 0)
                if status in self.RETRYABLE_STATUS_CODES:
                    wait = backoff_with_jitter(attempt, self.base_delay, self.max_delay)
                    print(
                        f"[attempt {attempt+1}/{self.max_attempts}] API error {status}. "
                        f"Retrying in {wait:.1f}s",
                        file=sys.stderr,
                    )
                    if attempt < self.max_attempts - 1:
                        time.sleep(wait)
                    last_error = e
                else:
                    # Non-retryable: 400, 401, 403, 404, etc.
                    raise

            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
                wait = backoff_with_jitter(attempt, self.base_delay, self.max_delay)
                print(
                    f"[attempt {attempt+1}/{self.max_attempts}] Connection error: {e}. "
                    f"Retrying in {wait:.1f}s",
                    file=sys.stderr,
                )
                if attempt < self.max_attempts - 1:
                    time.sleep(wait)
                last_error = e

        raise last_error or RuntimeError(
            f"All {self.max_attempts} retry attempts exhausted"
        )


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Set ANTHROPIC_API_KEY to run the demo", file=sys.stderr)
        sys.exit(1)

    client = ResilientClient(
        api_key=api_key,
        max_attempts=4,
        base_delay=1.0,
        failure_threshold=3,
        recovery_timeout=30.0,
    )

    print(f"Circuit state: {client.circuit.state.value}")

    msg = client.create_message(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        messages=[{"role": "user", "content": "Explain circuit breakers in one sentence."}],
    )
    print(f"Response: {msg.content[0].text}")
    print(f"Circuit state after success: {client.circuit.state.value}")
    print(f"Failures: {client.circuit.failure_count}")


if __name__ == "__main__":
    main()
