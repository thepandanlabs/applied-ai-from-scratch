---
name: skill-ai-slo-template
description: Template defining 6 AI-specific SLIs with targets, alert thresholds, and error budget calculations for any production LLM feature
version: "1.0"
phase: "07"
lesson: "11"
tags: [slo, sli, alerting, observability, error-budget]
---

# AI Feature SLO Template

Copy this template into your service's ops runbook. Fill in every field before launch. Sign off that each SLI has an owner, a target, and a defined alert recipient.

## SLI Definitions

### 1. Availability
- **Definition:** Fraction of requests that receive a non-error response within the timeout window.
- **Measurement:** `count(non_error_responses) / count(total_requests)` over a 30-minute rolling window.
- **Target:** >= 99.5%
- **Alert (WARNING):** < 99.0% for 5 minutes
- **Alert (CRITICAL):** < 98.0% for 5 minutes, or any 5-minute window with > 5% errors
- **Owner:** [YOUR TEAM ONCALL]

### 2. Latency - Time to First Token (TTFT)
- **Definition:** Time from request received to first token of response delivered, p95 over 15-minute window.
- **Measurement:** Measured via streaming response timing in the API client.
- **Target:** p95 <= 2000ms
- **Alert (WARNING):** p95 > 3000ms for 10 minutes
- **Alert (CRITICAL):** p95 > 5000ms for 5 minutes
- **Owner:** [YOUR TEAM ONCALL]

### 3. Error Rate
- **Definition:** Fraction of requests that fail after all retries, excluding expected client errors (4xx from invalid input).
- **Measurement:** `count(5xx + non-retried 429) / count(total_requests)` over 15-minute window.
- **Target:** <= 1.0%
- **Alert (WARNING):** > 2.0% for 5 minutes
- **Alert (CRITICAL):** > 5.0% for 5 minutes
- **Owner:** [YOUR TEAM ONCALL]

### 4. Eval Score
- **Definition:** Mean quality score from your evaluation suite, computed on a sample of production traffic.
- **Measurement:** Run eval suite hourly on last 100 production requests. Report mean score.
- **Target:** >= 0.80 (replace with your metric: RAGAS answer_correctness, Braintrust score, custom rubric)
- **Alert (WARNING):** mean < 0.75 sustained over 3 hourly eval runs
- **Alert (CRITICAL):** mean < 0.70 sustained over 2 hourly eval runs
- **Owner:** [AI/ML TEAM]
- **Note:** This SLI requires your eval pipeline to be running in production before you can alert on it.

### 5. Cache Hit Rate
- **Definition:** Fraction of requests that hit the prompt cache (Anthropic prompt caching), over 1-hour window.
- **Measurement:** `cache_read_input_tokens > 0` in API response usage field.
- **Target:** >= 40% (adjust based on your prompt structure: higher for templated prompts, lower for freeform)
- **Alert (WARNING):** < 20% for 30 minutes
- **Alert (CRITICAL):** < 10% for 15 minutes
- **Owner:** [YOUR TEAM ONCALL]
- **Note:** Sudden drops in cache hit rate indicate a prompt template change that broke cache key stability.

### 6. Cost per Request
- **Definition:** Mean USD cost per LLM call (input + output tokens x model pricing), p95 over 1-hour window.
- **Measurement:** `(input_tokens x input_price + output_tokens x output_price)` per request.
- **Target:** p95 <= $0.005 (adjust based on your model and traffic)
- **Alert (WARNING):** p95 > $0.008 for 15 minutes
- **Alert (CRITICAL):** p95 > $0.015 for 10 minutes
- **Owner:** [YOUR TEAM ONCALL + FINANCE NOTIFICATION]

## Error Budget Calculation

```
Monthly error budget for each SLI:
  Availability 99.5%: 0.5% x 30d x 24h x 60m = 216 minutes allowed downtime
  Error rate 1.0%:    1.0% x monthly request volume = N allowed failed requests
  Eval score 0.80:    track cumulative hours below threshold (target < 5% of hours)

Burn rate alert thresholds:
  WARNING: consuming > 3x expected daily budget
  CRITICAL: consuming > 10x expected daily budget (will exhaust monthly budget in < 3 days)
```

## Pre-Launch Checklist

Before deploying an AI feature to production:

- [ ] All 6 SLI targets are defined (no "TBD")
- [ ] Alert thresholds are configured in your alerting system
- [ ] Each alert has a named owner (oncall rotation)
- [ ] Eval pipeline is running in production and emitting scores
- [ ] Baseline SLI values are established from load tests (Lesson 10)
- [ ] Error budget calculation is documented in the runbook
- [ ] Runbook includes remediation steps for each alert type

## Alert Routing

| Alert | Severity | Recipients | Response time |
|-------|----------|------------|---------------|
| Availability CRITICAL | Page | Oncall engineer | < 5 min |
| Latency CRITICAL | Page | Oncall engineer | < 10 min |
| Error rate CRITICAL | Page | Oncall engineer | < 5 min |
| Eval score WARNING | Ticket | AI team | < 4 hours |
| Eval score CRITICAL | Slack + ticket | AI team lead | < 1 hour |
| Cache hit rate WARNING | Ticket | Oncall engineer | < 4 hours |
| Cost CRITICAL | Page + finance notify | Oncall + finance | < 30 min |
