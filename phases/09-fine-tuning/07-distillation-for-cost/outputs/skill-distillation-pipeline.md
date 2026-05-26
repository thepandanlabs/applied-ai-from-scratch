---
name: skill-distillation-pipeline
description: Pattern spec for building teacher-student distillation pipelines with quality filtering
version: "1.0"
phase: "09"
lesson: "07"
tags: [distillation, fine-tuning, cost-optimization, teacher-student]
---

# Skill: Teacher-Student Distillation Pipeline

A reusable pattern for replacing an expensive large model with a fine-tuned small model on a narrow, high-volume task.

---

## Architecture Overview

```
Teacher model (large, expensive)
  |
  v
Raw outputs: prompt + completion pairs
  |
  v
LLM quality judge (scores each output 1-5)
  |
  +-- score < threshold --> Discard
  |
  +-- score >= threshold --> Curated JSONL
                               |
                               v
                          Fine-tune student model (small, cheap)
                               |
                               v
                          Student in production (10x cheaper per call)
```

The quality filter is not optional. Training on unfiltered teacher outputs means training on the teacher's mistakes. A 50% discard rate is healthy, not a failure signal.

---

## When to Use Distillation

Distillation has positive ROI when all of the following are true:

- The task is narrow and repeatable (extraction, classification, formatting, structured output)
- Input distribution is stable (the same kinds of inputs will keep arriving)
- Teacher output quality is high (above 85% on your eval suite)
- Volume is sufficient to justify the fine-tune cost (typically 100+ calls per day)
- The task is well-defined enough to judge output quality with an LLM

Distillation underperforms when:

- The task is open-ended or creative (the small model lacks generative breadth)
- Inputs are highly variable or novel (the student generalizes poorly to new patterns)
- The teacher itself makes frequent errors (garbage in, garbage out)
- Volume is too low for the fine-tune cost to pay back within a reasonable window

---

## Data Generation Workflow

### Step 1: Prepare input prompts

Collect a representative sample of real production inputs. Aim for at least 500-2,000 examples covering the full input distribution you expect in production. Avoid repeating the same input with minor variations - diversity of prompts matters more than total count.

### Step 2: Generate with the teacher

Run each prompt through the teacher model. Use the same system prompt you use in production. Record both the prompt and the raw completion.

Key settings:
- Temperature: 0.0-0.3 for structured output tasks; higher for generation tasks
- Max tokens: set to match your production requirements, not the model maximum
- System prompt: identical to what production uses

### Step 3: Judge each output

Use an LLM judge (can be a smaller, cheaper model) to score each teacher output on a 1-5 scale:

```
5 = Exactly what a human expert would produce
4 = Good quality, accurate, well-formatted
3 = Correct but could be cleaner or more complete
2 = Partially correct, missing key information
1 = Wrong, incomplete, or harmful
```

Judge prompt structure:
1. State the task the model was asked to do
2. Provide the original user prompt
3. Provide the model completion
4. Ask for a score 1-5 with no explanation (reduces cost and parsing complexity)

### Step 4: Filter by quality threshold

Default threshold: 3.5 (keep scores 4 and 5; borderline 3.5+ accepted).

Do not lower the threshold to pad example count. If you need more data, generate more prompts from the teacher. Adding mediocre examples reduces student quality.

Health check: keep rate should be above 50%. Below 50% usually means the teacher is underperforming on your task, the judge prompt is miscalibrated, or the task is not well-defined enough for the student model to learn.

### Step 5: Format for fine-tuning

Output format for managed fine-tuning (Anthropic):

```json
{"messages": [{"role": "user", "content": "<prompt>"}, {"role": "assistant", "content": "<completion>"}]}
```

One JSON object per line (JSONL). Include system prompt in a system field if applicable.

---

## Quality Filtering Strategies

**Threshold selection:** Start at 3.5. If keep rate is below 40%, check whether the task is too open-ended for the judge to evaluate reliably. If keep rate is above 90%, lower the threshold or use a stricter judge prompt.

**Calibration check:** Before running the full pipeline, manually review 20 examples: 10 that scored 4-5 and 10 that scored 1-2. Verify the judge is discriminating correctly. A judge that always scores 4-5 is not filtering anything.

**Task-specific rubrics:** For structured output tasks (JSON extraction, classification), the judge prompt should check format validity explicitly. A malformed JSON response should score 1 regardless of content quality.

**Multi-judge agreement:** For high-stakes training data, run two different judge prompts and require both to score above threshold. Disagreement signals ambiguous quality.

---

## Cost Comparison Model

```
                    BEFORE DISTILLATION     AFTER DISTILLATION
                    --------------------    --------------------
Model               Teacher (Sonnet/Opus)   Fine-tuned student (Haiku)
Cost structure      Recurring inference     One-time train + cheap inference
Daily cost          High                    Low
Monthly cost        Baseline                Baseline * 0.05 to 0.15
One-time cost       None                    Fine-tune + generation sprint

Payback period = (teacher_generation_cost + fine_tune_cost) / monthly_savings
```

Target: payback period under 3 months. If the payback period exceeds 6 months, the volume is too low or the cost difference between models is too small to justify the project.

Cost to include in ROI:
- Teacher inference cost during generation sprint (N examples * avg tokens * teacher price)
- Fine-tuning training cost (total tokens * price per training token)
- Evaluation cost (eval calls * judge price)
- Engineering time (often the largest cost item; amortize across expected 12-month benefit window)

---

## Client Integration

The fine-tuned student is invoked identically to any other model. Store the fine-tuned model ID as a configuration variable, not hardcoded in the calling code. This allows switching back to the teacher model or to a newer fine-tuned checkpoint without a code change.

```python
import os
import anthropic

MODEL_ID = os.environ.get("STUDENT_MODEL_ID", "claude-haiku-ft-<your-id>")

client = anthropic.Anthropic()

response = client.messages.create(
    model=MODEL_ID,
    max_tokens=512,
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": user_prompt}]
)
```

Preserve the original teacher model ID in your configuration. If the student degrades unexpectedly, you want a one-line rollback path.

---

## Drift Monitoring

The student model was trained on a snapshot of your production task. Input distributions shift over time. The student will not adapt automatically.

Monitoring schedule:
- Week 1-4 after deployment: run a 20-example eval weekly
- Month 2-6: run monthly
- Trigger re-distillation when: accuracy drops more than 5 percentage points from deployment baseline, OR input distribution shifts detectably (new entity types, new formats, new topics)

Re-distillation process: run the full pipeline again with a fresh sample of current production inputs. The second round is usually faster because you have calibrated judge prompts and a validated pipeline.
