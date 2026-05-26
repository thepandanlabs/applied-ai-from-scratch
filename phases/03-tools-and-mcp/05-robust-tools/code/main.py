"""
L05: Robust Tools - Idempotency, Timeouts, Validation
appliedaifromscratch.com | Phase 03

Demonstrates a RobustTool base class that makes agent-callable tools safe to retry.
Three properties: idempotency (cache on call signature), timeouts (hard deadline),
and validation (pre-call check with structured errors back to the LLM).

Run:
    uv run main.py
    # or: python main.py
"""

import hashlib
import json
import time
import random
import concurrent.futures
from abc import ABC, abstractmethod
from typing import Any

import anthropic


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class RobustTool(ABC):
    """
    Base class for tools that agents can call (and retry) safely.

    Subclasses implement:
        validate(args) -> list[str]   - return error strings if args are invalid
        _execute(args) -> dict        - the actual external call

    The run() method orchestrates: validate -> idempotency check -> timed call.
    """

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds
        self._cache: dict[str, Any] = {}
        self._execute_count = 0  # for testing: counts real calls

    # --- Idempotency ---------------------------------------------------------

    def idempotency_key(self, args: dict) -> str:
        """Hash tool class name + sorted args into a 16-char hex key."""
        payload = json.dumps(
            {"tool": self.__class__.__name__, "args": args},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # --- Validation ----------------------------------------------------------

    @abstractmethod
    def validate(self, args: dict) -> list[str]:
        """Return a list of validation error strings. Empty list = valid."""
        ...

    # --- Implementation ------------------------------------------------------

    @abstractmethod
    def _execute(self, args: dict) -> dict:
        """The real external call. Must return a dict."""
        ...

    # --- Orchestrator --------------------------------------------------------

    def run(self, args: dict) -> dict:
        """
        Run the tool with full production safety.

        Returns a dict. Structure:
            Success:  {"ok": True, ...tool-specific fields...}
            Replay:   {"ok": True, ..., "idempotent_replay": True}
            Timeout:  {"ok": False, "error": "timeout", "retry_hint": "..."}
            Validate: {"ok": False, "error": "validation_failed", "details": [...]}
        """
        # 1. Validate first - cheap, never touches external system
        errors = self.validate(args)
        if errors:
            return {
                "ok": False,
                "error": "validation_failed",
                "details": errors,
            }

        # 2. Check idempotency cache
        key = self.idempotency_key(args)
        if key in self._cache:
            return {**self._cache[key], "idempotent_replay": True}

        # 3. Call with timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(self._execute, args)
            try:
                result = future.result(timeout=self.timeout_seconds)
                # Only cache successes
                if result.get("ok"):
                    self._cache[key] = result
                return result
            except concurrent.futures.TimeoutError:
                return {
                    "ok": False,
                    "error": "timeout",
                    "timeout_seconds": self.timeout_seconds,
                    "retry_hint": (
                        "The external system did not respond within the deadline. "
                        "The operation may have completed on the backend before the "
                        "timeout fired. Check the resource status before retrying "
                        "to avoid duplicate side effects."
                    ),
                }


# ---------------------------------------------------------------------------
# Concrete tool: ChargeCustomer
# ---------------------------------------------------------------------------

class ChargeCustomer(RobustTool):
    """
    Charge a customer a fixed amount.

    Demonstrates all three RobustTool properties:
    - Validation: customer_id, amount_cents (int > 0), currency required
    - Idempotency: same customer + amount + currency = same result, no double charge
    - Timeout: configurable deadline; payment APIs can be slow
    """

    SUPPORTED_CURRENCIES = {"usd", "eur", "gbp", "cad", "aud"}

    def validate(self, args: dict) -> list[str]:
        errors = []

        if "customer_id" not in args or not args["customer_id"]:
            errors.append("customer_id is required and must be a non-empty string")

        if "amount_cents" not in args:
            errors.append("amount_cents is required")
        elif not isinstance(args["amount_cents"], int):
            errors.append(
                f"amount_cents must be an integer (e.g. 1999 for $19.99), "
                f"got {type(args['amount_cents']).__name__}"
            )
        elif args["amount_cents"] <= 0:
            errors.append("amount_cents must be a positive integer")
        elif args["amount_cents"] > 99999999:
            errors.append("amount_cents exceeds maximum allowed ($999,999.99)")

        if "currency" not in args:
            errors.append(
                f"currency is required (one of: {', '.join(sorted(self.SUPPORTED_CURRENCIES))})"
            )
        elif args.get("currency", "").lower() not in self.SUPPORTED_CURRENCIES:
            errors.append(
                f"currency '{args['currency']}' is not supported. "
                f"Use one of: {', '.join(sorted(self.SUPPORTED_CURRENCIES))}"
            )

        return errors

    def _execute(self, args: dict) -> dict:
        """Simulate a payment API call (100-500ms latency)."""
        self._execute_count += 1
        time.sleep(random.uniform(0.1, 0.5))
        charge_id = f"ch_{args['customer_id']}_{args['amount_cents']}_{args['currency']}"
        return {
            "ok": True,
            "charge_id": charge_id,
            "customer_id": args["customer_id"],
            "amount_cents": args["amount_cents"],
            "currency": args["currency"].lower(),
            "status": "succeeded",
        }


# ---------------------------------------------------------------------------
# Tenacity composition
# ---------------------------------------------------------------------------

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_result,
    )

    class ChargeCustomerWithRetry(ChargeCustomer):
        """
        ChargeCustomer with automatic retry on transient timeout errors.

        Tenacity handles WHEN to retry.
        The idempotency cache handles WHAT HAPPENS when the retry reaches the tool:
        if the first attempt succeeded and was cached, the retry returns the cache
        immediately without firing a second charge.
        """

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_result(lambda r: r.get("error") == "timeout"),
            reraise=False,
        )
        def run(self, args: dict) -> dict:
            return super().run(args)

    HAS_TENACITY = True

except ImportError:
    HAS_TENACITY = False
    ChargeCustomerWithRetry = None  # type: ignore


# ---------------------------------------------------------------------------
# Demo: also shows how to wire tools into the Anthropic agent loop
# ---------------------------------------------------------------------------

def build_anthropic_tool_schema() -> dict:
    """Return the Anthropic tool schema for ChargeCustomer."""
    return {
        "name": "charge_customer",
        "description": (
            "Charge a customer a specific amount in the given currency. "
            "This tool is idempotent: calling it with the same arguments "
            "more than once will not result in duplicate charges."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "The unique customer identifier (e.g. 'cust_42')",
                },
                "amount_cents": {
                    "type": "integer",
                    "description": "Amount to charge in cents (e.g. 1999 for $19.99)",
                },
                "currency": {
                    "type": "string",
                    "description": "ISO currency code (usd, eur, gbp, cad, aud)",
                },
            },
            "required": ["customer_id", "amount_cents", "currency"],
        },
    }


def run_direct_demo():
    """Demonstrate all three RobustTool properties without the agent loop."""
    print("=" * 60)
    print("RobustTool Direct Demo")
    print("=" * 60)

    tool = ChargeCustomer(timeout_seconds=5.0)

    # --- Validation ---
    print("\n[1] Validation - bad args")
    result = tool.run({"customer_id": "cust_42", "amount_cents": "twenty dollars"})
    print(f"    Result: {json.dumps(result, indent=4)}")
    assert result["error"] == "validation_failed"

    # --- First real call ---
    print("\n[2] First call - real execution")
    args = {"customer_id": "cust_42", "amount_cents": 1999, "currency": "usd"}
    result = tool.run(args)
    print(f"    Result: {json.dumps(result, indent=4)}")
    print(f"    _execute called {tool._execute_count} time(s)")
    assert result["ok"] is True
    assert tool._execute_count == 1

    # --- Idempotent replay ---
    print("\n[3] Retry with same args - idempotent replay")
    result = tool.run(args)
    print(f"    Result: {json.dumps(result, indent=4)}")
    print(f"    _execute called {tool._execute_count} time(s) (should still be 1)")
    assert result.get("idempotent_replay") is True
    assert tool._execute_count == 1  # no second charge fired

    # --- Different customer - new call ---
    print("\n[4] Different customer - new real call")
    result = tool.run({"customer_id": "cust_99", "amount_cents": 500, "currency": "eur"})
    print(f"    Result: {json.dumps(result, indent=4)}")
    print(f"    _execute called {tool._execute_count} time(s) (should be 2)")
    assert tool._execute_count == 2

    print("\nAll direct assertions passed.\n")


def run_agent_demo():
    """Wire ChargeCustomer into the Anthropic agent loop."""
    print("=" * 60)
    print("Agent Loop Demo")
    print("=" * 60)

    client = anthropic.Anthropic()
    tool = ChargeCustomer(timeout_seconds=5.0)
    tool_schema = build_anthropic_tool_schema()

    messages = [
        {
            "role": "user",
            "content": (
                "Please charge customer cust_101 for $29.99 USD. "
                "If it fails, try once more."
            ),
        }
    ]

    print("\nStarting agent loop...\n")

    for turn in range(5):  # safety limit
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            tools=[tool_schema],
            messages=messages,
        )

        print(f"Turn {turn + 1} | stop_reason: {response.stop_reason}")

        if response.stop_reason == "end_turn":
            # Extract final text
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\nFinal response:\n{block.text}")
            break

        if response.stop_reason == "tool_use":
            # Add assistant message
            messages.append({"role": "assistant", "content": response.content})

            # Process each tool call
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  Tool call: {block.name}({json.dumps(block.input)})")
                    result = tool.run(block.input)
                    print(f"  Tool result: {json.dumps(result)}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

            messages.append({"role": "user", "content": tool_results})

    print(f"\n_execute was called {tool._execute_count} real time(s) across all turns.")


def run_tenacity_demo():
    if not HAS_TENACITY:
        print("\n[Tenacity demo skipped - install tenacity: pip install tenacity]\n")
        return

    print("=" * 60)
    print("Tenacity + Idempotency Composition Demo")
    print("=" * 60)

    tool = ChargeCustomerWithRetry(timeout_seconds=0.05)  # very short to force timeout

    print("\nCalling with 50ms timeout (designed to timeout then succeed on retry)...")
    # Note: with a 50ms timeout, the simulated 100-500ms sleep will always timeout.
    # On retry, the idempotency cache is empty (timeout means no cache entry),
    # so the real call fires again. This shows correct behavior:
    # cache only populated on success, not on timeout.
    result = tool.run({"customer_id": "cust_demo", "amount_cents": 100, "currency": "usd"})
    print(f"Result: {json.dumps(result, indent=4)}")
    print(f"_execute called {tool._execute_count} times (expected: up to 3 retries)")

    # Now with a reasonable timeout - should succeed and cache
    tool2 = ChargeCustomerWithRetry(timeout_seconds=5.0)
    print("\nCalling with 5s timeout - should succeed and cache...")
    r1 = tool2.run({"customer_id": "cust_demo", "amount_cents": 100, "currency": "usd"})
    r2 = tool2.run({"customer_id": "cust_demo", "amount_cents": 100, "currency": "usd"})
    print(f"First call: ok={r1['ok']}, replay={r1.get('idempotent_replay', False)}")
    print(f"Second call: ok={r2['ok']}, replay={r2.get('idempotent_replay', False)}")
    assert r2.get("idempotent_replay") is True
    assert tool2._execute_count == 1
    print("Idempotency confirmed: _execute called exactly once.")


if __name__ == "__main__":
    run_direct_demo()
    run_tenacity_demo()

    print("\n" + "=" * 60)
    print("Running agent loop (requires ANTHROPIC_API_KEY)...")
    print("=" * 60)
    try:
        run_agent_demo()
    except Exception as e:
        print(f"Agent loop error: {e}")
        print("Set ANTHROPIC_API_KEY to run the full agent demo.")
