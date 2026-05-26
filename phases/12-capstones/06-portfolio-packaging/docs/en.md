# Portfolio Packaging and Interview Prep

> Your portfolio is not the code. It is the argument that you can do the job.

**Type:** Learn
**Languages:** Python
**Prerequisites:** All prior phases
**Time:** ~2 hours
**Phase:** 12 · Capstones

---

## Learning Objectives

- Articulate the three questions every Applied AI Engineer and FDE interviewer asks, and map your curriculum artifacts to each
- Generate a formatted PORTFOLIO.md that groups artifacts by phase and surfaces the strongest capstone projects
- Write a project writeup for any capstone that answers all three interviewer questions in under 300 words
- Use the portfolio presentation prompt template to generate a tailored cover letter and project description from any job posting
- Identify which artifacts to highlight for Applied AI Engineer vs. FDE vs. AI Solutions Engineer roles

---

## The Problem

You have finished 12 phases of AI engineering work. You have roughly 150 reusable artifacts, 8+ capstone projects, and hands-on experience with context engineering, RAG, agents, evaluation, shipping, observability, security, fine-tuning, multimodal, and FDE skills.

But a hiring manager opening your GitHub repo sees 150 files organized by phase number and no narrative. They have 30 seconds before they decide whether to keep reading.

The problem is not the work. The problem is the presentation. Strong engineers lose opportunities to weaker candidates who package their work better. Your portfolio needs to answer three questions in 30 seconds, or the rest of the work is invisible.

This lesson is about building the packaging layer: the generated index, the project writeups, and the prompt template that customizes the presentation for any specific role.

---

## The Concept

### The Three-Question Test

Every interviewer for Applied AI Engineer, FDE, and AI Solutions Engineer roles is really asking three questions. They may not say them out loud, but every question they ask is a proxy for one of these:

```
QUESTION 1: Can you build it?
  Evidence: capstone projects with working code and measurable results
  What they fear: engineers who know the theory but cannot ship

QUESTION 2: Do you know when NOT to build it?
  Evidence: pattern decision artifacts, AI specs with explicit out-of-scope sections,
            scoping writeups that rejected complexity
  What they fear: engineers who reach for agents when a prompt would do

QUESTION 3: Can you deliver it to a customer?
  Evidence: FDE engagement, handoff packages, eval reports with go/no-go decisions,
            runbooks written for non-engineers
  What they fear: engineers who build but cannot communicate, scope, or hand off
```

Your curriculum has evidence for all three. The packaging job is to surface that evidence in the right order for the right audience.

### Artifact Map: Capstones to Job Requirements

```
ROLE: Applied AI Engineer
Key requirements: build and evaluate LLM systems, prompt engineering,
                  RAG, agents, production deployment, observability
Top artifacts to surface:
  - P12-01 through P12-04: capstone projects (build evidence)
  - P05 eval artifacts: RAGAS eval harness, LLM-as-judge framework
  - P06 shipping: FastAPI service template, Docker deployment pattern
  - P07 observability: Langfuse integration, GenAI tracing guide
  - P02 RAG artifacts: retrieval pipeline, chunking strategy guide

ROLE: Forward-Deployed Engineer (FDE)
Key requirements: customer discovery, scoping, demos that work on real data,
                  handoff packages, business impact measurement
Top artifacts to surface:
  - P12-05: FDE mock engagement (this capstone - the whole thing)
  - P11 artifacts: scoping interview guide, AI spec template, handoff template
  - P12-02 customer support agent: agent with production constraints
  - P05 evals: go/no-go decision framework
  - P08 security: guardrails and input validation (customers ask about safety)

ROLE: AI Solutions Engineer
Key requirements: technical sales support, POCs, integration patterns,
                  explaining tradeoffs to non-technical stakeholders
Top artifacts to surface:
  - P11 communication artifact: stakeholder presentation template
  - P12-01 through P12-05: all capstones (breadth evidence)
  - P04 agents: pattern selection guide
  - P03 tools/MCP: integration patterns
  - P05 evals: evidence that you measure before you claim
```

### Portfolio Narrative Structure

```
HERO SECTION (30 seconds)
  Name, role target, one-line summary
  3-5 featured projects with outcome statements

PROJECT WRITEUPS (3 minutes each)
  The problem (1 sentence): what real pain did this solve?
  The build (2-3 sentences): what did you build and how?
  The result (1-2 sentences): what did you measure, what worked?
  The artifact (link): what can they reuse or review?

ARTIFACT INDEX (searchable reference)
  All artifacts grouped by phase and type
  Skill, prompt, runbook, eval, service-template labels
  Quick-filter by role relevance
```

---

## Build It

### The Portfolio Generator CLI

The CLI in `code/main.py` reads `outputs/index.json` (the curriculum artifact index), groups artifacts by phase and type, and generates a `PORTFOLIO.md` with:
- A project summary table (capstone projects only)
- Artifact count by phase and type
- A recommended "feature projects" list: the 5 artifacts most relevant for a job application
- A sample interview narrative from a built-in template

```bash
# Generate PORTFOLIO.md from the artifact index
python main.py --generate

# Generate with a role filter (emphasizes relevant artifacts)
python main.py --generate --role fde
python main.py --generate --role applied-ai-engineer
python main.py --generate --role solutions-engineer

# Count artifacts by type across all phases
python main.py --count

# Generate a sample interview narrative for a specific capstone
python main.py --narrative --project email-triage
```

The demo mode (no index.json required) uses a hardcoded artifact list that mirrors the full curriculum:

```bash
python main.py --demo --generate
```

> **Real-world check:** Why generate PORTFOLIO.md from a script instead of writing it by hand? The curriculum has roughly 150 artifacts across 12 phases. Any hand-written index goes stale the moment you add a new artifact. The generator runs against the current state of the repo. More importantly, a script that generates a portfolio from structured data is itself portfolio evidence - it demonstrates you think about maintainability.

### Feature Project Selection Algorithm

The script uses a simple scoring heuristic:

```python
FEATURE_PROJECT_SCORES = {
    "capstone": 10,   # Any phase 12 lesson
    "runbook": 7,     # Operational artifact
    "eval": 6,        # Evaluation artifact
    "service": 5,     # Deployable service
    "prompt": 4,      # Reusable prompt
    "skill": 3,       # Process skill
}
```

Capstones always score highest. Within capstones, those with a go/no-go evaluation artifact score above those without. The top 5 become the feature projects list in `PORTFOLIO.md`.

---

## Use It

### GitHub README with Badges

The same output formatted as a GitHub README:

```markdown
# Applied AI From Scratch

![Lessons complete](https://img.shields.io/badge/lessons-157-green)
![Phases done](https://img.shields.io/badge/phases-12-blue)
![Artifacts built](https://img.shields.io/badge/artifacts-~150-orange)

## Featured Projects

| Project | What it demonstrates | Artifact |
|---------|---------------------|---------|
| Email Triage MVP | FDE engagement, go/no-go eval, handoff | runbook-fde-engagement-playbook.md |
| RAG Production Pipeline | Retrieval, chunking, RAGAS evaluation | rag-pipeline-template.md |
| Customer Support Agent | Agent patterns, tool use, safety | skill-agent-implementation-guide.md |
| Text-to-SQL Analytics | Tool calling, structured output | skill-sql-agent-safety-guide.md |
| Coding Automation Agent | Agents, code execution, safety | skill-coding-agent-patterns.md |
```

### LinkedIn Featured Section

The 5 feature projects map directly to LinkedIn Featured entries. For each:
1. Take the project writeup generated by `python main.py --narrative`
2. Add a link to the GitHub folder (not the artifact file - the folder with README context)
3. Set the thumbnail to a screenshot of the eval output or architecture diagram
4. Use the outcome statement as the LinkedIn description (under 200 characters)

> **Perspective shift:** Recruiters and hiring managers at AI-forward companies are not reading GitHub repos line by line. They are pattern-matching for signal: "Did this person ship something end to end? Do they know how to evaluate it? Did they document it?" The portfolio generator is not about impressing engineers - it is about being readable to the people who decide whether to get you to the engineering interview.

---

## Ship It

The output artifact is at `outputs/prompt-portfolio-presentation-guide.md`.

It contains a reusable prompt template that takes:
- A job posting (URL or pasted text)
- Your top 3 capstone projects from this curriculum
- Your target role (Applied AI Engineer / FDE / Solutions Engineer)

And outputs:
- A tailored project writeup that maps your curriculum work to the job requirements
- The 3 most relevant artifacts to highlight for that specific role
- 5 likely interview questions with answer frameworks based on your artifacts

The template is designed to be used with Claude, GPT-4, or any frontier model. It is a prompt, not a script.

---

## Evaluate It

### Does the Generator Work?

Run against the curriculum state:

```bash
python main.py --demo --generate
```

Verify:
1. Every capstone project (P12-01 through P12-07) appears in the feature projects table
2. Artifact counts by phase are non-zero for phases 00-12
3. Runbook artifacts score above plain prompt artifacts in feature project selection
4. The generated PORTFOLIO.md has no placeholder text (no `[fill in]` sections)

### Does the Narrative Answer the Three Questions?

For each featured project writeup, check manually:
- Q1 (Can you build it?): Is there a specific technical description with measurable output?
- Q2 (Do you know when not to?): Is there a scoping or pattern decision mentioned?
- Q3 (Can you deliver it?): Is there a handoff artifact or evaluation result referenced?

If any writeup misses one of the three questions, revise the narrative template.

### Role Alignment Check

Run the three role filters and verify the artifact ranking shifts appropriately:

```bash
python main.py --demo --generate --role fde         # P12-05 and P11 artifacts ranked highest
python main.py --demo --generate --role applied-ai-engineer  # P05 and P12 capstones ranked highest
python main.py --demo --generate --role solutions-engineer   # P11 comms + all capstones ranked
```

The feature projects list should differ meaningfully between roles. If the same 5 artifacts appear for all three roles, the scoring weights need adjustment.
