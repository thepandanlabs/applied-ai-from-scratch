---
name: skill-agent-loop
description: Copy-paste ready agent loop template with tool registry, tool dispatch pattern, and max-iteration guard
version: "1.0"
phase: "04"
lesson: "01"
tags: [agents, tool-use, agent-loop, anthropic-sdk]
---

# Skill: Agent Loop

A minimal, production-ready agent loop using only the `anthropic` SDK.
Drop this into any project. Swap the tool stubs for real implementations.

## Usage

```python
result = run_agent("Your goal here", max_iterations=10)
print(result)
```

## Full Template

```python
import anthropic
import json

client = anthropic.Anthropic()

# 1. Define your tools as JSON Schema objects
TOOLS = [
    {
        "name": "your_tool_name",
        "description": "What this tool does. Be specific - the model reads this.",
        "input_schema": {
            "type": "object",
            "properties": {
                "param_name": {
                    "type": "string",
                    "description": "Description of this parameter"
                }
            },
            "required": ["param_name"]
        }
    }
]

# 2. Implement your tools
def run_your_tool(param_name: str) -> str:
    # Your implementation here
    return f"Result for: {param_name}"

# 3. Build the registry
TOOL_REGISTRY = {
    "your_tool_name": lambda args: run_your_tool(args["param_name"]),
}

# 4. Tool executor - runs all tool_use blocks, returns tool_result list
def execute_tools(tool_use_blocks: list) -> list[dict]:
    results = []
    for block in tool_use_blocks:
        if block.name in TOOL_REGISTRY:
            output = TOOL_REGISTRY[block.name](block.input)
        else:
            output = f"Error: unknown tool '{block.name}'"
        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": output
        })
    return results

# 5. The loop
def run_agent(goal: str, max_iterations: int = 10) -> str:
    messages = [{"role": "user", "content": goal}]
    system = "Your system prompt here."

    for iteration in range(max_iterations):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=messages
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "(no text in final response)"

        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            # Append full assistant message (all content blocks, not just tool_use)
            messages.append({"role": "assistant", "content": response.content})
            tool_results = execute_tools(tool_use_blocks)
            messages.append({"role": "user", "content": tool_results})
            continue

        return f"Unexpected stop_reason: {response.stop_reason}"

    return f"Stopped after {max_iterations} iterations without end_turn."
```

## Key Rules

**Message history shape.** The history must alternate assistant/user. Every `tool_use` block in an assistant message needs a matching `tool_result` in the next user message with the same `tool_use_id`.

**Append the full content list.** When appending the assistant message, pass `response.content` (the full list), not just the tool_use blocks. The API requires this.

**Always guard with max_iterations.** Agents can loop. Set a limit. 10 is safe for most tasks. Log when you hit it.

**Return structured errors from tools.** If a tool raises an exception, catch it and return a string like `"Error: <message>"`. The model can read that and decide what to do. Never let a tool exception propagate up and break the loop.

**Tool result content is always a string.** The `content` field in a `tool_result` dict must be a string. If your tool returns structured data, `json.dumps()` it before returning.

## Message History Snapshot

After one tool call, the history looks like this:

```python
[
    # Turn 0: initial goal
    {"role": "user", "content": "What is 144 * 17?"},

    # Turn 1: model requested a tool
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_01", "name": "calculator",
         "input": {"expression": "144 * 17"}}
    ]},

    # Turn 1: tool result sent back
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_01", "content": "2448"}
    ]},

    # Turn 2: final answer (stop_reason = end_turn)
    {"role": "assistant", "content": [
        {"type": "text", "text": "144 times 17 is 2,448."}
    ]}
]
```

## Checklist Before Shipping

- [ ] Every tool has a clear `description` and typed `input_schema`
- [ ] All tool errors are caught and returned as strings, not raised
- [ ] `max_iterations` is set and tested with a goal that would exceed it
- [ ] Message history is logged (or persisted) for debugging
- [ ] Tool results are strings (not dicts or objects)
- [ ] System prompt tells the model when it has enough information to stop
