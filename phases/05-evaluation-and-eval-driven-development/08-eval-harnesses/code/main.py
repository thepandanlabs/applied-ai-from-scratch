"""
Lesson 08: Eval Harnesses: Raw to Braintrust / LangSmith / Phoenix
Phase 05: Evaluation & Eval-Driven Development

Demonstrates:
- EvalHarness class: dataset loader, system runner, scorer pipeline, results store, compare engine
- Three scorers: exact_match, fuzzy_match, format_compliance
- run(), compare(), report() on a 10-case golden set
- Equivalent Braintrust pattern (commented out, requires braintrust installed)

Run:
    uv run main.py

Requires: ANTHROPIC_API_KEY
Optional: BRAINTRUST_API_KEY (for the Braintrust section)
"""

import json
import os
import difflib
import statistics
from datetime import datetime
from pathlib import Path
from typing import Callable

from anthropic import Anthropic

client = Anthropic()


# ---------------------------------------------------------------------------
# Scorer interface: (case: dict, actual: str) -> float in [0.0, 1.0]
# ---------------------------------------------------------------------------

def exact_match(case: dict, actual: str) -> float:
    """Binary: 1.0 if actual exactly equals expected (after stripping whitespace)."""
    expected = case.get("expected", "").strip()
    return 1.0 if actual.strip() == expected else 0.0


def fuzzy_match(case: dict, actual: str, threshold: float = 0.7) -> float:
    """1.0 if difflib ratio between actual and expected is at or above threshold."""
    expected = case.get("expected", "").strip()
    ratio = difflib.SequenceMatcher(None, actual.lower(), expected.lower()).ratio()
    return 1.0 if ratio >= threshold else 0.0


def format_compliance(case: dict, actual: str) -> float:
    """1.0 if the actual output contains a valid JSON object (after stripping markdown fences)."""
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


# ---------------------------------------------------------------------------
# Eval Harness
# ---------------------------------------------------------------------------

class EvalHarness:
    """
    A full eval harness with five interchangeable layers:
    1. Dataset  - provided at construction time as list[dict]
    2. Runner   - system_fn(case) -> str
    3. Scorers  - {name: (case, actual) -> float}
    4. Store    - JSON files in results_dir/
    5. Comparison - compare(exp_a, exp_b) -> dict
    """

    def __init__(
        self,
        dataset: list[dict],
        system_fn: Callable[[dict], str],
        scorers: dict[str, Callable[[dict, str], float]],
        results_dir: str = "eval_results",
    ):
        self.dataset = dataset
        self.system_fn = system_fn
        self.scorers = scorers
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def run(self, experiment_name: str) -> dict:
        """
        Run the system on every case, score each output, store results to disk.

        Stores: results_dir/<experiment_name>.json
        Returns: the full experiment dict
        """
        results = []
        print(f"  Running experiment '{experiment_name}' on {len(self.dataset)} cases...")

        for i, case in enumerate(self.dataset):
            actual = self.system_fn(case)
            scores = {name: scorer(case, actual) for name, scorer in self.scorers.items()}
            results.append(
                {
                    "case_id": case.get("id", f"c{i}"),
                    "input": case.get("input", ""),
                    "expected": case.get("expected", ""),
                    "actual": actual,
                    "scores": scores,
                }
            )
            print(f"    [{i+1}/{len(self.dataset)}] {case.get('id', f'c{i}')}: {scores}")

        experiment = {
            "name": experiment_name,
            "timestamp": datetime.utcnow().isoformat(),
            "n": len(results),
            "results": results,
        }

        path = self.results_dir / f"{experiment_name}.json"
        path.write_text(json.dumps(experiment, indent=2))
        print(f"  Stored: {path}")
        return experiment

    def _summarize(self, experiment_name: str) -> dict:
        """Load experiment from disk and compute per-metric summary."""
        path = self.results_dir / f"{experiment_name}.json"
        exp = json.loads(path.read_text())

        all_scores: dict[str, list] = {}
        for result in exp["results"]:
            for metric, score in result["scores"].items():
                all_scores.setdefault(metric, []).append(score)

        return {
            metric: {
                "mean": statistics.mean(scores),
                "pass_rate": sum(1 for s in scores if s >= 1.0) / len(scores),
            }
            for metric, scores in all_scores.items()
        }

    def compare(self, experiment_a: str, experiment_b: str) -> dict:
        """
        Load two experiments from disk. Compute per-metric delta.
        Flags regressions where B drops more than 3% below A.

        Returns:
            {
                "experiment_a": str,
                "experiment_b": str,
                "metrics": {
                    metric: {
                        "a_mean": float, "b_mean": float,
                        "delta": float, "regression": bool
                    }
                }
            }
        """
        summary_a = self._summarize(experiment_a)
        summary_b = self._summarize(experiment_b)
        metrics = set(summary_a) | set(summary_b)

        comparison = {}
        for metric in sorted(metrics):
            a = summary_a.get(metric, {"mean": 0, "pass_rate": 0})
            b = summary_b.get(metric, {"mean": 0, "pass_rate": 0})
            delta = b["mean"] - a["mean"]
            comparison[metric] = {
                "a_mean": round(a["mean"], 4),
                "b_mean": round(b["mean"], 4),
                "delta": round(delta, 4),
                "regression": delta < -0.03,  # >3% drop
            }

        return {
            "experiment_a": experiment_a,
            "experiment_b": experiment_b,
            "metrics": comparison,
        }

    def report(self, experiment_name: str) -> None:
        """Print a formatted summary table for one experiment."""
        summary = self._summarize(experiment_name)

        path = self.results_dir / f"{experiment_name}.json"
        exp = json.loads(path.read_text())
        n = exp["n"]

        print(f"\nExperiment: {experiment_name} ({n} cases, {exp['timestamp'][:10]})")
        print(f"  {'Metric':<25} {'Mean':>8} {'Pass Rate':>12}")
        print("  " + "-" * 45)
        for metric, stats in summary.items():
            print(f"  {metric:<25} {stats['mean']:>8.3f} {stats['pass_rate']:>11.0%}")


def print_comparison(cmp: dict) -> None:
    """Pretty-print a comparison report."""
    print(f"\nComparison: {cmp['experiment_a']} vs {cmp['experiment_b']}")
    print(f"  {'Metric':<25} {'A Mean':>8} {'B Mean':>8} {'Delta':>8} {'Regression?':>12}")
    print("  " + "-" * 65)
    for metric, stats in cmp["metrics"].items():
        reg = "YES" if stats["regression"] else "no"
        print(
            f"  {metric:<25} "
            f"{stats['a_mean']:>8.3f} "
            f"{stats['b_mean']:>8.3f} "
            f"{stats['delta']:>+8.3f} "
            f"{reg:>12}"
        )


# ---------------------------------------------------------------------------
# System under test (two variants for comparison)
# ---------------------------------------------------------------------------

def make_system(system_prompt: str) -> Callable[[dict], str]:
    """Factory: returns a system_fn for the given system prompt."""
    def fn(case: dict) -> str:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            system=system_prompt,
            messages=[{"role": "user", "content": case["input"]}],
        )
        return response.content[0].text
    return fn


# ---------------------------------------------------------------------------
# Golden dataset
# ---------------------------------------------------------------------------

GOLDEN_SET = [
    {"id": "q01", "input": "What is 12 * 8?", "expected": "96"},
    {"id": "q02", "input": "What is the capital of Japan?", "expected": "Tokyo"},
    {"id": "q03", "input": "What color is the sky on a clear day?", "expected": "blue"},
    {"id": "q04", "input": "How many days are in a week?", "expected": "7"},
    {"id": "q05", "input": "What is the boiling point of water in Celsius?", "expected": "100"},
    {"id": "q06", "input": "What is the largest planet in our solar system?", "expected": "Jupiter"},
    {"id": "q07", "input": "What does HTTP stand for?", "expected": "HyperText Transfer Protocol"},
    {"id": "q08", "input": "What programming language was Python named after?", "expected": "Monty Python"},
    {"id": "q09", "input": "How many bits are in a byte?", "expected": "8"},
    {"id": "q10", "input": "What is the square root of 144?", "expected": "12"},
]


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo():
    print("=" * 60)
    print("EVAL HARNESS DEMO")
    print("=" * 60)

    scorers = {
        "exact_match": exact_match,
        "fuzzy_match": fuzzy_match,
        "format_compliance": format_compliance,
    }

    # Baseline: plain "answer concisely"
    system_v1 = make_system("Answer concisely with just the answer, nothing else.")

    # New prompt: adds a qualifier that breaks exact match sometimes
    system_v2 = make_system("Answer in one short phrase. Be precise.")

    harness = EvalHarness(
        dataset=GOLDEN_SET,
        system_fn=system_v1,
        scorers=scorers,
        results_dir="eval_results",
    )

    # Run baseline
    print("\n--- Baseline run ---")
    harness.run("baseline")
    harness.report("baseline")

    # Swap system fn and run new experiment
    harness.system_fn = system_v2
    print("\n--- New prompt run ---")
    harness.run("new-prompt")
    harness.report("new-prompt")

    # Compare
    cmp = harness.compare("baseline", "new-prompt")
    print_comparison(cmp)

    regressions = [m for m, s in cmp["metrics"].items() if s["regression"]]
    if regressions:
        print(f"\nREGRESSIONS DETECTED on: {', '.join(regressions)}")
        print("  -> Do not ship new-prompt without investigating.")
    else:
        print("\nNo regressions detected. New prompt is safe to consider for shipping.")


# ---------------------------------------------------------------------------
# Braintrust equivalent (requires: pip install braintrust; BRAINTRUST_API_KEY)
# ---------------------------------------------------------------------------

def braintrust_equivalent_example():
    """
    Equivalent harness using Braintrust.
    Uncomment and set BRAINTRUST_API_KEY to run.
    """
    # import braintrust
    # from braintrust import Score
    #
    # def bt_format_scorer(input, output, expected, **kwargs) -> Score:
    #     try:
    #         json.loads(output.strip())
    #         return Score(name="format_compliance", score=1.0)
    #     except json.JSONDecodeError:
    #         return Score(name="format_compliance", score=0.0)
    #
    # results = braintrust.Eval(
    #     "my-chatbot",
    #     data=lambda: [{"input": c["input"], "expected": c["expected"]} for c in GOLDEN_SET],
    #     task=lambda input: make_system("Answer concisely.")({"input": input}),
    #     scores=[
    #         braintrust.ExactMatch,
    #         braintrust.Levenshtein,
    #         bt_format_scorer,
    #     ],
    #     experiment_name="baseline"
    # )
    pass


if __name__ == "__main__":
    demo()
