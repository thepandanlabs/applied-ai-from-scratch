---
name: prompt-finetune-decision-guide
description: Structured decision guide for choosing between prompting, RAG, and fine-tuning for any AI feature
version: "1.0"
phase: "09"
lesson: "01"
tags: [fine-tuning, decision-framework, rag, prompting, strategy]
---

# Prompt, RAG, or Fine-Tune? Decision Guide

Use this guide when a team is deciding how to improve an AI feature. Work through the rungs from cheapest to most expensive. Stop at the first rung that solves the problem.

---

## The Ladder

```
[5] Train from Scratch .... millions of examples, months, tens of millions of $
[4] Fine-Tune ............. 100-10k examples, days-weeks, $50-$10k
[3] RAG ................... documents, hours, $0 extra infra cost
[2] Few-Shot Prompting .... 3-20 examples in context, minutes, free
[1] Better System Prompt .. zero examples, minutes, free
```

---

## Rung 1: Better System Prompt

**When to apply:** Always try this first.

**Questions:**
- Does the system prompt specify persona, tone, format, and constraints explicitly?
- Have you tested at least 10 variants of the instruction?
- Did you use a capable model (not the cheapest one) to rule out capability vs. instruction issues?

**If yes to all and still failing:** Move to rung 2.

**What this fixes:** Vague instructions, inconsistent persona, wrong output format.

**What this does NOT fix:** Knowledge the model was never trained on; style that requires hundreds of examples to define.

---

## Rung 2: Few-Shot Prompting

**When to apply:** After prompt engineering is exhausted.

**Questions:**
- Have you added 5-20 input/output examples that demonstrate the desired behavior?
- Are your examples diverse (edge cases, not just the easy case)?
- Did you test with examples at the START of the prompt and at the END?

**If yes to all and still failing:** Move to rung 3.

**What this fixes:** Novel task structure the model has not seen; inconsistent output format; tone calibration within a single prompt.

**What this does NOT fix:** Large knowledge gaps; style that requires more examples than fit in context.

---

## Rung 3: RAG

**When to apply:** When the problem is a KNOWLEDGE gap.

**Questions:**
- Is the model making up answers because it lacks the information?
- Do you have documents, databases, or records the model was not trained on?
- Is the information stale (cutoff date problem)?
- Is the information private (not on the public internet)?

**If yes to any:** Use RAG. Index your knowledge base and retrieve relevant context at query time.

**What this fixes:** Missing facts, stale data, private information.

**What this does NOT fix:** Tone, output format, specialized vocabulary, latency requirements.

**Critical note:** If you fine-tune instead of using RAG for a knowledge gap, the model will learn to generate text that looks like it knows the answer. It will hallucinate convincingly. Do not fine-tune for knowledge gaps.

---

## Rung 4: Fine-Tune

**When to apply:** When RAG and prompting are exhausted AND the problem is a BEHAVIOR gap.

**The three legitimate reasons to fine-tune:**

| Reason | Signal | Example |
|--------|--------|---------|
| Output format | Model cannot reliably produce a strict schema even with prompting | Strict JSON with 15 required fields |
| Domain vocabulary | Model consistently misuses specialized terms | Medical, legal, proprietary product names |
| Tone/style at scale | Brand voice that cannot be fully specified in a prompt | 200-word warm, direct, non-corporate replies |
| Smaller model | Must run at lower latency/cost than a large prompted model | Fine-tuned 7B replaces prompted 70B |

**Gates before starting:**
- [ ] Prompting + few-shot genuinely exhausted (documented failures)
- [ ] RAG evaluated and does not solve the problem
- [ ] At least 100 high-quality, human-reviewed input/output examples available
- [ ] Clear input/output contract defined
- [ ] Eval set of 50+ held-out examples prepared

**What this fixes:** Behavior, format, vocabulary, latency/cost via smaller model.

**What this does NOT fix:** Knowledge the base model lacks. Fine-tuning amplifies existing capability; it does not create new capability.

---

## Rung 5: Train from Scratch

**When to apply:** Almost never for a practitioner.

**Genuine triggers:**
- Completely novel domain with no pretrained overlap (new language family, new modality)
- Capability that no existing model has at any scale
- Regulatory requirement that no external model weights can be used

**Reality check:** If GPT-4, Claude, Llama, Mistral, and Qwen all fail at the task even with fine-tuning, you may have a genuine from-scratch case. In practice, this is research-team territory, not product-team territory.

---

## Common Mistakes

| Mistake | Correct action |
|---------|----------------|
| Fine-tuning to add knowledge (FAQ content, product docs) | Use RAG |
| Fine-tuning with under 100 examples | Try few-shot prompting first |
| Fine-tuning before trying few-shot | Add examples to the prompt first |
| Fine-tuning to fix a reasoning failure | Fine-tuning amplifies, not repairs. Use a more capable base model. |
| Treating "we have data" as "we should fine-tune" | Ask: is the data curated, consistent, and in input/output format? |
| Fine-tuning as a moat | The moat is the dataset, not the fine-tune. The dataset is the competitive advantage. |

---

## Decision Flowchart

```
Problem defined
    |
    v
Try better system prompt --> Works? --> Ship it
    |
    | (still fails)
    v
Add 5-20 few-shot examples --> Works? --> Ship it
    |
    | (still fails)
    v
Is it a knowledge gap? --> YES --> Use RAG --> Works? --> Ship it
    |                                              |
    | NO                                           | (still fails after RAG)
    v                                              v
Is it a behavior gap                        Fine-tune on behavior gap
with 100+ examples?    --> YES ---------->  AFTER RAG is in place
    |
    | NO (insufficient examples or unclear contract)
    v
Revisit problem definition.
You may be trying to solve two problems at once.
```

---

## Quick Reference Card

| Problem type | Right tool | Wrong tool |
|---|---|---|
| "Model doesn't know X" | RAG | Fine-tune |
| "Model says wrong things confidently" | RAG + grounding prompt | Fine-tune |
| "Output format is inconsistent" | Few-shot, then fine-tune | RAG |
| "Wrong brand voice" | System prompt, then fine-tune | RAG |
| "Misuses medical/legal terms" | RAG (term glossary) + fine-tune | Bigger model alone |
| "Too slow / too expensive at scale" | Fine-tune a smaller model | More prompting |
| "Can't answer complex reasoning" | Better base model | Fine-tune |
