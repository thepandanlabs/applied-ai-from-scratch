---
name: skill-mcp-mental-model
description: The four MCP primitives cheat sheet with usage criteria and architecture decision table
version: "1.0"
phase: "03"
lesson: "06"
tags: [mcp, tools, resources, prompts, sampling, architecture]
---

# Skill: MCP Mental Model

MCP (Model Context Protocol) solves the N*M integration problem.
N AI clients times M capability providers becomes N+M with a shared standard.

---

## The Four Primitives

```
Primitive    Direction        Who initiates     Primary use
-----------  ---------------  ----------------  --------------------------------
Tools        Host -> Server   LLM / agent       Action execution, on-demand data
Resources    Host -> Server   Host or LLM       Read structured data by URI
Prompts      Host -> Server   Host or LLM       Reusable prompt templates
Sampling     Server -> Host   MCP Server        Server-side LLM inference
```

**In one sentence each:**
- Tools = "do this thing and give me a result"
- Resources = "give me this named piece of data by address"
- Prompts = "give me a prompt template the server knows how to fill"
- Sampling = "server asks host to run the LLM for it"

---

## When to Use Each Primitive

| Capability | Use | Reason |
|---|---|---|
| Fetch current stock price | Tool | On-demand, variable result, not addressable |
| Read a specific config file | Resource | Stable URI, safely cacheable, read-only |
| List all open support tickets | Resource | Stable URI, listable, pre-fetchable |
| Create a support ticket | Tool | Mutates state, not read-only |
| Write a commit message for this diff | Prompt | Reusable template with parameters |
| Explain this error stack trace | Prompt | Domain-specific prompt the server owns |
| A summarizer needs LLM output | Sampling | Server-initiated inference |
| Search a knowledge base | Tool | Dynamic query, variable result |
| Subscribe to live data updates | Resource (with subscribe) | Push-based, not pull-on-demand |

**Decision rules:**
1. If it mutates state: Tool
2. If it is read-only with a stable address: Resource
3. If it is a prompt template the server owns: Prompt
4. If the server needs to invoke the LLM: Sampling

---

## JSON-RPC 2.0 Wire Format

```
Request                                 Response
--------------------------------------  --------------------------------------
{                                       {
  "jsonrpc": "2.0",                       "jsonrpc": "2.0",
  "id": 1,                                "id": 1,
  "method": "tools/call",                 "result": {
  "params": {                               "content": [
    "name": "tool_name",                     {"type": "text", "text": "..."}
    "arguments": { ... }                   ],
  }                                        "isError": false
}                                        }
                                        }

Notification (no id, no response):
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized",
  "params": {}
}
```

**Key fields:**
- Requests: `jsonrpc`, `id`, `method`, `params`
- Responses: `jsonrpc`, `id`, `result`
- Errors: `jsonrpc`, `id`, `error: {code, message}`
- Notifications: `jsonrpc`, `method`, `params` (no `id`)

---

## Initialization Sequence

```
1. Host sends initialize (protocol version + client capabilities)
2. Server responds (server name + server capabilities)
3. Host sends notifications/initialized (handshake complete, no response)
4. Host calls tools/list, resources/list, prompts/list to discover capabilities
5. Normal operation begins
```

---

## Architecture Decision Table

| Situation | Recommendation |
|---|---|
| One team, one AI client, internal tools only | Function calling is fine; MCP adds overhead |
| Multiple AI clients need same capabilities | Use MCP: write once, any client connects |
| Capabilities need to be user-browsable | Resource over Tool: Resources are listable |
| Capability is an action with side effects | Tool, never Resource |
| Capability is a domain prompt template | Prompt: server owns it, easier to update |
| Server needs to call the LLM | Sampling: standard way for server-to-host inference |
| Need live data push | Resource with subscribe capability |
| Packaging for Claude Desktop | MCP Server with stdio transport |

---

## SDK Quickstart (Python)

```bash
pip install mcp
```

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
def my_tool(param: str) -> dict:
    """Tool description shown to the LLM."""
    return {"result": param}

@mcp.resource("data://{id}")
def my_resource(id: str) -> str:
    """Read data by id."""
    return f"data for {id}"

@mcp.prompt()
def my_prompt(context: str) -> str:
    """Prompt template with context."""
    return f"Given this context: {context}\n\nPlease analyze..."

if __name__ == "__main__":
    mcp.run(transport="stdio")  # for Claude Desktop
```

---

## Transport Options

| Transport | Use when |
|---|---|
| stdio | Claude Desktop, single-process integration, local tools |
| SSE (Server-Sent Events) | Web-based host, remote server, streaming results |
| HTTP (Streamable) | Production deployment, load-balanced servers |

Default for local development: stdio.
Default for production services: HTTP with SSE.
