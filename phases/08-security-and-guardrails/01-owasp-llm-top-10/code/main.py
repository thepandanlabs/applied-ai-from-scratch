"""
Lesson 08-01: Threat Model - OWASP LLM Top 10 (2025)

Interactive threat-modeling script. Walk through each OWASP LLM risk,
rate likelihood and impact, and produce a prioritized risk register.

Run with: python main.py
Run headless: python main.py --app-desc "My app description" --auto
"""

import json
import argparse
from dataclasses import dataclass, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# OWASP LLM Top 10 (2025) definitions
# ---------------------------------------------------------------------------

OWASP_LLM_TOP_10 = [
    {
        "id": "LLM01",
        "name": "Prompt Injection",
        "description": (
            "User input or retrieved content overrides model instructions. "
            "The model treats injected text as trusted commands."
        ),
        "attack_surface": "User turn, retrieved documents, tool outputs, image alt text",
        "unique_to_llm": True,
    },
    {
        "id": "LLM02",
        "name": "Sensitive Information Disclosure",
        "description": (
            "Model reveals PII, API keys, credentials, or other sensitive data "
            "from training data or context window."
        ),
        "attack_surface": "Training data memorization, context window, direct questioning",
        "unique_to_llm": False,
    },
    {
        "id": "LLM03",
        "name": "Supply Chain",
        "description": (
            "Poisoned or backdoored model weights, datasets, or third-party "
            "components introduce vulnerabilities before deployment."
        ),
        "attack_surface": "Model checkpoints, training datasets, pip/npm dependencies, plugins",
        "unique_to_llm": False,
    },
    {
        "id": "LLM04",
        "name": "Data and Model Poisoning",
        "description": (
            "Training or fine-tuning data is manipulated to alter model behavior, "
            "introduce backdoors, or degrade performance on specific inputs."
        ),
        "attack_surface": "Training pipelines, fine-tuning datasets, RAG index",
        "unique_to_llm": False,
    },
    {
        "id": "LLM05",
        "name": "Improper Output Handling",
        "description": (
            "Model output is passed downstream (rendered as HTML, executed as code, "
            "used in shell commands) without sanitization."
        ),
        "attack_surface": "Frontend rendering, code execution, shell integration, SQL generation",
        "unique_to_llm": False,
    },
    {
        "id": "LLM06",
        "name": "Excessive Agency",
        "description": (
            "The model is granted more permissions, tools, or autonomy than the task requires. "
            "A successful injection can take real-world actions."
        ),
        "attack_surface": "Tool use, agent loops, file system access, API calls, email/calendar",
        "unique_to_llm": True,
    },
    {
        "id": "LLM07",
        "name": "System Prompt Leakage",
        "description": (
            "The contents of the system prompt are extracted by the user via direct "
            "questioning or indirect probing over multiple turns."
        ),
        "attack_surface": "Multi-turn conversation, indirect extraction, context confusion",
        "unique_to_llm": False,
    },
    {
        "id": "LLM08",
        "name": "Vector and Embedding Weaknesses",
        "description": (
            "Poisoned embeddings, adversarial retrieval, or index manipulation cause "
            "the retrieval layer to surface malicious or incorrect content."
        ),
        "attack_surface": "Vector index, embedding pipeline, retrieval ranking",
        "unique_to_llm": False,
    },
    {
        "id": "LLM09",
        "name": "Misinformation",
        "description": (
            "Model generates plausible but false information (hallucination) "
            "that users trust and act on."
        ),
        "attack_surface": "Any generation task without ground-truth grounding or citation",
        "unique_to_llm": False,
    },
    {
        "id": "LLM10",
        "name": "Unbounded Consumption",
        "description": (
            "No limits on token usage, API calls, or cost enable denial-of-service "
            "attacks or runaway spend."
        ),
        "attack_surface": "Public endpoints, agent loops, streaming responses",
        "unique_to_llm": False,
    },
]


# ---------------------------------------------------------------------------
# Risk register data structures
# ---------------------------------------------------------------------------

@dataclass
class RiskEntry:
    id: str
    name: str
    description: str
    attack_surface: str
    unique_to_llm: bool
    likelihood: int  # 1=rare, 2=possible, 3=likely
    impact: int      # 1=low, 2=medium, 3=high
    notes: str
    score: int       # likelihood * impact (1-9)
    priority: str    # CRITICAL (7-9), HIGH (5-6), MEDIUM (3-4), LOW (1-2)

    @staticmethod
    def priority_label(score: int) -> str:
        if score >= 7:
            return "CRITICAL"
        elif score >= 5:
            return "HIGH"
        elif score >= 3:
            return "MEDIUM"
        return "LOW"


# ---------------------------------------------------------------------------
# Interactive threat-modeling session
# ---------------------------------------------------------------------------

def rate_risk_interactive(risk: dict) -> RiskEntry:
    """Prompt the engineer to rate likelihood and impact for a single risk."""
    print(f"\n{'='*60}")
    print(f"{risk['id']}: {risk['name']}")
    if risk["unique_to_llm"]:
        print("  [UNIQUE TO LLM SYSTEMS - no traditional web security analogue]")
    print(f"  Description: {risk['description']}")
    print(f"  Attack surface: {risk['attack_surface']}")
    print()

    while True:
        try:
            likelihood = int(input("  Rate LIKELIHOOD (1=rare, 2=possible, 3=likely): ").strip())
            if likelihood in (1, 2, 3):
                break
            print("  Please enter 1, 2, or 3.")
        except ValueError:
            print("  Please enter 1, 2, or 3.")

    while True:
        try:
            impact = int(input("  Rate IMPACT (1=low, 2=medium, 3=high): ").strip())
            if impact in (1, 2, 3):
                break
            print("  Please enter 1, 2, or 3.")
        except ValueError:
            print("  Please enter 1, 2, or 3.")

    notes = input("  Notes (optional, press Enter to skip): ").strip()

    score = likelihood * impact
    priority = RiskEntry.priority_label(score)
    print(f"  => Score: {score}/9  Priority: {priority}")

    return RiskEntry(
        id=risk["id"],
        name=risk["name"],
        description=risk["description"],
        attack_surface=risk["attack_surface"],
        unique_to_llm=risk["unique_to_llm"],
        likelihood=likelihood,
        impact=impact,
        notes=notes,
        score=score,
        priority=priority,
    )


def auto_rate_risk(risk: dict, likelihood: int = 2, impact: int = 2) -> RiskEntry:
    """Rate a risk automatically (for testing/demo mode)."""
    # Assign defaults; LLM01 and LLM06 default to 3x3 = CRITICAL
    if risk["id"] in ("LLM01", "LLM06"):
        likelihood, impact = 3, 3
    elif risk["id"] in ("LLM02", "LLM07"):
        likelihood, impact = 3, 2
    elif risk["id"] in ("LLM09", "LLM05"):
        likelihood, impact = 2, 2
    else:
        likelihood, impact = 1, 2

    score = likelihood * impact
    return RiskEntry(
        id=risk["id"],
        name=risk["name"],
        description=risk["description"],
        attack_surface=risk["attack_surface"],
        unique_to_llm=risk["unique_to_llm"],
        likelihood=likelihood,
        impact=impact,
        notes="Auto-rated for demo",
        score=score,
        priority=RiskEntry.priority_label(score),
    )


# ---------------------------------------------------------------------------
# Risk register output
# ---------------------------------------------------------------------------

def print_risk_register(entries: list[RiskEntry], app_desc: str) -> None:
    """Print the sorted risk register."""
    sorted_entries = sorted(entries, key=lambda r: r.score, reverse=True)

    print("\n" + "=" * 70)
    print("RISK REGISTER")
    print("=" * 70)
    print(f"Application: {app_desc[:65]}")
    print()
    print(f"{'Rank':<5} {'ID':<7} {'Name':<32} {'L':>2} {'I':>2} {'Score':>5}  {'Priority'}")
    print("-" * 70)

    for rank, entry in enumerate(sorted_entries, 1):
        llm_marker = "*" if entry.unique_to_llm else " "
        print(
            f"{rank:<5} {entry.id:<7} {entry.name[:30]:<32} "
            f"{entry.likelihood:>2} {entry.impact:>2} {entry.score:>5}  {entry.priority}{llm_marker}"
        )

    print()
    print("* = Risk unique to LLM systems (no traditional web security analogue)")
    print()

    critical = [e for e in sorted_entries if e.priority == "CRITICAL"]
    high = [e for e in sorted_entries if e.priority == "HIGH"]

    if critical:
        print(f"CRITICAL risks ({len(critical)}) - address before launch:")
        for e in critical:
            print(f"  {e.id}: {e.name}")
            if e.notes and e.notes != "Auto-rated for demo":
                print(f"    Notes: {e.notes}")

    if high:
        print(f"\nHIGH risks ({len(high)}) - address in first sprint:")
        for e in high:
            print(f"  {e.id}: {e.name}")
            if e.notes and e.notes != "Auto-rated for demo":
                print(f"    Notes: {e.notes}")


def save_risk_register(entries: list[RiskEntry], app_desc: str, path: str = "risk_register.json") -> None:
    """Save the risk register to JSON."""
    sorted_entries = sorted(entries, key=lambda r: r.score, reverse=True)
    output = {
        "application": app_desc,
        "owasp_version": "LLM Top 10 2025",
        "risks": [asdict(e) for e in sorted_entries],
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nRisk register saved to {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 08-01: OWASP LLM Top 10 Threat Model")
    parser.add_argument(
        "--app-desc",
        default="",
        help="One-sentence description of your LLM application",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Use default ratings (demo mode, no interactive input)",
    )
    parser.add_argument(
        "--output",
        default="risk_register.json",
        help="Output path for the risk register JSON",
    )
    args = parser.parse_args()

    print("\n=== OWASP LLM Top 10 (2025) Threat Modeling Session ===\n")

    app_desc = args.app_desc
    if not app_desc and not args.auto:
        app_desc = input("Describe your LLM application in one sentence:\n> ").strip()
    elif not app_desc:
        app_desc = "Demo: RAG-based customer support assistant (no auth, public-facing)"

    print(f"\nApplication: {app_desc}")
    print(f"\nYou will rate each of the 10 OWASP LLM risks on:")
    print("  Likelihood: 1=rare, 2=possible, 3=likely")
    print("  Impact:     1=low,  2=medium,   3=high")
    print("  Score = Likelihood x Impact (max 9)")
    print("  Priority: CRITICAL (7-9), HIGH (5-6), MEDIUM (3-4), LOW (1-2)")

    entries: list[RiskEntry] = []

    for risk in OWASP_LLM_TOP_10:
        if args.auto:
            entry = auto_rate_risk(risk)
        else:
            entry = rate_risk_interactive(risk)
        entries.append(entry)

    print_risk_register(entries, app_desc)
    save_risk_register(entries, app_desc, args.output)


if __name__ == "__main__":
    main()
