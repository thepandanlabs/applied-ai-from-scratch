---
name: skill-moderation-refusal-policy
description: Reusable moderation policy template with three-tier decisions, category definitions, refusal message patterns, and threshold calibration guide
version: "1.0"
phase: "08"
lesson: "09"
tags: [moderation, refusal, safety, content-policy, guardrails]
---

# Moderation and Refusal Policy Template

A drop-in moderation layer for any AI service. Copy, configure categories, and plug into your request pipeline.

---

## Decision Tiers

| Tier | Action | LLM called? | When to use |
|------|--------|------------|-------------|
| HARD_BLOCK | Return refusal, no LLM call | No | Clear harm, no legitimate use |
| SOFT_BLOCK | Call LLM with safety qualifier, prepend note | Yes | Sensitive but answerable with care |
| ALLOW | Call LLM normally | Yes | Everything else (the default) |

---

## Category Template

```python
CategoryConfig(
    name="your-category",
    keywords=["phrase one", "phrase two"],   # replace with classifier in prod
    threshold=0.0,                           # 0.0 = any match; raise for classifiers
    decision=Decision.HARD_BLOCK,            # or SOFT_BLOCK
    refusal_template=(
        "One sentence. Direct. No preamble. No apology."
    ),
    alternative=(
        "What I CAN help with instead."
    ),
)
```

---

## Starter Category Set

### Violence (HARD_BLOCK)
- Keywords: "how to hurt", "how to kill", "instructions to harm"
- Template: "I can't help with that. Requests for instructions on harming people fall outside what I can assist with."
- Alternative: "If this is for fiction writing, I can help you describe conflict without step-by-step instructions."

### Self-Harm (HARD_BLOCK)
- Keywords: "how to self harm", "suicide method", "ways to end my life"
- Template: "I'm not able to provide that information. If you're struggling, please reach out to a crisis line (988 in the US)."
- Alternative: "I can help you find mental health resources."

### PII Harvesting (HARD_BLOCK)
- Keywords: "find their phone number", "look up their ssn", "get their address"
- Template: "I can't help locate or retrieve personal information about individuals."
- Alternative: "I can explain what public records are legitimately available."

### Competitive Attacks (SOFT_BLOCK)
- Keywords: "write a fake review", "spam their reviews", "defamatory content"
- Template: "I can help with competitive analysis, but not fake reviews or defamatory content."
- Alternative: "I can help you write honest feedback or improve your own positioning."

### Politically Divisive (SOFT_BLOCK)
- Keywords: "which party should i vote", "is abortion right or wrong", "best religion"
- Template: "This touches on a topic where I try not to push a particular view. I can present multiple perspectives."
- Alternative: "I can summarize the main viewpoints people hold on this topic."

---

## Refusal Message Rules

1. Never reveal which keyword or rule triggered the block.
2. Never use "As an AI..." preamble. One direct sentence.
3. Always offer an alternative action.
4. For HARD_BLOCK: do not call the LLM at all.
5. For SOFT_BLOCK: modify the system prompt, not the user message.

---

## Calibration Guide

### Finding your false positive rate

```python
# Write 20 prompts representing normal user behavior
normal_prompts = [
    "How do I kill a background process in bash?",
    "What's a lethal dose of caffeine? (writing a thriller)",
    "Explain the political history of Roe v. Wade",
    # ... more
]

policy = ModerationPolicy()
false_positives = [
    p for p in normal_prompts
    if policy.evaluate(p).decision != Decision.ALLOW
]
fpr = len(false_positives) / len(normal_prompts)
print(f"False positive rate: {fpr:.1%}")
# Target: below 5% for general assistants
# Target: below 1% for developer tools
```

### Threshold tuning with a classifier

When you replace keywords with a classifier score, use the `threshold` field:

```python
# Aggressive: block at 60% confidence (higher recall, more false positives)
CategoryConfig(name="violence", threshold=0.6, ...)

# Conservative: block at 90% confidence (lower recall, fewer false positives)
CategoryConfig(name="violence", threshold=0.9, ...)
```

Start conservative (threshold=0.9). Reduce only if you confirm missed blocks in production logs.

### Updating the blocklist

1. Review false-negative reports (blocked when shouldn't be) weekly.
2. Review missed-block incidents immediately when reported.
3. Add new keywords from production logs, not assumptions.
4. Test every keyword addition against 20 normal prompts before shipping.
5. Version your category configs in git. Every change should have a rationale comment.

---

## Integration Pattern

```python
# Drop into any FastAPI route
from moderation import ModerationPolicy, guarded_completion

policy = ModerationPolicy()

@app.post("/chat")
async def chat(request: ChatRequest):
    result = guarded_completion(
        user_input=request.message,
        policy=policy,
        system_prompt=YOUR_SYSTEM_PROMPT,
    )
    return {
        "response": result["response"],
        "moderated": result["decision"] != "allow",
    }
```

Do not expose `result["category"]` or `result["decision"]` to end users. These are internal signals for logging and dashboards, not user-facing fields.
