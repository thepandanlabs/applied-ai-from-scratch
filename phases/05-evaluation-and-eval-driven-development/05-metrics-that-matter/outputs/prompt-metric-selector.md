---
name: prompt-metric-selector
description: Prompt for choosing the right eval metrics given a system type and failure modes
version: "1.0"
phase: "05"
lesson: "05"
tags: [eval, metrics, rag, classification, extraction, agent]
---

# Prompt: Metric Selector for AI Systems

Use this prompt to identify the right eval metrics for any AI system. Paste the prompt into Claude with your system description filled in.

---

## The prompt

```
You are an AI evaluation expert. Given a description of an AI system and its known failure modes,
recommend the right eval metrics: what to measure, how to compute it, and what threshold to set
for pass/fail.

System description:
<TYPE: one of: RAG, open-ended Q&A, classification, extraction, multi-step agent, code generation>
<PURPOSE: what the system is supposed to do in one sentence>
<FAILURE MODES: list of known or suspected failure modes from your error analysis>

For each failure mode, recommend:
1. The metric name
2. How to compute it (exact match, fuzzy match, LLM judge, RAGAS scorer, custom rule)
3. The pass/fail threshold and why
4. Whether it should be segmented (by category, difficulty, or other dimension)

Then give me:
- The 3 most important metrics to start with (in priority order)
- Any metrics I should explicitly NOT use for this system type and why
- A one-line "actionability test" for each recommended metric:
  "If [metric] drops below [X], I will investigate [Y]."
```

---

## Metric reference by system type

### RAG systems

| Failure mode | Metric | How to compute | Threshold |
|---|---|---|---|
| Hallucinated answer | Faithfulness | RAGAS `faithfulness` | > 0.85 |
| Off-topic answer | Answer relevancy | RAGAS `answer_relevancy` | > 0.80 |
| Wrong source used | Context precision | RAGAS `context_precision` | > 0.75 |
| Incomplete retrieval | Context recall | RAGAS `context_recall` | > 0.70 |
| Factually wrong | LLM judge (correctness) | Custom judge prompt | > 0.75 |

### Classification systems

| Failure mode | Metric | How to compute | Threshold |
|---|---|---|---|
| Wrong category | Exact match (label) | `exact_match(expected_label, actual_label)` | > 0.90 |
| Confident wrong answer | Calibration | Compare confidence to accuracy | Error < 0.10 |
| Missed edge class | Per-class recall | Separate pass rate per class | > 0.80 each |

### Extraction systems

| Failure mode | Metric | How to compute | Threshold |
|---|---|---|---|
| Missing required fields | Format compliance | `format_compliance(output, required_keys)` | 1.0 |
| Wrong field value | Fuzzy match per field | `fuzzy_match(expected_val, actual_val)` | > 0.85 |
| Hallucinated fields | Extra keys check | count keys not in schema | 0 |

### Open-ended Q&A

| Failure mode | Metric | How to compute | Threshold |
|---|---|---|---|
| Wrong answer | LLM judge (correctness) | Custom judge: 1-5 rubric | >= 3 |
| Missing key info | Completeness | LLM judge checklist | >= 0.80 |
| Wrong tone/policy | Style compliance | LLM judge or keyword check | >= 0.90 |

### Multi-step agent

| Failure mode | Metric | How to compute | Threshold |
|---|---|---|---|
| Wrong tool call | Tool selection accuracy | Exact match on tool name | > 0.90 |
| Wrong final answer | End-to-end correctness | LLM judge on final output | >= 0.75 |
| Excessive steps | Step count | count(steps) vs expected | <= 1.5x expected |
| Tool call hallucination | Tool arg validity | Rule check on tool args | 0 invalid args |

---

## Segmentation rules

Always segment by difficulty (normal / edge / adversarial) as a baseline.

Add category segmentation when: the system handles multiple distinct topics and you expect
failure rates to differ by topic (they almost always do).

Add time segmentation when: you have enough volume to detect drift (typically 1,000+ cases/week).

**Never report only the overall metric without at least one segmentation dimension.**

---

## Thresholds: how to set them

1. Run your metrics on your current system to establish the baseline.
2. Set the threshold at (baseline - 5 percentage points) for a warning,
   (baseline - 10 percentage points) for a hard failure.
3. Exception: safety metrics. Set these at absolute thresholds (e.g., 0 harmful outputs per 1,000),
   not relative to your baseline.

---

## Vanity metrics to avoid

**Overall average score without segmentation:** hides regressions on hard cases.

**Thumbs up / thumbs down rate (raw):** user satisfaction is confounded by factors outside
your system (e.g., users are frustrated because of a shipping delay, not your AI).

**Response length as a proxy for quality:** longer is not better.

**Latency as a quality metric:** latency is an efficiency metric. Don't let it crowd out
correctness metrics in your eval dashboard.

**"Model confidence" from the LLM:** LLMs are not calibrated. Their self-reported confidence
scores do not correlate with factual accuracy.
