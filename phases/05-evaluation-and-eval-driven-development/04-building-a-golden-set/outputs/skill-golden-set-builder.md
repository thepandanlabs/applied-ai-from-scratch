---
name: skill-golden-set-builder
description: Guide for building and maintaining a golden dataset for any AI system
version: "1.0"
phase: "05"
lesson: "04"
tags: [eval, golden-set, regression, labeling, dataset]
---

# Skill: Building and Maintaining a Golden Set

A golden set is a curated collection of inputs with verified expected outputs. It is the foundation for regression tests, automated evals, and LLM-judge calibration. Without one, every prompt change is a leap of faith.

---

## The GoldenCase schema

Every case in the golden set must have these fields:

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique, stable identifier (e.g., `prod-001`, `adv-003`) |
| `input` | string | The exact input the system receives |
| `expected_output` | string | What a correct system should produce (verified by a human) |
| `category` | string | Failure taxonomy category (returns, billing, safety, etc.) |
| `difficulty` | string | `normal`, `edge`, or `adversarial` |
| `created_at` | ISO datetime | When this case was added |
| `notes` | string | Why this case was added, source, reviewer name |

No field is optional. `notes` is the audit trail.

---

## Sourcing strategy

Build from three sources in this priority order:

### 1. Production logs (highest value)

Mine real user inputs from your system logs. These cases represent the actual distribution of what users ask.

Process:
1. Pull the last 30 days of inputs from your logging system
2. Cluster by semantic similarity (or manually group into categories)
3. Pick 3-10 representative inputs per cluster
4. Have a domain expert write the expected output for each
5. Reviewer approves/rejects each expected output

### 2. Adversarial examples (highest coverage of failure modes)

After every error analysis session (L03), add the inputs that caused failures to the golden set.

Process:
1. After each incident or error analysis session, identify the failing input
2. Write a corrected expected output
3. Mark as `difficulty: adversarial`
4. Add a note explaining why this case was a failure

### 3. Synthetic generation (when you have no production data)

If you're building before launch, generate cases from your specification documents, user stories, or requirements.

Process:
1. List every supported query type from your spec
2. Write 2-3 representative inputs per type
3. Write the expected output from your policy/spec document
4. Mark as `difficulty: edge` or `difficulty: normal`
5. Plan to replace with production cases once you have traffic

---

## Size targets by system type

| System type | Start with | Solid | Production-grade |
|---|---|---|---|
| Simple classification | 30 | 100 | 500 |
| Open-ended Q&A | 50 | 200 | 1,000 |
| RAG over documents | 50 | 200 | 500 |
| Multi-step agent | 20 | 50 | 200 |
| Extraction / parsing | 30 | 100 | 300 |

Start small. A carefully curated 50-case set beats a sloppy 500-case set.

---

## Difficulty distribution target

```
60% normal      -- common cases that must always work
30% edge        -- unusual but valid inputs, boundary conditions
10% adversarial -- known failure modes, injection attempts, multi-intent
```

If your set is more than 80% normal cases, you will miss regressions on hard inputs.

---

## Labeling process

**Who labels:** a person who understands the domain and the system's intended behavior. Not the engineer who wrote the prompt.

**How to ensure consistency:**
1. Write a labeling guide: 1-2 pages explaining what "correct" means for this system
2. For each new case, have the labeler write the expected output independently
3. A second reviewer approves/rejects
4. If reviewers disagree more than 15% of the time, the criteria are underspecified: improve the labeling guide

**Labeling guide template:**
- System purpose: what is this system supposed to do?
- Correctness criteria: what makes an output correct? (factual accuracy, policy compliance, tone, completeness)
- Rejection criteria: what makes an output wrong? (hallucination, wrong policy, harmful content)
- Edge case rules: how should the system handle [X] edge case?

---

## Versioning

Use semantic versioning for the golden set file:
- `golden-set-v1.json`: initial set
- `golden-set-v1.1.json`: added cases, no cases removed
- `golden-set-v2.json`: significant restructuring, cases removed or fundamentally changed

Track version in the file header:
```json
{
  "name": "customer-support",
  "version": "1.1",
  "last_reviewed": "2025-04-01",
  "cases": [...]
}
```

When you bump the version, re-run all evals and save the scores alongside the version so you can track trends.

---

## Maintenance checklist (quarterly)

Run this checklist every 90 days or after any major product change:

- [ ] Pull the last 30 days of production inputs and compare to case distribution
- [ ] Add at least 2 cases per new product feature or policy change
- [ ] Add every failure from the last quarter's error analysis sessions
- [ ] Remove or update any cases where the expected output is now wrong (policy changes)
- [ ] Re-run label consistency check: pick 5 random cases, have a second reviewer approve/reject
- [ ] Bump the version number and re-run baseline eval to record the new scores
- [ ] Update `last_reviewed` in the file header

---

## Anti-patterns

**"We have 10,000 logs, we don't need to curate."** Wrong. You don't know which of those logs have correct responses. Use the logs as a mining source, not as a golden set directly.

**"The engineer who wrote the prompt labels the expected outputs."** This introduces bias. The labeler should be someone who knows the domain, not the person who built the system.

**"We set it up once and never touch it."** Golden sets rot. After a product launch, the old cases may no longer be representative. Maintain it like production code.

**"Pass/fail is too coarse, we need nuanced scores."** Start with pass/fail. Nuanced scores require calibrated judges (L06). Pass/fail catches regressions reliably before you have a calibrated judge.
