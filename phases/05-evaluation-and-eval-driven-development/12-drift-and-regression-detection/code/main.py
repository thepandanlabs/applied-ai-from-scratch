"""
Lesson 12: Drift & Regression Detection
-----------------------------------------
Two classes for detecting quality degradation over time:

ScoreHistory  - stores daily eval scores, computes rolling means,
                detects trend drift and absolute floor violations

RegressionDetector - compares current experiment metrics to a
                     versioned baseline and flags regressions

Demo: simulate 30 days of scores with an injected drift event at day 20,
then show regression detection across a prompt version bump.

Run:
    uv run python main.py
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path
from statistics import mean


# ---------------------------------------------------------------------------
# ScoreHistory
# ---------------------------------------------------------------------------

class ScoreHistory:
    """
    Store daily eval scores and detect quality drift.

    Usage:
        history = ScoreHistory()
        history.add("2025-01-01", 0.88, version="prompt-v3")
        drift = history.detect_drift(threshold=0.05)
    """

    def __init__(self, path: str = "score_history.json") -> None:
        self.path = Path(path)
        self.history: list[dict] = []
        if self.path.exists():
            self.history = json.loads(self.path.read_text())

    def add(self, score_date: str, score: float, version: str = "unknown") -> None:
        """Append a daily score entry and persist to disk."""
        self.history.append({"date": score_date, "score": score, "version": version})
        self.path.write_text(json.dumps(self.history, indent=2))

    def rolling_mean(self, window: int = 7) -> list[dict]:
        """
        Compute the rolling mean for each date in the history.
        Returns one entry per date starting at index (window - 1).
        """
        if len(self.history) < window:
            return []

        result = []
        for i in range(window - 1, len(self.history)):
            window_scores = [
                self.history[j]["score"] for j in range(i - window + 1, i + 1)
            ]
            result.append(
                {
                    "date": self.history[i]["date"],
                    "rolling_mean": round(mean(window_scores), 4),
                    "window": window,
                }
            )
        return result

    def detect_drift(self, threshold: float = 0.05, window: int = 7) -> dict:
        """
        Return a drift signal if the latest 7-day mean is more than
        `threshold` below the previous 7-day mean.

        Args:
            threshold: minimum drop that counts as drift (default 0.05 = 5%)
            window:    rolling window size in days (default 7)

        Returns:
            dict with drift_detected flag and supporting statistics.
        """
        means = self.rolling_mean(window=window)
        if len(means) < 2:
            return {"drift_detected": False, "reason": "insufficient history"}

        current_mean = means[-1]["rolling_mean"]
        previous_mean = means[-2]["rolling_mean"]
        drop = previous_mean - current_mean

        if drop > threshold:
            return {
                "drift_detected": True,
                "current_mean": current_mean,
                "previous_mean": previous_mean,
                "drop": round(drop, 4),
                "threshold": threshold,
                "window": window,
            }
        return {
            "drift_detected": False,
            "current_mean": current_mean,
            "previous_mean": previous_mean,
            "drop": round(drop, 4),
            "threshold": threshold,
        }

    def absolute_alert(self, floor: float = 0.70) -> dict:
        """Fire if the most recent score is below the absolute floor."""
        if not self.history:
            return {"alert": False, "reason": "no data"}
        latest = self.history[-1]
        below = latest["score"] < floor
        return {
            "alert": below,
            "date": latest["date"],
            "score": latest["score"],
            "floor": floor,
        }


# ---------------------------------------------------------------------------
# RegressionDetector
# ---------------------------------------------------------------------------

class RegressionDetector:
    """
    Compare current experiment metrics against a stored baseline.

    Usage:
        detector = RegressionDetector()
        detector.save_baseline("faq-v3", {"faithfulness": 0.91, "relevance": 0.87})
        detector.compare("faq-v3", {"faithfulness": 0.84, "relevance": 0.89})
        detector.report()
    """

    def __init__(self, baseline_dir: str = "baselines") -> None:
        self.baseline_dir = Path(baseline_dir)
        self.baseline_dir.mkdir(exist_ok=True)
        self._regressions: list[dict] = []

    def save_baseline(self, experiment_name: str, metrics: dict[str, float]) -> None:
        """Save current metrics as the reference baseline."""
        path = self.baseline_dir / f"{experiment_name}.json"
        path.write_text(
            json.dumps(
                {"experiment": experiment_name, "metrics": metrics}, indent=2
            )
        )
        print(f"Baseline saved: {path}")

    def compare(
        self,
        experiment_name: str,
        current_metrics: dict[str, float],
        threshold: float = 0.03,
    ) -> list[dict]:
        """
        Compare current_metrics to the saved baseline.
        Flags any metric where current < baseline - threshold.

        Args:
            experiment_name:  name matching a saved baseline file
            current_metrics:  dict of metric_name -> score
            threshold:        minimum drop that counts as regression

        Returns:
            List of comparison dicts, one per metric.
        """
        path = self.baseline_dir / f"{experiment_name}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"No baseline found for '{experiment_name}'. "
                "Run save_baseline() first."
            )

        baseline = json.loads(path.read_text())["metrics"]
        self._regressions = []

        for metric, baseline_value in baseline.items():
            current_value = current_metrics.get(metric)
            if current_value is None:
                continue

            delta = current_value - baseline_value
            self._regressions.append(
                {
                    "metric": metric,
                    "baseline": baseline_value,
                    "current": current_value,
                    "delta": round(delta, 4),
                    "threshold": threshold,
                    "regressed": delta < -threshold,
                }
            )

        return self._regressions

    def report(self) -> None:
        """Print a formatted regression/pass report."""
        if not self._regressions:
            print("No comparison run yet. Call compare() first.")
            return

        regressions = [r for r in self._regressions if r["regressed"]]
        clean = [r for r in self._regressions if not r["regressed"]]

        print("\n=== REGRESSION REPORT ===")
        if regressions:
            print(f"\nREGRESSIONS ({len(regressions)}):")
            for r in regressions:
                print(
                    f"  {r['metric']:30s}  "
                    f"baseline={r['baseline']:.3f}  "
                    f"current={r['current']:.3f}  "
                    f"delta={r['delta']:+.3f}"
                )
        else:
            print("\nNo regressions detected.")

        if clean:
            print(f"\nPASSING ({len(clean)}):")
            for r in clean:
                print(
                    f"  {r['metric']:30s}  "
                    f"baseline={r['baseline']:.3f}  "
                    f"current={r['current']:.3f}  "
                    f"delta={r['delta']:+.3f}"
                )


# ---------------------------------------------------------------------------
# Simulations
# ---------------------------------------------------------------------------

def simulate_drift_scenario() -> ScoreHistory:
    """
    30 days of scores with a drift event at day 20.
    Days 1-19: stable ~0.88 (provider model-v1)
    Days 20-30: degraded ~0.79 (provider silently updated model)
    """
    history_path = "simulated_history.json"
    Path(history_path).unlink(missing_ok=True)
    history = ScoreHistory(history_path)

    start = date(2025, 4, 1)
    random.seed(42)

    for i in range(30):
        current_date = (start + timedelta(days=i)).isoformat()
        if i < 19:
            score = round(random.gauss(0.88, 0.02), 3)
            version = "model-v1"
        else:
            # Provider silently updated model -- same version string, different behavior
            score = round(random.gauss(0.79, 0.025), 3)
            version = "model-v1"

        score = max(0.0, min(1.0, score))
        history.add(current_date, score, version)

    print("\n=== 30-DAY DRIFT SIMULATION ===")
    print(f"Total entries: {len(history.history)}")

    drift = history.detect_drift(threshold=0.05)
    print(f"\nDrift detection (threshold=0.05):")
    print(json.dumps(drift, indent=2))

    absolute = history.absolute_alert(floor=0.70)
    print(f"\nAbsolute floor alert (floor=0.70):")
    print(json.dumps(absolute, indent=2))

    means = history.rolling_mean(window=7)
    print("\nRolling means (last 10 days):")
    for m in means[-10:]:
        flag = " <-- drift visible" if m["rolling_mean"] < 0.83 else ""
        print(f"  {m['date']}: {m['rolling_mean']:.3f}{flag}")

    return history


def simulate_regression_scenario() -> None:
    """
    Regression detection: prompt-v3 (baseline) vs prompt-v4 (faithfulness regressed).
    """
    detector = RegressionDetector("baselines")

    # Baseline: prompt-v3 production results
    baseline_metrics = {
        "faithfulness": 0.91,
        "answer_relevance": 0.87,
        "format_compliance": 1.00,
        "avg_latency_ms": 850.0,
    }
    detector.save_baseline("faq-assistant", baseline_metrics)

    # Current: prompt-v4 (faithfulness dropped, relevance improved)
    current_metrics = {
        "faithfulness": 0.84,      # regressed: 0.91 - 0.84 = 0.07 > threshold 0.03
        "answer_relevance": 0.89,  # improved
        "format_compliance": 1.00, # unchanged
        "avg_latency_ms": 820.0,   # slightly faster
    }

    print("\n=== REGRESSION DETECTION: prompt-v3 vs prompt-v4 ===")
    detector.compare("faq-assistant", current_metrics, threshold=0.03)
    detector.report()


def test_sensitivity() -> None:
    """Verify detector fires within 3 days of a 10% quality drop."""
    path = "test_sensitivity.json"
    Path(path).unlink(missing_ok=True)
    history = ScoreHistory(path)

    random.seed(99)
    # 7 stable days
    for i in range(7):
        history.add(f"2025-01-{i+1:02d}", round(random.gauss(0.88, 0.01), 3))
    # 7 degraded days (10% drop)
    for i in range(7):
        history.add(f"2025-01-{i+8:02d}", round(random.gauss(0.79, 0.01), 3))

    result = history.detect_drift(threshold=0.05)
    status = "PASS" if result["drift_detected"] else "FAIL"
    print(f"\n[sensitivity] {status}: drift_detected={result['drift_detected']}, drop={result.get('drop', 'N/A')}")


def test_specificity() -> None:
    """Verify detector does NOT fire on normal noise (+-2%)."""
    path = "test_specificity.json"
    Path(path).unlink(missing_ok=True)
    history = ScoreHistory(path)

    random.seed(77)
    for i in range(14):
        history.add(f"2025-02-{i+1:02d}", round(random.gauss(0.88, 0.015), 3))

    result = history.detect_drift(threshold=0.05)
    status = "PASS" if not result["drift_detected"] else "FAIL"
    print(f"[specificity] {status}: drift_detected={result['drift_detected']}, drop={result.get('drop', 'N/A')}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    simulate_drift_scenario()
    print("\n" + "=" * 60)
    simulate_regression_scenario()
    print("\n" + "=" * 60 + "\n=== UNIT TESTS ===")
    test_sensitivity()
    test_specificity()
