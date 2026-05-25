"""
Lesson 09: CI for Prompts: Regression on Every Change
Phase 05: Evaluation & Eval-Driven Development

Demonstrates:
- eval_runner.py: CLI tool that runs evals and exits 1 on regression
- eval_config.yaml: threshold and dataset config
- GitHub Actions workflow template (printed to stdout)
- End-to-end demo: inject a regression, verify CI catches it

Run:
    uv run main.py

Or as the CI runner:
    python main.py --experiment my-run --baseline main --dataset data/smoke.json

Requires: ANTHROPIC_API_KEY
"""

import argparse
import json
import os
import sys
import difflib
import statistics
import yaml
from datetime import datetime
from pathlib import Path
from typing import Callable

from anthropic import Anthropic

client = Anthropic()

RESULTS_DIR = Path("eval_results")


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------

def exact_match(case: dict, actual: str) -> float:
    return 1.0 if actual.strip() == case.get("expected", "").strip() else 0.0


def fuzzy_match(case: dict, actual: str, threshold: float = 0.7) -> float:
    ratio = difflib.SequenceMatcher(
        None, actual.lower(), case.get("expected", "").lower()
    ).ratio()
    return 1.0 if ratio >= threshold else 0.0


def format_compliance(case: dict, actual: str) -> float:
    """1.0 if output is valid JSON, 0.0 otherwise."""
    try:
        text = actual.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
        json.loads(text.strip())
        return 1.0
    except (json.JSONDecodeError, IndexError, ValueError):
        return 0.0


SCORER_REGISTRY: dict[str, Callable[[dict, str], float]] = {
    "exact_match": exact_match,
    "fuzzy_match": fuzzy_match,
    "format_compliance": format_compliance,
}


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------

def run_experiment(
    dataset: list[dict],
    experiment_name: str,
    system_prompt: str = "Answer concisely.",
    results_dir: Path = RESULTS_DIR,
) -> dict:
    """
    Run the system on all cases, score each, store to disk.
    Returns the experiment record.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for i, case in enumerate(dataset):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            system=case.get("system_prompt", system_prompt),
            messages=[{"role": "user", "content": case["input"]}],
        )
        actual = response.content[0].text

        scores = {
            name: scorer(case, actual) for name, scorer in SCORER_REGISTRY.items()
        }
        results.append(
            {
                "case_id": case.get("id", f"c{i}"),
                "input": case["input"],
                "expected": case.get("expected", ""),
                "actual": actual,
                "scores": scores,
            }
        )

    experiment = {
        "name": experiment_name,
        "timestamp": datetime.utcnow().isoformat(),
        "n": len(results),
        "results": results,
    }

    path = results_dir / f"{experiment_name}.json"
    path.write_text(json.dumps(experiment, indent=2))
    return experiment


# ---------------------------------------------------------------------------
# Threshold checking
# ---------------------------------------------------------------------------

def load_means(experiment_name: str, results_dir: Path = RESULTS_DIR) -> dict:
    """Load an experiment from disk and return per-metric means."""
    path = results_dir / f"{experiment_name}.json"
    exp = json.loads(path.read_text())
    all_scores: dict[str, list] = {}
    for r in exp["results"]:
        for metric, score in r["scores"].items():
            all_scores.setdefault(metric, []).append(score)
    return {m: statistics.mean(s) for m, s in all_scores.items()}


def check_thresholds(
    baseline_means: dict,
    current_means: dict,
    thresholds: dict[str, float],
) -> list[dict]:
    """
    Returns list of regression dicts. Empty = all thresholds pass.

    thresholds: {metric: max_allowed_drop_as_fraction}
    Example: {"exact_match": 0.03, "format_compliance": 0.0}
    """
    failures = []
    for metric, max_drop in thresholds.items():
        baseline = baseline_means.get(metric, 0.0)
        current = current_means.get(metric, 0.0)
        delta = current - baseline
        if delta < -max_drop:
            failures.append(
                {
                    "metric": metric,
                    "baseline": round(baseline, 4),
                    "current": round(current, 4),
                    "delta": round(delta, 4),
                    "threshold": max_drop,
                }
            )
    return failures


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(baseline_means: dict, current_means: dict, failures: list[dict]) -> None:
    all_metrics = sorted(set(list(baseline_means) + list(current_means)))
    print(f"\n{'Metric':<25} {'Baseline':>10} {'Current':>10} {'Delta':>10} {'Status':>12}")
    print("-" * 70)
    for metric in all_metrics:
        b = baseline_means.get(metric, 0.0)
        c = current_means.get(metric, 0.0)
        delta = c - b
        status = "REGRESSION" if any(f["metric"] == metric for f in failures) else "ok"
        print(f"  {metric:<23} {b:>10.3f} {c:>10.3f} {delta:>+10.3f} {status:>12}")


def generate_pr_comment(failures: list[dict], experiment: str, baseline: str) -> str:
    """Generate the markdown comment text for a failing PR."""
    lines = [
        "## Eval CI Failed",
        "",
        f"Comparing `{experiment}` to baseline `{baseline}`:",
        "",
        "| Metric | Baseline | Current | Drop | Threshold |",
        "|--------|----------|---------|------|-----------|",
    ]
    for f in failures:
        lines.append(
            f"| {f['metric']} | {f['baseline']:.3f} | {f['current']:.3f} "
            f"| {abs(f['delta']):.1%} | {f['threshold']:.1%} |"
        )
    lines += [
        "",
        "**To fix:** update the prompt to restore metric scores above threshold.",
        "",
        "**For intentional changes:** add `[eval-override: reason]` to the PR description "
        "and get approval from a team lead. Then update the golden set in a follow-up PR.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run eval CI and check for regressions.")
    parser.add_argument("--experiment", required=True, help="Name for this run")
    parser.add_argument("--baseline", required=True, help="Baseline experiment name")
    parser.add_argument("--dataset", default="data/golden_set_smoke.json")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.03,
        help="Global max allowed metric drop (fraction, default 0.03 = 3%)",
    )
    parser.add_argument("--results-dir", default="eval_results")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)

    print(f"Eval CI: experiment='{args.experiment}' baseline='{args.baseline}'")
    print(f"Dataset: {args.dataset}  Threshold: {args.threshold:.0%}")

    # Load dataset
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"ERROR: dataset not found at {dataset_path}")
        sys.exit(2)
    dataset = json.loads(dataset_path.read_text())

    # Run experiment
    print(f"\nRunning {len(dataset)} cases...")
    run_experiment(dataset, args.experiment, results_dir=results_dir)

    # Load baseline (must already exist)
    baseline_path = results_dir / f"{args.baseline}.json"
    if not baseline_path.exists():
        print(f"ERROR: baseline experiment '{args.baseline}' not found at {baseline_path}")
        print("Run the harness once with --experiment=main to create the baseline.")
        sys.exit(2)

    baseline_means = load_means(args.baseline, results_dir)
    current_means = load_means(args.experiment, results_dir)

    thresholds = {
        "exact_match": args.threshold,
        "fuzzy_match": args.threshold,
        "format_compliance": 0.0,  # hard threshold: any drop fails
    }

    failures = check_thresholds(baseline_means, current_means, thresholds)
    print_report(baseline_means, current_means, failures)

    if failures:
        print(f"\nFAILED: {len(failures)} regression(s) detected.")
        comment = generate_pr_comment(failures, args.experiment, args.baseline)
        print("\n--- PR Comment (would be posted to GitHub) ---")
        print(comment)
        sys.exit(1)
    else:
        print("\nPASSED: No regressions above threshold.")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Demo: end-to-end without CLI args
# ---------------------------------------------------------------------------

SMOKE_DATASET = [
    {"id": "q01", "input": "What is 8 * 9?", "expected": "72", "system_prompt": "Answer with just the number."},
    {"id": "q02", "input": "Capital of Germany?", "expected": "Berlin", "system_prompt": "Answer with one word."},
    {"id": "q03", "input": "How many sides does a hexagon have?", "expected": "6", "system_prompt": "Answer with just the number."},
    {"id": "q04", "input": "What color do you get mixing red and blue?", "expected": "purple", "system_prompt": "Answer with one word."},
    {"id": "q05", "input": "What is the speed of light unit?", "expected": "m/s", "system_prompt": "Answer with just the unit abbreviation."},
]


def demo():
    """
    Demo without CLI args:
    1. Run baseline
    2. Run a normal experiment (should pass)
    3. Run a regression experiment (should fail)
    """
    results_dir = Path("eval_results_demo")
    results_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("PROMPT CI DEMO")
    print("=" * 60)

    # Step 1: Create baseline
    print("\n[1/3] Running baseline...")
    run_experiment(SMOKE_DATASET, "baseline", results_dir=results_dir)
    baseline_means = load_means("baseline", results_dir)
    print(f"  Baseline means: {baseline_means}")

    # Step 2: Normal experiment (same system prompt)
    print("\n[2/3] Running normal experiment (should pass)...")
    run_experiment(SMOKE_DATASET, "normal-run", results_dir=results_dir)
    current_means = load_means("normal-run", results_dir)
    thresholds = {"exact_match": 0.03, "fuzzy_match": 0.03, "format_compliance": 0.0}
    failures = check_thresholds(baseline_means, current_means, thresholds)
    print_report(baseline_means, current_means, failures)
    print("Result:", "PASSED" if not failures else "FAILED")

    # Step 3: Regression injection: use a bad system prompt that breaks format
    print("\n[3/3] Running regression experiment (should fail format_compliance)...")
    # Manually override: write an experiment with zero format compliance
    bad_results = {
        "name": "regression-run",
        "timestamp": datetime.utcnow().isoformat(),
        "n": len(SMOKE_DATASET),
        "results": [
            {
                "case_id": c["id"],
                "input": c["input"],
                "expected": c.get("expected", ""),
                "actual": "This is a plain text answer, not JSON at all.",
                "scores": {"exact_match": 0.0, "fuzzy_match": 0.0, "format_compliance": 0.0},
            }
            for c in SMOKE_DATASET
        ],
    }
    (results_dir / "regression-run.json").write_text(json.dumps(bad_results, indent=2))

    regression_means = load_means("regression-run", results_dir)
    failures = check_thresholds(baseline_means, regression_means, thresholds)
    print_report(baseline_means, regression_means, failures)

    if failures:
        print(f"\nFAILED as expected: {len(failures)} regression(s) detected.")
        comment = generate_pr_comment(failures, "regression-run", "baseline")
        print("\n--- PR Comment ---")
        print(comment)
    else:
        print("\nERROR: regression was not caught. Check threshold config.")


if __name__ == "__main__":
    # If called with CLI args, use the CLI runner
    if len(sys.argv) > 1:
        main()
    else:
        demo()
