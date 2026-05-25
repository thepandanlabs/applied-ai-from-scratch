---
name: skill-evaluator-optimizer
description: Automated generate-evaluate-optimize loop that iterates a draft against a structured rubric until it passes or hits max iterations
version: "1.0"
phase: "04"
lesson: "07"
tags: [evaluator, optimizer, loop, revision, quality-control]
---

# Skill: Evaluator-Optimizer

Use when: you can write a rubric for what "good" looks like, and the first draft is not reliably good enough to ship.

---

## Prompt templates

### Generator prompt

```
Task: [describe what to produce]

Requirements:
[list your requirements here, one per line]

Write the output now.
```

### Evaluator system prompt (customize the rubric section for your domain)

```
You are a quality evaluator for [your domain]. Evaluate the draft
against the requirements and return a JSON object with exactly this structure:

{
  "score": <integer 0-10>,
  "issues": [
    "<specific problem that must be fixed>",
    "<another specific problem>"
  ],
  "strengths": [
    "<what is already good>"
  ],
  "pass": <true if score >= 7 and no blocking issues, false otherwise>
}

Rubric:
- 9-10: [define excellent]
- 7-8: [define good - this is the pass threshold]
- 5-6: [define acceptable but needs revision]
- 3-4: [define below bar]
- 1-2: [define unusable]

Issues list: be specific. "[vague feedback]" is not useful.
"[specific problem with location and suggested direction]" is useful.

Return only valid JSON. No markdown, no code blocks.
```

### Optimizer prompt

```
Task: [original task]

Requirements:
[original requirements]

Current draft:
[draft text]

Issues to fix (address ALL of these):
- [issue 1]
- [issue 2]

Strengths to preserve:
- [strength 1]

Rewrite the draft. Fix every issue. Preserve the strengths.
```

---

## Loop skeleton

```python
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
import anthropic


@dataclass
class EvalResult:
    score: int
    issues: list
    strengths: list
    passed: bool


class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate(self, draft: str, task: str, requirements: str) -> EvalResult:
        ...


class LLMEvaluator(BaseEvaluator):
    def __init__(self, evaluator_system: str):
        self.client = anthropic.Anthropic()
        self.evaluator_system = evaluator_system

    def evaluate(self, draft: str, task: str, requirements: str) -> EvalResult:
        message = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system=self.evaluator_system,
            messages=[{
                "role": "user",
                "content": (
                    f"Original task: {task}\n\n"
                    f"Requirements:\n{requirements}\n\n"
                    f"Draft to evaluate:\n{draft}"
                )
            }]
        )
        data = json.loads(message.content[0].text)
        return EvalResult(
            score=data["score"],
            issues=data.get("issues", []),
            strengths=data.get("strengths", []),
            passed=data["pass"]
        )


class EvalOptimizeLoop:
    def __init__(self, evaluator: BaseEvaluator, max_iterations: int = 3):
        self.evaluator = evaluator
        self.max_iterations = max_iterations
        self.client = anthropic.Anthropic()

    def _generate(self, task: str, requirements: str) -> str:
        message = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": f"Task: {task}\n\nRequirements:\n{requirements}\n\nWrite the output now."
            }]
        )
        return message.content[0].text

    def _optimize(self, draft: str, task: str, requirements: str, eval_result: EvalResult) -> str:
        issues_text = "\n".join(f"- {i}" for i in eval_result.issues)
        strengths_text = "\n".join(f"- {s}" for s in eval_result.strengths)
        message = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": (
                    f"Task: {task}\n\nRequirements:\n{requirements}\n\n"
                    f"Current draft:\n{draft}\n\n"
                    f"Issues to fix (address ALL):\n{issues_text}\n\n"
                    f"Strengths to preserve:\n{strengths_text}\n\n"
                    "Rewrite the draft. Fix every issue. Preserve the strengths."
                )
            }]
        )
        return message.content[0].text

    def run(self, task: str, requirements: str) -> dict:
        history = []
        current_draft = self._generate(task, requirements)
        last_eval = None

        for i in range(self.max_iterations):
            eval_result = self.evaluator.evaluate(current_draft, task, requirements)
            last_eval = eval_result
            history.append({
                "iteration": i,
                "draft": current_draft,
                "score": eval_result.score,
                "issues": eval_result.issues,
                "passed": eval_result.passed,
            })
            if eval_result.passed:
                break
            if i < self.max_iterations - 1:
                current_draft = self._optimize(current_draft, task, requirements, eval_result)

        return {
            "final_draft": current_draft,
            "final_score": last_eval.score if last_eval else 0,
            "passed": last_eval.passed if last_eval else False,
            "iterations_used": len(history),
            "history": history,
        }
```

---

## Human-in-the-loop evaluator (drop-in replacement)

```python
class HumanEvaluator(BaseEvaluator):
    def evaluate(self, draft: str, task: str, requirements: str) -> EvalResult:
        print(f"\nDraft:\n{draft}\n")
        score = int(input("Score (0-10): ").strip())
        issues_str = input("Issues (comma-separated, ENTER for none): ").strip()
        issues = [i.strip() for i in issues_str.split(",") if i.strip()] if issues_str else []
        return EvalResult(score=score, issues=issues, strengths=[], passed=score >= 7 and not issues)

# Swap in:
loop = EvalOptimizeLoop(evaluator=HumanEvaluator(), max_iterations=3)
```

---

## Rubric writing guide

| Weak rubric | Strong rubric |
|-------------|---------------|
| "Is clear and well-written" | "Lead sentence states the primary benefit, not a feature" |
| "Has good tone" | "Uses second-person ('you') at least once; avoids 'revolutionary'" |
| "Is complete" | "Contains: benefit statement, one specific differentiator, CTA" |

Specific, checkable criteria produce consistent evaluations. Vague criteria produce inconsistent scores.

---

## When to use max_iterations = 1, 2, or 3

```
max_iterations = 1:  Evaluation only (no optimization). Use to measure baseline quality.
max_iterations = 2:  One revision pass. Fast; catches obvious issues.
max_iterations = 3:  Standard. Handles multi-issue content. Default recommendation.
max_iterations = 4+: Diminishing returns. Use only if score trends still show improvement.
```

---

## Common pitfalls

- **Score inflation**: Evaluator scores most outputs 7-8 and rarely gives issues. Fix: add examples of 7 vs. 5 to the rubric. A rubric without calibration examples drifts toward leniency.
- **Issue repetition**: The same issue appears in every iteration. The optimizer is not addressing it. Fix: add "You MUST address every issue in the list" and verify each issue is present in the optimizer input.
- **Evaluator inconsistency**: The same draft gets 6/10 on one run and 8/10 on another. Fix: set evaluator temperature to 0 for consistency.
- **Loop escape failure**: 80%+ of inputs hit max_iterations without passing. The rubric threshold is too strict OR the generator prompt is misaligned with the requirements. Check both.
