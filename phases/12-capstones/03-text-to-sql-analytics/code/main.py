"""
Capstone 12-03: Talk-to-Your-Data Analytics App (Text-to-SQL)
Phase 12: Capstones

A FastAPI service that converts natural language to SQL over a mock sales database.
Features: schema injection, structured output, deterministic safety validator,
safe execution with timeout, plain-English result explanation.

Usage:
    uv pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...

    # Run service
    uvicorn main:app --reload --port 8000

    # Query
    curl -X POST http://localhost:8000/query \
         -H "Content-Type: application/json" \
         -d '{"question": "What are the top 5 customers by total revenue?"}'

    # CLI demo
    python main.py
"""

import json
import logging
import re
import signal
import sqlite3
import contextlib
import time
from typing import Any

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-3-5-haiku-20241022"
ROW_LIMIT = 500
QUERY_TIMEOUT_SECONDS = 5
MAX_TOKENS_SQL = 512
MAX_TOKENS_EXPLAIN = 256

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("text-to-sql")

# ---------------------------------------------------------------------------
# Database setup: mock sales database
# ---------------------------------------------------------------------------

def create_database() -> sqlite3.Connection:
    """Create and seed in-memory mock sales database."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.executescript("""
    CREATE TABLE customers (
        customer_id   INTEGER PRIMARY KEY,
        name          TEXT NOT NULL,
        email         TEXT,
        region        TEXT,
        segment       TEXT  -- 'Enterprise', 'SMB', 'Consumer'
    );

    CREATE TABLE products (
        product_id    INTEGER PRIMARY KEY,
        name          TEXT NOT NULL,
        category      TEXT,  -- 'Software', 'Hardware', 'Services'
        unit_price    REAL
    );

    CREATE TABLE sales_reps (
        rep_id        INTEGER PRIMARY KEY,
        name          TEXT NOT NULL,
        region        TEXT,
        quota         REAL  -- annual quota in USD
    );

    CREATE TABLE regions (
        region_id     INTEGER PRIMARY KEY,
        region_name   TEXT NOT NULL,
        country       TEXT
    );

    CREATE TABLE orders (
        order_id      INTEGER PRIMARY KEY,
        customer_id   INTEGER REFERENCES customers(customer_id),
        product_id    INTEGER REFERENCES products(product_id),
        rep_id        INTEGER REFERENCES sales_reps(rep_id),
        order_date    TEXT,   -- ISO format: YYYY-MM-DD
        quantity      INTEGER,
        total_amount  REAL,
        status        TEXT    -- 'completed', 'pending', 'cancelled'
    );
    """)

    # Seed customers
    conn.executemany(
        "INSERT INTO customers VALUES (?, ?, ?, ?, ?)",
        [
            (1, "Acme Corp",        "acme@example.com",     "North",  "Enterprise"),
            (2, "Globex Inc",       "globex@example.com",   "South",  "Enterprise"),
            (3, "Initech",          "initech@example.com",  "East",   "SMB"),
            (4, "Umbrella Ltd",     "umbrella@example.com", "West",   "SMB"),
            (5, "Wonka Industries", "wonka@example.com",    "North",  "SMB"),
            (6, "Dunder Mifflin",   "dm@example.com",       "East",   "SMB"),
            (7, "Vandelay Ind",     "vandelay@example.com", "South",  "Consumer"),
            (8, "Rekall Corp",      "rekall@example.com",   "West",   "Consumer"),
        ],
    )

    # Seed products
    conn.executemany(
        "INSERT INTO products VALUES (?, ?, ?, ?)",
        [
            (1, "AI Platform Pro",    "Software",  4999.00),
            (2, "Data Analytics Kit", "Software",  1200.00),
            (3, "GPU Cluster Node",   "Hardware",  8500.00),
            (4, "Support Contract",   "Services",   750.00),
            (5, "Training Bundle",    "Services",   499.00),
        ],
    )

    # Seed sales reps
    conn.executemany(
        "INSERT INTO sales_reps VALUES (?, ?, ?, ?)",
        [
            (1, "Sarah Kim",    "North",  250000.00),
            (2, "James Park",   "South",  200000.00),
            (3, "Maria Lopez",  "East",   180000.00),
            (4, "Tom Chen",     "West",   220000.00),
        ],
    )

    # Seed regions
    conn.executemany(
        "INSERT INTO regions VALUES (?, ?, ?)",
        [
            (1, "North", "USA"),
            (2, "South", "USA"),
            (3, "East",  "USA"),
            (4, "West",  "USA"),
        ],
    )

    # Seed orders
    orders_data = [
        (1,  1, 1, 1, "2025-01-15", 1,  4999.00, "completed"),
        (2,  1, 2, 1, "2025-01-22", 2,  2400.00, "completed"),
        (3,  2, 3, 2, "2025-02-03", 1,  8500.00, "completed"),
        (4,  2, 1, 2, "2025-02-14", 1,  4999.00, "pending"),
        (5,  3, 4, 3, "2025-02-20", 3,  2250.00, "completed"),
        (6,  4, 2, 4, "2025-03-01", 1,  1200.00, "completed"),
        (7,  4, 5, 4, "2025-03-10", 5,  2495.00, "completed"),
        (8,  5, 1, 1, "2025-03-15", 1,  4999.00, "cancelled"),
        (9,  6, 2, 3, "2025-03-22", 2,  2400.00, "completed"),
        (10, 7, 5, 2, "2025-04-01", 1,   499.00, "completed"),
        (11, 1, 4, 1, "2025-04-05", 2,  1500.00, "completed"),
        (12, 3, 1, 3, "2025-04-12", 1,  4999.00, "completed"),
        (13, 8, 3, 4, "2025-04-18", 2, 17000.00, "completed"),
        (14, 2, 2, 2, "2025-04-25", 1,  1200.00, "completed"),
        (15, 5, 4, 1, "2025-05-02", 1,   750.00, "completed"),
        (16, 6, 1, 3, "2025-05-10", 2,  9998.00, "pending"),
        (17, 7, 5, 2, "2025-05-15", 3,  1497.00, "completed"),
        (18, 4, 3, 4, "2025-05-20", 1,  8500.00, "completed"),
        (19, 1, 1, 1, "2025-05-22", 1,  4999.00, "completed"),
        (20, 3, 4, 3, "2025-05-25", 2,  1500.00, "completed"),
    ]
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)", orders_data)

    conn.commit()
    log.info("Mock sales database created with %d orders", len(orders_data))
    return conn


# ---------------------------------------------------------------------------
# Schema introspection for system prompt injection
# ---------------------------------------------------------------------------

def get_schema_description(conn: sqlite3.Connection) -> str:
    """Build a natural language schema description for the system prompt."""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = [row[0] for row in cursor.fetchall()]

    lines = ["DATABASE SCHEMA (SQLite):\n"]
    for table in table_names:
        col_cursor = conn.execute(f"PRAGMA table_info({table})")
        columns = [(row[1], row[2], bool(row[5])) for row in col_cursor.fetchall()]

        sample_cursor = conn.execute(f"SELECT * FROM {table} LIMIT 1")
        sample_row = sample_cursor.fetchone()
        col_names = [c[0] for c in columns]

        lines.append(f"Table: {table}")
        for col_name, col_type, is_pk in columns:
            pk_note = " (PRIMARY KEY)" if is_pk else ""
            lines.append(f"  {col_name} {col_type}{pk_note}")
        if sample_row:
            lines.append(f"  Example row: { {k: v for k, v in zip(col_names, sample_row)} }")
        lines.append("")

    return "\n".join(lines)


def build_system_prompt(schema_desc: str) -> str:
    return (
        "You are a SQL analyst assistant for a sales database. "
        "Convert natural language questions into SQLite SELECT queries.\n\n"
        f"{schema_desc}\n"
        "RULES:\n"
        "- Generate ONLY SELECT statements. Never INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, or TRUNCATE.\n"
        "- Always include a LIMIT clause. Maximum 500 rows.\n"
        "- JOIN tables to return human-readable names (e.g. customer name, product name) rather than just IDs.\n"
        "- If the question is ambiguous, choose the most natural interpretation.\n"
        "- If the schema cannot answer the question, explain why in the reasoning field.\n\n"
        "Respond with valid JSON in this exact format (no markdown, no code fences):\n"
        '{"reasoning": "brief explanation of approach", "sql_query": "SELECT ..."}'
    )


# ---------------------------------------------------------------------------
# Safety validator (deterministic)
# ---------------------------------------------------------------------------

BLOCKED_KEYWORDS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|ATTACH|PRAGMA)\b",
    re.IGNORECASE,
)

LIMIT_RE = re.compile(r"\bLIMIT\s+(\d+)", re.IGNORECASE)


def validate_sql(sql: str) -> tuple[bool, str]:
    """Return (is_safe, error_message). Empty error means safe."""
    match = BLOCKED_KEYWORDS_RE.search(sql)
    if match:
        return False, f"Unsafe SQL keyword detected: {match.group().upper()}"

    stripped = sql.strip().lstrip(";").strip()
    if not stripped.upper().startswith("SELECT"):
        return False, "Query must begin with SELECT."

    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        return False, f"Query must include a LIMIT clause (max {ROW_LIMIT})."

    limit_match = LIMIT_RE.search(sql)
    if limit_match and int(limit_match.group(1)) > ROW_LIMIT:
        return False, f"LIMIT {limit_match.group(1)} exceeds maximum of {ROW_LIMIT}."

    return True, ""


def syntax_check(sql: str, conn: sqlite3.Connection) -> tuple[bool, str]:
    """Dry-run the query to check syntax without side effects."""
    try:
        conn.execute("BEGIN")
        conn.execute(sql)
        conn.execute("ROLLBACK")
        return True, ""
    except sqlite3.Error as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        return False, f"SQL syntax error: {e}"


# ---------------------------------------------------------------------------
# Safe execution with timeout
# ---------------------------------------------------------------------------

class QueryTimeoutError(Exception):
    pass


@contextlib.contextmanager
def query_timeout(seconds: int = QUERY_TIMEOUT_SECONDS):
    """Context manager that raises QueryTimeoutError after N seconds (POSIX only)."""
    def _handler(signum, frame):
        raise QueryTimeoutError(f"Query exceeded {seconds}s timeout.")

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def execute_safe(sql: str, conn: sqlite3.Connection) -> tuple[list[dict] | None, str]:
    """Execute a pre-validated SQL query safely. Returns (rows, error)."""
    try:
        with query_timeout(QUERY_TIMEOUT_SECONDS):
            cursor = conn.execute(sql)
            col_names = [d[0] for d in cursor.description]
            rows = [dict(zip(col_names, row)) for row in cursor.fetchall()]
            return rows, ""
    except QueryTimeoutError as e:
        return None, str(e)
    except sqlite3.Error as e:
        return None, f"Execution error: {e}"


# ---------------------------------------------------------------------------
# SQL generation and explanation
# ---------------------------------------------------------------------------

anthropic_client = anthropic.Anthropic()


def generate_sql(question: str, system_prompt: str) -> tuple[str | None, str, str]:
    """
    Call Claude to generate SQL.
    Returns (sql_query, reasoning, raw_response_text).
    sql_query is None if generation failed.
    """
    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_SQL,
        system=system_prompt,
        messages=[{"role": "user", "content": question}],
    )
    raw = next((b.text for b in response.content if hasattr(b, "text")), "")

    # Strip markdown code fences if present
    raw_clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    try:
        parsed = json.loads(raw_clean)
        return parsed.get("sql_query"), parsed.get("reasoning", ""), raw
    except (json.JSONDecodeError, AttributeError):
        return None, "", raw


def explain_results(question: str, sql: str, rows: list[dict]) -> str:
    """Ask Claude to explain query results in plain English."""
    preview = json.dumps(rows[:10], indent=2, default=str)
    prompt = (
        f"Question asked: {question}\n\n"
        f"SQL used:\n{sql}\n\n"
        f"Results returned ({len(rows)} rows total, showing first 10):\n{preview}\n\n"
        "Explain these results in 2-3 sentences of plain English. "
        "State the key finding directly. Do not mention SQL or technical details."
    )
    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_EXPLAIN,
        messages=[{"role": "user", "content": prompt}],
    )
    return next((b.text for b in response.content if hasattr(b, "text")), "(no explanation)")


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def answer_question(
    question: str,
    conn: sqlite3.Connection,
    schema_desc: str,
) -> dict[str, Any]:
    """Run the full text-to-SQL pipeline. Returns a result dict."""
    t_start = time.time()
    system_prompt = build_system_prompt(schema_desc)

    # 1. Generate SQL
    sql, reasoning, raw = generate_sql(question, system_prompt)
    if not sql:
        return {
            "question": question,
            "error": "SQL generation failed. The model did not return parseable JSON.",
            "raw_response": raw,
        }

    # 2. Safety validation
    safe, err = validate_sql(sql)
    if not safe:
        log.warning("SQL blocked by validator: %s | sql=%s", err, sql[:100])
        return {
            "question": question,
            "sql_generated": sql,
            "reasoning": reasoning,
            "error": f"Query blocked by safety validator: {err}",
        }

    # 3. Syntax check
    syntax_ok, syntax_err = syntax_check(sql, conn)
    if not syntax_ok:
        return {
            "question": question,
            "sql_generated": sql,
            "reasoning": reasoning,
            "error": f"SQL syntax error: {syntax_err}",
        }

    # 4. Execute
    rows, exec_err = execute_safe(sql, conn)
    if exec_err:
        return {
            "question": question,
            "sql_generated": sql,
            "reasoning": reasoning,
            "error": f"Execution failed: {exec_err}",
        }

    # 5. Explain
    explanation = explain_results(question, sql, rows)
    latency_ms = int((time.time() - t_start) * 1000)

    log.info(
        "query=%r rows=%d latency_ms=%d",
        question[:60], len(rows or []), latency_ms,
    )

    return {
        "question": question,
        "reasoning": reasoning,
        "sql": sql,
        "row_count": len(rows),
        "rows": rows[:50],  # return max 50 rows in API response
        "explanation": explanation,
        "latency_ms": latency_ms,
    }


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="Text-to-SQL Analytics", version="1.0")

# Module-level state (populated at startup)
DB_CONN: sqlite3.Connection | None = None
SCHEMA_DESC: str = ""


@app.on_event("startup")
def startup():
    global DB_CONN, SCHEMA_DESC
    DB_CONN = create_database()
    SCHEMA_DESC = get_schema_description(DB_CONN)
    log.info("Database ready. Schema:\n%s", SCHEMA_DESC[:300])


class QueryRequest(BaseModel):
    question: str


@app.post("/query")
def query_endpoint(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    if DB_CONN is None:
        raise HTTPException(status_code=503, detail="Database not ready.")
    return answer_question(req.question, DB_CONN, SCHEMA_DESC)


@app.get("/health")
def health():
    return {"status": "ok", "db_ready": DB_CONN is not None}


@app.get("/schema")
def schema_endpoint():
    return {"schema": SCHEMA_DESC}


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    db = create_database()
    schema = get_schema_description(db)

    demo_questions = [
        # Easy
        "How many orders have status 'completed'?",
        "What is the total revenue from all completed orders?",
        # Medium
        "Who are the top 3 customers by total revenue?",
        "What is the revenue breakdown by product category?",
        # Hard
        "Which sales rep has the highest ratio of actual revenue to quota?",
        # Safety tests (should be blocked or handled gracefully)
        "DROP TABLE orders; SELECT 1",
        "Show me all customers; UPDATE customers SET segment='VIP'",
    ]

    for q in demo_questions:
        print(f"\n{'='*60}")
        print(f"Question: {q}")
        result = answer_question(q, db, schema)
        if "error" in result:
            print(f"ERROR: {result['error']}")
        else:
            print(f"SQL: {result['sql']}")
            print(f"Rows: {result['row_count']}")
            print(f"Answer: {result['explanation']}")
            print(f"Latency: {result['latency_ms']}ms")
