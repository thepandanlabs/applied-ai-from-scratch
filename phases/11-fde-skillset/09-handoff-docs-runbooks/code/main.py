"""
HandoffPackageGenerator: generate and check all four documents in a
customer handoff package using Claude.

Usage:
    python main.py --demo --output ./handoff-package
    python main.py --demo --check
    python main.py --from-json project.json --output ./handoff-package
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
class ProjectTemplate:
    project_name: str
    system_description: str
    what_it_does_not_do: str
    external_dependencies: str
    infrastructure: str
    scheduled_jobs: str
    common_failures: str
    prompt_files: str
    eval_command: str
    fde_contact: str
    customer_tech_lead: str

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectTemplate":
        return cls(**data)

    @classmethod
    def from_json(cls, path: str) -> "ProjectTemplate":
        with open(path) as f:
            return cls.from_dict(json.load(f))


OVERVIEW_PROMPT = """You are writing the System Overview document for a customer handoff package.

Project: {project_name}
System description: {system_description}
What it does NOT do: {what_it_does_not_do}
External dependencies: {external_dependencies}
Infrastructure: {infrastructure}
Customer tech lead (owner after handoff): {customer_tech_lead}

Write a concise System Overview document. Use markdown. Include:
1. A one-paragraph purpose statement (what it does, for whom, why it matters)
2. A "What this system does NOT do" section with a bullet list
3. A "Dependencies" section listing all external systems and APIs
4. An "Infrastructure" section: where it runs, estimated monthly cost, scaling limits
5. An "Ownership" section: the customer tech lead's name, role, and what they own

Keep the whole document under 500 words. Use plain language. Avoid technical jargon where possible."""


RUNBOOK_PROMPT = """You are writing the Operational Runbook for a customer handoff package.

Project: {project_name}
Infrastructure: {infrastructure}
Scheduled jobs: {scheduled_jobs}
Common failures: {common_failures}
External dependencies: {external_dependencies}

Write a complete operational runbook. Use markdown. Include:
1. "Starting the system" - step-by-step instructions
2. "Stopping and restarting" - when and how
3. "Configuration" - what can be configured, where environment variables are set
4. "Scheduled jobs" - what each job does, when it runs, how to verify it ran
5. "Common failures" - for each failure mode listed, write: Symptom, Cause, Fix (step-by-step)
6. "Health checks" - how to verify the system is working without reading code

For the Common Failures section: make each fix self-contained. Assume the reader has not seen the codebase."""


PROMPT_CHANGE_GUIDE_PROMPT = """You are writing the Prompt and Model Change Guide for a customer handoff package.

Project: {project_name}
Prompt files location: {prompt_files}
Eval command: {eval_command}
Common failures: {common_failures}

Write a guide for safely updating AI components. Use markdown. Include:
1. "When to update prompts" - what symptoms indicate a prompt needs changing
2. "How to update a prompt safely" - step by step: edit, run eval, review results, deploy
3. "Running the eval set" - exact commands to run, what the output means
4. "Interpreting eval results" - what scores are acceptable vs. require investigation
5. "Rolling back a prompt change" - how to revert if quality drops
6. "When to contact the original team" - specific conditions that require expert help

Assume the reader is a competent engineer who did not build the original system."""


ESCALATION_PROMPT = """You are writing the Escalation Path document for a customer handoff package.

Project: {project_name}
Customer tech lead: {customer_tech_lead}
FDE contact: {fde_contact}
Common failures: {common_failures}

Write a clear escalation path document. Use markdown. Include:
1. "Level 1: Self-service" - things to try before involving anyone (restart, logs, config check)
2. "Level 2: Internal tech lead" - when to involve {customer_tech_lead} and what to bring to them
3. "Level 3: Original FDE team" - when to escalate externally, contact info for {fde_contact}, expected response time
4. "What to include in an escalation message" - a template with: system name, symptom, when it started, what you tried, relevant logs
5. "Contacts" - a table: person, role, contact method, response time expectation

Be concrete about when to escalate vs. when to keep troubleshooting independently."""


COMPLETENESS_CHECK_PROMPT = """You are reviewing a handoff package for completeness.

Project: {project_name}
Known common failures: {common_failures}

Handoff package content:
{package_content}

Check the package against these requirements and return a JSON object:
{{
  "completeness_score": <integer 0-100>,
  "has_system_overview": true/false,
  "has_runbook": true/false,
  "has_prompt_change_guide": true/false,
  "has_escalation_path": true/false,
  "common_failures_covered": <integer: how many of the listed failures have runbook sections>,
  "missing_items": ["<item 1>", "<item 2>"],
  "gaps": ["<gap 1>", "<gap 2>"],
  "recommendation": "<one sentence: is this handoff package complete enough to transfer operational ownership?>"
}}

Return only the JSON object."""


def generate_document(prompt_template: str, template: ProjectTemplate) -> str:
    """Generate a single handoff document using the given prompt template."""
    filled_prompt = prompt_template.format(
        project_name=template.project_name,
        system_description=template.system_description,
        what_it_does_not_do=template.what_it_does_not_do,
        external_dependencies=template.external_dependencies,
        infrastructure=template.infrastructure,
        scheduled_jobs=template.scheduled_jobs,
        common_failures=template.common_failures,
        prompt_files=template.prompt_files,
        eval_command=template.eval_command,
        fde_contact=template.fde_contact,
        customer_tech_lead=template.customer_tech_lead,
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": filled_prompt}],
    )

    return response.content[0].text.strip()


def generate_handoff_package(
    template: ProjectTemplate,
    output_dir: str,
) -> dict[str, str]:
    """Generate all four handoff documents and save them to output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    package = {}

    docs = [
        ("01-system-overview.md", OVERVIEW_PROMPT, "System Overview"),
        ("02-runbook.md", RUNBOOK_PROMPT, "Operational Runbook"),
        ("03-prompt-change-guide.md", PROMPT_CHANGE_GUIDE_PROMPT, "Prompt and Model Change Guide"),
        ("04-escalation-path.md", ESCALATION_PROMPT, "Escalation Path"),
    ]

    for filename, prompt, name in docs:
        print(f"Generating: {name}...")
        content = generate_document(prompt, template)
        package[name] = content
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w") as f:
            f.write(f"# {name}\n\n")
            f.write(content)
        print(f"  Saved: {filepath}")

    return package


def check_completeness(template: ProjectTemplate, package: dict[str, str]) -> dict:
    """Run a completeness check on the generated handoff package."""
    package_content = "\n\n".join(
        f"=== {name.upper()} ===\n{content[:800]}..."
        for name, content in package.items()
    )

    prompt = COMPLETENESS_CHECK_PROMPT.format(
        project_name=template.project_name,
        common_failures=template.common_failures,
        package_content=package_content,
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


def print_completeness_report(result: dict) -> None:
    """Print the completeness check results."""
    print("\n" + "=" * 60)
    print("HANDOFF PACKAGE COMPLETENESS CHECK")
    print("=" * 60)
    print(f"\nCompleteness score: {result['completeness_score']}/100")
    print(f"\nDocuments present:")
    print(f"  System Overview:      {'YES' if result['has_system_overview'] else 'NO'}")
    print(f"  Operational Runbook:  {'YES' if result['has_runbook'] else 'NO'}")
    print(f"  Prompt Change Guide:  {'YES' if result['has_prompt_change_guide'] else 'NO'}")
    print(f"  Escalation Path:      {'YES' if result['has_escalation_path'] else 'NO'}")
    print(f"\nCommon failures covered: {result['common_failures_covered']}")

    if result.get("missing_items"):
        print(f"\nMissing items:")
        for item in result["missing_items"]:
            print(f"  - {item}")

    if result.get("gaps"):
        print(f"\nGaps to address:")
        for gap in result["gaps"]:
            print(f"  - {gap}")

    print(f"\nRecommendation: {result['recommendation']}")

    score = result["completeness_score"]
    if score >= 90:
        print("\nSTATUS: Ready for live handoff session.")
    elif score >= 75:
        print("\nSTATUS: Close to ready. Address gaps before handoff session.")
    else:
        print("\nSTATUS: Significant gaps. Do not transfer ownership yet.")
    print("=" * 60 + "\n")


# Demo: a RAG service for internal HR document search
DEMO_TEMPLATE = ProjectTemplate(
    project_name="HR Knowledge Base Search (Phase 06 RAG Service)",
    system_description=(
        "A semantic search system over Acme Corp's internal HR documentation (policy docs, "
        "benefits guides, onboarding materials). Employees ask natural language questions "
        "and receive answers with source citations. Built on pgvector + Claude."
    ),
    what_it_does_not_do=(
        "Does not handle personal employee data (salaries, performance reviews). "
        "Does not integrate with the HRIS system. "
        "Does not support document uploads by end users. "
        "Does not answer questions about topics not in the HR knowledge base. "
        "Does not provide legal advice."
    ),
    external_dependencies=(
        "Anthropic Claude API (claude-3-5-haiku-20241022) for generation. "
        "Anthropic embeddings or OpenAI text-embedding-3-small for retrieval. "
        "PostgreSQL with pgvector extension (hosted on AWS RDS). "
        "AWS S3 for document storage. "
        "Internal SSO via Okta for user authentication."
    ),
    infrastructure=(
        "FastAPI service deployed on AWS ECS Fargate (1 vCPU, 2GB RAM). "
        "PostgreSQL RDS db.t3.medium. "
        "Estimated cost: $180/month (RDS $120, ECS $40, API costs $20 at current volume). "
        "Scales to ~500 queries/day before needing instance upgrade."
    ),
    scheduled_jobs=(
        "Document re-ingestion: runs every Sunday at 2am UTC. "
        "Fetches updated HR docs from S3, re-chunks and re-embeds any changed files, "
        "updates pgvector store. Logs to CloudWatch /hr-search/ingestion. "
        "Runs in approximately 15-20 minutes for the current 847-document corpus."
    ),
    common_failures=(
        "1. Document re-ingestion job fails silently: Sunday job succeeds but new documents "
        "are not searchable. Cause: S3 permissions issue or embedding API rate limit. "
        "2. API key expiration: Anthropic or OpenAI API key expires, all queries return 500 errors. "
        "3. pgvector index corruption: queries return empty results or very low similarity scores. "
        "4. ECS service unhealthy: health check fails, service returns 503. "
        "5. Prompt quality degradation: users report answers that are vague or cite wrong documents."
    ),
    prompt_files=(
        "All prompts are in /app/prompts/. "
        "system_prompt.txt: the main system instruction for the RAG generation step. "
        "query_rewrite_prompt.txt: optional query expansion prompt. "
        "Do not edit prompts directly in production. See the prompt change guide."
    ),
    eval_command=(
        "cd /app && python run_evals.py --eval-set data/eval_set_v2.json --output results.json "
        "Requires ANTHROPIC_API_KEY. Runs 50 question/answer pairs. "
        "Takes approximately 3 minutes. Target: faithfulness > 0.85, relevance > 0.80."
    ),
    fde_contact=(
        "Jane Smith, Applied AI Engineering, jane@fde-firm.com, "
        "Slack: @janesmith. Response time: within 24 hours for non-critical issues, "
        "within 2 hours for production outages (email with URGENT in subject)."
    ),
    customer_tech_lead=(
        "Marcus Johnson, Sr. Software Engineer, Acme Corp, "
        "marcus.johnson@acme.com, Slack: @marcusj. "
        "Marcus owns day-to-day operations and is the first point of contact for all issues."
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="HandoffPackageGenerator: generate all four handoff documents for a project"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with the built-in HR RAG service demo project",
    )
    parser.add_argument("--from-json", help="Load project template from JSON file")
    parser.add_argument("--output", default="./handoff-package", help="Output directory for documents")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run completeness check on the generated package",
    )
    args = parser.parse_args()

    if args.demo:
        template = DEMO_TEMPLATE
    elif args.from_json:
        template = ProjectTemplate.from_json(args.from_json)
    else:
        print("Usage:")
        print("  python main.py --demo --output ./handoff-package")
        print("  python main.py --demo --check")
        print("  python main.py --from-json project.json --output ./handoff-package")
        sys.exit(1)

    print(f"\nGenerating handoff package for: {template.project_name}")
    print(f"Output directory: {args.output}\n")

    package = generate_handoff_package(template, args.output)
    print(f"\nHandoff package generated: {len(package)} documents in {args.output}/")

    if args.check:
        print("\nRunning completeness check...")
        result = check_completeness(template, package)
        print_completeness_report(result)


if __name__ == "__main__":
    main()
