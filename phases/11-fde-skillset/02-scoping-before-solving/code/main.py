#!/usr/bin/env python3
"""
ScopingInterview CLI

Runs a structured scoping interview across 5 question areas and produces
a scope document in JSON and markdown formats.

Usage:
    python main.py
    python main.py --output scope.json
    python main.py --output scope.json --markdown scope.md
"""
import json
import argparse
from dataclasses import dataclass, field
from typing import Optional


QUESTION_AREAS = [
    {
        "id": "current_process",
        "label": "CURRENT PROCESS",
        "prompt": "Walk me through the current manual process, step by step.",
        "follow_up": "Roughly how many people do this, and how many times per day?",
        "vague_signals": ["it depends", "varies", "sometimes", "usually", "kind of"],
        "vague_follow_up": "Can you describe the most common case, even if it is not universal?",
        "missing_signals": [],
        "missing_prompt": None,
    },
    {
        "id": "failure_point",
        "label": "FAILURE POINT",
        "prompt": "Where does this process break down or take the most time?",
        "follow_up": "How long does that step take on average?",
        "vague_signals": ["too long", "slow", "frustrating", "painful", "manual"],
        "vague_follow_up": "Can you put a time estimate on it? Even a rough guess helps.",
        "missing_signals": ["minute", "hour", "day", "second", "week", "month"],
        "missing_prompt": "Your answer doesn't include a time estimate. How long does this take?",
    },
    {
        "id": "success_metric",
        "label": "SUCCESS METRIC",
        "prompt": "What does success look like as a specific number in 90 days?",
        "follow_up": "What is the baseline today (before this system exists)?",
        "vague_signals": ["better", "faster", "smarter", "improved", "more efficient", "easier"],
        "vague_follow_up": "Can you put a number on it? For example: reduce time by X%, or handle Y more per day.",
        "missing_signals": ["%", "minutes", "hours", "seconds", "per day", "per week", "from", "to"],
        "missing_prompt": "[FLAG] Your success metric doesn't include a measurable number. A metric without a number cannot be evaluated.",
    },
    {
        "id": "data",
        "label": "DATA OWNERSHIP",
        "prompt": "Who owns the data this system needs, what format is it in, and can we get access this week?",
        "follow_up": "Is there any approval process required for access (IT, legal, GDPR)?",
        "vague_signals": ["we have it", "it's available", "i can get it", "should be fine"],
        "vague_follow_up": "Who specifically owns it, and what is the approval path?",
        "missing_signals": [],
        "missing_prompt": None,
    },
    {
        "id": "integration_point",
        "label": "INTEGRATION POINT",
        "prompt": "Where exactly does the AI output go, and who acts on it next?",
        "follow_up": "What happens if the AI output is wrong? Who catches it?",
        "vague_signals": ["the team", "the system", "wherever", "into our workflow"],
        "vague_follow_up": "Can you name the specific tool or step where the output appears?",
        "missing_signals": [],
        "missing_prompt": None,
    },
    {
        "id": "out_of_scope",
        "label": "OUT OF SCOPE",
        "prompt": "What should this system explicitly NOT do in this first version?",
        "follow_up": "Are there any use cases the stakeholders might expect that you want to exclude?",
        "vague_signals": [],
        "vague_follow_up": None,
        "missing_signals": [],
        "missing_prompt": None,
    },
]


@dataclass
class ScopeDocument:
    answers: dict[str, str] = field(default_factory=dict)
    follow_up_answers: dict[str, str] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "current_process": self.answers.get("current_process", ""),
            "current_process_detail": self.follow_up_answers.get("current_process", ""),
            "failure_point": self.answers.get("failure_point", ""),
            "failure_point_detail": self.follow_up_answers.get("failure_point", ""),
            "success_metric": self.answers.get("success_metric", ""),
            "success_metric_baseline": self.follow_up_answers.get("success_metric", ""),
            "data": self.answers.get("data", ""),
            "data_access": self.follow_up_answers.get("data", ""),
            "integration_point": self.answers.get("integration_point", ""),
            "integration_fallback": self.follow_up_answers.get("integration_point", ""),
            "out_of_scope": self.answers.get("out_of_scope", ""),
            "flags": self.flags,
        }

    def to_markdown(self) -> str:
        d = self.to_dict()
        lines = [
            "# Scope Document\n",
            "## Problem",
            f"{d['failure_point']}",
            f"*Detail:* {d['failure_point_detail']}\n",
            "## Current Process",
            f"{d['current_process']}",
            f"*Detail:* {d['current_process_detail']}\n",
            "## Success Metric",
            f"{d['success_metric']}",
            f"*Baseline:* {d['success_metric_baseline']}\n",
            "## Data",
            f"{d['data']}",
            f"*Access path:* {d['data_access']}\n",
            "## Integration Point",
            f"{d['integration_point']}",
            f"*Fallback:* {d['integration_fallback']}\n",
            "## Out of Scope",
            f"{d['out_of_scope']}\n",
        ]
        if d["flags"]:
            lines.append("## Flags (Review Before Building)")
            for flag in d["flags"]:
                lines.append(f"- {flag}")
        return "\n".join(lines)


def is_vague(answer: str, signals: list[str]) -> bool:
    answer_lower = answer.lower()
    return any(s in answer_lower for s in signals)


def is_missing(answer: str, required_signals: list[str]) -> bool:
    if not required_signals:
        return False
    answer_lower = answer.lower()
    return not any(s in answer_lower for s in required_signals)


def ask(prompt: str) -> str:
    print(f"\n{prompt}")
    lines = []
    while True:
        line = input("> ").strip()
        if line:
            lines.append(line)
            break
    return " ".join(lines)


def run_interview() -> ScopeDocument:
    doc = ScopeDocument()

    print("\n" + "=" * 55)
    print("SCOPING INTERVIEW")
    print("=" * 55)
    print("This interview takes 15-20 minutes.")
    print("Answer as specifically as possible.")
    print("Vague answers will trigger follow-up questions.\n")

    for area in QUESTION_AREAS:
        print(f"\n--- {area['label']} ---")
        answer = ask(area["prompt"])
        doc.answers[area["id"]] = answer

        # Check for vagueness
        if area["vague_signals"] and is_vague(answer, area["vague_signals"]):
            print(f"\n[FOLLOW-UP] {area['vague_follow_up']}")
            follow_up = ask(area["follow_up"])
            doc.follow_up_answers[area["id"]] = follow_up
        else:
            follow_up = ask(area["follow_up"])
            doc.follow_up_answers[area["id"]] = follow_up

        # Check for missing required elements
        if area["missing_signals"] and is_missing(answer, area["missing_signals"]):
            print(f"\n{area['missing_prompt']}")
            clarification = ask("Please clarify:")
            doc.answers[area["id"]] = answer + " " + clarification
            if area["id"] == "success_metric":
                doc.flags.append(
                    "Success metric may lack a specific measurable number. Review before finalizing."
                )

    return doc


def print_scope(doc: ScopeDocument) -> None:
    print("\n" + "=" * 55)
    print("SCOPE DOCUMENT")
    print("=" * 55)
    print(doc.to_markdown())

    if doc.flags:
        print("\n[REVIEW BEFORE BUILDING]")
        for f in doc.flags:
            print(f"  * {f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ScopingInterview CLI")
    parser.add_argument("--output", metavar="FILE", help="Export scope document to JSON")
    parser.add_argument("--markdown", metavar="FILE", help="Export scope document to Markdown")
    args = parser.parse_args()

    doc = run_interview()
    print_scope(doc)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(doc.to_dict(), f, indent=2)
        print(f"\nScope document exported to {args.output}")

    if args.markdown:
        with open(args.markdown, "w") as f:
            f.write(doc.to_markdown())
        print(f"Markdown scope exported to {args.markdown}")


if __name__ == "__main__":
    main()
