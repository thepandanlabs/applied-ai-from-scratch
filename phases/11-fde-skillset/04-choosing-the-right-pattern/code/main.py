#!/usr/bin/env python3
"""
PatternMatcher CLI

Takes a requirement description and scores it against 5 AI patterns
using a decision matrix. Recommends a starting pattern and warns about
common mismatches.

Usage:
    python main.py --requirement "Classify support tickets"
    python main.py --interactive
    python main.py --requirement req.txt
"""
import json
import sys
import argparse
from pathlib import Path
import anthropic

MODEL = "claude-3-5-haiku-20241022"

DECISION_AXES = [
    "output_depends_on_knowledge_base",
    "requires_multistep_reasoning",
    "latency_under_2s_required",
    "output_must_be_deterministic",
    "integration_complexity_must_stay_low",
    "data_too_large_for_context_window",
    "highly_repetitive_with_abundant_examples",
]

AXIS_LABELS = {
    "output_depends_on_knowledge_base": "Output depends on a changing knowledge base",
    "requires_multistep_reasoning": "Requires multi-step reasoning or tool use",
    "latency_under_2s_required": "Latency under 2s is a hard requirement",
    "output_must_be_deterministic": "Output must be consistent for same input",
    "integration_complexity_must_stay_low": "Integration complexity must stay low",
    "data_too_large_for_context_window": "Data is too large to fit in a single context",
    "highly_repetitive_with_abundant_examples": "Highly repetitive task with many labeled examples",
}

# Score each pattern on each axis (0=bad fit, 1=neutral, 2=good fit)
PATTERN_MATRIX = {
    "single_llm_call": {
        "output_depends_on_knowledge_base": 0,
        "requires_multistep_reasoning": 0,
        "latency_under_2s_required": 2,
        "output_must_be_deterministic": 2,
        "integration_complexity_must_stay_low": 2,
        "data_too_large_for_context_window": 0,
        "highly_repetitive_with_abundant_examples": 0,
    },
    "rag": {
        "output_depends_on_knowledge_base": 2,
        "requires_multistep_reasoning": 0,
        "latency_under_2s_required": 1,
        "output_must_be_deterministic": 1,
        "integration_complexity_must_stay_low": 1,
        "data_too_large_for_context_window": 2,
        "highly_repetitive_with_abundant_examples": 0,
    },
    "agent_with_tools": {
        "output_depends_on_knowledge_base": 1,
        "requires_multistep_reasoning": 2,
        "latency_under_2s_required": 0,
        "output_must_be_deterministic": 0,
        "integration_complexity_must_stay_low": 0,
        "data_too_large_for_context_window": 1,
        "highly_repetitive_with_abundant_examples": 0,
    },
    "multi_agent": {
        "output_depends_on_knowledge_base": 1,
        "requires_multistep_reasoning": 2,
        "latency_under_2s_required": 0,
        "output_must_be_deterministic": 0,
        "integration_complexity_must_stay_low": 0,
        "data_too_large_for_context_window": 1,
        "highly_repetitive_with_abundant_examples": 0,
    },
    "fine_tuning": {
        "output_depends_on_knowledge_base": 0,
        "requires_multistep_reasoning": 0,
        "latency_under_2s_required": 1,
        "output_must_be_deterministic": 2,
        "integration_complexity_must_stay_low": 1,
        "data_too_large_for_context_window": 1,
        "highly_repetitive_with_abundant_examples": 2,
    },
}

PATTERN_LABELS = {
    "single_llm_call": "Single LLM call",
    "rag": "RAG (Retrieval-Augmented Generation)",
    "agent_with_tools": "Agent with tools",
    "multi_agent": "Multi-agent",
    "fine_tuning": "Fine-tuning",
}

PATTERN_DESCRIPTIONS = {
    "single_llm_call": "One prompt, one response. No retrieval, no tools. Best for fixed I/O with deterministic output needs.",
    "rag": "Retrieve relevant context from a knowledge base, then generate. Best for factual grounding against a large or changing corpus.",
    "agent_with_tools": "LLM decides which tools to call and combines results. Best for multi-step tasks requiring live data or external APIs.",
    "multi_agent": "Multiple LLMs with distinct roles coordinate. Best for complex workflows with parallel tasks or independent verification.",
    "fine_tuning": "Train the base model on task-specific examples. Best for highly repetitive tasks with abundant labeled data.",
}

MISMATCH_WARNINGS = [
    {
        "condition": lambda scores, requirement_text: (
            scores.get("agent_with_tools", 0) >= 7
            and scores.get("rag", 0) >= 6
            and "lookup" in requirement_text.lower()
        ),
        "warning": "This requirement may be solvable with RAG alone. If the only tool needed is a knowledge base lookup, agents add overhead without adding capability. Test RAG first.",
    },
    {
        "condition": lambda scores, requirement_text: (
            scores.get("multi_agent", 0) >= 7
            and scores.get("agent_with_tools", 0) >= 6
        ),
        "warning": "Multi-agent scores high, but agent_with_tools is close. Start with a single agent. Add a second agent only if the single-agent output quality is insufficient.",
    },
    {
        "condition": lambda scores, requirement_text: (
            scores.get("agent_with_tools", 0) >= 7
            and "latency" in requirement_text.lower()
            and any(w in requirement_text.lower() for w in ["2s", "2 second", "fast", "real-time"])
        ),
        "warning": "You require low latency but agents score highest. Agent overhead (multiple LLM calls, tool latency) typically adds 3-10 seconds. Verify latency is acceptable or reconsider pattern.",
    },
    {
        "condition": lambda scores, requirement_text: (
            scores.get("fine_tuning", 0) >= 6
            and scores.get("single_llm_call", 0) >= 6
        ),
        "warning": "Fine-tuning scores close to single LLM call. Start with a well-engineered prompt. Fine-tune only after validating the prompt approach fails to meet quality requirements.",
    },
]

SCORING_PROMPT = """You are analyzing an AI system requirement to score it on decision axes.

Requirement: {requirement}

For each decision axis below, score it 0, 1, or 2:
- 0: This axis does NOT apply to the requirement
- 1: This axis PARTIALLY applies or is uncertain
- 2: This axis CLEARLY applies to the requirement

Decision axes:
{axes}

Return a JSON object with axis names as keys and integer scores (0, 1, or 2) as values.
Return ONLY the JSON object, no explanation.
"""


def score_requirement(requirement: str, client: anthropic.Anthropic) -> dict[str, int]:
    """Use Claude to score a requirement against the decision axes."""
    axes_text = "\n".join(f"- {k}: {v}" for k, v in AXIS_LABELS.items())

    message = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": SCORING_PROMPT.format(
                    requirement=requirement, axes=axes_text
                ),
            }
        ],
    )

    raw = message.content[0].text.strip()
    # Extract JSON if wrapped in backticks
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def compute_pattern_scores(axis_scores: dict[str, int]) -> dict[str, int]:
    """Compute weighted pattern scores from axis scores."""
    pattern_totals: dict[str, int] = {}
    for pattern, weights in PATTERN_MATRIX.items():
        total = 0
        for axis, axis_score in axis_scores.items():
            weight = weights.get(axis, 0)
            # Multiply axis score (0-2) by matrix weight (0-2)
            total += axis_score * weight
        pattern_totals[pattern] = total
    return pattern_totals


def check_warnings(pattern_scores: dict[str, int], requirement: str) -> list[str]:
    """Check for known pattern mismatch warnings."""
    warnings = []
    for mw in MISMATCH_WARNINGS:
        try:
            if mw["condition"](pattern_scores, requirement):
                warnings.append(mw["warning"])
        except Exception:
            pass
    return warnings


def print_results(
    requirement: str,
    axis_scores: dict[str, int],
    pattern_scores: dict[str, int],
    warnings: list[str],
) -> None:
    print("\n" + "=" * 60)
    print("PATTERN MATCHER RESULTS")
    print("=" * 60)
    print(f"\nRequirement: {requirement[:120]}")

    print("\nAxis scores:")
    for axis, label in AXIS_LABELS.items():
        score = axis_scores.get(axis, 0)
        bar = "*" * score + "-" * (2 - score)
        print(f"  [{bar}] {label}")

    sorted_patterns = sorted(pattern_scores.items(), key=lambda x: x[1], reverse=True)
    max_score = sorted_patterns[0][1] if sorted_patterns else 1

    print("\nPattern scores:")
    for i, (pattern, score) in enumerate(sorted_patterns):
        label = PATTERN_LABELS[pattern]
        bar = "#" * min(int((score / (max_score or 1)) * 15), 15)
        bar = bar.ljust(15, "-")
        tag = "  *** RECOMMENDED ***" if i == 0 else ""
        print(f"  {label:<35} [{bar}] {score}{tag}")

    top_pattern = sorted_patterns[0][0]
    print(f"\nRecommendation: {PATTERN_LABELS[top_pattern]}")
    print(f"  {PATTERN_DESCRIPTIONS[top_pattern]}")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  ! {w}")
    else:
        print("\nNo pattern mismatch warnings.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="PatternMatcher CLI")
    parser.add_argument("--requirement", metavar="TEXT_OR_FILE", help="Requirement description or path to file")
    parser.add_argument("--interactive", action="store_true", help="Enter requirement interactively")
    parser.add_argument("--output", metavar="FILE", help="Export results to JSON")
    args = parser.parse_args()

    if args.requirement:
        path = Path(args.requirement)
        if path.exists():
            requirement = path.read_text().strip()
        else:
            requirement = args.requirement
    elif args.interactive:
        print("\nDescribe the requirement for the AI system:")
        print("Include latency constraints, data characteristics, and workflow details.")
        requirement = input("> ").strip()
    else:
        parser.print_help()
        sys.exit(0)

    if not requirement:
        print("Error: requirement is empty.", file=sys.stderr)
        sys.exit(1)

    print("\nAnalyzing requirement...")
    client = anthropic.Anthropic()

    axis_scores = score_requirement(requirement, client)
    pattern_scores = compute_pattern_scores(axis_scores)
    warnings = check_warnings(pattern_scores, requirement)

    print_results(requirement, axis_scores, pattern_scores, warnings)

    if args.output:
        sorted_patterns = sorted(pattern_scores.items(), key=lambda x: x[1], reverse=True)
        data = {
            "requirement": requirement,
            "axis_scores": axis_scores,
            "pattern_scores": {PATTERN_LABELS[p]: s for p, s in sorted_patterns},
            "recommendation": PATTERN_LABELS[sorted_patterns[0][0]],
            "warnings": warnings,
        }
        with open(args.output, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Results exported to {args.output}")


if __name__ == "__main__":
    main()
