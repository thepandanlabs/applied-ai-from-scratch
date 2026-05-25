"""
Lesson 04-08: Tool Use and Error Recovery in the Loop
Production-hardened tool executor with structured errors and retry logic.
"""

import functools
import inspect
import random
import time
from typing import Any, Callable

import anthropic

# ---------------------------------------------------------------------------
# DELIBERATELY FLAKY TOOLS (for demonstration)
# ---------------------------------------------------------------------------

def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web for current information on a topic.
    Deliberately fails 50% of the time to demonstrate error recovery.
    """
    if random.random() < 0.5:
        raise ConnectionError("Rate limited: too many requests to search API")

    return [
        {
            "title": f"Result {i} for '{query}'",
            "url": f"https://example.com/result-{i}",
            "snippet": f"Relevant content about {query} from source {i}."
        }
        for i in range(1, max_results + 1)
    ]


def get_weather(city: str) -> dict:
    """Get current weather conditions for a city."""
    return {
        "city": city,
        "temperature": 22,
        "conditions": "Partly cloudy",
        "humidity": 65,
    }


def calculate_sum(numbers: str) -> dict:
    """
    Calculate the sum of a comma-separated list of numbers.
    Raises ValueError on bad input to demonstrate terminal error handling.
    """
    try:
        nums = [float(n.strip()) for n in numbers.split(",")]
        return {"sum": sum(nums), "count": len(nums)}
    except ValueError:
        raise ValueError(f"Invalid number list: '{numbers}'. Expected comma-separated numbers.")


# ---------------------------------------------------------------------------
# TOOL REGISTRY
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Callable] = {
    "search_web": search_web,
    "get_weather": get_weather,
    "calculate_sum": calculate_sum,
}

# Tool definitions for the Anthropic API
TOOL_DEFINITIONS = [
    {
        "name": "search_web",
        "description": "Search the web for current information on a topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "max_results": {"type": "integer", "description": "Number of results (default 5)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_weather",
        "description": "Get current weather conditions for a city.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "calculate_sum",
        "description": "Calculate the sum of a comma-separated list of numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "numbers": {"type": "string", "description": "Comma-separated numbers, e.g. '1,2,3'"}
            },
            "required": ["numbers"]
        }
    }
]


# ---------------------------------------------------------------------------
# TOOL EXECUTOR WITH STRUCTURED ERROR RESPONSE
# ---------------------------------------------------------------------------

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
            "suggestion": f"Use one of the available tools: {list(TOOL_REGISTRY.keys())}"
        }

    try:
        result = TOOL_REGISTRY[tool_name](**tool_input)
        return {"success": True, "result": result}

    except ConnectionError:
        # Rate limit or transient network: retryable
        return {
            "success": False,
            "error": f"The {tool_name} tool is temporarily unavailable (connection error). It may be rate limited.",
            "retry_after": 2,
            "suggestion": "Wait 2 seconds and retry the same request, or try a simpler query."
        }

    except ValueError as e:
        # Bad input: terminal, not retryable
        return {
            "success": False,
            "error": f"The {tool_name} tool received invalid input: {str(e)}",
            "retry_after": None,
            "suggestion": "Check the input parameters and try again with corrected values."
        }

    except Exception:
        # Unknown: treat as retryable once
        return {
            "success": False,
            "error": f"The {tool_name} tool encountered an unexpected error.",
            "retry_after": 1,
            "suggestion": "Try once more. If this persists, try a different approach."
        }


def run_tool_with_retry(tool_name: str, tool_input: dict, max_retries: int = 2) -> dict:
    """
    Execute a tool with automatic retry on retryable errors.
    Returns the first success or the last error after max_retries.
    """
    for attempt in range(max_retries + 1):
        result = execute_tool(tool_name, tool_input)

        if result["success"]:
            return result

        retry_after = result.get("retry_after")

        if retry_after is None:
            # Terminal error: surface immediately
            print(f"  Terminal error on {tool_name}: {result['error']}")
            return result

        if attempt < max_retries:
            print(
                f"  Retryable error on {tool_name} "
                f"(attempt {attempt + 1}/{max_retries + 1}). "
                f"Waiting {retry_after}s..."
            )
            time.sleep(retry_after)
        else:
            print(f"  Max retries reached for {tool_name}. Returning error to LLM.")

    return result


# ---------------------------------------------------------------------------
# FULL AGENTIC LOOP
# ---------------------------------------------------------------------------

def run_agent(user_message: str, max_turns: int = 10) -> str:
    """
    Full agentic loop with production-hardened tool execution.
    Handles retries internally; sends structured errors to LLM on terminal failure.
    """
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user_message}]

    print(f"\nUser: {user_message}")

    for turn in range(max_turns):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "Agent completed with no text response."

        if response.stop_reason != "tool_use":
            break

        # Process all tool calls in this turn
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            print(f"\nAgent calling: {block.name}({block.input})")

            exec_result = run_tool_with_retry(block.name, block.input, max_retries=2)

            if exec_result["success"]:
                tool_result_content = str(exec_result["result"])
                print(f"  Success: {tool_result_content[:100]}...")
            else:
                # Structured, actionable error message to LLM
                tool_result_content = (
                    f"{exec_result['error']} "
                    f"Suggestion: {exec_result.get('suggestion', 'Try a different approach.')}"
                )
                print(f"  Error to LLM: {tool_result_content[:120]}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": tool_result_content,
            })

        messages.append({"role": "user", "content": tool_results})

    return "Agent reached max turns without completing."


# ---------------------------------------------------------------------------
# REFACTORED: ToolRegistry class with @tool decorator
# ---------------------------------------------------------------------------

class ToolRegistry:
    """
    Registry that stores tool functions and generates Anthropic tool definitions
    from type hints and docstrings.
    """

    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._definitions: list[dict] = []

    def tool(self, func: Callable) -> Callable:
        """Decorator to register a tool function."""
        self._tools[func.__name__] = func

        sig = inspect.signature(func)
        properties = {}
        required = []

        for name, param in sig.parameters.items():
            annotation = param.annotation
            if annotation == inspect.Parameter.empty:
                param_type = "string"
            elif annotation == int:
                param_type = "integer"
            elif annotation == bool:
                param_type = "boolean"
            else:
                param_type = "string"

            properties[name] = {
                "type": param_type,
                "description": f"The {name} parameter"
            }

            if param.default == inspect.Parameter.empty:
                required.append(name)

        self._definitions.append({
            "name": func.__name__,
            "description": func.__doc__ or f"Tool: {func.__name__}",
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        })

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    def execute(self, name: str, input_dict: dict) -> dict:
        """Execute a registered tool with structured error handling."""
        if name not in self._tools:
            return {
                "success": False,
                "error": f"Unknown tool: {name}",
                "retry_after": None,
                "suggestion": f"Available tools: {list(self._tools.keys())}"
            }
        try:
            result = self._tools[name](**input_dict)
            return {"success": True, "result": result}
        except ConnectionError:
            return {
                "success": False,
                "error": f"{name} is temporarily unavailable.",
                "retry_after": 2,
                "suggestion": "Retry in 2 seconds."
            }
        except ValueError as e:
            return {
                "success": False,
                "error": f"Invalid input for {name}: {e}",
                "retry_after": None,
                "suggestion": "Check input types and required fields."
            }
        except Exception:
            return {
                "success": False,
                "error": f"{name} encountered an unexpected error.",
                "retry_after": 1,
                "suggestion": "Try once more or try a different approach."
            }

    def execute_with_retry(self, name: str, input_dict: dict, max_retries: int = 2) -> dict:
        """Execute with retry logic. Returns first success or last error."""
        for attempt in range(max_retries + 1):
            result = self.execute(name, input_dict)
            if result["success"]:
                return result
            retry_after = result.get("retry_after")
            if retry_after is None or attempt >= max_retries:
                return result
            time.sleep(retry_after)
        return result

    @property
    def definitions(self) -> list[dict]:
        return self._definitions


# Example: register tools with the decorator
registry = ToolRegistry()


@registry.tool
def search_web_v2(query: str, max_results: int = 5) -> list:
    """Search the web for current information on a topic."""
    if random.random() < 0.5:
        raise ConnectionError("Rate limited")
    return [{"title": f"Result {i} for '{query}'", "url": f"https://example.com/{i}"}
            for i in range(1, max_results + 1)]


@registry.tool
def get_weather_v2(city: str) -> dict:
    """Get current weather conditions for a city."""
    return {"city": city, "temperature": 22, "conditions": "Partly cloudy"}


# ---------------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("DEMO 1: Tool executor with retry (standalone)")
    print("=" * 60)

    print("\nTesting search_web (50% flaky, max 2 retries):")
    for trial in range(3):
        result = run_tool_with_retry("search_web", {"query": "Python async best practices"}, max_retries=2)
        if result["success"]:
            print(f"  Trial {trial+1}: Success - {len(result['result'])} results")
        else:
            print(f"  Trial {trial+1}: Failed - {result['error'][:60]}")

    print("\nTesting calculate_sum with bad input (terminal error):")
    result = run_tool_with_retry("calculate_sum", {"numbers": "1,2,abc,4"}, max_retries=2)
    print(f"  Error (no retry): {result['error'][:80]}")
    print(f"  Suggestion: {result.get('suggestion', '')[:80]}")

    print("\n" + "=" * 60)
    print("DEMO 2: Full agentic loop with error recovery")
    print("=" * 60)

    response = run_agent(
        "Search for information about Python async programming and also get the weather in London.",
        max_turns=8
    )
    print(f"\nAgent final response:\n{response}")

    print("\n" + "=" * 60)
    print("DEMO 3: ToolRegistry class with @tool decorator")
    print("=" * 60)

    print(f"Registered tools: {[d['name'] for d in registry.definitions]}")

    result = registry.execute_with_retry("search_web_v2", {"query": "machine learning"}, max_retries=2)
    if result["success"]:
        print(f"search_web_v2: {len(result['result'])} results")
    else:
        print(f"search_web_v2 error: {result['error'][:80]}")
