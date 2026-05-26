---
name: skill-handoff-package-template
description: Four-document handoff package template for transferring operational ownership of an AI system to a customer team
version: "1.0"
phase: "11"
lesson: "09"
tags: [fde, handoff, runbook, documentation, operations]
---

# Handoff Package Template

Fill in each section before the live handoff session. All four documents must be complete before you transfer operational ownership.

---

## Document 1: System Overview

**Purpose:** What this system does, for whom, and why.

**Fill in:**

```
## System Overview: [PROJECT NAME]

### Purpose
[One paragraph: what the system does, who uses it, what problem it solves.]

### What this system does NOT do
- [Explicit non-scope item 1]
- [Explicit non-scope item 2]
- [Explicit non-scope item 3]

### Dependencies
| System | Purpose | Contact |
|--------|---------|---------|
| [e.g., Anthropic Claude API] | [Generation] | [docs URL or contact] |
| [e.g., PostgreSQL + pgvector] | [Vector storage] | [IT contact] |
| [e.g., Internal CRM API] | [Data source] | [System owner] |

### Infrastructure
- **Runs on:** [platform, region]
- **Estimated monthly cost:** $[N]
- **Scaling limit:** [N] requests/day before upgrade needed

### Ownership after handoff
- **Owner:** [Name, role, email]
- **Backup:** [Name, role, email]
```

**Completeness check:** A non-technical stakeholder should be able to understand the system's purpose and limits after reading this document.

---

## Document 2: Operational Runbook

**Purpose:** How to run the system day-to-day without calling the original team.

**Fill in:**

```
## Operational Runbook: [PROJECT NAME]

### Starting the system
1. [Step 1]
2. [Step 2]
3. [Step 3: verify it is running - what to check]

### Stopping and restarting
- To stop: [command or procedure]
- To restart: [command or procedure]
- When to restart: [list conditions, e.g., after config change, after deployment]

### Configuration
| Variable | What it does | Where it is set | Current value |
|----------|-------------|----------------|---------------|
| [VAR_NAME] | [purpose] | [location] | [value or "ask owner"] |

### Scheduled jobs
| Job | What it does | Schedule | Log location | How to verify |
|-----|-------------|----------|-------------|---------------|
| [job name] | [purpose] | [cron] | [path] | [check command] |

### Common failures

#### Failure 1: [Name]
- **Symptom:** [What the user or system sees]
- **Cause:** [Why this happens]
- **Fix:**
  1. [Step 1]
  2. [Step 2]
  3. [Verification: how to confirm it is resolved]

#### Failure 2: [Name]
[Same format]

#### Failure 3: [Name]
[Same format]

### Health check
To verify the system is working:
[Command or URL to hit, what a healthy response looks like, what an unhealthy response looks like]
```

**Completeness check:** A team member who did not build the system must be able to diagnose and fix each listed failure using this document alone.

---

## Document 3: Prompt and Model Change Guide

**Purpose:** How to safely update the AI components of the system.

**Fill in:**

```
## Prompt and Model Change Guide: [PROJECT NAME]

### When to update prompts
Update prompts when:
- [Symptom 1, e.g., users report answers are too long]
- [Symptom 2, e.g., eval faithfulness score drops below 0.80]
- [Symptom 3, e.g., model ignores context and answers from prior knowledge]

Do NOT update prompts when:
- The underlying data has changed (fix the data pipeline instead)
- One user complained (investigate before changing)

### How to update a prompt safely
1. Copy the current prompt file to a backup: `cp system_prompt.txt system_prompt.txt.bak`
2. Edit the prompt file: [path to prompt files]
3. Run the eval set: [exact command]
4. Compare the results to the baseline in [path to baseline results]
5. If results are better or equal: deploy to production
6. If results are worse: restore the backup and investigate

### Running the eval set
[Exact command, including required environment variables]
Expected output: [description of what good output looks like]
Eval set location: [path]
Baseline results: [path or score to beat]

### Interpreting eval results
| Score | Meaning | Action |
|-------|---------|--------|
| > [threshold] | Passing | Safe to deploy |
| [lower bound] to [threshold] | Marginal | Investigate before deploying |
| < [lower bound] | Failing | Do not deploy, contact original team |

### Rolling back a prompt change
1. Restore the backup: `cp system_prompt.txt.bak system_prompt.txt`
2. Restart the service: [restart command]
3. Re-run the eval set to confirm scores returned to baseline

### When to contact the original team
Contact [FDE contact] when:
- Eval scores drop below [threshold] and you cannot identify a cause
- The model starts refusing to answer certain categories of questions
- You need to change the model (not just the prompt)
- A compliance requirement changes that affects what the model can output
```

**Completeness check:** An engineer who did not build the system should be able to safely update and evaluate a prompt change using this document.

---

## Document 4: Escalation Path

**Purpose:** What to try first, when to escalate, and how.

**Fill in:**

```
## Escalation Path: [PROJECT NAME]

### Level 1: Self-service (try these first)
Before escalating, verify:
- [ ] System is running (health check: [command])
- [ ] API keys are valid and not expired
- [ ] Scheduled jobs ran successfully (check: [log location])
- [ ] Configuration has not changed unexpectedly

If the issue is in the Common Failures list (Runbook Document 2), follow that guide first.

### Level 2: Internal tech lead
Escalate to [internal owner name] when:
- You have followed the runbook and the issue is not resolved
- The issue affects multiple users simultaneously
- Data loss or corruption is suspected
- The system has been down for more than [N] minutes

**What to bring:** the symptom, what you tried, the relevant log lines, and a timestamp.

### Level 3: Original FDE team
Escalate to [FDE contact name] when:
- The issue requires changes to the model, embeddings, or core architecture
- Eval scores have dropped and you cannot identify the cause
- A new compliance or security requirement affects the system design
- Level 2 escalation has not resolved the issue within [N] hours

**Contact:** [email, Slack, phone for emergencies]
**Response time:**
- Production outage (system down): [N hours]
- Degraded performance: [N hours / next business day]
- General questions: [N business days]

### Escalation message template
Subject: [URGENT/NORMAL] [PROJECT NAME] - [brief symptom]

System: [project name]
Symptom: [what is broken or degraded]
Started at: [timestamp]
Impact: [who/what is affected]
What I tried: [steps from runbook or self-service]
Relevant logs: [paste key log lines or attach log file]

### Contacts
| Name | Role | Contact | Response Time |
|------|------|---------|---------------|
| [internal owner] | Tech Lead | [email/Slack] | [N hours] |
| [FDE name] | Original engineer | [email/Slack] | [N hours] |
```

**Completeness check:** Anyone on the customer team should be able to follow this path without needing to ask "who do I call?"

---

## Pre-Handoff Checklist

Before the live handoff session:

- [ ] All four documents are complete (no blank sections)
- [ ] The three most common failures have runbook sections
- [ ] All commands and paths in the runbook have been tested on the production system
- [ ] API keys and contact information are current
- [ ] The customer tech lead has been named in all four documents
- [ ] The escalation path has specific response times, not "as soon as possible"

## Live Handoff Session Agenda (~2 hours)

1. Walk through each document together (30 min)
2. Customer team runs the system and simulates a failure using only the runbook (45 min)
3. Update the runbook for every question that needed your help in step 2 (30 min)
4. Confirm escalation path and your post-handoff availability (15 min)
