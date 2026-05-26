---
name: prompt-scoping-interview-guide
description: Structured guide for running a customer scoping interview to convert a vague ask into a buildable AI requirement
version: "1.0"
phase: "11"
lesson: "02"
tags: [fde, scoping, requirements, discovery, interview]
---

# Scoping Interview Guide

Use this guide for live customer calls when you cannot run the CLI interactively. Print it or keep it open on a second screen. Fill in answers as the customer talks.

---

## Before the Call

- [ ] Block 30-45 minutes minimum
- [ ] Have a blank document open to capture answers
- [ ] Do not open the architecture diagram yet
- [ ] Do not propose a solution until Q5 is answered

---

## Q1: Current Process

**Primary prompt:**
"Walk me through the current manual process, step by step."

**Follow-up:**
"Roughly how many people do this, and how many times per day?"

**What to listen for:**
- Named steps (not just "we handle tickets")
- Volume numbers
- Who does the work (role, not just "the team")

**Vagueness signals:** "it depends," "varies by," "usually"
**Follow-up for vagueness:** "Can you give me the most common case?"

**Notes:**
_______________________________________________________________
_______________________________________________________________

---

## Q2: Failure Point

**Primary prompt:**
"Where does this process break down or take the most time?"

**Follow-up:**
"How long does that step take on average, per occurrence?"

**What to listen for:**
- Specific step, not just "everything"
- Time measurement (minutes, hours)
- Frequency (how often does it break)

**Missing signal:** No time number in the answer
**Flag:** "Your answer doesn't have a time estimate. Even a rough guess helps. How long?"

**Notes:**
_______________________________________________________________
_______________________________________________________________

---

## Q3: Success Metric

**Primary prompt:**
"What does success look like as a specific number in 90 days?"

**Follow-up:**
"What is the baseline today, before this system exists?"

**What to listen for:**
- A number (%, minutes, dollars, tickets/hour)
- A baseline to compare against
- A time horizon

**Vagueness signals:** "better," "faster," "more efficient," "smarter"
**Flag when vague:** "I need a number to evaluate the system. Can you say: reduce X from Y to Z?"

**Anti-pattern to avoid:**
Accepting "make it faster" as a success metric. If no number is provided, stop and measure the baseline yourself before proceeding.

**Notes:**
_______________________________________________________________
_______________________________________________________________

---

## Q4: Data Ownership

**Primary prompt:**
"Who owns the data this system needs, what format is it in, and can we get access this week?"

**Follow-up:**
"Is there an approval process? IT ticket, legal review, GDPR consideration?"

**What to listen for:**
- Named person, not "the team"
- Specific system (Zendesk, Salesforce, shared drive)
- Format (API, CSV export, database)
- Approval path

**Vagueness signals:** "we have it," "it's available," "I can get it"
**Flag when vague:** "Who specifically owns it, and how do I request access?"

**Risk:** "We have all the data" often means "I think we can get it eventually." Confirm a specific access path before starting the build.

**Notes:**
_______________________________________________________________
_______________________________________________________________

---

## Q5: Integration Point

**Primary prompt:**
"Where exactly does the AI output go, and who acts on it next?"

**Follow-up:**
"What happens if the AI output is wrong? Who catches it?"

**What to listen for:**
- Named tool or interface (Zendesk sidebar, Slack message, email draft)
- Named role (agent, manager, customer)
- Human-in-the-loop confirmation

**Vagueness signals:** "into our workflow," "the team handles it"
**Flag when vague:** "Can you name the specific screen or tool where the output appears?"

**Most commonly skipped question.** Engineers who skip this discover the constraint after building. Common surprises: the system needs a Salesforce plugin (not built), the output goes to a shared inbox the AI can't write to, the customer expected a PDF not a JSON.

**Notes:**
_______________________________________________________________
_______________________________________________________________

---

## Q6: Out of Scope (Bonus)

**Primary prompt:**
"What should this system explicitly NOT do in version 1?"

**Why ask this:**
Stakeholders often expect scope creep by default. Getting "out of scope" on paper prevents post-demo surprise conversations.

**Notes:**
_______________________________________________________________
_______________________________________________________________

---

## Scope Document Template

Fill this in after the call:

```
Problem:
  [failure point] + [time measurement] + [frequency]

Success metric:
  Reduce [X] from [baseline] to [target] within [90 days].
  Measured by: [specific data source].

Data:
  Source: [system name]
  Owner: [person name, role]
  Format: [API / CSV / database]
  Access path: [steps to get access + estimated time]

Integration point:
  Output: [what the AI produces]
  Destination: [where it goes]
  Human step: [what the human does with it]

Out of scope:
  - [item 1]
  - [item 2]

Flags / blockers:
  - [anything unresolved from the interview]
```

---

## Anti-Pattern Warning Card

Post this somewhere visible during the call:

```
STOP if you find yourself:

  Sketching architecture before Q1 is answered.
  --> The problem is not understood yet.

  Accepting "faster" or "better" as a success metric.
  --> Ask: "Can you put a number on that?"

  Assuming data access because the customer said "we have it."
  --> Ask: "Who specifically owns it, and how do I get access this week?"

  Moving to build without a confirmed integration point.
  --> Ask: "What exact tool or screen does the output land in?"
```
