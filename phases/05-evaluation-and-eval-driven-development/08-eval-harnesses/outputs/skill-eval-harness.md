---
name: skill-eval-harness
description: reusable eval harness template with scorer interface, results storage, comparison report, and platform decision matrix
version: "1.0"
phase: "05"
lesson: "08"
tags: [eval, harness, braintrust, langsmith, phoenix, tooling]
---

# Eval Harness Reference

## The Harness Class (copy-paste ready)

```python
import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Callable

class EvalHarness:
    def __init__(self, dataset, system_fn, scorers, results_dir="eval_results"):
        self.dataset = dataset
        self.system_fn = system_fn
        self.scorers = scorers
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def run(self, experiment_name: str) -> dict:
        results = []
        for i, case in enumerate(self.dataset):
            actual = self.system_fn(case)
            scores = {name: scorer(case, actual) for name, scorer in self.scorers.items()}
            results.append({
                "case_id": case.get("id", f"c{i}"),
                "input": case["input"],
                "expected": case.get("expected", ""),
                "actual": actual,
                "scores": scores
            })
        experiment = {
            "name": experiment_name,
            "timestamp": datetime.utcnow().isoformat(),
            "n": len(results),
            "results": results
        }
        path = self.results_dir / f"{experiment_name}.json"
        path.write_text(json.dumps(experiment, indent=2))
        return experiment

    def compare(self, experiment_a: str, experiment_b: str) -> dict:
        def summarize(name):
            exp = json.loads((self.results_dir / f"{name}.json").read_text())
            all_scores = {}
            for r in exp["results"]:
                for metric, score in r["scores"].items():
                    all_scores.setdefault(metric, []).append(score)
            return {m: statistics.mean(s) for m, s in all_scores.items()}

        a, b = summarize(experiment_a), summarize(experiment_b)
        return {
            "experiment_a": experiment_a,
            "experiment_b": experiment_b,
            "metrics": {
                metric: {
                    "a_mean": round(a.get(metric, 0), 4),
                    "b_mean": round(b.get(metric, 0), 4),
                    "delta": round(b.get(metric, 0) - a.get(metric, 0), 4),
                    "regression": (b.get(metric, 0) - a.get(metric, 0)) < -0.03
                }
                for metric in set(a) | set(b)
            }
        }

    def report(self, experiment_name: str) -> None:
        exp = json.loads((self.results_dir / f"{experiment_name}.json").read_text())
        all_scores = {}
        for r in exp["results"]:
            for metric, score in r["scores"].items():
                all_scores.setdefault(metric, []).append(score)
        print(f"\nExperiment: {experiment_name} ({exp['n']} cases)")
        print(f"  {'Metric':<25} {'Mean':>8} {'Pass Rate':>12}")
        print("  " + "-" * 45)
        for metric, scores in all_scores.items():
            mean = statistics.mean(scores)
            pr = sum(1 for s in scores if s >= 1.0) / len(scores)
            print(f"  {metric:<25} {mean:>8.3f} {pr:>11.0%}")
```

## Scorer Interface

Every scorer must match this signature:

```python
def my_scorer(case: dict, actual: str) -> float:
    """
    Args:
        case:   one item from the golden set (has "input", "expected", and any custom fields)
        actual: the system's output for this case

    Returns:
        float in [0.0, 1.0]
        1.0 = pass, 0.0 = fail, values in between for partial credit
    """
    ...
```

### Built-in Scorers

```python
import difflib, json

def exact_match(case, actual):
    return 1.0 if actual.strip() == case.get("expected", "").strip() else 0.0

def fuzzy_match(case, actual, threshold=0.7):
    ratio = difflib.SequenceMatcher(None, actual.lower(), case.get("expected","").lower()).ratio()
    return 1.0 if ratio >= threshold else 0.0

def format_compliance(case, actual):
    try:
        text = actual.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        json.loads(text)
        return 1.0
    except:
        return 0.0
```

## Results Storage Format

Every experiment file stored at `eval_results/<experiment-name>.json`:

```json
{
  "name": "experiment-name",
  "timestamp": "2024-01-15T14:32:00",
  "n": 10,
  "results": [
    {
      "case_id": "q01",
      "input": "question text",
      "expected": "expected answer",
      "actual": "system output",
      "scores": {
        "exact_match": 1.0,
        "fuzzy_match": 1.0,
        "format_compliance": 0.0
      }
    }
  ]
}
```

Rules:
- Never overwrite an existing experiment file. Append a timestamp suffix if you need to re-run.
- Experiment names should encode what changed: `baseline`, `pr-42-new-prompt`, `v2-temp-0.7`.
- Once tagged as "baseline," a file is immutable.

## Comparison Report Format

```
Comparison: baseline vs new-prompt
  Metric                   A Mean   B Mean    Delta  Regression?
  -----------------------------------------------------------------
  exact_match               0.800    0.900   +0.100           no
  fuzzy_match               0.850    0.900   +0.050           no
  format_compliance         1.000    0.800   -0.200          YES
```

Regression threshold: a delta below -0.03 (3% drop) is flagged. Adjust per metric:
- `format_compliance`: any drop below 0.0 is a regression (binary)
- `exact_match`: 3% threshold
- LLM judge scores: 5% threshold (higher variance)

## Platform Decision Matrix

| Criterion | Build Your Own | Braintrust | LangSmith | Arize Phoenix |
|-----------|---------------|------------|-----------|---------------|
| Data leaves your infra | No | Yes | Yes | No (self-hosted) |
| Cost | Eng time | Paid | Paid | Free (OSS) |
| Comparison UI | DIY | Excellent | Good | Good |
| Tracing built-in | No | No | Yes | Yes |
| LangChain integration | Manual | Manual | Native | Good |
| OTel native | Manual | Partial | Partial | Yes |
| Setup time | Hours | Minutes | Minutes | 30 min |

**Choose Braintrust if:** your team runs evals frequently and needs a shared comparison UI; you do not have strict data residency requirements.

**Choose LangSmith if:** you already use LangChain or LangGraph and want tracing and evals in one tool.

**Choose Arize Phoenix if:** data must stay in your infrastructure; you want OpenTelemetry `gen_ai.*` spans for free; you want open-source with no vendor dependency.

**Build your own if:** you need full control over the harness logic; you are integrating eval into an existing CI system; or you are in a regulated environment where even self-hosted SaaS is not permitted.

## Smoke Set Pattern

For fast CI feedback, maintain two datasets:

```
golden_set_full.json   (100-500 cases)  Used for: merge to main, release gates
golden_set_smoke.json  (20-30 cases)    Used for: every PR, fast feedback (<5 min)
```

Smoke set selection criteria: cases that historically caught regressions, one case per major capability, edge cases that are easy to accidentally break.

```python
# Run smoke set on PR, full set on merge
dataset = SMOKE_SET if os.getenv("CI_EVENT") == "pull_request" else FULL_SET
harness = EvalHarness(dataset=dataset, ...)
```
