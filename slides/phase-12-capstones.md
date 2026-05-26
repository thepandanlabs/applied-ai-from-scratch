---
marp: true
theme: applied-ai
class: title
paginate: true
footer: 'Applied AI From Scratch · Phase 12'
---

# Phase 12: Capstones
## Build the Portfolio

Phase 12 of 13 · 7 projects · ~18 hours

<!-- SPEAKER: Welcome to Phase 12. This is the integration phase. Every prior phase taught you a skill. This phase forces you to use all of them together, on real problems, under real constraints. The output is not a certificate. It is a portfolio a hiring manager or customer can click through and evaluate. Time for this intro section: ~5 min -->

---

## Who this is for

You are a **working software engineer** who:

- Has completed Phases 00-11 (or holds equivalent skills)
- Wants to move into Applied AI Engineer, FDE, or AI Solutions Engineer roles
- Needs portfolio evidence, not just course completion

**What you will NOT get:**
- Step-by-step tutorials that hand you the answer
- Synthetic toy data with curated happy paths
- "It works on my machine" as a definition of done

<!-- SPEAKER: Be direct about expectations. These projects require independent judgment. The instructions give constraints and definitions of done, not recipes. -->

---

## Prerequisites

| Skill | Where |
|-------|-------|
| RAG pipelines end-to-end | Phase 02 |
| Tool use + agent loops | Phases 03, 04 |
| Eval harnesses + golden sets | Phase 05 |
| FastAPI deployment + Docker | Phase 06 |
| Observability with Langfuse | Phase 07 |
| Guardrails + input validation | Phase 08 |
| FDE scoping and handoff | Phase 11 |

<!-- SPEAKER: This is a hard prerequisite list. If a student skips Phase 05, the evals will be hollow. If they skip Phase 08, the security stories will be missing. Both will show up in a technical interview. -->

---

## What makes a capstone

```ascii
Tutorial project           Capstone project
──────────────────────     ──────────────────────────────────
Curated test data          Real or realistic data
Works on your machine      Deployed publicly (URL exists)
No eval harness            Evaluated on golden set (score exists)
No docs                    README + architecture + runbook
Demo video optional        Demo video required
```

**The four criteria:** real data, deployed, evaluated, documented.

<!-- SPEAKER: Read this table aloud. Ask the room: how many projects on your current resume meet all four criteria? Most engineers have zero. That gap is the opportunity. -->

---

## The portfolio map

<div class="mermaid">
flowchart LR
    C1["RAG Assistant\nP02 P05 P06 P07 P08"] --> P["Portfolio"]
    C2["Support Agent\nP03 P04 P05 P08"] --> P
    C3["Text-to-SQL\nP01 P05 P06 P08"] --> P
    C4["Coding Agent\nP03 P04 P05 P08"] --> P
    C5["FDE Engagement\nP11 P04 P05 P06"] --> P
    C6["Portfolio Packaging"] --> P
    P --> J["Applied AI Engineer\nFDE\nAI Solutions Engineer"]
</div>

<!-- SPEAKER: Every capstone integrates multiple phases. The portfolio is the output. The job roles on the right are the actual hiring targets. Keep this map visible throughout the session. -->

---

<!-- _class: section -->

# C01: Production RAG Assistant
## Over a Real Corpus

Integrates: P02 · P05 · P06 · P07 · P08

<!-- SPEAKER: First capstone. This is the one most students are most comfortable with going in, and the one that exposes the most gaps on eval and observability. Budget ~25 min for this project's slides. -->

---

## C01: What you build

<div class="mermaid">
flowchart LR
    A["Corpus\n(your data)"] --> B["Chunker"]
    B --> C["Embedder"]
    C --> D["pgvector"]
    E["Query"] --> F["Retriever"]
    D --> F
    F --> G["LLM"]
    G --> H["Streaming\nresponse"]
    G --> I["Langfuse\ntrace"]
    H --> J["FastAPI"]
    J --> K["User"]
</div>

Use your own corpus: company docs, a GitHub repo, a public dataset you care about.

<!-- SPEAKER: The "real corpus" requirement is load-bearing. Students who pick a corpus they care about write better evals, because they know what a correct answer looks like. -->

---

## C01: Definition of done

```ascii
CAPSTONE C01: Production RAG Assistant
────────────────────────────────────────────────────────
[ ] Eval:    RAG Triad score > 0.75 on 20-question golden set
[ ] Deploy:  Running at Railway or Render public URL
[ ] Observe: Langfuse dashboard showing traces for all requests
[ ] Secure:  Input guardrail + output sanitization active
[ ] Document: README with setup steps + architecture diagram
[ ] Demo:    3-5 min Loom walkthrough recorded
[ ] Artifact: runbook committed to repo
```

<!-- SPEAKER: Walk through each item. Ask: which of these did the last RAG demo you saw actually have? Usually just the first. -->

---

<!-- _class: code -->

## C01: RAG Triad eval (golden set check)

```python
def rag_triad_score(question, context, answer) -> dict:
    faithfulness = judge(
        f"Is this answer fully supported by the context?\n"
        f"Context: {context}\nAnswer: {answer}",
        rubric="1=hallucinated, 5=fully grounded"
    )
    relevance = judge(
        f"Does the context contain info to answer: {question}?",
        rubric="1=irrelevant, 5=directly answers"
    )
    answer_rel = judge(
        f"Does this answer address: {question}?\nAnswer: {answer}",
        rubric="1=off-topic, 5=directly answers"
    )
    return {"faithfulness": faithfulness,
            "context_relevance": relevance,
            "answer_relevance": answer_rel}
```

> **Key insight:** All three scores must pass. A high faithfulness score on irrelevant context is still a failure.

<!-- SPEAKER: This is the eval harness from Phase 05 applied to production data. The insight is important: students often optimize one dimension. Make sure they run all three. -->

---

<!-- _class: section -->

# C02: Customer-Support Agent
## With Tools, Guardrails, and HITL

Integrates: P03 · P04 · P05 · P08

<!-- SPEAKER: Second capstone. This one is closest to what most enterprise AI teams actually build. The HITL gate is the differentiator. Time: ~20 min -->

---

## C02: What you build

```ascii
Inbound message
      |
      v
  [Guardrail]  ---- out of scope? ----> [Refuse + log]
      |
      v
  [Agent loop]
      |
  [Tool calls]
      |-- look_up_order_status
      |-- create_ticket
      |-- escalate_to_human
      |
  [HITL gate]  ---- process_refund? ---> [Human approval]
      |                                       |
      |                          approved    denied
      v                              |         |
  [Response]  <---------------------+         |
                                    [Return denied status]
```

FastAPI webhook receives inbound messages. Human approval is a real async call.

<!-- SPEAKER: The HITL gate is not optional in the definition of done. A refund action that skips human approval fails the capstone. That is intentional. -->

---

## C02: Definition of done

```ascii
CAPSTONE C02: Customer-Support Agent
────────────────────────────────────────────────────────
[ ] Eval:    Task completion rate > 80% on 15 test scenarios
[ ] Deploy:  FastAPI service with simulated inbound webhook
[ ] Observe: Traces per conversation, escalation rate logged
[ ] Secure:  Out-of-scope requests blocked, angry-customer escalation tested
[ ] HITL:    Approval gate blocks/allows refund action (tested both paths)
[ ] Document: README + tool schema + guardrail rules documented
[ ] Demo:    Loom showing approve and deny paths
[ ] Artifact: HITL gate implementation committed
```

<!-- SPEAKER: Note two security items: the guardrail for out-of-scope AND the angry-customer escalation. Both must be demonstrated in the demo video. -->

---

<!-- _class: code -->

## C02: HITL gate implementation

```python
def execute_with_approval(action: str, params: dict) -> dict:
    REQUIRES_APPROVAL = {
        "process_refund",
        "cancel_order",
        "escalate_to_manager"
    }
    if action in REQUIRES_APPROVAL:
        approval = get_human_approval(
            f"Agent requests: {action} with {params}"
        )
        if not approval:
            return {"status": "denied", "reason": "Human declined"}
    return execute_tool(action, params)
```

> **Key insight:** The approval set is a policy decision, not a code decision. Externalizing it means non-engineers can adjust it without a deploy.

<!-- SPEAKER: Ask the room: where should REQUIRES_APPROVAL live in a production system? Config file, database, or hardcoded? This is a real architecture discussion. -->

---

<!-- _class: section -->

# C03: Talk-to-Your-Data Analytics App
## Text-to-SQL

Integrates: P01 · P05 · P06 · P08

<!-- SPEAKER: Third capstone. Text-to-SQL looks simple until you try to make it safe and accurate at the same time. The eval setup is where most students struggle. Time: ~20 min -->

---

## C03: What you build

```ascii
Natural language query
         |
         v
    [LLM: NL to SQL]
         |
         v
  [SQL validator]  -- EXPLAIN before execute
         |
         v
  [Safety check]   -- blocked keywords + read-only conn
         |
         v
  [Execute query]  -- parameterized, timeout enforced
         |
         v
  [LLM: results to NL summary]
         |
         v
  [FastAPI response: JSON + summary]
```

Database: SQLite with realistic data (sales, inventory, or HR schema you build).

<!-- SPEAKER: The EXPLAIN-before-execute pattern is from Phase 08. The read-only connection is non-negotiable for the security criterion. -->

---

## C03: Definition of done

```ascii
CAPSTONE C03: Text-to-SQL Analytics App
────────────────────────────────────────────────────────
[ ] Eval:    Exact SQL match rate > 70% on 20-question golden set
[ ] Deploy:  FastAPI service with /query endpoint
[ ] Observe: Queries logged with SQL generated, latency, match flag
[ ] Secure:  No SQL injection (parameterized + read-only validated)
[ ] Safety:  EXPLAIN runs before every execution
[ ] Document: README + schema diagram + sample queries
[ ] Demo:    Loom showing correct query + attempted injection (blocked)
[ ] Artifact: SQL safety wrapper committed
```

<!-- SPEAKER: The demo must show a blocked injection attempt. Not just "it works for valid queries." Security is a first-class result, not a footnote. -->

---

<!-- _class: code -->

## C03: SQL safety wrapper

```python
BLOCKED = ["DROP", "DELETE", "INSERT",
           "UPDATE", "ALTER", "CREATE"]

def safe_execute(sql: str, conn) -> list[dict]:
    upper = sql.upper()
    if any(kw in upper for kw in BLOCKED):
        raise ValueError("Write operations not allowed")
    # Run EXPLAIN first to catch syntax errors cheaply
    conn.execute(f"EXPLAIN {sql}")
    cursor = conn.execute(sql)
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row))
            for row in cursor.fetchall()]
```

> **Key insight:** The EXPLAIN call catches malformed SQL before it touches data. It is free validation on SQLite.

<!-- SPEAKER: Point out that the BLOCKED list is a denylist, not an allowlist. Ask: what is the failure mode of a denylist? (Someone finds a keyword you forgot.) Allowlist is safer for production. -->

---

<!-- _class: section -->

# C04: Coding Automation Agent
## On a Real Repo

Integrates: P03 · P04 · P05 · P08

<!-- SPEAKER: Fourth capstone. This is the one that scares engineers the most, because the agent is operating on real code. The sandbox requirement is strict. Time: ~20 min -->

---

## C04: What you build

```ascii
Issue description (natural language)
         |
         v
    [Agent loop]
         |
    [Tool calls]
         |-- read_file(path)
         |-- write_file(path, content)
         |-- run_tests(test_path)  --> returns pass/fail + output
         |-- search_codebase(query)
         |
    [Kill switch]  -- max steps or failing assert
         |
         v
    [Output: diff + test results]

All file I/O sandboxed inside Docker.
No network access from agent container.
```

<!-- SPEAKER: The kill switch is from Phase 04. Ask: what happens to a coding agent with no kill switch and a write_file tool? This is a concrete production failure mode. -->

---

## C04: Definition of done

```ascii
CAPSTONE C04: Coding Automation Agent
────────────────────────────────────────────────────────
[ ] Eval:    Completes 3 of 5 test tasks on a real repo
[ ] Deploy:  Agent runs inside Docker (no network access)
[ ] Observe: Steps logged, tool calls recorded, token usage tracked
[ ] Secure:  All file operations sandboxed, kill switch triggers
[ ] Tasks:   Fix bug from issue description, add unit test, refactor fn
[ ] Document: README + tool schema + sandbox setup instructions
[ ] Demo:    Loom showing one task start-to-finish with test pass
[ ] Artifact: Dockerized agent scaffold committed
```

<!-- SPEAKER: "3 of 5 test tasks" is the bar. Not 5 of 5. Reliable partial completion on a real repo is harder than perfect completion on a toy. -->

---

<!-- _class: section -->

# C05: FDE Mock Engagement
## Scope, Ship, Handoff

Integrates: P11 · P04 · P05 · P06

<!-- SPEAKER: Fifth capstone. This is the most different one. No code spec is given. Students simulate a full FDE engagement from scoping call through handoff package. Time: ~20 min -->

---

## C05: What you build

```ascii
Phase 1: Scoping
  [ ] Conduct scoping interview with mock stakeholder
  [ ] Document: problem statement, success criteria, constraints
  [ ] Produce: AI spec one-pager (signed off by mock stakeholder)

Phase 2: Build
  [ ] Build working prototype on real data (chosen domain)
  [ ] Demo prototype to mock stakeholder, gather feedback
  [ ] Iterate once based on feedback

Phase 3: Handoff
  [ ] Architecture diagram (can a stranger understand it?)
  [ ] Deployment runbook (can a stranger run it?)
  [ ] Eval results (does it actually work at threshold?)
  [ ] "If I had two more weeks" section (honest scope reflection)
```

Pick a domain: HR, finance, legal, or one you know well.

<!-- SPEAKER: The mock stakeholder is real. It should be a friend, colleague, or mentor who plays the customer role. The scoping interview should be recorded or have written notes. This simulates the actual FDE workflow. -->

---

## C05: Definition of done

```ascii
CAPSTONE C05: FDE Mock Engagement
────────────────────────────────────────────────────────
[ ] Scope:   Interview conducted, notes committed to repo
[ ] Spec:    AI spec one-pager created and stakeholder sign-off documented
[ ] Build:   Prototype built and demoed on real (not synthetic) data
[ ] Eval:    At least one quantitative eval result in the handoff doc
[ ] Handoff: Architecture doc + runbook a stranger can follow
[ ] Honest:  "What I'd do differently" section present and specific
[ ] Demo:    Loom showing demo to stakeholder + their feedback
[ ] Artifact: Full handoff package committed (not just code)
```

> **Key insight:** The handoff package is the product. The prototype proves it is possible. The package proves someone else can operate it.

<!-- SPEAKER: Ask the room: have you ever received a handoff package that was actually complete? What was missing? This frames why the artifact definition is this specific. -->

---

<!-- _class: section -->

# C06: Portfolio Packaging
## Make the Work Visible

<!-- SPEAKER: Sixth capstone. Technical work that is invisible does not exist for hiring managers and customers. This section is about making the work legible. Time: ~15 min -->

---

## C06: How to present the portfolio

```ascii
For each capstone project, publish:

GitHub repo
  README.md
    - Problem (1 paragraph, no jargon)
    - Approach (what you built, why these choices)
    - Architecture diagram (mermaid or PNG)
    - Eval results (the actual numbers)
    - How to run it (Docker command or hosted URL)
    - What you'd do differently

Demo video (Loom, 3-5 min)
    - Show it working on real data
    - Show one eval result
    - Show one failure mode and how you handle it

Portfolio page (personal site or GitHub profile)
    - One-line description per project
    - Link to repo + demo
    - Eval score visible without clicking
```

<!-- SPEAKER: The eval score visible without clicking is a filter. Hiring managers spend 30 seconds on a portfolio. If the number isn't front and center, it doesn't exist. -->

---

## C06: Write-up template

```ascii
Project write-up structure (300-500 words)
──────────────────────────────────────────
1. Problem
   "I built X to solve Y for Z type of user."

2. Approach
   "I used A because B. I chose C over D because E."

3. What I built
   Architecture in one diagram. Stack listed.

4. Eval results
   "Scored X on metric Y using golden set of N examples."

5. What I'd do differently
   One specific, honest limitation. Not "I'd make it better."
   Example: "The chunking strategy is naive; overlapping
   windows would improve recall on long documents."
```

> **Key insight:** Section 5 is a signal of seniority. Junior engineers omit it. Senior engineers lead with it.

<!-- SPEAKER: The "what I'd do differently" section is often the most valuable part of a technical interview. It shows calibration. Practice saying it out loud. -->

---

## C06: Interview mapping

| Capstone | Role signal |
|----------|-------------|
| C01: RAG Assistant | Applied AI Engineer, AI Platform |
| C02: Support Agent | Applied AI Engineer, AI Products |
| C03: Text-to-SQL | Applied AI Engineer, Data + Analytics |
| C04: Coding Agent | AI Tooling, Dev Tools, AI Infrastructure |
| C05: FDE Engagement | Forward-Deployed Engineer, AI Solutions |
| C06: Portfolio | All roles: communication and judgment |

**Three target roles:** Applied AI Engineer · FDE · AI Solutions Engineer

<!-- SPEAKER: Walk through each row. Ask students which capstone maps most directly to the role they want. That capstone should be the one they polish most. -->

---

<!-- _class: section -->

# C07: What Comes Next
## The Curriculum Ends. The Learning Doesn't.

<!-- SPEAKER: Final section. This is motivational but grounded. No hype. The field moves fast; production habits are durable. Time: ~10 min -->

---

## C07: After the curriculum

```ascii
Contribute
  - Pick one open-source AI project you used in these phases
  - Open one bug report, one PR, or one test
  - You now understand the internals. Use that.

Build in a domain you care about
  - Pick a problem that makes you angry or curious
  - Apply the same loop: scope, build, eval, ship, observe
  - Boring domain + good eval discipline beats flashy demo

Apply to roles
  - Applied AI Engineer
  - Forward-Deployed Engineer (FDE)
  - AI Solutions Engineer
  - ML Platform Engineer

Stay current (without noise)
  - Latent Space podcast
  - AI Engineer newsletter (Swyx + Alessio)
  - Anthropic research blog
  - Simon Willison's weblog
```

<!-- SPEAKER: The "boring domain + good eval discipline" line is intentional. The engineers who build durable careers are the ones who apply rigor to unglamorous problems. That is the through-line of the whole curriculum. -->

---

## What stays true as models change

| What changes fast | What stays durable |
|-------------------|--------------------|
| Model capabilities | Eval discipline |
| Framework APIs | Production habits |
| Benchmark scores | Scoping and handoff skills |
| Default context windows | Observability patterns |
| Pricing | Understanding failure modes |

> **Key insight:** Your eval harness from Phase 05 works on any model. Your observability setup from Phase 07 works on any stack. Invest in the durable layer.

<!-- SPEAKER: This is the closing argument of the entire curriculum. The specific tools will change. The habits of an engineer who measures, observes, and documents will not. -->

---

## Definition of done: all capstones

```ascii
PORTFOLIO: Complete when all 5 capstones have:
────────────────────────────────────────────────────────
[ ] Eval:    golden set score meets stated threshold
[ ] Deploy:  running at a public URL or Docker image
[ ] Observe: traces/logs capturing all requests
[ ] Secure:  guardrails and input validation in place
[ ] Document: README with setup + architecture diagram
[ ] Demo:    3-5 min Loom walkthrough recorded
[ ] Artifact: runbook committed to repo

Choose any 5 of C01-C05 as your core portfolio.
C05 (FDE Engagement) is required if targeting FDE roles.
```

<!-- SPEAKER: Students often ask "do I have to do all five?" The answer is: you choose five, but C05 is required for FDE-track students. Quality over quantity. A fully done capstone beats three half-done ones. -->

---

## Discussion prompts

> **Facilitator prompt:** Which of the four capstone criteria (real data, deployed, evaluated, documented) is hardest to fake in a technical interview? Why?

> **Facilitator prompt:** You are in a 30-minute technical screen for an FDE role. Which single artifact from your portfolio do you lead with? Walk us through your reasoning.

> **Facilitator prompt:** A hiring manager says your RAG Triad score of 0.77 is good but asks: "How do you know your golden set is representative?" What do you say?

<!-- SPEAKER: These are real interview questions, not hypotheticals. Give students 5 minutes to think in pairs before opening to the group. The third question is the hardest and most important. -->

---

## Exercises

**Easy:** Take any prior phase project and add the two missing capstone criteria it lacks. Document what changed and why.

**Medium:** Build C03 (Text-to-SQL) using a real database from your current job or a public dataset (NYC taxi data, Northwind, etc.). Run the 20-question eval. Publish the results.

**Hard:** Complete C05 (FDE Mock Engagement) with an actual domain expert as your mock stakeholder. Record the scoping interview (with permission). Add their feedback verbatim to the handoff package. Publish everything.

<!-- SPEAKER: The hard exercise is the one that actually prepares engineers for FDE roles. It requires coordination with another person. That friction is the point. -->

---

## Phase 12 summary

| What you did | Why it matters |
|--------------|----------------|
| Built on real data | Shows judgment, not just technique |
| Deployed publicly | Proves production competence |
| Evaluated on golden sets | Replaces intuition with measurement |
| Documented for strangers | Demonstrates communication ability |
| Demoed on video | Makes the work legible to non-engineers |

**The portfolio is the argument.** Not "I learned AI." But "I built these systems, measured their quality, shipped them, and here are the numbers."

<!-- SPEAKER: Close with this summary. Read the right column slowly. These are the exact signals hiring managers and customers are looking for. The curriculum gives students the means to produce all five. -->

---

<!-- _class: title -->

# You shipped it.
## Now make sure someone can measure it.

**Phase 12 of 13 complete.**

Next: Phase 13 (elective depth tracks) or start applying.

<!-- SPEAKER: End on the core principle. Not "you learned it." You shipped it. And shipping without measurement is just hoping. The curriculum taught you the difference. -->

<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({
    startOnLoad: true,
    theme: 'dark',
    themeVariables: {
      primaryColor: '#7c6af5',
      primaryTextColor: '#e8e8e8',
      primaryBorderColor: '#2a2a2a',
      lineColor: '#8a8a8a',
      secondaryColor: '#252019',
      tertiaryColor: '#2e2820',
      background: '#1c1714',
      mainBkg: '#252019',
      nodeBorder: '#2a2a2a',
      clusterBkg: '#2e2820',
      titleColor: '#e8e8e8',
      edgeLabelBackground: '#2e2820',
      attributeBackgroundColorEven: '#252019',
      attributeBackgroundColorOdd: '#2e2820',
    }
  });
</script>
