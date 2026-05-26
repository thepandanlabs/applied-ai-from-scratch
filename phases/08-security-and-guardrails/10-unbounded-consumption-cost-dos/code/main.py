"""
L10: Unbounded Consumption and Cost-DoS
ConsumptionGuard enforces 5 limits: input token limit, output token limit
(max_tokens), per-user rate limit, per-session cost cap, and agent loop
iteration limit. Returns structured errors when limits are hit.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import anthropic

# ---------------------------------------------------------------------------
# Cost constants (claude-3-5-haiku-20241022, per million tokens, May 2026)
# ---------------------------------------------------------------------------

COST_PER_INPUT_TOKEN = 0.80 / 1_000_000   # $0.80 per million input tokens
COST_PER_OUTPUT_TOKEN = 4.00 / 1_000_000  # $4.00 per million output tokens

# ---------------------------------------------------------------------------
# Structured limit-exceeded errors
# ---------------------------------------------------------------------------

@dataclass
class LimitExceeded:
    limit_type: str      # "input_tokens" | "output_tokens" | "rate" | "cost" | "iterations"
    value: float         # the value that exceeded the limit
    limit: float         # the configured limit
    message: str         # user-safe message


@dataclass
class GuardResult:
    allowed: bool
    error: Optional[LimitExceeded] = None


# ---------------------------------------------------------------------------
# ConsumptionGuard
# ---------------------------------------------------------------------------

class ConsumptionGuard:
    """
    Enforces 5 consumption limits before and during LLM calls.

    Limits:
      1. input_token_limit  -- max tokens allowed in a single request input
      2. max_output_tokens  -- passed as max_tokens to the LLM API call
      3. rate_limit_rpm     -- max requests per minute per user_id
      4. session_cost_cap   -- max USD spent per session_id
      5. loop_iteration_limit -- max agent loop iterations per session

    All limits are checked before the LLM call. Cost is tracked after each call.
    """

    def __init__(
        self,
        input_token_limit: int = 4_000,
        max_output_tokens: int = 1_024,
        rate_limit_rpm: int = 10,
        session_cost_cap: float = 1.00,
        loop_iteration_limit: int = 10,
    ):
        self.input_token_limit = input_token_limit
        self.max_output_tokens = max_output_tokens
        self.rate_limit_rpm = rate_limit_rpm
        self.session_cost_cap = session_cost_cap
        self.loop_iteration_limit = loop_iteration_limit

        # Per-user rate tracking: {user_id: [timestamp, ...]}
        self._request_timestamps: dict[str, list[float]] = defaultdict(list)

        # Per-session cost tracking: {session_id: float}
        self._session_costs: dict[str, float] = defaultdict(float)

        # Per-session iteration tracking: {session_id: int}
        self._session_iterations: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------
    # Limit 1: Input token estimation
    # ------------------------------------------------------------------

    def _estimate_input_tokens(self, text: str) -> int:
        """
        Estimate token count without an API call.
        Rule of thumb: 1 token ~ 4 characters for English prose.
        """
        return len(text) // 4

    def check_input_tokens(self, user_input: str) -> GuardResult:
        estimated = self._estimate_input_tokens(user_input)
        if estimated > self.input_token_limit:
            return GuardResult(
                allowed=False,
                error=LimitExceeded(
                    limit_type="input_tokens",
                    value=estimated,
                    limit=self.input_token_limit,
                    message=(
                        f"Your message is too long (estimated {estimated:,} tokens). "
                        f"Please shorten it to under {self.input_token_limit:,} tokens."
                    ),
                ),
            )
        return GuardResult(allowed=True)

    # ------------------------------------------------------------------
    # Limit 2: Output token cap is enforced via max_tokens in the API call
    # (see guarded_completion below -- max_tokens=self.max_output_tokens)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Limit 3: Per-user rate limit
    # ------------------------------------------------------------------

    def check_rate_limit(self, user_id: str) -> GuardResult:
        now = time.time()
        window_start = now - 60.0  # 1-minute sliding window

        # Purge old timestamps
        timestamps = self._request_timestamps[user_id]
        timestamps[:] = [t for t in timestamps if t >= window_start]

        if len(timestamps) >= self.rate_limit_rpm:
            oldest = timestamps[0]
            retry_after = int(60 - (now - oldest)) + 1
            return GuardResult(
                allowed=False,
                error=LimitExceeded(
                    limit_type="rate",
                    value=len(timestamps),
                    limit=self.rate_limit_rpm,
                    message=(
                        f"Rate limit exceeded ({self.rate_limit_rpm} requests/minute). "
                        f"Please wait {retry_after} seconds before retrying."
                    ),
                ),
            )

        # Record this request
        timestamps.append(now)
        return GuardResult(allowed=True)

    # ------------------------------------------------------------------
    # Limit 4: Per-session cost cap
    # ------------------------------------------------------------------

    def check_session_cost(self, session_id: str) -> GuardResult:
        current_cost = self._session_costs[session_id]
        if current_cost >= self.session_cost_cap:
            return GuardResult(
                allowed=False,
                error=LimitExceeded(
                    limit_type="cost",
                    value=round(current_cost, 4),
                    limit=self.session_cost_cap,
                    message=(
                        f"Session cost cap reached (${current_cost:.4f} of "
                        f"${self.session_cost_cap:.2f} limit). "
                        "Please start a new session."
                    ),
                ),
            )
        return GuardResult(allowed=True)

    def record_cost(self, session_id: str, input_tokens: int, output_tokens: int) -> float:
        """Track actual cost after a successful LLM call. Returns cost of this call."""
        call_cost = (
            input_tokens * COST_PER_INPUT_TOKEN +
            output_tokens * COST_PER_OUTPUT_TOKEN
        )
        self._session_costs[session_id] += call_cost
        return call_cost

    def get_session_cost(self, session_id: str) -> float:
        return self._session_costs[session_id]

    # ------------------------------------------------------------------
    # Limit 5: Agent loop iteration limit
    # ------------------------------------------------------------------

    def check_iteration_limit(self, session_id: str) -> GuardResult:
        iterations = self._session_iterations[session_id]
        if iterations >= self.loop_iteration_limit:
            return GuardResult(
                allowed=False,
                error=LimitExceeded(
                    limit_type="iterations",
                    value=iterations,
                    limit=self.loop_iteration_limit,
                    message=(
                        f"Agent loop limit reached ({iterations} iterations). "
                        "The task may be too complex or stuck in a loop. "
                        "Please reformulate your request."
                    ),
                ),
            )
        self._session_iterations[session_id] += 1
        return GuardResult(allowed=True)

    def reset_session(self, session_id: str) -> None:
        """Reset per-session state (cost and iteration count) for a new session."""
        self._session_costs[session_id] = 0.0
        self._session_iterations[session_id] = 0

    # ------------------------------------------------------------------
    # Convenience: run all pre-call checks in order
    # ------------------------------------------------------------------

    def check_all(
        self,
        user_input: str,
        user_id: str,
        session_id: str,
    ) -> GuardResult:
        """
        Run all pre-call checks. Returns the first LimitExceeded found.
        Check order: input tokens -> rate -> cost -> (iteration checked separately)
        """
        for check in [
            self.check_input_tokens(user_input),
            self.check_rate_limit(user_id),
            self.check_session_cost(session_id),
        ]:
            if not check.allowed:
                return check
        return GuardResult(allowed=True)


# ---------------------------------------------------------------------------
# Guarded completion
# ---------------------------------------------------------------------------

def guarded_completion(
    user_input: str,
    user_id: str,
    session_id: str,
    guard: ConsumptionGuard,
    system_prompt: str = "You are a helpful AI assistant.",
    is_agent_loop: bool = False,
) -> dict:
    """
    Run user_input through the ConsumptionGuard before calling the LLM.

    Returns a dict with:
      allowed     -- bool
      error       -- LimitExceeded dict or None
      response    -- LLM response text or None
      cost_usd    -- cost of this call in USD
      session_cost_usd -- cumulative session cost
    """
    # Check iteration limit first if this is inside an agent loop
    if is_agent_loop:
        iter_result = guard.check_iteration_limit(session_id)
        if not iter_result.allowed:
            return _limit_response(iter_result.error)

    # Run all other pre-call checks
    result = guard.check_all(user_input, user_id, session_id)
    if not result.allowed:
        return _limit_response(result.error)

    # All checks passed -- call the LLM with output token cap enforced
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=guard.max_output_tokens,  # Limit 2: hard output cap
        system=system_prompt,
        messages=[{"role": "user", "content": user_input}],
    )

    response_text = message.content[0].text
    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    call_cost = guard.record_cost(session_id, input_tokens, output_tokens)

    return {
        "allowed": True,
        "error": None,
        "response": response_text,
        "cost_usd": round(call_cost, 6),
        "session_cost_usd": round(guard.get_session_cost(session_id), 6),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def _limit_response(error: LimitExceeded) -> dict:
    return {
        "allowed": False,
        "error": {
            "limit_type": error.limit_type,
            "value": error.value,
            "limit": error.limit,
            "message": error.message,
        },
        "response": None,
        "cost_usd": 0.0,
        "session_cost_usd": 0.0,
    }


# ---------------------------------------------------------------------------
# Demo: simulate attacks and legitimate requests
# ---------------------------------------------------------------------------

def run_consumption_demo() -> None:
    guard = ConsumptionGuard(
        input_token_limit=500,
        max_output_tokens=256,
        rate_limit_rpm=3,
        session_cost_cap=0.01,
        loop_iteration_limit=5,
    )

    print("\n" + "=" * 60)
    print("CONSUMPTION GUARD DEMO")
    print("=" * 60)

    # Attack 1: Massive input
    print("\n[Attack 1] Massive input (100k character payload)")
    big_input = "A" * 100_000
    result = guard.check_input_tokens(big_input)
    print(f"  Allowed: {result.allowed}")
    if result.error:
        print(f"  Error: {result.error.message}")

    # Attack 2: Rate limit burst
    print("\n[Attack 2] Rate limit burst (4 requests, limit=3/min)")
    user_id = "attacker-001"
    for i in range(4):
        result = guard.check_rate_limit(user_id)
        status = "OK" if result.allowed else f"BLOCKED: {result.error.message[:60]}"
        print(f"  Request {i+1}: {status}")

    # Attack 3: Cost cap exhaustion
    print("\n[Attack 3] Session cost cap")
    session_id = "session-001"
    # Simulate a $0.009 call
    guard._session_costs[session_id] = 0.0090
    result = guard.check_session_cost(session_id)
    print(f"  Cost so far: ${guard.get_session_cost(session_id):.4f}")
    print(f"  Allowed: {result.allowed}")
    if result.error:
        print(f"  Error: {result.error.message}")

    # Attack 4: Agent loop runaway
    print("\n[Attack 4] Agent loop iteration limit (limit=5)")
    loop_session = "loop-session-001"
    for i in range(7):
        result = guard.check_iteration_limit(loop_session)
        status = "OK" if result.allowed else f"BLOCKED: {result.error.message[:60]}"
        print(f"  Iteration {i+1}: {status}")

    # Legitimate request
    print("\n[Legitimate] Normal short request")
    guard2 = ConsumptionGuard()
    result = guard2.check_all("What is the capital of France?", "user-legit", "session-legit")
    print(f"  Allowed: {result.allowed}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        run_consumption_demo()
    else:
        print("Run with --demo to simulate attacks and legitimate requests.")
        print("Or import ConsumptionGuard and guarded_completion into your FastAPI app.")
