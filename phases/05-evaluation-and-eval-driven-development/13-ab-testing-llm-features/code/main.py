"""
Lesson 13: A/B Testing LLM Features
--------------------------------------
ABRouter  - deterministic user assignment by hashed user_id,
            logs exposures and outcomes to JSONL files

ABAnalyzer - loads logs, computes per-metric statistics,
             runs Welch's t-test for significance, prints report

Demo: simulate 1,000 users across two variants.
Variant B wins on quality_score (significant); conversion_rate is a wash.

Run:
    uv run python main.py

Requirements:
    uv add scipy
"""

import hashlib
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, stdev
from typing import Literal

from scipy import stats


Variant = Literal["A", "B"]


# ---------------------------------------------------------------------------
# ABRouter
# ---------------------------------------------------------------------------

class ABRouter:
    """
    Deterministic A/B router.

    The same user_id always maps to the same variant within an experiment.
    Logs every exposure and outcome to JSONL files.

    Usage:
        router = ABRouter("faq-prompt-test")
        variant = router.assign("user_1234")
        router.log_exposure("user_1234", variant)
        router.log_outcome("user_1234", variant, "quality_score", 0.87)
    """

    def __init__(
        self,
        experiment_name: str,
        split: float = 0.50,
        exposure_log: str = "exposures.jsonl",
        outcome_log: str = "outcomes.jsonl",
    ) -> None:
        self.experiment_name = experiment_name
        self.split = split
        self.exposure_log = Path(exposure_log)
        self.outcome_log = Path(outcome_log)

    def assign(self, user_id: str) -> Variant:
        """
        Deterministic assignment: hash user_id + experiment name to a stable bucket.
        The same (user_id, experiment_name) pair always returns the same variant.
        """
        key = f"{self.experiment_name}:{user_id}"
        digest = int(hashlib.md5(key.encode()).hexdigest(), 16)
        bucket = digest % 100
        return "B" if bucket < int(self.split * 100) else "A"

    def log_exposure(
        self, user_id: str, variant: Variant, timestamp: float | None = None
    ) -> None:
        """Record that a user was exposed to a variant."""
        entry = {
            "experiment": self.experiment_name,
            "user_id": user_id,
            "variant": variant,
            "timestamp": timestamp or time.time(),
        }
        with open(self.exposure_log, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_outcome(
        self,
        user_id: str,
        variant: Variant,
        metric_name: str,
        value: float,
        timestamp: float | None = None,
    ) -> None:
        """Record a metric value for a user in a variant."""
        entry = {
            "experiment": self.experiment_name,
            "user_id": user_id,
            "variant": variant,
            "metric": metric_name,
            "value": value,
            "timestamp": timestamp or time.time(),
        }
        with open(self.outcome_log, "a") as f:
            f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# ABAnalyzer
# ---------------------------------------------------------------------------

@dataclass
class VariantStats:
    variant: str
    n: int
    mean: float
    std: float


class ABAnalyzer:
    """
    Load exposure and outcome logs, compute per-metric statistics,
    and run significance tests.

    Usage:
        analyzer = ABAnalyzer("exposures.jsonl", "outcomes.jsonl")
        analyzer.report(["quality_score", "conversion_rate"])
    """

    def __init__(self, exposure_log: str, outcome_log: str) -> None:
        self.exposures = self._load_jsonl(exposure_log)
        self.outcomes = self._load_jsonl(outcome_log)

    def _load_jsonl(self, path: str) -> list[dict]:
        p = Path(path)
        if not p.exists():
            return []
        lines = p.read_text().strip().splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def compute_stats(self, metric_name: str) -> dict[str, VariantStats]:
        """Compute mean, std, and n per variant for a given metric."""
        values: dict[str, list[float]] = {"A": [], "B": []}

        for entry in self.outcomes:
            if entry.get("metric") == metric_name:
                variant = entry.get("variant")
                if variant in values:
                    values[variant].append(float(entry["value"]))

        result = {}
        for variant, vals in values.items():
            if vals:
                result[variant] = VariantStats(
                    variant=variant,
                    n=len(vals),
                    mean=round(mean(vals), 4),
                    std=round(stdev(vals) if len(vals) > 1 else 0.0, 4),
                )
        return result

    def is_significant(self, metric_name: str, alpha: float = 0.05) -> dict:
        """
        Run Welch's t-test between variant A and B for a metric.

        Returns:
            dict with mean_A, mean_B, lift, p_value, significant, and sample sizes.
        """
        a_vals = [
            e["value"]
            for e in self.outcomes
            if e.get("metric") == metric_name and e.get("variant") == "A"
        ]
        b_vals = [
            e["value"]
            for e in self.outcomes
            if e.get("metric") == metric_name and e.get("variant") == "B"
        ]

        if not a_vals or not b_vals:
            return {"error": f"insufficient data for metric '{metric_name}'"}

        t_stat, p_value = stats.ttest_ind(a_vals, b_vals, equal_var=False)

        mean_a = round(mean(a_vals), 4)
        mean_b = round(mean(b_vals), 4)
        lift = round(mean_b - mean_a, 4)
        lift_pct = round(lift / mean_a * 100, 2) if mean_a != 0 else 0.0

        return {
            "metric": metric_name,
            "n_A": len(a_vals),
            "n_B": len(b_vals),
            "mean_A": mean_a,
            "mean_B": mean_b,
            "lift": lift,
            "lift_pct": lift_pct,
            "p_value": round(float(p_value), 4),
            "significant": bool(p_value < alpha),
            "alpha": alpha,
        }

    def report(self, metrics: list[str] | None = None) -> None:
        """Print a formatted results table."""
        all_metrics = metrics or sorted({e["metric"] for e in self.outcomes})

        print(f"\n{'=' * 82}")
        print(
            f"{'METRIC':<30} {'A MEAN':>8} {'B MEAN':>8} "
            f"{'LIFT':>8} {'LIFT%':>7} {'P-VALUE':>9} {'SIG?':>6}"
        )
        print(f"{'-' * 82}")

        for metric in all_metrics:
            result = self.is_significant(metric)
            if "error" in result:
                print(f"{metric:<30}  (no data)")
                continue

            sig_marker = "YES *" if result["significant"] else "no"
            print(
                f"{metric:<30} "
                f"{result['mean_A']:>8.3f} "
                f"{result['mean_B']:>8.3f} "
                f"{result['lift']:>+8.3f} "
                f"{result['lift_pct']:>+7.1f}% "
                f"{result['p_value']:>9.4f} "
                f"{sig_marker:>6}"
            )

        print(f"{'=' * 82}")
        print("* p < 0.05 (alpha=0.05)")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def check_balance(exposure_log: str, expected_split: float = 0.5, tolerance: float = 0.05) -> None:
    """Verify that exposure counts are within tolerance of the expected split."""
    exposures = [json.loads(l) for l in Path(exposure_log).read_text().splitlines() if l.strip()]
    a_count = sum(1 for e in exposures if e["variant"] == "A")
    b_count = sum(1 for e in exposures if e["variant"] == "B")
    total = a_count + b_count
    actual_b_fraction = b_count / total

    ok = abs(actual_b_fraction - expected_split) < tolerance
    status = "PASS" if ok else "FAIL"
    print(f"[balance-check] {status}: split={actual_b_fraction:.1%} (expected ~{expected_split:.0%})")


def check_no_overlap(exposure_log: str) -> None:
    """Verify no user appears in both variants (deterministic router invariant)."""
    exposures = [json.loads(l) for l in Path(exposure_log).read_text().splitlines() if l.strip()]
    user_variants: dict[str, set] = {}
    for e in exposures:
        user_variants.setdefault(e["user_id"], set()).add(e["variant"])

    overlaps = {uid: v for uid, v in user_variants.items() if len(v) > 1}
    status = "PASS" if not overlaps else f"FAIL (overlaps: {overlaps})"
    print(f"[holdout-check] {status}: {len(user_variants)} unique users checked")


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def simulate_ab_test() -> None:
    """
    Simulate 1,000 users across two variants over ~30 days.
    Variant B wins on quality_score; conversion_rate is not significantly different.
    """
    exp = "faq-prompt-test"

    # Clear previous simulation
    for fname in ["sim_exposures.jsonl", "sim_outcomes.jsonl"]:
        Path(fname).unlink(missing_ok=True)

    router = ABRouter(
        experiment_name=exp,
        split=0.50,
        exposure_log="sim_exposures.jsonl",
        outcome_log="sim_outcomes.jsonl",
    )

    random.seed(42)
    user_ids = [f"user_{i:04d}" for i in range(1000)]

    for user_id in user_ids:
        variant = router.assign(user_id)
        router.log_exposure(user_id, variant)

        if variant == "A":
            quality = round(random.gauss(0.85, 0.08), 3)
            conversion = round(random.gauss(0.32, 0.05), 3)
        else:
            quality = round(random.gauss(0.89, 0.08), 3)   # real improvement
            conversion = round(random.gauss(0.33, 0.05), 3)  # noise only

        quality = max(0.0, min(1.0, quality))
        conversion = max(0.0, min(1.0, conversion))

        router.log_outcome(user_id, variant, "quality_score", quality)
        router.log_outcome(user_id, variant, "conversion_rate", conversion)

    print("\n=== A/B TEST SIMULATION: faq-prompt-test ===")
    print("1,000 users, 50/50 split, 30-day simulation")

    analyzer = ABAnalyzer("sim_exposures.jsonl", "sim_outcomes.jsonl")
    analyzer.report(["quality_score", "conversion_rate"])

    q_result = analyzer.is_significant("quality_score")
    c_result = analyzer.is_significant("conversion_rate")

    print(f"\nQuality:    B {'IS' if q_result['significant'] else 'IS NOT'} significantly better (p={q_result['p_value']})")
    print(f"Conversion: B {'IS' if c_result['significant'] else 'IS NOT'} significantly better (p={c_result['p_value']})")
    print("\nConclusion: Ship B (quality improvement is real). Monitor conversion post-ship.")

    check_balance("sim_exposures.jsonl")
    check_no_overlap("sim_exposures.jsonl")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    simulate_ab_test()
