# Phase 11: The Forward-Deployed Skillset

10 lessons. ~10 hours. The part nobody teaches: the human and process skills that separate engineers who build demos from engineers who ship production AI into real customer environments.

## The through-line

95% of enterprise AI pilots fail. Not because the models are weak, but because the deployment is broken: requirements were never properly scoped, demos used synthetic data, integration blockers appeared after build, business impact was never measured, and handoffs left the customer unable to operate the system. This phase fixes all of that.

## What you build

```mermaid
graph LR
    A[FDE Role Map] --> B[Scoping Interview]
    B --> C[Discovery: Vague Ask to Spec]
    C --> D[Pattern Decision Guide]
    D --> E[Demo Prep + Testing]
    E --> F[Scope Change Playbook]
    F --> G[Integration Audit]
    G --> H[Business Impact Tracker]
    H --> I[Handoff Package Generator]
    I --> J[Stakeholder Translator]
```

## Lessons

| # | Lesson | Artifact | Time |
|---|--------|----------|------|
| 01 | What an FDE Actually Does | `prompt-fde-role-map.md` | ~45 min |
| 02 | Scoping Before Solving: Requirements Gathering | `prompt-scoping-interview-guide.md` | ~60 min |
| 03 | Discovery: Vague Ask to AI Spec | `prompt-ai-spec-template.md` | ~60 min |
| 04 | Choosing the Right Pattern | `prompt-pattern-decision-guide.md` | ~45 min |
| 05 | Demos That Survive Real Data | `skill-demo-prep-checklist.md` | ~60 min |
| 06 | Mid-Stream Scope Changes & Expectation Setting | `prompt-scope-change-playbook.md` | ~45 min |
| 07 | Integrating into a Messy Customer Environment | `skill-integration-audit-checklist.md` | ~60 min |
| 08 | Measuring Business Impact | `prompt-impact-measurement-framework.md` | ~45 min |
| 09 | Handoff: Docs, Runbooks, Teaching the Team | `skill-handoff-package-template.md` | ~60 min |
| 10 | Communicating with Non-Technical Stakeholders | `prompt-stakeholder-communication-guide.md` | ~45 min |

## Prerequisites

All prior phases. This phase assumes you can build AI systems (Phases 00-08) and focuses on the surrounding process skills. Phase 03 (Tools/MCP), Phase 04 (Agents), Phase 06 (Shipping) are most relevant.

## Stack

- Python + `anthropic` SDK (Claude as assistant in the tools)
- CLI tools built with `argparse` and `json`
- No external services required — all tools run locally
