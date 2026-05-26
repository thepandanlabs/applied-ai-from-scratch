---
name: skill-mcp-client
description: Generic MCP client that auto-discovers tools from any server and wires them into the Anthropic agent loop
version: "1.0"
phase: "03"
lesson: "08"
tags: [mcp, client, agents, tool-discovery, anthropic]
---

# Skill: MCP Client

A generic MCP client that connects to any MCP server, discovers its tools,
and wires them into the Anthropic agent loop without hardcoding schemas.

---

## The Core Pattern

```python
import asyncio
import json
import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def mcp_to_anthropic_schema(tool) -> dict:
    """MCP inputSchema -> Anthropic input_schema (key rename only)."""
    return {
        "name": tool.name,
        "description": tool.description or tool.name,
        "input_schema": tool.inputSchema,
    }


async def run_agent(user_message: str, server_script: str) -> str:
    client = anthropic.Anthropic()
    server_params = StdioServerParameters(command="python", args=[server_script])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            # 1. Initialize
            await session.initialize()

            # 2. Discover tools (the key: no hardcoded schemas)
            tools_result = await session.list_tools()
            tools = [mcp_to_anthropic_schema(t) for t in tools_result.tools]

            # 3. Agent loop
            messages = [{"role": "user", "content": user_message}]

            while True:
                resp = client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=2048,
                    tools=tools,
                    messages=messages,
                )

                if resp.stop_reason == "end_turn":
                    return next(
                        (b.text for b in resp.content if hasattr(b, "text")), ""
                    )

                # Route tool calls through the MCP server
                messages.append({"role": "assistant", "content": resp.content})
                results = []
                for b in resp.content:
                    if b.type == "tool_use":
                        r = await session.call_tool(b.name, b.input)
                        text = "\n".join(
                            c.text for c in r.content if hasattr(c, "text")
                        )
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": b.id,
                            "content": text,
                        })
                messages.append({"role": "user", "content": results})


# Usage
if __name__ == "__main__":
    result = asyncio.run(run_agent(
        "What keyboards do you have?",
        server_script="/path/to/server/main.py",
    ))
    print(result)
```

---

## Schema Conversion Reference

```
MCP Tool Definition                     Anthropic Tool Schema
(from session.list_tools())             (for client.messages.create())
-----------------------------------     -----------------------------------
tool.name           ->  "name"
tool.description    ->  "description"
tool.inputSchema    ->  "input_schema"  (camelCase -> snake_case rename)
  .type                   .type         (identical)
  .properties             .properties   (identical)
  .required               .required     (identical)
```

The conversion is a single key rename. All nested fields are unchanged.

---

## Tool Call Routing

```python
async def call_tool_safe(session: ClientSession, name: str, args: dict) -> str:
    """Route a tool call and handle errors gracefully."""
    try:
        result = await session.call_tool(name, args)
        if result.isError:
            error = "\n".join(
                getattr(b, "text", str(b)) for b in result.content
            )
            return f"Tool error: {error}"
        return "\n".join(
            getattr(b, "text", "") for b in result.content if hasattr(b, "text")
        )
    except Exception as e:
        return f"Transport error calling {name}: {e}"
```

---

## Error Handling Checklist

- [ ] Catch transport errors on `stdio_client` context enter (server not found)
- [ ] Check `result.isError` on each `call_tool` response
- [ ] Set a turn limit (e.g. `for turn in range(10)`) to prevent infinite loops
- [ ] Handle `stop_reason == "max_tokens"` in addition to `"end_turn"` and `"tool_use"`
- [ ] Log to `sys.stderr`, not `sys.stdout`, if output is being parsed downstream

---

## Multi-Server Discovery

When connecting to multiple servers, namespace tool names to prevent collisions:

```python
async def discover_all_tools(
    servers: dict[str, ClientSession]
) -> tuple[list[dict], dict[str, str]]:
    """
    Discover tools from multiple servers.
    Returns (tools_list, tool_to_server_map).
    """
    all_tools = []
    tool_server_map = {}  # tool_name -> server_name

    for server_name, session in servers.items():
        result = await session.list_tools()
        for tool in result.tools:
            namespaced_name = f"{server_name}__{tool.name}"
            all_tools.append({
                "name": namespaced_name,
                "description": f"[{server_name}] {tool.description or tool.name}",
                "input_schema": tool.inputSchema,
            })
            tool_server_map[namespaced_name] = server_name

    return all_tools, tool_server_map

# In the agent loop, route by server:
async def call_tool_multi(
    sessions: dict[str, ClientSession],
    tool_server_map: dict[str, str],
    tool_name: str,
    args: dict,
) -> str:
    server_name = tool_server_map[tool_name]
    original_name = tool_name.split("__", 1)[1]
    session = sessions[server_name]
    result = await session.call_tool(original_name, args)
    return "\n".join(
        getattr(b, "text", "") for b in result.content if hasattr(b, "text")
    )
```

---

## When Discovery Runs

| Agent Pattern | When to Discover |
|---|---|
| Stateless (new connection per request) | On every request |
| Long-running (persistent connection) | On startup, then on tools/list_changed notification |
| Serverless function | On cold start; cache result in memory for warm starts |
| Multiple replicas | Each replica discovers independently on startup |

For most production agents: discover on connection start, re-discover if the
server sends a `notifications/tools/list_changed` event.

---

## Discovery Overhead

Expected timing for a local stdio server:
- `session.initialize()`: 5-20ms
- `session.list_tools()`: 2-10ms
- Total discovery: under 50ms

If discovery is slow, the server's `__main__` block is doing work before
handling the `initialize` request. Move expensive setup (DB connections,
model loading) to lazy initialization inside the first tool call.
