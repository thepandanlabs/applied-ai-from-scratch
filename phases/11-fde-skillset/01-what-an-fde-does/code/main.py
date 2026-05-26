# What an FDE Actually Does

> Your deliverable is not code. It is a customer outcome.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Completion of at least one prior phase
**Time:** ~45 min
**Phase:** 11 - FDE Skillset

## Learning Objectives

- Describe the 5-phase FDE engagement lifecycle and what happens in each phase
- Distinguish an FDE role from a backend engineer role in terms of success metrics
- Identify the pilot-to-production gap and articulate why it kills AI projects
- Build a self-assessment CLI that scores FDE competencies across an active engagement
- Recognize the tradeoffs FDEs make between code quality and demo velocity

---

## The Problem

You've been building AI systems for months. Your code is clean, your evals look solid, and you know how to wire up a RAG pipeline in under an hour. Now you're told you're joining a Forward-Deployed Engineering team, or your company is putting you in front of customers to scope and build AI pilots.

The job description sounds familiar. In practice, it is a different role.

A backend engineer ships code that other engineers depend on. An FDE ships outcomes that customers are willing to pay for. The measurement changes everything. You can write the most elegant LLM orchestration pipeline on the planet and lose the customer because you demo'd on synthetic data, the integration point wasn't confirmed before the build, or you spent three weeks on infrastructure before proving the core use case worked on their data.

The pilot-to-production gap is the gap between "this looks great in a controlled demo" and "this is running in our system handling real volume." Most AI pilots die in that gap, not because the AI was bad, but because the FDE didn't have the skills to bridge it. Those skills are learnable. This lesson maps them.

---

## The Concept

### The 5-Phase FDE Engagement Lifecycle

Every customer engagement follows the same shape, regardless of the AI use case. Durations shift, but the phases don't.

```
Phase        Duration     Key Activities                 Deliverable
-----------  -----------  ----------------------------   -----------------
DISCOVER     1-2 days     Customer calls, process        Discovery notes,
                          observation, stakeholder        problem hypothesis
                          mapping

SCOPE        1-3 days     Requirements extraction,       Written AI spec:
                          success metric definition,     problem + metric +
                          data audit, integration        I/O contract
                          point confirmation

BUILD        1-3 weeks    Rapid prototype, eval          Working demo on
                          harness, iteration on          customer data with
                          customer feedback              eval score

VALIDATE     2-5 days     Demo on real customer data,    Validation report,
                          edge case testing, latency     go/no-go decision
                          measurement, stakeholder
                          sign-off

HAND OFF     1-2 weeks    Documentation, runbook,        Deployed system or
                          handoff to product/eng,        handoff package
                          success metric baseline
```

The pilot-to-production gap lives between VALIDATE and HAND OFF. An FDE who skips validation (goes straight from build to handoff) hands off a system that the receiving team cannot operate, cannot debug, and cannot improve. The customer churns.

### FDE vs. Backend Engineer

The mental model shift:

```
                BACKEND ENGINEER        FDE
                ----------------        ---
Measured by:    Code merged             Customer outcome
Facing:         Internal team           Customer stakeholders
Cadence:        Sprint velocity         Engagement milestones
Output:         Working software        Working software + alignment
Risk if wrong:  Bug ticket              Lost deal / churned pilot
Planning unit:  Story point             Discovery call
```

FDEs write production-quality code. But code quality is table stakes, not the job. The job is diagnosing the right problem to solve, scoping a build that can succeed in 2-3 weeks, validating on real data before the demo, and handing off something the customer's team can own.

### The Pilot Killer: Optimizing the Wrong Thing

The most common FDE failure: spending week one on clean architecture when week one should prove the core hypothesis on customer data. The correct tradeoff is:

- Week 1: Prove it works on their data (quick, dirty, disposable prototype)
- Week 2: Build it properly (production patterns, eval harness)
- Week 3: Validate, document, and hand off

Engineers trained on code quality instincts reverse this order. They build the clean architecture first, then try to demo it on customer data in week three. By then, there is no time to fix the three edge cases that show up.

---

## Build It

The self-assessment tool asks 10 questions about your current engagement and scores you across 5 FDE competencies: Scoping, Technical Depth, Demo Quality, Communication, and Handoff Readiness.

```python
#!/usr/bin/env python3
"""
FDE Self-Assessment CLI

Asks 10 questions about your current engagement and scores you
across 5 FDE competencies. Run this before a customer milestone
to identify where you are under-prepared.

Usage:
    python main.py
    python main.py --export results.json
"""
import json
import sys
import argparse
from dataclasses import dataclass, field
from typing import Optional

QUESTIONS = [
    {
        "id": "q1",
        "competency": "Scoping",
        "text": "Do you have a written success metric for this engagement (a number, not a description)?",
        "options": [
            "A. Yes, it's written down and the customer has confirmed it",
            "B. We have discussed it but it's not written down",
            "C. We have a general direction but no specific number",
            "D. Not yet",
        ],
        "scores": {"A": 4, "B": 2, "C": 1, "D": 0},
    },
    {
        "id": "q2",
        "competency": "Scoping",
        "text": "Have you confirmed who owns the data your system needs, and that you have access to it?",
        "options": [
            "A. Yes, confirmed access and data format",
            "B. We know who owns it but haven't confirmed format or access",
            "C. We assume we'll get access but haven't asked",
            "D. Data source is not yet identified",
        ],
        "scores": {"A": 4, "B": 2, "C": 1, "D": 0},
    },
    {
        "id": "q3",
        "competency": "Technical Depth",
        "text": "Have you run your current prototype on at least 20 real customer samples (not synthetic data)?",
        "options": [
            "A. Yes, and I have failure rate and latency numbers",
            "B. Yes, but only a handful of samples",
            "C. Not yet, still working on the prototype",
            "D. No real customer data available yet",
        ],
        "scores": {"A": 4, "B": 2, "C": 1, "D": 0},
    },
    {
        "id": "q4",
        "competency": "Technical Depth",
        "text": "Do you have an eval harness that scores your system's output against the success metric?",
        "options": [
            "A. Yes, automated eval that runs on every change",
            "B. Manual eval process, run occasionally",
            "C. Spot-check by looking at outputs",
            "D. No eval process yet",
        ],
        "scores": {"A": 4, "B": 2, "C": 1, "D": 0},
    },
    {
        "id": "q5",
        "competency": "Demo Quality",
        "text": "If you were to demo right now, what data would you use?",
        "options": [
            "A. Customer's real data, already tested on 20+ samples",
            "B. Customer's real data, tested on a few samples",
            "C. Realistic synthetic data built from customer examples",
            "D. Generic synthetic data or fixed examples",
        ],
        "scores": {"A": 4, "B": 3, "C": 2, "D": 0},
    },
    {
        "id": "q6",
        "competency": "Demo Quality",
        "text": "Have you confirmed with the customer what output format they expect the system to produce?",
        "options": [
            "A. Yes, confirmed and tested against that format",
            "B. Discussed but not formally confirmed",
            "C. Assumed based on similar projects",
            "D. Not discussed yet",
        ],
        "scores": {"A": 4, "B": 2, "C": 1, "D": 0},
    },
    {
        "id": "q7",
        "competency": "Communication",
        "text": "When did you last share a written update with your primary stakeholder?",
        "options": [
            "A. Within the last 2 days",
            "B. Within the last week",
            "C. Over a week ago",
            "D. We communicate verbally only / no written updates",
        ],
        "scores": {"A": 4, "B": 3, "C": 1, "D": 0},
    },
    {
        "id": "q8",
        "competency": "Communication",
        "text": "Have you identified any risks or blockers and communicated them proactively?",
        "options": [
            "A. Yes, written risk log shared with stakeholder",
            "B. Mentioned in conversation but not tracked",
            "C. I'm aware of risks but haven't raised them yet",
            "D. No risks identified",
        ],
        "scores": {"A": 4, "B": 2, "C": 1, "D": 0},
    },
    {
        "id": "q9",
        "competency": "Handoff",
        "text": "Who will own this system after you hand it off, and do they know it's coming?",
        "options": [
            "A. Named person or team, already briefed, handoff plan exists",
            "B. Named person or team, not yet briefed",
            "C. General team but no specific owner identified",
            "D. Handoff ownership not yet discussed",
        ],
        "scores": {"A": 4, "B": 2, "C": 1, "D": 0},
    },
    {
        "id": "q10",
        "competency": "Handoff",
        "text": "Does the team taking over have enough documentation to operate the system without you?",
        "options": [
            "A. Yes: runbook, architecture diagram, known edge cases, escalation path",
            "B. Partial docs, some gaps",
            "C. Mostly in my head, documentation not started",
            "D. Too early to have written this yet",
        ],
        "scores": {"A": 4, "B": 2, "C": 1, "D": 0},
    },
]

COMPETENCIES = ["Scoping", "Technical Depth", "Demo Quality", "Communication", "Handoff"]

COMPETENCY_ADVICE = {
    "Scoping": {
        "low": "Run a structured scoping interview before building anything else. See Lesson 02.",
        "mid": "Write down your success metric and get customer sign-off before the next build cycle.",
        "high": "Solid. Keep the scope document updated as you learn more.",
    },
    "Technical Depth": {
        "low": "Get real customer data samples this week. Build before you eval.",
        "mid": "Add an automated eval harness. Manual checks don't catch regressions.",
        "high": "Strong technical foundation. Share your eval methodology with the customer.",
    },
    "Demo Quality": {
        "low": "Do not demo on synthetic data. Get real samples or delay the demo.",
        "mid": "Confirm output format with customer before demo day.",
        "high": "Well-prepared. Run one more rehearsal with realistic edge cases.",
    },
    "Communication": {
        "low": "Send a written update today. Silence reads as blocked.",
        "mid": "Move to written updates. Verbal-only creates alignment gaps.",
        "high": "Good communication rhythm. Make sure risks are captured in writing.",
    },
    "Handoff": {
        "low": "Identify your handoff recipient this week. Late handoff planning kills pilots.",
        "mid": "Start the runbook now, even if incomplete. Writing it surfaces gaps.",
        "high": "Handoff ready. Schedule a dry-run walkthrough with the receiving team.",
    },
}


@dataclass
class AssessmentResult:
    competency_scores: dict[str, int] = field(default_factory=dict)
    competency_max: dict[str, int] = field(default_factory=dict)
    answers: dict[str, str] = field(default_factory=dict)

    def pct(self, competency: str) -> float:
        max_score = self.competency_max.get(competency, 1)
        return (self.competency_scores.get(competency, 0) / max_score) * 100

    def advice(self, competency: str) -> str:
        pct = self.pct(competency)
        level = "high" if pct >= 75 else ("mid" if pct >= 40 else "low")
        return COMPETENCY_ADVICE[competency][level]

    def overall_pct(self) -> float:
        total = sum(self.competency_scores.values())
        max_total = sum(self.competency_max.values())
        return (total / max_total) * 100 if max_total else 0


def ask_question(q: dict) -> str:
    print(f"\n[{q['competency']}] {q['text']}")
    for opt in q["options"]:
        print(f"  {opt}")
    while True:
        answer = input("Your answer (A/B/C/D): ").strip().upper()
        if answer in ("A", "B", "C", "D"):
            return answer
        print("Please enter A, B, C, or D.")


def run_assessment() -> AssessmentResult:
    result = AssessmentResult()
    for comp in COMPETENCIES:
        result.competency_scores[comp] = 0
        result.competency_max[comp] = 0

    print("\n=== FDE Self-Assessment ===")
    print("10 questions across 5 competencies. Answer honestly.")
    print("This takes about 5 minutes.\n")

    for q in QUESTIONS:
        answer = ask_question(q)
        score = q["scores"][answer]
        result.answers[q["id"]] = answer
        result.competency_scores[q["competency"]] += score
        result.competency_max[q["competency"]] += 4  # max 4 per question

    return result


def print_report(result: AssessmentResult) -> None:
    print("\n" + "=" * 50)
    print("FDE SELF-ASSESSMENT RESULTS")
    print("=" * 50)

    overall = result.overall_pct()
    print(f"\nOverall readiness: {overall:.0f}%")

    status = (
        "READY: Strong position across competencies."
        if overall >= 75
        else (
            "DEVELOPING: Gaps to address before next milestone."
            if overall >= 50
            else "AT RISK: Significant gaps. Address before customer-facing activities."
        )
    )
    print(f"Status: {status}\n")

    print("Competency breakdown:")
    for comp in COMPETENCIES:
        pct = result.pct(comp)
        bar = "#" * int(pct / 10) + "-" * (10 - int(pct / 10))
        print(f"  {comp:<16} [{bar}] {pct:.0f}%")
        print(f"    Advice: {result.advice(comp)}")

    print("\n" + "=" * 50)


def export_results(result: AssessmentResult, path: str) -> None:
    data = {
        "overall_pct": result.overall_pct(),
        "competencies": {
            comp: {
                "score": result.competency_scores[comp],
                "max": result.competency_max[comp],
                "pct": result.pct(comp),
                "advice": result.advice(comp),
            }
            for comp in COMPETENCIES
        },
        "answers": result.answers,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Results exported to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="FDE Self-Assessment CLI")
    parser.add_argument("--export", metavar="FILE", help="Export results to JSON file")
    args = parser.parse_args()

    result = run_assessment()
    print_report(result)

    if args.export:
        export_results(result, args.export)


if __name__ == "__main__":
    main()
