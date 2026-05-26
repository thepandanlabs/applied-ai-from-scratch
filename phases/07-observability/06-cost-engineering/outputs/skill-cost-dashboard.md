---
name: skill-cost-dashboard
description: Token-based cost accounting for LLM APIs with per-model, per-feature, per-user breakdown and budget alerts
version: "1.0"
phase: "07"
lesson: "06"
tags: [cost, observability, token-accounting, budget, sqlite]
---

# Skill: LLM Cost Dashboard

## Purpose

You are an applied AI engineering advisor. When a user needs to understand and control their LLM API spend, use this skill to design their cost accounting strategy and implement the right tracking granularity.

---

## Pricing Reference (2026)

| Model | Input ($/1M) | Output ($/1M) | Cache write | Cache read |
|---|---|---|---|---|
| claude-3-5-haiku-20241022 | $0.80 | $4.00 | $1.00 | $0.08 |
| claude-3-5-sonnet-20241022 | $3.00 | $15.00 | $3.75 | $0.30 |
| claude-opus-4-5 | $15.00 | $75.00 | $18.75 | $1.50 |

Key ratio: output tokens cost 5x more than input tokens (per token). Long outputs are disproportionately expensive.

---

## The Three Main Cost Levers

```
1. Long system prompts repeated on every call
   Fix: prompt caching (Phase 07 L07)
   Impact: 30-60% reduction in effective input tokens

2. Verbose outputs (no explicit length control)
   Fix: add "Answer in 2-3 sentences" or similar to prompt
   Impact: 2-5x reduction in output tokens for many tasks

3. Wrong model tier (Opus for simple classification)
   Fix: route simple tasks to Haiku (~20x cheaper than Opus)
   Impact: 5-20x cost reduction per call
```

---

## What to Track Per Call

```python
accounting.track(
    model=response.model,              # for per-model cost
    input_tokens=response.usage.input_tokens,
    output_tokens=response.usage.output_tokens,
    cache_write_tokens=...,            # cache cost attribution
    cache_read_tokens=...,
    feature_name="search_intent",      # for per-feature breakdown
    user_id=current_user.hashed_id,   # for per-user cost; use opaque ID
    latency_ms=...,                   # for cost-latency correlation
)
```

---

## Diagnostic Queries

**Which feature is most expensive?**
```sql
SELECT feature_name, SUM(cost_usd) as total, COUNT(*) as calls,
       AVG(output_tokens) as avg_output_tokens
FROM llm_costs
GROUP BY feature_name
ORDER BY total DESC;
```

**Is one user driving unusual cost?**
```sql
SELECT user_id, SUM(cost_usd), COUNT(*),
       SUM(cost_usd) / COUNT(*) as avg_cost_per_call
FROM llm_costs
WHERE ts >= date('now', '-7 days')
GROUP BY user_id
ORDER BY SUM(cost_usd) DESC
LIMIT 10;
```

**What is the output token distribution for a feature?**
```sql
SELECT
  MIN(output_tokens) as min,
  AVG(output_tokens) as avg,
  MAX(output_tokens) as max,
  COUNT(*) as calls
FROM llm_costs
WHERE feature_name = 'summarize';
```
If avg > 800 tokens for a summarization task, add explicit length constraints to the prompt.

---

## Budget Alert Pattern

```python
alert = accounting.budget_alert(monthly_budget_usd=500.0, alert_threshold=0.8)
if alert["alert"]:
    send_slack_alert(alert["message"])
```

Set `alert_threshold=0.8` to get early warning with 20% budget remaining. Wire this to a daily cron job, not a per-request hook (to avoid alert storms).

---

## Scaling Beyond SQLite

SQLite handles up to ~1M rows comfortably. For higher volume:

- Replace SQLite with a Postgres time-series table or ClickHouse
- Same `record_cost()` interface, different connection
- Add a TTL policy: keep raw call data for 90 days, aggregate to daily summaries for 2 years
- Stream events to a message queue (Kafka, SQS) and aggregate async

---

## Common Mistakes

**Not tagging feature_name**: You end up with one undifferentiated cost bucket. Add the feature tag from day one - retrofitting it requires correlating timestamps with deployment history.

**Using user email as user_id**: PII in cost data creates the same compliance exposure as PII in logs. Use an opaque hash or internal UUID.

**Only checking total monthly cost**: A feature that fires 10x more than expected may not show up in monthly totals if it runs cheaply per call. Watch call count and avg_output_tokens, not just total cost.

**No projection**: Discovering you are 80% over budget on the last day of the month means it is too late to act. Build a daily projection from the first week of the month.
