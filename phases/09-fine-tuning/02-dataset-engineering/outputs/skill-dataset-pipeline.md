---
name: skill-dataset-pipeline
description: Template for defining a fine-tuning dataset contract, annotation guidelines, and pipeline configuration
version: "1.0"
phase: "09"
lesson: "02"
tags: [fine-tuning, dataset, annotation, jsonl, pipeline]
---

# Fine-Tuning Dataset Pipeline Template

Use this template to define your fine-tuning dataset before collecting a single example. Complete every section before annotation begins.

---

## Step 1: Define the Contract

### Task Description

**What task is the fine-tuned model performing?**
(One sentence. Be specific. "Answer customer support questions" is too vague. "Answer product questions in 2-4 sentences using warm, direct brand voice" is correct.)

```
Task: _______________________________________________
```

### Input/Output Contract

**Input format:**
```
System prompt: (paste the exact system prompt all examples will use)

User message format:
- Min length: ___ characters
- Max length: ___ characters
- Must include: (required elements, e.g., "must be a question")
- Must not include: (forbidden elements, e.g., "no internal employee IDs")
```

**Output format:**
```
Assistant response format:
- Min length: ___ characters
- Max length: ___ characters
- Required structure: (e.g., "JSON with keys: name, status, notes")
- Required tone: (e.g., "warm, direct, no jargon")
- Forbidden content: (words or patterns that disqualify an example)
```

---

## Step 2: Annotation Guidelines

### Quality Rubric

Rate each example on a 1-3 scale before including it in the dataset.

| Score | Criteria |
|-------|----------|
| 3 - Include | Correct, well-formatted, right length, matches brand voice. Would be proud to show this to a customer. |
| 2 - Revise | Mostly right but has one fixable issue (slightly too long, one awkward phrase). Fix before including. |
| 1 - Reject | Wrong answer, wrong format, wrong tone, truncated, or contains forbidden content. Do not include. |

### Example Judgments

**Reject examples - explain WHY:**
```
Example 1 (rejected):
  User: "What are your support hours?"
  Assistant: "9-5."
  Reason: Too short, no timezone, no alternative for after-hours. Score: 1.

Example 2 (rejected):
  User: "I need a refund."
  Assistant: "I don't know if I can help with that."
  Reason: Contains "I don't know", passes off responsibility. Score: 1.
```

**Good examples - explain WHY:**
```
Example 1 (include):
  User: "How do I reset my password?"
  Assistant: "Click 'Forgot Password' on the login page and enter your email. You'll get a reset link within 2 minutes - check spam if you don't see it. Happy to help if you run into trouble!"
  Reason: Correct, warm tone, right length, actionable, anticipates follow-up. Score: 3.
```

### Annotation Calibration

Before full annotation: have two annotators independently rate the same 20 examples. Compute agreement rate. Target: 80%+ agreement before proceeding.

| Annotator A | Annotator B | Agreement? |
|-------------|-------------|------------|
| (score)     | (score)     | Y/N        |

Agreement rate: ___/20 = ___%

If below 80%: identify the disagreements and rewrite the rubric criteria for the contested cases.

---

## Step 3: Collection Guidelines

### Source Selection

**Where are your examples coming from?**
- [ ] Production traffic (log real user inputs + ideal responses)
- [ ] Manual creation by domain experts
- [ ] Existing documents rewritten into input/output format
- [ ] Synthetic generation with human review

**Quality of sources:**
- Production traffic: highest quality inputs, variable output quality (must filter bad agent responses)
- Manual creation: highest quality outputs, time-intensive
- Synthetic generation: fastest, but requires 100% human review before including

### Collection Checklist

- [ ] Input/output contract is written and approved
- [ ] Annotation guidelines written with at least 5 reject examples and 5 include examples
- [ ] Annotator calibration done (80%+ agreement)
- [ ] PII removal process defined (names, emails, account numbers)
- [ ] Edge cases identified and deliberately collected (don't just collect easy examples)
- [ ] Category distribution target set (no single category >30%)

---

## Step 4: Pipeline Configuration

### DatasetPipeline settings

```python
from code.main import Contract, DatasetPipeline

contract = Contract(
    system_prompt="(your exact system prompt)",
    min_user_length=10,          # adjust for your task
    max_user_length=2000,
    min_assistant_length=30,     # catches truncated responses
    max_assistant_length=800,    # adjust for your typical response length
    forbidden_output_words=[     # list words that disqualify an example
        "I don't know",
        "I cannot help",
    ],
)

pipeline = DatasetPipeline(
    contract=contract,
    seed=42,     # NEVER change the seed after you start training runs
)
```

### Split Ratios

Default: 80/10/10 (train/val/test)

For small datasets (<200 examples): consider 80/10/10 but note your val and test sets will be small (16-20 examples each). This is workable but noisy.

For very small datasets (<100 examples): use 90/5/5 but treat results as directional, not definitive.

### Dataset Size Targets

| Dataset size | Expected outcome |
|---|---|
| Under 50 examples | Do not fine-tune. Use few-shot prompting. |
| 50-100 examples | Minimal signal. Expect marginal improvement only. |
| 100-500 examples | Workable. Enough to shape format and tone. |
| 500-2000 examples | Strong signal. Good for vocabulary and behavior. |
| 2000+ examples | Diminishing returns unless diversity is high. |

---

## Step 5: Pre-Training Checklist

Before submitting to the fine-tuning API:

- [ ] Pipeline ran with 0 errors
- [ ] Validation rejection rate under 20%
- [ ] Deduplication removed under 10%
- [ ] Manual spot check: 10 random training examples reviewed and approved
- [ ] Test set saved separately and not used for any training or hyperparameter decisions
- [ ] Baseline eval score recorded (prompt-only model on test set)
- [ ] JSONL files have the correct format (`messages` array with system/user/assistant)

### JSONL Validation

Each line in your JSONL must match this format exactly:

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
```

Quick validation:
```python
import json
with open("train.jsonl") as f:
    for i, line in enumerate(f):
        obj = json.loads(line)
        assert "messages" in obj
        roles = [m["role"] for m in obj["messages"]]
        assert roles == ["system", "user", "assistant"], f"Line {i}: wrong roles {roles}"
print("JSONL format valid")
```

---

## Anti-Pattern Reference

| Anti-pattern | Symptom in fine-tuned model | Fix |
|---|---|---|
| Near-duplicates | Memorizes specific phrasings, poor generalization | Dedup by fingerprint or embedding similarity |
| Inconsistent format | Output format is a hybrid of multiple styles | Annotation guidelines with explicit format examples |
| Bad responses included | Model learns incorrect or grumpy behavior | Human review with a reject/include rubric |
| Imbalanced categories | Overperforms on dominant category, fails others | Count by category, oversample underrepresented |
| Auto-generated without review | Model learns generator's errors and hallucinations | Review 100% of synthetic examples |
| Too few examples | Marginal or no improvement over baseline | Collect more or use few-shot prompting instead |
