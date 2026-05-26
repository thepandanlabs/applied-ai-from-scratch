---
name: skill-real-system-integration
description: Three integration patterns with hardening templates and failure mode checklists for database, SaaS API, and internal tool integrations
version: "1.0"
phase: "03"
lesson: "13"
tags: [mcp, integration, database, saas-api, internal-tools, hardening]
---

# Real System Integration Skill

Use this artifact as a starting point for any MCP tool that integrates with an external system. Copy the pattern for your archetype, work through the hardening checklist, and do not ship until every item is checked.

---

## Pattern 1: Database Integration

### Hardening Checklist

```
DATABASE HARDENING
==================
[ ] Parameterized queries only -- no f-string or .format() with user values in SQL
[ ] Read-only connection -- separate DB user with SELECT only, no INSERT/UPDATE/DELETE
[ ] Row limit enforced in code -- max 1000 rows, default 100, configurable but capped
[ ] DDL/DML rejection -- block INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE at tool layer
[ ] Schema exposure -- provide a describe_schema tool so the model uses real table/column names
```

### Failure Mode Reference

| Failure | Symptom | Fix |
|---------|---------|-----|
| SQL injection | User input changes query structure | Parameterized queries, never string concat |
| Schema unknowns | `relation "X" does not exist` errors | Inject schema in system prompt or provide describe_schema tool |
| Result explosion | Context window overflow, timeout | Hard row limit in code, not in prompt |
| Write operation | Model deletes or updates production data | Read-only DB user + DDL/DML rejection |
| Slow query | Tool hangs, agent times out | Statement timeout at DB level (SET statement_timeout) |

### Code Template

```python
_BLOCKED_PREFIXES = (
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE",
    "ALTER", "TRUNCATE", "GRANT", "REVOKE",
)

def query_database(sql: str, limit: int = 100) -> dict:
    sql = sql.strip()
    sql_upper = sql.upper()

    for prefix in _BLOCKED_PREFIXES:
        if sql_upper.startswith(prefix):
            return {
                "error": "query_blocked",
                "message": f"'{prefix}' statements are not allowed. SELECT only.",
            }

    capped_limit = min(max(1, limit), 1000)
    if "LIMIT" not in sql_upper:
        sql = f"{sql.rstrip('; ')} LIMIT {capped_limit}"

    try:
        # Use read-only DB user in connection string
        conn = get_readonly_connection()
        cursor = conn.cursor()
        cursor.execute(sql)  # No user values -- model generates the SQL
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description] if cursor.description else []
        return {
            "columns": columns,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": len(rows) >= capped_limit,
        }
    except Exception as e:
        return {"error": "query_failed", "message": str(e)}
```

---

## Pattern 2: SaaS API Integration

### Hardening Checklist

```
SAAS API HARDENING
==================
[ ] Rate limit handling -- parse Retry-After header on 429, sleep, retry once
[ ] Pagination -- follow next_page cursors up to a configured max page count (default: 3)
[ ] Token refresh -- catch 401, refresh once, retry; fail loudly on second 401
[ ] Timeout -- connection timeout 5s, read timeout 30s; never let requests hang
[ ] Error normalization -- map status codes to structured error dicts
```

### Failure Mode Reference

| Failure | Symptom | Fix |
|---------|---------|-----|
| Rate limit ignored | 429 loop, eventually blocked | Parse Retry-After, sleep, single retry |
| Pagination skipped | Tool returns only first 20 records silently | Follow next_page cursor up to max_pages |
| Token expiry | 401 mid-session, tool fails | Catch 401, refresh, retry once |
| No timeout | Tool hangs on slow API, agent blocks | Set (connect_timeout, read_timeout) in requests |
| Raw HTTP errors | Model sees `400 Bad Request` with no context | Normalize to {"error": "type", "message": "..."} |

### Code Template

```python
def call_saas_api(query: str, page: int = 1, max_pages: int = 3) -> dict:
    all_results = []
    current_page = page
    end_page = page + max_pages - 1
    token_refreshed = False

    while current_page <= end_page:
        try:
            resp = requests.get(
                f"{BASE_URL}/search",
                params={"q": query, "page": current_page},
                headers={"Authorization": f"Bearer {get_token()}"},
                timeout=(5, 30),
            )
        except requests.Timeout:
            return {"error": "timeout", "message": "API did not respond within 30s"}
        except requests.ConnectionError as e:
            return {"error": "connection_failed", "message": str(e)}

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            time.sleep(retry_after)
            continue  # retry same page

        if resp.status_code == 401 and not token_refreshed:
            if refresh_token():
                token_refreshed = True
                continue
            return {"error": "auth_failed", "message": "Token refresh failed"}

        if resp.status_code == 401:
            return {"error": "auth_failed", "message": "Invalid token after refresh"}

        if not resp.ok:
            return {"error": f"http_{resp.status_code}", "message": resp.text[:300]}

        data = resp.json()
        all_results.extend(data.get("results", []))
        next_page = data.get("pagination", {}).get("next_page")
        if not next_page:
            break
        current_page = next_page

    return {"results": all_results, "total_fetched": len(all_results)}
```

---

## Pattern 3: Internal Tool Integration

### Hardening Checklist

```
INTERNAL TOOL HARDENING
========================
[ ] Timeout enforcement -- hard timeout 15-30s per attempt; never block indefinitely
[ ] Exponential backoff retry -- delays: 1s, 2s, 4s; max 3 attempts
[ ] Error normalization -- catch stack traces/XML/custom formats, return structured dict
[ ] Network check -- fast failure with clear message if endpoint is unreachable
[ ] Auth protocol testing -- test auth in the real network environment (VPN, internal subnet)
```

### Failure Mode Reference

| Failure | Symptom | Fix |
|---------|---------|-----|
| No timeout | Tool hangs 30+ seconds, agent unresponsive | Hard timeout per attempt (requests timeout param) |
| No retry | Transient failure kills the tool call | Exponential backoff, max 3 attempts |
| Opaque errors | Java stack trace confuses the model | Normalize to {"error": "type", "message": "..."} |
| Network unreachable | `ConnectionError` with no context | Catch, return {"error": "unreachable", "message": "Check VPN"} |
| Wrong auth protocol | 401 or 403 with no explanation | Test auth end-to-end in real environment before shipping |

### Code Template

```python
def call_internal_tool(params: dict) -> dict:
    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                time.sleep(base_delay * (2 ** (attempt - 1)))

            resp = requests.post(
                INTERNAL_ENDPOINT,
                json=params,
                headers={"Authorization": f"Bearer {SERVICE_TOKEN}"},
                timeout=15,
            )

            if resp.status_code == 200:
                try:
                    return {"status": "success", "data": resp.json()}
                except Exception:
                    return {"status": "success", "data": resp.text[:2000]}

            return normalize_http_error(resp)

        except requests.Timeout:
            if attempt < max_retries - 1:
                continue
            return {"error": "timeout", "message": "Tool did not respond within 15s"}

        except requests.ConnectionError:
            if attempt < max_retries - 1:
                continue
            return {"error": "unreachable", "message": "Cannot reach internal endpoint. Check VPN."}

        except Exception as e:
            return normalize_opaque_error(e)

    return {"error": "max_retries_exceeded", "attempts": max_retries}


def normalize_http_error(resp) -> dict:
    codes = {400: "invalid_request", 401: "auth_required", 403: "permission_denied",
             404: "not_found", 500: "server_error", 503: "unavailable"}
    try:
        body = resp.json()
        msg = body.get("message") or str(body)[:200]
    except Exception:
        msg = resp.text[:200] or f"HTTP {resp.status_code}"
    return {"error": codes.get(resp.status_code, f"http_{resp.status_code}"), "message": msg}


def normalize_opaque_error(e: Exception) -> dict:
    s = str(e)
    if "java.lang" in s:
        return {"error": "internal_server_error", "message": "Java exception on server", "detail": s[:200]}
    return {"error": "unexpected_error", "message": s[:200]}
```

---

## Pre-Ship Integration Review Checklist

Before marking any integration "production ready":

```
PRE-SHIP REVIEW
===============
[ ] Tested in the real environment (not just localhost or staging)
[ ] All error paths return structured {"error": ..., "message": ...} dicts
[ ] No user values are string-concatenated into SQL or shell commands
[ ] Timeout is set at the HTTP/DB layer, not just in the prompt
[ ] Rate limit and 401 handling tested with mock responses
[ ] Row/result limits are enforced in code, not in the system prompt
[ ] Error messages contain enough context for the model to explain the failure
[ ] No credentials are hardcoded -- all secrets from environment variables
```
