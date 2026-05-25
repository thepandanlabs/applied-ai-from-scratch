---
name: skill-error-analysis
description: Step-by-step guide for running structured error analysis on any LLM system before writing eval metrics
version: "1.0"
phase: "05"
lesson: "02"
tags: [eval, error-analysis, taxonomy, annotation, open-coding]
---

# Skill: Structured Error Analysis

Use this guide before writing any eval metrics for an LLM system. The goal: discover what is actually failing before you decide what to measure.

---

## When to Use This

- Before starting a new eval project
- When your aggregate score isn't improving despite prompt changes
- When users complain but your metrics look fine
- When a new team member joins and needs to understand the system's failure modes
- After a major prompt or model change (failure modes shift)

---

## The Annotation Schema

Each annotated output should capture:

```json
{
  "input": "the original user query",
  "output": "what the system produced",
  "category": "one of the taxonomy categories",
  "note": "optional: why you chose this category, what specifically is wrong",
  "metadata": {
    "model": "claude-opus-4-5",
    "timestamp": "2025-05-01T10:00:00Z",
    "session_id": "optional"
  }
}
```

---

## Standard Failure Categories

Use these as a starting point. Rename or split them as needed for your specific system.

| Category | Definition | Example |
|---|---|---|
| `correct` | Output is accurate, complete, and appropriately formatted | "Your PTO accrues at 1.5 days/month" |
| `wrong_fact` | Output contains a factually incorrect claim | "FSA limit is $3,050" (actual: $2,750) |
| `incomplete` | Correct but missing key information the user needed | Tells how to submit but not where to find the form |
| `unnecessary_caveat` | Correct answer buried under hedges and disclaimers | "I'm not a lawyer, but..." before a clear policy answer |
| `refused` | System declines to answer when it should | "I can't help with compensation questions" for a public policy |
| `format_mismatch` | Answer is correct but in the wrong format | Returns bullet list when user asked for a single number |
| `hallucination` | System adds information not in the knowledge base | References a competitor's policy or invents a policy detail |
| `off_topic` | Response drifts to something unrelated | Answers a different question than what was asked |
| `other` | Doesn't fit any category above | Use sparingly; if you see more than 2-3 "other" cases, split the category |

---

## The Open Coding Process

### Step 1: Sample (15 minutes)

Sample 30-50 outputs from your system logs. Use a random sample, not hand-picked examples. If you pick examples, you'll bias toward the failures you already know about.

```python
import json, random

with open("outputs.jsonl") as f:
    all_outputs = [json.loads(line) for line in f if line.strip()]

random.seed(42)  # reproducible sample
sample = random.sample(all_outputs, min(50, len(all_outputs)))
```

### Step 2: Open Coding (60-90 minutes)

Read each output. Write a short note. Don't try to categorize yet. Examples of good notes:
- "correct, but long"
- "wrong amount, confident tone"
- "correct answer, three sentences of disclaimers"
- "totally off topic"
- "refused, shouldn't have"

The notes are for you. They don't need to be systematic yet.

### Step 3: Find Clusters (20 minutes)

Read your notes. Look for patterns. What phrases or descriptions repeat? Each repeated pattern is a potential category. Name it.

Typical outcome: 5-8 distinct categories across 30-50 outputs.

### Step 4: Re-annotate with Categories (30 minutes)

Go back through the outputs and assign the category name to each one. This second pass is faster because you know what you're looking for. You'll find edge cases that don't fit cleanly; use "other" for now and revisit after the first pass is complete.

### Step 5: Saturation Check

If the last 10 outputs you annotated introduced zero new categories, you've reached saturation. Stop. If you're still finding new categories, continue sampling in batches of 10 until you reach saturation.

---

## Inter-Rater Agreement

For high-stakes systems, have two people annotate the same 20 cases independently.

Compute % agreement: `agreed_cases / total_cases`

Target: 70-80% agreement. Below 60% means your category definitions need sharper examples. Above 90% is unusual for subjective tasks and might mean the categories are too broad.

For a more rigorous measure, compute Cohen's kappa (accounts for chance agreement):

```python
from sklearn.metrics import cohen_kappa_score

labels_a = ["correct", "wrong_fact", "incomplete", ...]  # reviewer A
labels_b = ["correct", "incomplete", "incomplete", ...]   # reviewer B

kappa = cohen_kappa_score(labels_a, labels_b)
# kappa > 0.6 is considered substantial agreement
# kappa > 0.8 is almost perfect agreement
```

---

## Turning the Taxonomy into Test Cases

For each non-`correct` category:

1. Write a definition: "This category fires when the output contains X but should contain Y."
2. Find 3 examples from your annotation data.
3. Write a test case: `{"input": "...", "expected": "...", "should_fail": ["unnecessary_caveat"]}`.
4. Write a scorer that detects this specific failure mode (LLM-as-judge works well for subjective categories).

Example: turning `unnecessary_caveat` into a test case:

```python
# Scorer for unnecessary_caveat
def caveat_scorer(output: str, question: str) -> float:
    """Returns 0.0 if output contains unnecessary hedging, 1.0 if it's direct."""
    # Use LLM-as-judge for this
    prompt = f"""Does this response to an HR policy question contain unnecessary caveats 
    or hedges when the answer is clear policy?

    QUESTION: {question}
    RESPONSE: {output}

    Answer with JSON: {{"has_unnecessary_caveat": true/false, "reason": "..."}}"""
    # ... LLM call ...
```

---

## When to Stop

You're done when:
- Saturation is reached (last 10 outputs, 0 new categories)
- Every category has at least 3 examples
- You can write a test case definition for each category
- The total failure rate and category distribution match your intuition from using the system

---

## Outputs to Produce

After completing error analysis, you should have:

1. `annotations.json`: the full annotated dataset
2. `taxonomy.md`: one paragraph per category, with 3 examples
3. `test_cases/`: one test case file per category
4. A prioritized fix list: categories ranked by count * severity

The fix list drives your prompt engineering, retrieval tuning, and guardrails work for the next sprint.
