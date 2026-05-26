"""
Lesson 03-04: Structured Tool Outputs and Error Handling
ToolResult dataclass + safe_execute wrapper for structured LLM-facing error responses.

Run:                        python main.py
Show four error cases:      python main.py --cases
Use Pydantic ToolResult:    python main.py --pydantic
Live LLM recovery demo:     python main.py --llm
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import Any, Optional

import anthropic

# ---------------------------------------------------------------------------
# Custom exception types
# ---------------------------------------------------------------------------

class NotFoundError(Exception):
    """Raised when a requested resource does not exist."""
    pass


class ValidationError(Exception):
    """Raised when the tool input is invalid or malformed."""
    pass


class ServiceTimeoutError(Exception):
    """Raised when an external service call times out."""
    pass


# ---------------------------------------------------------------------------
# ToolResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """
    Structured output contract for all tool calls.
    The LLM reads this as the tool_result content.

    Fields:
        success: Was the call successful?
        data:    The result data (only meaningful when success=True).
        error:   Human-readable error message (only when success=False).
        hint:    What the LLM should try next (only when success=False).
    """
    success: bool
    data:    Any            = None
    error:   Optional[str] = None
    hint:    Optional[str] = None

    def to_json(self) -> str:
        """Serialize to JSON string for use as tool_result content."""
        return json.dumps(asdict(self))

    @classmethod
    def ok(cls, data: Any) -> "ToolResult":
        """Convenience constructor for successful results."""
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, hint: Optional[str] = None) -> "ToolResult":
        """Convenience constructor for failure results."""
        return cls(success=False, error=error, hint=hint)


# ---------------------------------------------------------------------------
# safe_execute wrapper
# ---------------------------------------------------------------------------

def safe_execute(fn: callable, tool_name: str, **kwargs) -> ToolResult:
    """
    Execute a tool function and convert ALL exceptions to structured ToolResult.
    Never lets a raw exception reach the LLM.

    Args:
        fn:        The tool function to call.
        tool_name: Used in error messages so the LLM knows which tool failed.
        **kwargs:  Arguments forwarded to fn.

    Returns:
        ToolResult with success=True and data=result, or success=False with
        error and hint populated based on exception type.
    """
    try:
        result = fn(**kwargs)
        return ToolResult.ok(result)

    except NotFoundError as e:
        return ToolResult.fail(
            error=str(e),
            hint=(
                "The requested resource was not found. "
                "Try listing available resources to find the correct identifier."
            ),
        )

    except ValidationError as e:
        return ToolResult.fail(
            error=str(e),
            hint=(
                "The input is invalid. "
                "Check that all fields match the expected format from the tool description."
            ),
        )

    except ServiceTimeoutError as e:
        return ToolResult.fail(
            error=f"{tool_name} timed out: {e}",
            hint=(
                f"The service is slow right now. "
                f"Retry the call. If timeouts persist, try a simpler variant of {tool_name}."
            ),
        )

    except Exception:
        # Catch-all: log the real exception internally, never expose internals to the LLM.
        # In production: logger.exception(f"Unexpected error in {tool_name}")
        return ToolResult.fail(
            error=f"An unexpected error occurred in {tool_name}.",
            hint=(
                "This is a system error. "
                "Try again in a moment. If it persists, try a different approach."
            ),
        )


# ---------------------------------------------------------------------------
# Stub functions (each demonstrates one error type)
# ---------------------------------------------------------------------------

def get_invoice(invoice_id: str) -> dict:
    """Look up an invoice by ID. Raises typed exceptions for each failure mode."""
    # Validation: wrong format
    if not invoice_id.startswith("INV-"):
        raise ValidationError(
            f"Invalid invoice ID format: {invoice_id!r}. Expected format: INV-NNNN (e.g. INV-8834)."
        )
    # Not found
    if invoice_id == "INV-0000":
        raise NotFoundError(
            f"Invoice {invoice_id!r} not found. "
            "Use list_invoices(customer_id=...) to find valid invoice IDs for this customer."
        )
    # Timeout
    if invoice_id == "INV-SLOW":
        raise ServiceTimeoutError("billing service did not respond within 5 seconds")
    # Unexpected error
    if invoice_id == "INV-BOOM":
        raise RuntimeError("database connection pool exhausted")
    # Success
    return {
        "invoice_id": invoice_id,
        "amount":     142.00,
        "currency":   "USD",
        "status":     "unpaid",
        "due_date":   "2026-06-01",
        "line_items": [
            {"description": "Professional Services", "amount": 120.00},
            {"description": "Expense Reimbursement",  "amount":  22.00},
        ],
    }


def list_invoices(customer_id: str, limit: int = 5) -> dict:
    """List recent invoices for a customer. Used as the recovery path in hints."""
    if not customer_id.startswith("C-"):
        raise ValidationError(f"Invalid customer_id: {customer_id!r}. Expected format: C-NNN.")
    return {
        "customer_id":  customer_id,
        "invoices": [
            {"invoice_id": "INV-8834", "amount": 142.00, "status": "unpaid"},
            {"invoice_id": "INV-8799", "amount":  89.50, "status": "paid"},
            {"invoice_id": "INV-8750", "amount": 210.00, "status": "paid"},
        ][:limit],
    }


# ---------------------------------------------------------------------------
# Demo: four error cases (no API call)
# ---------------------------------------------------------------------------

def demo_four_cases() -> None:
    """Show ToolResult output for each error type."""
    print("\n=== ToolResult: Four Error Cases ===\n")

    cases = [
        {"label": "Success",          "input": {"invoice_id": "INV-8834"}},
        {"label": "Not found",        "input": {"invoice_id": "INV-0000"}},
        {"label": "Validation error", "input": {"invoice_id": "bad-format"}},
        {"label": "Timeout",          "input": {"invoice_id": "INV-SLOW"}},
        {"label": "Unexpected error", "input": {"invoice_id": "INV-BOOM"}},
    ]

    for case in cases:
        result = safe_execute(get_invoice, "get_invoice", **case["input"])
        output = json.loads(result.to_json())
        status = "OK" if result.success else "FAIL"
        print(f"[{status}] {case['label']}")
        print(f"  Input:   {case['input']}")
        if result.success:
            print(f"  Data:    {json.dumps(output['data'])[:80]}...")
        else:
            print(f"  Error:   {output['error']}")
            print(f"  Hint:    {output['hint']}")
        print()


# ---------------------------------------------------------------------------
# Pydantic version
# ---------------------------------------------------------------------------

def demo_pydantic() -> None:
    """Show Pydantic ToolResult with exclude_none serialization."""
    try:
        from pydantic import BaseModel
    except ImportError:
        print("Install pydantic: pip install pydantic")
        return

    class PydanticToolResult(BaseModel):
        success: bool
        data:    Optional[Any] = None
        error:   Optional[str] = None
        hint:    Optional[str] = None

        def to_json(self) -> str:
            return self.model_dump_json(exclude_none=True)

        @classmethod
        def ok(cls, data: Any) -> "PydanticToolResult":
            return cls(success=True, data=data)

        @classmethod
        def fail(cls, error: str, hint: Optional[str] = None) -> "PydanticToolResult":
            return cls(success=False, error=error, hint=hint)

    print("\n=== Pydantic ToolResult: Compact Serialization ===\n")

    success = PydanticToolResult.ok({"invoice_id": "INV-8834", "amount": 142.00})
    failure = PydanticToolResult.fail(
        "Invoice 'INV-0000' not found.",
        "Call list_invoices(customer_id='C-884') to find valid IDs.",
    )

    print(f"Success (exclude_none): {success.to_json()}")
    print(f"Failure (exclude_none): {failure.to_json()}")
    print()
    print("Comparison:")
    print(f"  With None fields:    {json.dumps(asdict(ToolResult.ok({'id': 'INV-8834'})))}")
    print(f"  Without None fields: {success.to_json()}")


# ---------------------------------------------------------------------------
# Live LLM demo: structured vs raw error
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_invoice",
        "description": (
            "Look up an invoice by ID. Returns invoice amount, status, and line items. "
            "Use when the user asks about a specific invoice by ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "invoice_id": {
                    "type": "string",
                    "description": "Invoice ID in format INV-NNNN, e.g. 'INV-8834'.",
                }
            },
            "required": ["invoice_id"],
        },
    },
    {
        "name": "list_invoices",
        "description": (
            "List recent invoices for a customer. "
            "Use when the user doesn't know the invoice ID, or as a fallback after a get_invoice failure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Customer ID in format C-NNN, e.g. 'C-884'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum invoices to return. Default: 5.",
                },
            },
            "required": ["customer_id"],
        },
    },
]

FUNCTION_MAP = {
    "get_invoice":   get_invoice,
    "list_invoices": list_invoices,
}


def run_llm_demo(user_message: str, use_structured_errors: bool = True) -> str:
    """
    Run the full dispatch loop.
    If use_structured_errors=False, passes raw exception strings as tool_result.
    """
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user_message}]
    mode = "structured" if use_structured_errors else "raw"

    print(f"\n[{mode}] {user_message}")

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )

    if response.stop_reason == "end_turn":
        return response.content[0].text

    tool_uses = [b for b in response.content if b.type == "tool_use"]
    messages.append({"role": "assistant", "content": response.content})

    tool_results = []
    for tu in tool_uses:
        fn = FUNCTION_MAP.get(tu.name)
        if use_structured_errors:
            result_obj = safe_execute(fn, tu.name, **tu.input)
            content = result_obj.to_json()
        else:
            # Raw error path: let exceptions become plain strings
            try:
                content = json.dumps(fn(**tu.input))
            except Exception as e:
                content = f"{type(e).__name__}: {e}"

        print(f"  [tool] {tu.name}({tu.input})")
        print(f"  [result] {content[:100]}")
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": tu.id,
            "content": content,
        })

    messages.append({"role": "user", "content": tool_results})

    final = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )

    # If the LLM made another tool call (recovery), handle it
    if final.stop_reason == "tool_use":
        second_tool_uses = [b for b in final.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": final.content})
        second_results = []
        for tu in second_tool_uses:
            fn = FUNCTION_MAP.get(tu.name)
            result_obj = safe_execute(fn, tu.name, **tu.input)
            print(f"  [recovery] {tu.name}({tu.input})")
            second_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result_obj.to_json(),
            })
        messages.append({"role": "user", "content": second_results})
        final = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )

    answer = next((b.text for b in final.content if hasattr(b, "text")), "")
    print(f"  [answer] {answer}")
    return answer


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 03-04: Structured Tool Outputs")
    parser.add_argument("--cases",    action="store_true", help="Show four error cases (no API)")
    parser.add_argument("--pydantic", action="store_true", help="Show Pydantic ToolResult (no API)")
    parser.add_argument("--llm",      action="store_true", help="Live LLM recovery demo (API call)")
    parser.add_argument(
        "--message",
        default="What's the status of invoice INV-0000 for customer C-884?",
        help="User message for LLM demo.",
    )
    args = parser.parse_args()

    if args.cases:
        demo_four_cases()
        return

    if args.pydantic:
        demo_pydantic()
        return

    if args.llm:
        print("=== 03-04: LLM Recovery Demo ===")
        print("\n--- With structured errors (hint guides LLM recovery) ---")
        run_llm_demo(args.message, use_structured_errors=True)
        return

    # Default: show four cases
    print("=== 03-04: Structured Tool Outputs and Error Handling ===")
    demo_four_cases()
    print("To see Pydantic serialization:   python main.py --pydantic")
    print("To run the live LLM demo:        python main.py --llm")


if __name__ == "__main__":
    main()
