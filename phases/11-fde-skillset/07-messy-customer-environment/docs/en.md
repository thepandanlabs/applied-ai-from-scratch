# Integrating into a Messy Customer Environment

> Run the integration audit in the first customer meeting, not after you have built the system.

**Type:** Build
**Languages:** Python
**Prerequisites:** 11-02 (scoping before solving), 11-03 (discovery: vague ask to spec)
**Time:** ~60 min
**Phase:** 11 · FDE Skillset

---

## Learning Objectives

- Identify the five integration domains that cause the most FDE deployment failures
- Run a structured integration audit before committing to a technical design
- Produce a risk-scored integration plan from audit results
- Build a CLI tool that walks through integration domains and generates a risk report
- Recognize the difference between a blocker (stops the project) and a risk (requires mitigation)

---

## The Problem

You spent six weeks building an AI system. The model is good, the eval results are solid, the demo is polished. Then you arrive at the customer's site for deployment day.

The customer's IT team informs you that all outbound API calls to external services are blocked by default. Their data lives in a legacy CRM that has no documented API. The service account you were promised has read-only access to two of the eight required tables. And by the way, data residency requirements mean the model cannot run on US-based cloud infrastructure.

This is not a hypothetical. It is the most common FDE failure mode. The technical work was done correctly, and the system is undeployable.

The root cause is always the same: the integration audit happened too late. Engineers ask about data access, auth, and infrastructure after they have committed to an architecture. At that point, every discovery is a crisis. The correct order is: audit first, design second, build third.

A structured integration audit is not bureaucracy. It is the conversation that determines whether the system you are about to build can actually run in the customer's environment.

---

## The Concept

### The Five Integration Domains

```
+------------------+------------------------------------------+---------------------------+
| DOMAIN           | WHAT IT COVERS                           | COMMON BLOCKERS           |
+------------------+------------------------------------------+---------------------------+
| AUTH             | How your system authenticates with        | No service accounts,      |
|                  | theirs: SSO, API keys, service accounts,  | SSO-only policies,        |
|                  | OAuth flows, mutual TLS                   | key rotation requirements |
+------------------+------------------------------------------+---------------------------+
| DATA             | Where data lives, what format it is in,   | No API, CSV exports only, |
|                  | who owns it, what latency is acceptable,  | PII restrictions, no      |
|                  | whether you can get it in real time       | historical data access    |
+------------------+------------------------------------------+---------------------------+
| NETWORK          | What network restrictions exist: no       | VPN-only, allowlisting    |
|                  | public internet, VPN requirements,        | process takes 4 weeks,    |
|                  | IP allowlisting, air-gapped segments      | no egress to cloud        |
+------------------+------------------------------------------+---------------------------+
| COMPLIANCE       | Data residency, audit logging, retention  | EU data cannot leave EU,  |
|                  | policies, regulatory requirements         | all API calls must be     |
|                  | (HIPAA, SOC2, GDPR, FedRAMP)             | logged, 90-day retention  |
+------------------+------------------------------------------+---------------------------+
| APIS             | What internal tools and systems exist,    | No docs, deprecated APIs, |
|                  | whether they have APIs, what the docs     | rate limits, auth unknown,|
|                  | look like, who to contact for access      | EOL systems still in prod |
+------------------+------------------------------------------+---------------------------+
```

### Risk Levels

```
BLOCKER  (red)    - Project cannot proceed without resolving this.
                    Example: data lives in a system with no API and no export capability.
                    Action: stop. Resolve before committing to timeline.

HIGH     (orange) - Likely to cause significant delay or require architectural change.
                    Example: IP allowlisting process takes 3-4 weeks.
                    Action: start resolution immediately. Factor into timeline.

MEDIUM   (yellow) - Manageable with mitigation. Adds work but not a showstopper.
                    Example: service account needs manual provisioning by IT.
                    Action: document mitigation. Assign owner and deadline.

LOW      (green)  - Minor friction. Solvable in a day or less.
                    Example: API key must be rotated every 90 days.
                    Action: add to ops runbook.
```

### When to Run the Audit

```
NOT this order:
  Discovery --> Design --> Build --> Deploy --> [discover blockers]

THIS order:
  Discovery --> Integration Audit --> Design --> Build --> Deploy
                    ^
              Week 1, Meeting 1.
              Before committing to any architecture.
```

The audit is not a checklist you hand the customer. It is a conversation you lead. The engineer drives the questions. The customer (or their IT/security contact) answers. You score the risks in real time and share the report within 24 hours.

---

## Build It

### Step 1: Dependencies and Setup

```python
# pip install anthropic
# Set ANTHROPIC_API_KEY in environment

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
```

### Step 2: Data Models

```python
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
    owner: str   # "FDE", "customer-IT", "customer-security", "shared"


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
```

### Step 3: The Question Bank

```python
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
        "Can we access historical data, or only real-time/recent records?",
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
```

### Step 4: The Risk Scorer

```python
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
```

### Step 5: Interactive Audit Runner

```python
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
```

### Step 6: Report Formatter

```python
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
```

### Step 7: Demo Mode with Pre-Filled Answers

```python
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
```

> **Real-world check:** Your manager says: "Stop asking so many questions in the first meeting. It makes the customer feel like we do not know what we are doing." How do you explain that an integration audit is not a sign of incompetence but the opposite: it is how experienced engineers avoid the most common deployment failure mode?

---

## Use It

Run the demo against the Acme Corp scenario:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --demo
```

The scenario includes several common enterprise blockers:
- SSO-only policy (no service accounts) in the auth domain
- Oracle CRM with no API access in the data domain
- 3-4 week IP allowlisting process in the network domain
- EU data residency requirements in the compliance domain
- Undocumented ORCA system in the APIs domain

Expected report: at least one BLOCKER (Oracle CRM data access or EU data residency), multiple HIGH risks (allowlisting, SSO-only policy), and a clear set of required mitigations before design begins.

Run the interactive audit against a real or hypothetical customer:

```bash
python main.py --interactive --customer "Contoso" --project "AI document summarizer for legal team"
```

Export the findings for project documentation:

```bash
python main.py --demo --export audit-report.json
```

> **Perspective shift:** A junior engineer on your team says: "Why do we need to audit all five domains? Most of the time only one or two are actually problems." How do you explain that the domains you skip are exactly the ones that produce the 3-day-before-launch discovery that kills the project?

---

## Ship It

The output for this lesson is `outputs/skill-integration-audit-checklist.md`. It is a printable one-page checklist version of the five-domain audit for use in customer meetings when you do not have the CLI tool available.

The runnable tool is `code/main.py`:

```bash
python main.py --demo
python main.py --interactive --customer "Company" --project "Project description"
```

---

## Evaluate It

**Check 1: Does the demo scenario produce realistic risk levels?**
The Acme Corp scenario is designed to surface at least 3 high-or-blocker findings. Run it and verify: Oracle CRM no-API should be HIGH or BLOCKER, EU data residency should be HIGH or BLOCKER, 3-4 week allowlisting should be HIGH. If all findings come back LOW, the scoring prompt is not calibrated correctly.

**Check 2: Does the overall risk classification match your manual assessment?**
Read the Acme Corp scenario description and classify the overall risk yourself before running the tool. Compare. If you assess BLOCKER and the tool outputs MEDIUM, the aggregation logic or the prompt needs tuning.

**Check 3: Are the mitigations actionable?**
For each finding, the mitigation should name a specific action and an owner. "Coordinate with IT" is not actionable. "Submit IP allowlisting request to security@acme.com with business justification form by [date]" is. Review the generated mitigations and flag any that are vague.

**Check 4: Does the interactive mode capture answers correctly?**
Run the interactive mode and deliberately enter a problematic answer (e.g., "No, we have no API and no export capability for the Oracle system"). Verify the tool scores this as BLOCKER or HIGH, not MEDIUM or LOW.
