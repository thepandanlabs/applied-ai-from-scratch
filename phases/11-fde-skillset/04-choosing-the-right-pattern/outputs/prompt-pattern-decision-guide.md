---
name: prompt-pattern-decision-guide
description: Decision guide for choosing the right AI pattern given a scoped requirement, with scoring worksheet and mismatch warnings
version: "1.0"
phase: "11"
lesson: "04"
tags: [fde, patterns, architecture, rag, agents, decision]
---

# AI Pattern Decision Guide

Use this before writing any architecture. Fill in the scoring worksheet for your requirement, then check for mismatch warnings.

---

## The 5 Patterns

### Single LLM Call
**When it fits:** Fixed input/output contract, no retrieval needed, deterministic output preferred, latency under 2s required.
**Watch for:** If you find yourself hardcoding context into the prompt that changes frequently, you've outgrown this pattern.

### RAG (Retrieval-Augmented Generation)
**When it fits:** Output must be grounded in a knowledge base that is too large for context or that changes over time.
**Watch for:** If the knowledge base is under 50 pages and changes monthly or less, a well-crafted prompt with the full context may outperform RAG.

### Agent with Tools
**When it fits:** Multi-step reasoning required, live data needed, workflow has branching logic based on tool results.
**Watch for:** If there is exactly one tool and the workflow is linear, this is RAG or a single call with a tool, not an agent.

### Multi-Agent
**When it fits:** Parallel subtasks with distinct expertise domains, independent verification required, complex orchestration.
**Watch for:** Almost always start with a single agent. Add a second agent when single-agent output quality is measurably insufficient.

### Fine-Tuning
**When it fits:** Task is highly repetitive, labeled examples are abundant (thousands), base model behavior needs to be overridden.
**Watch for:** Fine-tuning is expensive and brittle. Validate that prompt engineering cannot meet quality requirements first.

---

## Decision Scoring Worksheet

For each axis, score 0 (no), 1 (partially), or 2 (yes):

| Axis | Score (0-2) |
|------|-------------|
| Output depends on a changing knowledge base | |
| Requires multi-step reasoning or tool use | |
| Latency under 2s is a hard requirement | |
| Output must be consistent for the same input | |
| Integration complexity must stay low | |
| Data is too large to fit in a single context | |
| Highly repetitive task with many labeled examples | |

**Pattern weights** (axis score x weight = contribution):

| Axis | Single Call | RAG | Agent | Multi-Agent | Fine-Tune |
|------|-------------|-----|-------|-------------|-----------|
| Knowledge base | 0 | 2 | 1 | 1 | 0 |
| Multi-step | 0 | 0 | 2 | 2 | 0 |
| Latency < 2s | 2 | 1 | 0 | 0 | 1 |
| Deterministic | 2 | 1 | 0 | 0 | 2 |
| Low complexity | 2 | 1 | 0 | 0 | 1 |
| Large data | 0 | 2 | 1 | 1 | 1 |
| Repetitive + examples | 0 | 0 | 0 | 0 | 2 |

**My scores:**

| Pattern | Total Score |
|---------|-------------|
| Single LLM call | |
| RAG | |
| Agent with tools | |
| Multi-agent | |
| Fine-tuning | |

**Highest score = recommended starting pattern.**

---

## Mismatch Warning Card

Check these before finalizing the pattern:

**Warning 1: Agent when RAG would work**
If your highest-scoring pattern is Agent and the only tool is a knowledge base lookup, test RAG first. Agent adds latency and non-determinism without adding capability for single-tool linear workflows.

**Warning 2: Multi-agent when single agent would work**
If Multi-agent scores highest and Agent is within 2 points, start with a single agent. Add a second agent after measuring whether single-agent output quality is insufficient.

**Warning 3: Agent + low-latency requirement**
If Agent scores highest and your requirement says "under 2s," verify this is achievable. Agent workflows with 2+ tool calls typically run 3-8 seconds. Either accept higher latency or reconsider the pattern.

**Warning 4: Fine-tuning before prompt engineering**
If Fine-tuning scores highest and you haven't tested prompt engineering yet, run the prompt test first. Fine-tuning is expensive and brittle. Spend 2 days on prompt engineering before committing to fine-tuning.

---

## Pattern Decision Record

Document the decision before build starts:

```
Date:
Requirement summary:
Axes scored: [list]
Recommended pattern:
Second-best pattern:
Warnings triggered:
Decision rationale (why recommended pattern over second-best):
Decision made by:
Reviewed by:
```

Keep this in the repo. If the pattern needs to change mid-build, reference this record to understand what changed and why.
