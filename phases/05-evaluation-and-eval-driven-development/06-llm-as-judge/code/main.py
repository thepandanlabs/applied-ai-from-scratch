"""
Lesson 05-06: LLM-as-Judge
Build an LLM judge, calibrate it against human scores, detect verbosity and position bias.
"""

import json
import os
import re
import statistics
from typing import Optional


# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Judge function
# ---------------------------------------------------------------------------

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

    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
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

    # Extract JSON block (handles models that add extra commentary)
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not json_match:
        return {"error": "No JSON found in response", "raw": raw}

    try:
        result = json.loads(json_match.group())
        if "score" not in result:
            return {"error": "Missing 'score' key in response", "raw": raw}
        return result
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw": raw}


# ---------------------------------------------------------------------------
# Labeled holdout set (10 cases shown; use 20 in production)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Pearson correlation
# ---------------------------------------------------------------------------

def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = statistics.mean(xs)
    mean_y = statistics.mean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    std_x = sum((x - mean_x) ** 2 for x in xs) ** 0.5
    std_y = sum((y - mean_y) ** 2 for y in ys) ** 0.5
    if std_x == 0 or std_y == 0:
        return 0.0
    return cov / (std_x * std_y)


# ---------------------------------------------------------------------------
# Calibration harness
# ---------------------------------------------------------------------------

def run_calibration(holdout_cases: list[dict], judge_fn) -> dict:
    """
    Compare judge scores to human scores.
    Returns: {n, mae, pearson_r, agreement_within_1, usable, details}
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
            print(f"  Judge error: {result['error']}")
            continue

        js = int(result["score"])
        hs = int(case["human_score"])
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


# ---------------------------------------------------------------------------
# Bias detection: verbosity
# ---------------------------------------------------------------------------

def test_verbosity_bias(judge_fn) -> dict:
    """
    Compare scores for short correct vs long verbose correct answers.
    Gap > 0.5 indicates verbosity bias.
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
            print(
                f"  [{pair['question'][:40]}] "
                f"short={short_result['score']}  verbose={verbose_result['score']}"
            )

    if not short_scores:
        return {"error": "No valid verbosity test results"}

    avg_short = statistics.mean(short_scores)
    avg_verbose = statistics.mean(verbose_scores)
    gap = avg_verbose - avg_short

    return {
        "avg_short_score": round(avg_short, 2),
        "avg_verbose_score": round(avg_verbose, 2),
        "gap": round(gap, 2),
        "verbosity_bias_detected": gap > 0.5,
        "note": "Gap > 0.5 indicates verbosity bias. Fix: strengthen conciseness rubric anchor.",
    }


# ---------------------------------------------------------------------------
# Bias detection: position bias (pairwise)
# ---------------------------------------------------------------------------

def test_position_bias(judge_fn) -> dict:
    """
    For pairwise evaluation, swap A/B order and measure consistency.
    Consistency < 80% indicates position bias.
    """
    import anthropic

    PAIRWISE_PROMPT = """Which answer better responds to the question? Be objective.

Question: {question}

Answer A: {a}

Answer B: {b}

Output ONLY valid JSON: {{"winner": "A" or "B", "reasoning": "one sentence"}}"""

    client = anthropic.Anthropic()

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

    def call_pairwise(question, a, b):
        prompt = PAIRWISE_PROMPT.format(question=question, a=a, b=b)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {}

    results = []
    for case in pairwise_cases:
        # Order 1: A=answer_a, B=answer_b
        r1 = call_pairwise(case["question"], case["answer_a"], case["answer_b"])
        # Order 2: A=answer_b, B=answer_a (labels swapped)
        r2 = call_pairwise(case["question"], case["answer_b"], case["answer_a"])

        winner1 = r1.get("winner", "?")
        winner2_raw = r2.get("winner", "?")
        # In order2, "A" in the response means answer_b won
        winner2_normalized = "B" if winner2_raw == "A" else ("A" if winner2_raw == "B" else "?")

        consistent = (winner1 == winner2_normalized) and winner1 != "?"
        results.append({
            "question": case["question"][:50],
            "order1_winner": winner1,
            "order2_winner": winner2_normalized,
            "consistent": consistent,
        })

    if not results:
        return {"error": "No pairwise results"}

    consistency_rate = sum(1 for r in results if r["consistent"]) / len(results)
    return {
        "consistency_rate": round(consistency_rate, 2),
        "position_bias_detected": consistency_rate < 0.8,
        "details": results,
        "note": "Consistency < 80% indicates position bias. Fix: run both orders, take majority vote.",
    }


# ---------------------------------------------------------------------------
# Score distribution check (detect compression)
# ---------------------------------------------------------------------------

def check_score_distribution(calibration_details: list[dict]) -> dict:
    """Check if judge scores are compressed (all clustering in narrow range)."""
    scores = [d["judge_score"] for d in calibration_details]
    if not scores:
        return {}
    score_range = max(scores) - min(scores)
    dist = {i: scores.count(i) for i in range(1, 6)}
    compressed = score_range < 2  # only using 2 out of 5 scale points
    return {
        "min": min(scores),
        "max": max(scores),
        "range": score_range,
        "distribution": dist,
        "score_compression_detected": compressed,
        "note": "Range < 2 indicates score compression. Fix: add concrete rubric anchors for 1, 2, and 5.",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY to run live judge calls.")
        print("Demo mode: showing structure only.\n")
        _demo_mode()
        return

    print("=== LLM-as-Judge Demo ===\n")

    # Calibration
    print("--- Running calibration on holdout set ---")
    cal = run_calibration(HOLDOUT_CASES, judge)

    if "error" in cal:
        print(f"Calibration error: {cal['error']}")
        return

    print(f"  n={cal['n']}")
    print(f"  Pearson r:        {cal['pearson_r']:.3f}  (target: >= 0.70)")
    print(f"  MAE:              {cal['mae']:.3f}")
    print(f"  Agreement +/-1:   {cal['agreement_within_1']:.1%}")
    print(f"  Judge mean:       {cal['judge_mean']:.2f}")
    print(f"  Human mean:       {cal['human_mean']:.2f}")
    print(f"  Usable:           {'YES' if cal['usable'] else 'NO -- improve rubric'}")

    print("\n  Per-case results:")
    for d in cal["details"]:
        status = "OK" if d["within_1"] else "MISMATCH"
        print(f"  [{status}] human={d['human_score']}  judge={d['judge_score']}  diff={d['diff']}  {d['question']}")

    # Score distribution
    print("\n--- Score distribution check ---")
    dist = check_score_distribution(cal["details"])
    print(f"  Range: {dist['min']}-{dist['max']}  (range={dist['range']})")
    print(f"  Distribution: {dist['distribution']}")
    print(f"  Compression detected: {dist['score_compression_detected']}")

    # Verbosity bias
    print("\n--- Verbosity bias test ---")
    vb = test_verbosity_bias(judge)
    print(f"  Avg short score:   {vb.get('avg_short_score', '?')}")
    print(f"  Avg verbose score: {vb.get('avg_verbose_score', '?')}")
    print(f"  Gap:               {vb.get('gap', '?')}")
    print(f"  Bias detected:     {vb.get('verbosity_bias_detected', '?')}")

    # Position bias
    print("\n--- Position bias test (pairwise) ---")
    pb = test_position_bias(judge)
    print(f"  Consistency rate:      {pb.get('consistency_rate', '?')}")
    print(f"  Position bias detected: {pb.get('position_bias_detected', '?')}")
    for r in pb.get("details", []):
        print(f"  [{r['question'][:40]}] order1={r['order1_winner']}  order2={r['order2_winner']}  consistent={r['consistent']}")


def _demo_mode():
    """Show the data structures without making API calls."""
    print("Judge prompt structure:")
    print("  - Role: expert evaluator")
    print("  - Inputs: question, expected, actual")
    print("  - Rubric: 1-5 with concrete anchors")
    print("  - Output: JSON {score, reasoning, criteria_scores}")

    print("\nCalibration report structure:")
    example_cal = {
        "n": 10,
        "mae": 0.7,
        "pearson_r": 0.82,
        "agreement_within_1": 0.9,
        "judge_mean": 3.2,
        "human_mean": 3.1,
        "usable": True,
    }
    print(json.dumps(example_cal, indent=2))

    print("\nVerbosity bias result structure:")
    example_vb = {
        "avg_short_score": 4.3,
        "avg_verbose_score": 4.4,
        "gap": 0.1,
        "verbosity_bias_detected": False,
    }
    print(json.dumps(example_vb, indent=2))


if __name__ == "__main__":
    main()
