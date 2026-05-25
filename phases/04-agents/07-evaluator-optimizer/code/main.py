"""
Lesson 04-07: Pattern: Evaluator-Optimizer
Generate a draft, evaluate against a rubric, optimize using feedback, loop until pass.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

import anthropic

# ---------------------------------------------------------------------------
# EVALUATOR SYSTEM PROMPT
# ---------------------------------------------------------------------------

EVALUATOR_SYSTEM = """You are a quality evaluator for product copy. Evaluate the draft
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
- 9-10: Excellent. Clear benefit statement, specific details, compelling CTA.
- 7-8: Good. Passes. Minor improvements possible but not required.
- 5-6: Acceptable draft. Needs at least one specific revision before shipping.
- 3-4: Below bar. Multiple issues that reduce customer confidence or clarity.
- 1-2: Not usable. Missing critical elements or actively misleading.

Issues list: be specific. "Too vague" is not useful. "Benefit statement uses generic
phrase 'high quality' instead of a specific differentiator" is useful.

Return only valid JSON. No markdown, no code blocks."""


# ---------------------------------------------------------------------------
# RAW IMPLEMENTATION
# ---------------------------------------------------------------------------

def generate_draft(task: str, requirements: str) -> str:
    """Initial draft generation."""
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Task: {task}\n\n"
                    f"Requirements:\n{requirements}\n\n"
                    "Write the output now."
                )
            }
        ]
    )
    return message.content[0].text


def evaluate_draft(draft: str, task: str, requirements: str) -> dict:
    """Evaluate the draft against the rubric. Returns structured JSON."""
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system=EVALUATOR_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Original task: {task}\n\n"
                    f"Requirements:\n{requirements}\n\n"
                    f"Draft to evaluate:\n{draft}"
                )
            }
        ]
    )
    return json.loads(message.content[0].text)


def optimize_draft(draft: str, task: str, requirements: str, eval_result: dict) -> str:
    """Revise the draft based on evaluator feedback."""
    client = anthropic.Anthropic()

    issues_text = "\n".join(f"- {issue}" for issue in eval_result["issues"])
    strengths_text = "\n".join(f"- {s}" for s in eval_result.get("strengths", []))

    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Task: {task}\n\n"
                    f"Requirements:\n{requirements}\n\n"
                    f"Current draft:\n{draft}\n\n"
                    f"Issues to fix (address ALL of these):\n{issues_text}\n\n"
                    f"Strengths to preserve:\n{strengths_text}\n\n"
                    "Rewrite the draft. Fix every issue. Preserve the strengths."
                )
            }
        ]
    )
    return message.content[0].text


def eval_optimize_loop(task: str, requirements: str, max_iterations: int = 3) -> dict:
    """
    Run the evaluator-optimizer loop until pass or max_iterations.
    Returns the final draft and the full iteration history.
    """
    history = []
    eval_result = {}

    current_draft = generate_draft(task, requirements)
    print(f"\nInitial draft generated ({len(current_draft)} chars)")

    for iteration in range(max_iterations):
        print(f"\nIteration {iteration + 1}/{max_iterations}: Evaluating...")

        eval_result = evaluate_draft(current_draft, task, requirements)

        print(f"  Score: {eval_result['score']}/10  Pass: {eval_result['pass']}")
        if eval_result.get("issues"):
            for issue in eval_result["issues"]:
                print(f"  Issue: {issue}")

        history.append({
            "iteration": iteration,
            "draft": current_draft,
            "eval": eval_result,
        })

        if eval_result["pass"]:
            print(f"  Passed on iteration {iteration + 1}.")
            break

        if iteration < max_iterations - 1:
            print(f"  Optimizing...")
            current_draft = optimize_draft(current_draft, task, requirements, eval_result)
        else:
            print(f"  Max iterations reached. Returning best draft.")

    return {
        "final_draft": current_draft,
        "final_score": eval_result.get("score", 0),
        "passed": eval_result.get("pass", False),
        "iterations_used": len(history),
        "history": history,
    }


# ---------------------------------------------------------------------------
# REFACTORED: Swappable evaluator + EvalOptimizeLoop class
# ---------------------------------------------------------------------------

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
    """LLM-based evaluator using EVALUATOR_SYSTEM prompt."""

    def __init__(self):
        self.client = anthropic.Anthropic()

    def evaluate(self, draft: str, task: str, requirements: str) -> EvalResult:
        message = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system=EVALUATOR_SYSTEM,
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


class HumanEvaluator(BaseEvaluator):
    """
    Human-in-the-loop evaluator. Collects feedback via stdin.
    Use for high-stakes content where LLM judgment alone is not sufficient.
    """

    def evaluate(self, draft: str, task: str, requirements: str) -> EvalResult:
        print("\n" + "=" * 50)
        print("HUMAN REVIEW REQUIRED")
        print("=" * 50)
        print(f"\nTask: {task}\n")
        print(f"Draft:\n{draft}\n")
        print("-" * 50)

        score_str = input("Score (0-10): ").strip()
        score = int(score_str)

        issues_str = input("Issues (comma-separated, or ENTER for none): ").strip()
        issues = [i.strip() for i in issues_str.split(",") if i.strip()] if issues_str else []

        passed = score >= 7 and not issues
        print(f"Pass decision: {passed}")

        return EvalResult(score=score, issues=issues, strengths=[], passed=passed)


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
        """Run the loop. Returns final draft, score, pass status, and history."""
        history = []
        current_draft = self._generate(task, requirements)
        last_eval = None

        for i in range(self.max_iterations):
            eval_result = self.evaluator.evaluate(current_draft, task, requirements)
            last_eval = eval_result

            print(f"  Iteration {i+1}: score={eval_result.score}/10 pass={eval_result.passed}")

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


# ---------------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------------

TASK = "Write a product description for the ThermoBreeze Pro portable air purifier"

REQUIREMENTS = """- Lead with the primary benefit (cleaner air), not the feature list
- Include one specific technical differentiator (HEPA H13 filter, covers 500 sq ft)
- Include a call to action
- Maximum 100 words
- Tone: confident, benefit-first, no jargon
- Do not use the word 'revolutionary' or 'cutting-edge'"""


if __name__ == "__main__":
    print("=" * 60)
    print("DEMO 1: Raw eval-optimize loop")
    print("=" * 60)

    result = eval_optimize_loop(TASK, REQUIREMENTS, max_iterations=3)

    print("\n--- Final Result ---")
    print(f"Score: {result['final_score']}/10")
    print(f"Passed: {result['passed']}")
    print(f"Iterations used: {result['iterations_used']}")
    print(f"\nFinal draft:\n{result['final_draft']}")

    print("\n" + "=" * 60)
    print("DEMO 2: EvalOptimizeLoop class with LLMEvaluator")
    print("=" * 60)

    loop = EvalOptimizeLoop(evaluator=LLMEvaluator(), max_iterations=3)
    result2 = loop.run(TASK, REQUIREMENTS)

    print(f"\nFinal score: {result2['final_score']}/10  Passed: {result2['passed']}")
    print(f"Iterations: {result2['iterations_used']}")
    print(f"\nFinal draft:\n{result2['final_draft']}")

    # Uncomment to test human-in-the-loop evaluator:
    # print("\n" + "=" * 60)
    # print("DEMO 3: Human-in-the-loop evaluator")
    # print("=" * 60)
    # loop_human = EvalOptimizeLoop(evaluator=HumanEvaluator(), max_iterations=3)
    # result3 = loop_human.run(TASK, REQUIREMENTS)
    # print(f"\nFinal draft:\n{result3['final_draft']}")
