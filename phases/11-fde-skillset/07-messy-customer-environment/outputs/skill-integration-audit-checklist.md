---
name: skill-integration-audit-checklist
description: Five-domain integration audit checklist for deploying AI systems in customer environments
version: "1.0"
phase: "11"
lesson: "07"
tags: [fde, integration, deployment, audit, enterprise]
---

# Integration Audit Checklist

Run this audit in the first customer meeting. Before design. Before architecture. Before committing to a timeline.

---

## Domain 1: Auth

- [ ] What authentication method does the customer use? (SSO, API keys, service accounts, OAuth, mTLS)
- [ ] Can a dedicated service account be provisioned for the AI system?
- [ ] Are API keys or secrets subject to rotation policies? How often?
- [ ] Are there IP-based or certificate-based auth requirements in addition to credential-based auth?

**Common blockers:** SSO-only policy (no service accounts allowed), no external API key support

---

## Domain 2: Data

- [ ] Where does the required data live? Which system of record?
- [ ] Does that system have a documented, working API?
- [ ] Is historical data accessible, or only real-time records?
- [ ] Are there PII or sensitive data fields? Who owns data classification?
- [ ] What is the required data access latency? (Real-time, batch overnight, on-demand?)

**Common blockers:** No API on the data source (CSV exports only), no access to historical data, PII restrictions that prevent sending data to external APIs

---

## Domain 3: Network

- [ ] Does the environment allow outbound calls to external cloud services?
- [ ] Is VPN or private network access required?
- [ ] Are there IP allowlisting requirements? What is the process and timeline?
- [ ] Are there air-gapped or isolated network segments involved?

**Common blockers:** All egress blocked by default, allowlisting process takes 3-4 weeks, VPN-only access with no external egress

---

## Domain 4: Compliance

- [ ] Are there data residency requirements? Which regions can data be processed in?
- [ ] Which regulatory frameworks apply? (HIPAA, SOC2, GDPR, FedRAMP, CCPA)
- [ ] Are all API calls to AI providers required to be logged? What is the retention requirement?
- [ ] Who is the compliance or privacy officer to loop in?

**Common blockers:** EU data cannot leave EU (blocks US-hosted model providers), HIPAA BAA required (not all providers offer this), FedRAMP-only (limits model options significantly)

---

## Domain 5: APIs and Internal Systems

- [ ] What internal systems does the AI need to read from or write to?
- [ ] Do those systems have documented, maintained APIs?
- [ ] Are any systems legacy, near end-of-life, or lacking a technical owner?
- [ ] Who is the technical contact for each integration point?

**Common blockers:** Homegrown internal tools with no docs and no owner, legacy systems with no API and IT-controlled access only

---

## Risk Scoring

After collecting answers, score each finding:

| Risk | Definition | Action |
|------|-----------|--------|
| BLOCKER | Cannot proceed without resolving this | Stop. Resolve before design. |
| HIGH | Significant delay or architectural change required | Start mitigation this week. |
| MEDIUM | Manageable with work. Adds effort but not a showstopper. | Document and assign owner. |
| LOW | Minor friction, solvable in less than a day | Add to runbook. |

---

## Overall Risk Aggregation

- Any BLOCKER present: do not commit to timeline. Resolve first.
- Two or more HIGH findings: surface to project leadership. Adjust timeline.
- One HIGH finding: start mitigation immediately. Flag in weekly status.
- MEDIUM and LOW only: document all mitigations. Proceed to design.

---

## The First Meeting Checklist

Before you leave the first customer meeting:

- [ ] All five domains covered (even partially)
- [ ] At least one technical contact identified per domain
- [ ] Any blockers identified and surfaced to the room
- [ ] Next step assigned for each HIGH risk (owner + deadline)
- [ ] Audit report sent to the customer within 24 hours

---

## Common "Surprise" Discoveries to Probe For

These are the blockers engineers discover three days before launch. Ask about them explicitly:

- "Is there any data that lives in a system with no API, only direct database access?"
- "Has your security team done a vendor review for AI model providers? What is the timeline for that?"
- "Are there any upcoming infrastructure changes, migrations, or freezes that could affect our timeline?"
- "Who has final approval for deploying a new system to production? Have they been looped in?"
- "Are there any systems we are integrating with that are currently unsupported or maintained by one person?"
