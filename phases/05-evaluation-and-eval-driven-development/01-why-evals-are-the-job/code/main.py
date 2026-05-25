"""
Lesson 05-01: Why Evals Are the Job
A minimal eval harness from scratch: no frameworks, pure Python stdlib + optional braintrust.

Run with: python main.py
Run with Braintrust: BRAINTRUST_API_KEY=your-key python main.py --braintrust
"""

import difflib
import argparse
import json
from typing import Callable


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------

def exact_match(expected: str, actual: str) -> float:
    """Returns 1.0 if strings match exactly (case-insensitive, stripped)."""
    return 1.0 if expected.strip().lower() == actual.strip().lower() else 0.0


def fuzzy_match(expected: str, actual: str) -> float:
    """Returns similarity ratio between 0.0 and 1.0 using difflib."""
    return difflib.SequenceMatcher(None, expected.strip().lower(), actual.strip().lower()).ratio()


def combined_scorer(expected: str, actual: str) -> float:
    """
    Exact match wins if it fires. Otherwise falls back to fuzzy match.
    This is a reasonable default for short factual answers.
    """
    exact = exact_match(expected, actual)
    if exact == 1.0:
        return 1.0
    return fuzzy_match(expected, actual)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def run_eval(
    test_cases: list[dict],
    system_fn: Callable[[str], str],
    scorer_fn: Callable[[str, str], float],
    pass_threshold: float = 0.8,
) -> list[dict]:
    """
    Run a list of test cases through the system and scorer.

    Each test_case must have keys: 'input', 'expected'.
    Returns a list of result dicts with: input, expected, actual, score, pass.
    """
    results = []
    for i, case in enumerate(test_cases):
        print(f"  Running case {i+1}/{len(test_cases)}: {case['input'][:50]}...")
        actual = system_fn(case["input"])
        score = scorer_fn(case["expected"], actual)
        results.append(
            {
                "input": case["input"],
                "expected": case["expected"],
                "actual": actual,
                "score": round(score, 4),
                "pass": score >= pass_threshold,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

def print_results(results: list[dict]) -> None:
    """Print a human-readable results table and aggregate stats."""
    col_w = {"input": 40, "expected": 25, "actual": 25, "score": 6}
    header = (
        f"{'Input':<{col_w['input']}} "
        f"{'Expected':<{col_w['expected']}} "
        f"{'Actual':<{col_w['actual']}} "
        f"{'Score':<{col_w['score']}} Pass"
    )
    print(f"\n{header}")
    print("-" * (sum(col_w.values()) + 10))

    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(
            f"{r['input'][:col_w['input']-2]:<{col_w['input']}} "
            f"{r['expected'][:col_w['expected']-2]:<{col_w['expected']}} "
            f"{r['actual'][:col_w['actual']-2]:<{col_w['actual']}} "
            f"{r['score']:<{col_w['score']}.2f} {status}"
        )

    scores = [r["score"] for r in results]
    passed = sum(1 for r in results if r["pass"])
    mean = sum(scores) / len(scores) if scores else 0.0

    print(f"\nAggregate: {passed}/{len(results)} passed | mean score: {mean:.3f}")
    print(f"Pass rate: {passed/len(results)*100:.1f}%")

    failures = [r for r in results if not r["pass"]]
    if failures:
        print(f"\nFailed cases ({len(failures)}):")
        for r in failures:
            print(f"  Input:    {r['input']}")
            print(f"  Expected: {r['expected']}")
            print(f"  Actual:   {r['actual']}")
            print(f"  Score:    {r['score']:.2f}")
            print()


# ---------------------------------------------------------------------------
# Mock system under test (replace with your actual LLM call)
# ---------------------------------------------------------------------------

# A simple lookup table that simulates a Q&A system with realistic imperfections.
# Real usage: replace this with an anthropic.Anthropic() or openai.OpenAI() call.
_MOCK_ANSWERS = {
    "What is the capital of France?": "Paris",
    "Who wrote Hamlet?": "Shakespeare",  # abbreviated, will fuzzy-fail exact match
    "What year did WWII end?": "The war ended in 1945",  # correct but verbose
    "What is the boiling point of water?": "100°C",  # correct, different format
    "What does HTTP stand for?": "HyperText Transfer Protocol",  # exact
}


def mock_qa_system(question: str) -> str:
    """
    Stand-in for a real LLM. Replace with:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=256,
            messages=[{"role": "user", "content": question}],
        )
        return message.content[0].text
    """
    return _MOCK_ANSWERS.get(question, "I don't know.")


# ---------------------------------------------------------------------------
# Sample dataset
# ---------------------------------------------------------------------------

SAMPLE_TEST_CASES = [
    {"input": "What is the capital of France?", "expected": "Paris"},
    {"input": "Who wrote Hamlet?", "expected": "William Shakespeare"},
    {"input": "What year did WWII end?", "expected": "1945"},
    {"input": "What is the boiling point of water?", "expected": "100 degrees Celsius"},
    {"input": "What does HTTP stand for?", "expected": "HyperText Transfer Protocol"},
]


# ---------------------------------------------------------------------------
# Braintrust integration (optional)
# ---------------------------------------------------------------------------

def run_with_braintrust(test_cases: list[dict]) -> None:
    """
    Run the same eval through Braintrust for experiment tracking.

    Requires: pip install braintrust autoevals
    Requires: BRAINTRUST_API_KEY environment variable
    """
    try:
        from braintrust import Eval
        from autoevals import LevenshteinScorer
    except ImportError:
        print("Install braintrust: pip install braintrust autoevals")
        return

    print("\nRunning eval with Braintrust...")

    Eval(
        "qa-system-lesson-05-01",
        data=[{"input": c["input"], "expected": c["expected"]} for c in test_cases],
        task=lambda input: mock_qa_system(input),
        scores=[LevenshteinScorer],
    )

    print("Done. View results at https://www.braintrust.dev")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 05-01: Minimal eval harness")
    parser.add_argument(
        "--braintrust",
        action="store_true",
        help="Run via Braintrust instead of the manual harness",
    )
    parser.add_argument(
        "--scorer",
        choices=["exact", "fuzzy", "combined"],
        default="combined",
        help="Scoring strategy (default: combined)",
    )
    args = parser.parse_args()

    scorer_map = {
        "exact": exact_match,
        "fuzzy": fuzzy_match,
        "combined": combined_scorer,
    }
    scorer = scorer_map[args.scorer]

    if args.braintrust:
        run_with_braintrust(SAMPLE_TEST_CASES)
        return

    print(f"\n=== Eval Harness: 05-01 ===")
    print(f"Scorer: {args.scorer}")
    print(f"Test cases: {len(SAMPLE_TEST_CASES)}")
    print("\nRunning cases...")

    results = run_eval(SAMPLE_TEST_CASES, mock_qa_system, scorer)
    print_results(results)

    # Save results to JSON for downstream use
    output_path = "eval_results.json"
    with open(output_path, "w") as f:
        json.dump({"scorer": args.scorer, "results": results}, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
