---
name: skill-managed-finetune-workflow
description: End-to-end workflow for managed fine-tuning APIs with validation, cost estimation, and status polling
version: "1.0"
phase: "09"
lesson: "03"
tags: [fine-tuning, openai, managed-api, workflow]
---

# Managed Fine-Tuning Workflow

A production runbook for the managed fine-tuning lifecycle. Apply these steps in order every time. Skipping steps wastes money or ships a worse model.

---

## Pre-Flight Checklist

Complete every item before uploading a file. A failed validation after 2 hours of training is avoidable.

| Check | What to verify | Failure signal |
|-------|---------------|----------------|
| JSONL format | Each line is valid JSON with a `messages` key | JSON parse error on any line |
| Role sequence | Every example ends with `assistant` role | Last role is `user` or `system` |
| Minimum examples | At least 100 examples (10 absolute minimum) | Count below threshold |
| No empty content | Every message has non-empty `content` | Empty string in any `content` field |
| No truncated responses | Assistant content does not end mid-sentence | Ends with `and`, `but`, `the`, etc. |
| System prompt consistency | Every example uses the same system prompt | Variation in system content across lines |
| Dataset split ready | Separate train and validation files exist | Only one JSONL file available |

Run `validate_dataset()` before every upload. It costs nothing. Uploading a broken file costs hours.

---

## Cost Estimation Formula

Estimate cost before submitting. The formula is an approximation: actual token count may vary by model tokenizer.

```
approx_tokens_per_epoch = (total_chars_in_dataset / 4) * 1.3
total_training_tokens   = approx_tokens_per_epoch * n_epochs
estimated_cost_usd      = (total_training_tokens / 1_000_000) * cost_per_1m_tokens
```

Reference pricing (verify current rates before use):

| Model | Cost per 1M training tokens |
|-------|----------------------------|
| gpt-4o-mini-2024-07-18 | $3.00 |
| gpt-3.5-turbo | $8.00 |
| gpt-4o-2024-08-06 | $25.00 |

A typical 300-example dataset at average 150 tokens per example, 3 epochs:
- Total tokens: ~175,500
- Cost at gpt-4o-mini rate: ~$0.53

Fine-tuning a small model on a curated dataset costs less than a single engineer-hour. The expensive part is the dataset curation time.

---

## The 6-Step Lifecycle

Follow these steps in order. Each step produces an artifact to save before continuing.

```
Step 1: VALIDATE
  Input:  train.jsonl
  Action: validate_dataset(filepath)
  Save:   fix any errors before proceeding

Step 2: ESTIMATE
  Input:  train.jsonl, base_model, n_epochs
  Action: estimate_cost(filepath, base_model, n_epochs)
  Save:   record estimated cost in your run log

Step 3: UPLOAD
  Input:  train.jsonl
  Action: upload_file(filepath)
  Save:   file_id (e.g. file-abc123) -> save to config

Step 4: CREATE JOB
  Input:  file_id, JobConfig
  Action: create_job(config, file_id=file_id)
  Save:   job_id (e.g. ftjob-xyz789) -> save to config

Step 5: POLL
  Input:  job_id
  Action: wait_for_job(job_id, poll_interval_seconds=30)
  Save:   fine_tuned_model ID (e.g. ft:gpt-4o-mini:org::hash) -> save immediately

Step 6: EVALUATE
  Input:  fine_tuned_model, held-out test set
  Action: run quick_test() + full eval on test split
  Save:   metrics vs baseline in your eval log
```

Step 5 is critical: save the model ID to a config file or secret store before the terminal session ends. There is no recovery if you lose it.

---

## Common Failure Modes

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| Malformed JSONL | Job fails immediately after upload | Run `validate_dataset()` before every upload |
| Insufficient examples | Model shows minimal improvement | Target 100+ examples; 50 is the practical floor |
| Near-duplicate examples | Poor generalization on novel inputs | Run deduplication pipeline before training |
| Wrong base model | Output format mismatch | Match base model to the same model you evaluated against |
| Lost model ID | Cannot find fine-tuned model after job completes | Save model ID to a config file before terminal closes |
| Underperforms baseline | Fine-tune worse than prompted base model | Check dataset quality; review rejected/edge-case examples |
| Auto-hyperparameters poor fit | Loss curve does not converge | Try n_epochs=1 or n_epochs=5; check learning rate |
| Job timeout in wait_for_job | Script exits before job completes | Set timeout_seconds=14400 (4 hours) for large datasets |

---

## The Quick Test Pattern

Run at least 5 tests covering core use case + 2 edge cases before announcing a model is ready:

```python
manager = FineTuneManager()

test_cases = [
    # Core use case
    {"role": "user", "content": "This product is amazing!"},
    {"role": "user", "content": "Terrible. Broke on day one."},
    {"role": "user", "content": "It works fine, nothing special."},
    # Edge cases
    {"role": "user", "content": ""},  # empty input
    {"role": "user", "content": "I'm not sure how I feel about this."},  # ambiguous
]

system = {"role": "system", "content": "Extract sentiment as JSON."}

for test in test_cases:
    response = manager.quick_test(
        model_id="ft:gpt-4o-mini-2024-07-18:org::hash",
        test_messages=[system, test],
    )
    print(f"Input: {test['content'][:50]}")
    print(f"Output: {response}\n")
```

A model that fails on empty input or returns invalid JSON on ambiguous inputs is not ready for production.

---

## When to Move from Managed to Self-Hosted

Stay on the managed API until at least one of these is true:

- Training data cannot leave your infrastructure (regulated industries, PII)
- You need a base model not offered by the managed API
- Cost at scale: managed per-token pricing exceeds GPU-hour cost for your volume
- You need full control over hyperparameters (learning rate schedule, LoRA rank)

Self-hosted fine-tuning (LoRA) is covered in Lesson 04. Start here. Move when there is a documented reason.
