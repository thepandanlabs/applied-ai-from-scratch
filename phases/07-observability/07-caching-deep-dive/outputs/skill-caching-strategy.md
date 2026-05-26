---
name: skill-caching-strategy
description: Two-tier LLM caching strategy combining Anthropic prompt caching and semantic caching to reduce tokens and round-trips
version: "1.0"
phase: "07"
lesson: "07"
tags: [caching, prompt-caching, semantic-cache, cost, observability]
---

# Skill: LLM Caching Strategy

## Purpose

You are an applied AI engineering advisor. When a user wants to reduce LLM API costs or latency through caching, use this skill to select the right caching layer and implement it correctly.

---

## Which Cache Do You Need?

```
+---------------------------+------------------------+------------------------------+
| Symptom                   | Root Cause             | Fix                          |
+---------------------------+------------------------+------------------------------+
| High input token cost     | Long static prefix     | Prompt/prefix caching        |
| (same system prompt       | sent on every call     | (cache_control breakpoint)   |
| on every call)            |                        |                              |
+---------------------------+------------------------+------------------------------+
| High call volume for      | Same question asked    | Semantic caching             |
| FAQ-style queries         | many ways, same answer | (embedding + similarity)     |
+---------------------------+------------------------+------------------------------+
| Both problems             | Both                   | Two-tier: semantic first,    |
|                           |                        | then model with prompt cache |
+---------------------------+------------------------+------------------------------+
```

---

## Prompt Caching Quick Reference

**Minimum token threshold for caching:** 1,024 tokens (Anthropic requirement)

**Cost model:**
- Cache write: 125% of normal input token cost (first call or after TTL expiry)
- Cache read: 10% of normal input token cost (subsequent calls within TTL)
- TTL: 5 minutes (refreshed on each cache hit)

**Break-even:** cache becomes profitable at call 3 (1 write + 2 reads saves vs 3 uncached)

**Implementation:**
```python
system=[{
    "type": "text",
    "text": your_long_system_prompt,
    "cache_control": {"type": "ephemeral"},
}]
```

**Rules for a cache hit:**
1. Cached content must be at the start of messages array or in system block
2. Content must be byte-identical up to the breakpoint
3. Model must be the same
4. Call must happen within 5 minutes of the last hit/write

---

## Semantic Caching Quick Reference

**Threshold selection:**
- 0.95+: very conservative, low false-positive risk, low hit rate
- 0.90-0.93: good balance for FAQ content (start here)
- 0.85-0.89: higher hit rate but risk of returning wrong answers

**Validation before production:**
1. Collect 50+ labeled query pairs (query A, query B, should_use_same_answer: bool)
2. Plot score distribution for positive pairs (should share answer) and negative pairs
3. Pick the threshold at the 95th percentile of negative pair scores
4. Test that threshold on a held-out set before deploying

**Invalidation strategy:**
- Use TTL for content that changes (e.g., product details: 1-hour TTL)
- Flush specific cache entries on content updates (track query-to-content mapping)
- For static content (FAQs that rarely change): TTL of 24 hours or no TTL

---

## Operational Metrics to Track

| Metric | Target | Alert If |
|---|---|---|
| Prompt cache hit rate | > 80% for warm workloads | < 50% (TTL too short or prefix changing) |
| Semantic cache hit rate | 20-60% for FAQ workloads | > 70% (threshold may be too low) |
| Cache-attributable savings | > 30% of input token cost | < 10% (consider disabling if maintenance > savings) |
| Semantic cache false positive rate | < 1% | > 2% (lower threshold or improve labeling) |

---

## Common Mistakes

**Placing cache_control in the middle of messages**: Cache hits require byte-identical content from the start of the prefix. Anything after the breakpoint is uncached. Put long static content (docs, examples) before dynamic content (user message).

**Using semantic caching without a labeled test set**: A threshold that looks fine on 10 examples may fail on edge cases. Always validate on 50+ labeled pairs before shipping.

**Caching personalized responses**: Semantic caching assumes the answer to a query is the same regardless of user. If your system includes user-specific context (account data, history) in the prompt, the cached answer may be correct for one user but wrong for another. Cache only queries where the answer is user-agnostic.

**Not tracking cache hit rates**: You cannot tell if your cache is working without measuring it. Log `cache_read_input_tokens` (prompt caching) and semantic cache stats on every call.
