---
name: skill-parallel-tool-calls
description: Parallel tool executor template that handles N tool_use blocks concurrently using asyncio.gather or ThreadPoolExecutor
version: "1.0"
phase: "03"
lesson: "03"
tags: [tools, parallel, asyncio, concurrency, function-calling, performance]
---

# Parallel Tool Executor Template

Drop this into any agent dispatch loop where the LLM may request 2+ independent tools per turn. Includes both async (asyncio.gather) and sync (ThreadPoolExecutor) patterns, with per-tool timeout and structured error output.

## Async Pattern (asyncio.gather)

Use when your codebase is async (FastAPI, aiohttp, httpx, etc.).

```python
import asyncio
import json

async def dispatch_parallel_async(
    tool_uses: list,
    function_map: dict[str, callable],
    timeout_secs: float = 10.0,
) -> list[dict]:
    """
    Execute all tool_use blocks concurrently.
    Returns tool_result dicts ready to send to the LLM.

    Args:
        tool_uses:    List of tool_use content blocks from the LLM response.
        function_map: {tool_name: async_function} mapping.
        timeout_secs: Per-tool timeout. Failed tools return structured errors.
    """
    async def execute_one(tool_use) -> dict:
        try:
            fn = function_map.get(tool_use.name)
            if fn is None:
                result = {"error": f"Unknown tool: {tool_use.name!r}",
                          "hint": "Check that the tool is registered in function_map."}
            else:
                result = await asyncio.wait_for(fn(**tool_use.input), timeout=timeout_secs)
        except asyncio.TimeoutError:
            result = {
                "error": f"Tool {tool_use.name!r} timed out after {timeout_secs}s.",
                "hint": "The data source may be slow. Try again or request less data.",
            }
        except Exception as e:
            result = {"error": str(e), "type": type(e).__name__,
                      "hint": "Unexpected error. Check tool implementation."}
        return {
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": json.dumps(result),
        }

    return list(await asyncio.gather(*[execute_one(tu) for tu in tool_uses]))


# Full async dispatch loop
async def run_with_parallel_tools(
    user_message: str,
    tools: list[dict],
    function_map: dict[str, callable],
    model: str = "claude-3-5-haiku-20241022",
) -> str:
    import anthropic
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user_message}]

    response = client.messages.create(
        model=model, max_tokens=1024, tools=tools, messages=messages
    )

    if response.stop_reason == "end_turn":
        return response.content[0].text

    tool_uses = [b for b in response.content if b.type == "tool_use"]
    if not tool_uses:
        return next((b.text for b in response.content if hasattr(b, "text")), "")

    messages.append({"role": "assistant", "content": response.content})

    # Run all tools concurrently
    tool_results = await dispatch_parallel_async(tool_uses, function_map)
    messages.append({"role": "user", "content": tool_results})

    final = client.messages.create(
        model=model, max_tokens=1024, tools=tools, messages=messages
    )
    return next((b.text for b in final.content if hasattr(b, "text")), "")
```

## Sync Pattern (ThreadPoolExecutor)

Use when your codebase is synchronous (Flask, standard scripts, CLI tools).

```python
import concurrent.futures
import json

def dispatch_parallel_sync(
    tool_uses: list,
    function_map: dict[str, callable],
    timeout_secs: float = 10.0,
) -> list[dict]:
    """
    Execute all tool_use blocks concurrently using a thread pool.
    Returns tool_result dicts ready to send to the LLM.
    """
    def execute_one(tool_use) -> dict:
        fn = function_map.get(tool_use.name)
        if fn is None:
            result = {"error": f"Unknown tool: {tool_use.name!r}"}
        else:
            try:
                result = fn(**tool_use.input)
            except Exception as e:
                result = {"error": str(e), "type": type(e).__name__}
        return {
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": json.dumps(result),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tool_uses)) as executor:
        futures = [executor.submit(execute_one, tu) for tu in tool_uses]
        results = []
        try:
            for f in concurrent.futures.as_completed(futures, timeout=timeout_secs):
                results.append(f.result())
        except concurrent.futures.TimeoutError:
            results.append({
                "type": "tool_result",
                "tool_use_id": "timeout",
                "content": json.dumps({"error": "Batch timed out", "hint": "Reduce concurrent tool count or increase timeout."})
            })
    return results
```

## Key Rules

1. All tool_use blocks from a single LLM response belong in the same execution batch.
2. All tool_results must be sent back in a single `role: user` message (not one message per result).
3. A tool failure must return a structured `tool_result` with `{"error": ..., "hint": ...}`. Never raise an exception that prevents other tools in the batch from completing.
4. Use `asyncio.wait_for` or `ThreadPoolExecutor` timeout to prevent one slow tool from blocking the whole batch.
5. Log start and end timestamps per tool to verify concurrency in production.

## Latency Model

```
Sequential N tools:  t1 + t2 + ... + tN
Parallel N tools:    max(t1, t2, ..., tN) + small overhead (~50ms)

For 3 tools at 1.2s, 0.9s, 1.4s:
  Sequential: 3.5s
  Parallel:   ~1.45s  (2.4x faster)

For 5 tools at 0.5s each:
  Sequential: 2.5s
  Parallel:   ~0.55s  (4.5x faster)
```

## Usage Example

```python
import asyncio

# Define your async tool functions
async def get_weather(location: str) -> dict:
    # real API call here
    return {"location": location, "temp": 18, "condition": "sunny"}

async def get_news(topic: str, limit: int = 3) -> dict:
    # real API call here
    return {"topic": topic, "articles": ["article 1", "article 2"]}

TOOLS = [
    {"name": "get_weather", "description": "...", "input_schema": {...}},
    {"name": "get_news",    "description": "...", "input_schema": {...}},
]

FUNCTION_MAP = {
    "get_weather": get_weather,
    "get_news":    get_news,
}

answer = asyncio.run(
    run_with_parallel_tools(
        user_message="What's the weather in NYC and top AI news today?",
        tools=TOOLS,
        function_map=FUNCTION_MAP,
    )
)
print(answer)
```
