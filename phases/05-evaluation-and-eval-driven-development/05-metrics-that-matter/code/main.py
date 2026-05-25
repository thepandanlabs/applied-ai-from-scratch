"""
Lesson 05-05: Metrics That Matter
Build a metric computation library: exact match, fuzzy match, format compliance,
segmented reporting. Then show the same via RAGAS and Braintrust.
"""

import difflib
import json
import statistics
from collections import defaultdict
from typing import Callable


# ---------------------------------------------------------------------------
# Core metric functions
# ---------------------------------------------------------------------------

def exact_match(expected: str, actual: str) -> float:
    """1.0 if strings match exactly (case-insensitive, stripped), 0.0 otherwise."""
    return 1.0 if expected.strip().lower() == actual.strip().lower() else 0.0


def fuzzy_match(expected: str, actual: str) -> float:
    """
    Sequence-based similarity score between 0.0 and 1.0.
    Uses difflib.SequenceMatcher (Ratcliff/Obershelp algorithm).
    Good for short-form answers where exact match is too strict.
    """
    return difflib.SequenceMatcher(None, expected.lower(), actual.lower()).ratio()


def format_compliance(actual: str, required_keys: list[str]) -> float:
    """
    Returns (keys present / total required keys) for JSON outputs.
    0.0 if the output is not valid JSON.
    """
    try:
        parsed = json.loads(actual)
    except json.JSONDecodeError:
        return 0.0
    if not isinstance(parsed, dict):
        return 0.0
    present = sum(1 for k in required_keys if k in parsed)
    return present / len(required_keys) if required_keys else 1.0


# ---------------------------------------------------------------------------
# Metric report aggregator
# ---------------------------------------------------------------------------

ScorerFn = Callable[[str, str], float]


def metric_report(
    cases: list[dict],
    scorers: dict[str, ScorerFn],
) -> dict:
    """
    Run each scorer over all cases and compute per-metric statistics.

    cases: list of {"expected": str, "actual": str, ...}
    scorers: dict of metric_name -> scorer(expected, actual) -> float
    Returns: dict of metric_name -> {mean, min, max, p25, p75, pass_rate, n}
    """
    per_metric: dict[str, list[float]] = {name: [] for name in scorers}

    for case in cases:
        for name, scorer in scorers.items():
            score = scorer(case["expected"], case["actual"])
            per_metric[name].append(score)

    report = {}
    for name, scores in per_metric.items():
        sorted_scores = sorted(scores)
        n = len(sorted_scores)
        report[name] = {
            "mean": round(statistics.mean(scores), 3),
            "min": round(min(scores), 3),
            "max": round(max(scores), 3),
            "p25": round(sorted_scores[n // 4], 3),
            "p75": round(sorted_scores[(3 * n) // 4], 3),
            "pass_rate": round(sum(1 for s in scores if s >= 0.5) / n, 3),
            "n": n,
        }
    return report


def segmented_report(
    cases: list[dict],
    scorers: dict[str, ScorerFn],
    segment_key: str = "difficulty",
) -> dict:
    """
    Run metric_report broken down by a segment key (e.g., difficulty or category).
    Returns: {segment_value: metric_report_dict}
    """
    segments: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        segments[case.get(segment_key, "unknown")].append(case)

    return {
        seg: metric_report(seg_cases, scorers)
        for seg, seg_cases in segments.items()
    }


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_CASES = [
    {
        "input": "What is the return policy?",
        "expected": "Items can be returned within 30 days of purchase.",
        "actual": "You can return items within 30 days of purchase.",
        "category": "returns",
        "difficulty": "normal",
    },
    {
        "input": "How do I contact support?",
        "expected": "Email support@example.com or call 1-800-555-0100.",
        "actual": "Contact us at support@example.com.",
        "category": "support",
        "difficulty": "normal",
    },
    {
        "input": "Is there a warranty on electronics?",
        "expected": "Electronics come with a 1-year manufacturer warranty.",
        "actual": "All products have a warranty.",
        "category": "warranty",
        "difficulty": "edge",
    },
    {
        "input": "Can I use two promo codes together?",
        "expected": "No, only one promo code can be applied per order.",
        "actual": "You can combine promo codes for maximum savings!",
        "category": "discounts",
        "difficulty": "adversarial",
    },
    {
        "input": "How long does shipping take?",
        "expected": "Standard shipping takes 5-7 business days.",
        "actual": "Shipping usually takes about a week.",
        "category": "shipping",
        "difficulty": "normal",
    },
    {
        "input": "What payment methods do you accept?",
        "expected": "We accept Visa, Mastercard, Amex, and PayPal.",
        "actual": "We accept all major credit cards.",
        "category": "payments",
        "difficulty": "normal",
    },
    {
        "input": "Can I track my order?",
        "expected": "Yes. You'll receive a tracking link by email once your order ships.",
        "actual": "Yes, order tracking is available.",
        "category": "orders",
        "difficulty": "normal",
    },
    {
        "input": "Do you ship internationally?",
        "expected": "We ship to 45 countries. International shipping takes 10-14 business days.",
        "actual": "International shipping is available to select countries.",
        "category": "shipping",
        "difficulty": "edge",
    },
    {
        "input": "What happens if my item arrives damaged?",
        "expected": "Contact support within 48 hours with photos. We'll send a replacement or issue a full refund.",
        "actual": "We're sorry about that. Please contact support.",
        "category": "returns",
        "difficulty": "edge",
    },
    {
        "input": "Can I cancel a subscription?",
        "expected": "Yes, cancel anytime from your account settings. No cancellation fees.",
        "actual": "Cancellations are handled by our billing team. There may be fees.",
        "category": "billing",
        "difficulty": "adversarial",
    },
]

# Format compliance cases: testing JSON classification output
FORMAT_CASES = [
    {
        "expected": "{}",
        "actual": '{"category": "returns", "intent": "refund_request", "sentiment": "negative"}',
        "required_keys": ["category", "intent", "sentiment"],
        "category": "classification",
        "difficulty": "normal",
    },
    {
        "expected": "{}",
        "actual": '{"category": "shipping"}',
        "required_keys": ["category", "intent", "sentiment"],
        "category": "classification",
        "difficulty": "edge",
    },
    {
        "expected": "{}",
        "actual": "I think this is about returns and the customer is angry.",
        "required_keys": ["category", "intent", "sentiment"],
        "category": "classification",
        "difficulty": "adversarial",
    },
]


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def print_report(report: dict, title: str = "Metric Report") -> None:
    print(f"\n=== {title} ===")
    for metric, stats in report.items():
        print(f"\n  {metric}:")
        print(f"    mean={stats['mean']:.3f}  pass_rate={stats['pass_rate']:.1%}")
        print(
            f"    min={stats['min']:.3f}  "
            f"p25={stats['p25']:.3f}  "
            f"p75={stats['p75']:.3f}  "
            f"max={stats['max']:.3f}  "
            f"n={stats['n']}"
        )


def print_segmented_report(seg_report: dict, title: str = "Segmented Report") -> None:
    print(f"\n=== {title} ===")
    for segment, report in sorted(seg_report.items()):
        print(f"\n  Segment: {segment}")
        for metric, stats in report.items():
            print(
                f"    {metric:20s}  mean={stats['mean']:.3f}  "
                f"pass_rate={stats['pass_rate']:.1%}  n={stats['n']}"
            )


# ---------------------------------------------------------------------------
# Braintrust integration (requires: uv add braintrust)
# ---------------------------------------------------------------------------

def make_exact_match_scorer():
    """Return a Braintrust-compatible scorer function."""
    try:
        import braintrust  # noqa: F401

        def scorer(output: str, expected: str):
            score = exact_match(expected=expected, actual=output)
            return braintrust.Score(
                name="exact_match",
                score=score,
                metadata={"expected_len": len(expected), "actual_len": len(output)},
            )
        return scorer
    except ImportError:
        print("braintrust not installed. Run: uv add braintrust")
        return None


def make_fuzzy_match_scorer():
    """Return a Braintrust-compatible fuzzy match scorer."""
    try:
        import braintrust  # noqa: F401

        def scorer(output: str, expected: str):
            score = fuzzy_match(expected=expected, actual=output)
            return braintrust.Score(name="fuzzy_match", score=score)
        return scorer
    except ImportError:
        print("braintrust not installed. Run: uv add braintrust")
        return None


# ---------------------------------------------------------------------------
# RAGAS integration (requires: uv add ragas datasets)
# ---------------------------------------------------------------------------

def run_ragas_eval_example():
    """
    Example of running RAGAS faithfulness and answer_relevancy.
    Requires: uv add ragas datasets
    """
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy
        from datasets import Dataset

        # Sample RAG outputs (question, answer, retrieved contexts, ground truth)
        rag_samples = [
            {
                "question": "What is the return window?",
                "answer": "Items can be returned within 30 days.",
                "contexts": ["Our return policy allows returns within 30 days of purchase."],
                "ground_truth": "30 days.",
            },
            {
                "question": "Do you offer free shipping?",
                "answer": "Yes, shipping is always free.",
                "contexts": ["Standard shipping is free on orders over $50."],
                "ground_truth": "Free on orders over $50.",
            },
        ]

        dataset = Dataset.from_list(rag_samples)
        result = evaluate(dataset=dataset, metrics=[faithfulness, answer_relevancy])
        print("\n=== RAGAS Results ===")
        print(result)
        return result

    except ImportError:
        print("ragas/datasets not installed. Run: uv add ragas datasets")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    scorers: dict[str, ScorerFn] = {
        "exact_match": exact_match,
        "fuzzy_match": fuzzy_match,
    }

    print("\n=== Running metrics on 10 sample cases ===")
    overall = metric_report(SAMPLE_CASES, scorers)
    print_report(overall, "Overall Report")

    print("\n=== Segmented by difficulty ===")
    by_difficulty = segmented_report(SAMPLE_CASES, scorers, segment_key="difficulty")
    print_segmented_report(by_difficulty, "By Difficulty")

    print("\n=== Segmented by category ===")
    by_category = segmented_report(SAMPLE_CASES, scorers, segment_key="category")
    print_segmented_report(by_category, "By Category")

    # Format compliance
    print("\n=== Format compliance (JSON classification output) ===")
    for i, case in enumerate(FORMAT_CASES):
        required = case["required_keys"]
        score = format_compliance(case["actual"], required)
        status = "PASS" if score >= 1.0 else "PARTIAL" if score > 0.0 else "FAIL"
        print(f"  Case {i+1} [{case['difficulty']:12s}]: score={score:.2f} [{status}]")

    print("\n=== Key insight ===")
    normal_pass = by_difficulty.get("normal", {}).get("fuzzy_match", {}).get("pass_rate", 0)
    adversarial_pass = by_difficulty.get("adversarial", {}).get("fuzzy_match", {}).get("pass_rate", 0)
    overall_pass = overall.get("fuzzy_match", {}).get("pass_rate", 0)
    print(f"  Overall fuzzy_match pass rate: {overall_pass:.1%}")
    print(f"  Normal cases:                  {normal_pass:.1%}")
    print(f"  Adversarial cases:             {adversarial_pass:.1%}")
    if adversarial_pass < normal_pass:
        gap = normal_pass - adversarial_pass
        print(f"  Gap: {gap:.1%} -- adversarial cases are underperforming.")
        print("  Without segmentation, this regression would be hidden in the overall number.")


if __name__ == "__main__":
    main()
