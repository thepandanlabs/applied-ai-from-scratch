"""
IntegrationAudit: walk through 5 integration domains, score each finding,
and produce a risk-scored integration plan.

Usage:
    python main.py --demo
    python main.py --interactive --customer "Acme" --project "AI ticket router"
    python main.py --demo --export report.json
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"


class RiskLevel(str, Enum):
    BLOCKER = "blocker"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class DomainFinding:
    domain: str
    question: str
    answer: str
    risk_level: RiskLevel
    risk_description: str
    mitigation: str
    owner: str


@dataclass
class IntegrationAuditReport:
    customer_name: str
    project_description: str
    findings: list[DomainFinding] = field(default_factory=list)

    @property
    def blockers(self) -> list[DomainFinding]:
        return [f for f in self.findings if f.risk_level == RiskLevel.BLOCKER]

    @property
    def high_risks(self) -> list[DomainFinding]:
        return [f for f in self.findings if f.risk_level == RiskLevel.HIGH]

    @property
    def overall_risk(self) -> str:
        if self.blockers:
            return "BLOCKER - do not commit to timeline until resolved"
        if len(self.high_risks) >= 2:
            return "HIGH - significant mitigation work required"
        if self.high_risks:
            return "MEDIUM-HIGH - one high risk, monitor closely"
        return "MEDIUM or below - proceed with documented mitigations"


AUDIT_QUESTIONS = {
    "auth": [
        "How will our system authenticate with yours? Do you use SSO, API keys, or service accounts?",
        "Can you provision a dedicated service account for our system, or must it use a human user account?",
        "Are there API key rotation policies? How frequently do keys expire?",
        "Do you require mutual TLS or IP-based authentication in addition to API keys?",
    ],
    "data": [
        "Where does the data our system needs live? Which system of record?",
        "Does that system have a documented API? Is it REST, GraphQL, or something else?",
        "Can we access historical data, or only real-time and recent records?",
        "Are there PII or sensitive data fields we will encounter? Who owns data classification decisions?",
        "What is the acceptable latency for data access? Batch overnight, or near-real-time?",
    ],
    "network": [
        "Does your environment allow outbound API calls to external cloud services?",
        "Is there a VPN or private network our system must operate within?",
        "Are there IP allowlisting requirements? What is the process and timeline for getting IPs approved?",
        "Are there air-gapped segments that our system needs to reach?",
    ],
    "compliance": [
        "Are there data residency requirements? Can data be processed in US-based cloud infrastructure?",
        "Are there regulatory requirements that apply to this system: HIPAA, SOC2, GDPR, FedRAMP?",
        "Does every API call to an AI model need to be logged for audit purposes? What is the retention requirement?",
        "Who is the data privacy or compliance officer we should loop in?",
    ],
    "apis": [
        "What internal tools or systems does this AI system need to read from or write to?",
        "Do those systems have documented APIs? Are the docs up to date?",
        "Are any of those systems legacy or near end-of-life?",
        "Who is the technical contact for each system we need to integrate with?",
    ],
}

SCORE_PROMPT = """You are an experienced AI systems integrator. You have just collected answers from a customer during an integration audit.

Project: {project}
Customer: {customer}

Domain: {domain}
Question asked: {question}
Customer's answer: {answer}

Assess the risk level of this finding and provide a structured response in this exact JSON format:
{{
  "risk_level": "blocker" | "high" | "medium" | "low",
  "risk_description": "<one sentence: what the risk is and why it matters>",
  "mitigation": "<one to two sentences: specific action to resolve or reduce this risk>",
  "owner": "FDE" | "customer-IT" | "customer-security" | "shared"
}}

Risk level definitions:
- blocker: project cannot proceed without resolving this (e.g., no data access at all, compliance requirement that eliminates the proposed architecture)
- high: likely to cause significant delay or require architectural change (e.g., 3-4 week allowlisting process, no API requires building an export pipeline)
- medium: manageable with mitigation, adds work but not a showstopper (e.g., manual provisioning needed, rate limits require caching layer)
- low: minor friction, solvable in a day or less (e.g., key rotation every 90 days, needs docs request to IT)

Return only the JSON object."""


def score_finding(
    customer: str,
    project: str,
    domain: str,
    question: str,
    answer: str,
) -> tuple[RiskLevel, str, str, str]:
    """Score a single audit finding. Returns (risk_level, description, mitigation, owner)."""
    prompt = SCORE_PROMPT.format(
        project=project,
        customer=customer,
        domain=domain,
        question=question,
        answer=answer,
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

    data = json.loads(raw)
    return (
        RiskLevel(data["risk_level"]),
        data["risk_description"],
        data["mitigation"],
        data["owner"],
    )


RISK_ORDER = [RiskLevel.BLOCKER, RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW]
RISK_LABELS = {
    RiskLevel.BLOCKER: "[BLOCKER]",
    RiskLevel.HIGH: "[HIGH]   ",
    RiskLevel.MEDIUM: "[MEDIUM] ",
    RiskLevel.LOW: "[LOW]    ",
}


def print_report(report: IntegrationAuditReport) -> None:
    """Print a structured integration audit report."""
    print("\n" + "=" * 60)
    print("INTEGRATION AUDIT REPORT")
    print("=" * 60)
    print(f"Customer: {report.customer_name}")
    print(f"Project:  {report.project_description}")
    print(f"Findings: {len(report.findings)}")
    print(f"\nOVERALL RISK: {report.overall_risk}")

    if report.blockers:
        print(f"\n*** {len(report.blockers)} BLOCKER(S) FOUND - DO NOT PROCEED ***")

    print("\n--- FINDINGS BY RISK LEVEL ---\n")

    for risk_level in RISK_ORDER:
        findings = [f for f in report.findings if f.risk_level == risk_level]
        if not findings:
            continue
        for f in findings:
            print(f"{RISK_LABELS[risk_level]} [{f.domain.upper()}] {f.risk_description}")
            print(f"           Mitigation: {f.mitigation}")
            print(f"           Owner: {f.owner}")
            print()

    print("=" * 60)
    if report.blockers:
        print("NEXT STEP: Resolve blockers before committing to any timeline.")
    elif report.high_risks:
        print("NEXT STEP: Start mitigation on HIGH risks this week.")
    else:
        print("NEXT STEP: Document mitigations in project plan. Proceed to design.")
    print("=" * 60 + "\n")


def export_report_json(report: IntegrationAuditReport, path: str) -> None:
    """Export the report as JSON for inclusion in project documentation."""
    data = {
        "customer": report.customer_name,
        "project": report.project_description,
        "overall_risk": report.overall_risk,
        "findings": [
            {
                "domain": f.domain,
                "question": f.question,
                "answer": f.answer,
                "risk_level": f.risk_level.value,
                "risk_description": f.risk_description,
                "mitigation": f.mitigation,
                "owner": f.owner,
            }
            for f in sorted(report.findings, key=lambda x: RISK_ORDER.index(x.risk_level))
        ],
    }
    with open(path, "w") as fp:
        json.dump(data, fp, indent=2)
    print(f"Report saved to {path}")


DEMO_SCENARIO = {
    "customer": "Acme Corp",
    "project": "AI-powered customer support ticket routing system, integrating with legacy CRM",
    "answers": {
        "auth": [
            "We use SSO with Okta for all internal systems. Service accounts are not allowed by policy.",
            "No, all accounts must be tied to a human user in Okta.",
            "API keys for external systems rotate every 30 days, automatically.",
            "No mutual TLS required, but all traffic must go through our API gateway.",
        ],
        "data": [
            "Customer data lives in Salesforce and a legacy Oracle CRM from 2008 that we are planning to retire.",
            "Salesforce has a REST API. The Oracle system has no API, only direct database access which IT controls.",
            "Historical data in Oracle goes back 10 years. Access requires a formal IT request with 2-week SLA.",
            "Yes, every ticket contains customer name, email, and sometimes payment info. Data classification is owned by our Legal team.",
            "Near-real-time preferred, under 5 seconds latency for ticket ingestion.",
        ],
        "network": [
            "Our corporate network blocks all direct outbound calls to cloud services. Everything goes through a proxy.",
            "Yes, VPN is required for internal systems access. Contractors get a limited VPN profile.",
            "Yes, IP allowlisting for external services. The security team runs this. Process takes 3 to 4 weeks and requires a business justification form.",
            "No air-gapped segments for this use case.",
        ],
        "compliance": [
            "We process EU customer data so GDPR applies. EU data cannot leave the EU.",
            "We are SOC 2 Type II certified. No HIPAA. GDPR as mentioned.",
            "Yes, all calls to external AI APIs must be logged. Retention is 1 year.",
            "Sarah Chen is our DPO. She will need to sign off on any third-party AI vendor.",
        ],
        "apis": [
            "Salesforce, the Oracle CRM, our internal ticketing system (Zendesk), and a homegrown escalation tool called ORCA.",
            "Salesforce and Zendesk have good REST APIs. Oracle has no API. ORCA has docs but they are 3 years old and the lead developer left.",
            "Oracle CRM is 2008-era, actively planning to retire in 18 months. ORCA is maintained by one person.",
            "Salesforce admin is Tom Rivera. Zendesk: Maria Santos. Oracle: IT helpdesk (no named contact). ORCA: check with Tom, the original dev is gone.",
        ],
    },
}


def run_demo(scenario: dict) -> IntegrationAuditReport:
    """Run the audit with pre-filled demo answers."""
    report = IntegrationAuditReport(
        customer_name=scenario["customer"],
        project_description=scenario["project"],
    )

    print(f"\nRunning integration audit for: {scenario['customer']}")
    print(f"Project: {scenario['project']}\n")

    for domain, questions in AUDIT_QUESTIONS.items():
        answers = scenario["answers"].get(domain, [])
        for i, question in enumerate(questions):
            if i >= len(answers):
                continue
            answer = answers[i]
            print(f"  [{domain.upper()}] Scoring: {question[:60]}...")

            risk_level, risk_desc, mitigation, owner = score_finding(
                customer=scenario["customer"],
                project=scenario["project"],
                domain=domain,
                question=question,
                answer=answer,
            )

            finding = DomainFinding(
                domain=domain,
                question=question,
                answer=answer,
                risk_level=risk_level,
                risk_description=risk_desc,
                mitigation=mitigation,
                owner=owner,
            )
            report.findings.append(finding)

    return report


def run_interactive_audit(customer: str, project: str) -> IntegrationAuditReport:
    """Walk through all five domains interactively. Collect answers and score each finding."""
    report = IntegrationAuditReport(
        customer_name=customer,
        project_description=project,
    )

    print(f"\nStarting integration audit for: {customer}")
    print(f"Project: {project}")
    print("=" * 60)
    print("For each question, enter the customer's answer.")
    print("Press Enter to skip a question.\n")

    for domain, questions in AUDIT_QUESTIONS.items():
        print(f"\n--- Domain: {domain.upper()} ---")
        for question in questions:
            print(f"\nQ: {question}")
            answer = input("A: ").strip()
            if not answer:
                continue

            risk_level, risk_desc, mitigation, owner = score_finding(
                customer=customer,
                project=project,
                domain=domain,
                question=question,
                answer=answer,
            )

            finding = DomainFinding(
                domain=domain,
                question=question,
                answer=answer,
                risk_level=risk_level,
                risk_description=risk_desc,
                mitigation=mitigation,
                owner=owner,
            )
            report.findings.append(finding)

            risk_label = risk_level.value.upper()
            print(f"  >> Risk: {risk_label} | {risk_desc}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IntegrationAudit: risk-score integration domains for AI deployments"
    )
    parser.add_argument("--demo", action="store_true", help="Run the Acme Corp demo scenario")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run interactive audit with prompted questions",
    )
    parser.add_argument("--customer", help="Customer name (for interactive mode)")
    parser.add_argument("--project", help="Project description (for interactive mode)")
    parser.add_argument("--export", help="Export report to JSON file at this path")
    args = parser.parse_args()

    if args.demo:
        report = run_demo(DEMO_SCENARIO)
        print_report(report)
        if args.export:
            export_report_json(report, args.export)
    elif args.interactive:
        if not args.customer or not args.project:
            print("Error: --interactive requires --customer and --project")
            sys.exit(1)
        report = run_interactive_audit(args.customer, args.project)
        print_report(report)
        if args.export:
            export_report_json(report, args.export)
    else:
        print("Usage:")
        print("  python main.py --demo")
        print("  python main.py --demo --export report.json")
        print("  python main.py --interactive --customer 'Acme' --project 'AI ticket router'")
        sys.exit(1)


if __name__ == "__main__":
    main()
