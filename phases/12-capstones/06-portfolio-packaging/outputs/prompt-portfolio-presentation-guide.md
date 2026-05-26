---
name: prompt-portfolio-presentation-guide
description: Prompt template for generating customized cover letters and project descriptions that map curriculum artifacts to a specific job posting
version: "1.0"
phase: "12"
lesson: "06"
tags: [portfolio, interview, career, fde, applied-ai-engineer]
---

# Portfolio Presentation Prompt Template

Use this prompt with Claude, GPT-4o, or any frontier model to generate a tailored project writeup and interview prep from any job posting.

---

## The Prompt

Copy this entire block and fill in the three sections marked with `[FILL IN]`.

```
You are helping me prepare a tailored application and interview prep for an AI engineering role.

## Job Posting
[FILL IN: Paste the full job posting text, or paste the URL if the model supports browsing]

## My Top 3 Capstone Projects

Project 1: [FILL IN: e.g., "FDE Mock Engagement - email triage system"]
- What I built: [1-2 sentences on the technical implementation]
- How I evaluated it: [metric + result, e.g., "92.3% category accuracy on 20-email golden set"]
- The artifact: [e.g., "runbook-fde-engagement-playbook.md - 4-document handoff package"]

Project 2: [FILL IN]
- What I built:
- How I evaluated it:
- The artifact:

Project 3: [FILL IN]
- What I built:
- How I evaluated it:
- The artifact:

## Target Role
[FILL IN: Applied AI Engineer / Forward-Deployed Engineer / AI Solutions Engineer]

## My Request

Please generate:

1. TAILORED PROJECT WRITEUP
   A 200-250 word description of my top 3 projects that maps them to the specific requirements
   in this job posting. Use the format:
   - Opening sentence: what kind of engineer I am (not "I am a software engineer")
   - One paragraph per project: what I built, how I evaluated it, what it demonstrates
   - Closing sentence: the through-line (e.g., "I build AI systems that can be operated
     by someone other than the engineer who built them")

2. TOP 3 ARTIFACTS TO HIGHLIGHT
   From my three projects above, identify the 3 specific artifacts (runbook, eval,
   prompt template, etc.) that most directly map to the stated requirements of this role.
   For each, explain in one sentence why it is the right artifact for this job posting.

3. FIVE LIKELY INTERVIEW QUESTIONS
   Based on the job posting requirements and my three projects, generate 5 interview questions
   I am likely to face. For each question, provide an answer framework (not a script) that:
   - References a specific artifact or result from my work
   - Answers the underlying question the interviewer is really asking
   - Is 3-5 bullet points, not a paragraph

Keep the language direct and specific. Do not use phrases like "passionate about," "strong
background in," or "proven track record." Let the artifacts and metrics do the work.
```

---

## Example Output

To calibrate expectations, here is what well-formed output looks like for a FDE role posting.

### Tailored Project Writeup (example)

I design and deliver AI systems for B2B customers, from initial scoping through production handoff. For a B2B SaaS customer facing 200 support emails daily, I built an email triage and auto-response system: a router pattern with a Claude-powered classifier and category-specific draft generators. The system reached 92.3% category accuracy and 100% escalation recall on a 20-email golden set. I delivered a four-document handoff package covering operations, prompt update procedures, monitoring thresholds, and 30/60/90 day success criteria.

For a text-to-SQL analytics use case, I built a natural language query pipeline with schema introspection, query validation against a read-only replica, and result formatting for non-technical users. The system handled complex joins through iterative refinement while enforcing hard limits on query scope and execution time.

Across both projects, the evaluation artifact is the deliverable that matters: a go/no-go decision backed by a golden set with defined pass criteria. The code gets the system to production; the eval artifact justifies keeping it there.

### Top 3 Artifacts (example for FDE role)

1. `runbook-fde-engagement-playbook.md` (P12-05) - Directly demonstrates the full engagement lifecycle the job posting requires: discovery, scoping, MVP, go/no-go, and handoff to a non-engineering operator.

2. `prompt-ai-spec-template.md` (P11-03) - Shows the tool you use to convert "we want AI" into a measurable design before writing code; the posting specifically asks for scoping experience.

3. `eval-llm-as-judge-template.md` (P05-04) - The posting mentions "quality measurement" as a requirement; this template shows you have a repeatable evaluation method, not just ad-hoc testing.

### Five Interview Questions with Answer Frameworks (example)

**Q: Tell me about a time you scoped an ambiguous AI project.**

Answer framework:
- Start with what the customer actually said ("we want AI") vs. what they meant (automate the routine 60% of support emails)
- Describe the discovery process: the scoping interview guide, the discovery questions, the specific numbers that emerged (200 emails/day, 60% routine, 6.2 hour response time)
- Show the output: the AI Spec with success metric (90% accuracy, escalation recall = 100%)
- The key insight: "I did not write code until both sides agreed what success looked like"

**Q: How do you decide between a simple prompt and a full agent?**

Answer framework:
- Reference the pattern decision guide (P11-04)
- Concrete example: email triage. Fixed categories, deterministic routing, latency constraint = router pattern wins, not agent
- The test: "what capability does an agent add that a prompt with structured output does not?" If the answer is "nothing," the agent is overhead
- You tried single-call classification first; it worked; you did not add tools

**Q: How do you handle handoffs to non-technical teams?**

Answer framework:
- The four-document handoff package (P11-09, P12-05): system overview, operational runbook, prompt change guide, escalation path
- The test: can a team member who did not build the system diagnose the three most common failures using the runbook alone?
- Concrete: the email triage runbook has 5 common failures, each with symptom, cause, and exact fix steps
- "A handoff where I answer questions afterward is a failed handoff"

---

## Customization Notes

- For Applied AI Engineer roles: lead with P05 eval artifacts and P12 capstones with go/no-go decisions. Emphasize measurement.
- For FDE roles: lead with P12-05 (the full engagement) and P11 artifacts (scoping, spec, handoff). Emphasize delivery.
- For Solutions Engineer roles: lead with breadth (all 12 phases), emphasize the stakeholder communication prompt (P11-10), and the pattern decision guide (P11-04) as tools for explaining tradeoffs to non-technical audiences.
- Never claim you are "passionate about AI." Show you are competent at it. Competence is rarer and more valued.
