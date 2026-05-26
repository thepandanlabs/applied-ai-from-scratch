---
marp: true
theme: applied-ai
class: title
paginate: true
footer: 'Applied AI From Scratch · Phase 05: Evaluation'
---

# Phase 05: Evaluation & Eval-Driven Development

### The part that separates guesswork from engineering

**Applied AI From Scratch**
14 lessons · ~15 hours · Python

<!-- SPEAKER: Welcome to Phase 05. This is the differentiator phase. Every other phase teaches you to build AI systems. This one teaches you to know whether they work. That's the harder problem. Time: ~5 min -->

---

## Who this is for

You are a **working software engineer** who:

- Has shipped an LLM feature and felt uneasy about it
- Has eyeballed outputs and called it "good enough"
- Wants to replace intuition with a repeatable engineering process

**What you will NOT get:**
- Academic benchmarks disconnected from your actual product
- Metric soup (BLEU, ROUGE, METEOR) applied blindly
- Evals as an afterthought after the feature ships

<!-- SPEAKER: The target pain is specific: you shipped something, it felt OK, and now you have no way to know if a prompt change made it better or worse. That is the gap this phase closes. -->

---

## Prerequisites

| Skill | Where |
|-------|-------|
| Calling an LLM API and parsing structured output | P01 |
| RAG pipeline: retrieve, embed, generate | P02 |
| Tool calling + basic agent loop | P03, P04 |
| Reading Python dicts and writing simple loops | any |

**Time commitment:** ~15 hours across 14 lessons. Capstone adds another 2-3 hours.

<!-- SPEAKER: The most important prerequisite is not technical. It is having built something you want to measure. Evals without a system to evaluate are abstract. -->

---

## What you will build: the eval stack

| Artifact | Lesson |
|----------|--------|
| Failure taxonomy + annotation schema | 05-02, 05-03 |
| Versioned golden set (100 examples) | 05-04 |
| LLM-as-judge scorer with calibration | 05-06 |
| Pairwise eval harness | 05-07 |
| End-to-end eval harness (raw + Braintrust) | 05-08 |
| GitHub Actions CI eval step | 05-09 |
| RAG Triad + agent trajectory evaluator | 05-10 |
| Online eval pipeline with drift detection | 05-11, 05-12 |
| A/B testing scaffold with ABRouter | 05-13 |
| Eval-first feature (capstone) | 05-14 |

<!-- SPEAKER: Every artifact is reusable. By the capstone you have a complete eval stack you can drop into any project. -->

---

## The through-line: eval-driven development

<div class="mermaid">
flowchart LR
    A[Define success] --> B[Golden set]
    B --> C[Write evals]
    C --> D[Build feature]
    D --> E[Run evals]
    E --> F{Pass?}
    F -->|no| G[Fix root cause]
    G --> D
    F -->|yes| H[Add to CI]
    H --> I[Ship + online eval]
    I --> J[Monitor drift]
    J --> B
    style A fill:#4f46e5,color:#fff
    style H fill:#10b981,color:#fff
    style F fill:#1e1e1e,color:#e8e8e8,stroke:#f59e0b
    style G fill:#1e1e1e,color:#ef4444,stroke:#ef4444
</div>

> **Key insight:** The loop does not start with code. It starts with a definition of done.

<!-- SPEAKER: This diagram is the phase. Every lesson is one segment of this loop. Keep coming back to it. -->

---
<!-- _class: section -->

## L01: Why Evals Are the Job

### The missing question

---

## L01: The problem

You shipped a new prompt. It "feels" better. A week later:

- A customer reports wrong answers
- You cannot reproduce the failure reliably
- You cannot tell if the fix you applied actually fixed anything

**The root cause:** you never defined "works correctly" in a form you could measure.

> **Key insight:** "How do you know it works?" is the most important question in AI engineering. Most teams skip it.

<!-- SPEAKER: This is the pain that motivates the entire phase. Call it out explicitly. Ask the room: how many of you shipped a prompt change last month and measured its effect? -->

---

## L01: Vibes vs engineering

```ascii
VIBES-BASED                    EVAL-DRIVEN
-----------                    -----------
Change prompt                  Define success criteria
Look at 5 examples             Build golden set (100+ examples)
"Looks good"                   Run scorer, get 0.82
Ship                           Compare to baseline (0.79)
Pray                           Gate CI, ship with confidence
Wonder what broke              Drift alert fires at 0.75
```

**The discipline gap:** software engineers would never ship without tests. AI engineers routinely do.

> **Key insight:** An eval is just a test. The fact that the output is text does not exempt it from software engineering standards.

<!-- SPEAKER: The ASCII comparison is the core of the lesson. Every column is a habit to replace. -->

---
<!-- _class: section -->

## L02: Error Analysis First

### Look at your data before building scorers

---

## L02: The problem

Teams reach for automated scorers before they understand their failure modes. They build metrics that measure the wrong thing, then tune against those metrics, and wonder why the system does not improve.

**Hamel Husain's rule:** You must manually review your outputs before you automate anything.

```ascii
WRONG ORDER            RIGHT ORDER
-----------            -----------
1. Build scorer        1. Sample 50-100 outputs
2. Run on data         2. Read them carefully
3. Get a number        3. Label what went wrong
4. Realize the         4. Build taxonomy
   number is           5. Now build scorer
   meaningless         6. Calibrate against labels
```

<!-- SPEAKER: This is one of the most counterintuitive lessons. Engineers want to automate immediately. Manual review feels slow. But it is the only way to know what you are measuring. -->

---

## L02: Open coding + annotation schema

**Open coding:** read outputs without a fixed rubric. Write down every distinct failure type you see.

**Consolidate:** cluster similar failures, give them names.

**Schema output:**

```json
{
  "failure_types": [
    "hallucinated_fact",
    "missed_context",
    "format_violation",
    "refusal_when_should_answer",
    "wrong_tool_selected",
    "chain_break",
    "latency_or_cost"
  ],
  "annotation_fields": ["id", "input", "output", "failure_type", "severity", "notes"]
}
```

Keep it flat. No nested taxonomy until you have 500+ labeled examples.

<!-- SPEAKER: The schema is the deliverable of L02. It becomes the basis for every scorer in L06 onward. -->

---
<!-- _class: section -->

## L03: Trace Review & Failure Taxonomy

### Name your failures before you count them

---

## L03: The problem

You have failures. But "it gave a bad answer" is not actionable. Without a taxonomy, every post-mortem restarts from scratch and fixes target the wrong layer.

**The 7 failure categories** (covers ~95% of production failures):

| Category | Description |
|----------|-------------|
| Wrong tool call | Called the wrong tool or skipped a required one |
| Hallucinated fact | Stated something false with confidence |
| Missed context | Had the context, did not use it |
| Format violation | Valid content, wrong structure |
| Refusal | Should have answered, did not |
| Latency or cost | Correct but unacceptably expensive |
| Chain break | Earlier step failed, error propagated silently |

<!-- SPEAKER: Drill the 7 categories. Have the room add any they have seen that do not fit. Usually they do fit on reflection. -->

---

## L03: The triage process

```ascii
New failure arrives
        |
        v
Read the full trace
        |
        v
Assign failure category (1 of 7)
        |
        v
Is it reproducible in the golden set?
   yes ---> Add to golden set, tag with category
   no  ---> Add to monitoring watchlist
        |
        v
Is the fix prompt, retrieval, or code?
   prompt    ---> Update prompt, re-run evals
   retrieval ---> Fix chunking or indexing
   code      ---> File bug, add regression test
```

> **Key insight:** Most "AI problems" are retrieval problems or prompt problems. Only a minority are model capability gaps.

<!-- SPEAKER: The triage decision tree prevents the common mistake of changing the model when the prompt or retrieval is the actual problem. -->

---
<!-- _class: section -->

## L04: Building a Golden Set

### Your 100 most important examples

---

## L04: The problem

You need a stable, representative set of examples to run your evals against. Without it, every eval run measures something slightly different.

**The golden set is not:**
- All your production data
- Randomly sampled logs
- Examples you cherry-picked because they are easy

**The golden set is:**
- ~100 examples that cover your success criteria
- Representative of real usage (not demo usage)
- Labeled with expected outputs or evaluation criteria
- Version controlled alongside your code

<!-- SPEAKER: 100 is not a magic number but it is the practical minimum. Below 50 your variance is too high. Above 500 your iteration speed suffers. -->

---

## L04: Sources and labeling

**Sources (in priority order):**

1. Real production logs (best signal, but need privacy review)
2. Synthetic: generate from real templates + parameter variation
3. Adversarial: edge cases, injection attempts, ambiguous inputs

**Labeling schema:**

```json
{
  "id": "gs-0042",
  "input": "...",
  "expected_output": "...",
  "expected_criteria": ["cites source", "under 100 words", "no hallucination"],
  "tags": ["edge_case", "multi-hop"],
  "source": "prod_log",
  "added": "2025-11-01",
  "version": "1.2"
}
```

**Version control your golden set.** Treat changes to it as breaking changes.

<!-- SPEAKER: The version field is critical. If you change your golden set without tracking it, you cannot compare scores across runs. -->

---
<!-- _class: section -->

## L05: Metrics That Matter vs Vanity Metrics

### Pick the metric that would change your decision

---

## L05: The problem

Teams report BLEU scores on open-ended generation. They optimize semantic similarity when task completion is what ships. They have dashboards full of numbers that do not tell them whether to ship.

**The test:** if the metric improved by 10%, would you ship? If no, it is a vanity metric.

```ascii
METRIC              GOOD FOR                BAD FOR
---------           --------                -------
Exact match         SQL, structured output  Any natural language
Fuzzy match         Keyword presence        Semantic meaning
BLEU / ROUGE        Fixed-form summaries    Open generation
Semantic similarity Paraphrase detection    Factual accuracy
Task completion     End-to-end success      Partial credit
LLM-as-judge        Open-ended quality      Speed, ground truth
```

<!-- SPEAKER: The chart is the deliverable. Work through each row. Ask: which of these is your team currently using? Is it the right one? -->

---

## L05: Choosing your primary metric

**Decision rule:**

1. If outputs have a known correct answer: use exact or fuzzy match
2. If outputs are evaluated by humans today: use LLM-as-judge calibrated against those humans
3. If the task has a binary success state (booked, resolved, classified): use task completion rate
4. If you are comparing two prompt versions: use pairwise

> **Key insight:** Most teams need exactly one primary metric and one guard metric. The primary drives decisions. The guard prevents regressions on a dimension you are not actively optimizing.

**Anti-pattern:** averaging five metrics into a single score. You lose all signal.

<!-- SPEAKER: The primary + guard structure is the practical takeaway. Force a choice. Averaging metrics is almost always hiding a tradeoff. -->

---
<!-- _class: section -->

## L06: LLM-as-Judge

### Build it, calibrate it, know when it lies

---

## L06: The problem

You need to evaluate open-ended text quality at scale. Human review is the ground truth but it does not scale to 1,000 examples per CI run. LLM-as-judge is the scalable proxy, but an uncalibrated judge is worse than no judge.

**The core setup:**

```python
def judge(question: str, answer: str, rubric: str) -> dict:
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=256,
        system=rubric,
        messages=[{
            "role": "user",
            "content": f"Question: {question}\nAnswer: {answer}\nScore 1-5 with reasoning."
        }]
    )
    return parse_score(response.content[0].text)
```

<!-- SPEAKER: The model choice matters. Use the strongest available judge. Claude Opus is the current default. The judge model should be stronger or different from the model being judged. -->

---

## L06: The LLM-as-judge calibration loop

<div class="mermaid">
flowchart LR
    A[Input + Output] --> B[Judge prompt\nwith rubric]
    B --> C[LLM judge]
    C --> D[Score 1-5\n+ reasoning]
    D --> E[Aggregate]
    E --> F[Compare to\nhuman labels]
    F --> G{Calibrated?}
    G -->|no| H[Adjust rubric]
    H --> B
    G -->|yes| I[Use in CI]
    style A fill:#1e1e1e,color:#e8e8e8,stroke:#4f46e5
    style I fill:#10b981,color:#fff
    style G fill:#1e1e1e,color:#e8e8e8,stroke:#f59e0b
    style H fill:#1e1e1e,color:#ef4444,stroke:#ef4444
</div>

**Calibration target:** Cohen's kappa > 0.6 against your human labels. Below that, your judge is unreliable.

<!-- SPEAKER: Most teams skip calibration. This is the most dangerous shortcut in eval work. An uncalibrated LLM judge can show you improving scores while quality is actually declining. -->

---

## L06: Failure modes and mitigations

| Failure mode | What happens | Fix |
|---|---|---|
| Position bias | Favors the first answer in a comparison | Randomize order, swap and average |
| Verbosity bias | Longer answers score higher regardless of quality | Add length-penalty clause to rubric |
| Self-preference | Model prefers its own outputs when judging | Use a different model family as judge |
| Rubric drift | Judge interprets 3/5 differently across runs | Lock rubric version, revalidate on new model releases |

> **Key insight:** A judge with known, measured failure modes is still useful. An uncalibrated judge with unknown biases is dangerous.

<!-- SPEAKER: Work through each failure mode with a concrete example. Position bias is the most common. Verbosity bias is the most insidious because it looks like quality improvement. -->

---
<!-- _class: section -->

## L07: Pairwise & Reference-Based Evals

### A vs B is a stronger signal than a score

---

## L07: The problem

Point scores (3.2 vs 3.4) are noisy. A 0.2 difference on a 1-5 scale may not be meaningful. Pairwise comparison (which is better, A or B?) has higher inter-rater agreement and directly answers the question you actually care about.

**When pairwise beats single-score:**
- Comparing two prompt versions for the same task
- Measuring regression after a model upgrade
- Evaluating style or tone changes that are hard to rubric-ize

```python
def pairwise(question: str, a: str, b: str) -> str:
    # Returns "A", "B", or "tie"
    result_1 = judge_pair(question, a, b)   # A first
    result_2 = judge_pair(question, b, a)   # B first (swapped)
    if result_1 == result_2:
        return result_1
    return "tie"  # Disagreement means position bias fired
```

<!-- SPEAKER: The swap-and-average is the key technique. If the judge picks A when A is first and B when B is first, that is pure position bias, not preference. -->

---

## L07: Reference-based evals

When you have a gold-standard answer, score against it directly.

```ascii
REFERENCE-FREE          REFERENCE-BASED
--------------          ---------------
Judge sees only         Judge sees question +
question + output       output + reference answer

Good for: style,        Good for: factual accuracy,
tone, coherence         completeness, hallucination
                        detection

Bias risk: HIGH         Bias risk: LOWER (anchored)
```

**Decision rule:** if you have a reference answer, use it. Reference-based evals are more reliable. Build the reference-free fallback only for tasks where no ground truth exists.

<!-- SPEAKER: Many teams do not realize they already have reference answers in their golden set. Always use them when available. -->

---
<!-- _class: section -->

## L08: Eval Harnesses

### From a loop in a script to a platform

---

## L08: The problem

You have a golden set and a scorer. Now you need to run them reliably, store results, and compare across runs. A hand-rolled loop breaks when the team grows. A platform adds too much ceremony before you have signal.

**Start raw, then migrate.**

```python
results = []
for example in golden_set:
    output = system.run(example["input"])
    score = scorer(example["input"], output, example["expected"])
    results.append({"id": example["id"], "score": score, "output": output})

avg = sum(r["score"] for r in results) / len(results)
print(f"Score: {avg:.3f} ({len(results)} examples)")
assert avg >= THRESHOLD, f"Quality regression: {avg:.3f} < {THRESHOLD}"
```

This is the full harness. Add concurrency and you are done for a single project.

<!-- SPEAKER: The assert at the end is the CI gate. This single line is what makes eval-driven development possible. Without it you have a report, not a gate. -->

---

## L08: Platform decision matrix

```ascii
PLATFORM        BEST FOR                    TRADEOFF
---------       --------                    --------
Raw loop        Getting started fast        No persistence, no UI
Braintrust      Prompt engineering teams    Cost, vendor lock-in
LangSmith       LangChain-heavy stacks      Coupled to LangChain
Phoenix         Open-source, Arize          Self-hosted ops burden
```

**Migration signal:** when you need to:
- Compare prompt versions side by side
- Share results with non-engineers
- Store eval history beyond a local JSON file

> **Key insight:** The raw loop teaches you what the platforms abstract. Build it first. Migrate when the raw loop becomes the bottleneck, not before.

<!-- SPEAKER: Platform adoption is a common premature optimization. The raw loop is production-grade for most teams up to 10-20 evals per day. -->

---
<!-- _class: section -->

## L09: CI for Prompts

### Regression on every change

---

## L09: The problem

Your prompt lives in a string. It is not compiled. It has no type checker. A one-word change can degrade quality by 15% and nothing in your pipeline will catch it unless you built a gate.

**The missing layer in most AI repos:**

```ascii
STANDARD REPO           AI REPO WITHOUT EVALS    AI REPO WITH EVALS
-------------           ---------------------    ------------------
Code change             Code change              Code change
Unit tests              (no tests for prompts)   Unit tests
Integration tests       Deploy                   Prompt eval step
Deploy                  Hope                     Gate: score >= baseline
                                                 Deploy
                                                 Monitor
```

<!-- SPEAKER: The comparison is pointed. AI repos skip the test layer for the most variable part of the system. This is the problem CI for prompts solves. -->

---

## L09: The GitHub Actions eval step

```yaml
- name: Run eval suite
  run: |
    uv run python evals/run.py \
      --golden-set evals/golden_set.json \
      --threshold 0.75 \
      --baseline evals/baseline.json \
      --output evals/results.json

- name: Check for regression
  run: |
    uv run python evals/check_regression.py \
      --results evals/results.json \
      --max-drop 0.05
```

**Threshold guard:** fail the PR if score drops more than 5% from baseline.

**Intentional regression process:** when you deliberately change behavior, update `baseline.json` in the same PR with a justification comment. Do not just raise the threshold.

<!-- SPEAKER: The intentional regression process is the discipline piece. It forces the team to acknowledge when they are accepting a quality tradeoff rather than hiding it. -->

---
<!-- _class: section -->

## L10: Evaluating RAG, Agents, Multi-Step Systems

### You cannot eval the whole thing with one score

---

## L10: The problem

RAG pipelines and agents fail in multiple places. A single end-to-end score hides which component is responsible. When your RAG score drops from 0.82 to 0.71, you need to know: is it retrieval quality, context relevance, or generation faithfulness?

**RAG Triad (RAGAS framework):**

| Metric | Measures | Question |
|--------|----------|----------|
| Faithfulness | Does the answer come from the context? | "Did the model hallucinate?" |
| Answer relevance | Does the answer address the question? | "Did the model answer what was asked?" |
| Context relevance | Does the retrieved context address the question? | "Did retrieval fetch the right chunks?" |

<!-- SPEAKER: The RAG Triad was formalized by the RAGAS team. It is the standard decomposition. The third component (context relevance) is where most teams find the real problem. -->

---

## L10: Agent trajectory evaluation

For agents, the final answer is not enough. You need to evaluate the path.

```python
def trajectory_eval(trace: list[dict], expected_tools: list[str]) -> dict:
    called = [s["tool"] for s in trace if s["type"] == "tool_call"]
    return {
        "tool_precision": len(set(called) & set(expected_tools)) / len(called),
        "tool_recall":    len(set(called) & set(expected_tools)) / len(expected_tools),
        "extra_calls":    [t for t in called if t not in expected_tools],
        "missed_calls":   [t for t in expected_tools if t not in called],
        "step_count":     len(trace),
    }
```

**Component vs end-to-end strategy:** run component evals first (they are cheap and fast). Run end-to-end evals before shipping.

<!-- SPEAKER: Trajectory eval catches the case where the agent gets the right answer by accident (called wrong tools, got lucky). You want to gate on correct behavior, not just correct output. -->

---
<!-- _class: section -->

## L11: Online Evals & Production Feedback Loops

### Evals do not stop at deployment

---

## L11: The problem

Offline evals tell you the system worked on your golden set at deploy time. Production is different: different users, different inputs, different context lengths, models updated under you. Offline evals go stale. Online evals do not.

<div class="mermaid">
flowchart LR
    A[Prod request] --> B[AI service]
    B --> C[Response to user]
    B --> D[Async sample\n5-10% traffic]
    D --> E[Eval queue]
    E --> F[LLM judge]
    F --> G[Score DB]
    G --> H[Dashboard]
    G --> I{Drift?}
    I -->|yes| J[Alert on-call]
    style A fill:#1e1e1e,color:#e8e8e8,stroke:#4f46e5
    style C fill:#10b981,color:#fff
    style J fill:#ef4444,color:#fff
    style I fill:#1e1e1e,color:#e8e8e8,stroke:#f59e0b
</div>

<!-- SPEAKER: The async path is critical. Never block the user response to run an eval. The eval queue decouples latency from quality measurement. -->

---

## L11: Feedback signal hierarchy

```ascii
SIGNAL TYPE         LATENCY    VOLUME    RELIABILITY
-----------         -------    ------    -----------
Explicit thumbs     Hours      Low (2%)  High
Copy / retry        Minutes    Medium    Medium
Escalation          Hours      Low       Very high
Session abandonment Minutes    Medium    Low
LLM-as-judge        Seconds    High      Medium
                    (async)
```

**Combining signals:** use explicit feedback to calibrate your LLM judge. Use the judge at volume. Use escalation as a precision-at-top signal (these are your worst failures).

> **Key insight:** 2% explicit feedback is enough to calibrate a judge that scores 100% of traffic. You do not need high explicit feedback volume.

<!-- SPEAKER: The 2% calibration insight is the key practical takeaway. Most teams undervalue the small amount of explicit signal they do have. -->

---
<!-- _class: section -->

## L12: Drift & Regression Detection

### Your score from last Tuesday is a baseline, not a guarantee

---

## L12: The problem

You shipped. Scores look good. Three weeks later scores are quietly declining. Model provider pushes an update. Data distribution shifts. Your prompt starts hitting edge cases from a new user segment. Without active monitoring, you find out from a customer complaint.

**The three drift types:**

| Type | Cause | Detection |
|------|-------|-----------|
| Model drift | Provider updates model weights or behavior | Score drop on fixed golden set |
| Data drift | User inputs shift outside training distribution | Input embedding distance from baseline |
| Prompt drift | Prompt interpretation changes with model update | LLM-judge disagreement vs locked reference run |

<!-- SPEAKER: Model drift is the sneakiest. Providers can update models with no announcement that causes measurable behavior change. Pinning model versions mitigates this but introduces its own ops burden. -->

---

## L12: ScoreHistory pattern

```python
class ScoreHistory:
    def __init__(self, window=100, threshold=0.05):
        self.scores = deque(maxlen=window)
        self.baseline = None
        self.threshold = threshold

    def add(self, score: float) -> bool:
        self.scores.append(score)
        avg = sum(self.scores) / len(self.scores)
        if self.baseline and (self.baseline - avg) > self.threshold:
            return True  # drift detected
        return False

    def set_baseline(self):
        self.baseline = sum(self.scores) / len(self.scores)
```

**Alert threshold guide:** 5% drop triggers investigation. 10% drop triggers incident response. Set these based on your product SLA, not arbitrarily.

<!-- SPEAKER: The rolling window prevents single-outlier alerts. The threshold is a starting point. Calibrate it based on your score variance in the first 2 weeks of production. -->

---
<!-- _class: section -->

## L13: A/B Testing LLM Features

### Statistical rigor for prompt changes

---

## L13: The problem

You have Prompt A (current) and Prompt B (candidate). Your LLM judge says B is slightly better on the golden set. That is not enough to ship. The golden set is 100 examples. Production is millions. You need to know if the improvement holds at scale with real users.

```python
class ABRouter:
    def __init__(self, variants: dict[str, float]):
        # variants: {"control": 0.5, "treatment": 0.5}
        self.variants = variants

    def assign(self, user_id: str) -> str:
        h = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        bucket = (h % 1000) / 1000.0
        cumulative = 0.0
        for variant, weight in self.variants.items():
            cumulative += weight
            if bucket < cumulative:
                return variant
        return list(self.variants.keys())[-1]
```

**Hash on user ID, not request ID.** Same user always gets same variant. Consistency prevents novelty effect.

<!-- SPEAKER: The hash-on-user-id pattern is the most commonly missed detail in LLM A/B tests. Request-level randomization causes within-user inconsistency that users notice and complain about. -->

---

## L13: A/B pitfalls and the decision template

```ascii
PITFALL              WHAT GOES WRONG           FIX
-------              ---------------           ---
Novelty effect       New variant scores        Run for 2+ weeks
                     high because it is new
Partial rollout      Treatment gets edge       Stratify by user segment
confounding          case users by accident
Underpowered test    Declare winner too early  Calculate min sample size
                     (n < 1000 per arm)        before starting
Metric mismatch      A/B metric differs from   Use same metric as CI gate
                     CI gate metric
```

**Decision template:** document expected effect size, minimum sample size, run duration, and primary metric before starting. Lock it. Do not change the rules mid-experiment.

> **Key insight:** Most LLM A/B tests are underpowered. A 5% improvement needs ~1,600 users per arm to detect at 80% power with a 5% false positive rate.

<!-- SPEAKER: The statistical power point lands hard in practice. Ask the room: how many of them have run an A/B test to completion without peeking at results early? -->

---
<!-- _class: section -->

## L14: Capstone: Eval-First Development of a Feature

### Ship something you can measure from day one

---

## L14: The capstone task

Build a new LLM feature from scratch using the eval-first process. Suggested: a customer-facing Q&A feature with a defined success bar.

**The 7-step eval-first process:**

| Step | Action | Output |
|------|--------|--------|
| 1 | Define success criteria | Written definition, primary metric |
| 2 | Build golden set | 100 labeled examples |
| 3 | Write evals | Scorer + harness |
| 4 | Build the feature | Initial implementation |
| 5 | Run evals, fix failures | Iterated implementation |
| 6 | Add to CI | Gated PR workflow |
| 7 | Ship + monitor | Online eval pipeline live |

**Gate:** do not proceed to step N+1 until step N is complete. The order is not optional.

<!-- SPEAKER: The gate rule is the discipline piece of the capstone. Most students want to skip to the build. Hold the line. The golden set before the build is what makes this eval-first, not eval-after. -->

---

## L14: The eval-first feedback loops

<div class="mermaid">
flowchart TD
    A[Step 1: Define success] --> B[Step 2: Golden set]
    B --> C[Step 3: Write evals]
    C --> D[Step 4: Build feature]
    D --> E[Step 5: Run evals]
    E --> F{Score meets bar?}
    F -->|no| G[Error analysis]
    G --> H{Root cause}
    H -->|prompt| D
    H -->|retrieval| D
    H -->|golden set wrong| B
    F -->|yes| I[Step 6: Add to CI]
    I --> J[Step 7: Ship]
    J --> K[Online evals]
    K --> L{Drift?}
    L -->|yes| G
    L -->|no| K
    style A fill:#4f46e5,color:#fff
    style J fill:#10b981,color:#fff
    style F fill:#1e1e1e,color:#e8e8e8,stroke:#f59e0b
    style L fill:#1e1e1e,color:#e8e8e8,stroke:#f59e0b
</div>

<!-- SPEAKER: Note the loop back from error analysis to golden set. If your evals are failing because the golden set is wrong, fix the golden set first. Fixing the feature against a wrong golden set is worse than having no evals. -->

---
<!-- _class: section -->

## Discussion Prompts

### For facilitators and study groups

---

## Discussion: 5 questions for your team

> **Facilitator prompt:** Pick 2-3 of these. Give 5 minutes of silent thinking before opening discussion.

1. What is the last LLM feature you shipped? How did you decide it was ready? What would it have taken to know that more rigorously?

2. If you had to build a golden set for your current system today, what are the 5 most important failure modes you would want it to cover?

3. Your LLM judge disagrees with your human reviewers 30% of the time. Is that acceptable? What would you do to close that gap?

4. A PM wants to know if the new prompt is better. You have 500 users. How do you run the experiment and when do you call it?

5. You have no evals. A model provider announces a major model update next week. What is your minimum viable eval process before you upgrade?

<!-- SPEAKER: Question 5 is the most practical entry point. It forces a minimum viable process without requiring the full eval stack. Use it as the starting point if the team is resistant. -->

---
<!-- _class: section -->

## Exercises

### Put it into practice

---

## Exercises: three levels

**Easy (1-2 hours): manual error analysis**
Take 50 outputs from a system you work with. Read them. Classify each failure using the 7-category taxonomy. Write a one-paragraph annotation schema. Do not write any code.

**Medium (4-6 hours): build and calibrate a judge**
Build an LLM-as-judge scorer for a task you care about. Label 30 examples yourself. Run the judge on the same 30. Calculate Cohen's kappa. Adjust the rubric until kappa > 0.6. Document what changed and why.

**Hard (full capstone, 8-12 hours): eval-first feature**
Pick any feature from your current project. Follow the 7-step eval-first process exactly. Ship with a CI gate and online eval pipeline live. Write a one-page retrospective: what did the evals catch that eyeballing would have missed?

> **Key insight:** The medium exercise is the highest leverage single thing in this phase. Cohen's kappa below 0.5 is a common discovery and it changes how the team thinks about automated scoring.

<!-- SPEAKER: The retrospective in the hard exercise is not optional. The insight of what evals caught that vibes would have missed is what creates the habit. Without it the exercise is just mechanical. -->

---
<!-- _class: section -->

## Further Reading

### Curated, not exhaustive

---

## Further reading: 5 items

**Foundational:**
1. **Hamel Husain, "Your AI Product Needs Evals"** (hamel.ai): The essay that defines the manual-review-first discipline. Read before L02.

2. **RAGAS documentation** (docs.ragas.io): The RAG Triad formalization with implementation. Required context for L10.

**Practical:**
3. **Braintrust "Eval-Driven Development" guide** (braintrust.dev/docs): How the platforms think about the loop. Read after L08.

4. **Anthropic "Building Effective Prompts" cookbook**: Prompt iteration under eval feedback. Directly applicable to the CI gate in L09.

**Deep cut:**
5. **"Chatbot Arena: An Open Platform for Evaluating LLMs by Human Preference"** (LMSYS, 2023): The academic foundation for pairwise evals. Informs L07 and the statistics in L13.

<!-- SPEAKER: Item 1 is mandatory. It is short, practical, and changes how engineers think about the job. Assign it as pre-reading if possible. -->

---
<!-- _class: section -->

## What's Next

### Phase 06: Shipping

---

## P06: Shipping: what you are walking into

You have a feature that evals say works. Now you need to deploy it reliably.

| P06 Lesson | What it adds to your eval foundation |
|------------|--------------------------------------|
| Versioning and rollback | Tie model versions to your eval baseline |
| Canary deployments | Gradual rollout with eval gates at each stage |
| Latency and cost budgets | Add latency and cost to your eval harness |
| Feature flags | The mechanism behind your A/B router |
| Incident response | When online evals fire, what do you do next |

> The eval stack you built in P05 is not just a quality tool. It is the nervous system of your deployment pipeline. P06 shows you how to wire it in.

**Phase 06: Shipping** starts where the eval loop ends.

<!-- SPEAKER: Close by connecting the two phases explicitly. The eval work is not standalone. It gates every deploy decision in P06. This is the payoff for the 15 hours in P05. -->

---

## Quick reference: the eval stack

```ascii
LAYER               ARTIFACT              LESSON
-----               --------              ------
Failure taxonomy    annotation-schema.json  L02, L03
Golden set          golden_set.json         L04
Scorer              judge.py                L06
Harness             run_evals.py            L08
CI gate             .github/workflows/      L09
  eval.yml
RAG/agent eval      rag_triad.py,           L10
                    trajectory_eval.py
Online eval         eval_pipeline.py        L11
Drift detection     score_history.py        L12
A/B router          ab_router.py            L13
```

Everything here is reusable. Drop the harness and golden set into any new project and you have evals from day one.

<!-- SPEAKER: End on the artifact inventory. This is what the audience leaves with. Make it concrete: these are files they can copy. -->

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
