---
name: skill-model-router
description: Rule-based ModelRouter that routes LLM requests to the cheapest model able to handle the task, with cost tracking and structured routing reasons
version: "1.0"
phase: "07"
lesson: "09"
tags: [routing, cost-optimization, llm-gateway, model-selection]
---

# Model Router

A drop-in `ModelRouter` class that routes each request to the cheapest model capable of handling it. Rules are evaluated in priority order: explicit complexity flag, context length, cost budget, prompt size. The router returns a `(model_id, reason)` tuple you log alongside every LLM call.

## When to use

- You are serving a mixed-complexity traffic pattern (Q&A + summarization + reasoning) and defaulting all calls to the most capable model
- Your monthly LLM spend is growing faster than your user count
- You need an audit trail explaining why each request went to a given model

## Configuration

```python
from model_router import ModelRouter

router = ModelRouter(
    default_budget=0.01,           # Max USD per call before forcing Haiku
    default_model="claude-3-5-haiku-20241022",
)
```

Tune `token_threshold` on `LargeContextRule` and `MediumPromptRule` based on your traffic distribution. Start with the defaults; adjust after one week of data.

## Integration

```python
model, reason = router.route(
    prompt=full_prompt,        # system + user concatenated for length estimation
    complexity=task_complexity,  # None or "high"
    cost_budget=per_call_budget, # None to use router default
)

# Log the routing decision with every LLM call
response = anthropic_client.messages.create(
    model=model,
    messages=[{"role": "user", "content": user_prompt}],
    max_tokens=500,
)
logger.info("llm_call", model=model, routing_reason=reason, tokens=response.usage.input_tokens)
```

## Routing rules (in priority order)

| Priority | Rule | Condition | Model |
|----------|------|-----------|-------|
| 1 | explicit_complexity | complexity == "high" | claude-sonnet-4-5 |
| 2 | large_context | prompt_tokens > 6000 | claude-sonnet-4-5 |
| 3 | budget_constraint | cost_budget tight | claude-3-5-haiku-20241022 |
| 4 | medium_prompt | prompt_tokens > 1500 | claude-sonnet-4-5 |
| 5 | default | no rule matched | claude-3-5-haiku-20241022 |

## Cost model

```python
MODEL_COSTS = {
    "claude-3-5-haiku-20241022": 0.000001,  # $1/M input tokens
    "claude-sonnet-4-5":        0.000003,  # $3/M input tokens
}
```

Update when Anthropic adjusts pricing. The router uses these for cost estimates and budget enforcement, not for billing.

## Monitoring

Log `routing_reason` on every LLM call. Build a dashboard with:
- Distribution of routing_reason values (tells you if rules are firing as expected)
- Cost per routing_reason bucket (shows actual savings)
- Requests routed to Sonnet as a fraction of total (alert if exceeds 40%)
