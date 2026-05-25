"""
Lesson 05-02: Error Analysis First
A structured error analysis tool: sample outputs, annotate failure categories, build a taxonomy.

Run with: python main.py
Run non-interactive demo: python main.py --demo
Run from a log file: python main.py --log-file outputs.jsonl --sample 30
"""

import json
import random
import argparse
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Sample dataset (hardcoded so you can run without a live system)
# ---------------------------------------------------------------------------

SAMPLE_OUTPUTS = [
    {
        "input": "What is the PTO accrual rate for full-time employees?",
        "output": "Full-time employees accrue 1.5 days of PTO per month, totaling 18 days per year.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:00:00Z"},
    },
    {
        "input": "Can I carry over unused PTO to next year?",
        "output": "I'm not a lawyer and this varies by state, but generally speaking, the policy allows up to 5 days of PTO rollover. You should consult HR directly to confirm your specific situation.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:02:00Z"},
    },
    {
        "input": "What is the FSA contribution limit this year?",
        "output": "The FSA contribution limit is $3,050 per year.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:04:00Z"},
    },
    {
        "input": "How do I submit an expense report?",
        "output": "Log in to the expense portal and fill out the form with your receipts.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:06:00Z"},
    },
    {
        "input": "What is the CEO's salary?",
        "output": "I'm not able to provide information about individual employee compensation. Please contact HR for any compensation-related questions.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:08:00Z"},
    },
    {
        "input": "How many sick days do I get per year?",
        "output": "Employees receive 10 sick days per year, which reset on January 1st.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:10:00Z"},
    },
    {
        "input": "Does the company match 401k contributions?",
        "output": "I want to note that benefits can change and you should verify this with HR, but as of last year the company matches 4% of your salary for 401k contributions, up to the IRS limit.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:12:00Z"},
    },
    {
        "input": "What is the parental leave policy?",
        "output": "New parents receive 12 weeks of paid parental leave, available to all employees regardless of gender.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:14:00Z"},
    },
    {
        "input": "Can I work remotely full-time?",
        "output": "The company has a hybrid policy requiring 2 days in office per week. Fully remote arrangements require manager and HR approval.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:16:00Z"},
    },
    {
        "input": "What health insurance plans are available?",
        "output": "We offer three plans: Bronze, Silver, and Gold. Bronze has the lowest premium. Silver is the most popular. Gold has the highest coverage. You should review the plan documents on the benefits portal for exact costs.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:18:00Z"},
    },
    {
        "input": "How do I request a leave of absence?",
        "output": "Submit form HR-22 to your manager, then to HR, at least 30 days before the leave starts.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:20:00Z"},
    },
    {
        "input": "What is the dental coverage limit per year?",
        "output": "The annual dental benefit maximum is $2,000 per covered person.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:22:00Z"},
    },
    {
        "input": "Does the company pay for certifications?",
        "output": "Yes, the company reimburses up to $2,500 per year for job-related certifications and training. Approval from your manager is required before enrollment.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:24:00Z"},
    },
    {
        "input": "When is open enrollment for benefits?",
        "output": "Open enrollment typically runs in November, but I'm not certain of the exact dates this year. Please check the HR portal or contact HR directly for the current schedule.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:26:00Z"},
    },
    {
        "input": "What is the performance review cycle?",
        "output": "Reviews are conducted annually in Q4, with mid-year check-ins in Q2.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:28:00Z"},
    },
    {
        "input": "How much does the company contribute to the HSA?",
        "output": "Company HSA contribution: $500 for individual coverage, $1,000 for family coverage.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:30:00Z"},
    },
    {
        "input": "Can I use my FSA for gym memberships?",
        "output": "Generally FSA funds cannot be used for gym memberships unless prescribed by a doctor for a specific medical condition. Under IRS rules, gyms are typically considered a general health expense, not a qualified medical expense. Note: policies differ by plan, so check your FSA plan documents.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:32:00Z"},
    },
    {
        "input": "What is the company's bereavement leave policy?",
        "output": "3 days for immediate family, 1 day for extended family.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:34:00Z"},
    },
    {
        "input": "How do I update my emergency contact information?",
        "output": "Log in to Workday, go to Personal Information, then Emergency Contacts, and update your details there.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:36:00Z"},
    },
    {
        "input": "What is the company's dress code policy?",
        "output": "Business casual is the standard. Client-facing days may require business professional attire. Our competitors at Acme Corp have a stricter policy, but we believe comfort improves productivity.",
        "metadata": {"model": "claude-opus-4-5", "timestamp": "2025-05-01T10:38:00Z"},
    },
]

# Pre-computed annotations for the demo mode (so it runs without user input)
DEMO_ANNOTATIONS = [
    {"category": "correct", "note": ""},
    {"category": "unnecessary_caveat", "note": "Correct answer buried under caveats"},
    {"category": "wrong_fact", "note": "FSA limit is $2,750 not $3,050"},
    {"category": "incomplete", "note": "Missing: where to find the portal, manager approval step"},
    {"category": "refused", "note": "Correct refusal but could redirect more helpfully"},
    {"category": "correct", "note": ""},
    {"category": "unnecessary_caveat", "note": "Correct but hedged unnecessarily"},
    {"category": "correct", "note": ""},
    {"category": "correct", "note": ""},
    {"category": "incomplete", "note": "Missing: cost information that was asked about"},
    {"category": "correct", "note": ""},
    {"category": "correct", "note": ""},
    {"category": "correct", "note": ""},
    {"category": "unnecessary_caveat", "note": "Knows the answer but hedges"},
    {"category": "correct", "note": ""},
    {"category": "correct", "note": ""},
    {"category": "unnecessary_caveat", "note": "Over-qualified a clear policy"},
    {"category": "correct", "note": ""},
    {"category": "correct", "note": ""},
    {"category": "hallucination", "note": "Referenced a competitor (Acme Corp) not in the knowledge base"},
]


# ---------------------------------------------------------------------------
# Sampler
# ---------------------------------------------------------------------------

def sample_outputs(log_path: str, n: int = 30, seed: int = 42) -> list[dict]:
    """Sample N outputs from a JSON lines log file."""
    path = Path(log_path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")
    with open(path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    random.seed(seed)
    return random.sample(lines, min(n, len(lines)))


# ---------------------------------------------------------------------------
# Annotation CLI
# ---------------------------------------------------------------------------

PREDEFINED_CATEGORIES = [
    "correct",
    "wrong_fact",
    "incomplete",
    "unnecessary_caveat",
    "refused",
    "format_mismatch",
    "hallucination",
    "off_topic",
    "other",
]


def annotate_outputs(outputs: list[dict]) -> list[dict]:
    """Interactive CLI for annotating outputs with failure categories."""
    print(f"\nAnnotating {len(outputs)} outputs.")
    print("Type a category name or press Enter to use the last category.")
    print(f"Predefined categories: {', '.join(PREDEFINED_CATEGORIES)}\n")

    annotations = []
    last_category = ""

    for i, item in enumerate(outputs):
        print(f"\n{'='*60}")
        print(f"Case {i+1}/{len(outputs)}")
        print(f"INPUT:  {item['input']}")
        print(f"OUTPUT: {item['output']}")
        print(f"{'='*60}")

        while True:
            prompt = f"Category [{last_category}]: " if last_category else "Category: "
            raw = input(prompt).strip().lower()
            category = raw if raw else last_category
            if category:
                last_category = category
                break
            print("  (category required)")

        note = input("Note (optional): ").strip()

        annotations.append(
            {
                "input": item["input"],
                "output": item["output"],
                "category": category,
                "note": note,
                "metadata": item.get("metadata", {}),
            }
        )

    return annotations


def demo_annotate(outputs: list[dict]) -> list[dict]:
    """
    Non-interactive demo mode: applies pre-computed annotations.
    Use this to see the tool's output without going through the CLI.
    """
    annotations = []
    for item, demo in zip(outputs, DEMO_ANNOTATIONS):
        annotations.append(
            {
                "input": item["input"],
                "output": item["output"],
                "category": demo["category"],
                "note": demo["note"],
                "metadata": item.get("metadata", {}),
            }
        )
    return annotations


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_annotations(annotations: list[dict], path: str) -> None:
    """Save annotations to a JSON file."""
    with open(path, "w") as f:
        json.dump(annotations, f, indent=2)
    print(f"\nAnnotations saved to {path}")


def load_annotations(path: str) -> list[dict]:
    """Load saved annotations from a JSON file."""
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Taxonomy reporter
# ---------------------------------------------------------------------------

def print_taxonomy(annotations: list[dict]) -> None:
    """Print a frequency table and example inputs per failure category."""
    counts = Counter(a["category"] for a in annotations)
    total = len(annotations)

    print(f"\nFailure Taxonomy ({total} cases annotated)")
    print(f"{'Category':<25} {'Count':<8} {'%':<8} {'Example input'}")
    print("-" * 90)

    for category, count in counts.most_common():
        examples = [a["input"] for a in annotations if a["category"] == category]
        print(f"{category:<25} {count:<8} {count/total*100:<8.1f} {examples[0][:45]}")

    print()
    failures = [a for a in annotations if a["category"] != "correct"]
    if failures:
        print(f"Top failure category: {counts.most_common()[1][0] if counts.most_common()[0][0] == 'correct' else counts.most_common()[0][0]}")
        print(f"Failure rate: {len(failures)/total*100:.1f}%")

    print("\nActionable next steps:")
    for category, count in counts.most_common():
        if category == "correct":
            continue
        print(f"  [{category}] ({count} cases) -> write a targeted test case and scorer for this failure mode")


def check_saturation(annotations: list[dict], window: int = 10) -> None:
    """
    Check whether the last `window` annotations introduced any new categories.
    This is the saturation signal: if no new categories in the last window, stop sampling.
    """
    if len(annotations) < window * 2:
        print(f"\nSaturation check: need at least {window*2} annotations (have {len(annotations)})")
        return

    early_categories = {a["category"] for a in annotations[:-window]}
    late_categories = {a["category"] for a in annotations[-window:]}
    new_in_late = late_categories - early_categories

    if new_in_late:
        print(f"\nSaturation check: NOT saturated. Last {window} outputs introduced new categories: {new_in_late}")
        print("Recommendation: continue annotating.")
    else:
        print(f"\nSaturation check: SATURATED. Last {window} outputs added no new categories.")
        print("Recommendation: stop sampling. Your taxonomy is stable.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 05-02: Structured error analysis")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode (no user input required, uses pre-computed annotations)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to a JSON lines log file to sample from",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=20,
        help="Number of outputs to sample (default: 20)",
    )
    parser.add_argument(
        "--annotations-file",
        type=str,
        default="annotations.json",
        help="Path to save/load annotations (default: annotations.json)",
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Load existing annotations instead of running a new session",
    )
    args = parser.parse_args()

    # Load or sample outputs
    if args.load:
        print(f"Loading annotations from {args.annotations_file}")
        annotations = load_annotations(args.annotations_file)
    else:
        if args.log_file:
            print(f"Sampling {args.sample} outputs from {args.log_file}...")
            outputs = sample_outputs(args.log_file, n=args.sample)
        else:
            print(f"Using built-in sample dataset ({len(SAMPLE_OUTPUTS)} outputs)")
            outputs = SAMPLE_OUTPUTS[: args.sample]

        # Annotate
        if args.demo:
            print("\n[DEMO MODE] Applying pre-computed annotations...")
            annotations = demo_annotate(outputs)
        else:
            annotations = annotate_outputs(outputs)

        save_annotations(annotations, args.annotations_file)

    # Report
    print_taxonomy(annotations)
    check_saturation(annotations)


if __name__ == "__main__":
    main()
