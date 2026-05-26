# code/main.py
# Dependencies: none (stdlib only)
# Usage: python main.py

from __future__ import annotations
import json
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LadderQuestion:
    """A single question in the decision ladder."""
    id: str
    text: str
    yes_rung: Optional[str]  # rung to recommend if yes
    yes_label: str           # human label for the yes outcome
    no_continue: bool        # if True, continue to next question on no


LADDER_QUESTIONS: list[LadderQuestion] = [
    LadderQuestion(
        id="q1",
        text=(
            "Does the current system prompt clearly specify the persona, tone, "
            "format, and constraints? Have you tested at least 10 different phrasings "
            "of the instruction?"
        ),
        yes_rung=None,
        yes_label="Prompt engineering is not yet exhausted. Improve the system prompt first.",
        no_continue=True,
    ),
    LadderQuestion(
        id="q2",
        text=(
            "Have you tried adding 5-20 few-shot examples directly in the prompt "
            "that demonstrate the desired input/output pattern?"
        ),
        yes_rung=None,
        yes_label="Few-shot prompting is not yet exhausted. Add examples to the prompt first.",
        no_continue=True,
    ),
    LadderQuestion(
        id="q3",
        text=(
            "Is the problem primarily a KNOWLEDGE gap (missing facts, stale info, "
            "private documents the model was not trained on)? "
            "If yes, RAG is the right tool."
        ),
        yes_rung="RAG",
        yes_label=(
            "Use RAG. Index your knowledge base and retrieve relevant context at query time. "
            "Fine-tuning will not help here because it does not add new knowledge."
        ),
        no_continue=True,
    ),
    LadderQuestion(
        id="q4",
        text=(
            "Is the problem a BEHAVIOR gap: consistent output format, specialized vocabulary, "
            "brand tone, or latency/cost requirements that demand a smaller model? "
            "AND do you have at least 100 high-quality input/output examples?"
        ),
        yes_rung="FINE-TUNE",
        yes_label=(
            "Fine-tuning is justified. Build a curated dataset (see Lesson 02), "
            "start with the managed API (Lesson 03), and evaluate against your baseline (Lesson 05)."
        ),
        no_continue=True,
    ),
    LadderQuestion(
        id="q5",
        text=(
            "Are you building something with no available pretrained foundation - "
            "a completely novel domain with no overlap with any existing model? "
            "(This is extremely rare in practice.)"
        ),
        yes_rung="TRAIN-FROM-SCRATCH",
        yes_label=(
            "Training from scratch may be warranted, but verify that no existing model "
            "covers your domain first. This requires millions of examples, significant compute, "
            "and an ML research team."
        ),
        no_continue=False,
    ),
]


@dataclass
class EvaluationResult:
    """The result of running the decision ladder."""
    recommendation: str
    rung: int
    reasoning: str
    answers: list[dict] = field(default_factory=list)


RUNG_LABELS = {
    "PROMPT": 1,
    "FEW-SHOT": 2,
    "RAG": 3,
    "FINE-TUNE": 4,
    "TRAIN-FROM-SCRATCH": 5,
}


def ask_question(question: LadderQuestion) -> bool:
    """Ask a single ladder question and return True for yes, False for no."""
    print(f"\n{'='*60}")
    print(f"Question: {question.text}")
    print(f"{'='*60}")
    while True:
        answer = input("Answer [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")


def run_ladder(problem: str) -> EvaluationResult:
    """Walk through the decision ladder and return a recommendation."""
    print(f"\nProblem: {problem}")
    print("\nWorking through the decision ladder from cheapest to most expensive...\n")

    answers = []

    for i, question in enumerate(LADDER_QUESTIONS):
        answered_yes = ask_question(question)
        answers.append({"question_id": question.id, "answer": "yes" if answered_yes else "no"})

        if answered_yes and question.yes_rung:
            # Positive branch: this rung is the recommendation
            rung_num = RUNG_LABELS.get(question.yes_rung, 4)
            return EvaluationResult(
                recommendation=question.yes_rung,
                rung=rung_num,
                reasoning=question.yes_label,
                answers=answers,
            )

        if answered_yes and not question.yes_rung:
            # Not yet exhausted this level - stay here
            return EvaluationResult(
                recommendation="PROMPT" if i == 0 else "FEW-SHOT",
                rung=i + 1,
                reasoning=question.yes_label,
                answers=answers,
            )

        # answered no: continue to next question

    # If we get through all questions with all no answers, default to prompting review
    return EvaluationResult(
        recommendation="REVISIT",
        rung=0,
        reasoning=(
            "Could not determine the right rung. Re-examine whether the problem is clearly "
            "defined. A fuzzy problem statement leads to the wrong tool choice."
        ),
        answers=answers,
    )


def print_result(result: EvaluationResult) -> None:
    """Print the evaluation result in a readable format."""
    print(f"\n{'='*60}")
    print("DECISION LADDER RESULT")
    print(f"{'='*60}")
    print(f"Recommendation: {result.recommendation} (Rung {result.rung})")
    print(f"\nReasoning:\n{result.reasoning}")
    print(f"\nYour answers: {json.dumps(result.answers, indent=2)}")


THREE_SCENARIOS = [
    {
        "name": "Customer tone matching",
        "description": (
            "The support chatbot answers correctly but sounds generic and corporate. "
            "The brand voice should be warm, direct, and human. "
            "We have 200 examples of 'bad' vs 'good' tone responses."
        ),
    },
    {
        "name": "Medical terminology extraction",
        "description": (
            "We need to extract ICD-10 codes from clinical notes. "
            "The base model gets common codes right but misses rare codes "
            "and uses wrong terminology for subspecialty conditions."
        ),
    },
    {
        "name": "FAQ answering",
        "description": (
            "Customers ask questions answered in our 500-page product manual. "
            "The base model makes up answers when it does not know. "
            "We have the manual but have not indexed it anywhere."
        ),
    },
]


def run_demo_scenarios() -> None:
    """Demonstrate the ladder on three canned scenarios without interactive input."""
    print("\nDEMO MODE: Running three scenarios with predetermined answers\n")

    scenario_answers = [
        # Customer tone matching: prompting exhausted, few-shot exhausted, not a knowledge gap, behavior gap with examples
        [False, False, False, True],
        # Medical terminology: prompting exhausted, few-shot exhausted, knowledge + behavior gap - RAG first
        [False, False, True, None],
        # FAQ answering: prompting not exhausted yet (no RAG in place)
        [False, False, True, None],
    ]

    for i, (scenario, answers) in enumerate(zip(THREE_SCENARIOS, scenario_answers)):
        print(f"\n{'#'*60}")
        print(f"Scenario {i+1}: {scenario['name']}")
        print(f"Problem: {scenario['description']}")
        print(f"{'#'*60}")

        # Simulate the ladder with predetermined answers
        result_answers = []
        recommendation = "REVISIT"
        rung = 0
        reasoning = ""

        for j, (question, answer) in enumerate(zip(LADDER_QUESTIONS, answers)):
            if answer is None:
                break
            result_answers.append({"question_id": question.id, "answer": "yes" if answer else "no"})

            if answer and question.yes_rung:
                recommendation = question.yes_rung
                rung = RUNG_LABELS.get(question.yes_rung, 4)
                reasoning = question.yes_label
                break
            if answer and not question.yes_rung:
                recommendation = "PROMPT" if j == 0 else "FEW-SHOT"
                rung = j + 1
                reasoning = question.yes_label
                break

        result = EvaluationResult(
            recommendation=recommendation,
            rung=rung,
            reasoning=reasoning,
            answers=result_answers,
        )
        print_result(result)


if __name__ == "__main__":
    if "--demo" in sys.argv:
        run_demo_scenarios()
    else:
        print("Decision Ladder: Prompt, RAG, or Fine-Tune?")
        print("--------------------------------------------")
        problem = input("Describe your problem in one sentence: ").strip()
        if not problem:
            problem = "Unspecified problem"
        result = run_ladder(problem)
        print_result(result)
