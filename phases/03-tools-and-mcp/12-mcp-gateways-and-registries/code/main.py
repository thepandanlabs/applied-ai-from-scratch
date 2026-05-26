"""
Lesson 03-12: MCP Gateways and Registries
A minimal MCP gateway that aggregates tools from multiple upstream servers.

This demo uses in-process mock servers instead of real network connections.
The routing, discovery, and config-loading logic is production-representative.

Run with: python main.py
Run with verbose output: python main.py --verbose
"""

import argparse
import json
import textwrap
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic

# ---------------------------------------------------------------------------
# Mock upstream server infrastructure
# ---------------------------------------------------------------------------

@dataclass
class MockServer:
    """
    Represents a remote MCP server for demo purposes.
    In production, this would be a real network connection to an MCP server.
    """
    name: str
    namespace: str
    tool_schemas: list[dict]
    handler: Callable[[str, dict[str, Any]], Any]


def make_crm_server() -> MockServer:
    """CRM server: contacts and account management."""

    def handle(tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "get_contact":
            contact_id = args.get("id", "unknown")
            return {
                "id": contact_id,
                "name": "Priya Sharma",
                "email": "priya@techcorp.com",
                "company": "TechCorp Inc.",
                "stage": "active_customer",
                "arr": 48000,
            }
        elif tool_name == "search_contacts":
            return {
                "contacts": [
                    {"id": "c_001", "name": "Priya Sharma", "company": "TechCorp Inc."},
                    {"id": "c_002", "name": "Marcus Webb", "company": "DataFlow Labs"},
                ],
                "total": 2,
                "query": args.get("query", ""),
            }
        elif tool_name == "create_contact":
            return {"id": "c_new_001", "status": "created", **args}
        else:
            return {"error": f"Unknown CRM tool: {tool_name}"}

    return MockServer(
        name="crm-server",
        namespace="crm",
        tool_schemas=[
            {
                "name": "get_contact",
                "description": "Retrieve a CRM contact by ID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"id": {"type": "string", "description": "Contact ID"}},
                    "required": ["id"],
                },
            },
            {
                "name": "search_contacts",
                "description": "Search CRM contacts by name, email, or company.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "create_contact",
                "description": "Create a new CRM contact.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                        "company": {"type": "string"},
                    },
                    "required": ["name", "email"],
                },
            },
        ],
        handler=handle,
    )


def make_warehouse_server() -> MockServer:
    """Data warehouse server: SQL query execution and schema discovery."""

    def handle(tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "run_query":
            sql = args.get("sql", "")
            return {
                "columns": ["customer_id", "total_revenue", "last_purchase"],
                "rows": [
                    ["c_001", 48000, "2026-04-15"],
                    ["c_002", 12500, "2026-03-22"],
                ],
                "row_count": 2,
                "query_time_ms": 87,
                "sql": sql,
            }
        elif tool_name == "list_tables":
            return {
                "tables": ["customers", "orders", "products", "events", "sessions"],
                "schema": "analytics",
            }
        elif tool_name == "describe_table":
            return {
                "table": args.get("table"),
                "columns": [
                    {"name": "id", "type": "varchar", "nullable": False},
                    {"name": "created_at", "type": "timestamp", "nullable": False},
                    {"name": "total_revenue", "type": "numeric(12,2)", "nullable": True},
                ],
            }
        else:
            return {"error": f"Unknown warehouse tool: {tool_name}"}

    return MockServer(
        name="warehouse-server",
        namespace="warehouse",
        tool_schemas=[
            {
                "name": "run_query",
                "description": "Execute a read-only SQL query against the data warehouse.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "SQL SELECT statement"},
                        "limit": {"type": "integer", "default": 100, "maximum": 1000},
                    },
                    "required": ["sql"],
                },
            },
            {
                "name": "list_tables",
                "description": "List all tables in the analytics schema.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "describe_table",
                "description": "Get column definitions for a specific table.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"table": {"type": "string"}},
                    "required": ["table"],
                },
            },
        ],
        handler=handle,
    )


def make_tickets_server() -> MockServer:
    """Ticketing server: issue tracking and support ticket management."""

    def handle(tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "create_ticket":
            return {
                "id": "TKT-8841",
                "status": "open",
                "title": args.get("title"),
                "priority": args.get("priority", "medium"),
                "created_at": "2026-05-25T10:30:00Z",
            }
        elif tool_name == "get_ticket":
            return {
                "id": args.get("id"),
                "title": "API rate limit exceeded for warehouse queries",
                "status": "in_progress",
                "priority": "high",
                "assignee": "eng-platform",
                "created_at": "2026-05-24T08:15:00Z",
                "notes": ["Investigating root cause", "Rate limit increased temporarily"],
            }
        elif tool_name == "list_tickets":
            return {
                "tickets": [
                    {"id": "TKT-8841", "title": "API rate limit issue", "status": "open"},
                    {"id": "TKT-8840", "title": "CRM sync delay", "status": "in_progress"},
                ],
                "total": 2,
                "status_filter": args.get("status"),
            }
        elif tool_name == "add_comment":
            return {
                "ticket_id": args.get("ticket_id"),
                "comment_id": "cmt_001",
                "status": "added",
            }
        else:
            return {"error": f"Unknown tickets tool: {tool_name}"}

    return MockServer(
        name="tickets-server",
        namespace="tickets",
        tool_schemas=[
            {
                "name": "create_ticket",
                "description": "Create a new support or engineering ticket.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "get_ticket",
                "description": "Retrieve a ticket by ID, including notes and history.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                },
            },
            {
                "name": "list_tickets",
                "description": "List tickets filtered by status.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["open", "in_progress", "resolved", "all"]},
                        "limit": {"type": "integer", "default": 20},
                    },
                },
            },
            {
                "name": "add_comment",
                "description": "Add a comment to an existing ticket.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "string"},
                        "comment": {"type": "string"},
                    },
                    "required": ["ticket_id", "comment"],
                },
            },
        ],
        handler=handle,
    )


# ---------------------------------------------------------------------------
# Gateway core
# ---------------------------------------------------------------------------

class MCPGateway:
    """
    A minimal MCP gateway that aggregates tools from multiple upstream servers.

    Responsibilities:
    - Discovery: exposes a unified tools/list across all upstream servers
    - Routing: dispatches tools/call to the correct server by namespace prefix
    - Error handling: returns structured errors for unknown namespaces and
      unavailable servers
    """

    def __init__(self, servers: list[MockServer]) -> None:
        # Index by namespace for O(1) routing
        self._servers: dict[str, MockServer] = {s.namespace: s for s in servers}
        self._health: dict[str, bool] = {s.namespace: True for s in servers}

    def list_tools(self) -> list[dict]:
        """
        Aggregate tool schemas from all healthy upstream servers.
        Prefix each tool name with its server namespace.
        """
        all_tools = []
        for namespace, server in self._servers.items():
            if not self._health[namespace]:
                # Omit tools from unhealthy servers rather than letting clients
                # discover tools they cannot call.
                continue
            for schema in server.tool_schemas:
                prefixed = dict(schema)
                prefixed["name"] = f"{namespace}::{schema['name']}"
                prefixed["description"] = (
                    f"[{server.name}] {schema.get('description', '')}"
                )
                all_tools.append(prefixed)
        return all_tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Route a prefixed tool call to the correct upstream server.

        Expected format: "namespace::tool_name"
        """
        if "::" not in tool_name:
            return {
                "error": "invalid_tool_name",
                "message": (
                    f"Tool name '{tool_name}' must use format 'namespace::tool_name'. "
                    f"Available namespaces: {', '.join(self._servers.keys())}"
                ),
            }

        namespace, raw_name = tool_name.split("::", 1)

        if namespace not in self._servers:
            return {
                "error": "unknown_namespace",
                "message": f"Namespace '{namespace}' not found.",
                "available_namespaces": list(self._servers.keys()),
            }

        if not self._health[namespace]:
            return {
                "error": "server_unavailable",
                "server": self._servers[namespace].name,
                "namespace": namespace,
                "retry_after_seconds": 60,
            }

        server = self._servers[namespace]
        return server.handler(raw_name, arguments)

    def set_health(self, namespace: str, healthy: bool) -> None:
        """Mark a server as healthy or unhealthy (for testing graceful degradation)."""
        if namespace in self._health:
            self._health[namespace] = healthy

    def status(self) -> dict:
        """Return health status of all upstream servers."""
        return {
            "servers": [
                {
                    "name": server.name,
                    "namespace": ns,
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


# ---------------------------------------------------------------------------
# Demo: gateway with Claude using tools
# ---------------------------------------------------------------------------

def run_gateway_demo(verbose: bool = False) -> None:
    """
    Demonstrate the gateway:
    1. List all aggregated tools
    2. Route several tool calls
    3. Show graceful degradation when a server is unavailable
    4. Run a Claude session that uses tools across multiple namespaces
    """
    print("\n=== MCP Gateway Demo: Lesson 03-12 ===\n")

    # Build the gateway from three mock upstream servers
    gateway = MCPGateway(
        servers=[
            make_crm_server(),
            make_warehouse_server(),
            make_tickets_server(),
        ]
    )

    # --- 1. Discovery ---
    print("--- Gateway Status ---")
    status = gateway.status()
    for s in status["servers"]:
        health_str = "healthy" if s["healthy"] else "UNAVAILABLE"
        print(f"  {s['namespace']:12} -> {s['name']:22} [{health_str}] ({s['tool_count']} tools)")
    print(f"\nTotal tools available: {status['total_tools']}")

    print("\n--- Aggregated tools/list ---")
    tools = gateway.list_tools()
    for t in tools:
        print(f"  {t['name']}")

    # --- 2. Routing ---
    print("\n--- Tool call routing ---")
    calls = [
        ("crm::get_contact", {"id": "c_001"}),
        ("warehouse::list_tables", {}),
        ("tickets::create_ticket", {"title": "Gateway routing test", "priority": "low"}),
    ]
    for tool_name, args in calls:
        result = gateway.call_tool(tool_name, args)
        print(f"\n  {tool_name}")
        if verbose:
            print(f"  args: {json.dumps(args)}")
        print(f"  result: {json.dumps(result, indent=4)}")

    # --- 3. Error cases ---
    print("\n--- Error handling ---")
    error_cases = [
        ("search_contacts", {"query": "tech"}),  # missing namespace
        ("unknown::get_thing", {}),              # unknown namespace
    ]
    for tool_name, args in error_cases:
        result = gateway.call_tool(tool_name, args)
        print(f"\n  {tool_name}")
        print(f"  error response: {json.dumps(result, indent=4)}")

    # --- 4. Graceful degradation ---
    print("\n--- Graceful degradation (CRM server goes down) ---")
    gateway.set_health("crm", False)
    tools_after = gateway.list_tools()
    crm_tools = [t for t in tools_after if t["name"].startswith("crm::")]
    print(f"  CRM tools in list after server down: {len(crm_tools)} (expected: 0)")
    unavailable_result = gateway.call_tool("crm::get_contact", {"id": "c_001"})
    print(f"  Call to unavailable server: {json.dumps(unavailable_result, indent=4)}")
    gateway.set_health("crm", True)  # restore for the Claude demo

    # --- 5. Claude using the gateway ---
    print("\n--- Claude using the gateway ---")
    print("  Asking Claude: 'Search for contacts at TechCorp and check any open tickets.'")
    print()

    # Convert gateway tools to Anthropic tool format
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
            "content": "Search for contacts at TechCorp and check any open tickets.",
        }
    ]

    # Agentic loop: let Claude call tools until it has a final answer
    for _ in range(6):  # max iterations to prevent infinite loops
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            tools=anthropic_tools,
            messages=messages,
        )

        if verbose:
            print(f"  [stop_reason: {response.stop_reason}]")

        # Collect text output
        for block in response.content:
            if hasattr(block, "text") and block.text:
                print(f"  Claude: {textwrap.fill(block.text, width=80, subsequent_indent='          ')}")

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            # Process all tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    print(f"  [gateway routes] {tool_name}({json.dumps(tool_input)})")
                    result = gateway.call_tool(tool_name, tool_input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })

            # Append assistant turn and tool results
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

    print("\n=== Demo complete ===")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lesson 03-12: MCP Gateway demo")
    parser.add_argument("--verbose", action="store_true", help="Show raw arguments and stop reasons")
    args = parser.parse_args()

    run_gateway_demo(verbose=args.verbose)
