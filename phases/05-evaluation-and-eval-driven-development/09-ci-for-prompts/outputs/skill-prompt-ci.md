---
name: skill-prompt-ci
description: CI setup guide for prompt regression testing with GitHub Actions, threshold config, and intentional-change approval flow
version: "1.0"
phase: "05"
lesson: "09"
tags: [ci, eval, prompts, github-actions, regression]
---

# Prompt CI Setup Guide

## GitHub Actions Workflow Template

```yaml
# .github/workflows/eval.yml
name: Prompt Eval CI

on:
  pull_request:
    paths:
      - 'prompts/**'
      - 'src/**'
      - 'golden_set_smoke.json'

jobs:
  eval:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install anthropic

      - name: Run eval
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python eval_runner.py \
            --experiment pr-${{ github.event.pull_request.number }} \
            --baseline main \
            --dataset golden_set_smoke.json \
            --threshold 0.03

      - name: Post failure comment
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## Eval CI Failed\n\nA metric regressed beyond threshold. Run \`python eval_runner.py\` locally to see details.\n\nTo override: add \`[eval-override: reason]\` to the PR description and get team lead approval. Update the golden set in a follow-up PR.`
            });
```

## eval_runner.py Template

```python
import argparse, json, sys, difflib, statistics
from datetime import datetime
from pathlib import Path
from anthropic import Anthropic

client = Anthropic()

def exact_match(case, actual):
    return 1.0 if actual.strip() == case.get("expected","").strip() else 0.0

def fuzzy_match(case, actual, t=0.7):
    r = difflib.SequenceMatcher(None, actual.lower(), case.get("expected","").lower()).ratio()
    return 1.0 if r >= t else 0.0

def format_compliance(case, actual):
    try:
        json.loads(actual.strip())
        return 1.0
    except:
        return 0.0

SCORERS = {"exact_match": exact_match, "fuzzy_match": fuzzy_match, "format_compliance": format_compliance}

def run_experiment(dataset_path, name, results_dir="eval_results"):
    dataset = json.loads(Path(dataset_path).read_text())
    results = []
    for i, case in enumerate(dataset):
        resp = client.messages.create(
            model="claude-3-5-haiku-20241022", max_tokens=256,
            system=case.get("system_prompt", "Answer concisely."),
            messages=[{"role": "user", "content": case["input"]}]
        )
        actual = resp.content[0].text
        results.append({"case_id": case.get("id", f"c{i}"), "actual": actual,
                        "scores": {n: s(case, actual) for n, s in SCORERS.items()}})
    exp = {"name": name, "timestamp": datetime.utcnow().isoformat(),
           "n": len(results), "results": results}
    Path(results_dir).mkdir(exist_ok=True)
    Path(f"{results_dir}/{name}.json").write_text(json.dumps(exp, indent=2))

def load_means(name, results_dir="eval_results"):
    exp = json.loads(Path(f"{results_dir}/{name}.json").read_text())
    scores = {}
    for r in exp["results"]:
        for m, s in r["scores"].items():
            scores.setdefault(m, []).append(s)
    return {m: statistics.mean(s) for m, s in scores.items()}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--experiment", required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--dataset", default="golden_set_smoke.json")
    p.add_argument("--threshold", type=float, default=0.03)
    p.add_argument("--results-dir", default="eval_results")
    args = p.parse_args()

    run_experiment(args.dataset, args.experiment, args.results_dir)
    baseline = load_means(args.baseline, args.results_dir)
    current = load_means(args.experiment, args.results_dir)

    thresholds = {
        "exact_match": args.threshold,
        "fuzzy_match": args.threshold,
        "format_compliance": 0.0,
    }

    failures = [
        {"metric": m, "baseline": baseline.get(m, 0), "current": current.get(m, 0),
         "delta": current.get(m, 0) - baseline.get(m, 0), "threshold": t}
        for m, t in thresholds.items()
        if (current.get(m, 0) - baseline.get(m, 0)) < -t
    ]

    for m in sorted(set(list(baseline) + list(current))):
        b, c = baseline.get(m, 0), current.get(m, 0)
        flag = " [REGRESSION]" if any(f["metric"] == m for f in failures) else ""
        print(f"  {m:<25} baseline={b:.3f}  current={c:.3f}  delta={c-b:+.3f}{flag}")

    if failures:
        print(f"\nFAILED: {len(failures)} regression(s)")
        sys.exit(1)
    else:
        print("\nPASSED")
        sys.exit(0)

if __name__ == "__main__":
    main()
```

## Threshold-Setting Guidance

| Metric type | Recommended threshold | Reasoning |
|-------------|----------------------|-----------|
| Format compliance (JSON, SQL) | 0.0 (hard) | Any format regression is a breaking change |
| Safety / refusal rules | 0.0 (hard) | Safety must never regress |
| Exact match | 0.03 (3%) | Allow for minor LLM variance |
| Fuzzy / semantic match | 0.05 (5%) | Higher variance, allow more room |
| LLM judge quality score | 0.05 (5%) | Judge itself has ~3% variance |
| Coverage / recall | 0.03 (3%) | |

Calibration process:
1. Run your baseline 3 times with identical code. Record the score variance per metric.
2. Set your threshold at 2x the observed variance. This separates noise from signal.
3. Inject a known bad change. Verify CI fails. If it does not, tighten the threshold.

## Intentional Regression Approval Process

When a PR intentionally changes system behavior (new format, new tone, expanded scope):

1. **PR author:** add `[eval-override: changing X because Y]` to the PR description
2. **CI workflow:** detect the flag and skip the threshold check (or post a warning instead of failing)
3. **Team lead:** review the override justification and approve
4. **Follow-up PR:** update the golden set to reflect the new expected behavior
5. **Re-run baseline:** tag the new experiment as the baseline for future comparisons

Workflow check for override flag:

```yaml
- name: Check for eval override
  id: check_override
  run: |
    PR_BODY="${{ github.event.pull_request.body }}"
    if echo "$PR_BODY" | grep -q "\[eval-override:"; then
      echo "override=true" >> $GITHUB_OUTPUT
    else
      echo "override=false" >> $GITHUB_OUTPUT
    fi

- name: Run eval
  if: steps.check_override.outputs.override != 'true'
  run: python eval_runner.py --experiment pr-${{ github.event.pull_request.number }} --baseline main
```

## Fast Smoke Set vs Full Golden Set

| Trigger | Dataset | Time target | Coverage |
|---------|---------|-------------|----------|
| Every PR | `golden_set_smoke.json` (20-30 cases) | Under 5 min | High-priority capabilities |
| Merge to main | `golden_set_full.json` (100-500 cases) | Under 60 min | Full coverage |
| Pre-release | `golden_set_full.json` + adversarial set | Unlimited | Full + edge cases |

Smoke set selection: include cases that have historically caught regressions, one representative case per major capability, and the hardest cases in each category. Do not include redundant "easy" cases in the smoke set.

## Prompt Versioning Convention

Tag every prompt with a semantic version. Record the version in every experiment run.

```python
SYSTEM_PROMPT_VERSION = "1.3.0"  # bump when prompt changes

experiment = {
    "name": experiment_name,
    "prompt_version": SYSTEM_PROMPT_VERSION,
    ...
}
```

Use the version to answer: "which prompt version produced this eval result?"
