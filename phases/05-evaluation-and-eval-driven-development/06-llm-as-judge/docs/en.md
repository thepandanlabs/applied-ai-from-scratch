**Type:** Build
**Languages:** Python
**Prerequisites:** 05-04 (building a golden set), 05-05 (metrics that matter)
**Time:** ~75 min
**Learning Objectives:**
- Build an LLM-as-judge with a structured rubric and JSON output
- Calibrate a judge against human scores and measure correlation
- Detect and quantify verbosity bias, position bias, and score compression

---

## MOTTO

An uncalibrated judge is worse than no judge: it gives you false confidence.

---

## THE PROBLEM

You ship an LLM-as-judge for your Q&A system. It runs on every eval, scores outputs from 1 to 5, and your dashboard shows a steady 4.2 average. Feels good. Six months later, a senior engineer audits the judge and finds that it gives every output between 3.5 and 4.5 regardless of quality. A completely wrong answer scores 3.8. A perfect answer scores 4.3. The 4.2 average is meaningless.

This is the uncalibrated judge problem. An LLM judge is just another model: it has biases, failure modes, and patterns that systematically distort scores. If you never measure whether the judge agrees with humans, you have no idea what it's actually measuring.

The fix is calibration: before you trust a judge, you verify that its scores correlate with human judgment on a labeled holdout set. And you run bias tests to catch systematic distortions before they corrupt your eval pipeline.

---

## THE CONCEPT

An LLM judge takes a question, an expected output (or criteria), and an actual output, then scores the actual output using a rubric. The key architectural decision is structure: the judge must output valid JSON with numeric scores and reasoning. Free-text output is not parseable at scale.

```mermaid
flowchart LR
    A[Question] --> D[Judge Prompt]
    B[Expected Output\nor Criteria] --> D
    C[Actual Output] --> D
    D --> E[LLM]
    E --> F[JSON Response\nscore + reasoning\n+ criteria_scores]
    F --> G{Calibration\ncheck?}
    G -->|Not yet| H[Run against\nlabeled holdout]
    G -->|Calibrated| I[Use in\neval pipeline]
    H --> J[Compute correlation\nvs human scores]
    J -->|r > 0.7| I
    J -->|r <= 0.7| K[Fix judge prompt\nor rubric]
```

**Judge failure modes:**

```
FAILURE MODE        SYMPTOM                         FIX
----------------    ----------------------------    --------------------------
Verbosity bias      Long answers score higher       Add explicit rubric anchor:
                    regardless of quality           "5 = correct AND concise"
Self-preference     Model scores own outputs        Use a different model as
  bias              higher                          judge than the one being
                                                    evaluated
Position bias       In A/B eval, A wins more        Swap order, check if
                    often than B regardless         winner flips
Score compression   All scores between 3-4,         Use concrete anchors per
                    nothing below 2 or above 5      score (see rubric below)
Criteria drift      Different standards across       Use structured JSON output,
                    runs on same input              same prompt every time
```

**Rubric design: concrete anchors prevent score compression**

```
SCORE   VAGUE ANCHOR        CONCRETE ANCHOR (for Q&A)
-----   ----------------    -----------------------------------------------
5       Excellent           Correct, complete, cites source, concise
4       Good                Correct, minor omission that doesn't affect use
3       Acceptable          Mostly correct, one factual gap or unclear part
2       Poor                Contains a significant factual error
1       Unacceptable        Wrong, hallucinated, or harmful
```

Vague anchors produce score compression. Concrete anchors force the judge to distinguish between quality levels.

---

## BUILD IT

### Step 1: Judge prompt template

```python
# code/main.py
import json
import re
import statistics
from typing import Optional

JUDGE_PROMPT = """You are an expert evaluator for AI-generated answers to customer questions.

Your task: score the ACTUAL ANSWER against the CRITERIA below. Be strict. Use the full 1-5 scale.

---
QUESTION: {question}

EXPECTED ANSWER (use as a reference for correctness, not as the only acceptable phrasing):
{expected}

ACTUAL ANSWER (the response you are evaluating):
{actual}

---
SCORING RUBRIC:

Score 5: Correct, complete, directly addresses the question, no unnecessary filler.
Score 4: Correct, minor omission that does not affect usefulness (e.g., missing one detail that is not critical).
Score 3: Mostly correct, but has one factual gap or one unclear section that a user would need to follow up on.
Score 2: Contains a significant factual error, wrong policy, or misleading statement.
Score 1: Wrong answer, hallucination, harmful content, or did not attempt to answer the question.

---
CRITERIA (what makes a good answer for this system):
- Factual accuracy: the answer matches the expected answer or known policy
- Completeness: all critical information is present
- Conciseness: no unnecessary filler or repetition
- Safety: no harmful, offensive, or policy-violating content

---
Output ONLY valid JSON in this exact format. Do not include any text outside the JSON block.

{{
  "score": <integer 1-5>,
  "reasoning": "<one paragraph explaining the score, citing specific issues if score < 5>",
  "criteria_scores": {{
    "factual_accuracy": <integer 1-5>,
    "completeness": <integer 1-5>,
    "conciseness": <integer 1-5>,
    "safety": <integer 1-5>
  }}
}}"""
```

### Step 2: The judge function

```python
def judge(
    question: str,
    expected: str,
    actual: str,
    model: str = "claude-sonnet-4-6",
    api_key: Optional[str] = None,
) -> dict:
    """
    Call the LLM judge and return structured scores.
    Returns: {score, reasoning, criteria_scores} or {error} on failure.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = JUDGE_PROMPT.format(
        question=question,
        expected=expected,
        actual=actual,
    )

    message = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Extract JSON from response (handles cases where model adds extra text)
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not json_match:
        return {"error": "No JSON found in response", "raw": raw}

    try:
        result = json.loads(json_match.group())
        return result
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw": raw}
```

### Step 3: Calibration harness

```python
# Labeled holdout set: 20 cases with human scores
# Format: {question, expected, actual, human_score (1-5)}
HOLDOUT_CASES = [
    {
        "question": "What is the return policy?",
        "expected": "Items can be returned within 30 days of purchase with original receipt.",
        "actual": "You can return items within 30 days of purchase with your receipt.",
        "human_score": 5,
    },
    {
        "question": "How long does standard shipping take?",
        "expected": "Standard shipping takes 5-7 business days.",
        "actual": "Shipping usually takes about a week.",
        "human_score": 4,
    },
    {
        "question": "Do you offer a student discount?",
        "expected": "Yes, 15% off for verified students through StudentBeans.",
        "actual": "We have various discounts available for eligible customers.",
        "human_score": 2,
    },
    {
        "question": "Can I use two promo codes at once?",
        "expected": "No, only one promo code can be applied per order.",
        "actual": "Yes, you can stack multiple promo codes for bigger savings!",
        "human_score": 1,
    },
    {
        "question": "What payment methods do you accept?",
        "expected": "We accept Visa, Mastercard, Amex, and PayPal.",
        "actual": "We accept Visa, Mastercard, American Express, and PayPal.",
        "human_score": 5,
    },
    {
        "question": "How do I track my order?",
        "expected": "You'll receive a tracking link by email once your order ships.",
        "actual": "Order tracking is available in your account dashboard.",
        "human_score": 3,
    },
    {
        "question": "Is there a warranty on electronics?",
        "expected": "Electronics come with a 1-year manufacturer warranty.",
        "actual": "All products include a standard warranty.",
        "human_score": 2,
    },
    {
        "question": "Can I cancel my order?",
        "expected": "Orders can be cancelled within 1 hour of placement if not yet shipped.",
        "actual": "Yes, you can cancel your order.",
        "human_score": 2,
    },
    {
        "question": "What happens if my item arrives damaged?",
        "expected": "Contact support within 48 hours with photos. We'll send a replacement or full refund.",
        "actual": "Contact our support team and we'll make it right.",
        "human_score": 3,
    },
    {
        "question": "Do you ship internationally?",
        "expected": "We ship to 45 countries. International shipping takes 10-14 business days.",
        "actual": "International shipping is available to select countries.",
        "human_score": 2,
    },
]


def run_calibration(holdout_cases: list[dict], judge_fn) -> dict:
    """
    Run the judge on all holdout cases and compare against human scores.
    Returns calibration report with MAE, Pearson correlation, and agreement rate.
    """
    judge_scores = []
    human_scores = []
    details = []

    for case in holdout_cases:
        result = judge_fn(
            question=case["question"],
            expected=case["expected"],
            actual=case["actual"],
        )
        if "error" in result:
            print(f"  Judge error on case: {result['error']}")
            continue

        js = result["score"]
        hs = case["human_score"]
        judge_scores.append(js)
        human_scores.append(hs)
        details.append({
            "question": case["question"][:50],
            "human_score": hs,
            "judge_score": js,
            "diff": abs(js - hs),
            "within_1": abs(js - hs) <= 1,
        })

    if not judge_scores:
        return {"error": "No valid judge results"}

    n = len(judge_scores)
    mae = sum(abs(j - h) for j, h in zip(judge_scores, human_scores)) / n
    agreement_rate = sum(1 for d in details if d["within_1"]) / n

    # Pearson correlation
    pearson_r = _pearson(judge_scores, human_scores)

    return {
        "n": n,
        "mae": round(mae, 3),
        "pearson_r": round(pearson_r, 3),
        "agreement_within_1": round(agreement_rate, 3),
        "judge_mean": round(statistics.mean(judge_scores), 2),
        "human_mean": round(statistics.mean(human_scores), 2),
        "usable": pearson_r >= 0.7,
        "details": details,
    }


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    std_x = (sum((x - mean_x) ** 2 for x in xs) ** 0.5)
    std_y = (sum((y - mean_y) ** 2 for y in ys) ** 0.5)
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)
```

> **Real-world check:** You run calibration and find your judge has a 0.45 Pearson correlation with human scores. Is this judge usable? What would you check first to improve it?

A 0.45 correlation means the judge is better than random but not reliable enough for production. It's not usable as the primary eval signal. Check these three things first: (1) score compression: print the distribution of judge scores. If everything clusters between 3 and 4, your rubric anchors are too vague. (2) Specific cases where human and judge disagreed most (diff >= 2). Often there is a pattern: the judge is consistently lenient on verbosity or consistently harsh on short correct answers. (3) The system prompt wording: even small changes to the rubric anchors can shift correlation by 0.15 to 0.20.

### Step 4: Bias detection

```python
def test_verbosity_bias(judge_fn) -> dict:
    """
    Create pairs of (short correct answer, long verbose correct answer).
    If verbose answers score meaningfully higher, the judge has verbosity bias.
    """
    test_pairs = [
        {
            "question": "What is the return window?",
            "expected": "30 days.",
            "short_correct": "30 days.",
            "verbose_correct": (
                "Thank you for your question! Our return policy allows customers to return "
                "items within a 30-day window from the date of purchase, provided the item "
                "is in its original condition with all tags attached. We want to make sure "
                "you're completely satisfied with your purchase experience with us."
            ),
        },
        {
            "question": "Is express shipping available?",
            "expected": "Yes, express shipping is available for $12.99.",
            "short_correct": "Yes, $12.99.",
            "verbose_correct": (
                "Absolutely! We're pleased to offer express shipping as one of our premium "
                "delivery options. Express shipping is available to all customers for a fee "
                "of $12.99 and delivers within 2 business days. It's a great option if you "
                "need your order quickly for an upcoming event or special occasion."
            ),
        },
        {
            "question": "Do you offer free returns?",
            "expected": "Yes, returns are free within 30 days.",
            "short_correct": "Yes, free within 30 days.",
            "verbose_correct": (
                "Great news! We absolutely offer free returns to all of our valued customers. "
                "You can return any item free of charge within the 30-day return window. "
                "Simply visit the Returns page in your account, download your prepaid label, "
                "and drop off the package at your nearest UPS location. We process refunds "
                "within 5-7 business days once we receive the item."
            ),
        },
    ]

    short_scores = []
    verbose_scores = []

    for pair in test_pairs:
        short_result = judge_fn(
            question=pair["question"],
            expected=pair["expected"],
            actual=pair["short_correct"],
        )
        verbose_result = judge_fn(
            question=pair["question"],
            expected=pair["expected"],
            actual=pair["verbose_correct"],
        )
        if "error" not in short_result and "error" not in verbose_result:
            short_scores.append(short_result["score"])
            verbose_scores.append(verbose_result["score"])

    if not short_scores:
        return {"error": "No valid results"}

    avg_short = statistics.mean(short_scores)
    avg_verbose = statistics.mean(verbose_scores)
    bias_present = (avg_verbose - avg_short) > 0.5

    return {
        "avg_short_score": round(avg_short, 2),
        "avg_verbose_score": round(avg_verbose, 2),
        "gap": round(avg_verbose - avg_short, 2),
        "verbosity_bias_detected": bias_present,
        "note": "Gap > 0.5 indicates verbosity bias. Fix: add explicit rubric anchor for conciseness.",
    }


def test_position_bias(judge_fn) -> dict:
    """
    For pairwise evaluation, swap A/B order and check if winner flips.
    Position bias: the first option wins more than expected by chance.
    """
    pairwise_cases = [
        {
            "question": "What is the return policy?",
            "answer_a": "Items can be returned within 30 days with receipt.",
            "answer_b": "Returns are accepted for 30 days from purchase date.",
        },
        {
            "question": "How long does shipping take?",
            "answer_a": "5-7 business days for standard shipping.",
            "answer_b": "Standard delivery takes about one week.",
        },
    ]

    PAIRWISE_PROMPT = """Which answer better responds to the question?

Question: {question}

Answer A: {a}

Answer B: {b}

Output JSON: {{"winner": "A" or "B", "reasoning": "..."}}"""

    import anthropic
    client = anthropic.Anthropic()

    results = []
    for case in pairwise_cases:
        # Order 1: A first
        prompt1 = PAIRWISE_PROMPT.format(
            question=case["question"], a=case["answer_a"], b=case["answer_b"]
        )
        # Order 2: B first (swap labels)
        prompt2 = PAIRWISE_PROMPT.format(
            question=case["question"], a=case["answer_b"], b=case["answer_a"]
        )

        def call_judge(prompt):
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {}

        r1 = call_judge(prompt1)
        r2 = call_judge(prompt2)

        winner1 = r1.get("winner", "?")
        winner2_raw = r2.get("winner", "?")
        # In order2, "A" means answer_b won, "B" means answer_a won
        winner2 = "B" if winner2_raw == "A" else "A"

        consistent = winner1 == winner2
        results.append({
            "question": case["question"][:50],
            "order1_winner": winner1,
            "order2_winner": winner2,
            "consistent": consistent,
        })

    consistent_count = sum(1 for r in results if r["consistent"])
    consistency_rate = consistent_count / len(results) if results else 0

    return {
        "consistency_rate": round(consistency_rate, 2),
        "position_bias_detected": consistency_rate < 0.8,
        "details": results,
        "note": "Consistency < 80% indicates position bias. Fix: always run both orders and average.",
    }
```

---

## USE IT

The same judge, registered as a Braintrust scorer and compared to RAGAS faithfulness.

```python
import braintrust

def register_judge_as_braintrust_scorer(judge_fn):
    """
    Wrap the custom judge as a Braintrust Score function.
    Braintrust calls this with (output, expected, input) for each eval case.
    """
    def llm_judge_scorer(output: str, expected: str, input: dict) -> braintrust.Score:
        result = judge_fn(
            question=input.get("question", ""),
            expected=expected,
            actual=output,
        )
        if "error" in result:
            return braintrust.Score(
                name="llm_judge",
                score=0.0,
                metadata={"error": result["error"]},
            )
        # Normalize 1-5 to 0.0-1.0
        normalized = (result["score"] - 1) / 4
        return braintrust.Score(
            name="llm_judge",
            score=round(normalized, 3),
            metadata={
                "raw_score": result["score"],
                "reasoning": result.get("reasoning", ""),
                "criteria_scores": result.get("criteria_scores", {}),
            },
        )
    return llm_judge_scorer


def run_judge_experiment(cases, model_fn, judge_fn, experiment_name: str):
    scorer = register_judge_as_braintrust_scorer(judge_fn)

    result = braintrust.Eval(
        "support-bot-evals",
        data=lambda: [
            {"input": {"question": c["input"]}, "expected": c["expected"]}
            for c in cases
        ],
        task=lambda input: model_fn(input["question"]),
        scores=[scorer],
        experiment_name=experiment_name,
    )
    return result
```

**Custom judge vs RAGAS faithfulness:**

```
CUSTOM JUDGE                    RAGAS FAITHFULNESS
------------------------------  --------------------------------
Measures what you define        Measures claim attribution to
                                 retrieved context only
Works on any output type        Requires contexts + answer
Requires calibration work       Pre-validated on benchmarks
Full control of rubric          Fixed methodology
Best for: Q&A, support, code    Best for: RAG systems
  review, style compliance
```

Build your own judge when: the quality criteria are specific to your domain, you need to measure things RAGAS doesn't cover (tone, policy compliance, completeness by your criteria), or you're not building a RAG system.

Use RAGAS faithfulness when: you're building a RAG system and want a peer-reviewed faithfulness metric without calibrating from scratch.

> **Perspective shift:** A PM asks "if the AI is judging AI, how do we know the judge is right?" Walk them through what calibration means in plain language and why it matters more than which model you use as the judge.

Calibration is the process of checking whether the judge agrees with humans on cases where we already know the right answer. We take 20 examples, have a human expert score them, and then have the judge score the same examples. If the judge and the human agree most of the time (correlation above 0.7), we trust the judge on new cases. The model you use as the judge matters less than whether it's been calibrated. A calibrated GPT-3.5 judge is more trustworthy than an uncalibrated GPT-4 judge, because at least you know the calibrated one tracks human judgment.

---

## SHIP IT

The artifact this lesson produces: `outputs/prompt-llm-judge.md`

A production-ready LLM-as-judge prompt template with rubric, calibration checklist, and bias-checking instructions.

---

## EVALUATE IT

How to know your LLM judge is reliable:

**Calibration target:** Pearson correlation >= 0.7 with human scores on a 20-case holdout. Below 0.5 means the judge is not measuring what humans care about. Between 0.5 and 0.7 means it can be used as a weak signal but not as the primary eval metric.

**Consistency check:** Run the same case 5 times. Score variance should be less than 1 point. If the same answer gets a 3 on one run and a 5 on another, the judge is too noisy to be useful.

**Verbosity bias check:** Compare scores for a short correct answer vs a long verbose correct answer. The gap should be less than 0.5 points. If verbose answers score more than 0.5 points higher, add "conciseness" as an explicit scoring criterion with a concrete anchor.

**Recalibrate quarterly:** LLM behavior changes with model updates. After any model version change (including version bumps by your API provider), re-run calibration on your holdout set. A model update can shift your judge's scoring distribution without any changes to your prompt.

**Calibrate on the right domain:** A judge calibrated on customer support questions is not calibrated for code review. If you use the same judge prompt for multiple domains, calibrate separately for each.
