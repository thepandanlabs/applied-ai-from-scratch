---
name: skill-online-eval-pipeline
description: Architecture guide and runbook for setting up async online eval pipelines in production
version: "1.0"
phase: "05"
lesson: "11"
tags: [eval, online-eval, feedback-loop, production, async]
---

# Online Eval Pipeline: Architecture and Runbook

## What This Is

A reusable guide for building and operating an async online eval pipeline. Online evals run on sampled production traffic, score it in the background, and surface quality trends without adding user-facing latency.

---

## Architecture Diagram

```mermaid
flowchart LR
    U[User Request] --> API[API Handler]
    API --> R[Response to User]
    API --> Q[Eval Queue]
    Q --> W[Eval Worker]
    W --> J[LLM Judge]
    J --> L[Score Log]
    F[User Feedback] --> FE[/feedback endpoint]
    FE --> L
    L --> S[Summary + Alerts]
```

The key invariant: the eval queue is fire-and-forget. The API handler enqueues and returns immediately. Users never wait for scoring.

---

## Sampling Strategy

| Traffic volume | Sample rate | Target evals/day |
|----------------|-------------|------------------|
| Under 1,000 req/day | 100% | all traffic |
| 1,000-10,000 req/day | 10-20% | 100-2,000 |
| Over 10,000 req/day | 5-10% | 500-1,000 |

Always override sample rate to 100% for:
- Inputs matching risk patterns (long inputs, out-of-scope topics)
- Interactions that received explicit thumbs-down feedback
- Inputs from new user segments not in your golden set

Target minimum: 100 sampled evals per day to detect a 10% quality drop within 24 hours.

---

## Feedback Signal Schema

```json
{
  "trace_id": "abc12345",
  "score": 1.0,
  "rationale": "user feedback",
  "timestamp": "2025-04-01T14:23:11Z",
  "input": "user question (nullable for feedback-only entries)",
  "output": "model answer (nullable for feedback-only entries)",
  "source": "judge | user_feedback"
}
```

Fields:
- `trace_id`: links the eval result back to the original request
- `score`: 0.0-1.0 (judge score or 1.0/0.0 for thumbs up/down)
- `source`: distinguish judge scores from user feedback in aggregation
- Nullable `input`/`output`: feedback entries don't carry the original content (looked up by trace_id if needed)

---

## Eval Log Format

Append-only JSONL, one entry per line:

```
{"trace_id": "a1b2c3d4", "score": 0.87, "rationale": "...", "timestamp": "...", "input": "...", "output": "...", "source": "judge"}
{"trace_id": "e5f6g7h8", "score": 1.0, "rationale": "user feedback", "timestamp": "...", "input": null, "output": null, "source": "user_feedback"}
```

Query examples (jq):
```bash
# Average score today
jq -r 'select(.source=="judge") | .score' score_log.jsonl | awk '{s+=$1; n++} END {print s/n}'

# Flagged cases (score < 0.5)
jq 'select(.source=="judge" and .score < 0.5)' score_log.jsonl

# Thumbs-up rate
jq -r 'select(.source=="user_feedback") | .score' score_log.jsonl | sort | uniq -c
```

---

## Runbook: Score Drops Below Threshold

Trigger: `summary.alert == true` (average score < 0.70) or score drops >5% over 7-day rolling window.

**Step 1 - Confirm it's real (not a judge failure).**

Check judge error rate: entries with `score == -1.0` in the log. If >10% of today's evals failed with an error, your judge is broken, not your feature.

**Step 2 - Pull the flagged cases.**

```bash
jq 'select(.source=="judge" and .score < 0.5) | {trace_id, score, input}' score_log.jsonl
```

Read 10-20 of them. Look for a pattern. Is it a specific question type? A length range? A new topic?

**Step 3 - Classify the failure.**

Use the failure taxonomy:
- Format failure: output missing required fields
- Faithfulness failure: answer makes claims not in the source
- Relevance failure: answer doesn't address the question
- Scope failure: question is outside what the system was built for
- Drift failure: previously correct behavior changed (model update, distribution shift)

**Step 4 - Act based on classification.**

| Failure type | Immediate action | Long-term fix |
|---|---|---|
| Format | Tighten output format instructions in prompt | Add format check to CI |
| Faithfulness | Review retrieval: are relevant chunks being found? | Add retrieval eval to CI |
| Relevance | Review prompt: is the question being understood? | Add to golden set |
| Scope | Add scope-handling to prompt | Consider routing out-of-scope inputs |
| Drift | Pin model version, re-run golden set | Check provider release notes |

**Step 5 - Verify fix.**

Re-run offline eval against golden set. Confirm metric recovers. Deploy. Confirm online eval recovers within 24 hours.

---

## Cost Management

LLM judge costs at scale:

| Evals/day | Cost @ $0.02/eval | Cost/year |
|-----------|-------------------|-----------|
| 100 | $2/day | $730 |
| 500 | $10/day | $3,650 |
| 2,000 | $40/day | $14,600 |

Cost reduction strategies (in priority order):
1. Use a cheaper judge model (Haiku vs Opus) for routine scoring. Reserve Opus for flagged cases.
2. Reduce sample rate for known-stable traffic segments.
3. Tier your scoring: rule-based format checks first (free), LLM judge only for format-passing responses.
4. Cache judge scores for identical inputs (dedup by input hash before scoring).
