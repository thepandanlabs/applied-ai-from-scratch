"""
Lesson 03-14: Capstone -- MCP Tool Ecosystem for a Domain
A complete Engineering Operations MCP ecosystem with 3 servers behind a gateway.

Servers:
  - code-server:      search_codebase, get_file, list_directory
  - incidents-server: list_incidents, get_incident, add_note
  - metrics-server:   get_metric, list_metrics

Run demo mode:   python main.py
Run MCP server:  python main.py --server
Run tests:       python main.py --test
"""

import argparse
import asyncio
import json
import sqlite3
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import anthropic

# ---------------------------------------------------------------------------
# Mock data stores
# ---------------------------------------------------------------------------

def _build_code_index() -> sqlite3.Connection:
    """In-memory SQLite file index simulating a codebase."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            content TEXT,
            language TEXT,
            size_bytes INTEGER,
            last_modified TEXT
        )
    """)
    files = [
        ("README.md", "# Engineering Platform\n\nThis repo contains the core platform services.", "markdown", 512, "2026-05-20"),
        ("ARCHITECTURE.md", "# Architecture\n\n## Services\n- auth-service: handles token validation\n- api-gateway: routes requests\n- metrics-collector: aggregates metrics", "markdown", 1024, "2026-05-15"),
        ("auth/token_validator.py", "import redis\n\ncache = redis.Redis(host='redis-prod')\n\ndef validate_token(token: str) -> bool:\n    cached = cache.get(f'token:{token}')\n    if cached:\n        return cached == b'valid'\n    result = db_validate(token)\n    cache.setex(f'token:{token}', 300, 'valid' if result else 'invalid')\n    return result", "python", 387, "2026-05-25"),
        ("auth/middleware.py", "from .token_validator import validate_token\n\ndef auth_middleware(request):\n    token = request.headers.get('Authorization', '').replace('Bearer ', '')\n    if not validate_token(token):\n        raise AuthError('Invalid token')", "python", 215, "2026-05-18"),
        ("api/routes.py", "from fastapi import FastAPI\nfrom auth.middleware import auth_middleware\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'status': 'ok'}\n\n@app.get('/api/users')\nasync def list_users(auth=Depends(auth_middleware)):\n    return db.get_users()", "python", 432, "2026-05-22"),
        ("metrics/collector.py", "from prometheus_client import Counter, Histogram\n\nerror_counter = Counter('api_errors_total', 'Total API errors')\nlatency_histogram = Histogram('request_latency_seconds', 'Request latency')", "python", 198, "2026-05-19"),
        ("infra/docker-compose.yml", "version: '3.8'\nservices:\n  auth-service:\n    image: auth-service:latest\n  redis:\n    image: redis:7-alpine\n  api-gateway:\n    image: api-gateway:latest", "yaml", 344, "2026-05-21"),
    ]
    conn.executemany("INSERT INTO files VALUES (?, ?, ?, ?, ?)", files)
    conn.commit()
    return conn


def _build_incidents_store() -> sqlite3.Connection:
    """In-memory SQLite store for incidents."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE incidents (
            id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            severity TEXT,
            service TEXT,
            opened_at TEXT,
            resolved_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE incident_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT,
            note TEXT,
            added_at TEXT,
            author TEXT
        )
    """)
    incidents = [
        ("INC-2024", "auth-service latency spike", "investigating", "P1", "auth-service", "2026-05-25T14:40:00Z", None),
        ("INC-2023", "metrics-collector OOM crash", "resolved", "P2", "metrics-collector", "2026-05-24T09:15:00Z", "2026-05-24T11:30:00Z"),
        ("INC-2022", "api-gateway 502 errors on /api/users", "resolved", "P1", "api-gateway", "2026-05-23T16:00:00Z", "2026-05-23T17:45:00Z"),
        ("INC-2021", "redis eviction causing stale token cache", "open", "P3", "redis", "2026-05-22T08:00:00Z", None),
    ]
    conn.executemany("INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?, ?)", incidents)
    notes = [
        ("INC-2024", "Alert fired at 14:40 UTC. auth-service p95 latency at 1800ms, baseline 80ms.", "2026-05-25T14:41:00Z", "oncall-bot"),
        ("INC-2024", "Deployed Redis cache for token validation 2 hours prior. Investigating correlation.", "2026-05-25T14:55:00Z", "eng-platform"),
        ("INC-2023", "Metrics collector heap exhausted processing 24h backfill. Restarted with 4GB limit.", "2026-05-24T11:00:00Z", "sre-team"),
        ("INC-2022", "Auth middleware throwing AuthError due to invalid token format after auth-service upgrade. Rolled back.", "2026-05-23T17:30:00Z", "oncall-eng"),
    ]
    conn.executemany(
        "INSERT INTO incident_notes (incident_id, note, added_at, author) VALUES (?, ?, ?, ?)", notes
    )
    conn.commit()
    return conn


# In-memory metrics (stub data)
_METRICS_DATA: dict[str, dict[str, Any]] = {
    "api_error_rate": {
        "name": "api_error_rate",
        "unit": "percent",
        "description": "API endpoint error rate",
        "windows": {
            "5m":  {"value": 2.8, "trend": "up",   "prev": 0.4},
            "15m": {"value": 2.1, "trend": "up",   "prev": 0.5},
            "1h":  {"value": 1.2, "trend": "up",   "prev": 0.4},
            "24h": {"value": 0.6, "trend": "stable", "prev": 0.5},
        },
    },
    "auth_service_latency_p95": {
        "name": "auth_service_latency_p95",
        "unit": "milliseconds",
        "description": "auth-service p95 response latency",
        "windows": {
            "5m":  {"value": 1840, "trend": "up",   "prev": 82},
            "15m": {"value": 1620, "trend": "up",   "prev": 79},
            "1h":  {"value": 940,  "trend": "up",   "prev": 80},
            "24h": {"value": 290,  "trend": "up",   "prev": 81},
        },
    },
    "redis_eviction_rate": {
        "name": "redis_eviction_rate",
        "unit": "keys_per_second",
        "description": "Redis key eviction rate",
        "windows": {
            "5m":  {"value": 142, "trend": "up",   "prev": 3},
            "15m": {"value": 98,  "trend": "up",   "prev": 4},
            "1h":  {"value": 55,  "trend": "up",   "prev": 3},
            "24h": {"value": 18,  "trend": "up",   "prev": 3},
        },
    },
    "deployment_frequency": {
        "name": "deployment_frequency",
        "unit": "deployments_per_day",
        "description": "Number of production deployments per day",
        "windows": {
            "24h": {"value": 4, "trend": "stable", "prev": 3},
            "7d":  {"value": 3.2, "trend": "stable", "prev": 3.1},
        },
    },
}


# ---------------------------------------------------------------------------
# Server handlers
# ---------------------------------------------------------------------------

# These are shared database handles (module-level for demo)
_CODE_DB = _build_code_index()
_INCIDENTS_DB = _build_incidents_store()


def _handle_code(tool_name: str, args: dict[str, Any]) -> Any:
    """Handler for code-server tools."""
    if tool_name == "search_codebase":
        query = args.get("query", "").lower()
        limit = min(int(args.get("limit", 10)), 50)
        cursor = _CODE_DB.cursor()
        cursor.execute(
            """SELECT path, language, size_bytes, last_modified,
                      SUBSTR(content, 1, 200) as snippet
               FROM files
               WHERE LOWER(path) LIKE ? OR LOWER(content) LIKE ?
               LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit),
        )
        rows = cursor.fetchall()
        return {
            "results": [
                {
                    "path": r["path"],
                    "language": r["language"],
                    "snippet": r["snippet"],
                    "size_bytes": r["size_bytes"],
                }
                for r in rows
            ],
            "count": len(rows),
            "query": query,
        }

    elif tool_name == "get_file":
        path = args.get("path", "")
        cursor = _CODE_DB.cursor()
        cursor.execute("SELECT * FROM files WHERE path = ?", (path,))
        row = cursor.fetchone()
        if not row:
            return {"error": "file_not_found", "path": path}
        return {
            "path": row["path"],
            "content": row["content"],
            "language": row["language"],
            "size_bytes": row["size_bytes"],
            "last_modified": row["last_modified"],
        }

    elif tool_name == "list_directory":
        dir_path = args.get("path", "/").rstrip("/")
        cursor = _CODE_DB.cursor()
        if dir_path in ("/", ""):
            # List top-level items
            cursor.execute("SELECT path FROM files")
            all_paths = [r["path"] for r in cursor.fetchall()]
            # Extract top-level dirs and files
            items: set[str] = set()
            for p in all_paths:
                parts = p.split("/")
                if len(parts) == 1:
                    items.add(f"FILE: {parts[0]}")
                else:
                    items.add(f"DIR:  {parts[0]}/")
            return {"path": "/", "items": sorted(items)}
        else:
            prefix = dir_path.lstrip("/") + "/"
            cursor.execute("SELECT path FROM files WHERE path LIKE ?", (f"{prefix}%",))
            rows = cursor.fetchall()
            return {
                "path": dir_path,
                "items": [r["path"] for r in rows],
                "count": len(rows),
            }

    return {"error": "unknown_tool", "name": tool_name}


def _handle_incidents(tool_name: str, args: dict[str, Any]) -> Any:
    """Handler for incidents-server tools."""
    if tool_name == "list_incidents":
        status = args.get("status", "all")
        limit = min(int(args.get("limit", 10)), 50)
        cursor = _INCIDENTS_DB.cursor()
        if status == "all":
            cursor.execute("SELECT * FROM incidents ORDER BY opened_at DESC LIMIT ?", (limit,))
        else:
            cursor.execute(
                "SELECT * FROM incidents WHERE status = ? ORDER BY opened_at DESC LIMIT ?",
                (status, limit),
            )
        rows = cursor.fetchall()
        return {
            "incidents": [dict(r) for r in rows],
            "count": len(rows),
            "status_filter": status,
        }

    elif tool_name == "get_incident":
        inc_id = args.get("id", "")
        cursor = _INCIDENTS_DB.cursor()
        cursor.execute("SELECT * FROM incidents WHERE id = ?", (inc_id,))
        row = cursor.fetchone()
        if not row:
            return {"error": "incident_not_found", "id": inc_id}
        incident = dict(row)
        cursor.execute(
            "SELECT * FROM incident_notes WHERE incident_id = ? ORDER BY added_at",
            (inc_id,),
        )
        notes = [dict(n) for n in cursor.fetchall()]
        incident["notes"] = notes
        return incident

    elif tool_name == "add_note":
        inc_id = args.get("incident_id", "")
        note = args.get("note", "")
        if not inc_id or not note:
            return {"error": "invalid_args", "message": "incident_id and note are required"}
        cursor = _INCIDENTS_DB.cursor()
        cursor.execute("SELECT id FROM incidents WHERE id = ?", (inc_id,))
        if not cursor.fetchone():
            return {"error": "incident_not_found", "id": inc_id}
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO incident_notes (incident_id, note, added_at, author) VALUES (?, ?, ?, ?)",
            (inc_id, note, now, "ai-agent"),
        )
        _INCIDENTS_DB.commit()
        return {"status": "added", "incident_id": inc_id, "note": note, "added_at": now}

    return {"error": "unknown_tool", "name": tool_name}


def _handle_metrics(tool_name: str, args: dict[str, Any]) -> Any:
    """Handler for metrics-server tools."""
    if tool_name == "list_metrics":
        return {
            "metrics": [
                {"name": m["name"], "unit": m["unit"], "description": m["description"]}
                for m in _METRICS_DATA.values()
            ],
            "count": len(_METRICS_DATA),
        }

    elif tool_name == "get_metric":
        name = args.get("name", "")
        window = args.get("window", "1h")
        if name not in _METRICS_DATA:
            return {
                "error": "metric_not_found",
                "name": name,
                "available": list(_METRICS_DATA.keys()),
            }
        metric = _METRICS_DATA[name]
        windows = metric["windows"]
        if window not in windows:
            return {
                "error": "window_not_available",
                "name": name,
                "window": window,
                "available_windows": list(windows.keys()),
            }
        point = windows[window]
        return {
            "name": name,
            "unit": metric["unit"],
            "description": metric["description"],
            "window": window,
            "value": point["value"],
            "trend": point["trend"],
            "previous_value": point["prev"],
            "change_pct": round((point["value"] - point["prev"]) / max(point["prev"], 0.001) * 100, 1),
            "sampled_at": "2026-05-25T15:00:00Z",
        }

    return {"error": "unknown_tool", "name": tool_name}


# ---------------------------------------------------------------------------
# Gateway (reuses pattern from Lesson 12)
# ---------------------------------------------------------------------------

@dataclass
class MockServer:
    name: str
    namespace: str
    tool_schemas: list[dict]
    handler: Callable[[str, dict[str, Any]], Any]


class MCPGateway:
    """
    Minimal MCP gateway: aggregates tools from multiple servers,
    routes calls by namespace prefix.
    """

    def __init__(self, servers: list[MockServer]) -> None:
        self._servers: dict[str, MockServer] = {s.namespace: s for s in servers}
        self._health: dict[str, bool] = {s.namespace: True for s in servers}

    def list_tools(self) -> list[dict]:
        all_tools = []
        for ns, server in self._servers.items():
            if not self._health[ns]:
                continue
            for schema in server.tool_schemas:
                prefixed = dict(schema)
                prefixed["name"] = f"{ns}::{schema['name']}"
                prefixed["description"] = f"[{server.name}] {schema.get('description', '')}"
                all_tools.append(prefixed)
        return all_tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if "::" not in tool_name:
            return {
                "error": "invalid_tool_name",
                "message": f"Expected 'namespace::tool_name', got '{tool_name}'",
                "available_namespaces": list(self._servers.keys()),
            }
        namespace, raw_name = tool_name.split("::", 1)
        if namespace not in self._servers:
            return {
                "error": "unknown_namespace",
                "namespace": namespace,
                "available": list(self._servers.keys()),
            }
        if not self._health[namespace]:
            return {
                "error": "server_unavailable",
                "server": self._servers[namespace].name,
                "retry_after_seconds": 30,
            }
        return self._servers[namespace].handler(raw_name, arguments)

    def status(self) -> dict:
        return {
            "servers": [
                {
                    "namespace": ns,
                    "name": server.name,
                    "healthy": self._health[ns],
                    "tool_count": len(server.tool_schemas),
                }
                for ns, server in self._servers.items()
            ],
            "total_tools": sum(
                len(s.tool_schemas)
                for ns, s in self._servers.items()
                if self._health[ns]
            ),
        }

    def set_health(self, namespace: str, healthy: bool) -> None:
        if namespace in self._health:
            self._health[namespace] = healthy


# ---------------------------------------------------------------------------
# Build the gateway
# ---------------------------------------------------------------------------

def build_gateway() -> MCPGateway:
    """Initialize the full Engineering Operations ecosystem gateway."""
    code_tools = [
        {
            "name": "search_codebase",
            "description": "Full-text search across the indexed codebase.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term"},
                    "limit": {"type": "integer", "default": 10, "description": "Max results"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_file",
            "description": "Get the content of a file by path.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "File path"}},
                "required": ["path"],
            },
        },
        {
            "name": "list_directory",
            "description": "List files in a directory.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string", "default": "/"}},
            },
        },
    ]

    incidents_tools = [
        {
            "name": "list_incidents",
            "description": "List incidents filtered by status.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["open", "investigating", "resolved", "all"],
                        "default": "all",
                    },
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
        {
            "name": "get_incident",
            "description": "Get full incident details including timeline notes.",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string", "description": "Incident ID, e.g. INC-2024"}},
                "required": ["id"],
            },
        },
        {
            "name": "add_note",
            "description": "Add a note to an existing incident.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "incident_id": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["incident_id", "note"],
            },
        },
    ]

    metrics_tools = [
        {
            "name": "get_metric",
            "description": "Get a named metric for a time window.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Metric name"},
                    "window": {
                        "type": "string",
                        "description": "Time window: 5m, 15m, 1h, 24h",
                        "default": "1h",
                    },
                },
                "required": ["name"],
            },
        },
        {
            "name": "list_metrics",
            "description": "List all available metric names and their units.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]

    return MCPGateway(
        servers=[
            MockServer(
                name="code-server",
                namespace="code",
                tool_schemas=code_tools,
                handler=_handle_code,
            ),
            MockServer(
                name="incidents-server",
                namespace="incidents",
                tool_schemas=incidents_tools,
                handler=_handle_incidents,
            ),
            MockServer(
                name="metrics-server",
                namespace="metrics",
                tool_schemas=metrics_tools,
                handler=_handle_metrics,
            ),
        ]
    )


# ---------------------------------------------------------------------------
# MCP server (stdio transport for Claude Desktop)
# ---------------------------------------------------------------------------

async def run_as_mcp_server(gateway: MCPGateway) -> None:
    """Expose the full ecosystem as a single MCP server over stdio."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent
    except ImportError:
        print("Install mcp: pip install mcp")
        return

    app = Server("eng-ops-gateway")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {"type": "object", "properties": {}}),
            )
            for t in gateway.list_tools()
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        result = gateway.call_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_tests(gateway: MCPGateway) -> None:
    """Level 1-3 tests: schema validation, round-trip, routing."""
    print("\n=== Running Ecosystem Tests ===\n")
    passed = 0
    failed = 0

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if condition:
            print(f"  PASS  {name}")
            passed += 1
        else:
            print(f"  FAIL  {name}" + (f" -- {detail}" if detail else ""))
            failed += 1

    # --- Level 1: Schema validation ---
    print("Level 1: Tool schema validation")
    for tool in gateway.list_tools():
        schema = tool.get("inputSchema", {})
        required = schema.get("required", [])
        properties = set(schema.get("properties", {}).keys())
        check(
            f"schema: {tool['name']}",
            set(required).issubset(properties),
            f"required={required}, properties={list(properties)}",
        )

    # --- Level 2: Round-trip per tool ---
    print("\nLevel 2: Round-trip integration tests")
    test_calls = [
        ("code::search_codebase", {"query": "auth"}),
        ("code::get_file", {"path": "auth/token_validator.py"}),
        ("code::list_directory", {"path": "/"}),
        ("incidents::list_incidents", {"status": "open"}),
        ("incidents::get_incident", {"id": "INC-2024"}),
        ("incidents::add_note", {"incident_id": "INC-2024", "note": "automated test note"}),
        ("metrics::get_metric", {"name": "api_error_rate", "window": "5m"}),
        ("metrics::list_metrics", {}),
    ]
    for tool_name, args in test_calls:
        result = gateway.call_tool(tool_name, args)
        check(f"round-trip: {tool_name}", "error" not in result, str(result))

    # --- Level 2: Error cases ---
    print("\nLevel 2: Error handling")
    check("unknown_namespace",
          gateway.call_tool("unknown::tool", {}).get("error") == "unknown_namespace")
    check("missing_prefix",
          gateway.call_tool("search_codebase", {}).get("error") == "invalid_tool_name")
    check("file_not_found",
          gateway.call_tool("code::get_file", {"path": "nonexistent.py"}).get("error") == "file_not_found")
    check("incident_not_found",
          gateway.call_tool("incidents::get_incident", {"id": "INC-9999"}).get("error") == "incident_not_found")
    check("metric_not_found",
          gateway.call_tool("metrics::get_metric", {"name": "fake_metric"}).get("error") == "metric_not_found")

    # --- Level 3: Routing correctness ---
    print("\nLevel 3: Gateway routing")
    call_log: list[str] = []
    original_handlers = {ns: server.handler for ns, server in gateway._servers.items()}

    for ns in gateway._servers:
        def make_logging_handler(namespace: str, original):
            def handler(tool, args):
                call_log.append(namespace)
                return original(tool, args)
            return handler
        gateway._servers[ns].handler = make_logging_handler(ns, original_handlers[ns])

    gateway.call_tool("code::search_codebase", {"query": "test"})
    check("routing: code::search_codebase goes to code",
          call_log == ["code"], str(call_log))

    call_log.clear()
    gateway.call_tool("incidents::list_incidents", {})
    check("routing: incidents::list_incidents goes to incidents",
          call_log == ["incidents"], str(call_log))

    call_log.clear()
    gateway.call_tool("metrics::list_metrics", {})
    check("routing: metrics::list_metrics goes to metrics",
          call_log == ["metrics"], str(call_log))

    # Restore original handlers
    for ns, handler in original_handlers.items():
        gateway._servers[ns].handler = handler

    # --- Graceful degradation ---
    print("\nLevel 3: Graceful degradation")
    gateway.set_health("incidents", False)
    tools_after = gateway.list_tools()
    inc_tools = [t for t in tools_after if t["name"].startswith("incidents::")]
    check("degradation: incidents tools removed when server down", len(inc_tools) == 0, str(inc_tools))

    unavailable = gateway.call_tool("incidents::list_incidents", {})
    check("degradation: call to down server returns structured error",
          unavailable.get("error") == "server_unavailable")
    gateway.set_health("incidents", True)

    print(f"\n=== Results: {passed} passed, {failed} failed ===\n")


# ---------------------------------------------------------------------------
# Demo: Claude using the full ecosystem
# ---------------------------------------------------------------------------

def run_demo(gateway: MCPGateway) -> None:
    print("\n=== Engineering Operations MCP Ecosystem: Lesson 03-14 ===\n")

    # Status
    status = gateway.status()
    print("--- Ecosystem Status ---")
    for s in status["servers"]:
        health = "healthy" if s["healthy"] else "UNAVAILABLE"
        print(f"  {s['namespace']:12} -> {s['name']:22} [{health}] ({s['tool_count']} tools)")
    print(f"\nTotal available tools: {status['total_tools']}")

    print("\n--- All Tools (aggregated via gateway) ---")
    for t in gateway.list_tools():
        print(f"  {t['name']}")

    # Claude session
    print("\n--- Claude: Cross-Server Incident Investigation ---")
    print("  User query: 'Our API error rate spiked. What is going on? Use the tools to investigate.'")
    print()

    # Build Anthropic tool list from gateway
    anthropic_tools = []
    for t in gateway.list_tools():
        anthropic_tools.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("inputSchema", {"type": "object", "properties": {}}),
        })

    client = anthropic.Anthropic()
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                "Our API error rate spiked recently. "
                "Investigate using the available tools: check the metrics, "
                "look at any related incidents, and find the relevant code change. "
                "Give me a clear summary of what happened and why."
            ),
        }
    ]

    for iteration in range(10):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=2048,
            tools=anthropic_tools,
            messages=messages,
        )

        for block in response.content:
            if hasattr(block, "text") and block.text:
                wrapped = textwrap.fill(block.text, width=80, subsequent_indent="  ")
                print(f"  Claude: {wrapped}")

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    ns = block.name.split("::")[0] if "::" in block.name else "?"
                    print(f"  [gateway -> {ns}] {block.name}({json.dumps(block.input)})")
                    result = gateway.call_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    print("\n=== Demo complete ===")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Lesson 03-14: MCP Ecosystem Capstone"
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Run as MCP server over stdio (for Claude Desktop connection)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run ecosystem tests only",
    )
    args = parser.parse_args()

    gateway = build_gateway()

    if args.server:
        asyncio.run(run_as_mcp_server(gateway))
    elif args.test:
        run_tests(gateway)
    else:
        run_demo(gateway)
        print()
        run_tests(gateway)
