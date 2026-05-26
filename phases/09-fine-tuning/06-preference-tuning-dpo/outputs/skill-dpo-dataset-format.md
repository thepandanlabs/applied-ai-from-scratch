---
name: skill-dpo-dataset-format
description: Format spec and validation checklist for DPO training datasets using preference annotation triplets
version: "1.0"
phase: "09"
lesson: "06"
tags: [fine-tuning, dpo, preference-tuning, dataset, alignment]
---

# DPO Dataset Format Spec

## What it does

Defines the canonical JSONL format for Direct Preference Optimization (DPO) training datasets and provides a validation checklist to run before submitting a dataset to a training job.

## Format

Each line of the JSONL file is one DPO triplet:

```json
{
  "prompt": "How do I reset my password?",
  "chosen": "Click 'Forgot password' on the login page. You'll receive an email within 2 minutes with a reset link. The link expires after 24 hours.",
  "rejected": "Use the forgot password link."
}
```

Fields:
- `prompt`: the user input (identical in chosen and rejected)
- `chosen`: the preferred completion
- `rejected`: the dispreferred completion

## Source format (annotation input)

Annotation platforms export in this shape:

```json
{
  "prompt": "...",
  "response_a": "...",
  "response_b": "...",
  "preferred": "A",
  "annotator_id": "ann_001"
}
```

Use `DPODatasetBuilder` (code/main.py) to convert and validate.

## Validation checklist

Run before submitting to training:

- [ ] No ties included (preferred != "tie")
- [ ] Prompt is non-empty for all examples
- [ ] Chosen and rejected are different (not identical strings)
- [ ] All text within min/max length bounds (default: 20-2000 chars)
- [ ] Keep rate is above 60% (if below, fix annotation guidelines)
- [ ] Chosen length is not consistently 2x+ longer than rejected (verbosity bias risk)
- [ ] Prompt diversity: no single scenario type exceeds 50% of dataset
- [ ] Dataset has at least 200 examples (below this, DPO signal is too sparse)

## Production pipeline context

DPO belongs after SFT in the training pipeline:

```
1. SFT - teach the model the task and output format
2. DPO - align style, tone, safety preferences
```

Running DPO on an untrained base model degrades performance. The reference model (ref_model in TRL) must be the SFT checkpoint.

## TRL consumption

The JSONL built here is consumed directly by TRL's DPOTrainer:

```python
from datasets import load_dataset
dataset = load_dataset("json", data_files="dpo_dataset.jsonl", split="train")
```

Key hyperparameter: `beta` (KL penalty coefficient, default 0.1). Higher beta keeps the DPO model closer to the reference SFT model. Start at 0.1 and adjust based on over/under-alignment.

## When to use DPO vs SFT

Use DPO when:
- You have pairs of outputs and can say which is better, but cannot write the "correct" output from scratch
- Aligning tone, style, formality, or safety behaviors
- You have an existing SFT model and want to refine preference behavior

Use SFT when:
- Teaching new domain knowledge or output formats
- No existing model for the task
- You have ground-truth completions
