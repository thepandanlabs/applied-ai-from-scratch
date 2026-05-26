"""
StakeholderTranslator: rewrite technical AI project updates for
non-technical executive audiences, then score the output.

Usage:
    python main.py --demo
    python main.py --update "your technical update text here"
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"


@dataclass
class TranslationResult:
    original: str
    translated: str
    clarity_score: float
    business_relevance_score: float
    jargon_score: float              # 0 = no jargon, 1 = full jargon
    improvements: list[str]


TRANSLATE_PROMPT = """You are an expert at translating technical AI project updates into clear, business-focused language for non-technical stakeholders.

The audience is a VP or C-level executive who:
- Has no background in machine learning or software engineering
- Cares about business outcomes: time saved, cost reduced, risk managed, users helped
- Makes decisions based on confidence and clarity, not technical details
- Will escalate or block a project if they feel uncertain or out of the loop

Technical update to translate:
{update}

Translate this into a stakeholder-ready update. Then score the original and your translation.

Return a JSON object:
{{
  "translation": "<your stakeholder-friendly rewrite of the update>",
  "clarity_score": <float 0.0-1.0: how clear is the translated version to a non-technical reader>,
  "business_relevance_score": <float 0.0-1.0: does it speak to business outcomes and impact?>,
  "jargon_score": <float 0.0-1.0: how much technical jargon remains? 0=none, 1=all jargon>,
  "improvements": ["<specific change 1>", "<specific change 2>", "<specific change 3>"]
}}

Translation rules:
- Replace every metric with its business meaning (e.g., "accuracy 0.84" becomes "correctly handles 84% of requests")
- Replace "hallucination" with a concrete description of what happens and how often
- Replace infrastructure terms (RAG, embedding, p95, tokens, RAGAS, F1, precision, recall) with plain-language equivalents
- Keep the update under 150 words
- End with either a concrete status (on track / at risk) or a specific ask
- Do not introduce uncertainty you did not have - be honest about risks using plain language
- Never start with "I hope this email finds you well" or similar filler

Return only the JSON object."""


def translate_update(technical_update: str) -> TranslationResult:
    """Translate a technical update into stakeholder-ready language and score it."""
    prompt = TRANSLATE_PROMPT.format(update=technical_update)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    data = json.loads(raw)

    return TranslationResult(
        original=technical_update,
        translated=data["translation"],
        clarity_score=float(data["clarity_score"]),
        business_relevance_score=float(data["business_relevance_score"]),
        jargon_score=float(data["jargon_score"]),
        improvements=data.get("improvements", []),
    )


def print_translation(result: TranslationResult) -> None:
    """Print the original, translation, and scores."""
    print("\n" + "=" * 60)
    print("STAKEHOLDER TRANSLATOR")
    print("=" * 60)

    print("\n--- ORIGINAL (TECHNICAL) ---")
    print(result.original)

    print("\n--- TRANSLATED (STAKEHOLDER-READY) ---")
    print(result.translated)

    print("\n--- SCORES ---")
    print(f"Clarity:            {result.clarity_score:.2f} / 1.0")
    print(f"Business relevance: {result.business_relevance_score:.2f} / 1.0")
    print(f"Jargon remaining:   {result.jargon_score:.2f} / 1.0  (lower is better)")

    if result.improvements:
        print("\n--- KEY CHANGES MADE ---")
        for improvement in result.improvements:
            print(f"  - {improvement}")

    avg_score = (
        result.clarity_score
        + result.business_relevance_score
        + (1.0 - result.jargon_score)
    ) / 3

    print(f"\nOverall translation quality: {avg_score:.2f} / 1.0")
    if avg_score >= 0.80:
        print("STATUS: Ready to send to stakeholders.")
    elif avg_score >= 0.65:
        print("STATUS: Review and refine before sending.")
    else:
        print("STATUS: Needs significant rework.")
    print("=" * 60 + "\n")


DEMO_UPDATES = [
    {
        "name": "Status Update 1: Technical Progress",
        "text": (
            "Completed integration of the hybrid retrieval module with cross-encoder reranking. "
            "RAGAS scores improved: faithfulness 0.82 -> 0.89, answer relevance 0.77 -> 0.85. "
            "Latency p95 is 1.4s, within SLA. Still investigating occasional hallucinations "
            "on edge cases involving multi-hop reasoning over documents > 50 pages."
        ),
    },
    {
        "name": "Status Update 2: Risk Escalation",
        "text": (
            "We identified a risk: the customer's Oracle CRM database does not have an API. "
            "We need to build an ETL pipeline to export data nightly to S3 as a workaround. "
            "This adds approximately 8 engineering days and introduces a data freshness "
            "constraint: the system will only have access to data as of the previous day's "
            "export. This may impact the real-time classification use case."
        ),
    },
    {
        "name": "Status Update 3: Pilot Results",
        "text": (
            "Pilot results for the 4-week support ticket classification evaluation: "
            "precision 0.87, recall 0.83, F1 0.85. Escalation rate dropped from 34% to 18%. "
            "Average time-to-resolution improved from 185s to 62s. "
            "Correlation between model confidence score and task success: 0.71. "
            "Token usage averaging 2,800 tokens per query, within budget."
        ),
    },
]


def run_demo() -> None:
    """Run the translator on three demo technical updates."""
    for item in DEMO_UPDATES:
        print(f"\n{'#' * 60}")
        print(f"  {item['name']}")
        print(f"{'#' * 60}")
        result = translate_update(item["text"])
        print_translation(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="StakeholderTranslator: rewrite technical AI updates for executive audiences"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run on 3 built-in demo technical updates",
    )
    parser.add_argument(
        "--update",
        help="Translate a single technical update (pass as a string)",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.update:
        result = translate_update(args.update)
        print_translation(result)
    else:
        print("Usage:")
        print("  python main.py --demo")
        print("  python main.py --update 'your technical update text'")
        sys.exit(1)


if __name__ == "__main__":
    main()
