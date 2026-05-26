---
name: runbook-finetune-project
description: Complete runbook for a fine-tuning project from dataset prep through deployment and drift monitoring
version: "1.0"
phase: "09"
lesson: "09"
tags: [fine-tuning, capstone, runbook, roi, production]
---

# Runbook: Fine-Tuning Project

A complete, phase-by-phase runbook for executing a fine-tuning project from problem qualification through production drift monitoring.

---

## Phase 1: Problem Qualification

Before touching data or writing code, verify that fine-tuning is the right tool.

### Decision Ladder

Work through these in order. Stop at the first "no" and use the alternative.

```
1. Is there a production problem prompt engineering does not solve?
   YES: continue | NO: use prompt engineering

2. Is the task narrow, repeatable, and well-defined?
   YES: continue | NO: fine-tuning will not generalize reliably

3. Is the volume high enough to justify the cost?
   YES: continue | NO: prompt engineering is cheaper at low volume

4. Can you collect or generate 200+ high-quality labeled examples?
   YES: continue | NO: you cannot train without data

5. Can you measure whether the fine-tuned model is actually better?
   YES: continue | NO: define your success metric before starting
```

### Qualification Checklist

- [ ] Problem statement written in one sentence (not "make it better" but "achieve X on metric Y")
- [ ] Baseline metric measured on current production system
- [ ] Target metric defined (absolute number or relative improvement)
- [ ] Volume estimate documented (calls/day, tokens/call)
- [ ] Go/no-go criteria written down before training starts
- [ ] Stakeholder expectation set: fine-tuning takes days to weeks, not hours

---

## Phase 2: Dataset Engineering

### Collection

Sources for training data (in order of quality):

1. Human-labeled production examples with verified correct outputs
2. Expert-reviewed outputs from a stronger model (distillation approach)
3. Synthetic examples generated and filtered by an LLM judge
4. Historical examples with proxies for quality (user ratings, downstream success)

Minimum sizes:

| Task type | Minimum examples | Recommended |
|---|---|---|
| Classification (2-4 classes) | 50 per class | 200+ per class |
| Structured extraction (JSON) | 200 | 500-1,000 |
| Generation (format/style) | 300 | 500-1,500 |
| DPO preference tuning | 200 triplets | 500+ triplets |

### Curation

Every example must pass three checks before entering the training set:

1. Format correctness: the output matches the target schema exactly
2. Content correctness: the output is factually accurate for the given input
3. No contamination: the example does not come from the hold-out test set

### Validation

Run these checks on the full dataset before submitting the fine-tuning job:

- [ ] All records parse as valid JSONL
- [ ] All records have the required `messages` field with user/assistant turns
- [ ] No empty prompts or empty completions
- [ ] No duplicate examples (same prompt and same completion)
- [ ] If using DPO: no ties, no identical chosen/rejected pairs
- [ ] Keep rate for distilled data is above 60%
- [ ] Length distribution is not skewed more than 3:1 between chosen/rejected (DPO only)

### Format

Anthropic managed fine-tuning format:

```json
{"messages": [{"role": "user", "content": "<prompt>"}, {"role": "assistant", "content": "<completion>"}]}
```

Include a system prompt in the record if your production system uses one:

```json
{"system": "<system>", "messages": [{"role": "user", "content": "<prompt>"}, {"role": "assistant", "content": "<completion>"}]}
```

---

## Phase 3: Training

### Path A: Managed API (Anthropic)

Use this path when:
- You want the simplest operational setup
- You do not have GPU infrastructure
- You are fine-tuning a Claude model for deployment on Anthropic's API

Steps:
1. Upload training JSONL to the files API
2. Create a fine-tuning job with model, file ID, and hyperparameters
3. Poll job status until `succeeded` or `failed`
4. Record the fine-tuned model ID - this is your deployment artifact

Cost estimation before submitting:
- Count total tokens in training JSONL: `sum(len(tokenize(msg)) for all messages)`
- Multiply by training token price and number of epochs
- Typical 1,000-example job at 3 epochs: $10-50 depending on model and example length

### Path B: LoRA (open-weight models)

Use this path when:
- You are fine-tuning an open-weight model (Llama, Qwen, Mistral)
- You need full control over training hyperparameters
- You are optimizing for self-hosted deployment with vLLM

Key hyperparameters:

| Parameter | Starting value | Adjust when |
|---|---|---|
| `r` (LoRA rank) | 16 | Too high: overfitting; too low: underfitting |
| `alpha` | 32 | Usually set to 2x rank |
| `learning_rate` | 2e-4 | Reduce if training loss is unstable |
| `num_train_epochs` | 3 | Reduce if eval loss starts rising |
| `per_device_train_batch_size` | 4-8 | Reduce if OOM |

### Cost Estimation Template

```
Teacher generation cost  = N_examples * avg_tokens * teacher_price_per_token
Fine-tune training cost  = (total_training_tokens / 1M) * ft_price_per_1M
Evaluation cost          = eval_calls * avg_tokens * judge_price
Engineering time cost    = hours * hourly_rate (amortized over 12 months)

Total project cost       = sum of above
Monthly savings          = (daily_calls * avg_tokens * (baseline_price - ft_price)) * 30
Payback period (months)  = total_project_cost / monthly_savings
```

---

## Phase 4: Evaluation

Run a three-way comparison on a held-out test set the model has never seen.

### Test Set Requirements

- Minimum 50 examples; 100+ preferred
- Drawn from the same distribution as production inputs
- Collected before training (never use test examples for training data generation)
- Labeled with ground truth or evaluated by a calibrated LLM judge

### Three-Way Comparison

| Condition | Setup | Purpose |
|---|---|---|
| Baseline | Base model, no system prompt | Lower bound |
| Prompt-engineered | Base model + system prompt + few-shot | Upper bound without training |
| Fine-tuned | Fine-tuned model | What you actually built |

Fine-tuning is worth deploying only if the fine-tuned model beats prompt-engineering by at least 5 percentage points. If it does not, more prompt engineering work is the better investment.

### Go / No-Go Decision

Fill in this table with actual numbers before making the deployment decision:

| Dimension | Target | Measured | Pass/Fail |
|---|---|---|---|
| Task accuracy | >= 90%, +10pp over PE | ___% | |
| Accuracy gain vs. prompt-eng | >= +5pp | ___pp | |
| Safety / guardrail tests | 0 new violations | ___ | |
| Latency vs. baseline | Within 20% | ___% change | |
| Cost payback period | <= 3 months | ___ months | |

Decision: GO only if all five dimensions pass. Document the decision in writing with the actual numbers.

---

## Phase 5: Deployment

### Pre-Deployment Checklist

- [ ] Go/no-go decision recorded with numeric evidence (not "looks good")
- [ ] Fine-tuned model ID stored in configuration, not hardcoded
- [ ] Baseline model ID also stored (rollback path)
- [ ] Integration test run: send 10 representative production prompts and verify output format
- [ ] A/B rollout plan defined: percentage of traffic to route to new model at launch

### Rollout Strategy

Start at 5-10% of traffic. Monitor quality metrics for 48 hours. Increase to 25%, then 50%, then 100% at 48-hour intervals if metrics stay within bounds.

Define automatic rollback triggers before launch:
- Valid output rate drops below X% (set from your go/no-go threshold)
- Error rate exceeds Y%
- Latency P99 exceeds Z ms

### Model ID Preservation

The fine-tuned model ID is your deployment artifact. Treat it like a Docker image tag:

```python
# Good: configurable, rollback is a one-line change
MODEL_ID = os.environ.get("FINETUNE_MODEL_ID", "claude-haiku-ft-<your-id>")

# Bad: hardcoded, rollback requires a code deploy
model = "claude-haiku-ft-abc123"
```

Store both the fine-tuned model ID and the fallback baseline model ID in your environment configuration.

---

## Phase 6: Monitoring

### Drift Detection

Fine-tuned models do not degrade on their own. Accuracy drops signal input distribution shift.

Weekly eval job (for the first month post-deployment):

```python
import anthropic
import json

client = anthropic.Anthropic()
FINETUNE_MODEL = os.environ["FINETUNE_MODEL_ID"]
ACCURACY_THRESHOLD = 0.85  # alert below this

def weekly_drift_check(test_cases: list[dict]) -> float:
    """Run test cases and return accuracy rate."""
    correct = 0
    for case in test_cases:
        resp = client.messages.create(
            model=FINETUNE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": case["prompt"]}]
        )
        output = resp.content[0].text
        # Task-specific correctness check
        if check_correctness(output, case["expected"]):
            correct += 1
    accuracy = correct / len(test_cases)
    if accuracy < ACCURACY_THRESHOLD:
        alert(f"Drift detected: accuracy {accuracy:.1%} below threshold {ACCURACY_THRESHOLD:.1%}")
    return accuracy
```

### Monitoring Schedule

| Period | Frequency | Action on failure |
|---|---|---|
| Week 1-4 post-deployment | Weekly, 20 test prompts | Investigate input distribution; re-distill if confirmed |
| Month 2-6 | Monthly, 50 test prompts | Same |
| Month 7+ | Quarterly or event-driven | Trigger on major input distribution change |

### Retraining Triggers

Re-run the full distillation pipeline when any of these conditions occur:

- Accuracy drops more than 5 percentage points from deployment baseline
- A new category of input appears that was not in the training distribution (new product, new document format, new domain)
- Business requirements change enough that the original success metric no longer applies

Retraining is not failure. It is the normal maintenance cycle for a production fine-tuned model.

---

## Quick Reference: Decision Points

| Situation | Decision |
|---|---|
| Fine-tuning beats PE by less than 5pp | Do not deploy; invest in prompt engineering |
| Keep rate below 60% | Fix annotation/generation process before training |
| Payback > 6 months | Volume too low; use prompt engineering |
| Safety regression on any test | Hard no-go; audit training data |
| Accuracy drops 5pp+ post-deployment | Drift detected; re-distill with current inputs |
| One test prompt looks great | Not evidence; run full eval suite |
