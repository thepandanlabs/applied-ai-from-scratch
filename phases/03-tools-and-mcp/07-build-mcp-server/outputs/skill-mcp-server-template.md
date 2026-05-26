---
name: skill-mcp-server-template
description: Python and TypeScript MCP server templates with tools, resources, and prompts for any data source
version: "1.0"
phase: "03"
lesson: "07"
tags: [mcp, server, python, typescript, tools, resources, prompts]
---

# Skill: MCP Server Template

A complete MCP server exposes three primitive types.
This template shows all three in Python and TypeScript.

---

## Python Template (FastMCP)

```bash
pip install mcp
```

```python
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

# --- Tool (action with inputs, returns result) ---
@mcp.tool()
def my_tool(param: str, limit: int = 10) -> list[dict]:
    """Tool description shown to the LLM. Be specific about what it does."""
    # Validate inputs
    safe_limit = max(1, min(50, limit))
    # Use parameterized queries - never string interpolation
    return query_database(param, safe_limit)

# --- Resource (addressable data, read-only) ---
@mcp.resource("data://{category}")
def get_resource(category: str) -> str:
    """Read data for the given category. Returns JSON string."""
    rows = fetch_by_category(category)
    return json.dumps(rows, indent=2)

# --- Prompt (reusable template the server owns) ---
@mcp.prompt()
def my_prompt(item_id: str, style: str = "brief") -> str:
    """Generate a prompt for processing an item."""
    item = get_item(item_id)
    base = f"Item: {item['name']}\nDetails: {item['details']}\n\n"
    if style == "brief":
        return base + "Write a brief 1-2 sentence summary."
    return base + "Write a detailed analysis covering all aspects."

if __name__ == "__main__":
    import sys
    print("MCP server starting...", file=sys.stderr)
    mcp.run(transport="stdio")
```

---

## TypeScript Template (@modelcontextprotocol/sdk)

```bash
npm install @modelcontextprotocol/sdk zod better-sqlite3
```

```typescript
import { McpServer, ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({ name: "my-server", version: "1.0.0" });

// --- Tool ---
server.tool(
  "my_tool",
  "Tool description shown to the LLM.",
  {
    param: z.string().describe("Input parameter"),
    limit: z.number().int().min(1).max(50).default(10),
  },
  async ({ param, limit }) => {
    const results = await queryDatabase(param, limit);
    return { content: [{ type: "text", text: JSON.stringify(results) }] };
  }
);

// --- Resource ---
server.resource(
  "my-resource",
  new ResourceTemplate("data://{category}", { list: undefined }),
  async (uri, { category }) => {
    const cat = Array.isArray(category) ? category[0] : category;
    const rows = await fetchByCategory(cat);
    return {
      contents: [{
        uri: uri.href,
        mimeType: "application/json",
        text: JSON.stringify(rows, null, 2),
      }],
    };
  }
);

// --- Prompt ---
server.prompt(
  "my_prompt",
  "Generate a processing prompt for an item.",
  {
    item_id: z.string().describe("Item ID to process"),
    style: z.enum(["brief", "detailed"]).default("brief"),
  },
  async ({ item_id, style }) => {
    const item = await getItem(item_id);
    const text = `Item: ${item.name}\n\n` +
      (style === "brief" ? "Summarize briefly." : "Analyze in detail.");
    return { messages: [{ role: "user" as const, content: { type: "text" as const, text } }] };
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write("Server started\n");
}
main().catch(console.error);
```

---

## Claude Desktop Config

```json
{
  "mcpServers": {
    "my-server-python": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    },
    "my-server-node": {
      "command": "node",
      "args": ["/absolute/path/to/dist/main.js"]
    }
  }
}
```

Config file location:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Restart Claude Desktop after editing.

---

## SQL Injection Protection Checklist

- [ ] Use parameterized queries (`?` placeholders) for all user-supplied values
- [ ] Never use f-strings or string interpolation to build SQL
- [ ] Clamp numeric inputs to a safe range before using as LIMIT/OFFSET
- [ ] Whitelist allowed column names and sort directions if building dynamic ORDER BY
- [ ] Use read-only DB connections for Resource handlers (no INSERT/UPDATE/DELETE)

---

## Productionization: SQLite to PostgreSQL

Swap `get_db()` only. The tools and resources stay the same.

```python
# SQLite (demo)
import sqlite3
conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row

# PostgreSQL (production)
import psycopg2
import psycopg2.extras
conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.cursor_factory = psycopg2.extras.RealDictCursor
```

For async: use `asyncpg` with FastMCP's async tool handlers.

---

## stdio Transport Rules

1. ALL logging must go to `sys.stderr` (Python) or `process.stderr` (Node) - never `stdout`
2. Do not print anything to stdout before the first JSON-RPC message
3. Each JSON-RPC message is newline-delimited
4. The server process is spawned by the host - do not start an HTTP server

## When to Use MCP vs Direct Function Calling

| Situation | Use |
|---|---|
| Single AI client, internal tools, no sharing needed | Function calling |
| Multiple AI clients need same capabilities | MCP server |
| Tools need to be discoverable by off-the-shelf AI apps | MCP server |
| Capabilities include read-only data with stable URIs | MCP resource |
| Domain-specific prompts need to be packaged with data | MCP prompt |
