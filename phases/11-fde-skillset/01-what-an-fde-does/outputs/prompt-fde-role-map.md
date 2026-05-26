---
name: prompt-fde-role-map
description: Reference card mapping the 5 FDE engagement phases to competencies, red flags, and key questions
version: "1.0"
phase: "11"
lesson: "01"
tags: [fde, engagement, lifecycle, scoping, handoff]
---

# FDE Engagement Phase Reference Map

Use this card at the start of an engagement to orient yourself, or share it with a new FDE joining your team.

---

## Phase 1: Discover

**Duration:** 1-2 days
**Goal:** Understand the current state before proposing anything.

Key questions:
- What is the current manual process?
- Who does it today and how long does it take?
- What breaks most often?
- Who are the stakeholders and who makes the final decision?

Red flags:
- Customer jumps to solution before you've understood the problem
- You find yourself nodding along without capturing specifics
- No access to actual process documentation or examples

Output: Written discovery notes with a 1-sentence problem hypothesis.

---

## Phase 2: Scope

**Duration:** 1-3 days
**Goal:** Turn the problem hypothesis into a measurable requirement.

Key questions:
- What does success look like in a number (not a feeling)?
- Who owns the data the system needs?
- Where does this system plug into the existing workflow?
- What is explicitly out of scope?

Red flags:
- "Make it smarter" is the stated requirement
- No baseline measurement exists (you can't prove improvement)
- Data access is assumed, not confirmed

Output: Written AI spec with problem statement, success metric, I/O contract, and out-of-scope list.

---

## Phase 3: Build

**Duration:** 1-3 weeks
**Goal:** Working prototype on real customer data with a measured eval score.

Key questions:
- Have you run on 20+ real samples?
- What is the failure rate and where do failures cluster?
- Are you building toward the success metric or toward elegance?

Red flags:
- Still using synthetic data after day 5
- No eval harness (you're checking outputs by eye)
- Architecture discussions consuming more time than customer data testing

Output: Working demo with measured failure rate, latency, and eval score against the success metric.

---

## Phase 4: Validate

**Duration:** 2-5 days
**Goal:** Confirm with the customer that the system meets the success metric.

Key questions:
- Will the customer run the demo on their own machine with their own data?
- Have you tested at least 5 edge cases?
- Does the output format match what the customer expected?

Red flags:
- Demo uses your data, not theirs
- Output format confirmed only verbally
- Latency fine on your examples, untested on long inputs

Output: Validation report with pass/fail against success metric and documented edge cases.

---

## Phase 5: Hand Off

**Duration:** 1-2 weeks
**Goal:** Transfer ownership cleanly so the system runs without you.

Key questions:
- Who is the named owner at the customer organization?
- Can they restart the system from the runbook without calling you?
- Is the baseline metric recorded so improvement can be measured?

Red flags:
- Handoff recipient not identified until the last week
- Runbook written by you but never walked through with the recipient
- No escalation path documented for model failures or data drift

Output: Deployed system (or packaged handoff), runbook, architecture diagram, success metric baseline.

---

## Competency Quick Scores

Score yourself 1 (not started) to 4 (complete and confirmed) for each:

| Competency       | 1              | 2               | 3               | 4                    |
|------------------|----------------|-----------------|-----------------|----------------------|
| Scoping          | No requirement | Verbal only     | Written, unconfirmed | Written + customer sign-off |
| Technical Depth  | Synthetic only | Few real samples | 20+ samples, manual | 20+ samples, automated eval |
| Demo Quality     | Hardcoded      | Synthetic data  | Real data, untested | Real data, tested |
| Communication    | Ad hoc         | Verbal updates  | Written irregular | Written regular cadence |
| Handoff          | Not discussed  | Owner named     | Owner briefed   | Dry-run completed |

Any score of 1 in the week before a customer milestone is a blocker, not a gap.
