---
marp: true
theme: applied-ai
class: title
paginate: true
footer: 'Applied AI From Scratch · Phase 01: Prompt & Context Engineering'
---

# Phase 01: Prompt & Context Engineering

### The foundational skill of applied AI engineering

**Applied AI From Scratch**
14 lessons · ~15 hours · Python + TypeScript

<!-- SPEAKER: Welcome to Phase 01. This phase teaches the skill that underlies everything else in AI engineering: communicating precisely with models and managing what they see. Before RAG, before agents, before fine-tuning - you need this. Time: ~5 min -->

---

## Who this is for

You are a **working software engineer** who:

- Has made an API call and gotten a response
- Has been confused when the model ignores your instructions
- Wants outputs that are **reliable, not lucky**

**What you will NOT get:**
- "Just write better prompts" advice without a framework
- Prompt hacks that break on the next model version
- Techniques that only work in playgrounds

<!-- SPEAKER: Set realistic expectations. Prompting is engineering. It has structure, patterns, and measurable quality. This phase gives you the mental model. -->

---

## What you will build

| Artifact | Lesson |
|----------|--------|
| Request anatomy template | 01-01 |
| Few-shot + CoT pattern library | 01-03 |
| Context engineering playbook | 01-04 |
| Context-window manager | 01-05 |
| Structured output + retry loop | 01-06/07 |
| Prompt template + versioning system | 01-08 |
| DSPy optimizer scaffold | 01-09 |
| Production extraction service | Capstone |

<!-- SPEAKER: Every lesson ships a reusable artifact. The capstone wires the extraction service together with everything from the phase. -->

---
<!-- _class: section -->

## The Foundation

### Request anatomy and the probabilistic mindset

---

## The request is not a command

```python
response = client.messages.create(
    model="claude-opus-4-5",
    system="You are a precise JSON extractor. Return only valid JSON.",
    messages=[
        {"role": "user", "content": "Extract the company name: Acme Corp Q3 2024"},
        {"role": "assistant", "content": '{"company": "Acme Corp", "period": "Q3 2024"}'},
        {"role": "user", "content": user_input},
    ],
    max_tokens=512,
)
```

Three levers: **system** (persona + constraints), **user** (task), **assistant** (examples).

<!-- SPEAKER: The assistant prefill is the most underused lever. Showing the model the format of the expected output is more reliable than describing it in words. -->

---

## Request anatomy: the three roles

<div class="mermaid">
flowchart TD
    A[system prompt] -->|persona + constraints| M[Model]
    B[user message] -->|task + context| M
    C[assistant prefill] -->|output format example| M
    M --> D[Response]
    style M fill:#4f46e5,color:#fff
    style A fill:#141414,color:#a78bfa,stroke:#2a2a2a
    style B fill:#141414,color:#e8e8e8,stroke:#2a2a2a
    style C fill:#141414,color:#10b981,stroke:#2a2a2a
    style D fill:#10b981,color:#fff
</div>

**Rule:** put constraints in system, not user. The model prioritizes system instructions.

<!-- SPEAKER: This is the most common mistake: putting constraints in the user message where they get buried by the actual task content. -->

---

## Prompt Fundamentals: what actually works

| Technique | Effect | When to use |
|-----------|--------|-------------|
| Role assignment | Activates domain knowledge | Always in system |
| Explicit format | Reduces post-processing | Structured outputs |
| Negative constraints | Prevents common failures | Edge-case handling |
| Step-by-step | Improves reasoning quality | Complex tasks |
| Temperature control | Tunes determinism | 0 = consistent, 1 = creative |

> Prompts that work on one model may need adjustment on another. **Test on your target model, not a playground.**

<!-- SPEAKER: Temperature 0 doesn't mean deterministic - it means greedy decoding. You can still get variation from sampling. Always capture prompt + model version together in your version history. -->

---
<!-- _class: section -->

## Few-Shot & Chain-of-Thought

### Show the model how to think, not just what to produce

---

## Few-shot: examples beat instructions

```python
SYSTEM = """Extract structured data from support tickets.
Return JSON: {"priority": "low|medium|high", "category": str, "summary": str}"""

EXAMPLES = [
    {"role": "user",      "content": "My login has been broken for 3 days"},
    {"role": "assistant", "content": '{"priority":"high","category":"auth","summary":"Login broken 3 days"}'},
    {"role": "user",      "content": "Can I change my display name?"},
    {"role": "assistant", "content": '{"priority":"low","category":"settings","summary":"Display name change request"}'},
]

messages = EXAMPLES + [{"role": "user", "content": ticket_text}]
```

2-5 examples beats 200 words of instructions. Cover the edge cases.

<!-- SPEAKER: The examples ARE the specification. Write them like test cases: cover the boundary conditions, not just the happy path. -->

---

## Chain-of-thought: make reasoning visible

```python
SYSTEM = """Classify this support ticket. 
Think step by step:
1. What is the user trying to do?
2. Is there urgency signals (broken, can't, urgent, ASAP)?
3. What category fits best?
Then output: {"priority": ..., "category": ..., "reasoning": "..."}"""
```

CoT improves accuracy on multi-step reasoning by **~30-40%** on complex tasks.

**When to use:** classification with nuance, math, multi-constraint decisions.
**When to skip:** simple extraction, format conversion — adds latency, not value.

<!-- SPEAKER: The reasoning field in the output is also useful for debugging when the model classifies incorrectly. You can see where its reasoning went wrong. -->

---
<!-- _class: section -->

## Context Engineering

### "Context is the product" — the real job of an AI engineer

---

## What goes in the context window

<div class="mermaid">
flowchart LR
    A[System prompt] --> CTX[Context window]
    B[Conversation history] --> CTX
    C[Retrieved documents] --> CTX
    D[Tool results] --> CTX
    E[Current user message] --> CTX
    CTX --> M[Model]
    M --> F[Response]
    style CTX fill:#4f46e5,color:#fff
    style M fill:#a78bfa,color:#0a0a0a
    style F fill:#10b981,color:#fff
</div>

**The context window is finite.** Every token costs money and attention. The engineer decides what earns its place.

<!-- SPEAKER: "Context is the product" means your job as an AI engineer is to curate what the model sees, not just what you ask it. The quality of your context engineering determines the quality of your outputs. -->

---

## Context engineering: the decisions

| What to include | Why |
|-----------------|-----|
| Relevant retrieved docs | Ground the response in facts |
| Recent conversation turns | Maintain coherence |
| Structured state | Replace implicit memory |
| Negative examples | Prevent known failure modes |

| What to cut | Why |
|-------------|-----|
| Old conversation history | Low value, high cost |
| Verbose instructions | Compress to bullets |
| Duplicate information | Wastes attention budget |

<!-- SPEAKER: The hardest skill is knowing what NOT to include. A 200k context window doesn't mean you should fill it. Attention is diluted by irrelevant content. -->

---

## Context-window management

When the conversation grows beyond the model's window:

```python
def manage_context(messages: list, max_tokens: int = 150_000) -> list:
    total = count_tokens(messages)
    if total < max_tokens * 0.8:
        return messages

    # Keep system + last N turns + summarize the rest
    system = messages[0]
    recent = messages[-6:]          # last 3 user/assistant pairs
    middle = messages[1:-6]

    if middle:
        summary = summarize(middle)  # one LLM call to compress history
        return [system, summary_msg(summary)] + recent

    return [system] + recent
```

**Rule:** never silently drop messages. Summarize the middle, keep the ends.

<!-- SPEAKER: Silent truncation is how you get support agents that forget customer context mid-conversation. Always summarize and tell the model what happened in the omitted section. -->

---
<!-- _class: section -->

## Structured Outputs

### From "extract the name" to production-grade data pipelines

---

## Structured outputs: three approaches

<div class="mermaid">
flowchart LR
    A[Task] --> B{Reliability needed?}
    B -->|low - demos| C[JSON in prompt + parse]
    B -->|medium| D[JSON mode / response_format]
    B -->|high - production| E[Tool use with schema]
    C --> F[Fragile - breaks on refusals]
    D --> G[Valid JSON, wrong schema]
    E --> H[Validated against Pydantic schema]
    style E fill:#10b981,color:#fff
    style H fill:#10b981,color:#fff
    style F fill:#ef4444,color:#fff
</div>

For production: **always use tool use** with a Pydantic schema. The model is forced to conform.

<!-- SPEAKER: The progression from prompt-parsing to tool-use-with-schema mirrors the progression from demo to production. If your extraction pipeline breaks when the model adds a "Here is the JSON:" prefix, use tool use instead. -->

---

## Validation + retry loop

```python
from pydantic import BaseModel, ValidationError
import anthropic

class Ticket(BaseModel):
    priority: Literal["low", "medium", "high"]
    category: str
    summary: str

def extract_with_retry(text: str, max_retries: int = 3) -> Ticket:
    for attempt in range(max_retries):
        response = client.messages.create(
            tools=[{"name": "extract", "input_schema": Ticket.model_json_schema()}],
            messages=[{"role": "user", "content": text}],
        )
        try:
            return Ticket(**response.content[0].input)
        except ValidationError as e:
            text = f"Previous output had errors: {e}\n\nOriginal: {text}"
    raise ExtractionFailed(f"Failed after {max_retries} attempts")
```

<!-- SPEAKER: The retry loop feeds the validation error BACK to the model as context. The model can usually self-correct. Three retries catches ~99% of cases. -->

---
<!-- _class: section -->

## Optimization & State

### Templates, versioning, DSPy, multi-turn

---

## Prompt templates & versioning

```python
# prompts/extract_ticket_v2.py
SYSTEM = """You are a support ticket classifier.
Classify tickets into: {categories}
Priority rules: {priority_rules}
Output format: {output_schema}"""

# Version metadata
PROMPT_META = {
    "name": "extract_ticket",
    "version": "2.1",
    "model": "claude-opus-4-5",
    "last_eval_score": 0.94,
    "changed": "Added 'billing' category, tightened priority rules",
}
```

**Rule:** treat prompts like code. Git-track them, eval before deploy, never edit in prod.

<!-- SPEAKER: The "last_eval_score" field is the most important piece. If you can't answer "what's the accuracy of this prompt?" you're not ready to ship it. The eval is the gate. -->

---

## DSPy: when to automate prompt optimization

**Use DSPy when:**
- You have 50+ labeled examples
- Manual prompt tuning has plateaued
- The task has clear, measurable quality criteria

```python
import dspy

class ExtractTicket(dspy.Signature):
    """Classify a support ticket."""
    ticket_text: str = dspy.InputField()
    priority: Literal["low", "medium", "high"] = dspy.OutputField()
    category: str = dspy.OutputField()

extractor = dspy.ChainOfThought(ExtractTicket)
optimizer = dspy.BootstrapFewShot(metric=exact_match)
optimized = optimizer.compile(extractor, trainset=examples)
```

DSPy finds examples and CoT instructions that maximize your metric automatically.

<!-- SPEAKER: DSPy doesn't replace prompt engineering - it automates the trial and error of choosing examples and instructions. You still need a good metric and labeled data. Without those, it just optimizes noise. -->

---

## Multi-turn state: what belongs where

<div class="mermaid">
flowchart TD
    A{State type?} -->|ephemeral: this conversation| B[In-context messages list]
    A -->|user preferences across sessions| C[Database: user profile]
    A -->|long conversation history| D[Summarize + compress into context]
    A -->|tool results over 10k tokens| E[Truncate + store reference]
    style A fill:#4f46e5,color:#fff
    style B fill:#10b981,color:#fff
</div>

Most multi-turn bugs are **state management bugs**, not model bugs.

<!-- SPEAKER: When a conversation assistant "forgets" something the user said earlier, it's almost never the model's fault. The message was truncated, summarized away, or simply never inserted into the context. -->

---

## System prompt design: the patterns

```
SYSTEM PROMPT STRUCTURE (recommended order):

1. Role + persona          "You are a precise data extraction assistant."
2. Capabilities + limits   "You can: X, Y. You cannot: Z."
3. Output format           Describe exact structure. Show an example.
4. Priority rules          "If X, do Y. If ambiguous, ask."
5. Negative constraints    "Never output explanations unless asked."
6. Tone/style (if needed)  "Concise. No filler. Use technical terms."
```

**Rule:** test your system prompt against adversarial inputs. Users WILL try to override it.

<!-- SPEAKER: The order matters. The model pays more attention to the beginning and end. Put non-negotiable constraints at the start. Put style notes at the end. -->

---

## Handling refusals & edge cases

```python
def handle_refusal(response: str, fallback_fn) -> str:
    REFUSAL_SIGNALS = [
        "I can't", "I'm not able", "I won't", "I'm unable",
        "I don't have access", "As an AI",
    ]
    if any(sig.lower() in response.lower() for sig in REFUSAL_SIGNALS):
        # Log for analysis, route to fallback
        log_refusal(response)
        return fallback_fn()
    return response
```

**Three causes of refusals:**
1. Genuinely out-of-scope request - route elsewhere
2. Prompt triggered safety filter - rephrase the request
3. Model uncertainty - add clarifying context

<!-- SPEAKER: Refusals are data. Log them, categorize them, and look at your error distribution monthly. The most common cause is prompts that inadvertently trigger safety filters with otherwise benign requests. -->

---

## Prompt caching: cost and latency

```python
response = client.messages.create(
    system=[{
        "type": "text",
        "text": LONG_SYSTEM_PROMPT,      # e.g. 10k tokens of instructions + examples
        "cache_control": {"type": "ephemeral"},
    }],
    messages=[{"role": "user", "content": user_query}],
)

# Cache hit: ~90% cost reduction, ~2x latency reduction on the cached portion
print(response.usage.cache_read_input_tokens)   # tokens served from cache
print(response.usage.cache_creation_input_tokens) # tokens written to cache
```

Cache hits reduce input token cost by ~90%. TTL: 5 minutes.

<!-- SPEAKER: Prompt caching is the single highest-ROI optimization for systems with a large static system prompt or few-shot examples. Mark the stable prefix with cache_control and the cache is reused across requests. The 5-minute TTL means high-traffic systems benefit most. -->

---
<!-- _class: section -->

## The Capstone

### A production extraction service + prompt library

---

## Capstone architecture

<div class="mermaid">
flowchart TD
    A([HTTP request]) --> B[FastAPI endpoint]
    B --> C[Input validation: Pydantic]
    C --> D[Prompt template v2.x]
    D --> E[Claude API with tool use]
    E --> F[Validation + retry loop]
    F -->|valid| G[Cache result: Redis]
    F -->|failed after 3 retries| H([Return error + fallback])
    G --> I([Response: structured JSON])
    style A fill:#4f46e5,color:#fff
    style I fill:#10b981,color:#fff
    style H fill:#ef4444,color:#fff
    style E fill:#a78bfa,color:#0a0a0a
</div>

<!-- SPEAKER: This is the capstone architecture. Every component maps to a lesson in this phase. The retry loop and validation are from L06/07, caching from L13, FastAPI wrapping from Phase 06. -->

---

## What the capstone ships

```
phases/01-prompt-and-context/14-capstone-extraction/
├── code/
│   ├── main.py              # FastAPI service
│   ├── prompts/
│   │   ├── extract_v2.py    # versioned prompt + metadata
│   │   └── prompt_registry.py
│   ├── models.py            # Pydantic schemas
│   ├── retry.py             # validation + retry loop
│   └── Dockerfile
├── outputs/
│   ├── runbook-extraction-service.md
│   └── prompt-library/      # reusable prompt templates
└── checks.json
```

Ships: a running service + a library of 10+ reusable prompt patterns.

---

## Summary: the principles

| Principle | Rule |
|-----------|------|
| Role in system | Constraints go in system, not user |
| Examples beat instructions | 3 examples > 300 words |
| CoT for reasoning | Add when task has multiple steps |
| Structured outputs | Tool use > JSON mode > prompt parsing |
| Retry on failure | Feed validation error back as context |
| Version everything | Prompt + model + eval score together |
| Cache the static parts | 90% cost saving on large system prompts |

<!-- SPEAKER: These are the defaults. Internalize them before Phase 02. Every subsequent phase builds on this foundation. -->

---

## Further study

- **Anthropic Prompt Library** - production-tested patterns across domains
- **DSPy documentation** - dspy.ai - when to automate vs handcraft
- **Pydantic v2 docs** - for validation + retry loop patterns
- **"Prompt Report" (2024)** - survey of 58 prompting techniques with benchmarks

**Next phase:** Phase 02 Retrieval & RAG - once you can prompt reliably, you need to give the model knowledge it wasn't trained on.

---
<!-- _class: title -->

# Questions?

**Phase 01: Prompt & Context Engineering**

Applied AI From Scratch
github.com/thepandanlabs/applied-ai-from-scratch

<!-- SPEAKER: Open for questions. Good workshop exercise: take a failing prompt from your own work and apply the system/user/assistant anatomy and a validation loop. -->

<!-- MERMAID INIT -->
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
      titleColor: '#a78bfa',
      edgeLabelBackground: '#2e2820',
    }
  });
</script>
