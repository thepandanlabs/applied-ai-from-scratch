# Handoff: Docs, Runbooks, Teaching the Team

> A handoff where you answer questions afterward is a failed handoff.

**Type:** Build
**Languages:** Python
**Prerequisites:** 11-07 (messy customer environment), 06-01 (shipping basics)
**Time:** ~60 min
**Phase:** 11 · FDE Skillset

---

## Learning Objectives

- List the four documents in a complete handoff package and explain what each one covers
- Identify the three most common failures a customer team will encounter without a runbook
- Build a HandoffPackageGenerator that drafts all four documents from a project template
- Run a completeness check on a generated handoff package
- Measure whether a handoff succeeded: can the team diagnose the three most common failures without calling you?

---

## The Problem

You built a solid AI system. It is deployed, the customer accepted it, and the engagement is wrapping up. You spend the last two days writing a handoff document: a Word file with a system overview, some screenshots, and a section called "FAQ."

Three weeks later, the customer calls. Their scheduled job for re-ingesting documents stopped working. Nobody on their team knows how to restart it. The person who knows the system is you, and you are now on a different engagement.

This is not a customer support problem. It is a handoff failure. The runbook did not cover the most common operational issue. The team was not trained to diagnose it. The escalation path pointed to a Slack channel you are no longer monitoring.

A handoff is not a document. It is a transfer of operational ownership. The measure of success is binary: can the customer's team run, diagnose, and repair the system without you? If not, the handoff was incomplete regardless of how many pages the document has.

The four-part handoff package exists to close the gap systematically.

---

## The Concept

### The Four-Part Handoff Package

```
DOCUMENT 1: SYSTEM OVERVIEW
  What it does, what it does not do, what it needs to run.
  Audience: anyone who needs to understand the system at a high level.
  Key sections:
    - Purpose and scope (one paragraph)
    - What the system does NOT do (explicit)
    - Dependencies: external APIs, internal systems, data sources
    - Infrastructure: where it runs, what it costs per month
    - Owner after handoff: name, role, contact

DOCUMENT 2: OPERATIONAL RUNBOOK
  How to run it day-to-day.
  Audience: the person who will operate the system.
  Key sections:
    - How to start, stop, and restart the system
    - Configuration: all environment variables, where they are set
    - Scheduled jobs: what they do, when they run, how to check if they ran
    - The 5 most common failures and how to fix each one
    - How to check system health without reading code

DOCUMENT 3: PROMPT AND MODEL CHANGE GUIDE
  How to update the AI components safely.
  Audience: the engineer who will maintain the system.
  Key sections:
    - How to update a prompt (the safe way)
    - How to run the eval set before deploying a change
    - How to interpret eval results and decide whether to deploy
    - How to roll back if a prompt change degrades quality
    - When to contact the original team vs. handle it yourself

DOCUMENT 4: ESCALATION PATH
  What to try first, when to escalate, who to contact.
  Audience: everyone on the customer team.
  Key sections:
    - Level 1: things to try before escalating (restart, check logs, check config)
    - Level 2: when to involve the internal tech lead
    - Level 3: when to contact the original FDE team
    - Contact information: email, Slack, response time expectations
    - What to include in an escalation message (symptoms, logs, what you tried)
```

### The Four Documents and Their Audiences

```
+--------------------------+---------------------------+---------------------------+
| DOCUMENT                 | PRIMARY AUDIENCE          | ANSWERS THE QUESTION      |
+--------------------------+---------------------------+---------------------------+
| 1. System Overview       | Anyone new to the system  | What does this do?        |
+--------------------------+---------------------------+---------------------------+
| 2. Operational Runbook   | The system operator       | How do I run and fix it?  |
+--------------------------+---------------------------+---------------------------+
| 3. Prompt Change Guide   | The maintaining engineer  | How do I update the AI?   |
+--------------------------+---------------------------+---------------------------+
| 4. Escalation Path       | Everyone                  | Who do I call and when?   |
+--------------------------+---------------------------+---------------------------+
```

### The Handoff Completeness Test

```
A handoff is complete if and only if:

  The customer team can diagnose and fix the 3 most common failures
  without calling you.

Determine the 3 most common failures from your own knowledge of the system.
For each one, verify:
  [x] The runbook has a section for this failure
  [x] The section names the symptom, the cause, and the fix
  [x] A team member who did not build the system can follow the fix

If any of the three fails this test, the runbook is incomplete.
```

### The Live Handoff Session

A handoff document delivered by email is worth 20% of a live handoff session.

```
LIVE HANDOFF SESSION FORMAT (~2 hours)

1. Walk through each document (30 min)
   - You present, they ask questions
   - Do not read the doc out loud: explain the reasoning behind each section

2. They run it themselves, you watch (45 min)
   - They restart the system using only the runbook
   - They simulate the most common failure and fix it using only the runbook
   - You do not help unless they are completely stuck

3. Q&A and gap closing (30 min)
   - For every question that needed your help in step 2, update the runbook
   - That question is a runbook gap

4. Confirm escalation path (15 min)
   - Who do they call first? Second? When?
   - Confirm your availability and response time after handoff
```

---

## Build It

### Step 1: Setup

```python
# pip install anthropic
# Set ANTHROPIC_API_KEY in environment

import argparse
import json
import os
import sys
from dataclasses import dataclass

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
```

### Step 2: The Project Template

```python
@dataclass
class ProjectTemplate:
    project_name: str
    system_description: str          # what it does
    what_it_does_not_do: str         # explicit non-scope
    external_dependencies: str       # APIs, services
    infrastructure: str              # where it runs, estimated cost
    scheduled_jobs: str              # cron jobs, pipelines
    common_failures: str             # top 3-5 known failure modes
    prompt_files: str                # where prompts live
    eval_command: str                # how to run evals
    fde_contact: str                 # name and contact for escalation
    customer_tech_lead: str          # internal owner after handoff
```

### Step 3: Document Generators

```python
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
```

### Step 4: Completeness Checker

```python
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
}}"""


def check_completeness(template: ProjectTemplate, package: dict[str, str]) -> dict:
    """Run a completeness check on the handoff package."""
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
```

### Step 5: Main Package Generator

```python
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
        ("03-prompt-change-guide.md", PROMPT_CHANGE_GUIDE_PROMPT, "Prompt Change Guide"),
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
```

> **Real-world check:** The customer's CTO says: "We do not need all of this documentation. Our engineers are smart, they will figure it out." How do you explain that handoff documentation is not about engineer intelligence, but about reducing time-to-diagnosis from hours to minutes when something breaks at 2 a.m. and the original team is unavailable?

---

## Use It

Run the generator on a sample RAG service project:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --demo --output ./handoff-package
```

This generates four markdown files in `./handoff-package/`. Review each one and check:
- Does the system overview clearly state what the system does NOT do?
- Does the runbook cover all three listed common failures?
- Does the prompt change guide include exact eval commands?
- Does the escalation path include specific response time expectations?

Then run the completeness check:

```bash
python main.py --demo --check
```

To use with your own project, create a `project.json` file matching the project template fields and run:

```bash
python main.py --from-json project.json --output ./handoff-package
```

> **Perspective shift:** A junior engineer says: "I documented everything in the code comments. The runbook is redundant." How do you explain the difference between code documentation (for engineers modifying the system) and operational documentation (for engineers running the system), and why the audience is completely different?

---

## Ship It

The output for this lesson is `outputs/skill-handoff-package-template.md`. It is a ready-to-fill template for all four handoff documents that you can use at the end of any engagement.

The runnable tool is `code/main.py`:

```bash
python main.py --demo --output ./handoff-package
python main.py --demo --check
```

---

## Evaluate It

**Check 1: The three-failure test.**
After generating the runbook, identify the three most common failures for the demo project (ingestion job failure, API key expiration, prompt quality degradation). Check that the runbook has a dedicated section for each one with a clear symptom-cause-fix structure. If any failure is missing, the handoff is incomplete.

**Check 2: Completeness score.**
Run the completeness checker. A score below 75 means significant gaps. A score above 90 means the package is ready for a live handoff session. If your score is below 75, check the missing items list and address them.

**Check 3: The non-builder test.**
Give the generated runbook to a colleague who did not build the system. Ask them to follow the "restart the system" instructions and fix one simulated failure. If they need more than 3 minutes of help from you, there is a gap in the runbook.

**Check 4: Does the escalation path have concrete contact information?**
An escalation path with "contact the FDE team" and no email, no response time, and no guidance on what to include in the message is not a usable escalation path. Verify the generated document has all four elements: who, how, when, and what to include.
