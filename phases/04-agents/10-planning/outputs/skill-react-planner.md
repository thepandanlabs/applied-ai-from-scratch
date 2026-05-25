---
name: skill-react-planner
description: ReAct system prompt and thought parser for auditable multi-step agent loops
version: "1.0"
phase: "04"
lesson: "10"
tags: [agents, planning, react, tool-use, debugging]
---

# ReAct Planner

## The ReAct System Prompt

Copy this into any agent that needs auditable tool use. The `Thought:` prefix is the entire mechanism.

```
You are a research agent. You have access to tools.

IMPORTANT: Before every tool call, you MUST output a line starting exactly with "Thought:" that explains:
- What you know so far
- What you are about to do and why
- What you expect to find

Format:
Thought: [your reasoning]
[then call the tool]

If you have enough information to answer without calling more tools:
Thought: I have all the information I need. I will now write the final answer.
[then write your answer]

Be systematic. Work through the task step by step.
```

## The Thought Parser

```python
def extract_thought(text: str) -> str | None:
    """Extract the first Thought: line from a model response."""
    for line in text.splitlines():
        if line.strip().lower().startswith("thought:"):
            return line.strip()[len("thought:"):].strip()
    return None
```

## Thought Trace Dataclass

```python
from dataclasses import dataclass

@dataclass
class ThoughtTrace:
    iteration: int
    thought: str
    action: str | None = None
    observation: str | None = None
```

## Minimal ReAct Loop

```python
def react_loop(task, tools, tool_fn, client, max_iterations=12):
    messages = [{"role": "user", "content": task}]
    trace = []

    for iteration in range(max_iterations):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=REACT_SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        current_thought = None
        for block in response.content:
            if block.type == "text":
                current_thought = extract_thought(block.text)

        if response.stop_reason == "end_turn":
            return next(b.text for b in response.content if b.type == "text"), trace

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = tool_fn[block.name](**block.input)
                    trace.append(ThoughtTrace(
                        iteration=iteration+1,
                        thought=current_thought or "",
                        action=f"{block.name}({block.input})",
                        observation=str(result)[:200],
                    ))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })
            messages.append({"role": "user", "content": tool_results})

    return "Max iterations reached.", trace
```

## Pattern Decision Guide

```
Need to adapt based on intermediate tool results?
    YES -> Use ReAct
    NO  -> Consider Plan-and-Execute

Need to inspect/approve the plan before execution?
    YES -> Plan-and-Execute
    NO  -> ReAct

Task has < 5 tool calls?
    YES -> ReAct (simpler)
    NO  -> Either, depending on predictability

Need to resume from a specific step after failure?
    YES -> Plan-and-Execute (steps are numbered and indexable)
    NO  -> ReAct
```

## What the Thought Log Tells You

| Symptom | Look for in thought log |
|---------|------------------------|
| Agent calls wrong tool | Thought before bad action: misidentified task |
| Agent stops too early | Thought says "done" before all work is complete |
| Agent repeats work | Thoughts show it forgot prior observations |
| Agent goes off-topic | Thought diverges from original task statement |
| Agent never finishes | Thoughts keep finding "one more thing to check" |

## Evaluation Checklist

- [ ] Every tool call is preceded by a non-empty Thought: line
- [ ] Thoughts reference the task goal (not just the immediate action)
- [ ] Thought log is sufficient to explain why each tool was called
- [ ] 70%+ of thoughts correctly predict what the tool will return
- [ ] Agent reaches a terminal state (end_turn) within max_iterations
