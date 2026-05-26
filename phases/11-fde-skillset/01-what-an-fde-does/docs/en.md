# What an FDE Actually Does

> Your deliverable is not code. It is a customer outcome.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Completion of at least one prior phase
**Time:** ~45 min
**Phase:** 11 - FDE Skillset

## Learning Objectives

- Describe the 5-phase FDE engagement lifecycle and the key output of each phase
- Distinguish an FDE role from a backend engineer role in terms of success metrics
- Identify the pilot-to-production gap and explain why it kills AI projects
- Build a self-assessment CLI that scores FDE competencies across an active engagement
- Recognize the tradeoffs FDEs make between code quality and demo velocity

---

## The Problem

You've been building AI systems for months. Your code is clean, your evals look solid, and you can wire up a RAG pipeline in under an hour. Now you're told you're joining a Forward-Deployed Engineering team, or your company is putting you in front of customers to scope and build AI pilots.

The job description sounds familiar. In practice, it is a different role.

A backend engineer ships code that other engineers depend on. An FDE ships outcomes that customers are willing to pay for. The measurement changes everything. You can write the most elegant LLM orchestration pipeline and lose the customer because you demo'd on synthetic data, the integration point wasn't confirmed before the build, or you spent three weeks on infrastructure before proving the core use case worked on their data.

The pilot-to-production gap is the gap between "this looks great in a controlled demo" and "this is running in our system handling real volume." Most AI pilots die in that gap, not because the AI was bad, but because the FDE didn't have the skills to bridge it. Those skills are learnable. This lesson maps them.

---

## The Concept

### The 5-Phase FDE Engagement Lifecycle

Every customer engagement follows the same shape, regardless of the AI use case. Durations shift; the phases don't.

```
Phase        Duration     Key Activities                 Deliverable
-----------  -----------  -----------------------------  -----------------
DISCOVER     1-2 days     Customer calls, process        Discovery notes,
                          observation, stakeholder       problem hypothesis
                          mapping

SCOPE        1-3 days     Requirements extraction,       Written AI spec:
                          success metric definition,     problem + metric +
                          data audit, integration        I/O contract
                          point confirmation

BUILD        1-3 weeks    Rapid prototype, eval          Working demo on
                          harness, iteration on          customer data with
                          customer feedback              eval score

VALIDATE     2-5 days     Demo on real data, edge case   Validation report,
                          testing, latency measurement,  go/no-go decision
                          stakeholder sign-off

HAND OFF     1-2 weeks    Documentation, runbook,        Deployed system or
                          handoff to product/eng,        handoff package
                          success metric baseline
```

The pilot-to-production gap lives between VALIDATE and HAND OFF. An FDE who skips validation hands off a system the receiving team cannot operate, debug, or improve. The customer churns.

### FDE vs. Backend Engineer

```
                BACKEND ENGINEER        FDE
                ----------------        ---
Measured by:    Code merged             Customer outcome
Facing:         Internal team           Customer stakeholders
Cadence:        Sprint velocity         Engagement milestones
Output:         Working software        Working software + alignment
Risk if wrong:  Bug ticket              Lost deal, churned pilot
Planning unit:  Story point             Discovery call
```

FDEs write production-quality code. But code quality is table stakes, not the job. The job is diagnosing the right problem, scoping a build that can succeed in 2-3 weeks, validating on real data before the demo, and handing off something the customer's team can own.

### The Pilot Killer: Optimizing the Wrong Thing

The most common FDE failure: spending week one on clean architecture when week one should prove the core hypothesis on customer data.

The correct tradeoff:
- Week 1: Prove it works on their data (quick, disposable prototype)
- Week 2: Build it properly (production patterns, eval harness)
- Week 3: Validate, document, and hand off

Engineers trained on code quality instincts reverse this order. They build the clean architecture first, then try to demo it on customer data in week three. By then, there is no time to fix the three edge cases that show up.

---

## Build It

Build a self-assessment CLI that asks 10 questions about your current engagement and scores you across 5 FDE competencies: Scoping, Technical Depth, Demo Quality, Communication, and Handoff Readiness.

The questions are drawn from the 5-phase lifecycle above. Each answer maps to a score. The output is a per-competency percentage and a concrete action item.

```python
# Abbreviated view of the question structure
QUESTIONS = [
    {
        "id": "q1",
        "competency": "Scoping",
        "text": "Do you have a written success metric confirmed by the customer?",
        "options": [...],
        "scores": {"A": 4, "B": 2, "C": 1, "D": 0},
    },
    # ... 9 more questions across the 5 competencies
]
```

Run the assessment:

```bash
python main.py
python main.py --export results.json
```

Sample output:

```
=== FDE Self-Assessment ===

[Scoping] Do you have a written success metric confirmed by the customer?
  A. Yes, written and customer-confirmed
  B. Discussed but not written
  C. General direction, no number
  D. Not yet
Your answer: B

...

================================================
FDE SELF-ASSESSMENT RESULTS
================================================

Overall readiness: 58%
Status: DEVELOPING: Gaps to address before next milestone.

Competency breakdown:
  Scoping          [#####-----] 50%
    Advice: Write down your success metric and get customer sign-off.
  Technical Depth  [######----] 62%
    Advice: Add an automated eval harness.
  Demo Quality     [#######---] 75%
    Advice: Solid. Run one more rehearsal with realistic edge cases.
  Communication    [####------] 50%
    Advice: Move to written updates. Verbal-only creates alignment gaps.
  Handoff          [##--------] 25%
    Advice: Identify your handoff recipient this week.
```

> **Real-world check:** You're 10 days into an engagement. You've been coding every day and have a working prototype. You run the self-assessment and score 25% on Handoff. The customer milestone is in 4 days. What does this tell you, and what should you do today? The score tells you that no one at the customer's organization knows who will own this system after you leave. That is not a documentation problem, it is a customer success risk. Today's action: email the customer and ask them to name the owner of this system. Everything else can wait.

The full implementation is in `code/main.py`. It is a complete CLI with argument parsing, per-competency scoring, and optional JSON export.

---

## Use It

Apply the self-assessment to a hypothetical engagement to see how the scores surface different risk profiles.

**Scenario A: The over-builder**

An engineer is 2 weeks into a pilot. They have a clean microservices architecture, a well-documented API, and thorough unit tests. They have not yet gotten real customer data samples and have no eval harness. The demo next week uses synthetic data.

Run the assessment for this engineer:
- Technical Depth: low (no real data, no evals) = 12%
- Demo Quality: low (synthetic data) = 0%
- Scoping: probably OK if they started well
- Communication: medium
- Handoff: unknown

The tool flags Technical Depth and Demo Quality as critical gaps. The advice: stop building new features and spend today on getting 20 real customer samples. Delay the demo if needed.

**Scenario B: The strong FDE**

An engineer is 10 days into a similar pilot. They have a rough prototype (it's scrappy), but they've run it on 40 real customer samples, have a failure rate and latency number, and have confirmed the output format with the customer. They've sent two written updates and already asked the customer who will own the system.

Assessment results:
- Technical Depth: high (real data, measured)
- Demo Quality: high (real data confirmed)
- Communication: high (written updates)
- Handoff: medium (recipient identified, not briefed yet)
- Scoping: needs check

The tool tells them one thing to fix: schedule a handoff briefing. Everything else is on track.

> **Perspective shift:** A backend engineer reading scenario A might see a disciplined team doing things right: clean code, tests, documented API. The FDE lens inverts this. The demo using synthetic data is the failure, not the missing docs. Success metric for the FDE role: pilot converts to production. A scrappy prototype that works on customer data converts. A beautiful architecture that the customer never saw run on their data does not.

---

## Ship It

The reusable artifact for this lesson is `outputs/prompt-fde-role-map.md`: a reference card mapping the 5 FDE phases to competencies, typical red flags, and the questions to ask at each stage. Use it during onboarding, when joining a new engagement, or to calibrate expectations with a customer.

---

## Evaluate It

How to know this lesson's concepts are working in practice:

1. **Pilot conversion rate** - the clearest signal. FDEs who internalize the lifecycle convert more pilots to production. Track ratio of pilots that reach production vs. pilots abandoned post-demo.

2. **Time-to-first-real-data** - measure how many days into an engagement before the prototype runs on real customer data. Target: under 5 days. An engineer running the self-assessment early will notice Technical Depth gaps before they become blockers.

3. **Handoff recipient named before week 2** - a process metric that predicts handoff success. If the customer can't name the system owner in week 2, the pilot is at risk regardless of technical quality.

4. **Self-assessment score trend** - run the assessment at the start, middle, and end of an engagement. The score should rise. A flat or declining score in week 3 signals a problem that needs escalation, not more code.
