---
name: prompt-sdk-tradeoffs
description: Decision rubric and comparison table for choosing between Raw SDK, Agents SDK, and LangGraph
version: "1.0"
phase: "04"
lesson: "12"
tags: [agents, sdk, langgraph, architecture, decision-making]
---

# Agent SDK Decision Rubric

## Five-Question Rubric (run at project start)

Answer these before writing any agent code:

1. Does the workflow need to resume after a process restart or failure?
2. Does a human need to approve or intervene at a specific step mid-flow?
3. How many distinct branching paths does the workflow have? (Count them.)
4. Do you need a custom loop pattern that standard SDKs don't support?
5. Is standard tool use with retry and streaming sufficient?

**If YES to 1, 2, or branching_paths > 5:** LangGraph
**If YES to 4:** Raw Anthropic SDK
**Otherwise:** Claude Agent SDK (or OpenAI Agents SDK)

## Decision Rubric as a Function

```python
def choose_sdk(
    needs_resumable_state: bool = False,
    needs_human_in_loop: bool = False,
    branching_paths: int = 1,
    has_custom_loop_pattern: bool = False,
) -> str:
    if needs_resumable_state or needs_human_in_loop or branching_paths > 5:
        return "LangGraph"
    if has_custom_loop_pattern:
        return "Raw Anthropic SDK"
    return "Claude Agent SDK (or OpenAI Agents SDK)"
```

## Comparison Table

```
Feature                   | Raw SDK   | Agents SDK | LangGraph
--------------------------|-----------|------------|----------
Lines for a 3-tool loop   | ~80       | ~40        | ~120+
Tool registration         | Manual    | @tool dec  | Manual/decorator
Input validation          | Manual    | Pydantic   | Pydantic
Retry / backoff           | Manual    | Built-in   | Manual or plugin
Streaming                 | Manual    | Built-in   | Manual
Agent handoffs            | Manual    | Built-in   | Via routing
Resumable state           | No        | No         | Yes (checkpoints)
Human-in-the-loop         | Manual    | Manual     | Built-in
Graph topology required   | No        | No         | Yes
Debuggability             | High      | Medium     | Low (complex graphs)
Learning curve            | Low       | Low        | High
```

## Task-to-SDK Mapping

| Task type | Recommended |
|-----------|-------------|
| Customer support bot (3-5 tools, linear) | Agents SDK |
| Document processing pipeline | Agents SDK |
| Research agent (adaptive, 5-10 tools) | Agents SDK or Raw |
| Financial approval workflow | LangGraph |
| Multi-day background research | LangGraph |
| Custom streaming chat interface | Raw SDK |
| Order fulfillment (40+ steps, branching) | LangGraph |
| Simple Q&A with tool use | Raw SDK |

## LangGraph Legitimacy Checklist

LangGraph is justified when you need at least one of:

- [ ] Workflow must resume after a process crash (checkpointing)
- [ ] Human must approve, reject, or modify output at a specific step
- [ ] Routing logic branches differently based on runtime state (5+ distinct paths)
- [ ] Long-running workflow that spans hours or days
- [ ] Parallel branches that fan out and merge

LangGraph is NOT justified by:

- "We might need it later"
- "The agent is complex" (many tools is not the same as branching state)
- "The team already knows LangGraph"
- "It's more organized"

## When Raw SDK is Better Than Agents SDK

- You need a non-standard loop pattern (e.g., parallel tool calls with custom merging)
- You need complete observability of every message in the list
- You are prototyping and want to understand exactly what is happening
- The Agents SDK abstraction doesn't match your tool calling pattern

## Warning Signs You Chose the Wrong SDK

| Symptom | Likely cause |
|---------|-------------|
| Graph has 30+ nodes | LangGraph chosen for a task that needed Agents SDK |
| State dict has 20+ keys | Over-engineered state schema; refactor to simpler flow |
| Debugging requires drawing the graph | Complexity exceeds the team's understanding |
| 3-tool agent took 3 weeks to build | Raw SDK chosen; should have used Agents SDK |
| Retry logic appears 4 times in the codebase | Raw SDK without shared utilities |
