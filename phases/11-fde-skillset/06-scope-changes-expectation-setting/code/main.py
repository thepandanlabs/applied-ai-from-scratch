"""
ScopeChangeEvaluator: classify scope changes, estimate effort impact,
and draft a customer response.

Usage:
    python main.py --demo
    python main.py --context "..." --scope "..." --change "..."
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from enum import Enum

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"


class ChangeType(str, Enum):
    CLARIFICATION = "clarification"
    EXPANSION = "expansion"
    PIVOT = "pivot"


@dataclass
class ScopeChangeAssessment:
    change_type: ChangeType
    effort_delta_days: int
    timeline_risk: str       # "low", "medium", "high"
    rationale: str
    customer_response: str
    scope_doc_update: str


CLASSIFY_PROMPT = """You are an experienced AI engineering consultant assessing a scope change request.

Project context:
{context}

Original scope:
{original_scope}

Scope change request:
{change_request}

Classify this change and provide your assessment in this exact JSON format:
{{
  "change_type": "clarification" | "expansion" | "pivot",
  "effort_delta_days": <integer, 0 for clarification>,
  "timeline_risk": "low" | "medium" | "high",
  "rationale": "<one paragraph explaining the classification and why>",
  "customer_response": "<draft message to send the customer, professional and direct>",
  "scope_doc_update": "<one sentence: what to add to the scope doc change log>"
}}

Classification rules:
- clarification: same goal, better definition, usually reduces or maintains scope
- expansion: same goal, additional features or coverage, adds work
- pivot: fundamentally different goal, requires restarting scoping

For customer_response:
- Do not commit to anything until impact is assessed (even if it is clarification, say you are updating the scope doc)
- For expansion and pivot: be honest about the tradeoff, do not hedge with "might" and "maybe"
- Keep it under 100 words, professional but direct
- Do not start with "I hope this message finds you well" or similar filler

Return only the JSON object, no other text."""


def classify_scope_change(
    context: str,
    original_scope: str,
    change_request: str,
) -> ScopeChangeAssessment:
    """Classify a scope change and generate a customer response."""
    prompt = CLASSIFY_PROMPT.format(
        context=context,
        original_scope=original_scope,
        change_request=change_request,
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    data = json.loads(raw)

    return ScopeChangeAssessment(
        change_type=ChangeType(data["change_type"]),
        effort_delta_days=int(data["effort_delta_days"]),
        timeline_risk=data["timeline_risk"],
        rationale=data["rationale"],
        customer_response=data["customer_response"],
        scope_doc_update=data["scope_doc_update"],
    )


RISK_LABELS = {
    "low": "[LOW]",
    "medium": "[MEDIUM]",
    "high": "[HIGH]",
}

CHANGE_LABELS = {
    ChangeType.CLARIFICATION: "CLARIFICATION (accept + update doc)",
    ChangeType.EXPANSION: "EXPANSION (negotiate or decline)",
    ChangeType.PIVOT: "PIVOT (restart scoping)",
}


def print_assessment(assessment: ScopeChangeAssessment) -> None:
    """Print a formatted assessment report."""
    print("\n" + "=" * 60)
    print("SCOPE CHANGE ASSESSMENT")
    print("=" * 60)

    print(f"\nType:          {CHANGE_LABELS[assessment.change_type]}")
    print(f"Effort delta:  +{assessment.effort_delta_days} engineering days")
    print(f"Timeline risk: {RISK_LABELS[assessment.timeline_risk]}")

    print("\n--- RATIONALE ---")
    print(assessment.rationale)

    print("\n--- DRAFT CUSTOMER RESPONSE ---")
    print(assessment.customer_response)

    print("\n--- SCOPE DOC UPDATE ---")
    print(assessment.scope_doc_update)

    print("\n" + "=" * 60)
    if assessment.change_type == ChangeType.PIVOT:
        print("ACTION REQUIRED: Stop current work. Schedule a scoping call.")
    elif assessment.change_type == ChangeType.EXPANSION:
        print("ACTION REQUIRED: Send response. Wait for customer decision before proceeding.")
    else:
        print("ACTION REQUIRED: Update scope doc. Confirm with customer in writing.")
    print("=" * 60 + "\n")


DEMO_SCENARIOS = [
    {
        "name": "Scenario 1: Expansion",
        "context": (
            "6-week engagement to build a support ticket classifier for a SaaS company. "
            "Week 3 of 6. Classifier covers Tier 1 support (password resets, account access, "
            "basic how-to questions). Eval set built, first model in staging."
        ),
        "original_scope": (
            "Build and deploy a text classifier that routes Tier 1 support tickets to the correct "
            "support queue. Includes: data labeling guide, model training, eval set (200 labeled "
            "examples), API endpoint, basic admin dashboard. "
            "NOT IN SCOPE: billing questions, Tier 2/3 tickets, multi-language support."
        ),
        "change_request": (
            "Hey, while you are at it, could you also make it handle billing questions? "
            "Customers always get confused between account access and billing, so it would be "
            "great to have both. That is basically the same data, right?"
        ),
    },
    {
        "name": "Scenario 2: Clarification",
        "context": (
            "4-week engagement to build a document summarization tool for a legal firm. "
            "Week 1. Discovery just completed."
        ),
        "original_scope": (
            "Build a tool that summarizes legal documents under 50 pages and returns key clauses, "
            "dates, and parties. Integrates with their Google Drive. "
            "NOT IN SCOPE: contracts over 50 pages, court filings, multi-language documents."
        ),
        "change_request": (
            "We realized we should clarify: when we said 'legal documents' we meant specifically "
            "contract amendments and NDAs. We do not need it to handle lease agreements or "
            "employment contracts. Those go to a different team."
        ),
    },
    {
        "name": "Scenario 3: Pivot",
        "context": (
            "5-week engagement to build an internal knowledge base search tool. "
            "Week 2. Architecture designed, data pipeline in progress."
        ),
        "original_scope": (
            "Build a semantic search system over the company's internal wiki (3,000 documents). "
            "Includes: ingestion pipeline, vector store, search API, basic UI. "
            "NOT IN SCOPE: real-time document sync, user access controls, analytics dashboard."
        ),
        "change_request": (
            "Our CEO just came back from a conference and wants us to pivot. Instead of the search "
            "tool, can you build a full customer-facing chatbot that answers questions about our "
            "product? He wants it launched in 3 weeks."
        ),
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ScopeChangeEvaluator: classify scope changes and draft customer responses"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run on 3 built-in demo scenarios",
    )
    parser.add_argument("--context", help="Project context (what is being built, what week)")
    parser.add_argument(
        "--scope",
        help="Original scope statement including NOT IN SCOPE section",
    )
    parser.add_argument("--change", help="The scope change request text")
    args = parser.parse_args()

    if args.demo:
        for scenario in DEMO_SCENARIOS:
            print(f"\n{'#' * 60}")
            print(f"  {scenario['name']}")
            print(f"{'#' * 60}")
            assessment = classify_scope_change(
                context=scenario["context"],
                original_scope=scenario["original_scope"],
                change_request=scenario["change_request"],
            )
            print_assessment(assessment)
    elif args.context and args.scope and args.change:
        assessment = classify_scope_change(
            context=args.context,
            original_scope=args.scope,
            change_request=args.change,
        )
        print_assessment(assessment)
    else:
        print("Usage:")
        print("  python main.py --demo")
        print("  python main.py --context '...' --scope '...' --change '...'")
        sys.exit(1)


if __name__ == "__main__":
    main()
