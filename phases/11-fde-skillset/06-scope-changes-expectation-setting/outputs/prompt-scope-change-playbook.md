---
name: prompt-scope-change-playbook
description: Playbook for receiving, classifying, and responding to mid-stream scope change requests in AI engineering engagements
version: "1.0"
phase: "11"
lesson: "06"
tags: [fde, scope-management, expectation-setting, customer-communication]
---

# Scope Change Playbook

Use this playbook at project kickoff. Share it with the customer. It removes ambiguity about how scope changes will be handled before the first change request arrives.

---

## The Three Change Types

| Type | Definition | Example | Your Response |
|------|-----------|---------|---------------|
| Clarification | Same goal, better definition | "By tickets we mean only Tier 1" | Accept, update scope doc, confirm in writing |
| Expansion | Same goal, more features | "Can we add billing questions too?" | Assess impact, present tradeoff, negotiate |
| Pivot | Different goal entirely | "Actually, build a chatbot instead" | Stop, schedule scoping call, new timeline |

---

## The 24-Hour Rule

Never respond to a scope change request immediately.

**Respond with:** "Thank you for this. Let me assess the impact and get back to you by [specific time, within 24 hours]. I want to give you an accurate picture of what this means for the timeline before we decide."

This pause:
- Protects you from a reactive yes that becomes a missed deadline
- Protects the customer from committing to something without understanding the cost
- Signals that you take their request seriously

---

## The Impact Assessment Checklist

Before responding to any expansion or pivot:

- [ ] How many additional engineering days does this require?
- [ ] Does it require new data, new labels, or a new eval set?
- [ ] Which current deliverable gets compressed or delayed?
- [ ] Does it introduce new dependencies (data access, approvals, third-party APIs)?
- [ ] Is the new scope something the current team can execute, or does it require different expertise?

---

## The Living Scope Doc

Every project gets a scope doc at kickoff with these sections:

```
## In Scope
[List of deliverables, explicitly defined]

## Not In Scope
[Explicit list of things that are NOT included]
Customer sign-off date: [date]

## Change Log
| Date | Request | Classification | Decision | Approved By |
|------|---------|---------------|----------|-------------|
```

The "Not In Scope" section is your primary protection against scope creep.
If it was not in scope and the customer signed off, it is a new request.

---

## Response Templates

### For Clarification

> "Thank you for the clarification. I have updated the scope doc to reflect that [summary of change]. This does not change the timeline or deliverables. I will send you the updated doc by end of day for your review. Let me know if anything else needs adjusting."

### For Expansion

> "Thank you for this request. Adding [change description] would require approximately [N] additional engineering days and would [shift / not shift] the delivery date. Before we proceed, I want to make sure we align on the tradeoff. Can we schedule 15 minutes this week to discuss? I want to make sure you have the full picture before deciding."

### For Pivot

> "I appreciate you sharing this direction. A pivot to [new goal] would mean setting aside the work completed so far and starting a new scoping phase. The current timeline would need to be reset. I recommend we schedule a scoping call before moving forward so we can size the new goal properly and agree on a realistic timeline. When are you available this week?"

---

## Weekly Status Update Template

Send every Monday morning, without exception.

```
Subject: [Project Name] Weekly Status - Week [N]

SHIPPED LAST WEEK
- [item 1]
- [item 2]

SHIPPING THIS WEEK
- [item 1]
- [item 2]

BLOCKERS
- [blocker or "None"]

OPEN QUESTIONS NEEDING YOUR INPUT
- [question or "None"]

SCOPE CHANGES THIS WEEK
- [change request received, classification, decision - or "None"]
```

---

## When to Escalate

Escalate to your manager or account lead when:
- The customer is requesting a pivot and is not receptive to a timeline reset
- The customer's stakeholders are misaligned (one person wants expansion, another wants the original scope)
- The scope change would require budget approval that has not happened
- You have already absorbed one expansion and a second has arrived

Do not absorb scope changes silently to avoid conflict. Silent absorption is how projects fail.
