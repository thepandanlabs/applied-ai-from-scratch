# SLOs, SLIs, and Alerting for AI Features

> Define what good means before you ship. "Users are complaining" is not a metric.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Phase 07 Lessons 01-10 (observability, cost, latency), Phase 06 (shipping)
**Time:** ~45 min
**Learning Objectives:**
- Define SLIs and SLOs for the 6 key AI feature metrics
- Write error budgets that translate SLO targets into actionable thresholds
- Implement a `SLOMonitor` that tracks all 6 SLIs and emits structured alerts on breach
- Map SLO metrics to Prometheus format for Grafana integration
- Distinguish actionable alerts from noise alerts

---

## The Problem

You ship an AI feature with a 99.5% availability SLO because that is what all the other services have. Three months in, you get an escalation: "The AI answers are getting worse." You check your dashboards. Availability is 99.7%. Latency p95 is within bounds. Error rate is 0.3%. Everything is green.

But the AI answers have been getting worse for two weeks because the eval score SLI was never defined. Nobody picked a threshold. The metric was being collected but not monitored.

This is the gap between traditional service observability and AI feature observability. Traditional SLIs cover availability, latency, and error rate. Those are necessary but not sufficient. AI features have three additional SLIs that traditional monitoring systems do not know about: eval score (quality), cache hit rate (cost efficiency), and cost per request (budget health). If you only monitor the traditional three, you can have green dashboards while your AI feature silently degrades.

The fix is to define all 6 SLIs before you ship and set alert thresholds at the same time. This lesson builds the monitoring class and the alert logic.

---

## The Concept

### The 6 AI SLIs with Example Targets

```
+---------------------+------------------+------------------+------------------+
| SLI                 | What it measures | Target           | Alert threshold  |
+---------------------+------------------+------------------+------------------+
| Availability        | % requests that  | >= 99.5%         | < 99.0%          |
|                     | get a response   | (30-day window)  | for 5 min        |
+---------------------+------------------+------------------+------------------+
| Latency (TTFT)      | Time to first    | p95 < 2000ms     | p95 > 3000ms     |
|                     | token            | (1-hour window)  | for 10 min       |
+---------------------+------------------+------------------+------------------+
| Error rate          | % requests with  | < 1.0%           | > 2.0%           |
|                     | non-retried err  | (15-min window)  | for 5 min        |
+---------------------+------------------+------------------+------------------+
| Eval score          | Quality score    | >= 0.80 mean     | < 0.75 mean      |
|                     | from eval suite  | (24-hour window) | for 1 hour       |
+---------------------+------------------+------------------+------------------+
| Cache hit rate      | Prompt cache     | >= 40%           | < 20%            |
|                     | hits / total     | (1-hour window)  | for 30 min       |
+---------------------+------------------+------------------+------------------+
| Cost per request    | USD per LLM call | <= $0.005 mean   | > $0.008 mean    |
|                     | (incl. retries)  | (1-hour window)  | for 15 min       |
+---------------------+------------------+------------------+------------------+
```

### Error Budgets

An error budget converts a percentage SLO into an allowance you can spend:

```
99.5% availability SLO over 30 days
= 0.5% allowed downtime
= 0.005 x 30 days x 24 hours x 60 min = 216 minutes of allowed downtime

Error budget burn rate:
  Normal: consuming ~7 min/day of budget -> fine
  Alert:  consuming > 30 min/day (3x normal) -> investigate
  Page:   consuming > 100 min/day (14x normal) -> incident
```

Burn rate alerting catches budget exhaustion before it happens. If you are burning 14x the normal rate, you will exhaust your 30-day budget in 2 days.

---

## Build It

Install dependencies:

```bash
pip install pydantic
```

The `SLOMonitor` tracks rolling windows for each SLI and emits alerts when thresholds are breached:

```python
from slo_monitor import SLOMonitor, RequestEvent, AlertLevel

monitor = SLOMonitor()

# Record each LLM call
monitor.record(RequestEvent(
    ttft_ms=450,
    total_latency_ms=2100,
    error=False,
    cache_hit=True,
    cost_usd=0.0035,
    eval_score=0.87,
))

# Check for SLO breaches
alerts = monitor.check_slos()
for alert in alerts:
    print(f"[{alert.level}] {alert.sli_name}: {alert.message}")

# Get current status
status = monitor.status()
print(status.to_dict())
```

Expected output (healthy system):

```
SLO Status Report
-----------------
availability:    99.8% [OK]   (target: >= 99.5%)
ttft_p95:        980ms [OK]   (target: <= 2000ms)
error_rate:      0.2%  [OK]   (target: <= 1.0%)
eval_score_mean: 0.86  [OK]   (target: >= 0.80)
cache_hit_rate:  47%   [OK]   (target: >= 40%)
cost_p95:        $0.004 [OK]  (target: <= $0.005)
```

Expected output (SLO breach):

```
[WARNING] eval_score: Mean eval score 0.74 is below SLO target 0.80. 24-hour window. Breach duration: 72 min.
[WARNING] cache_hit_rate: Cache hit rate 18% is below SLO target 40%. 1-hour window. Breach duration: 35 min.
```

> **Real-world check:** Why is the eval_score SLI window 24 hours while the error_rate window is 15 minutes? Because eval scores require running your evaluation suite, which typically processes a sample of production traffic asynchronously. You cannot compute eval scores in real time. A 24-hour window is the minimum meaningful window if your eval pipeline runs once per hour over a 24-hour sample. If you alert on a 1-hour eval window, you are alerting on too few samples to be statistically meaningful.

Run the implementation:

```bash
python code/main.py
```

---

## Use It

Expose the SLO metrics in Prometheus format for Grafana:

```python
from prometheus_client import Gauge, start_http_server

# Define Prometheus gauges
slo_gauges = {
    "availability": Gauge("ai_slo_availability_ratio", "Availability SLI ratio"),
    "ttft_p95_ms": Gauge("ai_slo_ttft_p95_ms", "TTFT p95 in milliseconds"),
    "error_rate": Gauge("ai_slo_error_rate_ratio", "Error rate ratio"),
    "eval_score": Gauge("ai_slo_eval_score_mean", "Mean eval score"),
    "cache_hit_rate": Gauge("ai_slo_cache_hit_rate_ratio", "Cache hit rate ratio"),
    "cost_p95_usd": Gauge("ai_slo_cost_p95_usd", "Cost p95 in USD"),
}

def push_slo_metrics(monitor: SLOMonitor):
    status = monitor.status()
    slo_gauges["availability"].set(status.availability)
    slo_gauges["ttft_p95_ms"].set(status.ttft_p95_ms)
    slo_gauges["error_rate"].set(status.error_rate)
    slo_gauges["eval_score"].set(status.eval_score_mean)
    slo_gauges["cache_hit_rate"].set(status.cache_hit_rate)
    slo_gauges["cost_p95_usd"].set(status.cost_p95_usd)

# In your FastAPI app
start_http_server(9090)  # Prometheus scrapes :9090/metrics
```

> **Perspective shift:** Prometheus gauges feel like over-engineering when you first set them up, but they unlock a superpower: dashboards that your non-engineering stakeholders can read. A product manager looking at a Grafana dashboard with green/red SLO status panels can self-serve on "is the AI feature healthy?" without filing a ticket. The engineering cost is one afternoon of setup. The organizational benefit is eliminating a category of status questions.

---

## Ship It

The artifact for this lesson is `outputs/skill-ai-slo-template.md`: a template defining all 6 AI SLIs with example targets and alert thresholds, ready to customize for your service.

Copy the template into your service's ops runbook. Fill in your specific targets based on your load test baselines from Lesson 10. Define the alert routing (who gets paged for what level) before you ship.

---

## Evaluate It

**Pre-ship SLO review:** Before launching any AI feature, the team lead signs off that all 6 SLIs have a defined target, a defined alert threshold, and a defined alert owner. No SLI should have "TBD" next to it when you press deploy.

**Alert noise audit:** After one week of alerts in production, count the false-positive rate: alerts that fired but resolved without any engineering action. If more than 20% of alerts are false positives, the threshold is too sensitive. Widen it. If more than 10% of incidents had no prior alert, the threshold is too lax. Tighten it.

**Error budget review:** Weekly review of error budget consumption across all 6 SLIs. If any SLI is consuming budget faster than 2x the expected rate, it is a leading indicator of a future SLO miss. Act before the monthly report shows a breach.
