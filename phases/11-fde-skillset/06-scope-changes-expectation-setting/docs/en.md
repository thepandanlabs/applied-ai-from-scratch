# Mid-Stream Scope Changes and Expectation Setting

> The right answer to "can we also add X?" is never yes or no. It is "let me assess the impact and get back to you within 24 hours."

**Type:** Learn
**Languages:** Python
**Prerequisites:** 11-02 (scoping before solving), 11-03 (discovery: vague ask to spec)
**Time:** ~45 min
**Phase:** 11 · FDE Skillset

---

## Learning Objectives

- Classify any incoming scope change as clarification, expansion, or pivot
- Explain the impact of each change type on timeline, cost, and delivery risk
- Apply the 24-hour pause rule to protect both sides from reactive decisions
- Build a CLI tool that classifies changes, estimates effort delta, and drafts a customer response
- Maintain a living scope doc with a signed "not in scope" section as your primary defense

---

## The Problem

You are three weeks into a six-week engagement. The customer sends a Slack message: "Hey, while you are building the support ticket classifier, could you also make it handle billing questions? That is basically the same thing, right?"

This is one of the three most dangerous moments in an FDE engagement. Not because the request is unreasonable, but because how you respond in the next 60 seconds determines whether you finish on time and on budget, or whether you quietly agree to scope creep that stretches two weeks of work into five.

The failure mode is not malice. Customers genuinely do not know that "billing questions" means retraining on a different data distribution, adding a new intent category, re-evaluating the classifier, updating the routing logic, and rewriting the demo. They see one form field. You see a different system.

The second failure mode is saying yes without thinking because you want to seem helpful. This is the one that causes 2 a.m. deployment scrambles, missed deadlines, and frayed relationships. The customer is not happy when you deliver late. They are unhappy with the engineer who "agreed" to do everything.

You need a repeatable process for receiving scope changes: classify the type, assess the impact, pause before responding, and communicate clearly.

---

## The Concept

### The Three Scope Change Types

Every scope change request fits one of three categories. Classifying it correctly determines the right response.

```
CLARIFICATION
  Definition: Same goal, better definition.
  Example: "By 'support tickets' we mean only Tier 1, not billing or returns."
  Impact: Usually reduces scope. Sometimes changes priority.
  Response: Accept immediately, update scope doc, document what changed.

EXPANSION
  Definition: Same goal, more features or coverage.
  Example: "Can we also handle billing questions with the classifier?"
  Impact: Additional work. Days to weeks. May shift delivery date.
  Response: Assess impact, communicate the tradeoff, negotiate or decline.

PIVOT
  Definition: Different goal entirely.
  Example: "Actually, instead of classifying tickets, can we build a chatbot?"
  Impact: Restart. New scoping, new timeline, new budget conversation.
  Response: Stop, scope the new goal from scratch, present options.
```

### The Decision Tree

```
Receive scope change request
           |
           v
 Is the core goal the same?
      |            |
     YES           NO
      |            |
      v            v
 Does it         PIVOT
 add work?     (restart scoping)
  |       |
 YES      NO
  |       |
  v       v
EXPANSION  CLARIFICATION
(negotiate) (accept + update doc)
```

### The Expectation-Setting Toolkit

Three tools protect you from scope drift:

```
TOOL 1: THE LIVING SCOPE DOC
  - Created at project start
  - Updated after every change
  - Has an explicit "NOT IN SCOPE" section
  - Customer signed off on the original version
  - Change log at the bottom: date, request, decision, who approved

TOOL 2: THE WEEKLY WRITTEN STATUS
  - Sent every Monday morning, no exceptions
  - Format: what shipped last week, what ships next week, blockers, open questions
  - Written, not verbal - creates a paper trail of shared understanding
  - Includes any scope changes discussed that week

TOOL 3: THE 24-HOUR RULE
  - Never respond to a scope change request immediately
  - "Let me assess the impact and get back to you by tomorrow"
  - This pause protects you from reactive yes/no answers
  - And it signals that you take the request seriously
```

### The Impact Assessment Formula

When you receive an expansion request, estimate impact across four dimensions:

```
EFFORT DELTA
  Additional engineering days to implement, test, evaluate, and deploy.
  Always round up. Hidden work is always present.

TIMELINE RISK
  Does this compress any other deliverable?
  What slips if this is added?

EVALUATION COST
  AI systems need evals. New features need new eval sets.
  Budget 20-30% of implementation time for eval work.

DEPENDENCY RISK
  Does the new scope depend on data, access, or decisions
  not yet available? New dependencies = new blockers.
```

---

## Build It

### Step 1: Setup

```python
# pip install anthropic
# Set ANTHROPIC_API_KEY in environment

import argparse
import json
import os
import sys
from dataclasses import dataclass
from enum import Enum

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
```

### Step 2: The Change Type Enum and Data Model

```python
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
```

### Step 3: The Classifier

```python
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
```

### Step 4: The Report Formatter

```python
RISK_COLORS = {
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
    print(f"Timeline risk: {RISK_COLORS[assessment.timeline_risk]}")

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
```

### Step 5: Main CLI

```python
DEMO_SCENARIOS = [
    {
        "name": "Scenario 1: Expansion",
        "context": "6-week engagement to build a support ticket classifier for a SaaS company. Week 3 of 6. Classifier covers Tier 1 support (password resets, account access, basic how-to questions). Eval set built, first model in staging.",
        "original_scope": "Build and deploy a text classifier that routes Tier 1 support tickets to the correct support queue. Includes: data labeling guide, model training, eval set (200 labeled examples), API endpoint, basic admin dashboard. NOT IN SCOPE: billing questions, Tier 2/3 tickets, multi-language support.",
        "change_request": "Hey, while you are at it, could you also make it handle billing questions? Customers always get confused between account access and billing, so it would be great to have both. That is basically the same data, right?",
    },
    {
        "name": "Scenario 2: Clarification",
        "context": "4-week engagement to build a document summarization tool for a legal firm. Week 1. Discovery just completed.",
        "original_scope": "Build a tool that summarizes legal documents under 50 pages and returns key clauses, dates, and parties. Integrates with their Google Drive. NOT IN SCOPE: contracts over 50 pages, court filings, multi-language documents.",
        "change_request": "We realized we should clarify: when we said 'legal documents' we meant specifically contract amendments and NDAs. We do not need it to handle lease agreements or employment contracts. Those go to a different team.",
    },
    {
        "name": "Scenario 3: Pivot",
        "context": "5-week engagement to build an internal knowledge base search tool. Week 2. Architecture designed, data pipeline in progress.",
        "original_scope": "Build a semantic search system over the company's internal wiki (3,000 documents). Includes: ingestion pipeline, vector store, search API, basic UI. NOT IN SCOPE: real-time document sync, user access controls, analytics dashboard.",
        "change_request": "Our CEO just came back from a conference and wants us to pivot. Instead of the search tool, can you build a full customer-facing chatbot that answers questions about our product? He wants it launched in 3 weeks.",
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
    parser.add_argument("--scope", help="Original scope statement including NOT IN SCOPE section")
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
```

> **Real-world check:** A startup founder you are working with says: "We are an agile team, we do not do formal scope documents. We just talk things through." How do you explain the value of the living scope doc and the "not in scope" section without sounding bureaucratic or like you distrust them?

---

## Use It

Run the tool on all three demo scenarios:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --demo
```

Expected output for Scenario 1 (expansion):
- Classification: EXPANSION
- Effort delta: 3-5 days (billing data requires new labels, new eval, new routing logic)
- Timeline risk: MEDIUM or HIGH
- Customer response: transparent about the tradeoff, does not commit

Expected output for Scenario 2 (clarification):
- Classification: CLARIFICATION
- Effort delta: 0 days (scope is narrowing, not growing)
- Timeline risk: LOW
- Customer response: confirms the update, thanks them for the clarity

Expected output for Scenario 3 (pivot):
- Classification: PIVOT
- Effort delta: large (full restart)
- Timeline risk: HIGH
- Customer response: honest about the impact, proposes a scoping call

You can also run it against your own scenario:

```bash
python main.py \
  --context "8-week RAG project, week 4, document pipeline complete" \
  --scope "Build RAG over internal HR docs. NOT IN SCOPE: real-time sync, user authentication." \
  --change "HR wants the system to also answer questions about employee performance reviews"
```

> **Perspective shift:** Your manager says "just say yes to everything, we will figure it out later, we need to keep the customer happy." You know this approach leads to missed deadlines and eroded trust. How do you push back constructively, and what evidence from this lesson do you use?

---

## Ship It

The output for this lesson is `outputs/prompt-scope-change-playbook.md`. It is a structured playbook you can paste into any project's shared drive or Notion workspace at kickoff. It gives the customer a clear picture of how scope changes will be handled before the first change request arrives.

The runnable tool is `code/main.py`:

```bash
python main.py --demo
```

---

## Evaluate It

**Check 1: Does the classification match reality?**
Run the three demo scenarios. For each one, manually classify the change before reading the output. If your classification and the model's classification disagree on more than one scenario, review the classifier prompt and add more explicit examples.

**Check 2: Is the customer response appropriate for each type?**
A good clarification response thanks the customer and confirms the scope doc will be updated. A good expansion response names the effort and timeline impact explicitly. A good pivot response stops, proposes a scoping call, and does not commit to the new timeline. If any response hedges with vague language, tighten the prompt.

**Check 3: Does the tool reduce response latency?**
Time yourself: how long does it take to draft a scope change response without the tool? With the tool? The tool should cut your first-draft time from 20 minutes to 3 minutes. If it does not, the prompt is producing responses that need too much editing.

**Check 4: Stress test with an ambiguous request.**
Submit a change request that could be either expansion or clarification depending on interpretation. The model should flag the ambiguity in the rationale rather than silently choosing one. If it does not, add a note to the prompt asking it to call out ambiguous cases.
