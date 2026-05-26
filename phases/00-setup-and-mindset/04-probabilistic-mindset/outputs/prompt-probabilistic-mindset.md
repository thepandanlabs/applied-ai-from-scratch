---
name: prompt-probabilistic-mindset
description: Reference guide on probabilistic thinking for AI engineering -- how to test, debug, and design systems where outputs vary
version: "1.0"
phase: "00"
lesson: "04"
tags: [testing, evaluation, temperature, variance, debugging, mindset]
---

# The Probabilistic Mindset for AI Engineering

## The Core Mental Model

A language model is a sampler, not a function.

```
Function:   f(x) = y     (same input always produces same output)
Sampler:    m(x) ~ P(y|x) (same input produces a draw from a distribution)
```

Every time you call the API, you get one sample from the model's output distribution. The distribution is shaped by the prompt and temperature. Your engineering job is to design systems that work reliably across the distribution, not just on individual samples.

---

## The 5 Failure Modes

| Failure Mode | What It Looks Like | The Fix |
|---|---|---|
| Testing one output | Unit test passes, ships with 8% failure rate | Test N outputs, measure pass rate |
| Exact string matching | `if response == "yes"` misses "Yes", "YES", "yes." | Normalize before comparing |
| Assuming idempotency | Re-running to "verify a fix" | Test with a distribution, not a re-run |
| Trusting a small eval | 9/10 on 10 examples = good enough | 50-100 examples minimum; 500+ for production |
| Brittle if/else on output | Parser breaks on unexpected format | Build robust parsers with fallback handling |

---

## Temperature Guide

| Temperature | Variance | Use For |
|---|---|---|
| 0.0 | Minimal | Classification, extraction, structured output, routing |
| 0.1-0.3 | Low | Q&A with specific correct answers, data transformation |
| 0.4-0.6 | Moderate | Summarization, explanation, translation |
| 0.7-0.9 | High | Creative writing, brainstorming, varied phrasing |
| 1.0 | Highest (default) | Exploratory generation, diversity sampling |

Note: temperature=0.0 is not fully deterministic due to GPU floating-point non-determinism. Expect occasional variation even at 0.0.

---

## How to Test AI Features

```python
def eval_classifier(
    client,
    test_cases: list[tuple[str, str]],
    n_per_case: int = 10,
    temperature: float = 0.0,
) -> dict:
    """
    Evaluate a classifier over N runs per test case.
    Returns per-case pass rate and overall accuracy.
    """
    results = {}
    for text, expected_label in test_cases:
        passes = 0
        for _ in range(n_per_case):
            predicted = classify(client, text, temperature=temperature)
            if predicted == expected_label:
                passes += 1
        pass_rate = passes / n_per_case
        results[text] = {"expected": expected_label, "pass_rate": pass_rate}
        print(f"  {text[:40]:40} pass rate: {pass_rate:.0%}")

    overall = sum(r["pass_rate"] for r in results.values()) / len(results)
    print(f"\nOverall accuracy: {overall:.1%} (over {n_per_case} runs per case)")
    return results
```

---

## Robust Output Handling Pattern

```python
def normalize_label(raw_output: str, valid_labels: list[str]) -> str:
    """
    Map a raw model output to a valid label.
    Handles: case variation, punctuation, extra text.
    Returns 'UNKNOWN' and logs if no label matches.
    """
    normalized = raw_output.strip().upper()

    for label in valid_labels:
        if label.upper() in normalized:
            return label.upper()

    # Log for prompt improvement -- unexpected outputs reveal prompt gaps
    print(f"WARNING: could not map output {raw_output!r} to any of {valid_labels}")
    return "UNKNOWN"


# Usage:
LABELS = ["POSITIVE", "NEGATIVE", "NEUTRAL"]
label = normalize_label(response.content[0].text, LABELS)
```

---

## Debugging a Probabilistic System

**Wrong approach:** Run the failing case once. It works. Close the bug.

**Correct approach:**

1. Reproduce the failure at scale: run the failing case 20-50 times and measure the failure rate.
2. Isolate the distribution: is the failure concentrated on specific input types, input lengths, or specific phrasings?
3. Identify the root cause in the distribution: is the prompt ambiguous? Does the output format vary in ways your parser does not handle? Is temperature too high for this task type?
4. Fix at the distribution level: improve the prompt, add normalization, or lower temperature.
5. Verify the fix at the distribution level: run 20-50 times again and confirm the failure rate dropped.

A fix that makes one trace pass is not a fix. A fix that changes the distribution is a fix.

---

## Minimum Viable Eval Sizes

| Stage | Minimum Cases | Runs Per Case | Why |
|---|---|---|---|
| Development | 20-50 | 5-10 | Catch obvious failure modes |
| Pre-launch | 100-200 | 10-20 | Representative tail coverage |
| Production monitoring | Continuous | 1 (log all) | Catch distribution shift |
| A/B test | 500+ | 1 | Statistical significance |

---

## Structured Output Reduces Variance

When you need reliable parsing, use structured output to constrain the distribution:

```python
import json

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=64,
    temperature=0.0,
    messages=[{
        "role": "user",
        "content": (
            "Classify the sentiment. Respond with valid JSON only: "
            '{"label": "POSITIVE"|"NEGATIVE"|"NEUTRAL", "confidence": 0.0-1.0}\n\n'
            f"Text: {text}"
        ),
    }],
)

try:
    result = json.loads(response.content[0].text)
    label = result["label"]
    confidence = result["confidence"]
except (json.JSONDecodeError, KeyError) as e:
    # Still handle failures -- JSON parsing can fail too
    label = "UNKNOWN"
    confidence = 0.0
    print(f"Parse error: {e}")
```

Even with structured output prompting, parse failures will occur at some rate. Always have a fallback.

---

## Key Numbers to Know

- A model at temperature=1.0 on a simple classification task: expect 10-25% variance in output phrasing
- A model at temperature=0.0 on the same task: expect 0-5% variance
- Production AI features with `>5%` "unexpected output format" rate need prompt hardening
- Production AI features with `>2%` wrong answer rate on well-defined tasks need evaluation-driven improvement (Phase 05)
