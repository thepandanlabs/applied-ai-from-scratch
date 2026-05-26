# Scoping Before Solving

> "We want AI" is not a requirement. Your job is to extract one.

**Type:** Build
**Languages:** Python
**Prerequisites:** 11-01 What an FDE Actually Does
**Time:** ~60 min
**Phase:** 11 - FDE Skillset

## Learning Objectives

- Identify the 5 scoping questions that convert a vague ask into a buildable requirement
- Recognize the 3 most common scoping anti-patterns and their consequences
- Build a ScopingInterview CLI that runs a structured customer interview and produces a scope document
- Apply the CLI to a realistic customer scenario and produce a scope document in under 30 minutes
- Explain why the integration point question is the one most commonly skipped

---

## The Problem

A customer says: "We want AI to help our support team." You nod, open your laptop, and start scaffolding a support bot. Three weeks later, you demo a working ticket classifier with auto-drafted responses. The customer says it looks great. Then they ask: "How does it plug into Zendesk?"

You don't have an answer. Zendesk has an API, but the customer's plan doesn't include API access. Their tickets are stored in a shared Gmail inbox. The data you need is locked behind an OAuth flow that requires their IT team's approval, which takes two weeks. Your demo works. Your integration does not. The pilot is paused.

This is a scoping failure. The Zendesk question is not a technical surprise: it's a question that should have been asked on day one. The scoping interview exists to surface these blockers before you write a line of code. Developers who skip it build the right system for the wrong environment.

---

## The Concept

### From Vague Ask to Scoped Requirement

The compression that happens at each question:

```
Customer input           Question asked               Output

"We want AI to           "What is the current    --> "Support agents spend
help our support         process step that            4 hours/day manually
team"                    takes the most time?"        triaging Tier 1 tickets"

"Reduce how long         "What does success      --> "Reduce Tier 1 first
it takes"                look like in a               response time from
                         number?"                     4 hours to 30 minutes"

"We have all our         "Who owns the data,     --> "Gmail shared inbox,
ticket history"          and what format              IT approval needed
                         is it in?"                   for OAuth access"

"It should connect       "Where exactly does     --> "Agent drafts response
to our workflow"         the output go and            in Gmail, human
                         who acts on it?"             reviews before send"

"We don't want it        "What is explicitly     --> "No auto-send.
to do everything"        out of scope?"               No Tier 2 routing.
                                                       No Spanish language."
```

Each question compresses uncertainty. By question 5, you have a buildable, measurable, integration-confirmed requirement.

### The 5 Scoping Questions

```
Q1: CURRENT PROCESS
    "Walk me through the current manual process, step by step."
    Goal: Understand what you are replacing or augmenting.
    Anti-pattern: Skipping this and assuming you understand the domain.

Q2: FAILURE POINT
    "Where does this process break down or take too long?"
    Goal: Find the pain point worth solving.
    Anti-pattern: Accepting "everything takes too long" as an answer.

Q3: SUCCESS METRIC
    "What does success look like as a specific number in 90 days?"
    Goal: Establish the eval criterion before the build starts.
    Anti-pattern: Accepting "faster" or "better" without a number.

Q4: DATA OWNERSHIP
    "Who owns the data the system needs, in what format, and can we
     get access this week?"
    Goal: Surface data blockers before they become timeline killers.
    Anti-pattern: Assuming access because the customer offered to "share."

Q5: INTEGRATION POINT
    "Where exactly does the AI output go, and who acts on it next?"
    Goal: Confirm the output lands somewhere usable.
    Anti-pattern: Skipping this because "we'll figure out integration later."
```

### The 3 Scoping Anti-Patterns

```
Anti-pattern            Symptom                     Consequence
---------------------   -------------------------   -----------------------
Jumping to solution     You sketch an architecture  You build the wrong
                        before Q1 is answered       thing. Correctly.

Accepting vague         Success = "make it          You have no eval
success criteria        smarter / faster"           criterion. The demo
                                                    "looks good" and no
                                                    one can prove it works.

Assuming data access    "We have all the data"       Week 2 blocker: IT
                        without confirming           approval, format mismatch,
                        format and access path       or GDPR restriction
```

---

## Build It

Build a `ScopingInterview` CLI that runs through the 5 question areas, captures answers, and produces a structured scope document in both JSON and human-readable formats.

The tool prompts for each question area with follow-up prompts if the answer is too vague. It detects common anti-pattern responses (answers with no number for Q3, answers with no data owner name for Q4) and flags them.

```python
# Key structure: each question area has a primary prompt,
# a vagueness detector, and a follow-up

QUESTION_AREAS = [
    {
        "id": "current_process",
        "label": "Current Process",
        "prompt": "Walk me through the current manual process, step by step.",
        "follow_up": "Roughly how many people do this, and how many times per day?",
        "vague_signals": ["it depends", "varies", "sometimes"],
        "vague_follow_up": "Can you give me the most common case, even if it's not universal?",
    },
    # ... 4 more
]
```

Run the interview:

```bash
python main.py
python main.py --output scope-document.json
```

Sample output:

```
=== SCOPING INTERVIEW ===
This interview takes 15-20 minutes. Answer as specifically as possible.
Vague answers will be flagged for follow-up.

--- CURRENT PROCESS ---
Walk me through the current manual process, step by step.
> Agents read incoming tickets, categorize them, and write a response.

Roughly how many people do this, and how many times per day?
> 8 agents, about 200 tickets per day total.

--- FAILURE POINT ---
Where does this process break down or take the most time?
> Categorization takes too long, especially for new agents.

[FLAG] Your answer does not include a time estimate.
How long does categorization take on average, per ticket?
> About 8 minutes per ticket for new agents, 2 minutes for experienced ones.

...

=== SCOPE DOCUMENT ===

Problem:
  Ticket categorization takes 8 min/ticket for new agents (vs. 2 min for
  experienced agents). With 200 tickets/day, new agents account for 30%
  of volume = 480 agent-minutes/day on categorization alone.

Success metric:
  Reduce average categorization time for new agents to under 3 minutes
  within 60 days of deployment.

Data: Zendesk tickets, owned by Support Ops (Maria Chen).
  Access path: Zendesk API, IT approval required (2-3 days).
  Format: JSON via REST API, 18 months of history available.

Integration point:
  AI suggests category in Zendesk sidebar. Agent confirms or overrides.
  No auto-assignment without human review.

Out of scope:
  Response drafting, Tier 2 routing, Spanish language support.
```

> **Real-world check:** You run the scoping interview and the customer gives a vague answer to Q3: "We just want it to be faster." The tool flags it. You ask for a number. The customer says: "I don't know what number to give you." What does this tell you? It tells you the customer does not have a baseline measurement. There is no timer on the current process. This is a scoping blocker, not a rounding error. Your next action is to observe the process for 30 minutes and measure it yourself, or ask the customer to run a 1-week measurement exercise before you scope the build. Building without a baseline means you cannot prove the system worked.

The full implementation is in `code/main.py`. It handles multi-line inputs, vagueness detection, follow-up logic, and produces a structured JSON scope document plus a markdown summary.

---

## Use It

Apply the ScopingInterview to the scenario: "We want AI to help our support team respond faster."

Run:
```bash
python main.py --output support-scope.json
```

Walk through each question area with realistic answers:

- **Current process:** Agents manually read, categorize, and respond to Zendesk tickets. 10 agents, 300 tickets/day.
- **Failure point:** First response time averages 4 hours for Tier 1. SLA is 2 hours. Missing SLA 40% of the time.
- **Success metric:** Reduce Tier 1 first-response time from 4 hours to under 2 hours. Hit SLA 90% of the time.
- **Data:** Zendesk, owned by Head of Support (James Li). API access available with admin key. 2 years of ticket history.
- **Integration point:** AI drafts response in Zendesk reply box. Agent edits and sends. No auto-send.
- **Out of scope:** Tier 2 tickets, billing inquiries, non-English tickets.

The tool produces:

```json
{
  "problem": "Tier 1 first-response time averages 4 hours against a 2-hour SLA. Missing SLA 40% of the time across 300 tickets/day.",
  "success_metric": "Reduce Tier 1 first-response time to under 2 hours. Achieve SLA compliance rate of 90% within 60 days.",
  "data": {
    "source": "Zendesk",
    "owner": "James Li, Head of Support",
    "access": "Admin API key available",
    "volume": "2 years of ticket history"
  },
  "integration_point": "AI draft in Zendesk reply box. Agent reviews and sends. No auto-send.",
  "out_of_scope": ["Tier 2 tickets", "billing inquiries", "non-English tickets"],
  "flags": []
}
```

No flags. This is a clean scope. Now you can build.

> **Perspective shift:** A product manager reading this scope document might say it looks like a standard requirements doc. It is, but with one difference: the success metric is the eval criterion. When you build the eval harness in Phase 05, the question is not "does the output look reasonable?" but "does average first-response time drop below 2 hours on a 100-ticket holdout set?" The scoping interview plants the seed for the eval before the first line of code is written. Requirements docs that don't do this produce systems that can't be measured and therefore can't be improved.

---

## Ship It

The reusable artifact for this lesson is `outputs/prompt-scoping-interview-guide.md`: a structured guide to running a scoping interview manually (without the CLI), with the 5 questions, follow-up prompts, vagueness signals, and anti-pattern warnings. Use it for customer calls when you can't run the CLI interactively.

---

## Evaluate It

How to know the scoping interview is working:

1. **Scope document produced before build starts** - the simplest check. If engineers start building before there is a written scope document with a success metric, the interview didn't happen. Measure the gap between engagement start and first scope document commit.

2. **Success metric specificity score** - review scope documents for metric quality: does it have a number, a baseline, a time horizon, and a data source? A metric like "reduce response time by 50% within 60 days measured via Zendesk average" scores 4/4. "Make it faster" scores 0/4.

3. **Data access confirmed before week 1 ends** - track whether data access was confirmed (tested, not just promised) before the first build cycle begins. Unconfirmed data access at the end of week 1 predicts a week 2 blocker with 80%+ reliability.

4. **Integration point confirmed before prototype** - check whether the output destination was confirmed before the prototype was built. Engineers who discover the integration constraint after building waste an average of 3-5 days rebuilding output format.
