---
name: prompt-mast-failure-checklist
description: Pre-ship checklist prompt for agent self-assessment against MAST failure criteria
version: "1.0"
phase: "04"
lesson: "14"
tags: [agents, failure-modes, mast, checklist, quality]
---

# Prompt: MAST Failure Checklist

Use this prompt as a final step before declaring an agent run complete. Provide the agent with its own message trace and ask it to run this self-assessment. Use the automated `FailureDetector` (from code/main.py) as the primary defense; this prompt is the second layer.

---

## The Prompt

```
You are a quality reviewer for AI agent runs. You will be given an agent's message trace.
Your job is to check the trace against the MAST failure taxonomy and report any issues found.

MAST categories:
- MEMORY: Did the agent repeat the same action? Did it contradict an earlier decision? Did it forget what it already tried?
- ACTION: Did any tool call have null or missing required arguments? Did the agent ignore a tool error and continue as if it succeeded? Did the agent choose the wrong tool for the task?
- SUPERVISION: Did the agent run without a clear stopping condition? Did it use more turns or tokens than the task required? Was there a point where it should have escalated to a human but did not?
- TASK: Did the agent misunderstand the original goal? Did it declare success before verifying the output satisfies the goal? Did it solve a slightly different problem than the one asked?

For each category, respond with:
- Status: PASS or FAIL
- Evidence: quote the specific turn that caused the flag (if FAIL), or state "no issues found" (if PASS)
- Recommendation: one sentence on what should change before this agent run pattern is used in production

Format your response as:

MEMORY: [PASS/FAIL]
Evidence: [quote or "no issues found"]
Recommendation: [one sentence]

ACTION: [PASS/FAIL]
Evidence: [quote or "no issues found"]
Recommendation: [one sentence]

SUPERVISION: [PASS/FAIL]
Evidence: [quote or "no issues found"]
Recommendation: [one sentence]

TASK: [PASS/FAIL]
Evidence: [quote or "no issues found"]
Recommendation: [one sentence]

Overall: [PASS if all four pass / FAIL if any fail]
```

---

## How to Use This Prompt

**Step 1:** Capture the agent's message history as a JSON array or plain-text transcript.

**Step 2:** Append the transcript to the prompt above:

```
[PROMPT TEXT ABOVE]

--- AGENT TRACE ---
[paste transcript here]
```

**Step 3:** Send to any capable model (Claude Sonnet or better recommended).

**Step 4:** Review the output. Any FAIL requires investigation before the agent pattern ships.

---

## Pre-Ship Checklist (Human Review)

Run this checklist manually before deploying any new agent or agent update to production.

**Memory**
- [ ] The agent has access to a summary of its completed steps in its context
- [ ] Repeated tool calls with identical arguments have been tested and confirmed absent in 10 test runs
- [ ] The agent's sliding window retains enough history to prevent re-doing completed work

**Action**
- [ ] All tool schemas have required fields marked and validated before the call is made
- [ ] The tool executor returns structured error messages the agent can parse, not raw HTTP codes
- [ ] A test has been run where each tool intentionally fails; the agent handles the error correctly

**Supervision**
- [ ] A governor is in place with: max iterations, max tokens, max elapsed time
- [ ] The system prompt includes explicit stopping conditions ("stop when you have X", "escalate if Y")
- [ ] There is a defined escalation path: what happens when the agent cannot complete the task within budget?

**Task**
- [ ] The system prompt includes explicit success criteria, not just the goal
- [ ] The agent has a self-check step: before declaring success, it verifies the output against the original goal
- [ ] A test has been run where the task is deliberately ambiguous; the agent asks for clarification rather than guessing

---

## MAST Failure Quick Reference

```
Category     Symptom                           Root Cause                Fix
-----------  --------------------------------  ------------------------  ---------------------------
MEMORY       Same tool called 3+ times         No completed-steps list   Add step summary to context
MEMORY       Contradicts prior decision        History not in context    Use sliding window
ACTION       null field in tool call           Missing data extraction   Validate args before call
ACTION       Error ignored, success claimed    Weak error surface        Structured error messages
SUPERVISION  20+ turns, no terminal action     No governor               Add max_steps + budget
SUPERVISION  Token usage unbounded             No token limit            Add max_tokens to governor
TASK         "Done" after zero results         No success criteria       Explicit criteria in prompt
TASK         Wrong question answered           Ambiguous goal            Add goal restatement step
```
