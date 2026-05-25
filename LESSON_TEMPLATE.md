# Lesson Template

A guide for contributors writing a new lesson for appliedaifromscratch.com. Follow this structure exactly. Deviations slow down review.

---

## Folder Structure

```
phases/NN-phase-name/NN-lesson-name/
├── code/
│   ├── main.py       (primary, always Python)
│   └── main.ts       (TypeScript, only for app/agent surface lessons)
├── docs/
│   └── en.md         (lesson narrative, 7 beats)
├── outputs/
│   └── [artifact]    (one of: prompt-*.md, skill-*.md, eval-*.md, service-template/, runbook-*.md)
└── checks.json       (self-check questions, NOT quiz.json)
```

---

## docs/en.md Template

Copy this exactly. Fill in every section. Do not skip beats.

```markdown
# [Lesson Title]

> [One-line motto: the core idea in one punchy sentence]

**Type:** Build
**Languages:** Python [, TypeScript]
**Prerequisites:** [list]
**Time:** ~N minutes
**Phase:** NN: Phase Name

## Learning Objectives
- [3-5 concrete measurables - what the learner can DO, not just "understand"]
- [Start with a verb: build, write, configure, debug, explain to a stakeholder, etc.]

---

## The Problem

[2-3 paragraphs. A real production pain point. Name the specific failure mode. Attach real costs: dollars lost, latency in milliseconds, customers churned, engineers paged at 2am. Make the reader feel why this matters before you explain anything.]

---

## The Concept

[Mental model only. No code here. Use mermaid diagrams, ASCII diagrams, or tables to show structure. Explain the idea in a way a new hire could sketch on a whiteboard. If you need a table to compare approaches, put it here.]

---

## Build It

[Step by step. Every code block must be runnable. Always include the pip install comment at the top of the first code block. Explain decisions, not just the mechanics. If you made a choice, say why.]

```python
# pip install [package-name]

# ... code here
```

[Continue building. Each step should produce observable output so the learner knows they're on track.]

> **Real-world check:** [A question from a non-technical stakeholder or a sceptical teammate. Forces the learner to explain WHY, not HOW. Example: "Your PM asks why you're not just using the vendor's built-in feature for this. What do you say?"]

[Finish the build. The learner should have a working artifact by the end of this section.]

---

## Use It

[Introduce the production library or platform that handles this problem at scale. Explain what it does and when you would reach for it instead of your handbuilt version. Be explicit about what it adds and what it costs.]

[Side-by-side comparison or before/after table works well here.]

> **Perspective shift:** [A question from an ops, cost, or team angle. Forces the learner to articulate the tradeoff in plain language. Example: "Your team is on-call. The vendor solution costs $400/month. Your handbuilt version is free but you own the bugs. How do you frame this tradeoff for your manager?"]

---

## Ship It

[Describe the reusable artifact in outputs/. What does it do? When should someone reach for it? Show the minimum usage example so a teammate can pick it up without reading the full lesson.]

---

## Evaluate It

[2-3 concrete production checks. Each one must be measurable. Name the failure mode it catches. This section is not optional.]

- **Check 1:** [What to measure, how to measure it, what failure looks like]
- **Check 2:** [What to measure, how to measure it, what failure looks like]
- **Check 3:** [What to measure, how to measure it, what failure looks like]

---

## Exercises

**Easy:** [A variation on the Build It task. Change one variable. Should take 15-30 minutes.]

**Medium:** [Extend or adapt the artifact. Requires understanding the concept, not just copying code. 30-60 minutes.]

**Hard:** [A production-scale challenge or integration with a real system. Should surface edge cases. 1-3 hours.]

---

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|------------------------|
| [Term 1] | [Common misconception or oversimplification] | [Precise, practitioner definition] |
| [Term 2] | [Common misconception or oversimplification] | [Precise, practitioner definition] |
| [Term 3] | [Common misconception or oversimplification] | [Precise, practitioner definition] |

---

## Further Reading

- [Title](https://real-url.com) - [One sentence on why this is worth reading and what angle it takes]
- [Title](https://real-url.com) - [One sentence on why this is worth reading and what angle it takes]
- [Title](https://real-url.com) - [One sentence on why this is worth reading and what angle it takes]
```

---

## outputs/ Artifact Frontmatter

Every file in outputs/ must start with this YAML block.

```yaml
---
name: artifact-name-kebab-case
description: >
  One or two sentences on what this artifact does and when to use it.
version: "1.0.0"
phase: N
lesson: N
tags: [relevant, tags]
---
```

---

## checks.json Format

Standard lessons: 6 questions. Capstone or high-importance lessons: 8 questions.

Questions must be scenario-based. "What do you do when X" not "What is X."

```json
{
  "phase": 2,
  "lesson": 1,
  "title": "Lesson Title",
  "questions": [
    {
      "q": "Scenario-based question (what do you do when X, not what is X)",
      "options": ["A", "B", "C", "D"],
      "answer": 0,
      "explanation": "Why A is correct. Why the others fall short."
    }
  ]
}
```

---

## Style Rules for Contributors

- No em dashes. Use colons, commas, or hyphens.
- The Problem must include real costs: dollars, latency in milliseconds, churn numbers.
- Every code block in Build It must run. Include the pip install comment at the top.
- Evaluate It is not optional. Every lesson has it.
- One Real-world check in Build It. One Perspective shift in Use It. Both required.
- Further Reading: real URLs only. No placeholder or made-up links.
- Tone is direct and practitioner-focused. Write for someone who has to ship this week.
