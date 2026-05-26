---
name: skill-tool-output-contract
description: ToolResult schema and safe_execute wrapper for structured, LLM-readable tool outputs and error handling
version: "1.0"
phase: "03"
lesson: "04"
tags: [tools, error-handling, structured-output, safe-execute, tool-result]
---

# Tool Output Contract Template

Drop this into any tool dispatch layer that needs structured, LLM-readable outputs for both success and failure cases. Includes the `ToolResult` dataclass, four exception types, and the `safe_execute` wrapper with error classification.

## ToolResult Schema

```python
from dataclasses import dataclass, asdict
from typing import Any, Optional
import json


@dataclass
class ToolResult:
    """
    Structured output contract for all tool calls.
    The LLM reads this as the tool_result content.
    """
    success: bool
    data:    Any            = None   # populated on success
    error:   Optional[str] = None   # human-readable error (on failure)
    hint:    Optional[str] = None   # what the LLM should try next (on failure)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def ok(cls, data: Any) -> "ToolResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, hint: Optional[str] = None) -> "ToolResult":
        return cls(success=False, error=error, hint=hint)
```

## Exception Types

```python
class NotFoundError(Exception):
    """Raised when a requested resource does not exist."""
    pass

class ValidationError(Exception):
    """Raised when the tool input is invalid or malformed."""
    pass

class ServiceTimeoutError(Exception):
    """Raised when an external service call times out."""
    pass
```

## safe_execute Wrapper

```python
def safe_execute(fn: callable, tool_name: str, **kwargs) -> ToolResult:
    """
    Execute a tool function and convert ALL exceptions to structured ToolResult.
    Never lets a raw exception reach the LLM.

    Usage:
        result = safe_execute(get_invoice, "get_invoice", invoice_id="INV-8834")
        # Pass result.to_json() as the tool_result content.
    """
    try:
        result = fn(**kwargs)
        return ToolResult.ok(result)

    except NotFoundError as e:
        return ToolResult.fail(
            error=str(e),
            hint="The resource was not found. Try listing available resources to find the correct identifier.",
        )

    except ValidationError as e:
        return ToolResult.fail(
            error=str(e),
            hint="The input is invalid. Check that all fields match the expected format from the tool schema.",
        )

    except ServiceTimeoutError as e:
        return ToolResult.fail(
            error=f"{tool_name} timed out: {e}",
            hint=f"Retry the call. If timeouts persist, try a simpler or scoped version of {tool_name}.",
        )

    except Exception:
        # IMPORTANT: log the real exception here, never expose internals to the LLM
        # logger.exception(f"Unexpected error in {tool_name}")
        return ToolResult.fail(
            error=f"An unexpected error occurred in {tool_name}.",
            hint="Try again. If the error persists, try a different approach.",
        )
```

## Dispatch Integration

```python
def dispatch_tool_call(tool_name: str, tool_input: dict, function_map: dict) -> str:
    """
    Look up and safely execute a tool. Returns JSON string as tool_result content.
    """
    fn = function_map.get(tool_name)
    if fn is None:
        return ToolResult.fail(
            error=f"Unknown tool: {tool_name!r}",
            hint="Check that the tool name matches one of the registered tools.",
        ).to_json()

    result = safe_execute(fn, tool_name, **tool_input)
    return result.to_json()
```

## Pydantic Version (for type-safe serialization)

```python
from pydantic import BaseModel

class ToolResult(BaseModel):
    success: bool
    data:    Optional[Any] = None
    error:   Optional[str] = None
    hint:    Optional[str] = None

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=True)

    @classmethod
    def ok(cls, data: Any) -> "ToolResult":
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str, hint: Optional[str] = None) -> "ToolResult":
        return cls(success=False, error=error, hint=hint)
```

## Output Examples

```json
// Success
{"success": true, "data": {"invoice_id": "INV-8834", "amount": 142.0, "status": "unpaid"}}

// Not found
{"success": false, "data": null, "error": "Invoice 'INV-0000' not found. Use list_invoices(customer_id=...) to find valid IDs.", "hint": "The resource was not found. Try listing available resources to find the correct identifier."}

// Validation error
{"success": false, "data": null, "error": "Invalid invoice ID format: 'bad-format'. Expected: INV-NNNN.", "hint": "The input is invalid. Check that all fields match the expected format from the tool schema."}

// Timeout
{"success": false, "data": null, "error": "get_invoice timed out: billing service did not respond within 5s", "hint": "Retry the call. If timeouts persist, try a simpler or scoped version of get_invoice."}
```

## Writing Effective Hints

The hint field is what turns a dead end into a recoverable failure. Hints must be:

1. Actionable: name the next tool call or next step explicitly.
   - Bad:  "Try again later."
   - Good: "Call list_invoices(customer_id='C-884') to find the correct invoice ID."

2. Specific: reference the tool by name and include example arguments when known.
   - Bad:  "The resource was not found."
   - Good: "Invoice 'INV-0000' not found. Use list_invoices(customer_id=...) to find valid invoice IDs for this customer."

3. Honest: don't promise a tool will succeed. Use "try" language for recovery hints.
   - Bad:  "Use search_products() to find the item."
   - Good: "Try search_products(query='..., category='footwear') to find similar items."

## Key Rules

1. Every tool function must only raise the three typed exceptions (NotFoundError, ValidationError, ServiceTimeoutError) or let safe_execute catch the rest.
2. Never let a raw Python exception or traceback reach the LLM as tool_result content.
3. The hint field is required for failure cases. A hint of None is only acceptable when there is truly no recovery path (rare).
4. Do not include internal implementation details in error or hint messages (file paths, database column names, internal service names).
5. Log the full exception internally (for debugging) before returning the structured error to the LLM.
