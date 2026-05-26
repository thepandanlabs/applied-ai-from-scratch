---
name: skill-feature-flag-pattern
description: Reusable feature flag pattern for AI services with deterministic user routing, shadow mode, canary, and A/B rollout ladder
version: "1.0"
phase: "06"
lesson: "13"
tags: [feature-flags, rollout, shadow-mode, canary, ab-testing, production]
---

# Feature Flag Pattern for AI Services

Use this pattern when releasing a new prompt version, model upgrade, or config change to production. Always start with shadow mode before canary.

---

## The Rollout Ladder

```
Step 1: Shadow   - run new version in parallel, compare on real traffic, zero user risk
Step 2: Canary   - 5% of users see new version, monitor for 24-48h
Step 3: Canary   - 25% of users see new version, monitor for 24-48h
Step 4: Canary   - 50% of users see new version, monitor for 24-48h
Step 5: Full     - remove flag, new version is the default
```

Move up the ladder only when the promotion criteria are met (see below). Roll back immediately if any threshold is exceeded.

---

## Minimal FeatureFlag Implementation

```python
import hashlib
from dataclasses import dataclass
from enum import Enum


class RolloutMode(str, Enum):
    SHADOW = "shadow"
    CANARY = "canary"
    AB = "ab"


@dataclass
class FeatureFlag:
    name: str           # unique flag ID, used in hash key
    rollout_pct: float  # 0-100, percentage assigned to variant B
    mode: RolloutMode
    variant_a: str      # current production prompt version
    variant_b: str      # new prompt version under test

    def variant_for(self, user_id: str) -> str:
        """Deterministic: same user_id always gets the same variant."""
        key = f"{self.name}:{user_id}"
        digest = hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()
        bucket = int(digest[:8], 16) % 100
        return "b" if bucket < self.rollout_pct else "a"
```

---

## Promotion Criteria Checklist

Before moving from shadow to canary, confirm all of the following from shadow logs:

- [ ] Variant B produces coherent, on-topic responses for at least 50 shadow comparison samples
- [ ] Variant B response length is within 30% of variant A average length
- [ ] Variant B latency p95 is within 20% of variant A latency p95
- [ ] No safety or refusal incidents in variant B outputs
- [ ] Shadow logging is working: both `a_tokens` and `b_tokens` appear in logs

Before moving from 5% canary to 25%, confirm:

- [ ] User error rate for variant B users is not higher than variant A users
- [ ] No increase in user escalations or support tickets from variant B cohort
- [ ] Eval suite (from Phase 05) shows improvement or no regression on key metrics
- [ ] At least 200 real variant B requests observed (not just shadow)

---

## Shadow Mode Quick Reference

Shadow mode runs both variants but returns only variant A to users:

```python
def run_shadow(flag, user_id, user_message, model_id):
    result_a = call_model(flag.variant_a, user_message, model_id)
    result_b = call_model(flag.variant_b, user_message, model_id)

    # Log for comparison - this feeds your eval harness
    logger.info(
        "shadow_compare flag=%s user=%s a_tokens=%d b_tokens=%d",
        flag.name, user_id,
        result_a["output_tokens"], result_b["output_tokens"],
    )

    # Return A to the user - B is never shown
    return {**result_a, "shadow_b_text": result_b["text"]}
```

**Important:** In shadow mode, double-check that the HTTP response always contains variant A's `prompt_version`. If variant B's prompt version appears in the response, shadow mode is misconfigured and users are seeing the wrong output.

---

## Rollback Procedure

If a canary deployment is showing problems:

1. Change `rollout_pct` to 0 (routes all traffic back to variant A):
   ```python
   ACTIVE_FLAG = FeatureFlag(
       name="prompt-v1.1-rollout",
       rollout_pct=0.0,     # back to 0
       mode=RolloutMode.CANARY,
       variant_a="v1.0",
       variant_b="v1.1",
   )
   ```

2. Redeploy. No service restart required for rollout_pct change if flag is loaded from config.

3. Verify with `/flag-preview/{some_user_id}` that all users return variant A.

---

## Flag Lifecycle

```
Created -> Shadow -> Canary 5% -> Canary 25% -> Canary 50% -> Full -> Removed
```

After full rollout, the flag must be removed and variant B becomes the default. Track flag removal in your deployment checklist. Dead flags accumulate and create confusion about what is actually routing traffic.

---

## Distribution Check

Use this snippet to verify that your hash function distributes users uniformly:

```python
from collections import Counter

flag = FeatureFlag("my-flag", rollout_pct=10.0, mode=RolloutMode.CANARY, ...)
buckets = Counter(flag.variant_for(f"user-{i}") for i in range(10_000))
pct_b = buckets["b"] / 10_000 * 100
print(f"B: {pct_b:.1f}%  (expected: {flag.rollout_pct:.0f}%)")
# Should be within 0.5% of the target
```
