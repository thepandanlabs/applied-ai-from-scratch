# Cost Engineering: Token Accounting and Dashboards

> Instrument first. Optimize second. Never guess which call is expensive.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 07 Lessons 01, 05 (Observability fundamentals, LLM request logging)
**Time:** ~60 min
**Learning Objectives:**
- Compute per-request LLM cost from API usage fields for Claude model tiers
- Aggregate costs by model, feature, and user using SQLite
- Build a cost breakdown report rendered as an ASCII table
- Identify the three main sources of LLM cost overruns and their fixes
- Set up a budget alert that fires when projected monthly spend exceeds a threshold

---

## The Problem

Your LLM feature launches. Three months later your infrastructure bill has a line item: $4,200 last month for AI API calls. Your CTO asks which feature drives the most cost. You open your code. Every team made API calls directly. Nobody tracked tokens. Nobody tracked which endpoint called which model. You have no answer.

You start guessing: "It's probably the summarization feature, that uses a lot of tokens." You are wrong. It's the search-intent classifier that runs on every keystroke because a developer set it to fire on `onChange` instead of `onBlur`. You would have caught this in week one if you had cost accounting. Instead you found it in month three, after spending $12,600.

Cost engineering is not about being cheap. It is about understanding where your money goes so you can make deliberate tradeoffs: pay more for quality where it matters, pay less for simple tasks, and catch bugs before they cost thousands of dollars.

---

## The Concept

### Where LLM Costs Come From

```
+---------------------------+-------------------+---------------------------+
| Cost Source               | Typical Impact    | Fix                       |
+---------------------------+-------------------+---------------------------+
| Long system prompts       | 30-60% of input   | Prompt caching (L07)      |
|   repeated on every call  | tokens per call   |                           |
+---------------------------+-------------------+---------------------------+
| Verbose model outputs     | 2-5x output cost  | Explicit length            |
|   (no max length control) | vs needed         | instructions in prompt    |
+---------------------------+-------------------+---------------------------+
| Wrong model tier          | 5-20x cost ratio  | Route simple tasks        |
|   (Opus for simple tasks) | vs correct tier   | to Haiku or Sonnet        |
+---------------------------+-------------------+---------------------------+
| Missing cache hits        | Cache reads cost  | Use cache_control          |
|   (cacheable data re-sent)| 10% of writes     | breakpoints (L07)         |
+---------------------------+-------------------+---------------------------+
| High call frequency       | Multiplies all    | Debounce, batch,          |
|   (per-keystroke callers) | above             | or async queue            |
+---------------------------+-------------------+---------------------------+
```

### Claude Pricing Model (2026 reference)

```
Model                        Input ($/1M)  Output ($/1M)  Cache write  Cache read
---------------------------  -----------  -------------  -----------  ----------
claude-3-5-haiku-20241022       $0.80         $4.00         $1.00       $0.08
claude-3-5-sonnet-20241022      $3.00        $15.00         $3.75       $0.30
claude-opus-4-5                $15.00        $75.00        $18.75       $1.50
```

Output tokens cost 4-5x more than input tokens per million. This means verbose responses are disproportionately expensive. A model that outputs 500 tokens when 100 would do is spending 5x on output alone.

### The Cost Accounting Data Model

```
                    +------------------+
                    |  LLM API Call    |
                    |  (each request)  |
                    +------------------+
                           |
          +----------------+----------------+
          |                |                |
    model tier        feature_name      user_id
    (for cost/token)  (for breakdown)   (for per-user)
          |                |                |
    +----------+    +----------+    +----------+
    | by model |    |by feature|    | by user  |
    | report   |    | report   |    | report   |
    +----------+    +----------+    +----------+
          \              |              /
           \             |             /
            +------------+------------+
                         |
               monthly projection
               budget alert threshold
```

---

## Build It

### Step 1: Cost Calculator

```python
from dataclasses import dataclass

# Pricing per 1M tokens (USD, 2026)
PRICING = {
    "claude-3-5-haiku-20241022": {
        "input": 0.80,
        "output": 4.00,
        "cache_write": 1.00,
        "cache_read": 0.08,
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-opus-4-5": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
}


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """
    Compute the USD cost of a single API call.
    Returns cost in dollars (e.g., 0.00034 for a typical short Haiku call).
    """
    prices = PRICING.get(model, PRICING["claude-3-5-haiku-20241022"])
    cost = (
        (input_tokens * prices["input"])
        + (output_tokens * prices["output"])
        + (cache_write_tokens * prices["cache_write"])
        + (cache_read_tokens * prices["cache_read"])
    ) / 1_000_000
    return round(cost, 8)
```

### Step 2: SQLite Cost Store

```python
import sqlite3
from datetime import datetime, timezone

DB_PATH = "llm_costs.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS llm_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    model TEXT NOT NULL,
    feature_name TEXT NOT NULL DEFAULT 'unknown',
    user_id TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    latency_ms REAL
);
"""

def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_SQL)
    conn.commit()
    return conn


def record_cost(
    conn: sqlite3.Connection,
    model: str,
    input_tokens: int,
    output_tokens: int,
    feature_name: str = "unknown",
    user_id: str | None = None,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    latency_ms: float | None = None,
) -> float:
    """Record a single API call's cost. Returns the computed cost_usd."""
    cost = compute_cost(
        model, input_tokens, output_tokens, cache_write_tokens, cache_read_tokens
    )
    conn.execute(
        """INSERT INTO llm_costs
           (ts, model, feature_name, user_id, input_tokens, output_tokens,
            cache_write_tokens, cache_read_tokens, cost_usd, latency_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now(timezone.utc).isoformat(),
            model,
            feature_name,
            user_id,
            input_tokens,
            output_tokens,
            cache_write_tokens,
            cache_read_tokens,
            cost,
            latency_ms,
        ),
    )
    conn.commit()
    return cost
```

> **Real-world check:** Your head of product asks: "Can you tell me how much the AI search feature costs us per user per month versus the AI summarization feature?" Walk through exactly what data you would need in your database schema to answer that question, and whether the schema above is sufficient.

### Step 3: Cost Breakdown Report

```python
def cost_report(conn: sqlite3.Connection) -> str:
    """
    Generate an ASCII cost breakdown report.
    Shows total cost by model, by feature, and top users.
    """
    lines = []
    lines.append("=" * 60)
    lines.append("LLM COST REPORT")
    lines.append("=" * 60)

    # Total
    row = conn.execute(
        "SELECT SUM(cost_usd), SUM(input_tokens), SUM(output_tokens), COUNT(*) FROM llm_costs"
    ).fetchone()
    total_cost, total_in, total_out, total_calls = row
    lines.append(f"\nTotal calls : {total_calls:,}")
    lines.append(f"Total cost  : ${total_cost or 0:.4f}")
    lines.append(f"Input tokens: {total_in or 0:,}")
    lines.append(f"Output tokens: {total_out or 0:,}")

    # By model
    lines.append("\n--- By Model ---")
    lines.append(f"{'Model':<35} {'Calls':>6} {'Cost ($)':>10} {'% Total':>8}")
    lines.append("-" * 62)
    for model, calls, cost in conn.execute(
        "SELECT model, COUNT(*), SUM(cost_usd) FROM llm_costs GROUP BY model ORDER BY cost_usd DESC"
    ):
        pct = (cost / total_cost * 100) if total_cost else 0
        lines.append(f"{model:<35} {calls:>6} {cost:>10.4f} {pct:>7.1f}%")

    # By feature
    lines.append("\n--- By Feature ---")
    lines.append(f"{'Feature':<25} {'Calls':>6} {'Cost ($)':>10} {'Avg Cost':>10}")
    lines.append("-" * 55)
    for feat, calls, cost in conn.execute(
        "SELECT feature_name, COUNT(*), SUM(cost_usd) FROM llm_costs GROUP BY feature_name ORDER BY cost_usd DESC"
    ):
        avg = cost / calls if calls else 0
        lines.append(f"{feat:<25} {calls:>6} {cost:>10.4f} {avg:>10.6f}")

    # Top users by cost
    lines.append("\n--- Top 5 Users by Cost ---")
    lines.append(f"{'User ID':<20} {'Calls':>6} {'Cost ($)':>10}")
    lines.append("-" * 40)
    for uid, calls, cost in conn.execute(
        "SELECT COALESCE(user_id, 'anonymous'), COUNT(*), SUM(cost_usd) "
        "FROM llm_costs GROUP BY user_id ORDER BY cost_usd DESC LIMIT 5"
    ):
        lines.append(f"{str(uid):<20} {calls:>6} {cost:>10.4f}")

    return "\n".join(lines)
```

### Step 4: Budget Alert

```python
from datetime import date


def monthly_projection(conn: sqlite3.Connection) -> float:
    """Project current month's total cost to end-of-month."""
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    days_elapsed = today.day
    days_in_month = 30  # approximate

    row = conn.execute(
        "SELECT SUM(cost_usd) FROM llm_costs WHERE ts >= ?",
        (month_start,),
    ).fetchone()
    cost_so_far = row[0] or 0.0

    if days_elapsed == 0:
        return 0.0
    return cost_so_far / days_elapsed * days_in_month


def check_budget_alert(
    conn: sqlite3.Connection,
    monthly_budget_usd: float,
    alert_threshold: float = 0.8,
) -> dict:
    """
    Returns alert status if projected spend exceeds threshold * budget.
    alert_threshold=0.8 means alert at 80% of budget.
    """
    projection = monthly_projection(conn)
    ratio = projection / monthly_budget_usd if monthly_budget_usd > 0 else 0
    return {
        "projected_monthly_usd": round(projection, 4),
        "budget_usd": monthly_budget_usd,
        "utilization_pct": round(ratio * 100, 1),
        "alert": ratio >= alert_threshold,
        "message": (
            f"ALERT: Projected spend ${projection:.2f} is "
            f"{ratio*100:.0f}% of ${monthly_budget_usd:.2f} monthly budget"
            if ratio >= alert_threshold
            else "Within budget"
        ),
    }
```

---

## Use It

The `CostAccounting` class wraps the above into a single cohesive interface and adds a `pandas`-free ASCII table renderer so the report works with zero extra dependencies.

```python
class CostAccounting:
    """
    High-level interface to cost tracking.
    Use this in your FastAPI middleware or LLM wrapper.
    """

    def __init__(self, db_path: str = "llm_costs.db"):
        self.conn = init_db(db_path)

    def track(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        feature_name: str = "unknown",
        user_id: str | None = None,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
        latency_ms: float | None = None,
    ) -> float:
        """Record a call. Returns cost in USD."""
        return record_cost(
            self.conn,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            feature_name=feature_name,
            user_id=user_id,
            cache_write_tokens=cache_write_tokens,
            cache_read_tokens=cache_read_tokens,
            latency_ms=latency_ms,
        )

    def report(self) -> str:
        return cost_report(self.conn)

    def budget_alert(self, monthly_budget_usd: float) -> dict:
        return check_budget_alert(self.conn, monthly_budget_usd)
```

You integrate `CostAccounting.track()` at the same layer as your LLM request logger (L05). Both share the same usage fields from the API response.

**What adding this to your stack looks like:**

```python
accounting = CostAccounting()

# In your API call wrapper:
cost = accounting.track(
    model=response.model,
    input_tokens=response.usage.input_tokens,
    output_tokens=response.usage.output_tokens,
    feature_name="search_intent_classifier",
    user_id=current_user.id,
)
```

> **Perspective shift:** A startup CTO says: "We spend $400/month on LLM calls. That's nothing - we make $40,000/month in revenue. Why build a cost accounting system now?" At what revenue-to-AI-cost ratio does instrumentation stop being optional, and what is the operational signal (not a dollar threshold) that tells you the answer?

---

## Ship It

**Artifact:** `outputs/skill-cost-dashboard.md`

This lesson produces a `CostAccounting` class backed by SQLite. The class is a drop-in for any project. For production scale (millions of calls per day), replace the SQLite backend with a time-series table in Postgres or a columnar store like ClickHouse: the interface stays the same.

The ASCII report is suitable for a daily Slack digest bot or a cron job that emails cost summaries to the engineering team. No frontend required.

---

## Evaluate It

**Verification 1: Per-call cost is accurate**

Verify the cost formula against the published Anthropic pricing page. For a Haiku call with 100 input tokens and 50 output tokens:

```python
cost = compute_cost("claude-3-5-haiku-20241022", 100, 50)
# Expected: (100 * 0.80 + 50 * 4.00) / 1_000_000
# = (80 + 200) / 1_000_000 = 0.00000028
assert abs(cost - 0.00000028) < 1e-10
```

**Verification 2: Feature breakdown is queryable**

After recording 10 calls with `feature_name="search"` and 5 with `feature_name="summarize"`, the report should show two rows in the feature breakdown with accurate call counts and costs.

**Verification 3: Budget alert fires at the right threshold**

```python
alert = check_budget_alert(conn, monthly_budget_usd=100.0, alert_threshold=0.8)
# If projected >= $80, alert["alert"] should be True
```

**Verification 4: The three main cost levers are visible**

After one week of production data:
- Run the model breakdown: if your cheapest model is not handling the most calls, that is a routing issue worth investigating
- Run the feature breakdown: if one feature accounts for more than 50% of cost, look at its call frequency and prompt length
- Query `SELECT AVG(output_tokens) FROM llm_costs GROUP BY feature_name`: any feature averaging 1,000+ output tokens is a candidate for explicit length instructions
