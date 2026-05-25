# /frame-it — FDE Scoping Playbook

Run this playbook when a learner has a vague AI request and needs to turn it into a buildable spec.

---

## Purpose

Practice the most important FDE skill: converting a vague stakeholder ask into a concrete, scoped AI system spec. This is the Phase 11 skill applied as an exercise. The learner brings a real (or realistic) ask; the playbook guides them through scoping it into something buildable and measurable.

This playbook is both a teaching tool (use it while studying Phase 11) and a working tool (use it on real projects before building anything).

---

## Usage

`/frame-it` with no args: guide the learner to describe their situation first.
`/frame-it "we want AI to handle customer support"`: start with the provided ask.

---

## Playbook

Work through four stages. One stage at a time. Within each stage, ask one question at a time.

---

## Stage 1 - Surface the real ask

The stated ask is almost never the real ask. Find it.

Start with:
> "Tell me about the ask. Who made it, what did they actually say (as close to verbatim as you can), and what problem are they trying to solve?"

Then probe:

- "What does success look like to them in 6 months? Not the AI feature - the business outcome."
- "What are they doing today without AI? What's slow, expensive, or broken about it?"
- "Who are the users of this system - the people who will actually interact with it day-to-day?"
- "Is there a deadline or event driving this?"

Stop probing when you can articulate: what pain, for whom, by when, measured how.

---

## Stage 2 - Scope the first deliverable

A scoped deliverable is 4-6 weeks of work, demonstrates clear value, and is reversible if it fails.

Ask:
> "If you had to ship something useful in 4 weeks, what's the smallest slice that would prove the idea works?"

Then probe:

- "What data do you have access to right now, today? Not what you'll get - what exists?"
- "What does 'good enough' look like for a pilot? Not perfect - good enough to get approval to continue."
- "What could go wrong that would kill the project? What's the riskiest assumption?"
- "Who needs to approve this before it goes to users?"

Stop probing when you have: a concrete artifact, a data source, a success criterion for the pilot.

---

## Stage 3 - Pick the pattern

Map the scoped deliverable to one (or two) of the core AI system patterns. Don't let the learner reach for agents when a prompt chain will do.

Present the decision framework:

```
Is the output predictable format + known inputs?
  Yes: structured prompt (Phase 01)

Is the output grounded in a document corpus?
  Yes: RAG (Phase 02)

Does the system need to call external tools or APIs?
  Yes: tool use / function calling (Phase 03)
  If those tools are multi-step with branching: agents (Phase 04)

Does accuracy need to be measurable and improvable over time?
  Always yes: add eval harness (Phase 05)
```

Ask:
> "Based on this framework, which pattern fits? Walk me through your reasoning."

Probe if they pick agents too quickly:
> "Could you solve 80% of this with RAG + one tool call instead of a full agent loop? What would you lose?"

Stop when the learner can name the pattern and justify it.

---

## Stage 4 - Define the spec

The output of /frame-it is a one-page spec. Build it together.

Ask the learner to fill in each field. Fill it in with them:

```markdown
## AI Spec

**Problem statement:** [one sentence - the pain, not the solution]

**Users:** [who interacts with the system]

**Pattern:** [RAG | tool use | agent | prompt chain | structured extraction]

**Input:** [what does the system receive]

**Output:** [what does the system return, in what format]

**Data sources:** [what exists today that the system uses]

**Success metric (pilot):** [how you know the pilot worked - a number, not "users are happy"]

**Success metric (production):** [the production SLO - latency, accuracy, cost per query, etc.]

**Out of scope (v1):** [what you are explicitly NOT building in the first version]

**Riskiest assumption:** [the one thing that, if wrong, kills the project]

**Next step:** [the first concrete action, this week]
```

---

## Output format

After Stage 4, output the completed spec in a markdown code block. Then add:

> **FDE check:** Before you build, verify two things:
> 1. Can you get the data listed in "Data sources" today, without waiting on anyone?
> 2. Is your "success metric (pilot)" something you can measure in 4 weeks with the tools you have?
>
> If either answer is no, go back to Stage 2 before writing any code.

---

## Example session

**Learner:** "My company wants to use AI to make our sales team more productive."

**Stage 1 probe:** "Who made this ask? What did they actually say?"
**Learner:** "The VP of Sales said 'I want AI to help reps write proposals faster.'"

**Stage 1 probe:** "What does a proposal look like today? How long does it take to write one?"
**Learner:** "It's a 5-page doc. Reps spend 3-4 hours per proposal, mostly copying from past proposals and editing."

**Stage 1 result:** Pain is clear: 3-4 hours per proposal, mostly copy-paste from past proposals.

**Stage 2:** "What data do you have today?" 
**Learner:** "We have 200 past proposals in Google Drive, all PDFs."

**Stage 2:** "What's the smallest useful thing in 4 weeks?"
**Learner:** "A tool that takes a customer name and deal type, finds relevant past proposals, and drafts a first version."

**Stage 3 result:** Pattern = RAG (corpus of past proposals) + structured extraction (fill in template fields).

**Spec output:**
```markdown
## AI Spec

**Problem statement:** Sales reps spend 3-4 hours per proposal copying from past proposals.

**Users:** Sales reps (20 people)

**Pattern:** RAG + structured extraction

**Input:** Customer name, deal type, deal size, key requirements (rep fills a short form)

**Output:** Draft proposal (markdown → PDF), 5 sections, pre-filled from similar past deals

**Data sources:** 200 past proposals in Google Drive (PDFs, accessible today)

**Success metric (pilot):** Rep reviews draft and says it saved >1 hour on 80% of test proposals (n=10)

**Success metric (production):** Proposal draft time under 30 minutes; rep edits under 20% of content

**Out of scope (v1):** Auto-sending proposals, CRM integration, pricing calculator

**Riskiest assumption:** Past proposals are clean enough to retrieve from (PDFs may not parse well)

**Next step:** Pull 10 proposals, test PDF extraction, check if text is machine-readable
```
