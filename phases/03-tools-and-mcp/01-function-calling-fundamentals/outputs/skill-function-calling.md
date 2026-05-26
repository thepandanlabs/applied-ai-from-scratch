---
name: skill-function-calling
description: Reusable tool dispatch loop template with schema generation and @tool decorator pattern
version: "1.0"
phase: "03"
lesson: "01"
tags: [tools, function-calling, dispatch, pydantic, anthropic-sdk]
---

# Tool Dispatch Loop Template

Drop this into any project that needs to give an LLM access to real functions. Includes the full dispatch loop, Pydantic schema generation, and a `@tool` decorator for registry-based setups.

## Core Dispatch Loop

```python
import anthropic
import json

client = anthropic.Anthropic()

TOOLS: list[dict] = []          # populated by @tool decorator or manual definitions
FUNCTION_MAP: dict[str, callable] = {}  # name -> function


def dispatch_tool_call(tool_name: str, tool_input: dict) -> str:
    """Execute a tool by name. Returns JSON string."""
    if tool_name not in FUNCTION_MAP:
        return json.dumps({"error": f"Unknown tool: {tool_name!r}"})
    try:
        result = FUNCTION_MAP[tool_name](**tool_input)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e), "type": type(e).__name__})


def run_with_tools(user_message: str, model: str = "claude-3-5-haiku-20241022") -> str:
    """
    Two-round-trip tool dispatch loop.
    Returns the final natural-language answer from the LLM.
    """
    messages = [{"role": "user", "content": user_message}]

    # Round 1: get tool call request (or direct answer)
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )

    if response.stop_reason == "end_turn":
        return response.content[0].text

    tool_uses = [b for b in response.content if b.type == "tool_use"]
    if not tool_uses:
        return next((b.text for b in response.content if hasattr(b, "text")), "")

    messages.append({"role": "assistant", "content": response.content})

    tool_results = []
    for tu in tool_uses:
        result_str = dispatch_tool_call(tu.name, tu.input)
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": tu.id,
            "content": result_str,
        })

    messages.append({"role": "user", "content": tool_results})

    # Round 2: get final answer
    final = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )
    return next((b.text for b in final.content if hasattr(b, "text")), "")
```

## Schema Generation with Pydantic

```python
from pydantic import BaseModel, Field

def make_tool_schema(name: str, description: str, input_model: type[BaseModel]) -> dict:
    """Generate a Claude-compatible tool schema from a Pydantic model."""
    schema = input_model.model_json_schema()
    schema.pop("title", None)
    return {"name": name, "description": description, "input_schema": schema}
```

## @tool Decorator (Registry Pattern)

```python
from functools import wraps

def tool(description: str, input_model: type[BaseModel]):
    """
    Decorator that registers a function as a callable tool.
    Populates both TOOLS (schemas for the API) and FUNCTION_MAP (callables).
    """
    def decorator(fn):
        schema = make_tool_schema(fn.__name__, description, input_model)
        TOOLS.append(schema)
        FUNCTION_MAP[fn.__name__] = fn

        @wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# Usage example:
class GetWeatherInput(BaseModel):
    location: str = Field(description="City name, e.g. 'San Francisco, CA'")
    unit: str = Field(default="celsius", description="Temperature unit: 'celsius' or 'fahrenheit'")

@tool(
    description="Returns current weather for a location. Use when the user asks about weather or temperature.",
    input_model=GetWeatherInput,
)
def get_weather(location: str, unit: str = "celsius") -> dict:
    # Replace with real API call
    return {"location": location, "temperature": 18, "unit": unit, "condition": "cloudy"}
```

## Key Rules

1. The assistant's response (including tool_use blocks) must be appended to messages before sending tool_results.
2. `tool_use_id` in the tool_result must exactly match the `id` from the tool_use block.
3. All tool results for a multi-tool response go in a single `role: user` message.
4. Never return raw exceptions as tool results. Return `{"error": "...", "hint": "..."}` instead.
5. Descriptions are the LLM's only signal for which tool to call. Write them for the LLM, not for humans.

## Message Structure Reference

```
Turn 1 (you → LLM):
  messages = [{role: user, content: "user message"}]
  tools = [schema1, schema2]

Turn 1 (LLM → you):
  content = [{type: tool_use, id: "toolu_XYZ", name: "...", input: {...}}]
  stop_reason = "tool_use"

Turn 2 (you → LLM):
  messages = [
    {role: user, content: "user message"},
    {role: assistant, content: [tool_use block from turn 1]},  # include verbatim
    {role: user, content: [{type: tool_result, tool_use_id: "toolu_XYZ", content: "..."}]},
  ]

Turn 2 (LLM → you):
  content = [{type: text, text: "final natural-language answer"}]
  stop_reason = "end_turn"
```
