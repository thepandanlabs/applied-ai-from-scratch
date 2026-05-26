---
name: prompt-ai-spec-template
description: Blank AI spec template with 7 required sections, section prompts, and a pre-build flags checklist
version: "1.0"
phase: "11"
lesson: "03"
tags: [fde, spec, discovery, requirements, eval]
---

# AI Spec Template

Fill this out before writing a single line of code. A spec with unresolved flags is not ready to build.

---

## 1. Problem Statement

*Describe the pain in customer terms. Not "we need an LLM to classify tickets." Instead: "Support agents spend 8 minutes manually categorizing each Tier 1 ticket. New agents take 4x longer than experienced ones."*

**Problem:**


**Who is affected:**


**Current workaround (if any):**


---

## 2. Success Metric

*Must include all four: a specific number, a baseline, a time horizon, and a measurement source. If you cannot fill this in, you are not ready to build.*

**Target metric:**


**Baseline today:**


**Time horizon:**


**How it will be measured:**


**Confirmed by customer:** [ ] Yes / [ ] No - needs confirmation

---

## 3. Input/Output Contract

*What goes into the system, what comes out, and in what format. Be specific enough that an engineer who was not on the discovery call can implement it.*

**Input:**
- Format:
- Source:
- Example:

**Output:**
- Format:
- Fields:
- Example:

**Latency requirement:**


---

## 4. Data Sources

*Name the person, name the system, confirm the format and access path before build starts.*

| Field | Details |
|-------|---------|
| System | |
| Owner (named person) | |
| Format | |
| Volume / history | |
| Access path | |
| Approval required | |
| Access confirmed | [ ] Yes / [ ] Not yet |

---

## 5. Integration Points

*Where does the output land? Who acts on it? What happens when the AI is wrong?*

**Output destination:**
(e.g., Zendesk sidebar, React dashboard field, Slack message)

**Who acts on it:**


**Human review step:**


**Error / low-confidence handling:**


**Integration confirmed with customer:** [ ] Yes / [ ] No - needs confirmation

---

## 6. Risks and Unknowns

*List everything that could affect the build that you don't know yet. Unresolved risks left here are better than hidden assumptions in code.*

| Risk / Unknown | Impact if unresolved | Owner | Resolved? |
|----------------|---------------------|-------|-----------|
| | | | |
| | | | |
| | | | |

---

## 7. Out of Scope

*List what this system will NOT do in version 1. Getting this on paper prevents post-demo scope creep.*

This system will not:
-
-
-

---

## Pre-Build Flags Checklist

Before starting the build, every item below must be checked:

- [ ] Success metric has a number, baseline, time horizon, and measurement source
- [ ] Success metric confirmed by the primary customer stakeholder
- [ ] Data owner is a named person (not "the team")
- [ ] Data access has been confirmed (not just promised)
- [ ] Integration point is a specific named tool or interface
- [ ] Integration point confirmed with the engineering or product owner
- [ ] At least one risk has been evaluated and a mitigation noted
- [ ] Out-of-scope list reviewed with stakeholders

**Flag count before build:** ___
**Target: 0 flags before first build cycle begins.**

---

## Change Log

Track significant spec changes after the first draft:

| Date | Change | Reason | Confirmed by |
|------|--------|--------|--------------|
| | | | |
