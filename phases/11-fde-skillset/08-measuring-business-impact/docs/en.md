# Measuring Business Impact

> If you cannot translate your eval score into a dollar amount or a time saving, the customer cannot justify the renewal.

**Type:** Build
**Languages:** Python
**Prerequisites:** 11-02 (scoping before solving), 05-01 (eval-driven development basics)
**Time:** ~45 min
**Phase:** 11 · FDE Skillset

---

## Learning Objectives

- Describe the three-layer metric translation chain from eval score to business KPI
- Instrument a pilot to capture business metrics alongside model metrics from day one
- Compute the correlation between model quality and business outcome for a pilot scenario
- Build an ImpactTracker that logs both metric layers and surfaces the relationship
- Frame business results in the language stakeholders act on: time, cost, error rate

---

## The Problem

You ran a successful pilot. Your eval score went from 0.74 to 0.84. Retrieval precision improved. The model is grounding its answers better. You are proud of the work.

You present this at the quarterly business review. The VP of Customer Success stares at you and says: "That is great. What does it mean for my team?"

You do not have an answer. You measured the thing you knew how to measure, which was the model. You did not instrument the thing the customer cares about, which was their team's performance.

This is one of the most common FDE gaps. Engineers are trained to measure model quality, not business outcomes. But the customer's renewal decision is based entirely on business outcomes. "Our eval accuracy went from 0.74 to 0.84" does not renew a contract. "Your support agents now handle 84% of Tier 1 tickets without escalation, up from 74%, saving approximately 200 agent-hours per month" does.

The solution is not to stop measuring model metrics. It is to build the business metric capture into the pilot from day one, so you always have both layers available.

---

## The Concept

### The Three-Layer Metric Chain

```
LAYER 1: TECHNICAL (eval metrics)
  What engineers measure
  Examples: accuracy, F1, BLEU, RAGAS faithfulness, answer relevance
  Audience: the FDE team
  Problem: meaningless to business stakeholders

         |
         | translation required
         v

LAYER 2: OPERATIONAL (task success metrics)
  What the system actually does in production
  Examples: ticket correctly routed (yes/no), time-to-resolution,
            escalation rate, first-contact resolution rate
  Audience: team leads, operations managers
  Problem: not yet connected to dollars or strategic KPIs

         |
         | translation required
         v

LAYER 3: BUSINESS (KPI metrics)
  What the business cares about
  Examples: cost per ticket, agent utilization, customer satisfaction score,
            revenue influenced, errors avoided, hours saved per week
  Audience: VPs, executives, budget owners
  The renewal decision is made here.
```

### The Translation Table

```
+------------------------+---------------------------+---------------------------+
| EVAL METRIC            | OPERATIONAL METRIC        | BUSINESS KPI              |
+------------------------+---------------------------+---------------------------+
| Classifier accuracy    | % tickets routed          | Agent hours saved / week  |
|   0.84                 |   correctly               |   ~200 hrs/month          |
+------------------------+---------------------------+---------------------------+
| Retrieval recall       | % queries answered        | Self-service deflection   |
|   0.91                 |   without escalation      |   rate: 40% -> 58%        |
+------------------------+---------------------------+---------------------------+
| Answer faithfulness    | Customer satisfaction     | NPS improvement           |
|   0.88                 |   proxy score             |   +12 points              |
+------------------------+---------------------------+---------------------------+
| Latency p95: 1.2s      | % queries completed       | Abandonment rate          |
|                        |   under SLA               |   12% -> 4%               |
+------------------------+---------------------------+---------------------------+
| Error rate: 3%         | % interactions needing    | Re-work cost avoided      |
|                        |   manual correction       |   $18k/quarter            |
+------------------------+---------------------------+---------------------------+
```

### Instrumenting the Pilot

The business metric capture must be built before the pilot goes live. You cannot instrument retroactively with enough fidelity to convince a skeptical executive.

```
PILOT INSTRUMENTATION PLAN

For every interaction in the pilot, log:
  - interaction_id
  - timestamp
  - model_quality_score       (your eval metric, 0-1)
  - task_success              (did the system accomplish the goal? boolean)
  - time_to_resolution        (how long did this take vs. baseline?)
  - escalation_required       (did a human need to intervene?)
  - customer_satisfaction     (proxy: was the next action a repeat inquiry?)

At the end of the pilot period:
  - Aggregate all three layers
  - Compute correlation between model_quality_score and task_success
  - Translate task_success rate into business KPI using baseline numbers
  - Present: "Before: X. After: Y. Delta: Z units of business value."
```

---

## Build It

### Step 1: Setup

```python
# pip install anthropic
# Set ANTHROPIC_API_KEY in environment

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import correlation, mean, stdev
from typing import Optional

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
```

### Step 2: The Interaction Data Model

```python
@dataclass
class Interaction:
    interaction_id: str
    timestamp: str
    query: str
    model_response: str
    model_quality_score: float    # eval layer: 0.0 - 1.0
    task_success: bool            # operational layer: did it accomplish the goal?
    time_to_resolution_seconds: float    # operational: time taken
    escalation_required: bool     # operational: human intervention needed?
    customer_satisfaction_proxy: float   # 0.0 - 1.0, e.g. no repeat inquiry = 1.0


@dataclass
class PilotMetrics:
    interactions: list[Interaction] = field(default_factory=list)

    @property
    def avg_model_quality(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(i.model_quality_score for i in self.interactions)

    @property
    def task_success_rate(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(1.0 if i.task_success else 0.0 for i in self.interactions)

    @property
    def escalation_rate(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(1.0 if i.escalation_required else 0.0 for i in self.interactions)

    @property
    def avg_resolution_seconds(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(i.time_to_resolution_seconds for i in self.interactions)

    @property
    def quality_success_correlation(self) -> Optional[float]:
        if len(self.interactions) < 3:
            return None
        quality_scores = [i.model_quality_score for i in self.interactions]
        success_scores = [1.0 if i.task_success else 0.0 for i in self.interactions]
        try:
            return correlation(quality_scores, success_scores)
        except Exception:
            return None
```

### Step 3: The Model Quality Scorer

```python
QUALITY_SCORE_PROMPT = """You are evaluating the quality of an AI system response in a support ticket context.

Customer query: {query}
AI response: {response}
Expected behavior: {expected}

Score the response on a scale from 0.0 to 1.0:
- 1.0: Fully correct, directly addresses the query, no hallucination, actionable
- 0.7-0.9: Mostly correct with minor gaps or unnecessary hedging
- 0.4-0.6: Partially correct, misses key information, or partially wrong
- 0.1-0.3: Mostly incorrect or misleading
- 0.0: Completely wrong, harmful, or no response

Return only a JSON object:
{{"score": <float 0.0-1.0>, "reason": "<one sentence>"}}"""


def score_model_quality(query: str, response: str, expected: str) -> tuple[float, str]:
    """Score a model response using Claude as judge. Returns (score, reason)."""
    prompt = QUALITY_SCORE_PROMPT.format(
        query=query,
        response=response,
        expected=expected,
    )

    result = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = result.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    data = json.loads(raw)
    return float(data["score"]), data["reason"]
```

### Step 4: Business Impact Translator

```python
TRANSLATE_PROMPT = """You are translating pilot metrics into business impact language for an executive audience.

Pilot context: {context}
Baseline metrics (before AI): {baseline}
Pilot metrics (with AI): {pilot_metrics}

Translate these results into business impact. Return a JSON object:
{{
  "headline": "<one sentence: the most important result, in business terms>",
  "time_saved_per_month": "<estimated hours or minutes saved per month, with reasoning>",
  "cost_impact": "<estimated cost impact if applicable, or 'requires cost-per-hour data from customer'>",
  "error_reduction": "<reduction in errors or escalations, expressed as percentage and absolute number>",
  "renewal_argument": "<one to two sentences a VP would use to justify renewing the contract>"
}}

Use concrete numbers. Do not hedge with 'potentially' or 'might'. If a number requires customer data you do not have, say what data is needed."""


def translate_to_business_impact(
    context: str,
    baseline: dict,
    pilot: PilotMetrics,
) -> dict:
    """Translate pilot metrics into business impact language."""
    pilot_summary = {
        "avg_model_quality": round(pilot.avg_model_quality, 3),
        "task_success_rate": round(pilot.task_success_rate, 3),
        "escalation_rate": round(pilot.escalation_rate, 3),
        "avg_resolution_seconds": round(pilot.avg_resolution_seconds, 1),
        "quality_success_correlation": round(pilot.quality_success_correlation or 0.0, 3),
        "total_interactions": len(pilot.interactions),
    }

    prompt = TRANSLATE_PROMPT.format(
        context=context,
        baseline=json.dumps(baseline, indent=2),
        pilot_metrics=json.dumps(pilot_summary, indent=2),
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    return json.loads(raw)
```

### Step 5: Report Printer

```python
def print_impact_report(
    pilot: PilotMetrics,
    business_impact: dict,
    baseline: dict,
) -> None:
    """Print the full three-layer impact report."""
    print("\n" + "=" * 60)
    print("PILOT IMPACT REPORT")
    print("=" * 60)

    print("\n--- LAYER 1: TECHNICAL (Model Quality) ---")
    print(f"Average model quality score: {pilot.avg_model_quality:.3f}")
    q_corr = pilot.quality_success_correlation
    if q_corr is not None:
        print(f"Quality-to-success correlation: {q_corr:.3f}")
    print(f"Total interactions evaluated: {len(pilot.interactions)}")

    print("\n--- LAYER 2: OPERATIONAL (Task Performance) ---")
    print(f"Task success rate: {pilot.task_success_rate:.1%}")
    baseline_success = baseline.get("task_success_rate", 0)
    if baseline_success:
        delta = pilot.task_success_rate - baseline_success
        print(f"  vs. baseline: {baseline_success:.1%}  (delta: {delta:+.1%})")
    print(f"Escalation rate: {pilot.escalation_rate:.1%}")
    baseline_esc = baseline.get("escalation_rate", 0)
    if baseline_esc:
        delta_esc = pilot.escalation_rate - baseline_esc
        print(f"  vs. baseline: {baseline_esc:.1%}  (delta: {delta_esc:+.1%})")
    print(f"Avg resolution time: {pilot.avg_resolution_seconds:.0f}s")
    baseline_time = baseline.get("avg_resolution_seconds", 0)
    if baseline_time:
        time_delta = pilot.avg_resolution_seconds - baseline_time
        print(f"  vs. baseline: {baseline_time:.0f}s  (delta: {time_delta:+.0f}s)")

    print("\n--- LAYER 3: BUSINESS (KPI Impact) ---")
    print(f"Headline: {business_impact.get('headline', 'N/A')}")
    print(f"Time saved per month: {business_impact.get('time_saved_per_month', 'N/A')}")
    print(f"Cost impact: {business_impact.get('cost_impact', 'N/A')}")
    print(f"Error reduction: {business_impact.get('error_reduction', 'N/A')}")
    print(f"\nRenewal argument:\n  {business_impact.get('renewal_argument', 'N/A')}")

    print("\n" + "=" * 60)
```

> **Real-world check:** Your customer's CFO says: "The pilot shows good accuracy numbers but we need to see ROI before we commit to a full deployment. We spent $40k on the pilot." How do you use the ImpactTracker output to build the ROI case, and what additional data do you need from the customer?

---

## Use It

Run the demo scenario: a support ticket classification pilot for a SaaS customer.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --demo
```

The demo generates 50 synthetic interactions with model quality scores and operational metrics, runs the business impact translation, and prints the three-layer report.

Example output structure:
- Layer 1: avg model quality 0.83, quality-success correlation 0.71
- Layer 2: task success rate 84% (vs. 68% baseline), escalation rate 18% (vs. 34% baseline)
- Layer 3: "Support agents now handle 84% of Tier 1 tickets without escalation, saving approximately 180 agent-hours per month"

To run the tracker against your own interaction data:

```bash
python main.py --from-json interactions.json --baseline baseline.json
```

The JSON format for interactions follows the `Interaction` dataclass fields. The baseline file is a simple dict with `task_success_rate`, `escalation_rate`, and `avg_resolution_seconds`.

> **Perspective shift:** A senior engineer on your team says: "We should focus on improving the model, not tracking business metrics. That is the product manager's job." How do you explain why business metric instrumentation is part of the engineer's job on an FDE engagement, not a separate responsibility?

---

## Ship It

The output for this lesson is `outputs/prompt-impact-measurement-framework.md`. It is a reusable framework for structuring the business impact conversation with customers before a pilot starts.

The runnable tool is `code/main.py`:

```bash
python main.py --demo
```

---

## Evaluate It

**Check 1: Does the correlation metric make sense?**
A quality-success correlation above 0.6 means your eval metric is a useful proxy for operational success. Below 0.4 means your eval is measuring something that does not predict real-world task success. Run the demo and check the correlation value. If it is very low in your real pilot data, your eval metric needs to change.

**Check 2: Does the business impact translation use concrete numbers?**
The output of `translate_to_business_impact` should include specific numbers, not vague language. "Approximately 180 agent-hours per month" is acceptable. "Potentially significant time savings" is not. If the output is vague, the prompt needs more explicit instructions to use numbers.

**Check 3: Does the three-layer report tell a coherent story?**
The technical metric, operational metric, and business metric should form a consistent chain. If the model quality is high (0.85) but the task success rate is low (55%), the chain is broken and you need to investigate why good eval scores are not translating to operational success. This is a sign that your eval metric does not match real usage.

**Check 4: Can you generate the renewal argument from the report alone?**
Take the Layer 3 output and read it to a non-technical person. Can they understand the business case without explanation? If they need you to explain the context, the framing needs work.
