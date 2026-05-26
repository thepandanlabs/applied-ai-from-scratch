---
name: runbook-text-to-sql-deploy
description: Deployment and operations runbook for the text-to-SQL analytics capstone
version: "1.0"
phase: "12"
lesson: "03"
tags: [text-to-sql, fastapi, sqlite, safety, structured-output, analytics]
---

# Runbook: Text-to-SQL Analytics Service

## Build and Run

### Local

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...

# Start service (in-memory SQLite db, seeded at startup)
uvicorn main:app --reload --port 8000

# CLI demo (no server needed)
python main.py
```

### Docker

```bash
docker build -t text-to-sql ./code

docker run \
  -p 8000:8000 \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  text-to-sql
```

## Querying the Service

```bash
# Valid query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the top 3 customers by total revenue?"}'

# Response
{
  "question": "What are the top 3 customers by total revenue?",
  "reasoning": "Join orders with customers, sum total_amount for completed orders, order descending",
  "sql": "SELECT c.name, SUM(o.total_amount) as revenue FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE o.status = 'completed' GROUP BY c.customer_id ORDER BY revenue DESC LIMIT 3",
  "row_count": 3,
  "rows": [...],
  "explanation": "The top three customers by revenue are Rekall Corp ($17,000), Acme Corp ($13,898), and Initech ($9,249).",
  "latency_ms": 1340
}

# Blocked unsafe query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Drop the orders table"}'
# Error: Query blocked by safety validator: Unsafe SQL keyword detected: DROP

# View schema
curl http://localhost:8000/schema

# Health check
curl http://localhost:8000/health
```

## Database Setup (Production)

For production, replace the in-memory SQLite database with a real read-only connection:

```python
# In main.py, replace create_database() with:
import psycopg2

def get_production_conn():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    return conn
```

Use a read-only database role: the service should connect with a user that has only SELECT privileges.

```sql
CREATE ROLE analytics_reader;
GRANT CONNECT ON DATABASE salesdb TO analytics_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_reader;
```

## Schema Prompt Management

The schema is injected into the system prompt at service startup via `get_schema_description()`. When the schema changes:

1. The service auto-reads the live schema at startup - no manual update needed for column/table additions
2. If column semantics change (e.g. a column is renamed), restart the service to reload the schema description
3. Review the schema description output at `/schema` to verify it accurately describes the tables

For large schemas (100+ tables), filter the schema injection to only include tables relevant to the expected query domain. Injecting the full schema of a 500-table database will exceed token limits.

## Safety Validator Rules

The validator is deterministic and runs before execution. Current blocked operations:

```
INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT, REVOKE, ATTACH, PRAGMA
```

To add a new blocked operation (e.g. VACUUM):

```python
BLOCKED_KEYWORDS_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|ATTACH|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)
```

Row limit is enforced at `ROW_LIMIT = 500`. Queries without a LIMIT clause are rejected. Queries with `LIMIT > 500` are rejected.

## Query Timeout Configuration

The default timeout is 5 seconds (`QUERY_TIMEOUT_SECONDS = 5`). For complex analytical queries on large datasets, increase to 15-30 seconds. On Windows (no SIGALRM), remove the signal-based timeout and use SQLite's `set_progress_handler` instead.

## Monitoring

Log fields for each query:
- `question` - original question (truncated to 60 chars in log)
- `rows` - number of rows returned
- `latency_ms` - total pipeline latency

Alert conditions:
- Error rate > 20% over 1 hour (validator rejections + generation failures)
- p95 latency > 5000ms
- Row count = 0 for > 30% of successful queries (may indicate overly restrictive SQL generation)

Cost per query at Haiku pricing:
- SQL generation: ~300-500 input tokens + ~100 output tokens
- Result explanation: ~200-400 input tokens + ~80 output tokens
- Total: approximately $0.0005-0.0010 per query

## Known Edge Cases

| Scenario | Behavior | Mitigation |
|----------|----------|------------|
| Ambiguous column name | Model generates incorrect JOIN | Add table aliases to schema description |
| Date range query (e.g. "this year") | Model assumes current year from training data | Inject `SELECT date('now')` result into system prompt |
| Question about non-existent table | Model hallucinates table name | Syntax check catches it; add table allowlist check to validator |
| Very large result set (near limit) | Returns 500 rows, explanation may be inaccurate | Add row count warning in explanation when rows = ROW_LIMIT |
| Windows deployment | query_timeout uses SIGALRM (not available on Windows) | Replace with threading.Timer or remove timeout |
