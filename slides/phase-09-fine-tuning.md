---
marp: true
theme: applied-ai
class: title
paginate: true
footer: 'Applied AI From Scratch · Phase 09'
---

# Phase 09: Fine-Tuning & Customization
## When prompting isn't enough: the decision ladder

Phase 09 of 13 · 9 lessons · ~10 hours

<!-- SPEAKER: Welcome to Phase 09. Most engineers jump to fine-tuning too early. This phase teaches you to climb the ladder correctly, and when you do reach fine-tuning, how to do it properly with evals to prove it was worth it. Time: ~5 min -->

---

## Who this is for

You are a **working software engineer** who:

- Has hit a wall with prompt engineering or RAG
- Is spending too much on inference and wants a smaller, faster model
- Needs format consistency the base model keeps breaking
- Has private domain data that shouldn't leave your infrastructure

**What you will NOT get:**
- Fine-tuning as a first resort
- Academic deep-dives into transformer math
- GPU cluster setup tutorials

<!-- SPEAKER: The key framing: fine-tuning is rung five. Most people in the room have not exhausted rungs one through four. Ask them before the session starts. -->

---

## Prerequisites

| Skill | Where |
|-------|-------|
| Prompt engineering + structured output | P01 |
| RAG pipeline: retrieve, embed, generate | P02 |
| Calling LLM APIs and parsing JSON responses | P01, P02 |
| Running evals on a golden set | P05 |
| Reading Python: loops, dicts, file I/O | any |

**Time commitment:** ~10 hours across 9 lessons. Capstone adds 2-3 hours.

<!-- SPEAKER: The P05 prerequisite is critical. If someone has not built evals, they cannot prove the fine-tune is better. That is the whole point of the capstone. -->

---

## What you will build: the fine-tune workflow

| Artifact | Lesson |
|----------|--------|
| Decision ladder qualification checklist | 09-01 |
| Annotated JSONL dataset (100+ examples) | 09-02 |
| Managed SFT job (OpenAI / Bedrock) | 09-03 |
| LoRA adapter on a 7B open-weight model | 09-04 |
| Fine-tune vs baseline eval report | 09-05 |
| DPO preference dataset and training run | 09-06 |
| Distillation pipeline: frontier to small model | 09-07 |
| vLLM serving stack with Docker Compose | 09-08 |
| End-to-end ROI proof (capstone) | 09-09 |

<!-- SPEAKER: Every artifact is reusable. The capstone ties them all together: qualify the problem, engineer the dataset, train, evaluate, measure ROI. -->

---

## The through-line: the decision ladder

```ascii
Rung 1: Better prompt + system message         cost: $0
Rung 2: Few-shot examples in prompt            cost: tokens
Rung 3: RAG (add knowledge, no retraining)     cost: retrieval
Rung 4: Prompt caching (cost reduction)        cost: cache setup
────────────────────────────────────────────
Rung 5: Fine-tune (managed API)                cost: $8/1M tokens
Rung 6: LoRA/QLoRA (DIY, needs GPU)            cost: GPU time
Rung 7: Full fine-tune (rare, massive data)    cost: very high
```

**95% of problems live above the line. This phase covers all 7 rungs.**

> **Key insight:** If you cannot articulate which rung you are on and why the ones above it failed, you are not ready to fine-tune.

<!-- SPEAKER: Come back to this diagram after every lesson. Every lesson is one rung or one part of using a rung correctly. The line separates "no GPU needed" from "GPU needed." -->

---
<!-- _class: section -->

## L01: The Decision Ladder
### Prompt, RAG, or Fine-Tune?

---

## L01: The problem

You have a support bot that keeps formatting JSON wrong. You spend a week tuning prompts. Nothing sticks. A colleague says "just fine-tune it."

**Before you do, have you actually tried:**

- A stricter system prompt with a JSON schema example?
- 3-5 few-shot examples of correct JSON in the prompt?
- A smaller temperature (0.0) to reduce format drift?
- Constrained generation / structured output mode?

**The fine-tuning reflex is expensive and slow. It is often the wrong tool.**

> **Key insight:** Format failures are almost always a prompt problem, not a training data problem. The model knows JSON: you have not told it clearly enough what you want.

<!-- SPEAKER: Get specific with the pain. Someone in the room has spent a week fine-tuning when a better prompt would have worked in an hour. -->

---

## L01: Qualifying the problem

```python
LADDER = [
    ("Prompt engineering", "Try 5 different prompt formulations. "
     "Measure on golden set. Baseline first."),
    ("Few-shot examples", "Add 3-5 examples of ideal outputs to prompt."),
    ("RAG", "Is the problem lack of knowledge? Retrieve it, don't train it."),
    ("Prompt caching", "Is cost the problem? Cache the system prompt."),
    ("Fine-tune", "Format consistency, latency, cost, private data? Now fine-tune."),
]

for rung, action in LADDER:
    print(f"[{rung}] {action}")
```

**Red flags that fine-tuning is wrong:**
- "It doesn't know X" - use RAG
- "It's not creative enough" - prompt engineering
- "It sometimes ignores instructions" - structured output + stricter prompt

<!-- SPEAKER: Walk through each red flag. Ask the room: which of these have you blamed on needing fine-tuning? -->

---
<!-- _class: section -->

## L02: Dataset Engineering
### The Durable Moat

---

## L02: The problem

You decide to fine-tune. You grab 50 examples from your test suite, upload them, and run the job. The fine-tuned model is worse than baseline.

**What went wrong:**
- 50 examples of the same input pattern (no diversity)
- Labels generated quickly, not matched to the actual target behavior
- No adversarial examples: edge cases the model currently fails on
- No validation split: no way to detect overfitting

**The dataset is the model.** Poor data in, poor model out.

> **Key insight:** Competitors can copy your model choice and your prompt strategy. They cannot easily copy 10,000 production examples with human-verified labels.

<!-- SPEAKER: The moat framing lands well with product engineers. The dataset is a long-term asset, not a one-time cost. -->

---

## L02: What a good dataset looks like

```python
import json

example = {
    "messages": [
        {
            "role": "user",
            "content": "Extract company and revenue from: "
                      "Acme Corp reported Q3 revenue of $42M"
        },
        {
            "role": "assistant",
            "content": '{"company": "Acme Corp", "revenue": "$42M", "period": "Q3"}'
        }
    ]
}
print(json.dumps(example))
```

**Sources by priority:**
1. Production logs with human-verified outputs (highest signal)
2. Frontier model synthetic + human QA (scalable)
3. Adversarial: examples the model currently fails on (highest leverage)

**Minimum size:** 50-100 for format tasks. 500+ for knowledge tasks. Diversity beats volume.

<!-- SPEAKER: Emphasize that the JSONL format is the OpenAI / compatible format. It is also what Anthropic Bedrock fine-tuning accepts with minor variation. -->

---
<!-- _class: section -->

## L03: Supervised Fine-Tuning via Managed APIs
### No GPU Required

---

## L03: The problem

You have 200 high-quality examples and a format consistency problem that prompting cannot solve. You want results this week, not after buying a GPU and debugging CUDA.

**Managed fine-tuning tradeoffs:**

```ascii
Option              Control    Speed      Cost          Ops overhead
──────────────────────────────────────────────────────────────────
OpenAI (gpt-4o-mini)  low       hours      $8/1M tokens   none
Anthropic (Bedrock)   low       hours      similar         none
DIY LoRA (GPU)        high      days       GPU time        high
```

**When managed wins:** no GPU, no ML ops team, want results in hours.

<!-- SPEAKER: The target customer for managed SFT is a small team or solo engineer. No infra, no ops. The tradeoff is control and cost at scale. -->

---

## L03: Running a managed fine-tune

```python
import time
from openai import OpenAI
client = OpenAI()
# Upload dataset
file = client.files.create(
    file=open("train.jsonl", "rb"), purpose="fine-tune"
)
# Create job
job = client.fine_tuning.jobs.create(
    training_file=file.id, model="gpt-4o-mini"
)
print(f"Job: {job.id}  Status: {job.status}")
# Poll until done
while job.status not in ("succeeded", "failed"):
    time.sleep(30)
    job = client.fine_tuning.jobs.retrieve(job.id)
    print(f"Status: {job.status}")
print(f"Model: {job.fine_tuned_model}")
```

<!-- SPEAKER: The polling loop is intentionally simple. In production you would use a webhook or a background job. But for a first run, polling is fine. -->

---
<!-- _class: section -->

## L04: LoRA and QLoRA
### Intuition and Hands-On

---

## L04: The problem

You need fine-tuning control that managed APIs do not give you: custom base model, no data leaving your infrastructure, the ability to run multiple adapters on the same base.

**But full fine-tuning a 7B model:**
- Rewrites 7 billion parameters
- Requires ~140GB VRAM in float16
- Costs thousands of dollars per run

**LoRA: train 0.12% of parameters instead.**

> **Key insight:** You are not rewriting the model. You are adding a thin adapter that steers its behavior. The base model is frozen.

<!-- SPEAKER: The frozen-base framing is the key intuition. Analogy: you are adding a lens filter to a camera, not rebuilding the camera. -->

---

## L04: LoRA intuition

```ascii
FULL FINE-TUNE                    LoRA
──────────────                    ────
W_original (7B params)            W_original (frozen)
         +                                 +
W_delta (7B params)               A (rank 16) x B (rank 16)
                                  = 0.12% of params
Total: 14B params updated         Total: 8M params updated
VRAM: ~140GB                      VRAM: ~16GB (+ QLoRA: ~10GB)
```

```python
from peft import LoraConfig, get_peft_model

lora_config = LoraConfig(
    r=16,                    # rank: higher = more capacity
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.05,
    task_type="CAUSAL_LM"
)
model = get_peft_model(base_model, lora_config)
model.print_trainable_parameters()
# trainable params: 4,194,304 || all params: 3,500,000,000 || 0.12%
```

<!-- SPEAKER: The print_trainable_parameters output is the money line. Show it live if possible. The number lands differently when people see 0.12% on their own screen. -->

---
<!-- _class: section -->

## L05: Evaluating a Fine-Tune vs Baseline
### Prove It Before You Ship It

---

## L05: Fine-tune vs baseline eval

A fine-tune is a code change. Code changes need tests. Never ship on vibes.

```python
results = {"baseline": [], "finetuned": []}

for example in golden_set:
    for variant, model in [("baseline", BASE_MODEL),
                            ("finetuned", FINETUNED_MODEL)]:
        output = call_model(model, example["input"])
        score = judge(example["input"], output, example["expected"])
        results[variant].append(score)

for variant, scores in results.items():
    print(f"{variant}: {sum(scores)/len(scores):.3f} avg score")
```

**Gate on all four metrics, not just quality:**
- Format compliance rate (exact match on structure)
- LLM-as-judge quality score (vs golden outputs)
- Latency (p50 and p95)
- Cost per 1,000 requests

> **Key insight:** A fine-tune that scores 2% higher but costs 3x more is probably not worth it. You cannot know that without measuring both sides.

<!-- SPEAKER: The four-metric gate is the key engineering habit. Teams focus on quality and ignore cost. Then the fine-tune ships and the bill triples. -->

---
<!-- _class: section -->

## L06: Preference Tuning with DPO
### Teaching What's Preferred, Not Just What's Correct

---

## L06: SFT vs DPO

You fine-tuned with SFT. The model gives correct answers. But the tone is wrong: too formal, inconsistent with your brand voice, or too generic when you need specificity.

**SFT teaches what to do. DPO teaches what is preferred among valid options.**

```ascii
SFT dataset:   (prompt, correct response)
DPO dataset:   (prompt, chosen response, rejected response)

RLHF (old way)                    DPO (current standard)
──────────────                    ──────────────────────
1. Collect preferences             1. Collect preferences
2. Train reward model              (no reward model needed)
3. PPO loop, 3+ hyperparameters    2. Optimize on preference pairs
4. Reward hacking is real          3. One hyperparameter (beta)
```

> **Key insight:** DPO is RLHF with the reward model removed. Same objective, simpler training loop, stabler results.

**Use when:** SFT gives correct but bland outputs. You want style, persona, or safety preference baked in.

<!-- SPEAKER: The chosen/rejected framing is the key concept. Both responses are plausibly correct. DPO teaches the model which is preferred, not which is right. -->

---
<!-- _class: section -->

## L07: Distillation for Cost
### Frontier Quality at Open-Weight Price

---

## L07: The distillation workflow

You use claude-opus for a high-volume extraction task. Quality is excellent. The bill is not. **Distillation:** use the frontier to generate training data for a smaller model.

<div class="mermaid">
flowchart LR
    A[Production inputs] --> B[Frontier model\nclaude-opus]
    B --> C[High-quality outputs]
    C --> D[Human QA sample\n10% spot-check]
    D --> E[JSONL dataset]
    E --> F[Fine-tune\nsmall model]
    F --> G[Distilled model\nmistral-7B]
    G --> H[Eval vs frontier\non golden set]
    H --> I{90% quality?}
    I -->|yes| J[Deploy distilled\n10x cheaper]
    I -->|no| K[Expand dataset\nor raise bar]
</div>

**Key risk:** the distilled model inherits the frontier's errors. Spot-check before training, bad labels compound.

> **Key insight:** You are training a specialist, not compressing a generalist. The frontier is the teacher; the task distribution is the curriculum.

<!-- SPEAKER: The 90% quality gate is a rule of thumb. Some teams accept 85% if the cost savings are large enough. The point is to measure and decide, not to guess. -->

---
<!-- _class: section -->

## L08: Serving an Open-Weight Model with vLLM
### From Fine-Tuned Weights to Production API

---

## L08: vLLM serving

You have a fine-tuned LoRA adapter. Turning it into a production API requires batching, KV cache management, and an OpenAI-compatible surface your existing code can call without changes.

```python
from openai import OpenAI

# vLLM exposes an OpenAI-compatible API
# Swap base_url, no other code changes needed
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="mistralai/Mistral-7B-v0.1",
    messages=[{"role": "user", "content": "Extract entities:"}]
)
```

```bash
vllm serve mistralai/Mistral-7B-v0.1 \
  --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.9
```

**GPU sizing:** 7B model needs ~16GB VRAM in float16. QLoRA reduces to ~10GB.

<!-- SPEAKER: The OpenAI-compatible surface is the key selling point. Teams already calling OpenAI can point at vLLM with one line change. -->

---

## L08: Architecture and cost at scale

<div class="mermaid">
flowchart LR
    A[App] --> B[OpenAI-compatible\nclient]
    B --> C[vLLM server\n:8000]
    C --> D[PagedAttention\nKV cache]
    C --> E[Continuous\nbatching]
    D --> F[Fine-tuned model\nor open-weight]
    E --> F
    F --> G[Response]
</div>

```ascii
Option                  Quality   Latency    Cost/1k req
──────────────────────────────────────────────────────
claude-opus (prompted)  ████████   ~3s        $0.90
claude-haiku (prompted) ██████     ~1s        $0.05
Fine-tuned gpt-4o-mini  ███████    ~0.8s      $0.06
LoRA on mistral-7B      ██████     ~0.5s      $0.01 (GPU amortized)
```

> **Key insight:** vLLM's PagedAttention manages KV cache like virtual memory in an OS. Concurrent requests share cache pages instead of each allocating full context length.

<!-- SPEAKER: The cost table is the ROI argument. At 10M requests per month, $0.90 vs $0.01 per thousand is a $9,000 bill vs a $100 bill. -->

---
<!-- _class: section -->

## L09: Capstone
### Fine-Tune for a Domain Task, Prove ROI

---

## L09: The capstone workflow

<div class="mermaid">
flowchart LR
    A[Production logs] --> B[Dataset pipeline]
    C[Synthetic data] --> B
    D[Adversarial cases] --> B
    B --> E[JSONL dataset]
    E --> F[Managed SFT]
    E --> G[LoRA training]
    F --> H[Fine-tuned model]
    G --> H
    H --> I[Eval vs baseline]
    I --> J{ROI positive?}
    J -->|yes| K[Deploy via vLLM]
    J -->|no| L[Back to prompting]
</div>

<!-- SPEAKER: This diagram is the whole phase. The capstone is not about the fine-tune. It is about proving whether the fine-tune was worth it. -->

---

## L09: Proving ROI

**The five questions you must answer before shipping:**

1. What rung on the ladder did you exhaust before reaching fine-tuning?
2. What is your golden set? How many examples? How were they labeled?
3. What is the quality delta vs baseline? (use your Phase 05 eval harness)
4. What is the latency delta?
5. What is the cost delta at your production request volume?

```ascii
fine-tune-roi-report.md
  - Problem qualified: rung 1-4 results
  - Dataset: 100 examples, sources, QA process
  - Quality: fine-tune 0.87 vs baseline 0.79 (+10%)
  - Latency: fine-tune 0.8s vs baseline 3.2s (-75%)
  - Cost: fine-tune $0.06/1k vs baseline $0.90/1k (-93%)
  - Decision: SHIP (ROI positive on all three axes)
```

> **Key insight:** The ROI report is the deliverable. The fine-tuned model is just the mechanism.

<!-- SPEAKER: The ROI report format is intentionally simple. It is a one-pager you can show a product manager or an engineering lead. That is the real artifact. -->

---

## Discussion prompts

> **Facilitator prompt:** Think about a model call in your current system that runs more than 1,000 times per day. Walk through the decision ladder for it. Which rung is it on? Which rungs above it have you actually tried?

> **Facilitator prompt:** What is the biggest risk in using a frontier model to generate your fine-tuning dataset? How would you detect if the frontier made systematic errors that got baked into your fine-tune?

> **Facilitator prompt:** A fine-tune scores 8% higher than baseline on your golden set. But it costs 3x more per request and adds 200ms of latency. Does it ship? What other information would you need?

> **Facilitator prompt:** Your team wants to fine-tune for "brand voice." What does a good preference dataset for that use case look like? Who writes the chosen vs rejected labels?

> **Facilitator prompt:** When does distillation fail? What kinds of tasks are bad candidates for distillation from a frontier model?

<!-- SPEAKER: Start with question 1 to warm up the room. Questions 3 and 5 are the deepest, use them if the group is engaged and time allows. -->

---

## Exercises

**Easy (1-2 hours)**

- Take a prompt you use today and run it through the decision ladder checklist. Document which rungs you have and have not tried. Write up the result as a one-page qualification doc.
- Write a 20-example JSONL dataset for a task you own. At least 5 examples must be adversarial (cases the current model gets wrong). Use the format from L02.

**Medium (3-4 hours)**

- Run a managed fine-tune on gpt-4o-mini with your 20-example dataset. Compare it to the baseline on a 10-example held-out set. Report quality, latency, and cost.
- Set up a local vLLM instance with a 7B open-weight model. Point an existing script at it using the OpenAI-compatible client. Measure latency vs the hosted API.

**Hard (6-8 hours)**

- Build the full capstone workflow: qualify a real production problem, engineer a 100-example dataset from three sources, run managed SFT, evaluate with your Phase 05 harness, and write the ROI report. Present findings including a go/no-go recommendation.

<!-- SPEAKER: The Hard exercise is the capstone. Encourage teams to work on a real production use case, not a toy dataset. The ROI report format from L09 is the deliverable. -->

---

## Further reading

**Foundational papers (read the abstract and conclusion, skip the math)**

- Hu et al. (2021) "LoRA: Low-Rank Adaptation of Large Language Models": the original LoRA paper. Appendix B has the rank sensitivity analysis.
- Rafailov et al. (2023) "Direct Preference Optimization": the DPO paper. Section 3 explains why the reward model can be eliminated.

**Practical guides**

- OpenAI Fine-Tuning Guide (platform.openai.com/docs/guides/fine-tuning): authoritative reference for the managed API. Read "When to use fine-tuning" first.
- Hugging Face PEFT docs (huggingface.co/docs/peft): LoRA, QLoRA, and adapter patterns with code examples.

**Benchmark context**

- "Is Fine-Tuning LLMs Worth It?" (Anyscale Blog, 2023): empirical comparison of prompting vs fine-tuning across task types. The results on format tasks vs knowledge tasks are directly relevant to L01.

<!-- SPEAKER: Do not assign all five. Pick two based on the room. The OpenAI guide is the most practical for most engineers. The Anyscale post is the most relevant to the L01 decision framework. -->

---

## What's next: Phase 10
### Multimodal and Voice

**Phase 10 adds a new input modality to everything you have built.**

| Lesson | What you build |
|--------|---------------|
| Vision: Images and Documents | Extract structured data from PDFs and screenshots |
| Audio: Transcription and Voice | Whisper pipeline, voice I/O for agents |
| Multimodal RAG | Retrieve across text, images, and tables |
| Video Analysis | Frame extraction and summarization |
| Multimodal Evals | How to evaluate outputs you cannot read |
| Capstone: Multimodal Agent | Document understanding pipeline, end to end |

**The skills from P09 carry forward:** fine-tuning multimodal models follows the same dataset engineering and eval patterns. The ladder still applies.

<!-- SPEAKER: Close by connecting forward. The decision ladder and the eval-first habit are not fine-tuning concepts. They are engineering habits that apply to every modality. -->

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
