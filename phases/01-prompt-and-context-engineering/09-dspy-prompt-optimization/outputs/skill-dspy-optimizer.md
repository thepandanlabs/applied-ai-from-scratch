---
name: skill-dspy-optimizer
description: Decision guide and implementation patterns for programmatic prompt optimization with DSPy - when to use it, which optimizer to pick, and how to integrate compilation into a production pipeline.
version: "1.0"
phase: "01"
lesson: "09"
tags: [dspy, prompt-optimization, few-shot, bootstrapfewshot, miprov2, classification]
---

# Skill: Programmatic Prompt Optimization with DSPy

Use this skill when manual prompt tuning has plateaued and you have labeled examples to optimize against.

---

## When to Use DSPy

Use DSPy when ALL of the following are true:
- You have labeled data: minimum 20 examples for BootstrapFewShot, 200+ for MIPROv2
- Manual tuning is not producing further accuracy improvements
- Your task has a clear, measurable success metric (accuracy, F1, exact match)
- The task is stable enough that the label distribution will not change weekly

Do NOT use DSPy when:
- You have no labeled data (build the dataset first)
- The task is still being defined (you do not yet know what "correct" looks like)
- You are prototyping and need fast iteration
- The baseline manual prompt already achieves acceptable performance

---

## Optimizer Selection Guide

```
How much labeled data do you have?

< 20 examples
  Build more data first. DSPy will overfit.

20-100 examples
  Use BootstrapFewShot.
  - Compile time: seconds to 2 minutes
  - Optimizes: few-shot demonstrations only
  - Good for: classification, extraction, short-form generation

100-500 examples
  Try BootstrapFewShot first. If accuracy gain is < 3pp, try MIPROv2 (auto="light").

500+ examples
  Use MIPROv2 (auto="medium" or "heavy").
  - Compile time: 20-60 minutes
  - Optimizes: instructions AND few-shot demonstrations
  - Good for: complex reasoning, multi-step tasks, nuanced generation
```

---

## Implementation Checklist

### 1. Define the Signature

```python
import dspy
from typing import Literal

class YourTask(dspy.Signature):
    """One sentence: what this task does."""
    input_field: str = dspy.InputField(desc="Description of what this field contains.")
    output_field: Literal["label_a", "label_b"] = dspy.OutputField(
        desc="Which label applies. Must be one of: label_a, label_b."
    )
```

Keep the docstring to one sentence. It becomes the task description in the compiled prompt.

### 2. Build Labeled Examples

```python
examples = [
    dspy.Example(input_field="...", output_field="label_a"),
    dspy.Example(input_field="...", output_field="label_b"),
    # ...
]
train_set = [ex.with_inputs("input_field") for ex in examples[:n_train]]
dev_set   = [ex.with_inputs("input_field") for ex in examples[n_train:]]
```

Critical: the dev set must NEVER be seen by the optimizer. Hold it out strictly.

### 3. Define the Metric

```python
def my_metric(example: dspy.Example, prediction, trace=None) -> bool:
    pred = getattr(prediction, "output_field", "").strip().lower()
    gold = example.output_field.strip().lower()
    return pred == gold
```

The metric is the target. Make it match your actual quality criteria.

### 4. Compile

```python
from dspy.teleprompt import BootstrapFewShot

optimizer = BootstrapFewShot(
    metric=my_metric,
    max_bootstrapped_demos=4,
    max_labeled_demos=4,
    max_rounds=1,
)

student = dspy.Predict(YourTask)
compiled = optimizer.compile(student=student, trainset=train_set)
```

### 5. Evaluate and Compare

```python
def accuracy(module, eval_set):
    correct = sum(
        int(my_metric(ex, module(input_field=ex.input_field)))
        for ex in eval_set
    )
    return correct / len(eval_set)

baseline_acc  = accuracy(dspy.Predict(YourTask), dev_set)
optimized_acc = accuracy(compiled, dev_set)
print(f"Baseline: {baseline_acc:.1%} | Optimized: {optimized_acc:.1%}")
```

### 6. Save the Compiled Program

```python
# Compile once, save, load at startup. Do not recompile on every deploy.
compiled.save("compiled_program.json")

# In production:
production_module = dspy.Predict(YourTask)
production_module.load("compiled_program.json")
result = production_module(input_field="...")
```

---

## Production Notes

**Recompile when:**
- You switch the underlying LLM (compiled state is model-specific)
- The label distribution changes significantly (more than ~10% shift)
- Accuracy drops more than 5pp in production monitoring

**Do not recompile:**
- On every deploy (the compiled state is stable until the above conditions trigger)
- Without also re-evaluating on a fresh dev set (always confirm the new compiled state is better)

**Latency:** The compiled module runs exactly one LLM call per inference. Runtime latency equals your manual prompt latency. All optimization cost is at compile time.

**Cost budget for BootstrapFewShot:**
```
Training examples:  N
LLM calls at compile: ~N * max_rounds * 2 (generate + evaluate)
Example: 50 examples, 1 round = ~100 LLM calls at compile time
Runtime cost: same as a single manual prompt call
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Optimized accuracy equals baseline | Not enough training data | Add more labeled examples |
| Optimized accuracy lower than baseline | Dev set contamination | Ensure dev_set examples are not in train_set |
| Metric always returns True | Bug in metric function | Test metric on a known wrong prediction |
| Output field has unexpected casing | Model adds capitalization | Normalize both sides in metric with `.strip().lower()` |
| Slow compile | Too many candidates | Reduce max_bootstrapped_demos or use auto="light" |
