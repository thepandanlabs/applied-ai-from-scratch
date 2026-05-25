---
name: prompt-llm-judge
description: Production-ready LLM-as-judge prompt template with rubric, calibration checklist, and bias checks
version: "1.0"
phase: "05"
lesson: "06"
tags: [eval, llm-judge, calibration, bias, rubric]
---

# Prompt: LLM-as-Judge

A production-ready judge prompt and calibration checklist for evaluating AI-generated outputs.

---

## The judge prompt

Copy this prompt and fill in the bracketed sections for your domain.

```
You are an expert evaluator for [describe your system, e.g., "AI-generated answers to customer support questions"].

Your task: score the ACTUAL ANSWER against the CRITERIA below. Be strict. Use the full 1-5 scale.

---
QUESTION: {question}

EXPECTED ANSWER (use as a reference for correctness, not as the only acceptable phrasing):
{expected}

ACTUAL ANSWER (the response you are evaluating):
{actual}

---
SCORING RUBRIC:

Score 5: [Describe what an excellent answer looks like in your domain. Example: "Correct, complete, directly addresses the question, no unnecessary filler."]
Score 4: [Describe a good but not perfect answer. Example: "Correct, minor omission that does not affect usefulness."]
Score 3: [Describe an acceptable but flawed answer. Example: "Mostly correct, but has one factual gap or unclear section."]
Score 2: [Describe a poor answer. Example: "Contains a significant factual error or misleading statement."]
Score 1: [Describe an unacceptable answer. Example: "Wrong answer, hallucination, or did not attempt to answer."]

Important: Do NOT give every answer a 3 or 4. Reserve 5 for genuinely excellent answers.
Use 1 and 2 for wrong or harmful answers.

---
CRITERIA:
[List 3-5 domain-specific quality criteria. Example:]
- Factual accuracy: the answer matches the expected answer or known policy
- Completeness: all critical information is present
- Conciseness: no unnecessary filler or repetition
- Safety: no harmful, offensive, or policy-violating content

---
Output ONLY valid JSON in this exact format. Do not include any text outside the JSON block.

{
  "score": <integer 1-5>,
  "reasoning": "<one paragraph explaining the score, citing specific issues if score < 5>",
  "criteria_scores": {
    "factual_accuracy": <integer 1-5>,
    "completeness": <integer 1-5>,
    "conciseness": <integer 1-5>,
    "safety": <integer 1-5>
  }
}
```

---

## Scoring rubric: how to write concrete anchors

Vague anchors produce score compression (everything scores 3-4). Concrete anchors force the judge to use the full scale.

**Vague (bad):**
```
5 = Excellent
4 = Good
3 = Acceptable
2 = Poor
1 = Very poor
```

**Concrete (good):**
```
5 = Correct, complete, no unnecessary filler, matches policy exactly
4 = Correct, one minor omission that doesn't change the user's action
3 = Mostly correct, one factual gap the user would need to follow up on
2 = Contains a wrong date, wrong amount, or wrong policy rule
1 = States the opposite of policy, hallucinates a product, or refuses to answer
```

The test: if you could give 10 different answers that all get a "4," your anchor for 4 is too vague.

---

## Required JSON output format

Always require structured JSON output from the judge. Free-text output is not parseable at scale.

Required keys:
- `score`: integer 1-5
- `reasoning`: string, one paragraph, must cite specific issues for scores below 5
- `criteria_scores`: dict of criterion name to integer 1-5

The `criteria_scores` field gives you diagnostic information: if the overall score is 2 but `safety` is 5 and `factual_accuracy` is 1, you know the failure mode is factual accuracy, not safety.

---

## Calibration checklist

Before using a judge in production, run this checklist:

**Step 1: Build a labeled holdout set (minimum 20 cases)**
- Include a range of quality levels: 3-4 cases at each score level (1-5)
- Have a domain expert (not the prompt author) label each case
- Cases should cover all major failure modes from your error taxonomy

**Step 2: Run the judge on all holdout cases**

**Step 3: Compute calibration metrics**
- Pearson correlation with human scores: target >= 0.7
- Mean absolute error: target <= 1.0 point
- Agreement within 1 point: target >= 80%

**Step 4: Check the score distribution**
- Plot the distribution of judge scores. If 70%+ of scores are in the 3-4 range, the rubric anchors are too vague.
- Fix: strengthen the anchor for score 2 (when would a judge actually give a 2?) and score 5.

**Step 5: Acceptance gate**
- Pearson r >= 0.7: judge is usable
- Pearson r 0.5-0.7: judge can be used as a weak signal, not as primary metric
- Pearson r < 0.5: fix the rubric before using in production

---

## Bias-checking instructions

Run these checks before deploying any judge:

### Verbosity bias check

Create 3 pairs: (short correct answer, long verbose correct answer). Score both.
If verbose answers score more than 0.5 points higher on average, you have verbosity bias.

Fix: add an explicit conciseness criterion with a concrete anchor:
"Score 5 requires conciseness. A correct but unnecessarily long answer is at most a 4."

### Position bias check (pairwise evaluation)

For any pairwise (A vs B) judge, run each case twice: once with A first, once with B first.
If the winner changes in more than 20% of cases, you have position bias.

Fix: always run both orders and take the majority vote (or average the pairwise wins).

### Self-preference check

Use a different model as the judge than the model being evaluated.
If you're evaluating Claude outputs, consider using GPT-4 as judge (and vice versa).
Note: self-preference bias is harder to detect but calibration against human scores will catch it indirectly.

---

## Calibration schedule

| Event | Action |
|---|---|
| First deployment | Full calibration (20-case holdout) |
| Every 90 days | Re-run calibration on same holdout |
| Model version update | Re-run calibration immediately |
| New eval domain added | Build new domain-specific holdout, calibrate separately |
| Pearson r drops below 0.7 | Investigate: check score distribution, review 5 worst-agreement cases, revise rubric |

---

## When to use a custom judge vs RAGAS

**Use a custom judge when:**
- You're not building a RAG system
- The quality criteria are specific to your domain (tone, policy compliance, brand voice)
- You need to evaluate multi-part answers where each part has different criteria
- RAGAS metrics don't cover your failure modes

**Use RAGAS faithfulness when:**
- You're building a RAG system and need to check that answers are grounded in retrieved context
- You want a peer-reviewed metric without running calibration from scratch

**Use RAGAS answer_relevancy when:**
- You need to verify that the answer addresses the question (not just retrieval faithfulness)

You can use both: RAGAS metrics for RAG-specific checks, custom judge for domain-specific quality.
