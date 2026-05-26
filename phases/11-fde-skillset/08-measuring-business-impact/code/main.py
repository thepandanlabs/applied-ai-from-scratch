"""
ImpactTracker: log model quality and business metrics for an AI pilot,
then translate results into business impact language.

Usage:
    python main.py --demo
    python main.py --from-json interactions.json --baseline baseline.json
"""

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass, field
from statistics import correlation, mean
from typing import Optional

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"


@dataclass
class Interaction:
    interaction_id: str
    timestamp: str
    query: str
    model_response: str
    model_quality_score: float         # eval layer: 0.0 - 1.0
    task_success: bool                 # operational layer: did it accomplish the goal?
    time_to_resolution_seconds: float  # operational: time taken
    escalation_required: bool          # operational: human intervention needed?
    customer_satisfaction_proxy: float # 0.0 - 1.0


@dataclass
class PilotMetrics:
    interactions: list[Interaction] = field(default_factory=list)

    @property
    def avg_model_quality(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(i.model_quality_score for i in self.interactions)

    @property
    def task_success_rate(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(1.0 if i.task_success else 0.0 for i in self.interactions)

    @property
    def escalation_rate(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(1.0 if i.escalation_required else 0.0 for i in self.interactions)

    @property
    def avg_resolution_seconds(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(i.time_to_resolution_seconds for i in self.interactions)

    @property
    def avg_satisfaction(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(i.customer_satisfaction_proxy for i in self.interactions)

    @property
    def quality_success_correlation(self) -> Optional[float]:
        if len(self.interactions) < 3:
            return None
        quality_scores = [i.model_quality_score for i in self.interactions]
        success_scores = [1.0 if i.task_success else 0.0 for i in self.interactions]
        try:
            return correlation(quality_scores, success_scores)
        except Exception:
            return None


QUALITY_SCORE_PROMPT = """You are evaluating the quality of an AI system response in a support ticket context.

Customer query: {query}
AI response: {response}
Expected behavior: {expected}

Score the response on a scale from 0.0 to 1.0:
- 1.0: Fully correct, directly addresses the query, no hallucination, actionable
- 0.7-0.9: Mostly correct with minor gaps or unnecessary hedging
- 0.4-0.6: Partially correct, misses key information, or partially wrong
- 0.1-0.3: Mostly incorrect or misleading
- 0.0: Completely wrong, harmful, or no response

Return only a JSON object:
{{"score": <float 0.0-1.0>, "reason": "<one sentence>"}}"""


def score_model_quality(query: str, response: str, expected: str) -> tuple[float, str]:
    """Score a model response using Claude as judge. Returns (score, reason)."""
    prompt = QUALITY_SCORE_PROMPT.format(
        query=query,
        response=response,
        expected=expected,
    )

    result = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = result.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    data = json.loads(raw)
    return float(data["score"]), data["reason"]


TRANSLATE_PROMPT = """You are translating pilot metrics into business impact language for an executive audience.

Pilot context: {context}
Baseline metrics (before AI): {baseline}
Pilot metrics (with AI): {pilot_metrics}

Translate these results into business impact. Return a JSON object:
{{
  "headline": "<one sentence: the most important result, in business terms>",
  "time_saved_per_month": "<estimated hours or minutes saved per month, with reasoning>",
  "cost_impact": "<estimated cost impact if applicable, or note what data is needed from customer>",
  "error_reduction": "<reduction in errors or escalations, expressed as percentage and absolute number>",
  "renewal_argument": "<one to two sentences a VP would use to justify renewing the contract>"
}}

Use concrete numbers from the metrics provided. Do not hedge with 'potentially' or 'might'.
If a specific calculation requires data not in the metrics (e.g., cost per agent hour), state what data is needed."""


def translate_to_business_impact(
    context: str,
    baseline: dict,
    pilot: PilotMetrics,
) -> dict:
    """Translate pilot metrics into business impact language."""
    pilot_summary = {
        "avg_model_quality": round(pilot.avg_model_quality, 3),
        "task_success_rate": round(pilot.task_success_rate, 3),
        "escalation_rate": round(pilot.escalation_rate, 3),
        "avg_resolution_seconds": round(pilot.avg_resolution_seconds, 1),
        "avg_customer_satisfaction": round(pilot.avg_satisfaction, 3),
        "quality_success_correlation": round(pilot.quality_success_correlation or 0.0, 3),
        "total_interactions": len(pilot.interactions),
    }

    prompt = TRANSLATE_PROMPT.format(
        context=context,
        baseline=json.dumps(baseline, indent=2),
        pilot_metrics=json.dumps(pilot_summary, indent=2),
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    return json.loads(raw)


def print_impact_report(
    pilot: PilotMetrics,
    business_impact: dict,
    baseline: dict,
) -> None:
    """Print the full three-layer impact report."""
    print("\n" + "=" * 60)
    print("PILOT IMPACT REPORT")
    print("=" * 60)

    print("\n--- LAYER 1: TECHNICAL (Model Quality) ---")
    print(f"Avg model quality score:         {pilot.avg_model_quality:.3f}")
    q_corr = pilot.quality_success_correlation
    if q_corr is not None:
        print(f"Quality-to-success correlation:  {q_corr:.3f}")
    print(f"Total interactions evaluated:    {len(pilot.interactions)}")

    print("\n--- LAYER 2: OPERATIONAL (Task Performance) ---")
    print(f"Task success rate: {pilot.task_success_rate:.1%}")
    baseline_success = baseline.get("task_success_rate", 0)
    if baseline_success:
        delta = pilot.task_success_rate - baseline_success
        print(f"  vs. baseline {baseline_success:.1%}  |  delta: {delta:+.1%}")
    print(f"Escalation rate:   {pilot.escalation_rate:.1%}")
    baseline_esc = baseline.get("escalation_rate", 0)
    if baseline_esc:
        delta_esc = pilot.escalation_rate - baseline_esc
        print(f"  vs. baseline {baseline_esc:.1%}  |  delta: {delta_esc:+.1%}")
    print(f"Avg resolution:    {pilot.avg_resolution_seconds:.0f}s")
    baseline_time = baseline.get("avg_resolution_seconds", 0)
    if baseline_time:
        time_delta = pilot.avg_resolution_seconds - baseline_time
        print(f"  vs. baseline {baseline_time:.0f}s  |  delta: {time_delta:+.0f}s")

    print("\n--- LAYER 3: BUSINESS (KPI Impact) ---")
    print(f"Headline:     {business_impact.get('headline', 'N/A')}")
    print(f"Time saved:   {business_impact.get('time_saved_per_month', 'N/A')}")
    print(f"Cost impact:  {business_impact.get('cost_impact', 'N/A')}")
    print(f"Error delta:  {business_impact.get('error_reduction', 'N/A')}")
    print(f"\nRenewal argument:\n  {business_impact.get('renewal_argument', 'N/A')}")

    print("\n" + "=" * 60)


# ---- Demo scenario: support ticket classification pilot ----

DEMO_INTERACTIONS = [
    {
        "id": "t001",
        "query": "How do I reset my password?",
        "response": "To reset your password, go to the login page and click 'Forgot Password'. Enter your email address and you will receive a reset link within 5 minutes.",
        "expected": "Direct the user to the password reset flow on the login page.",
        "base_quality": 0.92,
        "base_success": True,
        "base_time": 45.0,
        "base_escalation": False,
    },
    {
        "id": "t002",
        "query": "I was charged twice for my subscription this month",
        "response": "I understand your concern. Double billing issues need to be reviewed by our billing team. Please contact billing@company.com with your account number.",
        "expected": "Acknowledge the issue and route to the billing team with specific instructions.",
        "base_quality": 0.78,
        "base_success": True,
        "base_time": 62.0,
        "base_escalation": False,
    },
    {
        "id": "t003",
        "query": "How do I export my data?",
        "response": "You can export your data from the Settings menu under 'Account' then 'Data Export'. Choose CSV or JSON format.",
        "expected": "Guide user to Settings > Account > Data Export with format options.",
        "base_quality": 0.88,
        "base_success": True,
        "base_time": 38.0,
        "base_escalation": False,
    },
    {
        "id": "t004",
        "query": "The API is returning 429 errors",
        "response": "A 429 error means you have exceeded your rate limit. Check your current usage in the developer dashboard and consider upgrading your plan or implementing request throttling.",
        "expected": "Explain rate limiting and direct to developer dashboard for usage monitoring.",
        "base_quality": 0.85,
        "base_success": True,
        "base_time": 55.0,
        "base_escalation": False,
    },
    {
        "id": "t005",
        "query": "I need to cancel my enterprise contract immediately",
        "response": "Enterprise contract cancellations require review by our account management team. I am creating an urgent escalation to your dedicated account manager.",
        "expected": "Route to account management - this is outside Tier 1 scope.",
        "base_quality": 0.72,
        "base_success": True,
        "base_time": 120.0,
        "base_escalation": True,
    },
]


def generate_demo_interactions(n: int = 50, seed: int = 42) -> list[Interaction]:
    """Generate n synthetic interactions based on the demo templates."""
    random.seed(seed)
    interactions = []

    for i in range(n):
        template = DEMO_INTERACTIONS[i % len(DEMO_INTERACTIONS)]

        # Add realistic variation
        quality_noise = random.gauss(0, 0.06)
        quality = max(0.0, min(1.0, template["base_quality"] + quality_noise))

        # Task success is strongly correlated with quality
        success_prob = 0.3 + 0.7 * quality
        success = random.random() < success_prob

        # Escalation is correlated with low quality
        esc_base = 0.05 if not template["base_escalation"] else 0.80
        escalation = random.random() < (esc_base + (1.0 - quality) * 0.25)

        # Resolution time: faster if high quality, escalation adds time
        time_noise = random.gauss(0, 8.0)
        base_time = template["base_time"]
        if escalation:
            base_time *= 2.2
        resolution_time = max(10.0, base_time + time_noise + (1.0 - quality) * 30.0)

        # Satisfaction: proxy from success + no escalation + fast resolution
        sat = quality * 0.5 + (0.3 if success else 0.0) + (0.2 if not escalation else 0.0)
        satisfaction = max(0.0, min(1.0, sat + random.gauss(0, 0.05)))

        interactions.append(
            Interaction(
                interaction_id=f"demo-{i:04d}",
                timestamp=f"2025-01-{(i % 28) + 1:02d}",
                query=template["query"],
                model_response=template["response"],
                model_quality_score=quality,
                task_success=success,
                time_to_resolution_seconds=resolution_time,
                escalation_required=escalation,
                customer_satisfaction_proxy=satisfaction,
            )
        )

    return interactions


DEMO_BASELINE = {
    "task_success_rate": 0.68,
    "escalation_rate": 0.34,
    "avg_resolution_seconds": 185.0,
    "avg_satisfaction": 0.61,
    "description": "Manual routing by Tier 1 agents before AI deployment",
}

DEMO_CONTEXT = (
    "4-week pilot of AI-assisted support ticket routing for a B2B SaaS company. "
    "The system classifies and routes Tier 1 support tickets, reducing manual routing "
    "by agents. Measured across 50 real support interactions during the pilot period. "
    "The company has 12 Tier 1 support agents handling approximately 800 tickets per day."
)


def load_interactions_from_json(path: str) -> list[Interaction]:
    """Load interactions from a JSON file."""
    with open(path) as f:
        data = json.load(f)
    return [Interaction(**item) for item in data]


def load_baseline_from_json(path: str) -> dict:
    """Load baseline metrics from a JSON file."""
    with open(path) as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ImpactTracker: measure and translate AI pilot impact"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run on the built-in support ticket demo scenario",
    )
    parser.add_argument("--from-json", help="Load interactions from a JSON file")
    parser.add_argument("--baseline", help="Load baseline metrics from a JSON file")
    args = parser.parse_args()

    if args.demo:
        print("Generating demo interactions...")
        interactions = generate_demo_interactions(n=50)
        pilot = PilotMetrics(interactions=interactions)
        baseline = DEMO_BASELINE
        context = DEMO_CONTEXT

        print(f"Generated {len(interactions)} interactions.")
        print("Translating metrics to business impact...")
        business_impact = translate_to_business_impact(context, baseline, pilot)
        print_impact_report(pilot, business_impact, baseline)

    elif args.from_json:
        if not args.baseline:
            print("Error: --from-json requires --baseline")
            sys.exit(1)
        interactions = load_interactions_from_json(args.from_json)
        baseline = load_baseline_from_json(args.baseline)
        pilot = PilotMetrics(interactions=interactions)
        context = f"AI pilot with {len(interactions)} interactions"

        print(f"Loaded {len(interactions)} interactions.")
        print("Translating metrics to business impact...")
        business_impact = translate_to_business_impact(context, baseline, pilot)
        print_impact_report(pilot, business_impact, baseline)

    else:
        print("Usage:")
        print("  python main.py --demo")
        print("  python main.py --from-json interactions.json --baseline baseline.json")
        sys.exit(1)


if __name__ == "__main__":
    main()
