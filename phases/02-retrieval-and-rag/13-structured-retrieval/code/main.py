# pip install openai
# SQLite is part of Python's standard library - no install needed.
# Set environment variable: OPENAI_API_KEY=sk-...

import os
import sqlite3
import json
from openai import OpenAI

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def build_sample_database() -> sqlite3.Connection:
    """
    Create an in-memory SQLite database with three tables:
    customers, products, orders.
    Populated with 20 rows of realistic sample data.
    Returns a connection (write-enabled for setup; we enforce read-only per-query).
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE customers (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            city        TEXT,
            joined_at   TEXT  -- ISO 8601 date e.g. '2023-01-15'
        );

        CREATE TABLE products (
            id          INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            category    TEXT,
            price       REAL NOT NULL,
            stock       INTEGER DEFAULT 0
        );

        CREATE TABLE orders (
            id            INTEGER PRIMARY KEY,
            customer_id   INTEGER REFERENCES customers(id),
            product_id    INTEGER REFERENCES products(id),
            quantity      INTEGER NOT NULL DEFAULT 1,
            total_amount  REAL NOT NULL,
            status        TEXT DEFAULT 'pending',
            created_at    TEXT  -- ISO 8601 datetime e.g. '2024-11-01T09:15:00'
            -- status values: 'pending', 'shipped', 'delivered', 'cancelled'
        );
    """)

    customers = [
        (1,  "Alice Chen",    "alice@example.com",   "Seattle",     "2023-01-15"),
        (2,  "Bob Martinez",  "bob@example.com",     "Austin",      "2023-02-20"),
        (3,  "Carol Wu",      "carol@example.com",   "New York",    "2023-03-05"),
        (4,  "David Kim",     "david@example.com",   "Chicago",     "2023-03-18"),
        (5,  "Eve Santos",    "eve@example.com",     "Miami",       "2023-04-01"),
        (6,  "Frank Lee",     "frank@example.com",   "Seattle",     "2023-04-14"),
        (7,  "Grace Patel",   "grace@example.com",   "Austin",      "2023-05-09"),
        (8,  "Henry Okafor",  "henry@example.com",   "New York",    "2023-05-22"),
        (9,  "Iris Tanaka",   "iris@example.com",    "Los Angeles", "2023-06-10"),
        (10, "James Rivera",  "james@example.com",   "Chicago",     "2023-06-28"),
        (11, "Kate Thompson", "kate@example.com",    "Seattle",     "2023-07-03"),
        (12, "Liam O'Brien",  "liam@example.com",    "Boston",      "2023-07-19"),
        (13, "Maya Johnson",  "maya@example.com",    "Miami",       "2023-08-05"),
        (14, "Noah Williams", "noah@example.com",    "Austin",      "2023-08-20"),
        (15, "Olivia Brown",  "olivia@example.com",  "New York",    "2023-09-04"),
        (16, "Paul Davis",    "paul@example.com",    "Los Angeles", "2023-09-18"),
        (17, "Quinn Miller",  "quinn@example.com",   "Chicago",     "2023-10-02"),
        (18, "Rachel Wilson", "rachel@example.com",  "Seattle",     "2023-10-15"),
        (19, "Sam Taylor",    "sam@example.com",     "Boston",      "2023-11-01"),
        (20, "Tina Anderson", "tina@example.com",    "Miami",       "2023-11-20"),
    ]
    cursor.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", customers)

    products = [
        (1,  "Wireless Headphones", "Electronics", 89.99,  42),
        (2,  "Mechanical Keyboard", "Electronics", 129.99, 30),
        (3,  "USB-C Hub",           "Electronics", 49.99,  75),
        (4,  "Standing Desk Mat",   "Office",      39.99,  60),
        (5,  "Laptop Stand",        "Office",      59.99,  55),
        (6,  "Blue Light Glasses",  "Accessories", 24.99,  120),
        (7,  "Webcam HD 1080p",     "Electronics", 79.99,  25),
        (8,  "Desk Organizer",      "Office",      29.99,  80),
        (9,  "Ergonomic Mouse",     "Electronics", 69.99,  45),
        (10, "Monitor Light Bar",   "Electronics", 44.99,  65),
    ]
    cursor.executemany("INSERT INTO products VALUES (?,?,?,?,?)", products)

    orders = [
        (1,   2,  1, 1,  89.99, "delivered", "2024-11-01T09:15:00"),
        (2,   5,  2, 1, 129.99, "delivered", "2024-11-03T11:30:00"),
        (3,   1,  3, 2,  99.98, "shipped",   "2024-11-05T14:00:00"),
        (4,   8,  5, 1,  59.99, "delivered", "2024-11-08T10:20:00"),
        (5,   3,  1, 1,  89.99, "delivered", "2024-11-10T16:45:00"),
        (6,  12,  4, 2,  79.98, "shipped",   "2024-11-12T09:00:00"),
        (7,   7,  7, 1,  79.99, "delivered", "2024-11-14T13:10:00"),
        (8,  15,  2, 2, 259.98, "pending",   "2024-11-17T08:55:00"),
        (9,   4,  9, 1,  69.99, "delivered", "2024-11-19T15:30:00"),
        (10,  9,  6, 3,  74.97, "shipped",   "2024-11-21T11:00:00"),
        (11, 11, 10, 1,  44.99, "delivered", "2024-11-24T14:20:00"),
        (12,  6,  1, 1,  89.99, "cancelled", "2024-11-26T10:10:00"),
        (13, 13,  2, 1, 129.99, "delivered", "2024-11-28T12:00:00"),
        (14, 17,  5, 2, 119.98, "shipped",   "2024-11-30T09:45:00"),
        (15,  2,  3, 1,  49.99, "delivered", "2024-12-02T16:00:00"),
        (16, 20,  8, 2,  59.98, "pending",   "2024-12-04T11:30:00"),
        (17,  1,  9, 1,  69.99, "shipped",   "2024-12-06T13:45:00"),
        (18, 14,  7, 1,  79.99, "delivered", "2024-12-08T10:00:00"),
        (19, 10,  2, 1, 129.99, "delivered", "2024-12-10T15:20:00"),
        (20, 16,  4, 3, 119.97, "shipped",   "2024-12-12T08:30:00"),
    ]
    cursor.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", orders)

    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Schema serialization
# ---------------------------------------------------------------------------

def serialize_schema(conn: sqlite3.Connection, sample_rows: int = 3) -> str:
    """
    Serialize the full database schema into a context string for the LLM.
    Includes: table names, columns (name + type + constraints), foreign keys,
    and sample rows.

    More context = more accurate SQL generation.
    """
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    parts = ["DATABASE SCHEMA\n" + "=" * 60]
    parts.append(
        "NOTE: All date/datetime columns store ISO 8601 strings.\n"
        "Example: joined_at = '2023-01-15', created_at = '2024-11-01T09:15:00'\n"
        "Use strftime() or string comparison for date filtering."
    )

    for table in tables:
        parts.append(f"\nTable: {table}")

        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        parts.append("Columns:")
        for col in columns:
            # (cid, name, type, notnull, default_value, pk)
            col_def = f"  - {col[1]} ({col[2]})"
            if col[5]:
                col_def += ", PRIMARY KEY"
            if col[3]:
                col_def += ", NOT NULL"
            parts.append(col_def)

        cursor.execute(f"PRAGMA foreign_key_list({table})")
        fks = cursor.fetchall()
        if fks:
            parts.append("Foreign Keys:")
            for fk in fks:
                parts.append(f"  - {fk[3]} → {fk[2]}.{fk[4]}")

        cursor.execute(f"SELECT * FROM {table} LIMIT {sample_rows}")
        rows = cursor.fetchall()
        if rows:
            col_names = [col[1] for col in columns]
            parts.append(f"Sample rows (first {len(rows)}):")
            parts.append(f"  Columns: {col_names}")
            for row in rows:
                parts.append(f"  {tuple(row)}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM-based SQL generation
# ---------------------------------------------------------------------------

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MODEL = "gpt-4o-mini"

SQL_SYSTEM_PROMPT = """You are a SQLite expert. Write correct SQLite SELECT queries based on
the user's natural language question and the provided database schema.

Rules:
1. Write ONLY a single SELECT statement. Never write INSERT, UPDATE, DELETE, DROP, or CREATE.
2. Use only table and column names that appear in the schema.
3. For date comparisons, use SQLite string comparison (e.g., created_at >= '2024-12-01').
4. Always qualify column names with table name/alias when joining multiple tables.
5. Return ONLY the raw SQL query - no explanation, no markdown, no backticks.
6. If the question is ambiguous, make the most reasonable interpretation.
"""


def generate_sql(nl_query: str, schema_context: str) -> str:
    """
    Generate SQL from a natural language query using the schema context.
    Returns raw SQL string (no markdown fences).
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SQL_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{schema_context}\n\n"
                    f"{'─' * 60}\n\n"
                    f"Question: {nl_query}\n\n"
                    f"SQL:"
                ),
            },
        ],
        temperature=0.0,
    )
    sql = response.choices[0].message.content.strip()

    # Strip markdown code fences if the model adds them despite instructions
    if "```" in sql:
        parts = sql.split("```")
        for part in parts:
            if part.strip().upper().startswith("SELECT"):
                return part.strip()
        # Fallback: strip first fence
        sql = sql.replace("```sql", "").replace("```", "").strip()

    return sql


def correct_sql(
    nl_query: str,
    failed_sql: str,
    error_message: str,
    schema_context: str,
) -> str:
    """
    Feed a failed SQL + error message back to the LLM for self-correction.
    """
    correction_prompt = (
        f"{schema_context}\n\n"
        f"{'─' * 60}\n\n"
        f"The following SQL was generated for this question:\n"
        f"Question: {nl_query}\n\n"
        f"Failed SQL:\n{failed_sql}\n\n"
        f"SQLite Error:\n{error_message}\n\n"
        f"Write a corrected SQL query that fixes the error. "
        f"Return ONLY the raw SQL - no explanation, no backticks."
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SQL_SYSTEM_PROMPT},
            {"role": "user", "content": correction_prompt},
        ],
        temperature=0.0,
    )
    sql = response.choices[0].message.content.strip()

    if "```" in sql:
        sql = sql.replace("```sql", "").replace("```", "").strip()

    return sql


# ---------------------------------------------------------------------------
# Safe SQL execution
# ---------------------------------------------------------------------------

def is_read_only(sql: str) -> bool:
    """
    Secondary guard: ensure the SQL starts with SELECT.
    PRAGMA query_only is the primary guard; this catches obvious mistakes early.
    """
    first_word = sql.strip().lower().split()[0] if sql.strip() else ""
    return first_word == "select"


def execute_sql(
    conn: sqlite3.Connection,
    sql: str,
    max_rows: int = 100,
) -> tuple[list[dict], str | None]:
    """
    Execute SQL safely and return (rows, error).

    Safety:
    - is_read_only() check rejects non-SELECT statements before execution.
    - PRAGMA query_only = ON enforces read-only at the SQLite connection level.

    Returns:
      rows: list of dicts on success, empty list on failure.
      error: None on success, error string on failure.
    """
    if not is_read_only(sql):
        return [], (
            f"Safety check failed: SQL must start with SELECT. "
            f"Got: '{sql.strip()[:60]}'"
        )

    try:
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchmany(max_rows)]
        return rows, None
    except sqlite3.Error as e:
        return [], str(e)
    finally:
        conn.execute("PRAGMA query_only = OFF")


# ---------------------------------------------------------------------------
# Self-correction loop
# ---------------------------------------------------------------------------

def run_text_to_sql(
    nl_query: str,
    conn: sqlite3.Connection,
    schema_context: str,
    max_retries: int = 2,
    verbose: bool = True,
) -> dict:
    """
    Full text-to-SQL pipeline with self-correction.

    Flow:
      1. LLM generates SQL from NL query + schema
      2. Execute SQL
      3. On error: feed error back to LLM, request correction
      4. Repeat up to max_retries times
      5. Format successful result as natural language answer

    Returns dict with: sql, rows, answer, attempts, error
    """
    if verbose:
        print(f"\n{'─' * 60}")
        print(f"Query: {nl_query}")

    sql = generate_sql(nl_query, schema_context)

    if verbose:
        print(f"Generated SQL (attempt 1):\n  {sql}")

    attempts = 1
    last_error = None

    for attempt in range(max_retries + 1):
        rows, error = execute_sql(conn, sql)

        if error is None:
            answer = format_answer(nl_query, rows, sql)
            if verbose:
                print(f"Execution: SUCCESS ({len(rows)} rows returned)")
                print(f"Answer: {answer}")
            return {
                "sql": sql,
                "rows": rows,
                "answer": answer,
                "attempts": attempts,
                "error": None,
            }

        last_error = error
        if verbose:
            print(f"Execution: ERROR (attempt {attempt + 1}): {error}")

        if attempt < max_retries:
            if verbose:
                print(f"Requesting correction from LLM...")
            sql = correct_sql(nl_query, sql, error, schema_context)
            attempts += 1
            if verbose:
                print(f"Corrected SQL (attempt {attempts}):\n  {sql}")

    # All retries exhausted
    answer = f"Could not execute query after {attempts} attempts. Last error: {last_error}"
    if verbose:
        print(f"All retries exhausted. {answer}")
    return {
        "sql": sql,
        "rows": [],
        "answer": answer,
        "attempts": attempts,
        "error": last_error,
    }


# ---------------------------------------------------------------------------
# Natural language answer formatting
# ---------------------------------------------------------------------------

ANSWER_SYSTEM_PROMPT = """You are a helpful data analyst. Given a natural language question,
the SQL query used to answer it, and the query results as JSON rows, write a clear and concise
natural language answer. Be specific - include actual numbers, names, and values from the results.
Keep it to 1-3 sentences. If results are empty, say so directly."""


def format_answer(nl_query: str, rows: list[dict], sql: str) -> str:
    """
    Convert SQL result rows into a natural language answer.
    """
    if not rows:
        return "The query returned no results."

    results_json = json.dumps(rows[:20], indent=2)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Question: {nl_query}\n\n"
                    f"SQL:\n{sql}\n\n"
                    f"Results ({len(rows)} row(s)):\n{results_json}\n\n"
                    f"Answer:"
                ),
            },
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Building sample e-commerce database (in-memory SQLite)...")
    conn = build_sample_database()

    print("Serializing schema...")
    schema_context = serialize_schema(conn, sample_rows=3)

    print("\n" + "=" * 60)
    print("SCHEMA CONTEXT (what the LLM sees):")
    print("=" * 60)
    print(schema_context[:800] + "...\n[truncated for display]\n")

    demo_queries = [
        # Aggregation
        "How many orders are in each status category?",
        # Filtering + join
        "List all delivered orders with the customer name and product name.",
        # Top-N with aggregation
        "Which 3 customers have spent the most money in total?",
        # Date filtering
        "What orders were placed in December 2024?",
        # Average + grouping
        "What is the average order value by city?",
    ]

    print("=" * 60)
    print("RUNNING DEMO QUERIES")
    print("=" * 60)

    results_summary = []
    for query in demo_queries:
        result = run_text_to_sql(query, conn, schema_context, max_retries=2, verbose=True)
        results_summary.append({
            "query": query,
            "success": result["error"] is None,
            "attempts": result["attempts"],
        })

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    successes = sum(1 for r in results_summary if r["success"])
    print(f"Queries run:   {len(results_summary)}")
    print(f"Succeeded:     {successes}")
    print(f"Failed:        {len(results_summary) - successes}")
    for r in results_summary:
        status = "OK" if r["success"] else "FAIL"
        print(f"  [{status}] ({r['attempts']} attempt(s)) {r['query'][:60]}")

    conn.close()


if __name__ == "__main__":
    main()
