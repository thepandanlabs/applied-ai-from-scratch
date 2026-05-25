---
name: skill-text-to-sql
description: Guide for building a text-to-SQL pipeline - covers schema context, SQL generation, safety validation, error recovery, and evaluation.
version: "1.0"
phase: "02"
lesson: "13"
tags: [text-to-sql, structured-retrieval, sql-generation, safety, evaluation]
---

# Skill: Building a Text-to-SQL Pipeline

Use this skill when you need to let users query structured data (SQL databases) using natural language.

---

## When to Use Text-to-SQL

Use text-to-SQL when:
- Data lives in tables with a known, stable schema
- The question needs aggregation (count, sum, average), grouping, or date filtering
- Exact answers are required (not fuzzy matching)
- You're building analytics interfaces, internal tools, or support dashboards

Use RAG instead when:
- Data is unstructured (documents, emails, tickets)
- The question needs semantic matching, not exact lookups
- No schema exists

Use a hybrid when:
- SQL finds the entity (customer, order, product)
- RAG answers open-ended questions about documents related to that entity

---

## Step 1: Schema Serialization

The LLM needs your schema to write correct SQL. Include:

```
Table: orders
Columns:
  - id (INTEGER, PRIMARY KEY)
  - customer_id (INTEGER) → customers.id
  - total_amount (REAL)
  - status (TEXT)  -- values: 'pending', 'shipped', 'delivered', 'cancelled'
  - created_at (TEXT)  -- ISO 8601: '2024-11-01T09:15:00'

Sample rows:
  (1, 42, 149.99, 'shipped', '2024-11-15T10:23:00')
  (2, 17, 89.50, 'delivered', '2024-11-20T14:01:00')
```

Key rules for schema serialization:
- Always include foreign key relationships: they're how JOINs are discovered
- Always include 2–3 sample rows: they disambiguate column semantics
- Add inline comments for categorical columns listing the valid values
- Add a note about date storage format (ISO 8601, Unix timestamp, etc.)
- Keep it under 3,000 tokens for standard databases; use table selection for very large schemas

---

## Step 2: SQL Generation Prompt

```python
SQL_SYSTEM_PROMPT = """You are a SQLite expert. Write correct SELECT queries based on
the user's question and the provided schema.

Rules:
1. Write ONLY a single SELECT statement. Never write write operations.
2. Use only table and column names from the schema.
3. Return ONLY the raw SQL: no markdown, no explanation.
"""

def generate_sql(nl_query: str, schema: str, client, model: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SQL_SYSTEM_PROMPT},
            {"role": "user", "content": f"{schema}\n\nQuestion: {nl_query}\n\nSQL:"},
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content.strip()
```

---

## Step 3: Safety Enforcement

Two layers, both required:

**Layer 1: Keyword check (fast, before execution):**
```python
def is_read_only(sql: str) -> bool:
    first_word = sql.strip().lower().split()[0] if sql.strip() else ""
    return first_word == "select"
```

**Layer 2: SQLite PRAGMA (connection-level enforcement):**
```python
conn.execute("PRAGMA query_only = ON")
# ... execute the SQL ...
conn.execute("PRAGMA query_only = OFF")
```

For PostgreSQL/MySQL, use a read-only database role instead of pragmas.

Never rely on prompt constraints alone ("only write SELECT"). Prompt constraints are not security controls.

---

## Step 4: Self-Correction Loop

```python
def run_with_correction(nl_query, schema, conn, client, model, max_retries=2):
    sql = generate_sql(nl_query, schema, client, model)

    for attempt in range(max_retries + 1):
        rows, error = execute_safely(conn, sql)
        if error is None:
            return rows, sql, attempt + 1

        if attempt < max_retries:
            sql = correct_sql(nl_query, sql, error, schema, client, model)

    return None, sql, max_retries + 1
```

One retry resolves ~85% of SQL errors. Two retries resolves ~95%. Beyond two retries, the query is likely ambiguous or requires schema clarification.

---

## Step 5: Large Schema Handling

For databases with >20 tables, don't include the full schema in every prompt. Use a two-stage approach:

1. **Table selection**: ask the LLM which tables are relevant to the query
2. **Focused schema**: serialize only the selected tables

```python
def select_relevant_tables(nl_query: str, table_summaries: dict, client) -> list[str]:
    """
    table_summaries: {table_name: "one-line description of what it contains"}
    Returns list of relevant table names.
    """
    summaries_text = "\n".join(
        f"- {name}: {desc}" for name, desc in table_summaries.items()
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": (
                f"Given this question: {nl_query}\n\n"
                f"Which of these tables are needed to answer it?\n{summaries_text}\n\n"
                f"List only the table names, one per line."
            )},
        ],
        temperature=0.0,
    )
    lines = response.choices[0].message.content.strip().split("\n")
    return [l.strip().lower() for l in lines if l.strip()]
```

---

## Common Failure Modes and Fixes

| Failure | Cause | Fix |
|---------|-------|-----|
| Wrong column name | LLM guessed; column not in schema | Add sample rows; use exact column names in schema |
| Missing JOIN | LLM didn't know the relationship | Add FK relationships explicitly to schema |
| Wrong date filter | Date format not clear | Add comment: "dates stored as ISO 8601 strings" |
| Wrong aggregation (COUNT vs SUM) | Ambiguous column semantics | Add inline comments explaining numeric columns |
| Table name hallucination | Schema was truncated | Never truncate table names; include all tables |

---

## Evaluation

Build a test set before tuning:

```python
eval_set = [
    {
        "query": "How many orders have been delivered?",
        "expected_sql_fragment": "status = 'delivered'",  # must appear in generated SQL
        "expected_row_count": 11,
    },
    {
        "query": "What is the total revenue from all orders?",
        "check": lambda rows: rows[0].get("total") or rows[0].get("total_revenue"),
    },
]
```

Target metrics:
- **Execution success rate**: >90% (SQL runs without error)
- **Correct result rate**: >80% first attempt, >90% with retry
- **Self-correction success**: >85% of failed queries fixed in one retry

---

## Production Checklist

- [ ] Schema serialized with sample rows, FK relationships, and date format comments
- [ ] Read-only enforcement at connection level (PRAGMA or role)
- [ ] Keyword safety check before execution
- [ ] Self-correction loop with max 2 retries
- [ ] Result row cap (never return unbounded rows to the LLM)
- [ ] Logging: log generated SQL, execution result, attempt count
- [ ] Eval set of 20+ (NL query, expected result) pairs
- [ ] Response format: natural language answer, not raw JSON
