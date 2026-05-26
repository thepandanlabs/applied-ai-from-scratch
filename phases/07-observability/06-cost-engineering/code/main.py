"""
L06: Cost Engineering - Token Accounting and Dashboards
Phase 07 - Observability

Demonstrates:
- Per-request cost computation from API usage fields
- SQLite-backed cost store with model, feature, and user dimensions
- ASCII cost breakdown report
- Monthly projection and budget alert
- CostAccounting high-level interface
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

import anthropic

# ---------------------------------------------------------------------------
# Pricing Table (USD per 1M tokens, 2026)
# ---------------------------------------------------------------------------

PRICING: dict[str, dict[str, float]] = {
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

# Default to Haiku pricing for unknown models
_DEFAULT_MODEL = "claude-3-5-haiku-20241022"


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """
    Compute USD cost for a single API call.

    Returns cost in dollars. Typical Haiku call: $0.0000003 - $0.000003.
    Output tokens cost 5x more per token than input tokens.
    """
    prices = PRICING.get(model, PRICING[_DEFAULT_MODEL])
    cost = (
        (input_tokens * prices["input"])
        + (output_tokens * prices["output"])
        + (cache_write_tokens * prices["cache_write"])
        + (cache_read_tokens * prices["cache_read"])
    ) / 1_000_000
    return round(cost, 8)


# ---------------------------------------------------------------------------
# SQLite Store
# ---------------------------------------------------------------------------

_CREATE_SQL = """
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


def init_db(db_path: str = "llm_costs.db") -> sqlite3.Connection:
    """Create the database and cost table if they do not exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE_SQL)
    conn.commit()
    return conn


def record_cost(
    conn: sqlite3.Connection,
    model: str,
    input_tokens: int,
    output_tokens: int,
    feature_name: str = "unknown",
    user_id: Optional[str] = None,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    latency_ms: Optional[float] = None,
) -> float:
    """
    Persist a single API call's cost dimensions.
    Returns the computed cost_usd.
    """
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


# ---------------------------------------------------------------------------
# Cost Breakdown Report
# ---------------------------------------------------------------------------


def cost_report(conn: sqlite3.Connection) -> str:
    """
    Render an ASCII cost breakdown report to stdout.
    Shows totals, breakdown by model, by feature, and top 5 users.
    """
    lines: list[str] = []
    lines.append("=" * 62)
    lines.append("LLM COST REPORT")
    lines.append("=" * 62)

    # Totals
    row = conn.execute(
        "SELECT SUM(cost_usd), SUM(input_tokens), SUM(output_tokens), COUNT(*) FROM llm_costs"
    ).fetchone()
    total_cost = row[0] or 0.0
    total_in = row[1] or 0
    total_out = row[2] or 0
    total_calls = row[3] or 0

    lines.append(f"\n{'Total calls':<20}: {total_calls:,}")
    lines.append(f"{'Total cost':<20}: ${total_cost:.4f}")
    lines.append(f"{'Input tokens':<20}: {total_in:,}")
    lines.append(f"{'Output tokens':<20}: {total_out:,}")
    if total_calls > 0:
        lines.append(f"{'Avg cost/call':<20}: ${total_cost/total_calls:.6f}")

    # By model
    lines.append("\n--- By Model ---")
    lines.append(f"{'Model':<35} {'Calls':>6} {'Cost ($)':>10} {'% Total':>8}")
    lines.append("-" * 62)
    for model, calls, cost in conn.execute(
        "SELECT model, COUNT(*), SUM(cost_usd) FROM llm_costs "
        "GROUP BY model ORDER BY SUM(cost_usd) DESC"
    ):
        pct = (cost / total_cost * 100) if total_cost else 0.0
        lines.append(f"{model:<35} {calls:>6} {cost:>10.4f} {pct:>7.1f}%")

    # By feature
    lines.append("\n--- By Feature ---")
    lines.append(
        f"{'Feature':<25} {'Calls':>6} {'Cost ($)':>10} {'Avg/call':>10} {'Avg Out Tokens':>15}"
    )
    lines.append("-" * 70)
    for feat, calls, cost, avg_out in conn.execute(
        "SELECT feature_name, COUNT(*), SUM(cost_usd), AVG(output_tokens) "
        "FROM llm_costs GROUP BY feature_name ORDER BY SUM(cost_usd) DESC"
    ):
        avg = cost / calls if calls else 0.0
        lines.append(f"{feat:<25} {calls:>6} {cost:>10.4f} {avg:>10.6f} {avg_out:>15.0f}")

    # Top 5 users
    lines.append("\n--- Top 5 Users by Cost ---")
    lines.append(f"{'User ID':<25} {'Calls':>6} {'Cost ($)':>10} {'Avg/call':>10}")
    lines.append("-" * 55)
    for uid, calls, cost in conn.execute(
        "SELECT COALESCE(user_id, 'anonymous'), COUNT(*), SUM(cost_usd) "
        "FROM llm_costs GROUP BY user_id ORDER BY SUM(cost_usd) DESC LIMIT 5"
    ):
        avg = cost / calls if calls else 0.0
        lines.append(f"{str(uid):<25} {calls:>6} {cost:>10.4f} {avg:>10.6f}")

    lines.append("\n" + "=" * 62)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Budget Alert
# ---------------------------------------------------------------------------


def monthly_projection(conn: sqlite3.Connection) -> float:
    """
    Project current-month spend to end-of-month based on daily run rate.
    Uses 30-day month approximation.
    """
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    days_elapsed = today.day

    row = conn.execute(
        "SELECT SUM(cost_usd) FROM llm_costs WHERE ts >= ?",
        (month_start,),
    ).fetchone()
    cost_so_far = row[0] or 0.0

    if days_elapsed == 0:
        return 0.0
    return round(cost_so_far / days_elapsed * 30, 4)


def check_budget_alert(
    conn: sqlite3.Connection,
    monthly_budget_usd: float,
    alert_threshold: float = 0.8,
) -> dict:
    """
    Return budget alert status.

    alert_threshold: fraction of budget that triggers an alert (default 0.8 = 80%).
    """
    projection = monthly_projection(conn)
    ratio = projection / monthly_budget_usd if monthly_budget_usd > 0 else 0.0
    alert = ratio >= alert_threshold

    return {
        "projected_monthly_usd": projection,
        "budget_usd": monthly_budget_usd,
        "utilization_pct": round(ratio * 100, 1),
        "alert": alert,
        "message": (
            f"ALERT: Projected ${projection:.2f} is {ratio*100:.0f}% "
            f"of ${monthly_budget_usd:.2f} budget"
            if alert
            else f"OK: Projected ${projection:.2f} ({ratio*100:.0f}% of ${monthly_budget_usd:.2f})"
        ),
    }


# ---------------------------------------------------------------------------
# High-Level Interface
# ---------------------------------------------------------------------------


class CostAccounting:
    """
    Drop-in cost tracking for any LLM-calling service.

    Usage:
        accounting = CostAccounting()

        # In your LLM wrapper, after each API call:
        cost = accounting.track(
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            feature_name="search_intent_classifier",
            user_id=current_user.id,
        )
    """

    def __init__(self, db_path: str = "llm_costs.db"):
        self.db_path = db_path
        self.conn = init_db(db_path)

    def track(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        feature_name: str = "unknown",
        user_id: Optional[str] = None,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
        latency_ms: Optional[float] = None,
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
        """Return the ASCII cost breakdown report."""
        return cost_report(self.conn)

    def budget_alert(
        self, monthly_budget_usd: float, alert_threshold: float = 0.8
    ) -> dict:
        """Return budget alert status dict."""
        return check_budget_alert(self.conn, monthly_budget_usd, alert_threshold)


# ---------------------------------------------------------------------------
# API wrapper with cost tracking (optional - requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------

import time as _time


def call_with_cost_tracking(
    prompt: str,
    feature_name: str = "unknown",
    user_id: Optional[str] = None,
    accounting: Optional[CostAccounting] = None,
    model: str = "claude-3-5-haiku-20241022",
) -> tuple[str, float]:
    """
    Make a Claude API call and record cost.
    Returns (response_text, cost_usd).
    """
    if accounting is None:
        accounting = CostAccounting()

    client = anthropic.Anthropic()
    start = _time.monotonic()

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = (_time.monotonic() - start) * 1000

    cost = accounting.track(
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
        cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0),
        feature_name=feature_name,
        user_id=user_id,
        latency_ms=latency_ms,
    )

    text = response.content[0].text if response.content else ""
    return text, cost


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def demo() -> None:
    """
    Seed a demo database with synthetic call data and render the report.
    No API key needed for this demo.
    """
    import random
    import os

    db_path = "/tmp/llm_costs_demo.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    accounting = CostAccounting(db_path=db_path)

    # Synthetic call data
    features = ["search_intent", "summarize", "classify", "extract_entities"]
    models = [
        "claude-3-5-haiku-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-5-haiku-20241022",  # most calls on haiku
        "claude-3-5-sonnet-20241022",  # some on sonnet
    ]
    users = ["user_001", "user_002", "user_003", None]

    random.seed(42)
    for _ in range(50):
        model = random.choice(models)
        feature = random.choice(features)
        user = random.choice(users)
        input_tok = random.randint(50, 800)
        output_tok = random.randint(20, 500)
        accounting.track(
            model=model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            feature_name=feature,
            user_id=user,
            latency_ms=random.uniform(200, 1500),
        )

    print(accounting.report())

    alert = accounting.budget_alert(monthly_budget_usd=0.05)
    print(f"\nBudget check: {alert['message']}")

    # Verify cost formula
    cost = compute_cost("claude-3-5-haiku-20241022", 100, 50)
    expected = (100 * 0.80 + 50 * 4.00) / 1_000_000
    assert abs(cost - expected) < 1e-10, f"Cost formula wrong: {cost} != {expected}"
    print("\nCost formula verification: PASS")


if __name__ == "__main__":
    demo()
