"""
Lesson 01-03: Few-Shot and Chain-of-Thought
Phase 01: Prompt and Context Engineering

Three experiments comparing zero-shot, few-shot, and CoT prompting
on a severity classification task. Includes the SDK messages-array
pattern for structured few-shot examples.
"""

import anthropic

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Test tickets covering the full severity range
# ---------------------------------------------------------------------------

TEST_TICKETS = [
    # Clear Critical
    "The entire payment service is down. No transactions are going through for any users.",
    # Clear High
    "Our export to CSV feature is producing incorrect totals. Users cannot reconcile their data.",
    # Ambiguous Medium/High
    "The search results sometimes show duplicates when filtering by date range.",
    # Clear Low
    "The font in the mobile app looks slightly different than the web version.",
    # Ambiguous Critical/High
    "Users in the EU region cannot log in. This has been broken for 30 minutes.",
    # Clear Low
    "How do I change my billing address?",
    # Ambiguous High/Critical
    "Our webhook delivery rate dropped from 99.9% to 60% starting an hour ago.",
]

# Ground truth labels for evaluation (set manually)
GROUND_TRUTH = [
    "Critical",
    "High",
    "Medium",
    "Low",
    "Critical",
    "Low",
    "High",
]

# ---------------------------------------------------------------------------
# Experiment 1: Zero-shot baseline
# ---------------------------------------------------------------------------

ZERO_SHOT_PROMPT = """Classify the severity of this customer support ticket.
Severity levels: Critical, High, Medium, Low.

Definitions:
- Critical: complete outage, data loss, affects all/most users, revenue impact
- High: major feature broken, significant user impact, no workaround
- Medium: partial impact, workaround exists, affects some users
- Low: cosmetic issue, question, feature request, minor inconvenience

Output only the severity level. No explanation.

Ticket: {ticket}"""


def classify_zero_shot(ticket: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        messages=[{
            "role": "user",
            "content": ZERO_SHOT_PROMPT.format(ticket=ticket)
        }]
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Experiment 2: Few-shot (inline examples in prompt)
# ---------------------------------------------------------------------------

FEW_SHOT_PROMPT = """Classify the severity of this customer support ticket.
Severity levels: Critical, High, Medium, Low.

Examples:
Ticket: Our API is returning 500 errors for all requests. Production is down.
Severity: Critical

Ticket: The export to CSV function is producing incorrect totals.
Severity: High

Ticket: The search results sometimes show duplicates.
Severity: Medium

Ticket: Can you add a dark mode option to the app?
Severity: Low

Ticket: Half our users in Asia-Pacific cannot authenticate. Ongoing for 1 hour.
Severity: Critical

Ticket: The mobile notification sound plays twice occasionally.
Severity: Low

Output only the severity level. No explanation.

Ticket: {ticket}"""


def classify_few_shot(ticket: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        messages=[{
            "role": "user",
            "content": FEW_SHOT_PROMPT.format(ticket=ticket)
        }]
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Experiment 3: Chain-of-thought (reasoning before answer)
# ---------------------------------------------------------------------------

COT_SYSTEM = """You are a support ticket triage specialist.

When classifying tickets, reason through these questions:
1. Who is affected: one user, some users, or all/most users?
2. Is core functionality or revenue directly impacted?
3. Is this time-sensitive with no workaround available?

Severity definitions:
- Critical: complete outage, data loss, broad user impact, no workaround
- High: major feature broken, significant impact, limited workaround
- Medium: partial impact, workaround available, affects some users
- Low: cosmetic, question, feature request, minor inconvenience"""

COT_USER_TEMPLATE = """Reason through the 3 triage questions for this ticket,
then output your final answer on a line by itself as: SEVERITY: [level]

Ticket: {ticket}"""


def classify_cot(ticket: str) -> tuple[str, str]:
    """Returns (severity_label, full_reasoning)."""
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system=COT_SYSTEM,
        messages=[{
            "role": "user",
            "content": COT_USER_TEMPLATE.format(ticket=ticket)
        }]
    )
    full_text = response.content[0].text.strip()

    # Extract the severity label from the last line
    label = "Unknown"
    for line in full_text.split("\n"):
        if line.strip().startswith("SEVERITY:"):
            label = line.split(":", 1)[-1].strip()
            break

    return label, full_text


# ---------------------------------------------------------------------------
# Experiment 4: Few-shot using SDK messages array (structured, no inline examples)
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES = [
    ("Our API is returning 500 errors for all requests. Production is down.", "Critical"),
    ("The export to CSV function is producing incorrect totals.", "High"),
    ("The search results sometimes show duplicates.", "Medium"),
    ("Can you add a dark mode option to the app?", "Low"),
    ("Half our users in Asia-Pacific cannot authenticate. Ongoing for 1 hour.", "Critical"),
    ("The mobile notification sound plays twice occasionally.", "Low"),
]


def classify_few_shot_sdk(ticket: str) -> str:
    """
    Few-shot using the messages array pattern.
    Examples are user/assistant turn pairs, keeping them separate from instructions.
    """
    messages = []

    # Add each example as a user/assistant pair
    for example_ticket, example_label in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user",      "content": f"Ticket: {example_ticket}"})
        messages.append({"role": "assistant", "content": example_label})

    # Add the real ticket
    messages.append({"role": "user", "content": f"Ticket: {ticket}"})

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        system=(
            "You are a support ticket triage specialist. "
            "Classify severity: Critical, High, Medium, Low. "
            "Output only the label."
        ),
        messages=messages
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Evaluation: compare all approaches against ground truth
# ---------------------------------------------------------------------------

def evaluate_all() -> None:
    print("=" * 70)
    print("EVALUATION: Zero-shot vs Few-shot vs CoT vs Few-shot (SDK)")
    print("=" * 70)

    results = {
        "zero_shot":      [],
        "few_shot":       [],
        "cot":            [],
        "few_shot_sdk":   [],
    }

    for i, ticket in enumerate(TEST_TICKETS):
        expected = GROUND_TRUTH[i]
        print(f"\nTicket {i+1}: {ticket[:60]}...")
        print(f"  Expected: {expected}")

        zs  = classify_zero_shot(ticket)
        fs  = classify_few_shot(ticket)
        cot_label, _ = classify_cot(ticket)
        fs_sdk = classify_few_shot_sdk(ticket)

        results["zero_shot"].append(zs == expected)
        results["few_shot"].append(fs == expected)
        results["cot"].append(cot_label == expected)
        results["few_shot_sdk"].append(fs_sdk == expected)

        print(f"  Zero-shot:    {zs:10s}  {'OK' if zs == expected else 'WRONG'}")
        print(f"  Few-shot:     {fs:10s}  {'OK' if fs == expected else 'WRONG'}")
        print(f"  CoT:          {cot_label:10s}  {'OK' if cot_label == expected else 'WRONG'}")
        print(f"  Few-shot SDK: {fs_sdk:10s}  {'OK' if fs_sdk == expected else 'WRONG'}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    n = len(TEST_TICKETS)
    for method, correct_list in results.items():
        score = sum(correct_list)
        print(f"  {method:20s}: {score}/{n} ({100*score//n}%)")


# ---------------------------------------------------------------------------
# Demo: Show CoT reasoning for one ticket
# ---------------------------------------------------------------------------

def demo_cot_reasoning() -> None:
    print("\n" + "=" * 70)
    print("DEMO: CoT reasoning trace for an ambiguous ticket")
    print("=" * 70)

    ambiguous = "Our webhook delivery rate dropped from 99.9% to 60% starting an hour ago."
    label, reasoning = classify_cot(ambiguous)

    print(f"Ticket: {ambiguous}")
    print(f"\nFull CoT response:\n{reasoning}")
    print(f"\nExtracted severity: {label}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Lesson 01-03: Few-Shot and Chain-of-Thought")
    print("\nOptions:")
    print("  1. Run full evaluation (all 7 tickets, all 4 methods)")
    print("  2. Demo CoT reasoning trace")
    print("  3. Run both\n")

    choice = input("Choice [1/2/3]: ").strip()

    if choice == "1":
        evaluate_all()
    elif choice == "2":
        demo_cot_reasoning()
    else:
        demo_cot_reasoning()
        evaluate_all()
