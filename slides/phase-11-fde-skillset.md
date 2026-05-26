---
marp: true
theme: applied-ai
class: title
paginate: true
footer: 'Applied AI From Scratch · Phase 11'
---

# Phase 11: The Forward-Deployed Skillset
## The part nobody teaches

Phase 11 of 13 · 10 lessons · ~10 hours

<!-- SPEAKER: Welcome to Phase 11. Every other phase in this curriculum is about building things. This one is about deploying them into the real world, and keeping them there. The skills here are the difference between a demo that impresses and a system that ships. Time: ~5 min -->

---

## Who this is for

You are an engineer who:

- Has built working AI features (prompting, RAG, agents, evals)
- Has seen a pilot die between demo and production
- Wants to be the engineer who gets called back by the customer

**What you will NOT get:**
- Soft-skills lectures
- "Communication tips" without frameworks
- Theory divorced from the deployment loop

<!-- SPEAKER: This phase assumes you can build. The gap we're closing is between building something that works on your laptop and shipping something a customer operates six months later without you. -->

---

## What you will build: the FDE toolkit

| Artifact | Lesson |
|----------|--------|
| Discovery interview template | 11-02 |
| AI spec one-pager | 11-03 |
| Pattern decision guide | 11-04 |
| Demo prep checklist | 11-05 |
| Scope change playbook | 11-06 |
| Integration audit checklist | 11-07 |
| Business impact measurement plan | 11-08 |
| Handoff package template | 11-09 |
| Stakeholder translation guide | 11-10 |

<!-- SPEAKER: Every artifact in this phase is a template you fill in for your next engagement. The toolkit is the deliverable. -->

---

<!-- _class: section -->

## The Through-Line

### Why 95% of AI pilots fail

---

## The pilot-to-production gap

```ascii
PILOT                           PRODUCTION
──────────────────────────────────────────────────────────────
Synthetic or curated data       Messy, incomplete, real data
Single user, local network      Multiple users, firewalls, SSO
Scope defined by engineer       Scope defined by stakeholder
"It worked in the demo"         "It broke on day one"
Model metrics tracked           Business metrics never measured
Engineer stays on call          Engineer is gone in 6 weeks
──────────────────────────────────────────────────────────────
The gap is not the model. The gap is everything around it.
```

<!-- SPEAKER: Read across each row. The left column is where every AI pilot starts. The right column is what production actually looks like. The FDE skills close this gap. -->

---

## Why pilots fail: the real breakdown

```ascii
AI PILOT FAILURE CAUSES (estimated)
─────────────────────────────────────────────────────
Requirements never properly scoped     ████████████ 30%
Demo used synthetic or curated data    ████████     20%
Integration blockers discovered late   ████████     20%
Business impact never measured         ██████       15%
Handoff left customer unable to op.    ██████       15%
─────────────────────────────────────────────────────
Model quality:                                        1%
```

> **Key insight:** The model is almost never the reason a pilot fails.

<!-- SPEAKER: These are not made-up numbers. They reflect patterns across real enterprise AI deployments. The point is directional: fix the process, not the model. -->

---

## The FDE engagement flow

<div class="mermaid">
flowchart LR
    A[Vague ask] --> B[Scoping interview]
    B --> C[AI spec one-pager]
    C --> D[Pattern decision]
    D --> E[Build and integrate]
    E --> F[Demo on real data]
    F --> G{Customer\napproves?}
    G -->|no| H[Scope change\nplaybook]
    H --> C
    G -->|yes| I[Deploy and observe]
    I --> J[Handoff package]
    J --> K[Customer operates\nindependently]
</div>

<!-- SPEAKER: This is the spine of Phase 11. Every lesson covers one box in this flow. The loop back through scope change is intentional: it is the default path, not the exception. -->

---

<!-- _class: section -->

## L01: What an FDE Actually Does

---

## The FDE role defined

**FDE: Forward-Deployed Engineer.** Not a salesperson. Not a researcher.

```ascii
                    Can build it
                    (engineer)
                         |
                         |
  Understands  ──────────┼────────── Communicates
  the problem             |           to non-technical
  (domain)                |           (translator)
                          |
                     THE FDE
```

The FDE sits at the intersection of all three. Remove any one and the deployment fails.

<!-- SPEAKER: A sales engineer sells. A researcher publishes. An FDE ships into a customer environment and makes it stick. The triangle is the job description. -->

---

## A day in the FDE's life

```ascii
FDE TIME ALLOCATION (typical engagement week)
──────────────────────────────────────────────
Discovery and scoping        ████████████  30%
Building and integrating     ████████████  30%
Demos and presenting         ████████       20%
Handoff and documentation    ████████       20%
──────────────────────────────────────────────
Writing code: roughly half the job.
Everything else: the other half nobody warns you about.
```

> **Key insight:** If you spend 90% of your time coding, the deployment will probably fail.

<!-- SPEAKER: The ratio surprises most engineers. The non-coding half is what this phase teaches. -->

---

<!-- _class: section -->

## L02: Scoping Before Solving

### The most common FDE mistake

---

## The mistake: building before understanding

```ascii
COMMON PATTERN                     CORRECT PATTERN
──────────────────────────────     ──────────────────────────────
Customer: "We want AI for X"       Customer: "We want AI for X"
Engineer: "Great, I'll build it"   Engineer: "Tell me more..."
                                              (discovery interview)
[2 weeks of work]                  [2-hour interview]

"This isn't what we needed"        AI spec agreed and signed off
[Back to zero]                     [Build starts with clarity]
──────────────────────────────     ──────────────────────────────
Cost: weeks                        Cost: hours
```

<!-- SPEAKER: The most expensive thing an FDE can do is start building before understanding the problem. The discovery interview is the cheapest investment in the engagement. -->

---

## Discovery interview template

```ascii
SCOPING INTERVIEW: Applied AI Engagement
─────────────────────────────────────────
1. What does success look like? (quantified if possible)
2. What does failure look like?
3. What data do you have today?
4. Who owns the data? Who can grant access?
5. What systems must this integrate with?
6. What is the timeline and budget?
7. Who are the end users?
8. What is the approval process for AI output?
─────────────────────────────────────────
RED FLAGS TO LISTEN FOR:
  "We have lots of data"      (ask: what quality? what format?)
  "We just want to add AI"    (ask: to what end? what problem?)
  "We saw ChatGPT do it"      (ask: in what context? what data?)
```

<!-- SPEAKER: Print this. Use it on every engagement. The red flags are patterns that predict scope explosion. Probe them early. -->

---

<!-- _class: section -->

## L03: Discovery: Vague Ask to AI Spec

---

## The AI spec: bridge to implementation

The AI spec converts a vague ask into a contract both sides can execute against.

**One-pager rule:** if it does not fit one page, the scope is too large.

```ascii
AI SPEC: [Project Name]
─────────────────────────────────────────
Problem:    [1 sentence: the actual problem, not the solution]
Success:    [quantified metric: X% reduction in Y, within Z weeks]
Input:      [what goes in: format, volume, source system]
Output:     [what comes out: format, destination, consumer]
Data:       [available: yes/no | format | owner | access status]
Integrates: [system A, system B (auth type for each)]
Risks:      [top 3, each with a mitigation]
Timeline:   [phases with milestone dates]
─────────────────────────────────────────
Signed off by: _____________  Date: ______
```

<!-- SPEAKER: The sign-off line is not bureaucracy. It is protection. Without it, "we agreed on this" is always your word against theirs when scope creep hits. -->

---

## What a good success metric looks like

```ascii
WEAK SUCCESS METRICS          STRONG SUCCESS METRICS
─────────────────────────     ─────────────────────────────────
"Users like it"               "Support ticket volume drops 30%"
"It's faster"                 "Avg handle time drops from 8m to 5m"
"Better answers"              "Accuracy on held-out set > 85%"
"Fewer errors"                "Error rate on invoice parsing < 2%"
"Saves time"                  "Analyst saves 2h/day on report gen"
─────────────────────────     ─────────────────────────────────
Weak metrics make it          Strong metrics make it possible
impossible to know if         to know when you are done and
you have shipped.             when the system is working.
```

<!-- SPEAKER: If the customer cannot give you a strong success metric, you cannot know when you have shipped. Spend the time here. It saves time everywhere else. -->

---

<!-- _class: section -->

## L04: Choosing the Right Pattern

---

## The pattern decision guide

```ascii
PATTERN SELECTION: start at the top, stop at the first YES
──────────────────────────────────────────────────────────────────
Q: Does it need consistent format or style from examples?
   YES → fine-tune (consider carefully, high cost)
   NO  → continue

Q: Does it need multi-step reasoning with external tools?
   YES → agent (ensure budget governor + observability)
   NO  → continue

Q: Does it need to search or retrieve from a corpus?
   YES → RAG (pgvector default, Qdrant at scale)
   NO  → continue

Q: Does it need structured output?
   YES → structured prompt with Pydantic/Zod schema
   NO  → direct prompt call
──────────────────────────────────────────────────────────────────
Rule: pick the simplest pattern that meets the success metric.
```

<!-- SPEAKER: The ladder runs bottom to top in terms of complexity and cost. Most customer problems sit at the bottom two rungs. The pull toward agents because they "sound impressive" is real. This framework counters it. -->

---

## The complexity trap

```ascii
COMMON MISTAKE
──────────────────────────────────────────────────────────────────
Customer ask:  "Summarize our support tickets by category"

What teams build:  multi-agent orchestrator with tool use,
                   vector retrieval, ReAct loop, sub-agents

What actually works:  one prompt + structured output schema
                      runs in 200ms, costs 0.02 cents per call

──────────────────────────────────────────────────────────────────
Ask before adding complexity:
  Does this actually need memory and multi-step reasoning?
  Or is it a single API call with good prompting?
```

> **Key insight:** Complexity you add to impress is complexity you support forever.

<!-- SPEAKER: The customer does not care about the architecture. They care about the outcome. Always validate that the complexity is load-bearing before committing to it. -->

---

<!-- _class: section -->

## L05: Demos That Survive Real Data

---

## The three demo failure modes

```ascii
FAILURE MODE 1: The Curated Data Problem
  Worked on:   20 hand-selected clean documents
  Broke on:    10,000 production documents with 15 formats

FAILURE MODE 2: The Format Assumption Problem
  Worked on:   PDFs from one vendor
  Broke on:    Scanned PDFs, image-only PDFs, proprietary exports

FAILURE MODE 3: The Single-User Problem
  Worked on:   One user, local network, no auth
  Broke on:    Five concurrent users, SSO, corporate firewall
```

**The rule:** test on real customer data before the demo, not after.

<!-- SPEAKER: Every one of these has killed a real deployment. The fix is the same each time: get real data early and break things before the customer watches you break them. -->

---

## Demo prep checklist

```ascii
DEMO PREP: minimum bar before showing a customer
──────────────────────────────────────────────────
Data
  [ ] Tested on minimum 100 real production examples
  [ ] Identified the 3 hardest cases, tested explicitly
  [ ] Confirmed behavior on malformed / empty input

Failure
  [ ] System fails gracefully (no stack traces visible)
  [ ] "I don't have enough information" works correctly
  [ ] Error messages are customer-readable

Load
  [ ] Tested at expected concurrency (not just 1 user)
  [ ] Latency acceptable at p95, not just average

Rollback
  [ ] Can revert to previous behavior if demo breaks
  [ ] Backup slides prepared for live-demo failure
──────────────────────────────────────────────────
"I don't have enough information" beats a hallucination every time.
```

<!-- SPEAKER: Graceful degradation is the most underrated demo skill. A confident wrong answer during a demo is a lost contract. A clear "I can't answer that" is recoverable. -->

---

<!-- _class: section -->

## L06: Mid-Stream Scope Changes

### The default, not the exception

---

## The scope change playbook

Scope change is the default state of every real engagement.

```ascii
SCOPE CHANGE PLAYBOOK: 4 steps
──────────────────────────────────────────────────────────────────
Step 1: ACKNOWLEDGE
  "Got it, I understand the request."
  Do not commit. Do not refuse. Acknowledge first.

Step 2: ASSESS IMPACT
  Time added:       ___ days / weeks
  Complexity added: low / medium / high
  Dependencies:     ____________________

Step 3: PRESENT OPTIONS
  Option A: Build it now    (cost: X, delay: Y)
  Option B: Build it later  (cost: X, no delay now)
  Option C: Alternative:    (describe simpler approach)

Step 4: UPDATE THE SPEC
  Revise AI spec, get written sign-off, update timeline.
──────────────────────────────────────────────────────────────────
Never say yes without impact assessment.
Never say no without an alternative.
```

<!-- SPEAKER: The two failure modes are equally bad: agreeing without thinking (and then missing deadlines) or refusing without offering a path forward (and damaging the relationship). The playbook threads both. -->

---

## The scope change conversation

```ascii
CUSTOMER: "Can we also add X while you're in there?"

WRONG RESPONSE A: "Sure, no problem!"
  Result: timeline slips, customer surprised, trust damaged

WRONG RESPONSE B: "That's out of scope."
  Result: customer feels dismissed, relationship damaged

RIGHT RESPONSE:
  "Good idea. Let me assess the impact and I'll have
   options for you by end of day. My instinct is it's
   a [small/medium/large] addition. I'll confirm."

  [come back with the 3 options from the playbook]
```

<!-- SPEAKER: The right response buys time to think while keeping the relationship intact. The assessment is not a delay tactic. It is the professional standard. -->

---

<!-- _class: section -->

## L07: Integrating into a Messy Customer Environment

---

## The four integration blockers

```ascii
BLOCKER 1: DATA FORMAT SURPRISE
  Expected:   clean JSON from a REST API
  Reality:    scanned PDFs, Excel with merged cells,
              proprietary export format from 2009
  Fix:        confirm format with a real sample before scoping

BLOCKER 2: AUTH COMPLEXITY
  Expected:   API key
  Reality:    SSO with SAML, internal OAuth, IP allowlist,
              VPN required, cert-pinned endpoints
  Fix:        ask "how do internal services authenticate?" day one

BLOCKER 3: NETWORK RESTRICTIONS
  Expected:   outbound HTTPS to LLM API
  Reality:    no outbound internet from data center,
              LLM API blocked at firewall
  Fix:        run network audit before architecture decision

BLOCKER 4: COMPLIANCE REQUIREMENTS
  Expected:   send data to Claude API
  Reality:    data cannot leave EU, cannot go to third-party API
  Fix:        ask data residency questions in scoping interview
```

<!-- SPEAKER: Every one of these has caused a project to restart from scratch. They are all discoverable in the first week if you ask the right questions. The integration audit checklist is how you ask them systematically. -->

---

## Integration audit checklist

```ascii
INTEGRATION AUDIT: run before architecture is finalized
──────────────────────────────────────────────────────────
Data
  [ ] Format confirmed (CSV, PDF, API, DB: actual sample seen)
  [ ] Volume confirmed (records/day, file sizes)
  [ ] PII categories documented
  [ ] Compliance requirements documented (GDPR, HIPAA, etc.)

Auth
  [ ] Auth type confirmed (API key, OAuth, SAML, cert)
  [ ] Test credentials obtained and verified working
  [ ] Production credential provisioning process documented

Network
  [ ] Outbound internet allowed from runtime environment
  [ ] Firewall rules for LLM API endpoints confirmed
  [ ] Data residency requirements documented
  [ ] VPN or private link requirements confirmed

Deployment
  [ ] Target environment confirmed (cloud, on-prem, hybrid)
  [ ] Container / Kubernetes policy confirmed
  [ ] Secret management approach confirmed
──────────────────────────────────────────────────────────
Run this in week one. Not week four.
```

<!-- SPEAKER: The checklist sounds tedious. It takes 90 minutes. The cost of skipping it is measured in weeks. -->

---

<!-- _class: section -->

## L08: Measuring Business Impact

---

## Model metrics vs. business metrics

```ascii
MODEL METRICS            BUSINESS METRICS
────────────────         ────────────────────────────────────
Accuracy: 87%            Support tickets resolved without human: +40%
Latency: 320ms p95       Avg handle time: 8min → 5min
Cost: $0.002/call        Analyst hours on report generation: -2h/day
RAGAS score: 0.81        Invoice processing error rate: 8% → 1.5%
────────────────         ────────────────────────────────────
Necessary                Sufficient for the business to care
```

> **Key insight:** Model metrics prove the system works. Business metrics prove the deployment was worth doing.

<!-- SPEAKER: A system with 87% accuracy that nobody uses has zero business impact. A system with 75% accuracy that saves each analyst 2 hours per day has massive business impact. Measure both. Report the second one to stakeholders. -->

---

## The measurement plan

```ascii
BUSINESS IMPACT MEASUREMENT PLAN
──────────────────────────────────────────────────────────────────
Step 1: ESTABLISH BASELINE (before deployment)
  Metric:        [the business metric, e.g., avg handle time]
  Current value: [measured, not estimated]
  Measured by:   [data source, method]
  Sample size:   [N observations over M weeks]

Step 2: DEFINE ATTRIBUTION
  What behavior change indicates the AI caused the improvement?
  What confounds must be controlled? (team change, seasonality)

Step 3: MEASURE AFTER (4-6 weeks post-deployment)
  Same metric, same method, comparable period

Step 4: REPORT
  "Before: X. After: Y. Change: Z%. Attributed to: AI system."
  One number. One sentence. Show it to the executive.
──────────────────────────────────────────────────────────────────
Common mistake: measuring "users love it" instead of task outcomes.
```

<!-- SPEAKER: The attribution step is where most measurement plans fail. "Things got better" is not attribution. You need a mechanism. Even a simple before/after with controls is enough for most business cases. -->

---

<!-- _class: section -->

## L09: Handoff: Docs, Runbooks, Teaching the Team

---

## The handoff test

> A handoff that fails leaves the customer unable to operate the system six months later.

**The handoff test:** Can the customer's team, without you, reproduce a bug and fix it?

```ascii
HANDOFF PACKAGE: minimum viable
──────────────────────────────────────────────────────────────────
1. ARCHITECTURE DOC (one page, with diagrams)
   What each component does, how data flows, what can fail

2. OPERATIONS RUNBOOK
   How to restart the service
   How to update prompts without redeployment
   How to debug a bad output (log location, trace ID)
   How to roll back to the previous version

3. TRAINING SESSION (recorded)
   Walk through the runbook live
   Break something deliberately, fix it while they watch

4. CONTACT PLAN
   Who to contact for what, for how long after handoff
   Do not ghost. Define the support window explicitly.
──────────────────────────────────────────────────────────────────
```

<!-- SPEAKER: The recording of the training session is the most underused asset in a handoff. Six months later when the engineer who attended has left, the recording is what saves the deployment. -->

---

## The most common handoff failures

```ascii
FAILURE: "It's all in the README"
  The README covers setup.
  It does not cover: what to do when the LLM starts returning
  garbage, how to update the system prompt, where the logs are.
  Fix: write a runbook, not just a README.

FAILURE: "They can figure it out"
  Engineers figure it out. Non-technical operators do not.
  A non-technical operator will turn off the system.
  Fix: test the runbook with the actual operator, not a developer.

FAILURE: "I'll be on Slack if they need me"
  Six months later you are on a different project.
  "On Slack" is not an SLA.
  Fix: define a support window with an end date.
```

<!-- SPEAKER: All three of these are failures of empathy. Put yourself in the position of the operator at 11pm six months from now. What do they need to know? Write that down. -->

---

<!-- _class: section -->

## L10: Communicating with Non-Technical Stakeholders

---

## Three audiences, three translations

```ascii
AUDIENCE            WHAT THEY WANT TO SEE
──────────────────────────────────────────────────────────────────
Technical team      Architecture, code, latency numbers,
                    error rates, prompt versions

Product/Business    Capabilities and limitations (not code),
                    what users can and cannot do,
                    known failure modes

Executives          Business impact: time saved, errors reduced,
                    revenue or cost implication
                    One number if possible
──────────────────────────────────────────────────────────────────
Wrong: showing the same deck to all three audiences.
Right: three different documents, same underlying system.
```

<!-- SPEAKER: The most common communication failure is using the technical deck in front of the executive. They do not care about tokens or RAGAS scores. They care about the number on the bottom line. -->

---

## The translation guide

```ascii
TECHNICAL TERM          STAKEHOLDER TRANSLATION
──────────────────────  ──────────────────────────────────────────
Token                   Word-chunk (roughly a word or part of one)
Hallucination           Confident wrong answer
Context window          The amount of text it can read at once
RAG                     It reads your documents before answering
Fine-tuning             Teaching it with your own examples
Embedding               Turning text into a number for comparison
Agent                   A loop that uses tools to complete a task
Latency                 Response time
p95 latency             Slowest 1 in 20 responses
──────────────────────  ──────────────────────────────────────────
Never say:  "It's just statistics" or "It's just predicting tokens"
            (true but dismissive, breaks trust with the audience)
```

<!-- SPEAKER: The translations are not dumbing down. They are precision. "Confident wrong answer" is more accurate than "hallucination" for a non-technical audience because it sets the right mental model for what to do when it happens. -->

---

<!-- _class: section -->

## Facilitator Discussion Prompts

---

## Discussion: the pilot gap

> **Facilitator prompt:** Think about an AI project you have seen or worked on. Which of the five failure causes from the through-line slide applied? What would have changed if the FDE process had been followed from day one?

- Probe: was the scope ever written down and signed off on?
- Probe: was the business metric defined before building started?
- Probe: who was responsible for the handoff, and what did it include?

Allow 10-15 min. Expect: most participants have a story about at least two of the five failure causes.

<!-- SPEAKER: This prompt almost always generates strong discussion. Let it run. The pattern recognition across different industries is valuable for the whole group. -->

---

## Discussion: the complexity trap

> **Facilitator prompt:** You are scoping an engagement. The customer asks for "an AI agent that monitors our Slack channels and automatically files Jira tickets for bugs." Walk through the pattern decision guide. What do you actually build?

- Probe: does it need multi-step reasoning, or is it classify + create?
- Probe: what is the simplest pattern that meets the success metric?
- Probe: how would you explain your choice to the customer?

Allow 10 min. Expected answer: structured prompt + Pydantic schema calling Jira API. Not an agent.

<!-- SPEAKER: The answer is intentionally counterintuitive. Most participants will jump to "agent" because of the word "monitor." Walking back to the simplest pattern is the skill. -->

---

## Discussion: the stakeholder translation

> **Facilitator prompt:** Your system achieves a RAGAS faithfulness score of 0.83 on your eval set. How do you communicate this to: (1) the engineering team, (2) the product manager, (3) the CFO?

- Probe: what does 0.83 mean in practice for the CFO?
- Probe: what business outcome does faithfulness map to?
- Probe: what would you need to measure to make this meaningful for the CFO?

Allow 8 min. Expected: the CFO conversation requires translating to error rate and business cost, not the score.

<!-- SPEAKER: The translation exercise is the hardest one. Most engineers have never had to turn an eval score into a dollar figure. This is the skill that gets FDEs promoted. -->

---

<!-- _class: section -->

## Exercises

---

## Exercises: easy / medium / hard

**Easy (30 min)**
Take a real AI use case you know (or invent one). Fill out the complete discovery interview template and AI spec one-pager. Have a colleague review it: is the success metric quantified? Is the scope on one page?

**Medium (90 min)**
Run a mock scoping interview with a partner. One plays the customer, one plays the FDE. The customer deliberately introduces two of the red flags from the template. The FDE must identify them, probe them, and update the spec accordingly. Debrief: what did the FDE miss?

**Hard (3-4 hours)**
Take an existing AI project (your own or a public case study). Write the full handoff package: architecture doc, operations runbook, training session outline. Apply the handoff test: could an operator on-call at 11pm use this to fix a broken output without calling you?

<!-- SPEAKER: The hard exercise is the one that generates the most lasting artifacts. Teams that do this exercise usually find gaps in their real production systems. -->

---

<!-- _class: section -->

## Further Reading

---

## Further reading

**On the FDE role and enterprise AI deployment**
- "Building LLM Applications for Production" by Chip Huyen (huyenchip.com): the closest thing to a textbook for production AI, covers many FDE concerns
- "The Pragmatic Engineer" newsletter, AI in the Enterprise series: real patterns from engineers at hyperscalers deploying AI internally

**On scoping and requirements**
- "Shape Up" by Ryan Singer (Basecamp): not AI-specific, but the best writing on scoping work before building it; the AI spec one-pager is inspired by this approach

**On stakeholder communication**
- "Communicating Data Science Results" by Google's People + AI Research (PAIR): practical guidance on presenting AI capabilities and limitations to non-technical audiences

**On measuring business impact**
- "Measuring the Impact of ML Models" by Shreya Shankar et al.: academic but accessible; covers attribution, confounds, and the gap between model metrics and business outcomes

<!-- SPEAKER: The Chip Huyen post is required reading. It covers deployment patterns, failure modes, and organizational dynamics that Phase 11 addresses from the FDE perspective. -->

---

<!-- _class: section -->

## What's Next

### Phase 12: Capstones

---

## Phase 12: Capstones

You have all the pieces. Phase 12 puts them together.

```ascii
PHASE 12 CAPSTONE PROJECTS
──────────────────────────────────────────────────────────────────
C01: End-to-end RAG service
     Ingestion pipeline, retrieval, eval harness, deployed API

C02: Production agent with observability
     Tool use, budget governor, tracing, guardrails, dashboard

C03: Full FDE engagement simulation
     Scoping interview, AI spec, build, demo, handoff package
     (applies every artifact from Phase 11)

C04: Multi-tenant AI feature
     Auth, rate limiting, cost tracking, per-tenant evals
──────────────────────────────────────────────────────────────────
```

The capstones are portfolio pieces. They are designed to be shown to a hiring manager or a customer.

<!-- SPEAKER: Phase 12 is the payoff. The FDE engagement simulation capstone in particular is the one that makes Phase 11 concrete. Students who do it report it changes how they approach customer conversations. -->

---

## Phase 11 complete

You now have the full FDE toolkit:

- Discovery interview template
- AI spec one-pager
- Pattern decision guide
- Demo prep checklist
- Scope change playbook
- Integration audit checklist
- Business impact measurement plan
- Handoff package template
- Stakeholder translation guide

> **Key insight:** The engineer who ships AI into production and makes it stick is not the one who knows the most about models. It is the one who closes the gap between demo and production.

**Next:** Phase 12 Capstones: put it all together.

<!-- SPEAKER: Close with the through-line. The 95% failure rate is not a law of nature. It is a skills gap. This phase closes that gap. -->

---

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
