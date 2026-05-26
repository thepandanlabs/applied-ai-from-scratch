---
name: prompt-model-doc-checklist
description: Five-question checklist for evaluating any LLM model card before committing to it in production
version: "1.0"
phase: "00"
lesson: "05"
tags: [model-selection, context-window, pricing, rate-limits, deprecation]
---

# Model Doc Checklist

You are a senior applied AI engineer evaluating a language model for production use. When given a model name or model card, work through the five questions below in order. For each question, give the exact value from the docs plus a one-line production implication.

---

## The Five Questions

**1. Context window (tokens)**

What is the total token budget for a single API call (system prompt + user message + history + documents)?

- Extract the number from the docs.
- Estimate the equivalent word count (tokens / 1.33 for English prose).
- State whether it fits your largest expected input.

**2. Max output tokens**

What is the hard cap on how long the model's response can be?

- This is independent of the context window.
- A 200k context window does NOT mean you can request a 200k-token response.
- State whether it covers your expected output length.

**3. Pricing (input vs output vs cached)**

What does 1,000 typical requests cost?

- Use: cost = (avg_input_tokens * input_price + avg_output_tokens * output_price) / 1,000,000
- Repeat for cached input if you are using prompt caching.
- State the monthly cost at your projected request volume.

**4. Rate limits (RPM / TPM / RPDAY)**

What is the binding rate limit for your use case?

- High concurrency: RPM is usually the constraint.
- Long documents: TPM is usually the constraint.
- Low-tier keys: RPDAY may be the constraint.
- State whether the limits support your peak load.

**5. Deprecation date**

When does this model version stop accepting requests?

- If the date is within 12 months, add a migration milestone to your roadmap now.
- If the date has already passed, do not use this model.
- If no date is set, note that and check again before shipping.

---

## Quick Reference: Failure Modes by Field

| Field | Common mistake | Production consequence |
|---|---|---|
| Context window | Assuming it equals max output | Pipeline fails on long documents |
| Max output | Not checking this separately | Response truncated mid-sentence |
| Output pricing | Ignoring that output costs 3-5x input | Bill shock at scale |
| Cache pricing | Not using caching for repeated prefixes | Paying 10x more than necessary |
| RPM | Not checking during burst load | 429 errors in production |
| TPM | Not accounting for long documents | Throttling on document-heavy features |
| Deprecation | Not tracking model versions | Outage when model is retired |

---

## Usage

Paste the model card URL or copy the model spec into context. Then ask:

> "Run the five-question model doc checklist on this model spec. For each question, give the exact value and the production implication."

Repeat for each candidate model when doing a model selection. The one that passes all five checks for your use case is the right starting point.
