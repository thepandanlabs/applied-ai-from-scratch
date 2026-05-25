---
name: skill-tool-recovery
description: Production-hardened tool executor with structured error responses, retry logic, and ToolRegistry with @tool decorator
version: "1.0"
phase: "04"
lesson: "08"
tags: [tools, error-recovery, retry, tool-registry, agentic-loop]
---

# Skill: Tool Use and Error Recovery

Use when: any agent calls external APIs or tools that can fail. This is always.

---

## Core executor pattern

Every tool call goes through this wrapper. Never call a tool function directly in the loop.

```python
import time
from typing import Callable

# Your tool registry: map name to callable
TOOL_REGISTRY: dict[str, Callable] = {}


def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """
    Wraps every tool call in try/except.
    Returns {"success": True, "result": ...} or
            {"success": False, "error": ..., "retry_after": N, "suggestion": ...}
    """
    if tool_name not in TOOL_REGISTRY:
        return {
            "success": False,
            "error": f"Tool '{tool_name}' is not registered.",
            "retry_after": None,
            "suggestion": f"Use one of: {list(TOOL_REGISTRY.keys())}"
        }
    try:
        result = TOOL_REGISTRY[tool_name](**tool_input)
        return {"success": True, "result": result}

    except ConnectionError:
        return {
            "success": False,
            "error": f"The {tool_name} tool is temporarily unavailable.",
            "retry_after": 2,
            "suggestion": "Wait 2 seconds and retry, or try a simpler query."
        }
    except ValueError as e:
        return {
            "success": False,
            "error": f"The {tool_name} tool received invalid input: {e}",
            "retry_after": None,
            "suggestion": "Check the input parameters and try again."
        }
    except Exception:
        return {
            "success": False,
            "error": f"The {tool_name} tool encountered an unexpected error.",
            "retry_after": 1,
            "suggestion": "Try once more. If this persists, try a different approach."
        }


def run_tool_with_retry(tool_name: str, tool_input: dict, max_retries: int = 2) -> dict:
    """Execute with automatic retry on retryable errors."""
    for attempt in range(max_retries + 1):
        result = execute_tool(tool_name, tool_input)
        if result["success"]:
            return result
        retry_after = result.get("retry_after")
        if retry_after is None or attempt >= max_retries:
            return result
        time.sleep(retry_after)
    return result
```

---

## Error classification guide

| HTTP status / Exception | Classification | retry_after |
|------------------------|---------------|-------------|
| 429 Too Many Requests | Retryable | Use Retry-After header value |
| 503 Service Unavailable | Retryable | 2-5 seconds |
| 500 Internal Server Error | Retryable (once) | 1 second |
| ConnectionError / Timeout | Retryable | 2 seconds |
| 401 Unauthorized | Terminal | None |
| 403 Forbidden | Terminal | None |
| 400 Bad Request | Terminal | None |
| 404 Not Found | Terminal | None |
| ValueError (bad input) | Terminal | None |

---

## Structured error message templates

What to put in the `error` field that gets sent to the LLM:

```
Rate limit:     "The [tool] tool hit a rate limit (429). It cannot respond right now."
Auth failure:   "The [tool] tool returned 401 Unauthorized. The API credentials may be incorrect or expired."
Not found:      "The [tool] tool found no results for '[input]'. Try a different query."
Bad input:      "The [tool] tool rejected the input: [specific validation message]. Correct the [field] field."
Unknown error:  "The [tool] tool encountered an unexpected error. Try once more or try a different approach."
```

Key principle: the error message must tell the LLM WHAT happened and WHAT to do next. "Tool failed" is not enough.

---

## Wiring into the agentic loop

```python
# In your agentic loop, replace direct tool calls with this pattern:

for block in response.content:
    if block.type != "tool_use":
        continue

    exec_result = run_tool_with_retry(block.name, block.input, max_retries=2)

    if exec_result["success"]:
        tool_result_content = str(exec_result["result"])
    else:
        # Structured error: not a raw exception
        tool_result_content = (
            f"{exec_result['error']} "
            f"Suggestion: {exec_result.get('suggestion', 'Try a different approach.')}"
        )

    tool_results.append({
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": tool_result_content,
    })
```

---

## ToolRegistry with @tool decorator

Use when your tool set is large or evolves frequently.

```python
import functools
import inspect
from typing import Callable


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._definitions: list[dict] = []

    def tool(self, func: Callable) -> Callable:
        """Decorator: registers function and auto-generates tool definition."""
        self._tools[func.__name__] = func
        sig = inspect.signature(func)
        properties = {}
        required = []
        for name, param in sig.parameters.items():
            ann = param.annotation
            param_type = (
                "integer" if ann == int else
                "boolean" if ann == bool else
                "string"
            )
            properties[name] = {"type": param_type, "description": f"The {name} parameter"}
            if param.default == inspect.Parameter.empty:
                required.append(name)
        self._definitions.append({
            "name": func.__name__,
            "description": func.__doc__ or func.__name__,
            "input_schema": {"type": "object", "properties": properties, "required": required}
        })
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper

    def execute_with_retry(self, name: str, input_dict: dict, max_retries: int = 2) -> dict:
        for attempt in range(max_retries + 1):
            if name not in self._tools:
                return {"success": False, "error": f"Unknown tool: {name}", "retry_after": None,
                        "suggestion": f"Available: {list(self._tools.keys())}"}
            try:
                return {"success": True, "result": self._tools[name](**input_dict)}
            except ConnectionError:
                if attempt >= max_retries:
                    return {"success": False, "error": f"{name} unavailable.", "retry_after": 2,
                            "suggestion": "Retry in 2 seconds."}
                time.sleep(2)
            except ValueError as e:
                return {"success": False, "error": f"Invalid input: {e}", "retry_after": None,
                        "suggestion": "Check input parameters."}
            except Exception:
                if attempt >= max_retries:
                    return {"success": False, "error": f"{name} error.", "retry_after": 1,
                            "suggestion": "Try again."}
                time.sleep(1)

    @property
    def definitions(self) -> list[dict]:
        return self._definitions


# Usage
registry = ToolRegistry()

@registry.tool
def my_tool(query: str, limit: int = 10) -> list:
    """Describe what this tool does."""
    # ... implementation
    return []

# Pass to Anthropic API:
# tools=registry.definitions
# Execute: registry.execute_with_retry("my_tool", {"query": "..."})
```

---

## Common pitfalls

- **Passing raw tracebacks to LLM**: The model hallucinates responses when it cannot parse the error. Always structure errors before passing them back.
- **Retrying terminal errors**: A 401 will not fix itself. Classifying auth/validation errors as retryable wastes API calls and delays.
- **Missing retry_after field**: If the executor omits `retry_after`, the loop cannot distinguish retryable from terminal errors. Always set it to `None` for terminal, a number for retryable.
- **Infinite retry loops**: Always enforce `max_retries`. A retryable error that never resolves will run forever without a cap.
- **Silent success on partial failure**: If 3 tool calls happen and 2 succeed but 1 fails silently, the final LLM response may blend real results with hallucinated fill-ins. Log every tool execution result.
