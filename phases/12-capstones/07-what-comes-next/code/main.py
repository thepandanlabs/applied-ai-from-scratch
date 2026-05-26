"""
Learning Path Recommender CLI

Maps a learning goal to curriculum artifacts for review, suggests next steps
from a curated reading list, and generates a 4-week practice plan.

Demo mode requires no API calls (uses hardcoded knowledge mapping).
API mode uses Claude for open-ended goal interpretation.

Usage:
    python main.py --demo "get better at eval-driven development"
    python main.py --demo "prepare for FDE interviews"
    python main.py --demo "understand agent patterns better"
    python main.py --demo --list-goals       # Show all supported demo goals
    python main.py --goal "custom goal here" # Uses Claude (requires API key)
    python main.py --self-assess             # 5-pillar self-assessment prompt
"""

import argparse
import os
import sys
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Curated artifact knowledge base (curriculum-aligned)
# ---------------------------------------------------------------------------
CURRICULUM_ARTIFACTS = {
    "context_engineering": {
        "phase": "01",
        "artifacts": [
            ("prompt-system-prompt-template.md", "P01-02", "System prompt structure template"),
            ("skill-few-shot-design-guide.md", "P01-04", "Few-shot example selection and design guide"),
            ("prompt-chain-of-thought-template.md", "P01-06", "Chain-of-thought prompt template"),
            ("skill-context-window-budget.md", "P01-08", "Context window budget planning guide"),
        ],
        "description": "Prompt design, context window management, few-shot patterns",
    },
    "rag": {
        "phase": "02",
        "artifacts": [
            ("skill-chunking-strategy-guide.md", "P02-02", "Document chunking strategy decision guide"),
            ("skill-retrieval-quality-checklist.md", "P02-04", "Retrieval quality diagnostic checklist"),
            ("prompt-rag-system-prompt-template.md", "P02-06", "RAG system prompt with hallucination guardrails"),
            ("eval-ragas-baseline-template.md", "P02-08", "RAGAS evaluation baseline template"),
            ("runbook-rag-production-pipeline.md", "P02-10", "RAG production pipeline operational runbook"),
        ],
        "description": "Retrieval, chunking, RAGAS evaluation, production RAG pipelines",
    },
    "tools_mcp": {
        "phase": "03",
        "artifacts": [
            ("skill-tool-design-guide.md", "P03-03", "Tool interface design principles"),
            ("skill-mcp-server-template.md", "P03-06", "MCP server implementation template"),
        ],
        "description": "Tool calling, MCP integration, function design",
    },
    "agents": {
        "phase": "04",
        "artifacts": [
            ("skill-agent-pattern-guide.md", "P04-02", "Agent pattern selection and design guide"),
            ("skill-agent-safety-checklist.md", "P04-05", "Agent safety and guardrail checklist"),
            ("prompt-agent-system-prompt.md", "P04-08", "Agent system prompt with tool use instructions"),
            ("runbook-agent-deployment.md", "P04-12", "Agent deployment and operations runbook"),
        ],
        "description": "Agent patterns, multi-agent, safety, deployment",
    },
    "evaluation": {
        "phase": "05",
        "artifacts": [
            ("skill-golden-set-builder.md", "P05-02", "Golden set construction methodology"),
            ("eval-llm-as-judge-template.md", "P05-04", "LLM-as-judge evaluation template"),
            ("prompt-go-no-go-decision.md", "P05-06", "Go/no-go decision framework with evidence template"),
            ("skill-eval-driven-dev-guide.md", "P05-09", "Eval-driven development workflow guide"),
        ],
        "description": "Golden sets, LLM-as-judge, go/no-go decisions, eval-driven development",
    },
    "shipping": {
        "phase": "06",
        "artifacts": [
            ("service-fastapi-ai-template.md", "P06-02", "FastAPI AI service template with health checks"),
            ("skill-docker-ai-deployment.md", "P06-04", "Docker deployment pattern for AI services"),
        ],
        "description": "FastAPI services, Docker, production deployment patterns",
    },
    "observability": {
        "phase": "07",
        "artifacts": [
            ("skill-langfuse-integration-guide.md", "P07-03", "Langfuse tracing integration guide"),
            ("prompt-genai-otel-template.md", "P07-05", "GenAI OpenTelemetry instrumentation template"),
        ],
        "description": "Langfuse, OpenTelemetry, gen_ai.* conventions, tracing",
    },
    "security": {
        "phase": "08",
        "artifacts": [
            ("skill-input-validation-guide.md", "P08-02", "LLM input validation and sanitization guide"),
            ("prompt-prompt-injection-defense.md", "P08-05", "Prompt injection defense patterns"),
        ],
        "description": "Input validation, prompt injection, guardrails",
    },
    "fde": {
        "phase": "11",
        "artifacts": [
            ("skill-scoping-interview-guide.md", "P11-02", "Scoping interview guide for AI engagements"),
            ("prompt-ai-spec-template.md", "P11-03", "AI Spec template for converting vague asks to measurable designs"),
            ("prompt-pattern-decision-guide.md", "P11-04", "Pattern selection decision guide with scoring"),
            ("skill-demo-prep-checklist.md", "P11-05", "Demo preparation checklist for real customer data"),
            ("skill-handoff-package-template.md", "P11-09", "Four-document handoff package template"),
            ("prompt-stakeholder-communication.md", "P11-10", "Stakeholder communication template"),
        ],
        "description": "FDE engagement lifecycle, scoping, demos, handoffs, communication",
    },
}

CURATED_READING = {
    "evaluation": [
        ("Your AI Product Needs Evals", "Hamel Husain", "hamel.dev", "Grounded in production systems; the clearest argument for why evals are not optional"),
        ("Anthropic evals documentation", "Anthropic", "docs.anthropic.com/en/docs/test-and-evaluate", "Model-graded evals and constitutional AI evaluation patterns"),
        ("RAGAS documentation", "RAGAS team", "docs.ragas.io", "The framework used in this curriculum; the docs explain the metrics precisely"),
    ],
    "agents": [
        ("Building effective agents", "Anthropic", "anthropic.com/engineering/building-effective-agents", "The most useful agent patterns guide from the team that builds the models"),
        ("Latent Space podcast", "Various", "latent.space", "Filter for episodes on production agent systems; skip the hype episodes"),
        ("applied-llms.org", "Community", "applied-llms.org", "Curated applied engineering; low noise ratio"),
    ],
    "rag": [
        ("applied-llms.org RAG section", "Community", "applied-llms.org", "Production RAG patterns with measured results"),
        ("Anthropic's contextual retrieval post", "Anthropic", "anthropic.com/news/contextual-retrieval", "Specific technique for improving retrieval quality; has measured results"),
        ("RAGAS documentation", "RAGAS team", "docs.ragas.io", "Evaluation metrics for retrieval quality"),
    ],
    "fde": [
        ("Latent Space podcast", "Various", "latent.space", "Episodes featuring FDEs and AE at AI companies; filter for customer deployment stories"),
        ("Anthropic release notes", "Anthropic", "anthropic.com/changelog", "What actually shipped vs. what was announced; read the notes not the blog posts"),
        ("Hamel Husain's blog", "Hamel Husain", "hamel.dev", "Production deployment and evaluation; written by someone who does the work"),
    ],
    "general": [
        ("Anthropic release notes", "Anthropic", "anthropic.com/changelog", "What actually changed in the models and APIs you use"),
        ("Latent Space podcast", "Various", "latent.space", "High-signal interviews with engineers building production systems"),
        ("Hamel Husain's blog", "Hamel Husain", "hamel.dev", "Applied engineering grounded in measured production results"),
        ("applied-llms.org", "Community", "applied-llms.org", "Curated applied engineering content with low noise ratio"),
    ],
}

PRACTICE_PLANS = {
    "evaluation": [
        "Week 1: Rebuild the Phase 05 golden set builder from scratch on a new use case you have not worked on before",
        "Week 2: Write an LLM-as-judge prompt for your new use case. Test its agreement rate against your own judgments on 20 examples.",
        "Week 3: Make 3 prompt changes to an existing project. Use your eval to decide which to keep. Document the go/no-go with evidence.",
        "Week 4: Write a full eval report: golden set, metrics, LLM-as-judge results, go/no-go decision. Treat it as if a customer will read it.",
    ],
    "agents": [
        "Week 1: Rebuild the Phase 04 single-agent pattern with a new tool set. Focus on the system prompt and tool definitions.",
        "Week 2: Add a golden set eval for your agent. What are the 10 cases where the agent should succeed? Measure it.",
        "Week 3: Implement a multi-agent variant of the same use case. Compare quality and latency against the single-agent version.",
        "Week 4: Write the production runbook for your agent. Include 5 common failures and their fixes. Test the runbook by simulating each failure.",
    ],
    "rag": [
        "Week 1: Build a RAG pipeline for a new document set you have not used before. Measure retrieval precision at 5 and 10 results.",
        "Week 2: Run a RAGAS evaluation. Identify the weakest metric. Change one thing (chunking, retrieval k, or system prompt) and measure again.",
        "Week 3: Implement a second chunking strategy for the same documents. Compare retrieval quality between the two strategies.",
        "Week 4: Write the production runbook for your RAG system. Include the 5 most common failures you encountered during weeks 1-3.",
    ],
    "fde": [
        "Week 1: Take any project from the curriculum and write an AI Spec for it as if a new customer had described it vaguely. Practice the discovery-to-spec conversion.",
        "Week 2: Run a mock discovery call with a colleague (or yourself). Use the scoping interview guide. Produce an AI Spec from the output.",
        "Week 3: Build a demo-ready version of any Phase 12 capstone. Apply the demo prep checklist. Run it on a data sample that is not the golden set.",
        "Week 4: Write the four-document handoff package for any project you have built. Test it: can someone else follow the runbook without asking you questions?",
    ],
    "general": [
        "Week 1: Pick one Phase 12 capstone you found hardest. Rebuild the core component from scratch without looking at your notes.",
        "Week 2: Add evaluation (golden set + go/no-go) to a project that currently has no formal eval.",
        "Week 3: Write a handoff runbook for a project you built. Give it to a colleague and ask them to run the health check without your help.",
        "Week 4: Complete the 5-pillar self-assessment. Identify your weakest pillar. Plan one specific project to strengthen it.",
    ],
}

# Goal keyword mapping to curriculum areas
GOAL_KEYWORDS = {
    "evaluation": ["eval", "evaluation", "golden set", "llm-as-judge", "measure", "quality", "go/no-go"],
    "agents": ["agent", "agents", "multi-agent", "tool use", "function calling", "orchestration"],
    "rag": ["rag", "retrieval", "chunking", "embeddings", "vector", "knowledge base"],
    "fde": ["fde", "forward-deployed", "scoping", "handoff", "customer", "engagement", "interview"],
    "shipping": ["ship", "deploy", "deployment", "production", "fastapi", "docker", "service"],
    "observability": ["observability", "tracing", "monitoring", "langfuse", "opentelemetry"],
    "security": ["security", "guardrails", "injection", "safety", "validation"],
    "context_engineering": ["prompt", "context", "system prompt", "few-shot", "chain of thought"],
}

SELF_ASSESSMENT = """
5-Pillar Self-Assessment: Applied AI Engineering

Complete each statement. Be specific - no adjectives without artifacts.
If you cannot complete a statement with evidence, that is your next learning priority.

---

PILLAR 1: Context Engineering
"I can now: design a system prompt for a multi-step task, set a token budget,
use few-shot examples to shift model behavior, and diagnose a prompt that is
failing its quality target."

Evidence I have for this:
  - Artifact I built: _______________
  - Specific metric I measured: _______________
  - Project where I applied this: _______________

---

PILLAR 2: Retrieval and RAG
"I can now: choose a chunking strategy for a given document type, build a
retrieval pipeline, run a RAGAS evaluation, and interpret the results to
decide whether retrieval quality is good enough to deploy."

Evidence I have for this:
  - Artifact I built: _______________
  - RAGAS metric I measured and its value: _______________
  - Go/no-go decision I made with evidence: _______________

---

PILLAR 3: Agents
"I can now: select between a router, single agent, and multi-agent based on
requirements, implement a tool-using agent with safe boundaries, and measure
whether the agent is meeting its quality target."

Evidence I have for this:
  - Pattern I chose and the reason: _______________
  - Safety constraint I implemented: _______________
  - Eval result that justified the deployment: _______________

---

PILLAR 4: AI Evaluation
"I can now: build a golden set for a new use case, design an LLM-as-judge
evaluation, make a go/no-go decision with documented evidence, and set up
monitoring to detect post-deployment drift."

Evidence I have for this:
  - Golden set I built (size, use case): _______________
  - LLM-as-judge agreement rate I measured: _______________
  - Go/no-go decision I documented: _______________

---

PILLAR 5: Deployment and FDE Skills
"I can now: scope an AI engagement from a vague ask to a measurable AI spec,
deploy a service with Docker and FastAPI, produce a four-part handoff package,
and measure business impact against defined success criteria."

Evidence I have for this:
  - AI Spec I produced: _______________
  - Handoff artifact I completed: _______________
  - Business metric I defined and measured: _______________

---

After completing: identify your 2 weakest pillars.
Those are the first two items in your 90-day plan.
"""


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def detect_goal_areas(goal_text: str) -> list[str]:
    """Map goal text to curriculum areas using keyword matching."""
    goal_lower = goal_text.lower()
    matched = []
    for area, keywords in GOAL_KEYWORDS.items():
        if any(kw in goal_lower for kw in keywords):
            matched.append(area)
    return matched if matched else ["general"]


def build_demo_plan(goal: str) -> str:
    areas = detect_goal_areas(goal)
    primary_area = areas[0]

    lines = [
        f"Learning Goal: {goal}",
        "",
    ]

    # Artifacts to review
    lines.append("Review these curriculum artifacts first:")
    for area in areas[:2]:  # Top 2 matched areas
        if area in CURRICULUM_ARTIFACTS:
            for artifact_name, location, description in CURRICULUM_ARTIFACTS[area]["artifacts"][:3]:
                lines.append(f"  - {artifact_name} ({location}): {description}")
    lines.append("")

    # Reading suggestions
    reading_key = primary_area if primary_area in CURATED_READING else "general"
    lines.append("Three next steps:")
    readings = CURATED_READING[reading_key][:3]
    for i, (title, author, url, reason) in enumerate(readings, 1):
        lines.append(f"  {i}. Read: \"{title}\" - {author} ({url})")
        lines.append(f"     Why: {reason}")
    lines.append("")

    # Practice plan
    plan_key = primary_area if primary_area in PRACTICE_PLANS else "general"
    lines.append("4-Week Practice Plan:")
    for week_desc in PRACTICE_PLANS[plan_key]:
        lines.append(f"  {week_desc}")
    lines.append("")

    # New tool checklist reminder
    lines.append("When a new framework or model appears relevant to this goal:")
    lines.append("  1. Problem check: Does it solve a problem I actually have?")
    lines.append("  2. Foundation check: Does it replace a foundation or add surface area?")
    lines.append("  3. Evidence check: Is there a production case study, not just a benchmark?")
    lines.append("  4. Cost check: What does adoption actually cost?")
    lines.append("  5. Replace check: Is there measured evidence it is better than what I have?")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Learning Path Recommender")
    parser.add_argument("goal", nargs="?", help="Learning goal (quoted string)")
    parser.add_argument("--demo", action="store_true", help="Demo mode (no API key needed)")
    parser.add_argument("--self-assess", action="store_true", help="Print 5-pillar self-assessment")
    parser.add_argument("--list-goals", action="store_true", help="List supported demo goal areas")
    args = parser.parse_args()

    if args.list_goals:
        print("Supported learning goal areas (keyword examples):")
        for area, keywords in GOAL_KEYWORDS.items():
            print(f"  {area:<25} keywords: {', '.join(keywords[:3])}")
        return

    if args.self_assess:
        print(SELF_ASSESSMENT)
        return

    if not args.goal:
        parser.print_help()
        print("\nExample:")
        print("  python main.py --demo 'get better at eval-driven development'")
        print("  python main.py --demo 'prepare for FDE interviews'")
        print("  python main.py --self-assess")
        sys.exit(1)

    goal = args.goal

    if args.demo:
        output = build_demo_plan(goal)
        print(output)
        return

    # API mode: use Claude for open-ended goals
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("API mode requires ANTHROPIC_API_KEY. Use --demo for no-key mode.")
        sys.exit(1)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        MODEL = "claude-3-5-haiku-20241022"

        # Get the demo plan as structured context, then have Claude enhance it
        demo_context = build_demo_plan(goal)

        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system="""You are a learning coach for applied AI engineers.
You help engineers create specific, actionable learning plans based on their goals.
Be concrete and direct. No generic advice. Suggest specific artifacts, projects, and sources.
Do not use em dashes. Use colons, commas, or hyphens instead.""",
            messages=[{
                "role": "user",
                "content": f"""My learning goal: {goal}

Here is a structured plan based on the curriculum I completed:

{demo_context}

Please enhance this plan with:
1. One specific project I could build this week (buildable in 2-4 hours, tests the goal directly)
2. One thing to specifically watch for that indicates I am making progress
3. One common trap to avoid for this learning area

Keep each response to 3-4 sentences maximum. Be specific, not general."""
            }]
        )
        print(demo_context)
        print("\n--- Enhanced Plan (Claude) ---")
        print(response.content[0].text)

    except ImportError:
        print("anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)


if __name__ == "__main__":
    main()
