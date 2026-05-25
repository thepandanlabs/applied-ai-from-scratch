---
name: runbook-eval-first-development
description: Complete runbook for eval-first development of any AI feature, from success criteria through online eval in production
version: "1.0"
phase: "05"
lesson: "14"
tags: [eval, eval-first, runbook, ci, golden-set, production]
---

# Eval-First Development Runbook

## What This Is

The Phase 05 capstone artifact. A complete process for building AI features with evaluations driving every decision. Use this runbook whenever you start building a new AI feature or significantly modifying an existing one.

---

## The 7-Step Process

```
1. Define success criteria
2. Build golden set
3. Write evals (verify they fail on stub)
4. Build the feature
5. Run evals, read failures, fix
6. Add to CI
7. Deploy with online eval
```

Never skip step 3 (verify evals fail on stub). This is the one step that proves your evals actually test something. An eval that passes on an empty response is not an eval.

---

## Step 1: Success Criteria Template

Before writing any feature code, fill in this template:

```python
SUCCESS_CRITERIA = {
    # Primary quality metric -- the core thing the feature must do
    "primary_metric_name": 0.90,      # e.g., faithfulness, accuracy

    # Secondary quality metric -- another dimension of quality
    "secondary_metric_name": 0.85,    # e.g., answer_relevance, completeness

    # Structural requirements -- always binary (pass/fail)
    "format_compliance": 1.00,        # required output schema always satisfied

    # Optional: latency, safety, or domain-specific metrics
    # "safety_score": 1.00,
    # "latency_p95_ms": 2000,
}
```

Rules for setting thresholds:
- Start with thresholds that feel achievable but not trivial. You can raise them once you understand the problem.
- Format compliance should always be 1.00. Malformed output crashes downstream code.
- If you can't define a primary metric, you don't understand what the feature needs to do. Stop and clarify.
- Write these down before you look at any model outputs. Once you've seen outputs, your thresholds will be biased.

---

## Step 2: Golden Set Schema

```python
# Each case must have:
{
    "id": "gc-01",                      # unique ID for tracking across experiments
    "input": "...",                     # the user input, verbatim
    "expected_answer_contains": [...],  # key phrases the answer must include
    "expected_source_section": "...",   # for RAG: which section should be cited
    "category": "...",                  # failure taxonomy tag
}
```

Golden set size guide:

| Feature maturity | Target cases | Minimum cases |
|---|---|---|
| New feature | 20-30 | 10 |
| Established feature | 50-100 | 30 |
| Safety-critical feature | 100+ | 50 |

Category coverage: include at least 2 cases per category. Categories are the failure taxonomy axes for your domain (e.g., policy questions, shipping questions, edge cases, out-of-scope).

The golden set should catch 80% of failures you find in error analysis. If it's catching less, you need more coverage of the failure categories you see in production.

---

## Step 3: Scorer Selection Guide

| What you're measuring | Scorer type | Cost | Variance |
|---|---|---|---|
| JSON schema compliance | Rule-based | Free | Zero |
| Contains keyword / phrase | Rule-based | Free | Zero |
| Semantic faithfulness | LLM judge | Medium | Low-medium |
| Answer relevance | LLM judge | Medium | Low-medium |
| Tone and style | LLM judge | Medium | High |
| User satisfaction | Human / survey | High | High |
| Task completion | Execution test | Low | Low |

Rules:
- Use rule-based scorers for everything they can cover. They're free and deterministic.
- Use LLM judge for semantic quality. Always include a rubric with score anchors.
- Run your LLM judge on the same 20 cases twice and check consistency. If delta > 0.10, tighten the rubric.
- Never use a single LLM judge score as your only metric. Pair it with at least one rule-based check.

---

## Step 4: CI Threshold Guide

```yaml
# Fail CI if any metric falls below threshold
thresholds:
  faithfulness: 0.90
  answer_relevance: 0.85
  format_compliance: 1.00
```

Regression threshold (how much a metric can drop vs baseline before CI fails):
- Default: 3% (0.03 absolute drop)
- Strict: 1% for safety or format metrics
- Relaxed: 5% for exploratory changes with high upside

CI command pattern:
```bash
uv run python eval_runner.py \
    --experiment my-feature-v2 \
    --baseline my-feature-v1 \
    --threshold 0.03
```

---

## Step 5: Online Eval Sampling Strategy

| Traffic volume | Recommended sample rate | Notes |
|---|---|---|
| Under 500 req/day | 100% | Eval everything |
| 500-5,000 req/day | 20% | ~100-1,000 evals/day |
| 5,000-50,000 req/day | 5% | ~250-2,500 evals/day |
| Over 50,000 req/day | 1-2% | Cost-manage with tiered scoring |

Always override to 100% for:
- Thumbs-down responses
- Inputs matching known risk patterns
- First 72 hours after a new deploy

---

## Step 6: The Eval-Driven Debugging Loop

When evals fail, follow this loop:

```
1. Pull all failing cases
   - Sort by score ascending (worst first)
   - Read 10-15 of them

2. Find the pattern
   - Are failures concentrated in one category?
   - Is there a common input feature (length, topic, format)?
   - Is the failure in retrieval, generation, or format?

3. Form a hypothesis
   - "Faithfulness is failing because retrieval returns the wrong section for X-type queries"
   - "Format compliance is failing because the model adds a preamble before the JSON"

4. Make the smallest possible fix
   - Change one thing at a time
   - If changing the chunker: don't also change the prompt

5. Re-run evals
   - All metrics, not just the one you fixed
   - Check: did the fix help? Did it break anything else?

6. Iterate
   - If still failing: repeat from step 1 with the new result set
   - If passing: add the cases that triggered the fix to the golden set
```

The golden set grows with every bug you fix. That is the compound return of eval-first development.

---

## Eval-First vs Ship-First: The Real Cost Comparison

| Approach | Time to first working version | Time to stable production | Ongoing cost |
|---|---|---|---|
| Ship-first, eval-later | ~2 hours | Weeks-months (debugging blind) | High (regressions discovered in production) |
| Eval-first | ~4-6 hours | Days (evals guide fixes) | Low (regressions caught in CI) |

The eval setup takes 2-4 extra hours upfront. That cost is repaid the first time CI catches a regression you would have shipped. It's repaid again every time a new engineer makes a change and the evals tell them immediately if they broke something.

For any feature you expect to touch more than twice, eval-first development pays for itself.
