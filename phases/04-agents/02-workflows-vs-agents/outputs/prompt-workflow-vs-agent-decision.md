---
name: prompt-workflow-vs-agent-decision
description: Decision prompt that classifies a task as workflow, agent, or multi-agent before you start building
version: "1.0"
phase: "04"
lesson: "02"
tags: [agents, workflows, architecture, decision-framework]
---

# Prompt: Workflow vs Agent Decision

Use this prompt to classify any task before choosing an architecture.
Paste it into Claude with a task description to get a structured recommendation.

## The Prompt

```
You are a senior AI systems architect. An engineering team is deciding whether to implement
a task as a fixed workflow, a single agent, or a multi-agent system.

Analyze the task description below and answer each diagnostic question with Yes or No and
one sentence of reasoning. Then output a final recommendation with a cost and risk summary.

TASK DESCRIPTION:
{task_description}

DIAGNOSTIC QUESTIONS:

1. Fixed steps: Can you enumerate every step the system will take before the first API call?
   (If yes, this favors a workflow)

2. Predictable branches: Are all possible branches and their conditions known in advance?
   (If yes, this favors a workflow)

3. Real-time decisions: Must the model read intermediate results to decide what to do next?
   (If yes, this favors an agent)

4. Unbounded scope: Is the number of steps unknown until execution begins?
   (If yes, this favors an agent)

5. Session persistence: Does the task require memory or state across multiple separate conversations?
   (If yes, this favors multi-agent or stateful agent)

6. Coordination: Does the task require multiple specialized LLM roles working together?
   (If yes, this favors multi-agent)

OUTPUT FORMAT:
Diagnostic answers: [numbered list with Yes/No and one-sentence reasoning for each]

Recommendation: [workflow | agent | multi-agent]

Reasoning: [2-3 sentences explaining the recommendation]

Cost profile:
- Estimated API calls per execution: [range]
- Latency profile: [predictable/variable]
- Debuggability: [high/medium/low]

Risk if wrong:
- If you build a workflow when it should be an agent: [specific failure mode]
- If you build an agent when it should be a workflow: [specific cost/reliability impact]
```

## Example Output (Document Summarization Task)

**Diagnostic answers:**
1. Fixed steps: Yes. Load document, chunk, summarize each chunk, combine. All steps enumerable before execution.
2. Predictable branches: Yes. No branching needed - same steps for every document.
3. Real-time decisions: No. The summarization logic does not change based on what is found in the document.
4. Unbounded scope: No. The number of chunks is known once the document is loaded.
5. Session persistence: No. Each summarization is a single-session task.
6. Coordination: No. One model, one pass, one output.

**Recommendation:** workflow

**Reasoning:** All steps are fixed and enumerable. The LLM is executing a defined algorithm, not making control-flow decisions. A structured prompt with the document (or chunked inputs) produces identical output to an agent loop with 3-5x fewer API calls.

**Cost profile:**
- Estimated API calls per execution: 1-3 (depending on document length and chunking)
- Latency profile: predictable (linear with document length)
- Debuggability: high (each step is a Python function with inspectable inputs/outputs)

**Risk if wrong:**
- If you build a workflow when it should be an agent: not applicable here - this is correctly a workflow.
- If you build an agent when it should be a workflow: 3-10x higher cost per execution, variable latency, harder to test, potential for the model to re-read the same sections multiple times.

## Quick Reference Table

```
Task type                           Recommendation   Key signal
---------------------------------   --------------   ---------------------------
Summarization                       workflow         Fixed steps, known output schema
Classification                      workflow         Fixed categories, one LLM call
Data extraction                     workflow         Known fields, structured output
Content generation (fixed template) workflow         Same prompt structure every time
Customer support triage             agent            Branch depends on message content
Research and synthesis              agent            Number of searches unknown
Debugging assistant                 agent            Next step depends on error found
Multi-document analysis             agent or multi   Scope grows with findings
Long-running task (hours/days)      multi-agent      State spans sessions
Parallel specialized processing     multi-agent      Independent sub-goals
```

## When to Override the Recommendation

Use an agent even when the steps look fixed if:
- Edge cases cause steps to fail and recovery requires judgment
- The input space is so varied that prompt engineering for all cases is impractical
- The cost of a wrong output is high enough that iterative checking is worth the extra calls

Use a workflow even when real-time decisions are needed if:
- The decision space is small and can be encoded as an if/else tree
- Latency requirements make agent loops unacceptable
- The task must be 100% deterministic and auditable
