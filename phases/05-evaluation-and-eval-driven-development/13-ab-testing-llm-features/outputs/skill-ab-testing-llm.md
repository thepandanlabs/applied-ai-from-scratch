---
name: skill-ab-testing-llm
description: Templates and decision guide for running statistically rigorous A/B tests on LLM features
version: "1.0"
phase: "05"
lesson: "13"
tags: [eval, ab-testing, experimentation, statistics, production]
---

# A/B Testing LLM Features: Templates and Guide

## What This Is

A reusable guide for running clean, statistically rigorous A/B tests on AI features. Includes templates for traffic routing and analysis, sample size guidance, a pitfall checklist, and a decision template for calling a test.

---

## ABRouter Template

```python
import hashlib
import json
import time
from pathlib import Path
from typing import Literal

Variant = Literal["A", "B"]

class ABRouter:
    def __init__(self, experiment_name: str, split: float = 0.50,
                 exposure_log: str = "exposures.jsonl",
                 outcome_log: str = "outcomes.jsonl"):
        self.experiment_name = experiment_name
        self.split = split
        self.exposure_log = Path(exposure_log)
        self.outcome_log = Path(outcome_log)

    def assign(self, user_id: str) -> Variant:
        key = f"{self.experiment_name}:{user_id}"
        bucket = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100
        return "B" if bucket < int(self.split * 100) else "A"

    def log_exposure(self, user_id: str, variant: Variant) -> None:
        entry = {"experiment": self.experiment_name, "user_id": user_id,
                 "variant": variant, "timestamp": time.time()}
        with open(self.exposure_log, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_outcome(self, user_id: str, variant: Variant,
                    metric_name: str, value: float) -> None:
        entry = {"experiment": self.experiment_name, "user_id": user_id,
                 "variant": variant, "metric": metric_name,
                 "value": value, "timestamp": time.time()}
        with open(self.outcome_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
```

---

## Sample Size Calculator Guide

Before starting any test, compute the required sample size.

```python
from scipy.stats import norm
import math

def required_sample_size(
    baseline_mean: float,
    min_detectable_effect: float,  # absolute change you want to detect
    std_dev: float,
    alpha: float = 0.05,           # false positive rate
    power: float = 0.80,           # probability of detecting a real effect
) -> int:
    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)
    n = 2 * ((z_alpha + z_beta) ** 2 * std_dev ** 2) / (min_detectable_effect ** 2)
    return math.ceil(n)

# Example: detect a 0.04 quality score improvement
n = required_sample_size(
    baseline_mean=0.85,
    min_detectable_effect=0.04,
    std_dev=0.08,
    alpha=0.05,
    power=0.80,
)
print(f"Required per variant: {n}")  # ~313
```

Quick reference (std_dev=0.08, alpha=0.05, power=0.80):

| Effect size | Samples per variant | Days at 100 users/day |
|---|---|---|
| 0.02 (2% lift) | ~1,252 | ~13 days |
| 0.04 (4% lift) | ~313 | ~4 days |
| 0.08 (8% lift) | ~79 | ~1 day |
| 0.10 (10% lift) | ~51 | same day |

---

## Pitfall Checklist

Before calling a test winner, check all of these:

- [ ] **Novelty effect**: Has the test run at least 2 full weeks? New features inflate engagement for 1-2 weeks regardless of quality.
- [ ] **Carryover effect**: Is assignment deterministic by user_id? If a user saw variant A and then got switched to B, their behavior is contaminated.
- [ ] **Seasonal confound**: Does your test span weekends and weekdays? Different user populations behave differently.
- [ ] **Peeking early**: Did you look at results before hitting your pre-registered sample size? Early stopping inflates false positives.
- [ ] **Multiple metrics**: Did you pre-register your primary metric? Post-hoc metric selection is p-hacking.
- [ ] **Balance check**: Are variant A and B within 5% of equal size? Imbalance suggests a router bug.
- [ ] **Holdout check**: Does any user appear in both variants? Should be impossible with deterministic routing.
- [ ] **A/A test**: Did you run the same variant against itself and confirm no significant result? If yes, your infrastructure is working.

---

## Decision Template

Use this when a test reaches its sample size:

**Question 1: Is the primary metric significant?**
- Yes, p < 0.05: proceed to question 2.
- No: do not ship B based on this metric alone. If you still want to ship B, document why (e.g., secondary metric, qualitative feedback) and tag it as a judgment call, not an evidence-based decision.

**Question 2: Did any secondary metric regress significantly?**
- Regression found: investigate before shipping. A quality improvement that causes a latency regression may not be worth it.
- No regressions: proceed to question 3.

**Question 3: Have all pitfalls been checked?**
- Any unchecked pitfalls: address them or extend the test.
- All clear: ship B.

**Question 4: How will you monitor post-ship?**
- Document your expected metric range for B in production.
- Set an online eval alert for 7 days post-ship.
- Schedule a review at day 7 and day 30.

---

## What A/B Testing Doesn't Answer

A/B tests answer: "is B better than A on these metrics?" They do not answer:
- "Is this AI feature better than no AI feature?" (use a holdout group)
- "Is the quality improvement worth the latency cost?" (that's a product decision, not a stat test)
- "Will B still be better in 3 months?" (quality drifts; re-test periodically)
- "Why is B better?" (A/B testing is confirmatory, not explanatory; use error analysis for explanation)
