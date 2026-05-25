---
name: skill-drift-detection
description: Patterns and runbook for detecting quality drift and prompt/model regressions in production AI systems
version: "1.0"
phase: "05"
lesson: "12"
tags: [eval, drift, regression, monitoring, production]
---

# Drift and Regression Detection Guide

## What This Is

A reusable guide for detecting quality degradation in production AI systems. Covers two scenarios: drift (quality changes you didn't cause) and regression (quality changes caused by your own changes).

---

## Drift Taxonomy

```
INPUT DRIFT
  What it is:   User query distribution shifts (new user segments, new topics)
  Signal:       Score drops on specific query categories, not all traffic
  Diagnostic:   Cluster recent low-scoring inputs. New cluster = new input type.

OUTPUT DRIFT
  What it is:   Model behavior changes without input changes
  Signal:       Score drops uniformly across all query types
  Diagnostic:   Pin old model version, re-run golden set. Different result = model changed.

CONCEPT DRIFT
  What it is:   The "right answer" changes (policy update, world event)
  Signal:       Human reviewers disagree with LLM judge on recent cases
  Diagnostic:   Pull cases from before/after the event. Compare judge vs human scores.
```

---

## ScoreHistory Pattern

```python
from score_history import ScoreHistory

history = ScoreHistory("score_history.json")

# Add daily score (call from your online eval summary job)
history.add("2025-04-01", 0.88, version="prompt-v3")

# Check for trend drift
drift = history.detect_drift(threshold=0.05, window=7)
if drift["drift_detected"]:
    print(f"Drift: {drift['previous_mean']:.3f} -> {drift['current_mean']:.3f} (drop={drift['drop']:.3f})")

# Check absolute floor
alert = history.absolute_alert(floor=0.70)
if alert["alert"]:
    print(f"Floor breach: {alert['score']:.3f} on {alert['date']}")
```

---

## Alerting Thresholds Guide

| Threshold type | Formula | When to use |
|---|---|---|
| Absolute floor | `score < 0.70` | Catastrophic failure floor. Always set. |
| Trend drift (loose) | 7-day mean drops >5% | General production monitoring. Default. |
| Trend drift (strict) | 7-day mean drops >3% | High-stakes applications, medical, legal. |
| Trend drift (noisy) | 7-day mean drops >8% | High-variance metrics like creativity scores. |

Rules:
- Use both absolute AND trend thresholds. Absolute catches catastrophic failures fast. Trend catches gradual decay.
- Never set an absolute threshold lower than your current average - 15%. That's a floor, not a monitoring signal.
- Recalibrate thresholds after each major prompt change. The baseline shifts.

---

## Regression Comparison Workflow

Before every deploy that changes prompts, models, or retrieval config:

**1. Save baseline from current production.**
```python
detector = RegressionDetector()
detector.save_baseline("feature-name", current_metrics)
```

**2. Run new version against golden set.**
```python
new_metrics = run_eval_suite("feature-name-v2")
```

**3. Compare and flag.**
```python
comparisons = detector.compare("feature-name", new_metrics, threshold=0.03)
detector.report()
```

**4. Block deploy if any metric regresses.**
```python
regressions = [c for c in comparisons if c["regressed"]]
if regressions:
    sys.exit(1)  # Fail CI
```

Threshold guide for regression detection:
- 0.03 (3% drop): standard for production features
- 0.05 (5% drop): acceptable for exploratory changes with high upside
- 0.01 (1% drop): use for safety-critical metrics only (format compliance, safety scores)

---

## Model Provider Update Checklist

When your model provider announces a model update:

- [ ] Pin your model to a dated version ID (e.g., `claude-opus-4-5-20251101`) before the update rolls out
- [ ] Run your full golden set against both old and new model versions
- [ ] If scores differ by more than your regression threshold, investigate the specific cases
- [ ] Check provider release notes for behavior changes relevant to your use case
- [ ] Update your golden set if new behavior is "correct but different" (concept drift)
- [ ] If new version regresses, stay pinned to old version and file a support ticket
- [ ] Log the model version in every eval entry so you can bisect score drops later

---

## Detection Lag vs Threshold Tradeoff

With a 7-day rolling window:

| Quality drop | 5% threshold | 3% threshold |
|---|---|---|
| 5% quality drop | Detected in ~3 days | Detected in ~2 days |
| 10% quality drop | Detected in ~2 days | Detected in ~1 day |
| 2% quality drop | Not detected (noise) | Sometimes detected |

Rule of thumb: to detect a Q% drop in D days using a 7-day window, set threshold to roughly `(Q/10) * (D/7)`. More sensitive threshold = more false alarms.

If you're getting too many false alarms: raise the threshold or extend the window. If you're detecting drift too slowly: lower the threshold or use a shorter window.
