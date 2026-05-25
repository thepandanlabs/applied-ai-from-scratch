---
name: prompt-pairwise-judge
description: pairwise judge prompt template with position-bias mitigation for comparing two system outputs head-to-head
version: "1.0"
phase: "05"
lesson: "07"
tags: [eval, pairwise, judge, comparison]
---

# Pairwise Judge Prompt Template

Use this prompt to compare two system outputs head-to-head. Always run it twice with swapped order to detect position bias.

## Judge Prompt

```
You are evaluating two AI system responses to the same question.

Question: {question}

Response A:
{output_a}

Response B:
{output_b}

Evaluate both responses against these criteria:
1. Accuracy: Is the information correct and precise?
2. Completeness: Does it fully address the question?
3. Clarity: Is it easy to understand?
4. Usefulness: Would a user act on this confidently?

Instructions:
- Compare the responses directly, not against an abstract ideal.
- Do not favor longer responses unless length adds value.
- If the responses are essentially equivalent, return "tie".
- Your reasoning must cite specific differences, not general impressions.

Respond with JSON only:
{
  "winner": "A" or "B" or "tie",
  "reasoning": "one sentence citing the specific difference that determined your choice",
  "criteria": ["which criterion drove the decision", "secondary criterion if relevant"]
}
```

## Usage Pattern

### Single call (fast, biased)

```python
result = pairwise_judge(question, output_a, output_b)
# result["winner"] is A, B, or tie
# WARNING: may be biased toward whichever output appears first
```

### Debiased call (recommended for production)

```python
# Call 1: A first
result_ab = pairwise_judge(question, output_a, output_b)

# Call 2: B first
result_ba = pairwise_judge(question, output_b, output_a)

# Normalize: when B was "A" in call 2, translate back
flip_map = {"A": "B", "B": "A", "tie": "tie"}
normalized = flip_map[result_ba["winner"]]

if result_ab["winner"] == normalized:
    # Agreement: result is reliable
    final_winner = result_ab["winner"]
    confidence = "high"
else:
    # Disagreement: position bias is likely, call it a tie
    final_winner = "tie"
    confidence = "low"  # flag for human review
```

## Position Bias Mitigation Notes

Position bias: LLM judges statistically favor the response listed first in the prompt. The effect is real and measurable across all major models.

Mitigation: always run the comparison in both orders and check for agreement.

Flip rate interpretation:
- Under 15%: your criteria are clear, bias is low
- 15-30%: acceptable, monitor over time
- Over 30%: your judge prompt needs stronger discriminating criteria

## Preference Rate Calculation

After running across a golden set:

```
wins_a = count of cases where A won
wins_b = count of cases where B won
ties   = count of ties (including flips)

preference_rate_a = wins_a / (wins_a + wins_b)
```

Interpretation:
- 50%: systems are equivalent on your golden set
- 55-60%: slight preference, worth noting but not conclusive under 50 cases
- 60%+: meaningful preference at 30+ cases
- 70%+: strong preference, safe to ship the winning version

## Sample Size Guidelines

| Cases | Minimum detectable difference |
|-------|------------------------------|
| 10    | ~30% (too noisy for most decisions) |
| 30    | ~20% |
| 50    | ~15% |
| 100   | ~10% |

Rule of thumb: you need 30-50 cases before trusting a preference rate for shipping decisions.

## Segmented Analysis

Always break down preference rates by input category before making a shipping decision:

```python
by_category = {}
for case in results["cases"]:
    cat = case.get("category", "unknown")
    by_category.setdefault(cat, {"wins_a": 0, "wins_b": 0, "ties": 0})
    by_category[cat][f"wins_{case['winner'].lower()}"] += 1

for cat, counts in by_category.items():
    decisive = counts["wins_a"] + counts["wins_b"]
    rate = counts["wins_a"] / decisive if decisive else 0.5
    print(f"{cat}: A preference = {rate:.0%} (n={sum(counts.values())})")
```

A system that wins 65% overall but loses 55% on your hardest category is not ready to ship.
