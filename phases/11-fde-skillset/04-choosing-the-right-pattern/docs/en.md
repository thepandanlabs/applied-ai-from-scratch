# Choosing the Right Pattern

> The simplest pattern that meets the requirements is always the right starting point.

**Type:** Learn
**Languages:** Python
**Prerequisites:** 11-02 Scoping Before Solving, Phases 02-04 (RAG, Tools, Agents)
**Time:** ~45 min
**Phase:** 11 - FDE Skillset

## Learning Objectives

- Name the 5 main AI patterns and describe when each one is appropriate
- Apply a decision matrix to a scoped requirement and select the right starting pattern
- Identify the most common pattern mismatch (using agents when a single call works)
- Build a PatternMatcher CLI that scores a requirement description against each pattern
- Explain why starting with the simplest pattern is a maintenance, not just a complexity, argument

---

## The Problem

You finish the scoping interview and have a clean AI spec. Now you sit down to architect the system. You've built RAG pipelines, you know how to wire up tool-calling agents, you've done multi-agent orchestration in Phase 04. The instinct is to reach for the most capable pattern: agents with tool use, maybe a multi-agent supervisor.

Then you ship it. The system takes 8 seconds to respond. It's calling 4 tools on every request, 3 of which are never used for this customer's actual ticket types. Debugging is painful. The customer asks why it sometimes gives different answers for the same ticket. You're explaining non-determinism to a compliance team.

The problem is not the agent pattern: agents are correct for some problems. The problem is reaching for agents before checking whether a single LLM call, with a well-crafted prompt, would meet all the requirements. In FDE engagements, the wrong pattern chosen at the start of the build costs 3-5 days of rework. The pattern decision is worth 20 minutes of deliberate analysis.

---

## The Concept

### The 5 Patterns and Their Niches

```
PATTERN              WHAT IT IS              WHEN IT FITS
-------------------  ----------------------  ----------------------------------
Single LLM call      One prompt, one         Fixed I/O, no retrieval needed,
                     response               deterministic output preferred,
                                            latency < 2s required

RAG                  Retrieve + generate     Output depends on a knowledge base
                     from retrieved          that changes or is too large for
                     context                context, factual grounding required

Agent with tools     LLM decides which       Requires external data (live APIs,
                     tools to call and       databases), multi-step reasoning,
                     how to combine          output varies by inputs
                     results

Multi-agent          Multiple LLMs with      Complex workflow with parallel
                     different roles         tasks, different expertise
                     coordinate             domains, or verification step
                                            requiring independent judgment

Fine-tuning          Trained on task-        Pattern is highly repetitive,
                     specific examples       examples are abundant, base model
                                            behavior must be suppressed
```

### The Decision Matrix

Score each axis 0 (no), 1 (maybe), 2 (yes) for your requirement:

```
Decision Axis           Single  RAG  Agent  Multi  Fine-tune
                        Call         Tools  Agent
----------------------  ------  ---  -----  -----  ---------
Output depends on a       0      2     1      1       0
changing knowledge base

Multi-step reasoning      0      0     2      2       0
required

Latency < 2s required     2      1     0      0       1

Output must be            2      1     0      0       2
deterministic

Integration complexity    2      1     0      0       1
must stay low

Data volume too large     0      2     1      1       1
for context window

Task is extremely         0      0     0      0       2
repetitive with examples
```

The highest-scoring pattern for your axes is the starting point.

### The Most Common Mismatch

```
"This ticket needs context from our KB"
                |
                v
Engineer reaches for agent with KB tool
                |
                v
RAG pipeline + single LLM call would do the same job
at 4x lower latency and 10x simpler debugging
```

Agents earn their complexity when:
- The system must decide WHICH tools to call based on input
- The system must handle multi-step workflows with branching logic
- The system must respond to failures (retry, escalate, use alternative)

Agents do NOT earn their complexity when:
- There is one fixed tool to call on every request
- The workflow is linear with no branching
- Latency matters and the agent overhead is not justified

The simplest mismatch test: if you wrote the system as a single prompt + RAG + one structured output call, would it meet the spec? If yes, that is what you build.

---

## Build It

Build a `PatternMatcher` CLI that takes a requirement description, scores it against the 5 decision axes, and recommends a starting pattern with a warning if the recommendation conflicts with the description.

```python
# Each requirement description is scored on the decision axes.
# The scoring uses Claude to parse the description into axis scores,
# then applies the decision matrix.

DECISION_AXES = [
    "output_depends_on_knowledge_base",
    "requires_multistep_reasoning",
    "latency_under_2s_required",
    "output_must_be_deterministic",
    "integration_complexity_must_stay_low",
    "data_too_large_for_context_window",
    "highly_repetitive_with_abundant_examples",
]

PATTERN_SCORES = {
    "single_llm_call": {
        "output_depends_on_knowledge_base": 0,
        "requires_multistep_reasoning": 0,
        "latency_under_2s_required": 2,
        "output_must_be_deterministic": 2,
        "integration_complexity_must_stay_low": 2,
        "data_too_large_for_context_window": 0,
        "highly_repetitive_with_abundant_examples": 0,
    },
    # ... 4 more patterns
}
```

Run the matcher:

```bash
python main.py --requirement "Classify support tickets into 5 categories"
python main.py --interactive
python main.py --requirement req.txt --scenarios all
```

Sample output for 3 different scenarios:

**Scenario 1: Ticket classifier**
```
Requirement: Classify support tickets into 5 categories with <1s response time.
Customer has labeled examples from 18 months of history.

Axis scores:
  output_depends_on_knowledge_base:       No  (0)
  requires_multistep_reasoning:           No  (0)
  latency_under_2s_required:              Yes (2)
  output_must_be_deterministic:           Yes (2)
  integration_complexity_must_stay_low:   Yes (2)
  data_too_large_for_context_window:      No  (0)
  highly_repetitive_with_abundant_examples: Yes (2)

Pattern scores:
  Single LLM call:  8   *** RECOMMENDED ***
  RAG:              4
  Agent with tools: 2
  Multi-agent:      2
  Fine-tuning:      7   (close second - worth exploring if labeled data is large)

Warning: None.
```

**Scenario 2: Research assistant**
```
Requirement: Help analysts research any public company by pulling live data,
SEC filings, and news, then synthesizing a 1-page report.

Pattern scores:
  Single LLM call:  2
  RAG:              4
  Agent with tools: 9   *** RECOMMENDED ***
  Multi-agent:      7
  Fine-tuning:      1

Warning: Live data retrieval requires tool use. RAG alone won't work for
live sources. Multi-agent is worth exploring if the synthesis step
benefits from independent verification.
```

**Scenario 3: Agent overkill**
```
Requirement: Draft a response to a support ticket by looking it up in the
knowledge base and generating a reply.

Pattern scores:
  RAG:              8   *** RECOMMENDED ***
  Agent with tools: 7

Warning: This requirement scores close on RAG and Agent. RAG is recommended
because the knowledge base lookup is the only tool needed and the workflow
is linear. An agent adds overhead and non-determinism without adding capability
for this use case. Start with RAG.
```

> **Real-world check:** A customer asks you to build a system that "researches our competitors and writes a weekly summary." You run the pattern matcher and it recommends Agent with tools. Your instinct is to use multi-agent because the research feels complex. What should you do? Start with a single agent, not multi-agent. The pattern matcher recommends the simplest pattern that fits. Multi-agent earns its complexity when there are distinct roles that benefit from separate reasoning chains (researcher, fact-checker, writer). For a weekly summary, a single agent with web search and document tools is simpler, easier to debug, and meets the requirement. Add the second agent if the single-agent output quality is insufficient.

The full implementation is in `code/main.py`. It uses Claude to score the requirement description against the axes and applies the decision matrix to produce a ranked recommendation with warnings.

---

## Use It

Run the PatternMatcher on 3 different scenarios to see how the decision matrix changes the recommendation.

**Scenario A: Simple Q&A**

"Our sales team needs to ask questions about our product catalog. The catalog has 500 products, each with a spec sheet. Responses must be accurate and under 2 seconds."

```bash
python main.py --requirement "Sales team Q&A on 500-product catalog, accuracy required, < 2s"
```

Result: RAG recommended. The catalog is too large for context (500 products), retrieval grounds the answer in actual specs, latency is manageable with a good retrieval layer.

**Scenario B: Document extraction**

"Extract structured data (dates, parties, amounts, payment terms) from contract PDFs. We have 200 contracts per month. Same extraction template every time."

Result: Single LLM call recommended. Fixed I/O, same template every time, no retrieval needed. High-latency agent overhead is unjustified. Bonus: if you have 10,000 labeled extraction examples, fine-tuning is a strong second option.

**Scenario C: Autonomous research task**

"Monitor our top 10 competitors. Every Monday, check their pricing pages, job listings, and blog posts. Generate a competitive intelligence report with key changes highlighted."

Result: Agent with tools recommended. Multi-step workflow (10 competitors, 3 data sources each), live data required, branching logic (only report on changes vs. no changes), output varies week-to-week.

> **Perspective shift:** A developer with a background in software architecture might look at the single-LLM-call recommendation for simple Q&A and feel it's under-engineered. In software, adding abstraction layers is often called "good design." In AI engineering, adding LLM calls and agent loops that are not required by the spec is called "maintenance liability." Every additional agent step is a failure surface (timeout, tool error, unexpected output format). The simplest working architecture is not a shortcut; it is the production discipline.

---

## Ship It

The reusable artifact for this lesson is `outputs/prompt-pattern-decision-guide.md`: a printable decision guide with the 5 patterns, decision axes, the mismatch warning card, and a blank scoring worksheet. Use it at the start of every build to document the pattern decision before writing code.

---

## Evaluate It

How to know the pattern decision process is working:

1. **Pattern decision documented before build** - the most direct check. Does a pattern decision worksheet exist in the repo before the first implementation commit? If not, the decision was implicit and cannot be reviewed or revised.

2. **Pattern switches during build** - track how often the pattern changes after the build starts (e.g., started with agents, switched to single call). A pattern switch mid-build signals the initial pattern was chosen without analysis. A well-documented pattern decision reduces mid-build switches by catching mismatches before they are built.

3. **Latency vs. prediction** - for latency-sensitive requirements, did the chosen pattern meet the latency requirement in production? If a requirement said "< 2s" and you chose agents, you likely missed this. Track latency predictions vs. production latency for each pattern.

4. **Post-build pattern retrospective** - at the end of each engagement, ask: was the pattern we chose the right one? If not, what axes did we misjudge? Build a team record of pattern decisions and outcomes to calibrate the decision matrix over time.
