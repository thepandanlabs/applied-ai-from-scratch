---
name: prompt-continued-learning-map
description: Prompt template for generating a personalized 90-day skill maintenance plan, project list, and curated reading list for a specific AI engineering role
version: "1.0"
phase: "12"
lesson: "07"
tags: [learning, career, maintenance, fde, applied-ai-engineer]
---

# Continued Learning Map Prompt Template

Use this prompt to generate a personalized 90-day plan for maintaining and growing your AI engineering skills after completing the curriculum. Use with Claude, GPT-4o, or any frontier model.

---

## The Prompt

```
You are helping me build a 90-day skill maintenance and growth plan after completing
a 12-phase Applied AI engineering curriculum.

## My Profile

Target role: [FILL IN: Applied AI Engineer / Forward-Deployed Engineer / AI Solutions Engineer]

Current experience level: [FILL IN: e.g., "2 years as a backend engineer, new to AI systems"
or "3 years as a data scientist, building production LLM apps for 1 year"]

Top 3 areas from the curriculum where I feel strongest:
1. [FILL IN: e.g., Evaluation and eval-driven development]
2. [FILL IN: e.g., Agent patterns]
3. [FILL IN: e.g., RAG pipelines]

2 areas where I feel weakest or least practiced:
1. [FILL IN: e.g., Observability and tracing]
2. [FILL IN: e.g., FDE scoping and handoff skills]

Current job context: [FILL IN: e.g., "currently job searching" or "building AI features at
a B2B SaaS startup" or "working on ML infrastructure, want to move to applied AI"]

## Curriculum I Completed

Phase 01: Context engineering and prompt design
Phase 02: RAG and retrieval pipelines
Phase 03: Tools and MCP integration
Phase 04: Agents and multi-agent patterns
Phase 05: Evaluation and eval-driven development
Phase 06: Shipping AI services (FastAPI, Docker)
Phase 07: Observability (Langfuse, OpenTelemetry)
Phase 08: Security and guardrails
Phase 09: Fine-tuning
Phase 10: Multimodal and voice
Phase 11: FDE skills (scoping, demos, handoff, stakeholder communication)
Phase 12: Capstone projects (RAG assistant, support agent, text-to-SQL, coding agent,
           FDE mock engagement, portfolio packaging)

## My Request

Generate a 90-day skill maintenance and growth plan that includes:

1. WEEKLY COMMITMENT (realistic)
   What is the minimum weekly time investment to maintain these skills?
   Break it into: daily practice (15 min max), weekly project work (2-4 hours),
   monthly deep dives (one afternoon). Be realistic - I have a job and a life.

2. 5 SPECIFIC PROJECTS TO BUILD IN 90 DAYS
   Each project must:
   - Be completable in a single weekend (Sat + Sun, 6-8 hours total)
   - Test a specific skill from my weakest areas
   - Produce a reusable artifact (runbook, eval, service template, or prompt)
   - Be distinct from what I built in the curriculum (different domain, new use case)
   Format each as: Project name, what to build, what skill it sharpens, artifact produced.

3. CURATED READING LIST
   Exactly 3-5 sources. No more. For each source:
   - The specific URL or publication name
   - The specific section or type of content to focus on (not "read everything")
   - Why this source for my specific role and weak areas (one sentence)
   Do not suggest Twitter/X, LinkedIn, or generic "AI newsletters."

4. SELF-ASSESSMENT TRIGGERS
   List 5 specific questions I should ask myself every 30 days to detect skill drift.
   These should be concrete (not "am I staying current?") and should relate to my
   target role and weak areas.

5. THE "NEW TOOL" DECISION FILTER
   Given my target role and weak areas, what is the specific question I should ask
   before spending time on any new AI framework, model, or library that appears?
   Give me a 3-question filter customized to my role.

Keep the plan specific and honest. Do not suggest I read everything. The goal is
sustainable skill maintenance, not full-time AI news consumption.

Do not use em dashes anywhere in your response. Use colons, commas, or hyphens.
```

---

## Example Output

The following shows what well-formed output looks like for an Applied AI Engineer targeting a role at a B2B SaaS company.

### Weekly Commitment (example)

**Daily (15 min max):** Read Anthropic and OpenAI release notes when they ship. That is it. Do not add daily reading habits.

**Weekly (2-4 hours on one day):** One small project or experiment. Pick something from the 5-project list below. If there is no project this week, run the eval harness for something you have already built against a new sample.

**Monthly (one afternoon):** Run the 5-pillar self-assessment. Pick the weakest result. That is your project for the next month.

### 5 Projects to Build (example)

**Project 1:** Observability instrumentation for the email triage capstone
- Build: Add Langfuse tracing to the Phase 12-05 email triage MVP. Instrument: classification call latency, category distribution over time, confidence score distribution.
- Sharpens: observability (weakest area)
- Artifact: skill-email-triage-langfuse-setup.md

**Project 2:** Scoping interview simulation for a new domain
- Build: Use the Phase 11-02 scoping interview guide on a new use case (e.g., HR document review, legal contract analysis). Produce an AI Spec. Do not build the system - just the spec.
- Sharpens: FDE scoping skills (weakest area)
- Artifact: prompt-ai-spec-hr-document-review.md

**Project 3:** Golden set for a use case you have not worked on
- Build: Find a public dataset (e.g., customer reviews, news classification). Build a 30-item golden set. Write an LLM-as-judge eval. Report accuracy.
- Sharpens: evaluation (strongest area - maintains fluency)
- Artifact: eval-customer-review-classifier-baseline.md

**Project 4:** Multi-tool agent with a safe boundary specification
- Build: Build an agent with 3 tools (one read-only data lookup, one write, one external API). Write the safety specification before writing the code.
- Sharpens: agent patterns (strong area - deepens)
- Artifact: skill-safe-agent-boundary-spec.md

**Project 5:** Handoff package for a project you built in the curriculum
- Build: Write the complete four-document handoff package for the Phase 12-01 RAG assistant capstone, as if handing it to a non-engineering team.
- Sharpens: FDE handoff skills (weakest area)
- Artifact: runbook-rag-assistant-customer-handoff.md

### Curated Reading List (example)

1. **Anthropic engineering blog** (anthropic.com/engineering): Focus specifically on posts about production deployments and evaluation methodology. Skip capability announcement posts. Read when new posts appear.

2. **Hamel Husain's blog** (hamel.dev): The posts on evals and fine-tuning are directly applicable. Read the posts on how he structures evaluations for production systems.

3. **Latent Space podcast** (latent.space): Filter for episodes featuring engineers at companies deploying AI in B2B contexts. Skip pure research episodes. Listen at 1.5x while commuting.

### Self-Assessment Triggers (30-day check, example)

1. "Can I build a golden set for a new use case I have never worked on, without looking at my notes?"
2. "For the last new AI tool or framework I heard about: did I apply the 3-question filter before reading more?"
3. "Do I have a handoff document for at least one system I have built? Could someone else run it without calling me?"
4. "When did I last run an eval on a system I have in production (or deployed to a repo)?"
5. "If a customer asked me 'why did you choose this architecture over agents,' can I answer in 3 sentences with evidence?"

### New Tool Decision Filter (Applied AI Engineer, example)

Before spending more than 5 minutes on any new framework or model:
1. "Does it solve a problem I am actively working on right now?" (If no: bookmark, move on.)
2. "Is there a published evaluation or production case study showing it improves on what I already use?" (If no: wait 30 days, check again.)
3. "Does adopting it require me to change something that is currently working?" (If yes: the evidence bar is twice as high.)

---

## Usage Notes

- Run this prompt at the end of the curriculum, and then again every 90 days
- Update the "weakest areas" section as your skills develop
- Do not add more than 5 sources to your reading list. More sources means less time building.
- The 5 projects are more important than the reading list. Building is how you maintain skills.
- The self-assessment triggers replace quarterly performance reviews that most self-directed learners skip. Do them.
