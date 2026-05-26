---
name: skill-few-shot-cot
description: Reference patterns for few-shot and chain-of-thought prompting, with the SDK messages-array approach for structured examples
version: "1.0"
phase: "01"
lesson: "03"
tags: [prompt-engineering, few-shot, chain-of-thought, reasoning, examples]
---

# Skill: Few-Shot and Chain-of-Thought

Two techniques for improving model output quality. Each has a specific mechanism and a specific use case.

## Quick Decision Guide

| Task type | Recommended technique |
|-----------|----------------------|
| Format/style consistency | Few-shot |
| Multi-step reasoning | Chain-of-thought |
| Ambiguous classification | Few-shot + CoT combined |
| Simple lookup or factual Q&A | Zero-shot |
| High-volume, cost-sensitive | Few-shot (cheaper than CoT) |

---

## Few-Shot Pattern 1: Inline Examples

Examples embedded directly in the prompt. Simple, works well for stable example sets.

```python
FEW_SHOT_PROMPT = """Classify the severity of this support ticket.
Levels: Critical, High, Medium, Low.

Examples:
Ticket: API returning 500 errors for all users. Production down.
Severity: Critical

Ticket: CSV export producing incorrect totals.
Severity: High

Ticket: Search results sometimes show duplicates.
Severity: Medium

Ticket: Can you add dark mode?
Severity: Low

Output only the severity level.

Ticket: {ticket}"""
```

---

## Few-Shot Pattern 2: SDK Messages Array

Examples as user/assistant turn pairs in the messages array. Preferred when examples are loaded dynamically or maintained separately from the prompt.

```python
EXAMPLES = [
    ("API returning 500 errors for all users. Production down.", "Critical"),
    ("CSV export producing incorrect totals.", "High"),
    ("Search results sometimes show duplicates.", "Medium"),
    ("Can you add dark mode?", "Low"),
]

def classify_few_shot(ticket: str, examples: list[tuple]) -> str:
    messages = []
    for example_input, example_output in examples:
        messages.append({"role": "user",      "content": f"Ticket: {example_input}"})
        messages.append({"role": "assistant", "content": example_output})
    messages.append({"role": "user", "content": f"Ticket: {ticket}"})

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        system="Classify support ticket severity: Critical, High, Medium, Low. Output label only.",
        messages=messages
    )
    return response.content[0].text.strip()
```

**Advantages over inline:**
- Examples are a Python list: easy to add, remove, or load from config
- Instructions are in the system prompt, separate from examples
- No string manipulation needed to modify examples

---

## Chain-of-Thought Pattern

Force reasoning before the answer. Two trigger approaches:

**Approach 1: "Think step by step" instruction**

```python
COT_PROMPT = """Classify the severity of this support ticket.
Think through: scope of impact, core functionality affected, time sensitivity.
Then output your final answer as SEVERITY: [level].

Ticket: {ticket}"""
```

**Approach 2: Structured reasoning questions**

```python
COT_SYSTEM = """You are a support triage specialist.
When classifying, answer these questions:
1. Who is affected: one user, some users, or all users?
2. Is core functionality or revenue impacted?
3. Is there a workaround available?
Then assign: Critical / High / Medium / Low."""

COT_USER = """Reason through the 3 questions, then output: SEVERITY: [level]

Ticket: {ticket}"""
```

**Extracting the label from CoT output:**

```python
def extract_severity(cot_output: str) -> str:
    for line in cot_output.split("\n"):
        if line.strip().startswith("SEVERITY:"):
            return line.split(":", 1)[-1].strip()
    return "Unknown"
```

---

## Few-Shot + CoT Combined

Use when you need both: consistent output format (from few-shot) and careful reasoning (from CoT). The examples include the reasoning chain.

```python
FEW_SHOT_COT_PROMPT = """Classify support ticket severity.

Example 1:
Ticket: API returning 500 errors for all users.
Analysis: All users affected, core functionality down, no workaround.
SEVERITY: Critical

Example 2:
Ticket: CSV export shows wrong totals for reports over 1000 rows.
Analysis: Some users affected (large reports), core feature impaired, workaround exists (smaller date ranges).
SEVERITY: High

Now classify:
Ticket: {ticket}
Analysis:"""
```

---

## When Each Technique Fails

**Few-shot fails when:**
- Examples don't cover the input distribution (edge cases not in examples)
- Too many examples dilute the pattern (3-6 is usually optimal)
- Examples conflict with each other in subtle ways

**CoT fails when:**
- The task is a direct lookup (CoT adds cost with no accuracy benefit)
- The reasoning chain leads the model down a wrong path before the answer
- You need a short, deterministic output and CoT output is verbose

**Signs you need CoT over few-shot:**
- Accuracy plateaus with few-shot and errors concentrate on ambiguous cases
- The task requires weighing multiple factors against each other
- Wrong answers are "almost right" but miss a constraint

---

## Cost vs. Accuracy Trade-off

CoT uses 5-10x more output tokens than few-shot for classification tasks.

**Rule of thumb:** Use few-shot as the default. Switch to CoT only for the cases where few-shot consistently fails.

```python
# Routing pattern: CoT only for ambiguous cases
def smart_classify(ticket: str) -> str:
    # First pass: cheap few-shot
    label = classify_few_shot(ticket)

    # If result is ambiguous tier, apply CoT
    if label in ("High", "Medium"):
        label, _ = classify_cot(ticket)

    return label
```

---

## Example Quality Checklist

- [ ] Examples cover the full output distribution (all labels represented)
- [ ] At least 1 example per label for classification tasks
- [ ] Examples represent realistic inputs, not toy cases
- [ ] No duplicate or near-duplicate examples
- [ ] Examples are ordered: consistent (not arranged easy-to-hard)
- [ ] For combined few-shot + CoT: reasoning in examples is correct
