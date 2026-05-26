"""
FDE Mock Engagement: Email Triage and Auto-Response MVP

Router pattern: classify incoming emails into 4 categories,
generate draft responses for routine categories using Claude.

Usage:
    python main.py --demo                    # Process synthetic emails
    python main.py --demo --eval             # Run golden set evaluation
    python main.py --email "email body..."   # Process a single email
    python main.py --demo --output-json      # JSON output for integration

Requires: ANTHROPIC_API_KEY environment variable
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
MODEL = "claude-3-5-haiku-20241022"

# ---------------------------------------------------------------------------
# Category definitions (the spec, not the code)
# ---------------------------------------------------------------------------
CATEGORIES = {
    "password_reset": "User cannot access account due to forgotten or expired password",
    "billing": "Questions about charges, invoices, plans, or payment methods (NOT disputes)",
    "feature_how_to": "How-to questions about product features, not bugs",
    "escalate": "Billing disputes, bugs, account issues, threats, anything requiring human judgment",
}

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------
CLASSIFICATION_SYSTEM_PROMPT = """You are an email triage classifier for a B2B SaaS support team.

Classify the incoming support email into exactly one of these categories:
- password_reset: User cannot access account due to forgotten or expired password
- billing: Routine billing questions (NOT disputes, NOT complaints about charges)
- feature_how_to: How-to questions about existing product features
- escalate: Billing disputes, technical bugs, account issues, frustrated users, anything requiring human judgment

Return ONLY valid JSON in this exact format:
{
  "category": "<category_name>",
  "confidence": <0.0 to 1.0>,
  "reason": "<one sentence explaining the classification>"
}

When in doubt, choose escalate. A false positive on escalation is far less costly than a false negative."""

DRAFT_SYSTEM_PROMPTS = {
    "password_reset": """You are a support agent at a B2B SaaS company writing a helpful password reset response.

Be concise, friendly, and actionable. Include the exact steps:
1. Go to login page
2. Click "Forgot Password"
3. Enter email address
4. Check inbox for reset link (expires in 24 hours)
5. If no email received in 5 minutes, check spam or contact support

Keep the response under 150 words. Do not invent product-specific details.""",

    "billing": """You are a support agent at a B2B SaaS company writing a billing inquiry response.

Be helpful and specific. Acknowledge the question, explain where to find billing information in the account portal, and offer to help further. If the question is about a specific charge, acknowledge it and direct them to the billing portal.

Keep the response under 150 words. Do not make commitments about refunds or credits - direct those to the billing team.""",

    "feature_how_to": """You are a support agent at a B2B SaaS company writing a feature guidance response.

Be practical and step-by-step. If you don't know the specific feature details, provide a helpful general framework: where to find settings, how to access documentation, and how to reach the product team for specifics.

Keep the response under 200 words. Focus on empowering the user to solve it themselves.""",
}

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class ClassificationResult:
    category: str
    confidence: float
    reason: str

@dataclass
class EmailProcessingResult:
    email_id: str
    email_body: str
    classification: ClassificationResult
    draft_response: Optional[str]
    routed_to: str  # "automated" or "human_queue"

@dataclass
class GoldenSetItem:
    email_id: str
    email_body: str
    expected_category: str
    expected_route: str  # "automated" or "human_queue"

# ---------------------------------------------------------------------------
# Golden set: 20 representative emails
# ---------------------------------------------------------------------------
GOLDEN_SET: list[GoldenSetItem] = [
    # password_reset (7 examples)
    GoldenSetItem("g01", "Hi, I forgot my password and can't log in. Can you help?", "password_reset", "automated"),
    GoldenSetItem("g02", "My password reset email never arrived. I've been waiting 30 minutes.", "password_reset", "automated"),
    GoldenSetItem("g03", "I need to reset my password. I changed my email address last week so the old reset link won't work.", "password_reset", "automated"),
    GoldenSetItem("g04", "Our entire team is locked out. The admin account password expired and we can't access any accounts.", "password_reset", "automated"),
    GoldenSetItem("g05", "I keep getting 'invalid password' even after resetting. Something is broken.", "escalate", "human_queue"),
    GoldenSetItem("g06", "Password reset. Urgent.", "password_reset", "automated"),
    GoldenSetItem("g07", "I think someone changed my password without my permission. I can't log in.", "escalate", "human_queue"),

    # billing (5 examples)
    GoldenSetItem("g08", "Where can I find my invoice for last month?", "billing", "automated"),
    GoldenSetItem("g09", "How do I update my credit card on file?", "billing", "automated"),
    GoldenSetItem("g10", "What's the difference between the Pro and Enterprise plans?", "billing", "automated"),
    GoldenSetItem("g11", "I was charged twice this month and I want a refund immediately.", "escalate", "human_queue"),
    GoldenSetItem("g12", "I cancelled my account last week but I'm still being charged. This is fraud.", "escalate", "human_queue"),

    # feature_how_to (5 examples)
    GoldenSetItem("g13", "How do I export my data to CSV?", "feature_how_to", "automated"),
    GoldenSetItem("g14", "Is there a way to set up email notifications for new activity?", "feature_how_to", "automated"),
    GoldenSetItem("g15", "How do I add a team member to my workspace?", "feature_how_to", "automated"),
    GoldenSetItem("g16", "The export feature isn't working for me. The button does nothing.", "escalate", "human_queue"),
    GoldenSetItem("g17", "Can I integrate your tool with Salesforce?", "feature_how_to", "automated"),

    # escalate - explicit (3 examples)
    GoldenSetItem("g18", "Your product lost all my data after the update yesterday. I need this fixed immediately or I'm cancelling.", "escalate", "human_queue"),
    GoldenSetItem("g19", "I've submitted 5 support tickets in the last week and nobody has responded. This is unacceptable.", "escalate", "human_queue"),
    GoldenSetItem("g20", "I'm testing a security issue I found in your API. I can access other customers' data.", "escalate", "human_queue"),
]

# ---------------------------------------------------------------------------
# Demo emails for single-pass demo
# ---------------------------------------------------------------------------
DEMO_EMAILS = [
    "Hi, I forgot my password and I can't get into my account. Can you send a reset link?",
    "Where can I find my invoice for April? I need it for our accounting team.",
    "How do I set up webhook notifications for new signups?",
    "I was charged $299 last month but I'm on the $49 plan. I need this resolved immediately.",
    "Our entire engineering team is locked out after the SSO migration. We have a demo in 2 hours.",
]

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def classify_email(email_body: str) -> ClassificationResult:
    """Classify an email into one of 4 categories using Claude."""
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=CLASSIFICATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Support email to classify:\n\n{email_body}"}],
        )
        raw = response.content[0].text.strip()
        # Extract JSON if wrapped in markdown
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        return ClassificationResult(
            category=data["category"],
            confidence=float(data["confidence"]),
            reason=data["reason"],
        )
    except Exception as e:
        # Safe fallback: escalate anything that fails classification
        return ClassificationResult(
            category="escalate",
            confidence=0.5,
            reason=f"Classification error - defaulting to escalate: {e}",
        )


def generate_draft(email_body: str, category: str) -> str:
    """Generate a draft response for routine email categories."""
    if category not in DRAFT_SYSTEM_PROMPTS:
        raise ValueError(f"No draft template for category: {category}")

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=DRAFT_SYSTEM_PROMPTS[category],
        messages=[{"role": "user", "content": f"Write a response to this support email:\n\n{email_body}"}],
    )
    return response.content[0].text.strip()


def process_email(email_id: str, email_body: str) -> EmailProcessingResult:
    """Full pipeline: classify, then route to draft generation or human queue."""
    classification = classify_email(email_body)

    if classification.category in DRAFT_SYSTEM_PROMPTS:
        draft = generate_draft(email_body, classification.category)
        routed_to = "automated"
    else:
        draft = None
        routed_to = "human_queue"

    return EmailProcessingResult(
        email_id=email_id,
        email_body=email_body,
        classification=classification,
        draft_response=draft,
        routed_to=routed_to,
    )


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def run_golden_set_eval(verbose: bool = False) -> dict:
    """Run the 20-email golden set and report accuracy metrics."""
    print(f"\nRunning golden set evaluation ({len(GOLDEN_SET)} emails)...\n")

    results = []
    correct = 0
    escalation_tp = 0  # Correctly escalated
    escalation_fp = 0  # Escalated when should be automated
    escalation_fn = 0  # Automated when should be escalated
    category_counts: dict[str, dict] = {}

    for item in GOLDEN_SET:
        result = process_email(item.email_id, item.email_body)
        predicted = result.classification.category
        expected = item.expected_category

        match = predicted == expected
        if match:
            correct += 1

        # Escalation metrics
        if item.expected_route == "human_queue":
            if result.routed_to == "human_queue":
                escalation_tp += 1
            else:
                escalation_fn += 1
                if verbose:
                    print(f"  MISS (fn) {item.email_id}: should escalate, got {predicted}")
                    print(f"    Email: {item.email_body[:60]}...")
        else:
            if result.routed_to == "human_queue":
                escalation_fp += 1
                if verbose:
                    print(f"  MISS (fp) {item.email_id}: should automate, escalated as {predicted}")

        # Per-category tracking
        if expected not in category_counts:
            category_counts[expected] = {"total": 0, "correct": 0}
        category_counts[expected]["total"] += 1
        if match:
            category_counts[expected]["correct"] += 1

        results.append({
            "id": item.email_id,
            "expected": expected,
            "predicted": predicted,
            "match": match,
            "confidence": result.classification.confidence,
            "routed_to": result.routed_to,
        })

    total = len(GOLDEN_SET)
    routine_total = sum(v["total"] for k, v in category_counts.items() if k != "escalate")
    routine_correct = sum(v["correct"] for k, v in category_counts.items() if k != "escalate")
    routine_accuracy = routine_correct / routine_total if routine_total > 0 else 0

    escalation_precision = (
        escalation_tp / (escalation_tp + escalation_fp)
        if (escalation_tp + escalation_fp) > 0
        else 1.0
    )
    escalation_recall = (
        escalation_tp / (escalation_tp + escalation_fn)
        if (escalation_tp + escalation_fn) > 0
        else 1.0
    )

    print("EVALUATION RESULTS")
    print("=" * 50)
    print(f"Overall accuracy:              {correct}/{total} ({100*correct/total:.1f}%)")
    print(f"Routine category accuracy:     {routine_correct}/{routine_total} ({100*routine_accuracy:.1f}%)")
    print(f"Escalation recall:             {100*escalation_recall:.1f}% (target: 100%)")
    print(f"Escalation precision:          {100*escalation_precision:.1f}% (target: 95%)")
    print()
    print("Per-category accuracy:")
    for cat, counts in sorted(category_counts.items()):
        acc = counts["correct"] / counts["total"]
        print(f"  {cat:<20} {counts['correct']}/{counts['total']} ({100*acc:.0f}%)")
    print()

    # Go/no-go
    go = routine_accuracy >= 0.90 and escalation_recall >= 1.0
    if go:
        print("GO/NO-GO: GO")
        if escalation_precision < 0.95:
            print("  Note: escalation precision below 95% target - acceptable risk,")
            print("  monitor false positives in first 2 weeks of production.")
    else:
        print("GO/NO-GO: NO-GO")
        if routine_accuracy < 0.90:
            print(f"  Blocker: routine accuracy {100*routine_accuracy:.1f}% below 90% threshold")
        if escalation_recall < 1.0:
            print(f"  Blocker: escalation recall {100*escalation_recall:.1f}% below 100% threshold")

    return {
        "overall_accuracy": correct / total,
        "routine_accuracy": routine_accuracy,
        "escalation_recall": escalation_recall,
        "escalation_precision": escalation_precision,
        "go": go,
        "per_category": category_counts,
        "results": results,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Email Triage MVP - FDE Mock Engagement")
    parser.add_argument("--demo", action="store_true", help="Process synthetic demo emails")
    parser.add_argument("--eval", action="store_true", help="Run golden set evaluation")
    parser.add_argument("--email", type=str, help="Process a single email (body text)")
    parser.add_argument("--output-json", action="store_true", help="Output results as JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose evaluation output")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    if args.email:
        result = process_email("cli-input", args.email)
        if args.output_json:
            print(json.dumps({
                "category": result.classification.category,
                "confidence": result.classification.confidence,
                "reason": result.classification.reason,
                "routed_to": result.routed_to,
                "draft_response": result.draft_response,
            }, indent=2))
        else:
            print(f"\nCategory:   {result.classification.category}")
            print(f"Confidence: {result.classification.confidence:.2f}")
            print(f"Reason:     {result.classification.reason}")
            print(f"Routed to:  {result.routed_to}")
            if result.draft_response:
                print(f"\nDraft response:\n{result.draft_response}")
            else:
                print("\nRouted to human queue - no draft generated")
        return

    if args.eval:
        run_golden_set_eval(verbose=args.verbose)
        return

    if args.demo:
        print("Email Triage MVP - Demo Mode")
        print("=" * 50)
        all_results = []
        for i, email_body in enumerate(DEMO_EMAILS, 1):
            print(f"\n[Email {i}]")
            print(f"Body: {email_body[:80]}...")
            result = process_email(f"demo-{i:02d}", email_body)
            print(f"Category:   {result.classification.category} (confidence: {result.classification.confidence:.2f})")
            print(f"Routed to:  {result.routed_to}")
            if result.draft_response:
                preview = result.draft_response[:120].replace("\n", " ")
                print(f"Draft:      {preview}...")
            else:
                print("Draft:      [None - escalated to human queue]")
            all_results.append(result)

        automated = sum(1 for r in all_results if r.routed_to == "automated")
        print(f"\nSummary: {automated}/{len(all_results)} emails automated, "
              f"{len(all_results) - automated}/{len(all_results)} routed to human queue")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
