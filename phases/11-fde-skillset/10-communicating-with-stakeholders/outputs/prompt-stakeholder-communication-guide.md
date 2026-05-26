---
name: prompt-stakeholder-communication-guide
description: Templates and jargon replacement guide for communicating AI project status, risks, and results to non-technical executives
version: "1.0"
phase: "11"
lesson: "10"
tags: [fde, communication, stakeholders, executive, status-update]
---

# Stakeholder Communication Guide

Use this guide every time you write an update that will be read by a non-technical executive, VP, or business owner.

---

## The Core Rule

Before sending any project communication to a non-technical stakeholder, ask:
1. Does every metric have a plain-language meaning attached?
2. Is "hallucination" replaced with a concrete description and a percentage?
3. Does the update end with a clear status (on track / at risk / blocked) or a specific ask?

If any answer is no, revise before sending.

---

## Template 1: Weekly Status Update

Maximum 250 words. Sent every Monday morning.

```
Subject: [Project Name] Week [N] Status

HEADLINE
[One sentence: the most important thing that happened or will happen this week.]

SHIPPED LAST WEEK
- [Deliverable in plain language. What changed for users or the business? Not what code was written.]
- [Second item if applicable]

SHIPPING THIS WEEK
- [Deliverable with expected date]
- [Second item if applicable]

RISKS ON THE RADAR
- [Risk name in plain language]: [what it is, what we are doing about it, when you will know more]
- None this week [if applicable]

WHAT WE NEED FROM YOU
- [Specific ask with deadline, or "No action needed this week"]
```

---

## Template 2: Risk Escalation

Use when a risk requires a business decision or executive awareness.

```
Subject: [RISK] [Project Name] - [Risk Name in Plain Language]

WHAT IS THE RISK
[One sentence: what might happen and why it matters to the business.]

IMPACT IF NOT RESOLVED
[What breaks, who is affected, when it becomes a problem.]

LIKELIHOOD
[Likely / Possible / Unlikely - and why.]

WHAT WE ARE DOING
[Current mitigation actions. Be specific.]

WHAT WE NEED FROM YOU
[Specific decision, resource, or approval needed. With a deadline.]
```

---

## Template 3: Pilot Results Summary

Use at QBRs, end-of-pilot reviews, and renewal conversations.

```
Before the AI system: [operational metric in business terms - not eval scores]
After the AI system:  [same metric with new value]
The difference:       [delta in units the business understands: hours, dollars, percentage points]

At full deployment scale of [N] [interactions/queries/transactions] per day, this projects to:
[annual or monthly business value]

The system handles [X]% of [task type] without human review.
For the remaining [Y]%, it [routes to a human / flags for review / asks a clarifying question].

What we recommend next: [specific next step or ask]
```

---

## Template 4: AI Uncertainty Framing

Never say "hallucination" to a non-technical stakeholder without the following context:

```
The system handles [X]% of questions with high confidence.
For the remaining [Y]%, it [flags the answer for human review / says it does not have enough information / routes to a support agent].
This is by design: we set a confidence threshold so the system only answers when it is reliable.
[If a specific failure mode exists]: We have identified one category where the system occasionally gives incomplete answers - [describe in one sentence]. This affects [Z]% of expected queries. Fix is [scheduled for X / already deployed].
```

---

## Template 5: Launch Readiness

```
GREEN: On track for [launch date]. [N] items remaining, all on schedule. No action needed.

YELLOW: [Specific risk] may affect [date]. Our mitigation is [action] by [date]. We will have a clearer picture by [specific day]. [Ask if needed.]

RED: [Specific blocker] has put the [date] launch at risk. We have three options:
  Option A: [description, tradeoff]
  Option B: [description, tradeoff]
  Option C: [description, tradeoff]
We recommend Option [X] because [reason]. We need your decision by [date].
```

---

## Jargon Replacement Reference

| Say This Instead | Not This |
|-----------------|----------|
| The system correctly handles X% of requests | Model accuracy is X% |
| 95% of responses arrive within N seconds | Latency p95 is Ns |
| The system occasionally generates incorrect answers | Hallucination |
| Our quality test showed... | Our eval set / RAGAS scores showed... |
| The search component | The RAG pipeline / retrieval module |
| The component that understands text meaning | The embedding model |
| Trained on your specific data | Fine-tuned |
| The question was too long to process in one step | Context window exceeded |
| Correctly answered X out of Y test questions | Precision X, Recall Y, F1 Z |
| Finds the right document X% of the time | Retrieval recall of X% |
| The AI's written instructions | The prompt / system prompt |

---

## What Not to Do

- Do not send raw eval metrics (RAGAS, F1, BLEU, p95) without translation.
- Do not use "hallucination" without a percentage and a resolution plan.
- Do not end an update with "let us know if you have any questions." End with a status or an ask.
- Do not describe infrastructure choices (pgvector, LangChain, FastAPI) in stakeholder updates.
- Do not explain uncertainty as "the model sometimes makes mistakes." Frame it as a managed confidence threshold.
- Do not skip the "WHAT WE NEED FROM YOU" section if you actually need something. Vague asks get ignored.
