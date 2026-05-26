---
name: skill-mcp-transport-selector
description: Decision guide and config snippets for choosing between stdio, HTTP SSE, and Streamable HTTP MCP transports
version: "1.0"
phase: "03"
lesson: "09"
tags: [mcp, transport, stdio, sse, streamable-http, deployment]
---

# MCP Transport Selector

Use this guide when deploying an MCP server and you need to pick the right transport.

## The One-Question Decision

**Can the client fork the server process on the same machine?**

- Yes: use `stdio`
- No: are you in production or serving multiple clients? Yes: use `streamable_http`. No: use `sse`

## Transport Comparison

```
                  stdio           HTTP SSE        Streamable HTTP
                  ─────────────   ─────────────   ───────────────
Deployment        Same machine    Remote OK       Remote OK
Clients           One at a time   Multiple seq.   Multiple + concurrent
Session state     Process = session   Per-request     Session ID + reconnect
Streaming         Pipe (fast)     Server-to-client  Bidirectional
Setup             Zero            HTTP server     HTTP server + session mgr
Use case          Local dev,      Simple remote   Hosted, production,
                  Claude Desktop  single client   multi-team
```

## Config Snippets

### stdio - Claude Desktop

```json
{
  "mcpServers": {
    "your-server": {
      "command": "python",
      "args": ["/absolute/path/to/main.py"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/venv/lib/python3.11/site-packages"
      }
    }
  }
}
```

Critical: the server must never print to stdout except MCP protocol messages. Route all debug output to stderr.

### HTTP SSE - Server

```python
from mcp.server import FastMCP

mcp = FastMCP("your-server")

# ... register tools ...

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8080)
```

### HTTP SSE - Claude Desktop

```json
{
  "mcpServers": {
    "your-server": {
      "url": "http://your-host:8080/sse"
    }
  }
}
```

### Streamable HTTP - Server

```python
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
from mcp.server import FastMCP
from mcp.server.streamable_http import StreamableHTTPSessionManager

mcp = FastMCP("your-server")

# ... register tools ...

session_manager = StreamableHTTPSessionManager(
    app=mcp,
    event_store=None,  # Swap for Redis in production for cross-process sessions
)

app = Starlette(
    routes=[Mount("/mcp", app=session_manager.asgi_app())]
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

### Streamable HTTP - Claude Desktop

```json
{
  "mcpServers": {
    "your-server": {
      "url": "http://your-host:8080/mcp"
    }
  }
}
```

### Client Connection Code (Python)

```python
# stdio client
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async with stdio_client(StdioServerParameters(command="python", args=["main.py"])) as (r, w):
    async with ClientSession(r, w) as session:
        await session.initialize()

# SSE client
from mcp.client.sse import sse_client

async with sse_client("http://localhost:8080/sse") as (r, w):
    async with ClientSession(r, w) as session:
        await session.initialize()

# Streamable HTTP client
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client("http://localhost:8080/mcp") as (r, w, _):
    async with ClientSession(r, w) as session:
        await session.initialize()
```

## Common Pitfalls

- **stdio stdout pollution:** Any `print()` call in the server breaks the protocol. Use `print(..., file=sys.stderr)` or a logger configured to write to stderr.
- **SSE timeout on slow tools:** SSE does not support in-progress updates. If a tool runs for more than ~30 seconds, clients time out. Switch to Streamable HTTP and push progress events.
- **Streamable HTTP with in-memory session store:** `event_store=None` loses all sessions if the server restarts. For production, use a Redis-backed event store so clients can reconnect.
- **Firewall and load balancer config for SSE:** SSE requires the HTTP connection to stay open. Ensure your load balancer or reverse proxy does not time out long-lived connections (set `proxy_read_timeout` in nginx, or equivalent).
