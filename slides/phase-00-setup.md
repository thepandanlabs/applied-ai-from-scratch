---
marp: true
theme: applied-ai
class: title
paginate: true
footer: 'Applied AI From Scratch · Phase 00: Setup & the Applied AI Mindset'
---

# Phase 00: Setup & the Applied AI Mindset

**10 lessons. ~8 hours.**
Get your environment right. Make the one mental shift that separates engineers who ship AI systems from engineers who fight them.

<!-- SPEAKER: Welcome and framing. This phase is deceptively important. Most engineers underestimate it because "setup" sounds boring. The probabilistic mindset shift is the real payload. Time: ~5 min -->

---

## Who This Phase Is For

**Target:** Working software engineers moving into AI feature development
**Not required:** ML background, math, prior model experience

**What you need walking in:**
- Python installed (any version; we will fix it)
- An Anthropic API key (or ability to get one)
- Willingness to unlearn one habit from traditional software

**What you walk out with:**
- A working, reproducible dev environment
- The probabilistic mindset that prevents the most common AI production failures

<!-- SPEAKER: Explicitly name the target audience. Developers who know Python but may never have called an LLM API. The unlearning point is important to flag early. Time: ~3 min -->

---

## What You Build in Phase 00

```
Dev Environment     API Keys + Model Landscape
(uv + Node)         (providers, tiers, keys safe)
       |                      |
       v                      v
  First API Call        Probabilistic Mindset
  (Python + TS)         (the core shift)
       |                      |
       v                      v
  Model Docs            Cost + Latency
  (read the spec)       (measure from day one)
       |                      |
       v                      v
  Git Workflow          Docker Basics
  (prompts are code)    (portable AI apps)
       |                      |
       v                      v
  Notebook vs Script vs Service
       |
       v
  Debugging Non-Deterministic Systems
```

<!-- SPEAKER: Show the full arc. Each lesson feeds the next. The capstone (L10) only makes sense after L04 installs the mindset. Time: ~3 min -->

---

## The Through-Line

**The problem most engineers bring to AI work:**

They treat a probabilistic sampler like a deterministic function.

```
What they expect:          What actually happens:
f("input A") = "X"         f("input A") = "X"  (60% of the time)
f("input A") = "X"         f("input A") = "Y"  (25% of the time)
f("input A") = "X"         f("input A") = "Z"  (10% of the time)
```

**This phase installs the correct mental model** so every other phase builds on solid ground.

The environment lessons (L01, L03, L07, L08) remove friction. The mindset lessons (L04, L10) remove the failure mode that cannot be debugged away.

<!-- SPEAKER: This is the thesis of the entire phase. Return to it at L04. Deterministic thinking is not a beginner mistake; senior engineers make it too when first encountering LLMs. Time: ~4 min -->

---
<!-- _class: section -->

# L01: Dev Environment
## uv, Node, TypeScript

---

## L01: The Old Stack vs. the New Stack

**The old Python stack: 4 tools with no coordination**

```
pyenv        venv         pip          pip-tools
(version)    (isolation)  (install)    (lockfiles)
    |             |            |             |
.python-version  .venv/   requirements.txt  requirements.lock
                          (no pins = drift)  (optional, manual)
```

**The new stack: 1 tool, full coordination**

```
+------------------------------------------------------+
|                        uv                            |
|  version mgmt + isolation + install + lockfile       |
+------------------------------------------------------+
    |             |            |             |
.python-version  .venv/   pyproject.toml    uv.lock
                          (deps + metadata) (auto-generated)
```

uv is written in Rust. Installs are 10-100x faster than pip. The lockfile is automatic, not optional.

<!-- SPEAKER: uv replaces pyenv + venv + pip + pip-tools with one tool. The key sell: reproducibility is the default, not an afterthought. Time: ~5 min -->

---

## L01: Two Commands to Know

**Start any AI project:**

```bash
# Install uv (one time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create a project
uv init ai-scratch
cd ai-scratch

# Add the Anthropic SDK
uv add anthropic
# Creates .venv/, updates pyproject.toml, writes uv.lock atomically

# Run your script (never need to activate the venv)
uv run python main.py
```

**The key insight:** `uv run` injects the correct environment automatically. No `source .venv/bin/activate`. No "wrong venv" bugs when switching between projects.

**Exit condition for this lesson:** All six checks in the Evaluate section pass. Token counts print. No ImportError.

<!-- SPEAKER: Emphasize uv run vs. activate. Hands-on: have the room run uv init and uv add anthropic before moving on. Time: ~8 min -->

---
<!-- _class: section -->

# L02: API Keys and the Model Landscape
## Safe key loading. Deliberate model selection.

---

## L02: The Three-Layer Key Pattern

```
WRONG:
  client = Anthropic(api_key="sk-ant-api03-abc123...")
  # This is now in git history forever.

CORRECT (3-layer pattern):
  .env file          -->  ANTHROPIC_API_KEY=sk-ant-...  (in .gitignore)
       |
  os.environ         -->  loaded by python-dotenv at startup
       |
  client             -->  Anthropic()  (SDK reads from env automatically)
```

```bash
# Setup (one time per machine)
echo "ANTHROPIC_API_KEY=your-key-here" > .env
echo ".env" >> .gitignore
uv add python-dotenv
```

```python
from dotenv import load_dotenv
import anthropic

load_dotenv()           # reads .env into os.environ
client = anthropic.Anthropic()  # no api_key= needed
```

<!-- SPEAKER: The key leak via git history is real. GitHub scans for leaked keys within minutes of a push. Revocation and rotation is painful. The .env pattern costs 3 lines of code and eliminates the risk. Time: ~5 min -->

---

## L02: The 2026 Model Tier Matrix

```
FAST / CHEAP          BALANCED            POWERFUL / EXPENSIVE
(extraction,          (most production    (complex reasoning,
 classification)      workloads)           long synthesis)

Claude Haiku 3.5      Claude Sonnet 4     Claude Opus 4
~$0.80/1M in          ~$3/1M in           ~$15/1M in
~$4/1M out            ~$15/1M out         ~$75/1M out

GPT-4o mini           GPT-4o              o3
~$0.15/1M in          ~$2.50/1M in        ~$10/1M in

Gemini Flash 2.0      Gemini Pro 2.0      Gemini Ultra 2.0
~$0.10/1M in          ~$1.25/1M in        ~$5/1M in
1M context window     2M context window
```

**The decision heuristic:** Start with fast/cheap. Test it. Only upgrade if quality fails.

Most production AI features (classification, extraction, summarization, routing) run fine on Haiku or Flash.

<!-- SPEAKER: Prices shift frequently; treat as order-of-magnitude references. The point is the habit: make a deliberate tier choice, don't default to the most expensive model you know works. Time: ~6 min -->

---

## L02: Cost-Aware Model Selection

```python
@dataclass
class ModelConfig:
    provider: str
    model_id: str
    tier: str                   # "fast", "balanced", "powerful"
    input_cost_per_1m: float
    output_cost_per_1m: float
    context_window: int

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            (input_tokens  / 1_000_000) * self.input_cost_per_1m +
            (output_tokens / 1_000_000) * self.output_cost_per_1m
        )
```

**Exercise:** 500 users/day, 1,000 input tokens + 300 output tokens per request.
- Haiku monthly: `0.001 * 30 * 500 * haiku.estimate_cost(1000, 300)`
- Sonnet monthly: same formula, 20x higher

**Make the cost decision before writing the feature.**

<!-- SPEAKER: The ModelConfig pattern is the habit we want. Encode the cost into the selection decision, not as an afterthought. The exercise works out to roughly $18/month vs $360/month for this traffic pattern. Time: ~5 min -->

---
<!-- _class: section -->

# L03: First API Call
## Request anatomy. Streaming. Tokens.

---

## L03: The Response Object

```python
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    messages=[{"role": "user", "content": "Explain a context window."}],
)

# Every field matters in production:
print(response.id)                    # "msg_01XYZ..."
print(response.model)                 # actual model used
print(response.stop_reason)           # "end_turn" or "max_tokens"
print(response.usage.input_tokens)    # tokens you sent
print(response.usage.output_tokens)   # tokens the model generated
print(response.content[0].text)       # the response text
```

**The field that trips up engineers:**

```python
if response.stop_reason == "max_tokens":
    # Response is TRUNCATED. The sentence ended mid-word.
    # Increase max_tokens or shorten the prompt.
    raise RuntimeError("Response truncated")
```

Always check `stop_reason`. "max_tokens" is a silent truncation, not an error.

<!-- SPEAKER: The stop_reason check is the first production habit to install. Most engineers look only at content[0].text and never check if the response was cut off. Time: ~6 min -->

---

## L03: Streaming vs. Non-Streaming

```
NON-STREAMING: blocks until complete
  Client --> POST /v1/messages --> API generates full response --> 200 OK + text
  (4-8 seconds of silence, then all text at once)

STREAMING: tokens arrive as generated
  Client --> POST /v1/messages
        <-- message_start
        <-- content_block_delta (token)
        <-- content_block_delta (token)   (continues...)
        <-- message_delta (stop_reason + usage)
        <-- message_stop
```

```python
# The production streaming pattern
with client.messages.stream(model="...", max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]) as stream:
    for chunk in stream.text_stream:
        print(chunk, end="", flush=True)
        # In a web server: yield chunk to the HTTP response here

final = stream.get_final_message()
print(f"\n{final.usage.input_tokens} in / {final.usage.output_tokens} out")
```

**Print token counts on every call from day one.**

<!-- SPEAKER: The streaming benefit is both UX (user sees response start immediately) and server efficiency (no thread blocking). The habit of printing token counts is the entry point to cost awareness. Time: ~6 min -->

---

## L03: Token Counting

```python
# Count tokens BEFORE sending (to check context window limits)
count = client.messages.count_tokens(
    model="claude-3-5-haiku-20241022",
    messages=[{"role": "user", "content": your_large_document}],
)
print(f"This request will use {count.input_tokens} tokens")

# After the call, actual counts from the response are ground truth
print(f"Actual: {response.usage.input_tokens} in / "
      f"{response.usage.output_tokens} out")
```

**Rule:** Log token counts from the first API call. Not "when you have a cost problem." From call one. The log is how you see the cost problem coming before it arrives.

<!-- SPEAKER: Practical tip: build a simple wrapper that always logs tokens. The CostTracker in L06 formalizes this. Time: ~4 min -->

---
<!-- _class: section -->

# L04: The Probabilistic Mindset
## The most important lesson in Phase 00

---

## L04: The Mental Model Mismatch

**What software engineers expect from code:**

```
Input A --> function --> Output X  (always)
Input A --> function --> Output X  (always)
Input A --> function --> Output X  (always)
```

**What an LLM actually is:**

```
Input A --> model --> Output X  (60% of the time)
Input A --> model --> Output Y  (25% of the time)
Input A --> model --> Output Z  (10% of the time)
Input A --> model --> Output W  ( 5% of the time)
```

The model is not broken. It is a **sampler**, not a **function**. Every call draws one sample from a probability distribution over all possible responses.

The distribution is shaped by: model weights, temperature, and the prompt.

<!-- SPEAKER: This is the unlearning moment. The engineers in the room have 5-20 years of experience with deterministic systems. This is the single most important reframe in the entire course. Spend time here. Time: ~8 min -->

---

## L04: The 5 Failure Modes of Deterministic Thinking

| Assumption | How It Breaks |
|---|---|
| Unit test one output, ship if it passes | 1 sample tells you nothing about the 8% failure rate |
| Exact string matching in assertions | "POSITIVE" vs "Positive" vs "positive." - all correct, all fail |
| Assume idempotency (run twice = same result) | Running the same pipeline twice produces different outputs |
| Trust a 10-sample eval to measure quality | 9/10 on your eval can mean 73% in production at scale |
| Build brittle if/else on model output | `if response == "yes"` breaks on "Yes", "YES", "Yes, I agree" |

**The unlearning required:** `if response == expected_answer` is the wrong test. You need evals that measure pass rate over many samples.

<!-- SPEAKER: Go through each row. Ask the room: "Which of these have you already done or seen done?" Almost every hand will go up. That's the point. This is not theory; it's what teams discover the hard way. Time: ~8 min -->

---

## L04: Temperature is a Variance Dial, Not a Magic Number

```python
# Temperature 0.0: minimize variance (extraction, classification)
client.messages.create(..., temperature=0.0)
# Same input --> same output on nearly every run

# Temperature 0.3-0.5: moderate variance (summarization, explanation)
client.messages.create(..., temperature=0.3)
# Some run-to-run variation; acceptable for non-structured output

# Temperature 0.9-1.0: high variance (brainstorming, creative writing)
client.messages.create(..., temperature=1.0)
# Wide spread; intentionally diverse outputs
```

**The critical caveat:** Temperature=0 does not mean deterministic. It means minimal variance. Floating-point non-determinism on GPU hardware means you can still observe occasional variation.

**Task-appropriate temperature is an engineering decision, not a style preference.**

<!-- SPEAKER: A common mistake is setting temperature=0 everywhere "for consistency" or temperature=1 everywhere "to be creative." The right temperature is determined by the task type. Time: ~5 min -->

---

## L04: Measuring the Distribution

```python
def run_n_times(prompt: str, n: int = 10,
                temperature: float = 1.0) -> list[str]:
    results = []
    for i in range(n):
        r = client.messages.create(
            model="claude-3-5-haiku-20241022", max_tokens=32,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        results.append(r.content[0].text.strip())
    return results

# Run the same classification prompt 20 times
results = run_n_times(
    "Is 'The meeting was fine' POSITIVE, NEGATIVE, or NEUTRAL? One word.",
    n=20
)
from collections import Counter
print(Counter(results))
# {"Neutral": 12, "neutral": 4, "NEUTRAL": 2, "Positive": 2}
# This is your distribution. Not a single answer.
```

**Key exercise:** Run this. Observe the variance. Internalize that the counter is the correct mental model.

<!-- SPEAKER: This is a hands-on demo exercise. If there's a live coding session, run this now. The Counter output makes the distribution concrete and visceral in a way that slides cannot. Time: ~8 min -->

---
<!-- _class: section -->

# L05: Reading Model Docs
## The spec sheet is not optional

---

## L05: The Five Fields That Determine Production Feasibility

```
MODEL CARD: claude-3-5-haiku-20241022
+------------------------------------------------------------------+
| CONTEXT WINDOW          200,000 tokens  <-- max INPUT you send   |
|   (system prompt + messages + documents + conversation history)  |
|                                                                  |
| MAX OUTPUT TOKENS         8,192 tokens  <-- max RESPONSE size    |
|   (hard cap on what the model writes back)                       |
|                                                                  |
| PRICING                                                          |
|   Input:  $0.80 / 1M tokens                                      |
|   Output: $4.00 / 1M tokens                                      |
|   Cache read: $0.08 / 1M tokens  (10x cheaper for repeats)       |
|                                                                  |
| RATE LIMITS: 50 RPM / 50K TPM / 1K RPDAY                        |
|                                                                  |
| DEPRECATION DATE: 2025-12-01  <-- plan your migration now        |
+------------------------------------------------------------------+
```

**The most common engineer mistake:** Confusing context window (200K) with max output (8K). You cannot get a 50K-token summary even with a 200K context window.

<!-- SPEAKER: The context window vs. max output distinction causes real production failures. Engineers assume "200K context = 200K in, 200K out." Not true. Input + output together fit in the window, and output is separately capped. Time: ~6 min -->

---

## L05: Red Flags When Reading Model Docs

**Before committing a model to a feature:**

```
Five questions to answer in under 60 seconds:

1. Context window (tokens)?           200K, 128K, 32K?
2. Max output tokens?                 8K, 64K, 128K?
3. Cost at your typical prompt size?  $X per 1,000 requests
4. RPM limit on your tier?            50? 500? Unlimited?
5. Deprecation date in next 12 months? Plan migration if yes.
```

**Rate limit dimensions:**

| Limit | What it caps | When it bites you |
|---|---|---|
| RPM | Requests per minute | High-concurrency, burst traffic |
| TPM | Tokens per minute | Long-document pipelines |
| RPDAY | Requests per 24 hours | Low-tier keys, hobby plans |

In production, **TPM is usually the binding constraint** for AI apps. One 190K-token document uses 190K of your TPM budget in a single call.

<!-- SPEAKER: The 2 a.m. 429 error story from the lesson is real. Engineers get paged because they never read the rate limit section of the docs. Time: ~5 min -->

---
<!-- _class: section -->

# L06: Cost and Latency from Line One
## If you cannot measure it, you cannot afford to ship it

---

## L06: The Output Token Asymmetry

```
                INPUT TOKENS            OUTPUT TOKENS
Cost:           $0.80 / 1M              $4.00 / 1M
Processing:     parallel                sequential (one at a time)
Control:        you write the prompt    you cap with max_tokens
Ratio:          5x cheaper              5x more expensive
```

**The filler text problem:**

```
Every response that starts with "Sure! I'd be happy to help with that."
= ~12 output tokens = $0.000048 per call

At 100,000 calls/month = $4.80/month wasted on one greeting.
Multiplied across 10 prompt templates = ~$48/month of filler.

Fix: "Respond with the answer only. No introduction."
```

**Output tokens are expensive.** Instruct the model to skip preamble from day one.

<!-- SPEAKER: The filler text example from the lesson is concrete and memorable. Teams regularly discover this pattern after 3-4 weeks in production when the bill arrives. Time: ~5 min -->

---

## L06: The Cost Math

**Example: 500 users/day, 1,000 input + 300 output tokens per request**

| Model | Cost/request | Monthly cost |
|---|---|---|
| Claude Haiku | $0.0000020 | ~$9/month |
| Claude Sonnet | $0.0000075 | ~$34/month |
| Claude Opus | $0.0000375 | ~$169/month |
| GPT-4o mini | $0.0000003 | ~$1.35/month |
| GPT-4o | $0.000005 | ~$23/month |

**The habit, starting from line one:**

```python
# After every API call, log this:
print(f"in={response.usage.input_tokens} "
      f"out={response.usage.output_tokens} "
      f"cost=${response.usage.input_tokens * 0.80/1e6 + response.usage.output_tokens * 4.00/1e6:.6f}")
```

Print it. Every call. Build the cost intuition before you need it.

<!-- SPEAKER: The table makes the tier differences concrete. The key message: the habit of logging token counts costs 2 lines of code and prevents the "how did we spend $3,400 this month" conversation. Time: ~6 min -->

---

## L06: Latency: What You Control vs. What You Cannot

```
Your Code                Anthropic API
    |                          |
    |---[1. Network: ~30ms]--->|
    |                          |--[2. Queue: 0-2000ms]
    |                          |--[3. TTFT: 200-800ms]
    |<--[first token]----------|
    |                          |--[4. Generation: ~50ms/100 tokens]
    |<--[last token]-----------|
    |
Wall-clock latency = 1 + 2 + 3 + 4

You control: request size, output length, model choice, streaming, your code
You cannot control: network latency, queue time, TTFT
```

**Time-to-first-token (TTFT)** is the user-perceived latency for streaming. Streaming does not reduce total generation time; it reduces the time before the user sees any output.

Users abandon chatbots after ~3 seconds. TTFT is the metric that matters for UX.

<!-- SPEAKER: The latency breakdown demystifies "why is it slow?" You can only optimize what you control. Streaming is the primary tool for improving perceived UX without changing total time. Time: ~5 min -->

---
<!-- _class: section -->

# L07: Git Workflow for AI Projects
## Prompts are code. If you cannot diff them, you cannot debug them.

---

## L07: What Belongs in Git and What Does Not

```
AI PROJECT DIRECTORY
+-----------------------+-----------------------------+
|     GIT TRACKS        |    .gitignore EXCLUDES      |
+-----------------------+-----------------------------+
| code/main.py          | .env   (API keys)           |
| prompts/              | .venv/ (uv env)             |
| evals/                | __pycache__/                |
| checks.json           | outputs/raw_responses/      |
| Dockerfile            |   (may contain PII)         |
| README.md             | model_weights/  (too large) |
| .gitignore            | *.log                       |
+-----------------------+-----------------------------+

RULE: If it contains secrets OR auto-regenerates OR is >50MB: exclude.
RULE: If you need it to reproduce a past result: track it.
```

**AI-specific commit message convention:**

```bash
# Unhelpful: "update prompt"
# Helpful: "prompt: add chain-of-thought instruction, score 6->8 on eval"
# Helpful: "config: increase max_tokens 512->1024 for long summaries"
# Helpful: "revert: undo L04 prompt change - dropped score from 8 to 5"
```

<!-- SPEAKER: The regression story from the lesson lands well: "I just tweaked the prompt." No diff. No baseline. No rollback. Prompts are logic. Prompt changes are deployments. Time: ~5 min -->

---

## L07: The Prompt Versioning Workflow

```bash
# 1. Review what changed before committing
git diff HEAD -- code/main.py

# 2. Commit with behavioral intent in the message
git add code/main.py
git commit -m "prompt: narrow response to 2 sentences to cut output tokens"

# 3. Tag working versions before experimenting
git tag -a v1.0-production -m "Eval score: 9/10. Deployed $(date +%Y-%m-%d)"

# 4. Find the regression commit
git log --oneline --since="2 weeks ago"
git checkout <hash> && python code/main.py "eval question" && git checkout main

# 5. Roll back cleanly
git revert <hash>
```

**The moment to tag:** Any time eval score passes a threshold you want to preserve. The tag lets you `git show v1.0-production` six months later and see the exact prompt state.

<!-- SPEAKER: The git tag pattern for prompts is underused. Most teams rely on commit hashes, but tags give you named, human-readable checkpoints like "v1.0-production" that survive team changes. Time: ~5 min -->

---
<!-- _class: section -->

# L08: Docker Basics for AI Apps
## If it runs in a container, it runs everywhere

---

## L08: Why Docker for AI Work

**The "works on my machine" failure mode for AI apps:**

- Different Python version on their machine
- Different `anthropic` SDK version installed
- API key you set as an env var never made it to theirs
- System library required by a GPU-accelerated package not installed

Docker solves this: package code, exact dependencies, and runtime configuration into one portable unit.

```
Host vs. Container: the critical separation

HOST: ~/projects/app/
  code/main.py          --COPY at build time-->  /app/main.py (in container)
  Dockerfile
  ANTHROPIC_API_KEY     --docker run -e-------->  env var (injected at run time)
  (in shell env)

CONTAINER: isolated filesystem + process
  /app/main.py    (your code)
  python 3.12     (exact version)
  anthropic 0.40  (exact SDK)
  ENV: ANTHROPIC_API_KEY  (injected, never baked in)
```

**The key security rule:** The API key never enters the image. It flows at runtime.

<!-- SPEAKER: The security point is important: docker history --no-trunc reveals every layer. Keys baked into any layer are exposed even if later deleted. The -e flag keeps the key outside the image entirely. Time: ~5 min -->

---

## L08: The Minimal Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Layer order matters: copy requirements BEFORE code.
# If main.py changes but requirements.txt does not,
# Docker reuses the cached pip install layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

CMD ["python", "main.py"]
```

```bash
# Build
docker build -t ai-summarizer .

# Run (key injected at runtime, never baked in)
docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY ai-summarizer

# Debug a running or exited container
docker logs $(docker ps -lq)
docker run -it --entrypoint /bin/bash ai-summarizer
```

**Why `-slim`:** Strips dev headers and test suites. Smaller image, faster push/pull, smaller attack surface. Use full `python:3.12` only if a dependency needs C compilation.

<!-- SPEAKER: The layer caching explanation is the moment most developers have a genuine "ah" moment. Requirements before code is counterintuitive until you see cache CACHED vs. cache MISS in build output. Time: ~6 min -->

---
<!-- _class: section -->

# L09: Notebook vs. Script vs. Service
## The format you use to build determines how hard it is to ship

---

## L09: The Three Formats

```
FORMAT      PRIMARY USE                EXPIRES WHEN...
---------   -------------------------  --------------------------------
Notebook    Exploration, demos,        You need to run it on a schedule,
            stakeholder review         share it as an API, or run it
                                       more than once without Jupyter

Script      Repeatable pipeline,       More than one user needs to call
            scheduled jobs, CLI        it simultaneously, or it needs to
                                       stay alive between requests

Service     Persistent endpoint,       Never expires. This is the final
            multi-user, production     form for production AI features.
```

**The notebook trap:** A notebook stays useful until it expires. The expiration is invisible. The team that spends two weeks building a great notebook demo and then four weeks "migrating it to production" hit the trap.

**Trigger condition to promote:**
- Notebook to Script: "I need to run this again without Jupyter"
- Script to Service: "Multiple users need to call this simultaneously"

<!-- SPEAKER: The VP of Engineering story from the lesson is a real anti-pattern. "Can we put this in the product?" followed by four more weeks of work because nobody promoted the format at the right time. Time: ~6 min -->

---

## L09: What Changes at Each Promotion

```
Notebook           Script                 Service
   |                  |                      |
   |-- Remove cells   |-- Add HTTP interface |
   |-- Add main()     |-- Add async handling |
   |-- Add errors     |-- Add concurrency    |
   |-- Add env vars   |-- Add health check   |
   |-- Add config     |-- Add logging        |
                      |-- Add Docker         |
```

```python
# Script version: repeatable, testable, pipeable
def summarize(text: str) -> str: ...
def main():
    text = sys.stdin.read().strip()
    print(summarize(text))
if __name__ == "__main__": main()

# Service version: always-on, multi-user, observable
@app.post("/summarize")
async def summarize(req: SummarizeRequest) -> SummarizeResponse: ...

@app.get("/health")
async def health(): return {"status": "ok"}
```

The health endpoint is the signal load balancers, CI pipelines, and on-call tools understand. Scripts do not have one.

<!-- SPEAKER: The health check endpoint as a first-class concern is a concrete production readiness marker. If your AI feature cannot answer "are you healthy?" in milliseconds, it is not production-ready. Time: ~5 min -->

---

## L09: The Graduation Decision

```
Start: What are you actually building?
          |
          v
Exploration, one-off analysis, or stakeholder demo?
    YES --> Notebook
            Trigger: "I need to run this again" or "share as API"
    NO  -->
          |
          v
Single user, on demand, scheduled, or from command line?
    YES --> Script
            Trigger: "Multiple users" or "always available"
    NO  -->
          |
          v
Multiple users, persistent availability, system integration?
    YES --> Service (FastAPI + Docker)
```

**The rule of thumb:** If there is any chance you will run it more than twice, write a script. If there is any chance a second user will call it, write a service.

The notebook is not a destination. It is a staging area.

<!-- SPEAKER: The decision tree is practical and memorable. Ask the room: "Think of an AI project you've seen stay in notebook form too long. What was the cost?" Time: ~4 min -->

---
<!-- _class: section -->

# L10: Debugging Non-Deterministic Systems
## You cannot fix what you cannot measure

---

## L10: How AI Debugging Differs

```
DETERMINISTIC (traditional)        PROBABILISTIC (AI systems)
---------------------------        ---------------------------
Same input = same output           Same input = different output
Bug: wrong output for input X      Bug: wrong output at N% rate
Reproduce: re-run with args        Reproduce: temp=0 + logged prompt
Debug: read the stack trace        Debug: classify failures across runs
Fix: change the code               Fix: prompt, temp, model, or retry
Verify: test passes                Verify: failure RATE drops below threshold
```

**The three questions to ask when an AI feature misbehaves:**

1. Is it the **prompt**? (the most common cause)
2. Is it the **temperature**? (set it to 0, does it reproduce?)
3. Is it the **model**? (try a different tier)

You cannot answer any of these questions without a log of what was sent and received.

<!-- SPEAKER: Return to the through-line from slide 4. The probabilistic mindset from L04 is the prerequisite for L10. Without that mental model, engineers keep trying to find "the bug" instead of measuring the failure rate. Time: ~6 min -->

---

## L10: The Debug Logger

```python
@dataclass
class CallRecord:
    timestamp: str
    model: str
    prompt: str
    response: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: Optional[str] = None

class DebugLogger:
    def call(self, prompt: str, temperature: float = 1.0) -> str:
        start = time.monotonic()
        response = self.client.messages.create(...)
        record = CallRecord(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            prompt=prompt,
            response=response.content[0].text,
            latency_ms=int((time.monotonic() - start) * 1000),
            ...
        )
        # Append to JSONL: one record per line, queryable
        with open(self.log_path, "a") as f:
            f.write(json.dumps(asdict(record)) + "\n")
        return response.content[0].text
```

**Log format: JSONL.** One record per line. Easy to stream, easy to grep, easy to load in Python.

<!-- SPEAKER: The DebugLogger is the practical artifact. The insight is the logging format: JSONL is the right choice for append-only, per-call logs that need to be both streamable and queryable. Time: ~5 min -->

---

## L10: The AI Debug Loop

```
System produces wrong output
          |
          v
Check the log: Did you capture it?
    NO LOG --> You are debugging blind. Add logging first.
    LOG EXISTS -->
          |
          v
Retrieve the exact prompt + response from the log
          |
          v
Reproduce with temperature=0
          |
    Same failure? --> YES: classify failure type (prompt / model / integration)
                     NO:  intermittent failure, measure rate across N runs
          |
          v
Measure failure rate across similar inputs
          |
          v
Fix: prompt, model, retry logic, or input filter
          |
          v
Verify: failure RATE drops below your threshold
```

**Classify before you fix.** Integration failures (rate limits, timeouts, auth) are fixed in infrastructure. Model failures (refusals, wrong format) are fixed in the prompt.

<!-- SPEAKER: The classification step is critical and often skipped. Engineers jump to a fix without understanding whether it is a model problem or an infrastructure problem. Time: ~5 min -->

---

## L10: Systematic Approach in Practice

```python
records = load_log("ai_calls.jsonl")

# 1. Measure failure rate
failures = [r for r in records if r.get("error")]
rate = len(failures) / len(records)
print(f"Failure rate: {rate:.1%}")  # If >5%: investigate before shipping

# 2. Reproduce a specific failure at temperature=0
failed = failures[0]
response = logger.call(failed["prompt"], temperature=0.0)
# If same failure: model or prompt issue
# If passes: intermittent, measure rate

# 3. Classify failure type
for r in failures:
    if "rate_limit" in (r.get("error") or ""):
        print("INTEGRATION: rate limit - add backoff/retry")
    elif len(r["response"]) < 10:
        print("MODEL: suspiciously short - check max_tokens")
    elif "I cannot" in r["response"]:
        print("MODEL: refusal - revise prompt")
```

**Failing tests are expected. Write them anyway.** A test that measures failure rate, even if the rate is nonzero, is infinitely more useful than no test.

<!-- SPEAKER: The "failing tests are expected" point is important for engineers who are used to green/red binary. AI testing is about rates and thresholds, not binary pass/fail. Time: ~5 min -->

---
<!-- _class: section -->

# Discussion

---

## Discussion Prompts

> **Facilitator prompt:** Think of a time you shipped a feature that "worked in testing" but had unexpected behavior in production. Looking back, how many of the 5 deterministic thinking failure modes were at play? Which one would have been cheapest to catch early?

> **Facilitator prompt:** Your team is debating whether to use Claude Haiku or Claude Sonnet for a document extraction feature that will run 50,000 times a day. Walk the group through the cost math and the quality-testing process you would use to make that decision.

> **Facilitator prompt:** A product manager pushes back: "We just need a working demo by Friday; we can clean up the environment setup later." At what point does "later" become a production incident? What specific Phase 00 shortcut most often causes a 2 a.m. page?

> **Facilitator prompt:** You are onboarding a new engineer to an AI project. You have 30 minutes. Which three habits from Phase 00 do you install first, and why those three specifically?

<!-- SPEAKER: Give groups 5-7 minutes per prompt. These are designed to surface real experience and concrete war stories from the room. The fourth prompt is particularly good for senior engineers who may be skeptical of "basics." Time: ~20-25 min total -->

---

## Exercises

**Hands-on work for this phase (individual or pair):**

1. **Environment check:** Run all six verification commands from L01. Every check must pass before moving to Phase 01.

2. **Distribution exercise:** Write the `run_n_times` function from L04. Run the same classification prompt 20 times. Print the Counter. Is the distribution what you expected?

3. **Cost calculator:** Pick a feature you are building or have built. Estimate: average input tokens, average output tokens, expected calls per month. Which model tier hits your budget constraint?

4. **Debug log:** Add the `DebugLogger` from L10 to any existing Python script. Make 5 calls. Open the JSONL and verify every record has the expected fields.

5. **Git habit:** Make one prompt change to any AI script. Review it with `git diff`. Commit it with a message that describes the behavioral intent, not the mechanical edit.

<!-- SPEAKER: These are sequenced to build on each other. The distribution exercise is the one that generates the most discussion - people are often surprised by how much variance appears in a "consistent" classifier. Time: ~30-40 min depending on group -->

---

## What's Next: Phase 01

**Phase 01: Prompt and Context Engineering**

You now have:
- A working, reproducible environment
- The probabilistic mindset: you test distributions, not single outputs
- Cost and latency instrumentation from day one
- Logs that capture what was sent and received

**Phase 01 builds on all of this:**

| Phase 01 Lesson | Requires from Phase 00 |
|---|---|
| Anatomy of a prompt | First API call (L03) |
| System prompts | Probabilistic mindset (L04) |
| Few-shot examples | Token counting (L03, L06) |
| Structured output | Distribution testing (L04) |
| Context window management | Model docs (L05) |

The habit of measuring at the distribution level, not the single-sample level, is the foundation every Phase 01 technique builds on. You will write prompts differently now that you know a single passing test proves nothing.

<!-- SPEAKER: Bridge to Phase 01. Emphasize continuity: Phase 00 was not just setup, it was installing the mental operating system that makes all future phases more effective. Time: ~5 min -->

