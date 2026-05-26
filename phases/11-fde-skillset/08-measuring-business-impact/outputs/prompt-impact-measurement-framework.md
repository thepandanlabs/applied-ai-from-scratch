---
name: prompt-impact-measurement-framework
description: Framework for connecting AI model metrics to business KPIs and structuring the pilot instrumentation conversation
version: "1.0"
phase: "11"
lesson: "08"
tags: [fde, business-impact, metrics, pilot, kpi]
---

# Impact Measurement Framework

Use this framework before a pilot starts to align on which metrics to capture and how to translate them into business outcomes at the end.

---

## The Three-Layer Metric Chain

Every AI pilot produces metrics at three levels. You must capture all three, or the renewal conversation will fail.

```
LAYER 1: TECHNICAL
  What engineers measure. Meaningless to business stakeholders.
  Examples: accuracy, F1, BLEU, RAGAS faithfulness, latency p95

  |-- translate to -->

LAYER 2: OPERATIONAL
  What the system does in production. Meaningful to operations and team leads.
  Examples: task success rate, escalation rate, time-to-resolution,
            first-contact resolution, error rate

  |-- translate to -->

LAYER 3: BUSINESS
  What the business cares about. The renewal decision is made here.
  Examples: agent hours saved per month, cost per transaction,
            customer satisfaction score, revenue influenced, errors avoided
```

---

## Pre-Pilot Alignment Checklist

Before the pilot starts, align with the customer on:

- [ ] What is the baseline for each operational metric? (Measure it now, before AI goes live)
- [ ] What does "task success" mean for this use case? (Define it with the customer)
- [ ] How will we capture operational metrics? (Logging plan, not an afterthought)
- [ ] What is the business KPI that will determine renewal? (Get this in writing)
- [ ] Who is the business stakeholder who will use the impact data to make the renewal decision?

---

## Baseline Metrics Template

Capture these before the pilot period begins:

```json
{
  "task_success_rate": 0.0,
  "escalation_rate": 0.0,
  "avg_resolution_seconds": 0.0,
  "avg_customer_satisfaction": 0.0,
  "cost_per_transaction": 0.0,
  "volume_per_day": 0,
  "measurement_period": "YYYY-MM-DD to YYYY-MM-DD",
  "data_source": "manual review of N=X interactions"
}
```

If you cannot get the baseline before the pilot, the pilot cannot prove improvement. This is non-negotiable.

---

## Metric Translation Table

Use this to translate your eval metric to a business KPI.

| Eval Metric | Operational Metric | Business KPI |
|-------------|-------------------|--------------|
| Classifier accuracy 0.84 | 84% of tickets routed correctly | Agent hours saved: baseline escalation rate x volume x time per escalation |
| Retrieval recall 0.91 | 91% of queries answered without escalation | Self-service deflection rate improvement |
| Answer faithfulness 0.88 | Customer satisfaction proxy score | NPS improvement (requires survey data) |
| Latency p95: 1.2s | 96% of queries completed under SLA | Abandonment rate reduction |
| Error rate: 3% | 3% of interactions need manual correction | Re-work cost avoided per quarter |

---

## The Renewal Argument Template

Use this structure at the QBR:

```
Before: [operational metric at baseline] resulting in [business cost or pain].
After:  [operational metric in pilot] resulting in [business value].
Delta:  [specific improvement: X hours saved, Y% fewer escalations, $Z cost reduction].
Projection: At full deployment volume of [N] interactions per day, this translates to [annual business value].
```

Example:
"Before the pilot, your support team escalated 34% of Tier 1 tickets to senior agents, each escalation adding an average of 3 minutes of agent time. After 4 weeks with the AI routing system, the escalation rate dropped to 18%, saving approximately 180 agent-hours per month. At full deployment across your 800 daily tickets, this projects to 540 agent-hours saved per month."

---

## Common Mistakes to Avoid

- **Measuring only the eval metric.** An accuracy score with no operational context is not a renewal argument.
- **Skipping the baseline.** Without before/after, you cannot show improvement. "Our system achieves 84% accuracy" means nothing without "vs. 68% manual routing."
- **Selecting metrics after the pilot.** Cherry-picking the metrics that look good destroys credibility. Define all metrics before the pilot starts.
- **Measuring what is easy, not what matters.** Latency is easy to measure. Agent hours saved is harder but it is what the VP cares about.
- **Not involving the business stakeholder until the QBR.** The person who makes the renewal decision should review the measurement plan before the pilot, not after.

---

## Instrumenting Your Pilot: Minimal Logging Schema

For every interaction in the pilot, log:

```python
{
    "interaction_id": "unique-id",
    "timestamp": "ISO-8601",
    "model_quality_score": 0.0,      # your eval metric
    "task_success": True,             # did it accomplish the goal?
    "time_to_resolution_seconds": 0,  # total elapsed time
    "escalation_required": False,     # did a human need to intervene?
    "customer_satisfaction_proxy": 0.0  # e.g., no repeat inquiry = 1.0
}
```

This schema captures all three layers. Add business-specific fields as needed.
