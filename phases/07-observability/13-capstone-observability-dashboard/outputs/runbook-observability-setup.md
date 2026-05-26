---
name: runbook-observability-setup
description: Operations runbook for the Phase 07 observability stack covering startup, configuration, SLO threshold tuning, dashboard interpretation, and incident response
version: "1.0"
phase: "07"
lesson: "13"
tags: [runbook, operations, observability, slo, dashboard, incident-response]
---

# Observability Stack Operations Runbook

This runbook covers the complete Phase 07 observability stack for any LLM-backed service. Follow it to start the system, tune alerting, and respond to incidents.

---

## 1. Startup

### Local development

```bash
# Install dependencies
pip install -r code/requirements.txt

# Run demo mode (simulated traffic, no API key needed)
python code/main.py --demo

# Run FastAPI service (requires ANTHROPIC_API_KEY)
ANTHROPIC_API_KEY=sk-ant-... uvicorn code.main:app --port 8080 --reload
```

Dashboard starts automatically and renders to stdout every 5 seconds.

### Docker

```bash
# Build
docker build -t rag-service code/

# Run
docker run -p 8080:8080 \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e SERVICE_NAME=my-rag-service \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  rag-service
```

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | - | Anthropic API key |
| `SERVICE_NAME` | No | `rag-service` | Name shown in dashboard and logs |
| `DB_PATH` | No | `/app/data/cost_log.db` | SQLite cost database path |
| `LOG_PATH` | No | `/app/logs/app.jsonl` | Structured log output path |
| `LANGFUSE_PUBLIC_KEY` | No | - | Enable Langfuse tracing |
| `LANGFUSE_SECRET_KEY` | No | - | Enable Langfuse tracing |
| `PORT` | No | `8080` | HTTP port |

---

## 2. Configuration

### SLO targets

Edit the `ObsConfig` defaults in `main.py` or pass overrides at startup:

```python
obs = ObservabilityModule(ObsConfig(
    availability_target=0.995,     # 99.5% - adjust based on user expectations
    ttft_p95_target_ms=2000,       # 2s - use load test p95 as starting point
    error_rate_target=0.01,        # 1% - start here, tighten after first week
    eval_score_target=0.80,        # 0.80 - replace with your eval metric
    cache_hit_rate_target=0.40,    # 40% - lower for freeform prompts
    cost_p95_target_usd=0.005,     # $0.005 - based on model pricing + max_tokens
))
```

### Setting initial targets from load test data

After running the load test (Lesson 10), set these targets:

```
availability_target  = max(load_test_availability - 0.005, 0.990)
ttft_p95_target_ms   = load_test_p95_ttft * 1.5   (50% headroom)
error_rate_target    = max(load_test_error_rate * 2, 0.005)
cost_p95_target_usd  = load_test_cost_p95 * 1.2   (20% headroom)
```

### Eval score baseline

Before you can set `eval_score_target`, you need 1-2 weeks of production eval data. In the meantime:

1. Set `eval_score_target=0.0` to disable eval alerting.
2. Log eval scores for all sampled requests.
3. After week 2, compute `mean(eval_scores) - 2 * std(eval_scores)` as your target.

---

## 3. Dashboard Interpretation

```
+----------------------------------------------------+
|  rag-service Observability Dashboard               |
|  2026-05-26 14:32:11  |  uptime: 2h 14m           |
+----------------------------------------------------+
|  Requests (15m):   42  |  Error rate:   0.3%      |   <- (A)
|  TTFT p50:       380ms |  TTFT p95:    890ms      |   <- (B)
|  Total p50:      2.1s  |  Total p95:    5.2s      |   <- (C)
|  Cost/hr:       $0.18  |  Cache hits:  52%        |   <- (D)
|  Eval score:     0.87  |  SLO status:  OK         |   <- (E)
+----------------------------------------------------+
|  ALERTS: none                                      |
+----------------------------------------------------+
```

**(A) Request volume and error rate:** Requests/15m tells you current traffic level. Error rate above 1% warrants investigation.

**(B) TTFT:** Time-to-first-token is what users perceive as responsiveness. p95 > 3x p50 indicates bimodal distribution (some requests are much slower than others).

**(C) Total latency:** End-to-end response time. p95 > 4x p50 usually means a few very long responses; check max_tokens setting.

**(D) Cost/hr and cache hits:** Cost/hr should correlate with request volume. Sudden cost spike at constant volume means prompt length or output length increased unexpectedly. Cache hit rate below 20% is abnormal unless prompts are freeform.

**(E) Eval score and SLO status:** Green "OK" means all 6 SLIs are within target. Any alert shows "ALERT" and the alert count.

---

## 4. SLO Threshold Tuning

Run this review after the first two weeks of production traffic.

### Step 1: Review alert history

```bash
grep '"level":"WARNING"' logs/app.jsonl | grep slo | jq '.event' | sort | uniq -c
```

### Step 2: Calculate noise rate

```
noise_alerts = alerts that fired and self-resolved with no engineering action
total_alerts = all alerts fired in the 2-week period
noise_rate   = noise_alerts / total_alerts

Target noise rate: < 20%
```

### Step 3: Adjust thresholds

For each SLI where noise rate > 20%:

- Add minimum breach duration: only alert if the SLI is below target for > 5 minutes continuously.
- Widen the threshold by 10% and re-evaluate after one week.

For each incident that had no prior alert:

- Identify which SLI should have caught it.
- Tighten that SLI threshold by 10%.
- Add the incident scenario to the chaos test suite.

---

## 5. Cost Database Queries

```bash
# Total cost last 24 hours
sqlite3 data/cost_log.db "SELECT ROUND(SUM(cost_usd), 4) FROM llm_calls WHERE ts > strftime('%s', 'now') - 86400;"

# Hourly cost trend (last 12 hours)
sqlite3 data/cost_log.db "
SELECT strftime('%H:00', datetime(ts, 'unixepoch')) as hour,
       ROUND(SUM(cost_usd), 4) as total_cost,
       COUNT(*) as request_count
FROM llm_calls
WHERE ts > strftime('%s', 'now') - 43200
GROUP BY hour ORDER BY hour;
"

# Most expensive operations
sqlite3 data/cost_log.db "
SELECT operation, COUNT(*) as calls, ROUND(SUM(cost_usd), 4) as total_cost
FROM llm_calls
WHERE ts > strftime('%s', 'now') - 86400
GROUP BY operation ORDER BY total_cost DESC;
"
```

---

## 6. Incident Response

### Availability below target

1. Check `error_rate` in dashboard. If error rate is high, check Anthropic status page.
2. Check logs for error type: `grep '"error":true' logs/app.jsonl | tail -20 | jq '.event'`
3. If 429 errors: verify rate limit tier and check for routing misconfiguration.
4. If 529 errors: verify circuit breaker is open and serving fallback.
5. If timeout errors: check p95 latency trend for gradual degradation vs. sudden spike.

### Eval score below target

1. Check for recent deploys: `git log --since="24 hours ago" --oneline`
2. Sample degraded responses: query SQLite for requests in the low-score window.
3. Compare prompt template to last known-good version.
4. If no deploy: check model version pin (Anthropic model behavior can shift).

### Cost spike

1. Check routing reason distribution: `grep routing_reason logs/app.jsonl | jq '.routing_reason' | sort | uniq -c`
2. Check output token distribution: `sqlite3 data/cost_log.db "SELECT MAX(output_tokens), AVG(output_tokens) FROM llm_calls WHERE ts > strftime('%s','now') - 3600;"`
3. If routing changed: check for new `complexity='high'` defaults in recent deploy.
4. If output tokens increased: check for prompt change that removed max_tokens constraint.

### Cache hit rate drop

1. Check for recent prompt template changes (cache key invalidation).
2. Wait 30-60 minutes for cache to warm up with the new prompt key.
3. If cache never recovers: verify that the system prompt prefix is stable across requests (no per-request timestamps or user IDs in the prefix).

---

## 7. Pre-Deploy Checklist

Before any production deploy that changes LLM prompts, models, or routing:

- [ ] Run chaos test suite: `pytest tests/test_chaos_integration.py -v`
- [ ] Verify all 5 failure modes pass
- [ ] Check that `ObsConfig` SLO targets are still appropriate for new behavior
- [ ] If prompt template changed: note the cache warmup period in the deploy description
- [ ] If model changed: update `MODEL_PRICING` in `CostAccountant` if pricing differs
- [ ] Confirm dashboard renders within 10 seconds of service restart
