"""
Portfolio Generator CLI

Reads outputs/index.json (or demo data), groups artifacts by phase and type,
and generates PORTFOLIO.md with a project summary, artifact counts, and a
recommended "feature projects" list.

Usage:
    python main.py --demo --generate                       # Generate from demo data
    python main.py --demo --generate --role fde            # Role-filtered generation
    python main.py --demo --count                          # Count artifacts by type
    python main.py --demo --narrative --project email-triage  # Sample narrative
    python main.py --index ./outputs/index.json --generate    # From real index
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Artifact scoring for feature project selection
# ---------------------------------------------------------------------------
FEATURE_PROJECT_SCORES = {
    "capstone": 10,
    "runbook": 7,
    "eval": 6,
    "service": 5,
    "prompt": 4,
    "skill": 3,
    "guide": 2,
    "template": 2,
}

ROLE_BOOSTS = {
    "fde": {
        "phase": {"11": 3, "12": 2},
        "tags": {"fde": 4, "handoff": 3, "runbook": 2, "scoping": 2},
    },
    "applied-ai-engineer": {
        "phase": {"05": 3, "12": 2, "02": 2, "04": 2},
        "tags": {"eval": 4, "rag": 3, "agents": 2, "observability": 2},
    },
    "solutions-engineer": {
        "phase": {"11": 3, "12": 2},
        "tags": {"communication": 4, "demo": 3, "pattern": 2},
    },
}

# ---------------------------------------------------------------------------
# Demo dataset: mirrors the full curriculum artifact index
# ---------------------------------------------------------------------------
DEMO_ARTIFACTS = [
    # Phase 00
    {"phase": "00", "lesson": "01", "name": "skill-ai-engineer-self-assessment", "type": "skill", "tags": ["mindset", "self-assessment"], "description": "AI engineer competency self-assessment checklist"},
    {"phase": "00", "lesson": "05", "name": "prompt-learning-contract", "type": "prompt", "tags": ["mindset", "learning"], "description": "Learning contract template for the curriculum"},

    # Phase 01
    {"phase": "01", "lesson": "02", "name": "prompt-system-prompt-template", "type": "prompt", "tags": ["prompting", "context"], "description": "System prompt structure template"},
    {"phase": "01", "lesson": "04", "name": "skill-few-shot-design-guide", "type": "skill", "tags": ["prompting", "few-shot"], "description": "Few-shot example selection and design guide"},
    {"phase": "01", "lesson": "06", "name": "prompt-chain-of-thought-template", "type": "prompt", "tags": ["prompting", "reasoning"], "description": "Chain-of-thought prompt template for complex reasoning"},
    {"phase": "01", "lesson": "08", "name": "skill-context-window-budget", "type": "skill", "tags": ["context", "optimization"], "description": "Context window budget planning guide"},

    # Phase 02
    {"phase": "02", "lesson": "02", "name": "skill-chunking-strategy-guide", "type": "skill", "tags": ["rag", "chunking"], "description": "Document chunking strategy decision guide"},
    {"phase": "02", "lesson": "04", "name": "skill-retrieval-quality-checklist", "type": "skill", "tags": ["rag", "retrieval"], "description": "Retrieval quality diagnostic checklist"},
    {"phase": "02", "lesson": "06", "name": "prompt-rag-system-prompt-template", "type": "prompt", "tags": ["rag", "prompting"], "description": "RAG system prompt with hallucination guardrails"},
    {"phase": "02", "lesson": "08", "name": "eval-ragas-baseline-template", "type": "eval", "tags": ["rag", "eval", "ragas"], "description": "RAGAS evaluation baseline template"},
    {"phase": "02", "lesson": "10", "name": "runbook-rag-production-pipeline", "type": "runbook", "tags": ["rag", "production"], "description": "RAG production pipeline operational runbook"},

    # Phase 03
    {"phase": "03", "lesson": "03", "name": "skill-tool-design-guide", "type": "skill", "tags": ["tools", "mcp"], "description": "Tool interface design principles"},
    {"phase": "03", "lesson": "06", "name": "skill-mcp-server-template", "type": "service", "tags": ["mcp", "tools"], "description": "MCP server implementation template"},

    # Phase 04
    {"phase": "04", "lesson": "02", "name": "skill-agent-pattern-guide", "type": "skill", "tags": ["agents", "patterns"], "description": "Agent pattern selection and design guide"},
    {"phase": "04", "lesson": "05", "name": "skill-agent-safety-checklist", "type": "skill", "tags": ["agents", "safety"], "description": "Agent safety and guardrail checklist"},
    {"phase": "04", "lesson": "08", "name": "prompt-agent-system-prompt", "type": "prompt", "tags": ["agents", "prompting"], "description": "Agent system prompt with tool use instructions"},
    {"phase": "04", "lesson": "12", "name": "runbook-agent-deployment", "type": "runbook", "tags": ["agents", "production"], "description": "Agent deployment and operations runbook"},

    # Phase 05
    {"phase": "05", "lesson": "02", "name": "skill-golden-set-builder", "type": "skill", "tags": ["eval", "golden-set"], "description": "Golden set construction methodology"},
    {"phase": "05", "lesson": "04", "name": "eval-llm-as-judge-template", "type": "eval", "tags": ["eval", "llm-judge"], "description": "LLM-as-judge evaluation template"},
    {"phase": "05", "lesson": "06", "name": "prompt-go-no-go-decision", "type": "prompt", "tags": ["eval", "decision"], "description": "Go/no-go decision framework with evidence template"},
    {"phase": "05", "lesson": "09", "name": "skill-eval-driven-dev-guide", "type": "skill", "tags": ["eval", "process"], "description": "Eval-driven development workflow guide"},

    # Phase 06
    {"phase": "06", "lesson": "02", "name": "service-fastapi-ai-template", "type": "service", "tags": ["shipping", "fastapi"], "description": "FastAPI AI service template with health checks"},
    {"phase": "06", "lesson": "04", "name": "skill-docker-ai-deployment", "type": "skill", "tags": ["shipping", "docker"], "description": "Docker deployment pattern for AI services"},

    # Phase 07
    {"phase": "07", "lesson": "03", "name": "skill-langfuse-integration-guide", "type": "skill", "tags": ["observability", "langfuse"], "description": "Langfuse tracing integration guide"},
    {"phase": "07", "lesson": "05", "name": "prompt-genai-otel-template", "type": "prompt", "tags": ["observability", "opentelemetry"], "description": "GenAI OpenTelemetry instrumentation template"},

    # Phase 08
    {"phase": "08", "lesson": "02", "name": "skill-input-validation-guide", "type": "skill", "tags": ["security", "guardrails"], "description": "LLM input validation and sanitization guide"},
    {"phase": "08", "lesson": "05", "name": "prompt-prompt-injection-defense", "type": "prompt", "tags": ["security", "injection"], "description": "Prompt injection defense patterns"},

    # Phase 09
    {"phase": "09", "lesson": "03", "name": "skill-fine-tuning-readiness", "type": "skill", "tags": ["fine-tuning", "decision"], "description": "Fine-tuning readiness assessment checklist"},

    # Phase 10
    {"phase": "10", "lesson": "04", "name": "skill-multimodal-input-guide", "type": "skill", "tags": ["multimodal", "vision"], "description": "Multimodal input design guide"},

    # Phase 11
    {"phase": "11", "lesson": "02", "name": "skill-scoping-interview-guide", "type": "skill", "tags": ["fde", "scoping"], "description": "Scoping interview guide for AI engagements"},
    {"phase": "11", "lesson": "03", "name": "prompt-ai-spec-template", "type": "prompt", "tags": ["fde", "spec"], "description": "AI Spec template for converting vague asks to measurable designs"},
    {"phase": "11", "lesson": "04", "name": "prompt-pattern-decision-guide", "type": "prompt", "tags": ["fde", "pattern"], "description": "Pattern selection decision guide with scoring"},
    {"phase": "11", "lesson": "05", "name": "skill-demo-prep-checklist", "type": "skill", "tags": ["fde", "demo"], "description": "Demo preparation checklist for real customer data"},
    {"phase": "11", "lesson": "08", "name": "skill-business-impact-template", "type": "skill", "tags": ["fde", "metrics"], "description": "Business impact measurement template"},
    {"phase": "11", "lesson": "09", "name": "skill-handoff-package-template", "type": "skill", "tags": ["fde", "handoff"], "description": "Four-document handoff package template"},
    {"phase": "11", "lesson": "10", "name": "prompt-stakeholder-communication", "type": "prompt", "tags": ["fde", "communication"], "description": "Stakeholder communication template for AI projects"},

    # Phase 12 - Capstones
    {"phase": "12", "lesson": "01", "name": "runbook-rag-assistant-production", "type": "runbook", "tags": ["capstone", "rag", "production"], "description": "Production RAG assistant operational runbook"},
    {"phase": "12", "lesson": "02", "name": "runbook-customer-support-agent", "type": "runbook", "tags": ["capstone", "agents", "customer-support"], "description": "Customer support agent deployment runbook"},
    {"phase": "12", "lesson": "03", "name": "skill-sql-agent-safety-guide", "type": "skill", "tags": ["capstone", "sql", "agents"], "description": "Text-to-SQL agent safety and validation guide"},
    {"phase": "12", "lesson": "04", "name": "skill-coding-agent-patterns", "type": "skill", "tags": ["capstone", "agents", "coding"], "description": "Coding automation agent pattern guide"},
    {"phase": "12", "lesson": "05", "name": "runbook-fde-engagement-playbook", "type": "runbook", "tags": ["capstone", "fde", "handoff", "eval"], "description": "FDE mock engagement complete handoff package"},
    {"phase": "12", "lesson": "06", "name": "prompt-portfolio-presentation-guide", "type": "prompt", "tags": ["capstone", "portfolio", "interview"], "description": "Portfolio presentation and interview prep prompt template"},
    {"phase": "12", "lesson": "07", "name": "prompt-continued-learning-map", "type": "prompt", "tags": ["capstone", "learning", "career"], "description": "Continued learning map prompt template"},
]

CAPSTONE_PROJECTS = [
    {
        "id": "12-01",
        "name": "Production RAG Assistant",
        "folder": "phases/12-capstones/01-production-rag-assistant",
        "artifact": "runbook-rag-assistant-production.md",
        "q1": "Built a production RAG pipeline: document ingestion, pgvector retrieval, RAGAS evaluation, FastAPI service with health checks",
        "q2": "Chose RAG over agents when retrieval from a fixed knowledge base sufficed; no agent complexity added until single-pass retrieval failed quality gate",
        "q3": "Produced operational runbook covering start/stop, 5 common failures, monitoring thresholds, and 90-day success criteria",
    },
    {
        "id": "12-02",
        "name": "Customer Support Agent",
        "folder": "phases/12-capstones/02-customer-support-agent",
        "artifact": "runbook-customer-support-agent.md",
        "q1": "Built a multi-tool support agent: ticket lookup, knowledge base search, escalation routing, draft generation with quality gate",
        "q2": "Scoped to known support categories; added tools only when static prompts failed the golden set eval",
        "q3": "Deployed with observability (Langfuse tracing), handoff package, and agent safety checklist signed off before production",
    },
    {
        "id": "12-03",
        "name": "Text-to-SQL Analytics",
        "folder": "phases/12-capstones/03-text-to-sql-analytics",
        "artifact": "skill-sql-agent-safety-guide.md",
        "q1": "Built a natural language to SQL pipeline with schema introspection, query validation, and result formatting",
        "q2": "Chose tool-calling over agent for SQL generation; no iterative query planning until complex joins required it",
        "q3": "Packaged safety guide covering injection risks, read-only enforcement, result size limits, and audit logging",
    },
    {
        "id": "12-04",
        "name": "Coding Automation Agent",
        "folder": "phases/12-capstones/04-coding-automation-agent",
        "artifact": "skill-coding-agent-patterns.md",
        "q1": "Built a coding agent with file read/write tools, test execution, and self-correction loop against failing tests",
        "q2": "Defined explicit scope boundaries: no internet access, no package installation, pre-approved tool set only",
        "q3": "Produced pattern guide covering when coding agents are safe to deploy and what guardrails are non-negotiable",
    },
    {
        "id": "12-05",
        "name": "FDE Mock Engagement",
        "folder": "phases/12-capstones/05-fde-mock-engagement",
        "artifact": "runbook-fde-engagement-playbook.md",
        "q1": "Ran a complete engagement lifecycle: AI spec, pattern selection, email triage MVP, golden set evaluation, go/no-go decision",
        "q2": "Selected router pattern over agent; justified in writing with latency, auditability, and fixed-category constraints",
        "q3": "Delivered four-part handoff package with 30/60/90 day success criteria and retraining triggers",
    },
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Artifact:
    phase: str
    lesson: str
    name: str
    artifact_type: str
    tags: list
    description: str
    score: int = 0


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def score_artifact(artifact: dict, role: Optional[str] = None) -> int:
    base = FEATURE_PROJECT_SCORES.get(artifact["type"], 1)

    # Capstone bonus
    if artifact["phase"] == "12":
        base = max(base, FEATURE_PROJECT_SCORES["capstone"])

    # Eval bonus within capstone
    if "eval" in artifact.get("tags", []) and artifact["phase"] == "12":
        base += 2

    # Role boost
    if role and role in ROLE_BOOSTS:
        boosts = ROLE_BOOSTS[role]
        phase_boost = boosts["phase"].get(artifact["phase"], 0)
        tag_boost = max(
            (boosts["tags"].get(tag, 0) for tag in artifact.get("tags", [])),
            default=0,
        )
        base += phase_boost + tag_boost

    return base


def load_artifacts(index_path: Optional[str] = None) -> list[dict]:
    if index_path and os.path.exists(index_path):
        with open(index_path) as f:
            data = json.load(f)
        return data.get("artifacts", [])
    return DEMO_ARTIFACTS


def generate_portfolio(artifacts: list[dict], role: Optional[str] = None) -> str:
    """Generate PORTFOLIO.md content."""
    scored = sorted(
        [{"artifact": a, "score": score_artifact(a, role)} for a in artifacts],
        key=lambda x: x["score"],
        reverse=True,
    )

    # Feature projects: top 5 non-duplicate capstones first, then others
    feature_projects = []
    seen_phases_12 = set()
    for item in scored:
        a = item["artifact"]
        if a["phase"] == "12" and a["lesson"] not in seen_phases_12:
            feature_projects.append(item)
            seen_phases_12.add(a["lesson"])
            if len(feature_projects) >= 5:
                break

    # If we don't have 5 from phase 12, fill from top scored non-phase-12
    if len(feature_projects) < 5:
        for item in scored:
            if item["artifact"]["phase"] != "12" and item not in feature_projects:
                feature_projects.append(item)
                if len(feature_projects) >= 5:
                    break

    # Count by type and phase
    type_counts: dict[str, int] = {}
    phase_counts: dict[str, int] = {}
    for a in artifacts:
        t = a["type"]
        p = a["phase"]
        type_counts[t] = type_counts.get(t, 0) + 1
        phase_counts[p] = phase_counts.get(p, 0) + 1

    # Build markdown
    role_label = f" (optimized for: {role})" if role else ""
    lines = [
        f"# Applied AI Engineering Portfolio{role_label}",
        "",
        f"**Total artifacts:** {len(artifacts)}  ",
        f"**Phases complete:** {len(phase_counts)}  ",
        f"**Capstone projects:** {len([a for a in artifacts if a['phase'] == '12'])}  ",
        "",
        "---",
        "",
        "## Featured Projects",
        "",
    ]

    # Capstone project table
    lines.append("| Project | What it demonstrates | Key artifact |")
    lines.append("|---------|---------------------|-------------|")
    for project in CAPSTONE_PROJECTS:
        lines.append(
            f"| {project['name']} | "
            f"{project['q1'][:80]}... | "
            f"`{project['artifact']}` |"
        )
    lines.append("")

    # Feature artifacts (role-filtered)
    lines.append("## Top Artifacts for This Role")
    lines.append("")
    lines.append("| Artifact | Type | Phase | Score |")
    lines.append("|----------|------|-------|-------|")
    for item in feature_projects:
        a = item["artifact"]
        lines.append(
            f"| `{a['name']}.md` | {a['type']} | P{a['phase']} | {item['score']} |"
        )
    lines.append("")

    # Artifact counts
    lines.append("## Artifact Inventory")
    lines.append("")
    lines.append("**By type:**")
    for t, count in sorted(type_counts.items()):
        lines.append(f"- {t}: {count}")
    lines.append("")
    lines.append("**By phase:**")
    for p in sorted(phase_counts.keys()):
        count = phase_counts[p]
        lines.append(f"- Phase {p}: {count} artifact{'s' if count != 1 else ''}")
    lines.append("")

    # Three-question coverage
    lines.append("## Three-Question Coverage")
    lines.append("")
    lines.append("**Q1: Can you build it?**")
    lines.append("Evidence: All 5 capstone projects in phases/12-capstones/ with working code, Dockerfiles, and evaluation results.")
    lines.append("")
    lines.append("**Q2: Do you know when NOT to build it?**")
    lines.append("Evidence: prompt-pattern-decision-guide.md (P11-04), prompt-ai-spec-template.md (P11-03) with explicit out-of-scope sections, skill-fine-tuning-readiness.md (P09-03).")
    lines.append("")
    lines.append("**Q3: Can you deliver it to a customer?**")
    lines.append("Evidence: runbook-fde-engagement-playbook.md (P12-05) with go/no-go decision, skill-handoff-package-template.md (P11-09), eval-llm-as-judge-template.md (P05-04).")
    lines.append("")

    return "\n".join(lines)


def generate_narrative(project_id: str) -> str:
    """Generate a sample interview narrative for a capstone project."""
    project = next((p for p in CAPSTONE_PROJECTS if p["id"] == project_id or
                    project_id in p["name"].lower().replace(" ", "-")), None)
    if not project:
        available = [p["id"] for p in CAPSTONE_PROJECTS]
        return f"Project '{project_id}' not found. Available: {', '.join(available)}"

    narrative = f"""Interview Narrative: {project['name']}

"I built {project['q1'].lower()}

{project['q2']}

For the delivery side: {project['q3'].lower()}

The artifact I'd point to is {project['artifact']} - it covers the system architecture,
operating instructions, and the evaluation baseline that justified the go/no-go decision.
If you want to see the code, the full implementation is in {project['folder']}/code/main.py."
"""
    return narrative


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Portfolio Generator")
    parser.add_argument("--demo", action="store_true", help="Use demo artifact data")
    parser.add_argument("--index", type=str, help="Path to outputs/index.json")
    parser.add_argument("--generate", action="store_true", help="Generate PORTFOLIO.md")
    parser.add_argument("--count", action="store_true", help="Count artifacts by type")
    parser.add_argument("--narrative", action="store_true", help="Generate interview narrative")
    parser.add_argument("--project", type=str, help="Project ID for narrative (e.g., 12-05)")
    parser.add_argument("--role", type=str, choices=["fde", "applied-ai-engineer", "solutions-engineer"],
                        help="Role filter for artifact scoring")
    parser.add_argument("--output", type=str, default="PORTFOLIO.md", help="Output file path")
    args = parser.parse_args()

    # Load artifacts
    if args.demo:
        artifacts = DEMO_ARTIFACTS
        print(f"Using demo data: {len(artifacts)} artifacts across 13 phases\n")
    elif args.index:
        artifacts = load_artifacts(args.index)
        print(f"Loaded {len(artifacts)} artifacts from {args.index}\n")
    else:
        print("Specify --demo or --index <path>")
        parser.print_help()
        sys.exit(1)

    if args.count:
        type_counts: dict[str, int] = {}
        phase_counts: dict[str, int] = {}
        for a in artifacts:
            type_counts[a["type"]] = type_counts.get(a["type"], 0) + 1
            phase_counts[a["phase"]] = phase_counts.get(a["phase"], 0) + 1
        print(f"Total artifacts: {len(artifacts)}\n")
        print("By type:")
        for t, c in sorted(type_counts.items()):
            print(f"  {t:<20} {c}")
        print("\nBy phase:")
        for p in sorted(phase_counts.keys()):
            print(f"  Phase {p}: {phase_counts[p]}")
        return

    if args.narrative:
        project_id = args.project or "12-05"
        print(generate_narrative(project_id))
        return

    if args.generate:
        content = generate_portfolio(artifacts, role=args.role)
        output_path = args.output
        with open(output_path, "w") as f:
            f.write(content)
        print(f"Generated {output_path}")
        print(f"  Artifacts indexed: {len(artifacts)}")
        print(f"  Role filter: {args.role or 'none (all roles)'}")
        print(f"\nPreview:")
        print("-" * 50)
        print("\n".join(content.split("\n")[:20]))
        print("...")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
