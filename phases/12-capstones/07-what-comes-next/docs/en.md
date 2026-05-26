# What Comes Next

> The field moves fast. Your job is not to keep up with everything - it is to have the foundations to evaluate what matters.

**Type:** Learn
**Languages:** Python
**Prerequisites:** All prior phases
**Time:** ~1.5 hours
**Phase:** 12 · Capstones

---

## Learning Objectives

- Distinguish between the stable foundations of AI engineering (which change slowly) and the fast-moving surface area (which changes weekly)
- Identify the four information sources worth tracking and explain why each one matters
- Apply the "new tool" evaluation checklist to any framework or model release
- Generate a 4-week practice plan for a specific learning goal using the CLI
- Complete the curriculum loop: map your current capabilities against the role you targeted at the start

---

## The Problem

You have finished the curriculum. The model you used in Phase 01 may already have a successor. The framework you learned in Phase 04 may have released a breaking change. Two new agent orchestration libraries appeared while you were working through Phase 09.

The AI engineering field moves faster than any curriculum can track. This is not a problem with the curriculum - it is a property of the field. The question is not "how do I keep up with everything?" That question has no good answer. The question is: "how do I stay effective in a field that changes faster than I can read about it?"

The answer is two-part. First: the foundations you built in this curriculum do not change fast. Context engineering, evaluation-driven development, the difference between a router and an agent, how to hand off a system - these are not going away. Second: most of what feels like "new" in AI engineering is new surface area on stable foundations. A new model is still evaluated with a golden set. A new framework is still a pattern selection question. A new deployment tool is still a shipping concern.

Your job is not to read everything. Your job is to know which foundations are load-bearing, so you can evaluate new surface area quickly.

---

## The Concept

### Foundations vs. Surface Area

```
STABLE FOUNDATIONS (change in years)
+------------------------------------------+
| Context engineering principles           |
| Evaluation-driven development            |
| Pattern selection (router/RAG/agent)     |
| Go/no-go decision with evidence          |
| Handoff package disciplines              |
| Prompt design fundamentals               |
| Golden set construction                  |
+------------------------------------------+
         |
         | (frameworks sit on top of these)
         v
FAST-MOVING SURFACE (change in months)
+------------------------------------------+
| Specific model versions                  |
| Framework APIs (LangChain, LlamaIndex)   |
| Orchestration libraries                  |
| Deployment tooling                       |
| Benchmark scores                         |
| New modalities                           |
+------------------------------------------+
         |
         | (noise sits on top of these)
         v
NOISE (changes daily, mostly irrelevant)
+------------------------------------------+
| Twitter/X AI hot takes                   |
| Most benchmark announcements             |
| "Best practices" blog posts without evals|
| New model releases without papers        |
| Framework release announcements          |
+------------------------------------------+
```

When something new appears, the first question is: which layer is it? If it is noise, skip it. If it is surface area, apply the new tool checklist. If it challenges a foundation, study it carefully.

### The Four Sources That Matter

Not all information is worth your attention. Four sources have consistently produced high signal-to-noise for applied AI engineering:

**1. Anthropic and OpenAI release notes (not blog posts - release notes)**
Why: they tell you what changed in the models and APIs you actually use. Blog posts tell you what they want you to think. Release notes tell you what actually shipped.

**2. Latent Space podcast (latent.space)**
Why: the hosts interview the engineers who built the systems, not the marketing team. The technical depth is genuine and the "what actually works in production" filter is consistent.

**3. applied-llms.org**
Why: curated applied engineering content. The filter is: "has this been tested in production?" The noise ratio is low.

**4. Hamel Husain's blog (hamel.dev)**
Why: Hamel works on real production systems and writes about what he finds. His content on evals and fine-tuning specifically is grounded in measured results.

Everything else is optional. Social media, VC-backed AI newsletters, and most framework documentation can be read when you have a specific need, not as ambient input.

### The New Tool Checklist

When a new framework, model, or library appears:

```
1. PROBLEM CHECK: Does it solve a problem I actually have right now?
   - Yes: continue evaluation
   - No: bookmark, do not read further yet

2. FOUNDATION CHECK: Does it replace something from the stable foundations,
   or is it new surface area on existing foundations?
   - Replaces foundation: study carefully, this is rare and important
   - New surface area: evaluate against your current toolchain

3. EVIDENCE CHECK: Is there a benchmark, eval, or production case study?
   - Yes, from a team that published methodology: worth reading
   - No, or benchmark-only without production evidence: wait for production reports

4. COST CHECK: What does adopting this cost? (migration effort, learning curve,
   lock-in risk, infrastructure change)
   - Low cost, high evidence: try it on a small project
   - High cost, low evidence: do not adopt yet

5. REPLACE CHECK: Does it replace something you already have that works?
   - If you have a working solution: require measured evidence it is better
     before switching. "Newer" is not a reason.
```

### The 20% Time Pattern

Production AI engineering is not a field where you can stay current by reading. You stay current by building. The practical pattern:

- **80% of engineering time:** production work, existing systems, known patterns
- **20% of engineering time:** exploration. One new tool per quarter, evaluated on a real problem.

The exploration work produces two things: new capability when the tool is genuinely better, and informed judgment when the tool is not. Both have value. The informed "I tried X and here is why we are not using it" is as valuable as "we adopted X."

---

## Build It

### The Learning Path Recommender CLI

The CLI in `code/main.py` takes a learning goal, maps it to specific curriculum artifacts for review, suggests three next steps from a curated reading list, and generates a 4-week practice plan. Demo mode requires no API calls.

```bash
# Demo mode: no API key required
python main.py --demo "get better at eval-driven development"
python main.py --demo "prepare for FDE interviews"
python main.py --demo "understand agent patterns better"

# With Claude for more specific plans
python main.py --goal "build production RAG systems" --weeks 4
python main.py --goal "improve my observability practices" --weeks 6
```

**Demo mode output for "get better at eval-driven development":**

```
Learning Goal: get better at eval-driven development

Review these curriculum artifacts first:
  - skill-golden-set-builder.md (P05-02): Golden set construction methodology
  - eval-llm-as-judge-template.md (P05-04): LLM-as-judge evaluation template
  - prompt-go-no-go-decision.md (P05-06): Go/no-go decision framework
  - skill-eval-driven-dev-guide.md (P05-09): Eval-driven development workflow

Three next steps:
  1. Read: "Your AI Product Needs Evals" - Hamel Husain (hamel.dev)
  2. Build: Add a golden set eval to a project you have deployed. Measure quality
     baseline before making any prompt change.
  3. Study: Anthropic's evals documentation for model-graded evals
     (docs.anthropic.com/en/docs/test-and-evaluate)

4-Week Practice Plan:
  Week 1: Rebuild the P05 eval harness from scratch on a new use case
  Week 2: Write an LLM-as-judge prompt, test its agreement rate with human labels
  Week 3: Make 3 prompt changes to an existing project, use eval to decide which to keep
  Week 4: Write a go/no-go report with supporting evidence for a real or synthetic deployment
```

> **Real-world check:** Why does the demo mode work without an API call? The mapping from learning goals to curriculum artifacts is deterministic: "eval" maps to Phase 05 artifacts, "agents" maps to Phase 04, "FDE" maps to Phase 11. Using an LLM for this lookup adds latency and cost for no quality gain. API calls earn their keep when the task requires reasoning over open-ended input - not when it is a structured lookup.

---

## Use It

### Claude as a Learning Coach

Give Claude the curriculum context and ask it to generate a personalized 90-day plan:

```
I have completed a 12-phase Applied AI engineering curriculum covering:
- Phase 01: Context engineering and prompt design
- Phase 02: RAG and retrieval pipelines
- Phase 03: Tools and MCP
- Phase 04: Agents and multi-agent patterns
- Phase 05: Evaluation and eval-driven development
- Phase 06: Shipping AI services
- Phase 07: Observability with Langfuse and OpenTelemetry
- Phase 08: Security and guardrails
- Phase 09: Fine-tuning
- Phase 10: Multimodal and voice
- Phase 11: FDE skills (scoping, handoff, stakeholder communication)
- Phase 12: Capstone projects

My target role is: [Applied AI Engineer / FDE / AI Solutions Engineer]
My strongest areas from the curriculum: [list 3]
My weakest areas: [list 2]
My current job context: [brief description, or "job searching"]

Generate a 90-day skill maintenance and growth plan that:
1. Maintains the foundations I built (15 min/day max)
2. Deepens the 2-3 areas most relevant to my target role
3. Includes 5 specific small projects to build over 90 days (buildable in a weekend each)
4. Names 3-5 specific information sources to track (not general "stay current" advice)
5. Ends with a self-assessment question for each of the 5 curriculum pillars
```

### The Gate Playbook for Ongoing Self-Assessment

Use the `/gate` playbook from the curriculum for ongoing competency checks. Apply it quarterly:

1. Pick 5 representative tasks (one per pillar: context, RAG, agents, eval, deployment)
2. Attempt each task without looking at your notes
3. Compare to your curriculum artifacts from when you first completed each phase
4. Note where you needed to reference materials vs. where it was fluent
5. The gap is your next learning priority

> **Perspective shift:** The `/gate` playbook is designed for assessing understanding at the end of a phase. Applied quarterly to your own skills, it becomes a different tool: a fluency diagnostic. The goal is not to pass - it is to identify which foundations have stayed sharp and which have drifted. Drift is normal. The diagnostic makes it visible before it becomes a problem in production.

---

## Ship It

The output artifact is at `outputs/prompt-continued-learning-map.md`.

It contains a reusable prompt template that takes:
- Your target role
- Your current experience level
- Your top 3 areas from this curriculum

And outputs:
- A 90-day skill maintenance plan with specific weekly commitments
- 5 specific projects to build next (each scoped to a weekend)
- A curated reading list of 3-5 sources with a specific reason for each

---

## Evaluate It

### Closing the Curriculum Loop

The final evaluation is a self-assessment against the role you targeted at the start of the curriculum. Run the `/gate` playbook for Phase 12 across all five pillars.

**The "I Can Now..." Statement**

Complete this for each pillar. Be specific - no adjectives without artifacts:

```
CONTEXT ENGINEERING (Phase 01)
"I can now: design a system prompt for a multi-step task, set a token budget,
use few-shot examples to shift model behavior, and diagnose a prompt that is
failing its quality target. Evidence: P01 artifacts, P12 capstone prompts."

RETRIEVAL AND RAG (Phase 02)
"I can now: choose a chunking strategy for a given document type, build a
pgvector retrieval pipeline, run a RAGAS evaluation, and interpret the results
to decide whether retrieval quality is good enough to deploy. Evidence: P02 runbook,
P12-01 capstone."

AGENTS (Phase 04)
"I can now: select between a router, single agent, and multi-agent based on
requirements, implement a tool-using agent with safe boundaries, and measure
whether the agent is meeting its quality target. Evidence: P04 runbook,
P12-02 and P12-04 capstones."

AI EVALUATION (Phase 05)
"I can now: build a golden set for a new use case, design an LLM-as-judge
evaluation, make a go/no-go decision with documented evidence, and set up
monitoring to detect post-deployment drift. Evidence: P05 eval artifacts,
P12-05 golden set evaluation."

DEPLOYMENT AND FDE SKILLS (Phases 06, 11)
"I can now: scope an AI engagement from a vague ask to a measurable AI spec,
deploy a service with Docker and FastAPI, produce a four-part handoff package,
and measure business impact against defined success criteria. Evidence:
P11 artifacts, P12-05 FDE engagement runbook."
```

### Gap Measurement

After completing the "I can now..." statements:

1. Map them to the job requirements for your target role
2. Identify 1-2 areas where the statement feels thin (you can write it but cannot execute it fluently)
3. Those areas become the first two items in your 90-day plan

The curriculum is complete. The learning is ongoing.
