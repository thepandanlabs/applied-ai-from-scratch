# /calibrate — Placement Playbook

Run this playbook when a learner wants to find their starting phase.

---

## Purpose

Map the learner's software engineering background and AI exposure to the right entry point in the curriculum. Skip phases they already know. Avoid placing them too far ahead (they miss foundational applied skills) or too far back (they disengage).

---

## Playbook

Ask these questions in order. One at a time. Wait for the answer before asking the next.

### Q1 - Software background

> "How long have you been writing code professionally, and what's your primary stack?"

Map answers:

- Less than 1 year or still learning: start P00
- 1-3 years, any stack: start P00, may skip setup lesson
- 3+ years, Python comfortable: may start P01
- 3+ years, Python expert: assess further (Q2)

### Q2 - API and HTTP experience

> "Have you built or consumed REST APIs? Can you write a FastAPI or Express route from scratch without looking it up?"

Map answers:

- No/unfamiliar: start P00
- Yes but not Python: start P00 (setup lesson), then P01
- Yes, Python comfortable: may start P01

### Q3 - AI/LLM exposure

> "Have you called an LLM API before (OpenAI, Anthropic, etc.)? Just the API call - sending a prompt and getting a response?"

Map answers:

- Never: start P01 lesson 01
- Yes, basic calls: start P01 lesson 03 (skip API anatomy basics)
- Built something with LLMs: assess further (Q4)

### Q4 - Production AI experience

> "Have you shipped an AI feature to real users? Or built RAG, an agent, or an eval harness?"

Map answers:

- No: start P01 or P02 depending on Q3
- RAG only: start P03 or P04
- Agents but no evals: start P05 (Evaluation is the gap)
- Built + shipped + have eval metrics: start P06 or P07 (observability/shipping gaps)
- Full stack: start P11 (FDE skills are likely the gap)

---

## Output format

After all questions, give the learner:

1. **Your starting phase**: Phase NN - [Name]
2. **Why**: one sentence based on their answers
3. **First lesson**: `phases/NN-phase-name/01-lesson-name/docs/en.md`
4. **What to skip** (if anything): specific lessons they can skim

Keep the recommendation to 3-4 sentences. No need to recap all their answers.

---

## Example output

> Based on your background: you're comfortable with Python and REST APIs, and you've called the OpenAI API a few times but haven't shipped anything to users. Start at **Phase 01, Lesson 03** — you can skip the API anatomy basics and jump straight to prompt engineering fundamentals. Your first lesson: `phases/01-prompt-and-context/03-prompt-fundamentals/docs/en.md`. If Phase 01 feels too slow, jump to Phase 02 (RAG) — that's where things start getting interesting for someone at your level.
