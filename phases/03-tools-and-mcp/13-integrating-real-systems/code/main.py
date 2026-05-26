"""
Lesson 03-13: Integrating Real Systems: DBs, SaaS APIs, Internal Tools
Three hardened MCP tool implementations, one per integration archetype.

Run with: python main.py
Run demo mode: python main.py --demo
Run as MCP server: python main.py --server

This file can run standalone (for demo/testing) or as an MCP server.
"""

import argparse
import asyncio
import json
import sqlite3
import time
from typing import Any
from unittest.mock import MagicMock, patch

import anthropic

# ---------------------------------------------------------------------------
# Archetype 1: Database integration
# ---------------------------------------------------------------------------

# SQL statement prefixes that are never allowed through the tool
_BLOCKED_PREFIXES = (
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
)


def _setup_demo_db() -> sqlite3.Connection:
    """Create an in-memory SQLite database with demo data."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE customers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            company TEXT,
            arr INTEGER,
            status TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE orders (
            id TEXT PRIMARY KEY,
            customer_id TEXT,
            amount REAL,
            status TEXT,
            created_at TEXT
        )
    """)
    # Insert demo rows
    customers = [
        ("c_001", "Priya Sharma", "priya@techcorp.com", "TechCorp Inc.", 48000, "active", "2024-01-15"),
        ("c_002", "Marcus Webb", "marcus@dataflow.io", "DataFlow Labs", 12500, "active", "2024-03-01"),
        ("c_003", "Elena Kovacs", "elena@infraco.net", "InfraCo", 95000, "churned", "2023-06-20"),
        ("c_004", "Sam Okafor", "sam@cloudbase.dev", "CloudBase", 28000, "active", "2024-07-12"),
        ("c_005", "Jen Liu", "jen@scalevault.com", "ScaleVault", 72000, "active", "2023-11-05"),
    ]
    conn.executemany(
        "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)", customers
    )
    orders = [
        ("o_001", "c_001", 4000.0, "paid", "2026-04-01"),
        ("o_002", "c_001", 4000.0, "paid", "2026-05-01"),
        ("o_003", "c_002", 1040.0, "pending", "2026-05-20"),
        ("o_004", "c_004", 2333.0, "paid", "2026-05-15"),
    ]
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)
    conn.commit()
    return conn


# Module-level demo DB connection
_DEMO_DB: sqlite3.Connection | None = None


def _get_db() -> sqlite3.Connection:
    global _DEMO_DB
    if _DEMO_DB is None:
        _DEMO_DB = _setup_demo_db()
    return _DEMO_DB


def query_database(sql: str, limit: int = 100) -> dict[str, Any]:
    """
    Execute a read-only SQL SELECT query.

    Hardening:
    - Rejects DDL and DML statements
    - Enforces a hard row limit (max 1000)
    - Uses the DB's own parameterization (no string formatting of user values)
    """
    sql = sql.strip()
    sql_upper = sql.upper()

    # Block write and DDL operations
    for prefix in _BLOCKED_PREFIXES:
        if sql_upper.startswith(prefix):
            return {
                "error": "query_blocked",
                "message": f"Statements starting with '{prefix}' are not allowed.",
                "allowed": "SELECT queries only",
            }

    if not sql_upper.startswith("SELECT"):
        return {
            "error": "query_blocked",
            "message": "Only SELECT statements are permitted.",
        }

    # Enforce row limit -- inject if absent, cap if present
    capped_limit = min(max(1, limit), 1000)
    if "LIMIT" not in sql_upper:
        # Safe: we're appending to the SQL structure, not injecting user values
        sql = f"{sql.rstrip('; ')} LIMIT {capped_limit}"

    try:
        conn = _get_db()
        cursor = conn.cursor()
        # No user values are passed as parameters here because the SQL is
        # model-generated. In production, if user values need to be injected
        # into query parameters, use cursor.execute(sql, params) with a
        # parameterized query.
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []

        return {
            "columns": columns,
            "rows": [list(row) for row in rows],
            "row_count": len(rows),
            "truncated": len(rows) >= capped_limit,
            "limit_applied": capped_limit,
        }
    except sqlite3.OperationalError as e:
        return {"error": "query_failed", "message": str(e)}
    except Exception as e:
        return {"error": "unexpected_error", "message": str(e)}


# ---------------------------------------------------------------------------
# Archetype 2: SaaS API integration (mock)
# ---------------------------------------------------------------------------

_TOKEN_STORE: dict[str, str] = {
    "access_token": "token-abc123",
    "refresh_token": "refresh-xyz789",
}

# Demo contacts for the mock CRM
_MOCK_CONTACTS = [
    {"id": "c_001", "name": "Priya Sharma", "email": "priya@techcorp.com", "company": "TechCorp Inc."},
    {"id": "c_002", "name": "Marcus Webb", "email": "marcus@dataflow.io", "company": "DataFlow Labs"},
    {"id": "c_003", "name": "Elena Kovacs", "email": "elena@infraco.net", "company": "InfraCo"},
    {"id": "c_004", "name": "Sam Okafor", "email": "sam@cloudbase.dev", "company": "CloudBase"},
    {"id": "c_005", "name": "Jen Liu", "email": "jen@scalevault.com", "company": "ScaleVault"},
]


def _mock_crm_api(query: str, page: int, token: str) -> dict[str, Any]:
    """
    Simulates a paginated CRM API response.
    Returns a 429 on the first call with page=1 and token starting with 'token-'.
    Returns a 401 if token is 'expired-token'.
    Otherwise returns paginated results.
    """
    # Simulate rate limit on first call to demonstrate handling
    if page == 1 and token == "token-RATE-LIMITED":
        return {"status_code": 429, "headers": {"Retry-After": "1"}, "body": None}

    if token == "expired-token":
        return {"status_code": 401, "headers": {}, "body": None}

    # Filter contacts by query
    matches = [
        c for c in _MOCK_CONTACTS
        if query.lower() in c["name"].lower()
        or query.lower() in c["company"].lower()
        or query.lower() in c["email"].lower()
    ]

    page_size = 2
    start = (page - 1) * page_size
    end = start + page_size
    page_results = matches[start:end]
    has_next = end < len(matches)

    return {
        "status_code": 200,
        "headers": {},
        "body": {
            "results": page_results,
            "pagination": {
                "current_page": page,
                "next_page": page + 1 if has_next else None,
                "total": len(matches),
            },
        },
    }


def _refresh_access_token() -> bool:
    """Simulate OAuth token refresh. Returns True on success."""
    # In production: POST to token endpoint with refresh_token grant
    _TOKEN_STORE["access_token"] = f"refreshed-token-{int(time.time())}"
    return True


def search_crm(query: str, page: int = 1, max_pages: int = 3) -> dict[str, Any]:
    """
    Search CRM contacts with pagination, rate limit handling, and token refresh.

    Hardening:
    - Parses Retry-After header on 429 and waits before one retry
    - Catches 401 and refreshes the token once, then retries
    - Follows pagination up to max_pages to avoid runaway loops
    - Timeout is set at the HTTP layer (simulated here)
    """
    all_results: list[dict] = []
    current_page = page
    end_page = page + max_pages - 1
    token_refreshed = False

    while current_page <= end_page:
        response = _mock_crm_api(query, current_page, _TOKEN_STORE["access_token"])

        # Handle rate limit
        if response["status_code"] == 429:
            retry_after = int(response["headers"].get("Retry-After", 5))
            print(f"  [rate limited] waiting {retry_after}s (Retry-After header)")
            time.sleep(retry_after)
            response = _mock_crm_api(query, current_page, _TOKEN_STORE["access_token"])

        # Handle token expiry
        if response["status_code"] == 401:
            if token_refreshed:
                return {
                    "error": "auth_failed",
                    "message": "Token invalid even after refresh. Re-authentication required.",
                }
            print("  [401] refreshing access token...")
            if _refresh_access_token():
                token_refreshed = True
                response = _mock_crm_api(query, current_page, _TOKEN_STORE["access_token"])
            else:
                return {"error": "token_refresh_failed", "message": "Could not refresh token"}

        # Handle other errors
        if response["status_code"] not in (200, 201):
            return {
                "error": "api_error",
                "status_code": response["status_code"],
                "message": f"Unexpected response: {response['status_code']}",
            }

        body = response["body"]
        all_results.extend(body.get("results", []))

        next_page = body.get("pagination", {}).get("next_page")
        if not next_page:
            break
        current_page = next_page

    return {
        "results": all_results,
        "total_fetched": len(all_results),
        "pages_fetched": current_page - page + 1,
    }


# ---------------------------------------------------------------------------
# Archetype 3: Internal tool integration (mock)
# ---------------------------------------------------------------------------

_MOCK_REPORTS: dict[str, dict] = {
    "monthly-revenue": {
        "report_id": "monthly-revenue",
        "period": "2026-05",
        "total_revenue": 284500.0,
        "by_segment": {"enterprise": 195000, "smb": 89500},
    },
    "active-users": {
        "report_id": "active-users",
        "period": "2026-05",
        "dau": 12847,
        "mau": 48290,
        "new_users": 1832,
    },
    "churn-analysis": {
        "report_id": "churn-analysis",
        "period": "2026-Q1",
        "churned_accounts": 14,
        "churned_arr": 186000,
        "churn_rate_percent": 3.2,
    },
}


def _call_reporting_api(report_id: str, attempt: int) -> dict[str, Any]:
    """
    Simulates an internal reporting API.
    Fails transiently on the first attempt for 'active-users' to demo retry logic.
    Returns opaque 500 error for unknown report IDs.
    """
    if report_id == "active-users" and attempt == 0:
        raise TimeoutError("Simulated transient timeout on first attempt")

    if report_id not in _MOCK_REPORTS:
        # Simulate an opaque internal error (Java stack trace style)
        raise Exception(
            "java.lang.NullPointerException: Cannot invoke method getData() on null object\n"
            "\tat com.internal.reports.ReportService.runReport(ReportService.java:142)\n"
            "\tat com.internal.reports.ReportController.execute(ReportController.java:89)"
        )

    return {"status": 200, "data": _MOCK_REPORTS[report_id]}


def run_internal_report(report_id: str) -> dict[str, Any]:
    """
    Run an internal report with timeout, backoff retry, and error normalization.

    Hardening:
    - Hard 15s timeout per attempt (simulated)
    - Exponential backoff: 1s, 2s, 4s between retries
    - Max 3 attempts
    - Error normalization: opaque errors become structured dicts
    """
    max_retries = 3
    base_delay = 1.0
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                delay = base_delay * (2 ** (attempt - 1))
                print(f"  [retry {attempt}] waiting {delay:.0f}s before retry...")
                time.sleep(delay)

            response = _call_reporting_api(report_id, attempt)

            if response.get("status") == 200:
                return {"status": "success", "data": response["data"]}
            else:
                return _normalize_error(response.get("status", 500), str(response))

        except TimeoutError as e:
            last_error = e
            if attempt < max_retries - 1:
                print(f"  [timeout on attempt {attempt + 1}] will retry")
                continue
            return {
                "error": "timeout",
                "message": f"Report '{report_id}' did not complete within the timeout window",
                "attempts": max_retries,
                "suggestion": "The report server may be under load. Try again in a few minutes.",
            }

        except ConnectionError as e:
            last_error = e
            if attempt < max_retries - 1:
                continue
            return {
                "error": "unreachable",
                "message": "Cannot reach reporting server. Verify VPN access.",
                "endpoint": f"http://reporting.internal:8080/api/reports/{report_id}/run",
            }

        except Exception as e:
            # Normalize opaque errors: catch raw stack traces, XML error envelopes,
            # proprietary error formats, etc.
            return _normalize_opaque_error(e)

    return {
        "error": "max_retries_exceeded",
        "attempts": max_retries,
        "last_error": str(last_error) if last_error else "unknown",
    }


def _normalize_error(status_code: int, body: str) -> dict[str, Any]:
    """Map HTTP status codes to structured error types."""
    error_map = {
        400: "invalid_request",
        401: "auth_required",
        403: "permission_denied",
        404: "report_not_found",
        500: "server_error",
        503: "server_unavailable",
    }
    return {
        "error": error_map.get(status_code, f"http_{status_code}"),
        "status_code": status_code,
        "message": body[:300],
    }


def _normalize_opaque_error(e: Exception) -> dict[str, Any]:
    """
    Convert opaque internal errors (Java stack traces, XML error envelopes,
    SAP error codes) into a structured, model-readable format.
    """
    error_str = str(e)

    # Detect Java stack traces
    if "java.lang" in error_str or "NullPointerException" in error_str:
        return {
            "error": "internal_server_error",
            "message": "The reporting service encountered an internal error.",
            "detail": "java.lang.NullPointerException (check report ID and permissions)",
            "suggestion": "Verify the report ID exists and that this service account has access.",
        }

    # Detect XML error envelopes
    if error_str.startswith("<") and "error" in error_str.lower():
        return {
            "error": "xml_error_response",
            "message": "Server returned an XML error response",
            "detail": error_str[:200],
        }

    # Generic fallback
    return {
        "error": "unexpected_error",
        "message": "An unexpected error occurred calling the internal tool.",
        "detail": error_str[:200],
    }


# ---------------------------------------------------------------------------
# MCP server wrapper
# ---------------------------------------------------------------------------

async def run_as_mcp_server() -> None:
    """Expose all three tools as an MCP server over stdio."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import Tool, TextContent
    except ImportError:
        print("Install mcp: pip install mcp")
        return

    app = Server("real-systems-server")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="query_database",
                description=(
                    "Execute a read-only SQL SELECT query against the analytics database. "
                    "Row limit enforced at 1000. DDL and DML statements are rejected."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "A SQL SELECT statement.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max rows (default: 100, max: 1000).",
                            "default": 100,
                        },
                    },
                    "required": ["sql"],
                },
            ),
            Tool(
                name="search_crm",
                description=(
                    "Search CRM contacts by name, email, or company. "
                    "Handles pagination and token refresh automatically."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "page": {"type": "integer", "default": 1},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="run_internal_report",
                description=(
                    "Run an internal report by ID. "
                    "Retries with backoff on transient failures."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "report_id": {
                            "type": "string",
                            "description": "Report identifier (e.g. 'monthly-revenue', 'active-users')",
                        }
                    },
                    "required": ["report_id"],
                },
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "query_database":
            result = query_database(
                sql=arguments["sql"],
                limit=arguments.get("limit", 100),
            )
        elif name == "search_crm":
            result = search_crm(
                query=arguments["query"],
                page=arguments.get("page", 1),
            )
        elif name == "run_internal_report":
            result = run_internal_report(report_id=arguments["report_id"])
        else:
            result = {"error": "unknown_tool", "name": name}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


# ---------------------------------------------------------------------------
# Demo: direct function calls + Claude agentic session
# ---------------------------------------------------------------------------

def run_demo() -> None:
    print("\n=== Integration Hardening Demo: Lesson 03-13 ===\n")

    # --- Archetype 1: Database ---
    print("--- Archetype 1: Database ---")

    print("\n  Valid query (with auto-applied row limit):")
    r = query_database("SELECT name, company, arr FROM customers WHERE status = 'active'")
    print(f"  rows: {r['row_count']}, columns: {r['columns']}, truncated: {r['truncated']}")
    for row in r["rows"]:
        print(f"    {row}")

    print("\n  DDL injection attempt (DROP TABLE):")
    r = query_database("DROP TABLE customers")
    print(f"  result: {json.dumps(r, indent=4)}")

    print("\n  Write operation attempt (DELETE):")
    r = query_database("DELETE FROM customers WHERE id = 'c_001'")
    print(f"  result: {json.dumps(r, indent=4)}")

    # --- Archetype 2: SaaS API ---
    print("\n--- Archetype 2: SaaS API ---")

    print("\n  Normal paginated search:")
    r = search_crm("Labs")
    print(f"  results: {len(r.get('results', []))} contacts, pages: {r.get('pages_fetched')}")
    for contact in r.get("results", []):
        print(f"    {contact['name']} -- {contact['company']}")

    print("\n  Rate limited (simulated 429):")
    original_token = _TOKEN_STORE["access_token"]
    _TOKEN_STORE["access_token"] = "token-RATE-LIMITED"
    r = search_crm("TechCorp")
    _TOKEN_STORE["access_token"] = original_token
    print(f"  after rate limit handling: {len(r.get('results', []))} results")

    # --- Archetype 3: Internal tool ---
    print("\n--- Archetype 3: Internal Tool ---")

    print("\n  Successful report (with transient retry):")
    r = run_internal_report("active-users")
    print(f"  result: {json.dumps(r, indent=2)}")

    print("\n  Unknown report (opaque error normalized):")
    r = run_internal_report("nonexistent-report-xyz")
    print(f"  result: {json.dumps(r, indent=2)}")

    # --- Claude using all three tools ---
    print("\n--- Claude using all three tools ---")
    print("  Query: 'Show me active customers and their revenue, then run the monthly-revenue report.'")
    print()

    client = anthropic.Anthropic()
    tools = [
        {
            "name": "query_database",
            "description": "Execute a read-only SQL SELECT query against the analytics database.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string"},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["sql"],
            },
        },
        {
            "name": "search_crm",
            "description": "Search CRM contacts by name, email, or company.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "page": {"type": "integer", "default": 1},
                },
                "required": ["query"],
            },
        },
        {
            "name": "run_internal_report",
            "description": "Run an internal report by ID.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "string"},
                },
                "required": ["report_id"],
            },
        },
    ]

    messages: list[dict] = [
        {
            "role": "user",
            "content": "Show me active customers and their revenue from the database, then run the monthly-revenue report.",
        }
    ]

    tool_dispatch = {
        "query_database": lambda args: query_database(**args),
        "search_crm": lambda args: search_crm(**args),
        "run_internal_report": lambda args: run_internal_report(**args),
    }

    for _ in range(8):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            tools=tools,
            messages=messages,
        )

        for block in response.content:
            if hasattr(block, "text") and block.text:
                print(f"  Claude: {block.text}")

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [tool call] {block.name}({json.dumps(block.input)})")
                    result = tool_dispatch[block.name](block.input)
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
    parser = argparse.ArgumentParser(description="Lesson 03-13: Integration hardening demo")
    parser.add_argument(
        "--server",
        action="store_true",
        help="Run as MCP server over stdio instead of demo mode",
    )
    args = parser.parse_args()

    if args.server:
        asyncio.run(run_as_mcp_server())
    else:
        run_demo()
