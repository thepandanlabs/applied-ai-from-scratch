---
name: skill-finetune-eval-harness
description: Reusable template for evaluating a fine-tuned model against a baseline, covering test set requirements, metric definitions, the go/no-go decision framework, and CI integration.
version: "1.0"
phase: "09"
lesson: "05"
tags: [fine-tuning, evaluation, harness, go-no-go, metrics]
---

# Fine-Tune Evaluation Harness

Use this before deploying any fine-tuned model. The harness answers: "Is the fine-tune good enough to justify deployment and ongoing operational overhead?"

---

## Test Set Requirements

Before running any eval, verify the test set meets all three criteria:

### 1. No overlap with training data

Verify by hashing inputs:

```python
import hashlib
import json

def hash_input(text: str) -> str:
    return hashlib.sha256(text.strip().encode()).hexdigest()

# Build sets of hashes
train_hashes = {hash_input(ex["input"]) for ex in train_examples}
test_hashes = {hash_input(ex["input"]) for ex in test_examples}

overlap = train_hashes & test_hashes
if overlap:
    raise ValueError(f"CONTAMINATED: {len(overlap)} test examples found in training set.")
print("Test set is clean.")
```

Overlap inflates accuracy by 20-30% on memorized examples, making a weak fine-tune appear production-ready.

### 2. Minimum size

| Task Type | Minimum Examples | Preferred |
|-----------|----------------|-----------|
| Structured extraction (JSON) | 200 | 500+ |
| Classification (binary) | 200 | 500+ |
| Classification (multi-class) | 400 | 1,000+ |
| Open-ended generation | 100 | 300+ |
| Regression / scoring | 200 | 500+ |

With fewer than 200 examples, the 95% confidence interval exceeds 7 percentage points, making a 5-10% improvement indistinguishable from noise.

### 3. Representativeness

The test set should reflect production traffic distribution, not just the easy cases. Explicitly include:

- Short inputs and long inputs (edge cases for context handling)
- Ambiguous inputs (where the base model often fails)
- Rare categories (even if underrepresented - catch regression on tail cases)
- Adversarial inputs (inputs designed to confuse the model)

Aim for 10-15% of the test set to be edge cases.

---

## Metric Definitions by Task Type

### Structured Output (JSON extraction, slot filling)

| Metric | Definition | Threshold for Production |
|--------|-----------|------------------------|
| Exact match accuracy | output == expected after JSON normalization | Depends on task |
| Format validity rate | % of outputs that are parseable JSON | >95% required |
| Field-level accuracy | Per-field correct rate (for nested objects) | Track separately |
| Error rate | % of API errors or empty outputs | <1% required |

JSON normalization: parse both output and expected, re-serialize with sorted keys. This prevents penalizing for key order differences.

### Classification

| Metric | Definition |
|--------|-----------|
| Accuracy | % of correct class labels |
| Per-class recall | Catch regressions on rare classes |
| Confusion matrix | Understand failure modes, not just aggregate |

### Generation (summarization, rewriting)

| Metric | Definition |
|--------|-----------|
| LLM-as-judge score | Use claude-3-5-haiku-20241022 to rate 1-5 on criteria |
| Exact match | Not useful - use for format headers/structure only |
| Length ratio | Avg output length / expected length (1.0 is ideal) |

---

## Go/No-Go Decision Framework

### Step 1: Check minimum bars (blocking)

If any of these fail, verdict is NO-GO regardless of accuracy:

- [ ] Format validity rate >= 95%
- [ ] Error rate < 1%
- [ ] No regression >5% on edge case subset

### Step 2: Calculate relative improvement

```
relative_improvement = (fine_tune_accuracy - baseline_accuracy) / baseline_accuracy
```

### Step 3: Apply deployment cost threshold

| Deployment Overhead | Minimum Relative Improvement |
|--------------------|------------------------------|
| No new infrastructure (API swap) | 5% |
| Hosted adapter, same serving stack | 10% |
| New model server or container | 15% |
| Separate service with own monitoring | 20% |

### Step 4: Cost-per-correct-output analysis

Fine-tuning often changes the economics even when accuracy improves:

```python
def cost_per_correct(total_cost_usd: float, exact_match_count: int) -> float:
    if exact_match_count == 0:
        return float("inf")
    return total_cost_usd / exact_match_count

baseline_cpc = cost_per_correct(baseline_cost, baseline_exact_match)
ft_cpc = cost_per_correct(ft_cost, ft_exact_match)
cpc_improvement = (baseline_cpc - ft_cpc) / baseline_cpc
```

If cost-per-correct improves by more than the accuracy improvement, the fine-tune has a compounding economic benefit (higher accuracy + lower cost per success).

---

## CI Integration

### Run eval as a CI step

```bash
python eval/main.py \
  --baseline $BASE_MODEL_ID \
  --fine-tuned $FINE_TUNED_MODEL_ID \
  --test-set data/test.jsonl \
  --threshold 0.15 \
  --output-json eval-results.json \
  --fail-below-threshold
```

Exit code 0 = GO, exit code 1 = NO-GO. CI pipelines treat this as a quality gate.

### GitHub Actions example

```yaml
- name: Evaluate fine-tune
  run: |
    python eval/main.py \
      --baseline ${{ vars.BASE_MODEL_ID }} \
      --fine-tuned ${{ steps.train.outputs.model_id }} \
      --test-set data/test.jsonl \
      --threshold 0.15 \
      --output-json eval-results.json \
      --fail-below-threshold
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}

- name: Upload eval results
  uses: actions/upload-artifact@v3
  if: always()
  with:
    name: eval-results
    path: eval-results.json
```

---

## Evaluator Calibration Checklist

Before trusting your harness, validate it:

- [ ] Run harness on 50 examples you already labeled manually
- [ ] Agreement rate with human labels > 90% (if 75-90%, review normalization logic)
- [ ] Test normalization on at least 5 edge cases: None vs null, integers vs strings, extra whitespace
- [ ] Verify test set has zero overlap with training data (run hash check above)
- [ ] Confirm test distribution matches production traffic (not cherry-picked easy cases)
- [ ] Document the normalization logic and which fields are included in exact match

---

## Regression Test Suite

Maintain a separate 50-example regression set that covers behaviors the baseline model handles well. Run this as part of every eval:

```
REGRESSION CATEGORY         WHAT TO INCLUDE
-------------------------------------------------
Simple cases                Clear, unambiguous inputs the baseline scores >90% on
Edge cases                  Inputs the baseline used to fail but now handles
Format variations           Different input phrasings for the same underlying task
Out-of-distribution         Inputs outside the training distribution
Adversarial                 Inputs designed to cause incorrect output
```

A fine-tune that improves exact match by 15% but regresses 20% on the regression set should not deploy. Set a regression threshold of -5% maximum on any category.

---

## Continuous Eval with Braintrust

For tracking multiple fine-tuning runs over time:

```python
import braintrust

experiment = braintrust.Experiment(
    project="json-extraction-finetune",
    name="qlora-r16-epoch3-clinical-qa-v2",
)

for example in test_examples:
    output = run_model(model_id, example.input)
    experiment.log(
        input=example.input,
        output=output,
        expected=example.expected_output,
        scores={
            "exact_match": int(is_exact_match(output, example.expected_output)),
            "format_valid": int(is_valid_json(output)),
        },
    )

result = experiment.summarize()
print(result)
```

The platform stores all runs, computes confidence intervals, and flags regressions automatically. Use it after the local harness gives you the go/no-go, not as a replacement for the local harness.
