---
name: skill-consumption-limits
description: ConsumptionGuard configuration template with recommended limits by use case and cost-impact calculator for LLM API services
version: "1.0"
phase: "08"
lesson: "10"
tags: [consumption, rate-limiting, cost, dos, guardrails, owasp-llm10]
---

# Consumption Limits Configuration Template

Drop-in limits configuration for any LLM API service. Copy the profile matching your use case, adjust to your model's pricing, and plug `ConsumptionGuard` into your request pipeline.

---

## Recommended Limits by Use Case

### Consumer Chatbot (public-facing)

```python
guard = ConsumptionGuard(
    input_token_limit=2_000,      # ~1,500 words. Blocks massive pastes.
    max_output_tokens=512,         # Short answers. Upgrade for long-form products.
    rate_limit_rpm=5,              # 5 requests/minute per user. Stops burst attacks.
    session_cost_cap=0.25,         # $0.25 per session. One abusive session = $0.25 max.
    loop_iteration_limit=0,        # No agent loops in basic chatbots.
)
```

### Developer Tools (authenticated engineers)

```python
guard = ConsumptionGuard(
    input_token_limit=8_000,       # Supports pasting code files.
    max_output_tokens=2_048,       # Code generation needs longer outputs.
    rate_limit_rpm=30,             # Engineers iterate fast.
    session_cost_cap=2.00,         # $2 per session. Budget for deep work.
    loop_iteration_limit=20,       # Agents for multi-step tasks.
)
```

### Internal Tool (company employees only)

```python
guard = ConsumptionGuard(
    input_token_limit=16_000,      # Large documents, reports, datasets.
    max_output_tokens=4_096,       # Long reports, summaries.
    rate_limit_rpm=60,             # Power users need headroom.
    session_cost_cap=10.00,        # $10 per session. Monitor for anomalies.
    loop_iteration_limit=50,       # Complex research agents.
)
```

---

## Cost-Impact Calculator

```python
# Plug in your model's pricing (check provider docs for current rates)
COST_PER_INPUT_TOKEN_M = 0.80   # $ per million input tokens (haiku)
COST_PER_OUTPUT_TOKEN_M = 4.00  # $ per million output tokens (haiku)

def worst_case_cost_per_request(
    input_token_limit: int,
    max_output_tokens: int,
) -> float:
    input_cost = (input_token_limit / 1_000_000) * COST_PER_INPUT_TOKEN_M
    output_cost = (max_output_tokens / 1_000_000) * COST_PER_OUTPUT_TOKEN_M
    return input_cost + output_cost

def worst_case_hourly_cost(
    input_token_limit: int,
    max_output_tokens: int,
    rate_limit_rpm: int,
    concurrent_users: int = 1,
) -> float:
    per_request = worst_case_cost_per_request(input_token_limit, max_output_tokens)
    requests_per_hour = rate_limit_rpm * 60 * concurrent_users
    return per_request * requests_per_hour

# Example: consumer chatbot with 1,000 simultaneous abusive users
hourly = worst_case_hourly_cost(2_000, 512, 5, concurrent_users=1_000)
print(f"Worst-case hourly cost: ${hourly:.2f}")
```

---

## Five Limits Reference

| Limit | Parameter | What it stops | Check timing |
|-------|-----------|--------------|-------------|
| Input token limit | `input_token_limit` | 100k-token document pastes | Pre-call |
| Output token cap | `max_output_tokens` | Model generating 50k-token responses | In API call |
| Per-user rate limit | `rate_limit_rpm` | Burst attacks, parallel request floods | Pre-call |
| Session cost cap | `session_cost_cap` | Session cost drain, zombie sessions | Pre-call |
| Agent loop limit | `loop_iteration_limit` | Runaway agent loops, stuck tasks | Pre-call (per iteration) |

All five must be configured. Leaving any one out creates an exploitable gap.

---

## Production Notes

### Replace in-memory state with Redis for multi-worker deployments

```python
import redis

class RedisConsumptionGuard(ConsumptionGuard):
    def __init__(self, redis_url: str, **kwargs):
        super().__init__(**kwargs)
        self.redis = redis.from_url(redis_url)

    def check_rate_limit(self, user_id: str) -> GuardResult:
        key = f"rate:{user_id}"
        pipe = self.redis.pipeline()
        now = time.time()
        window_start = now - 60.0

        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, 120)
        _, count, _, _ = pipe.execute()

        if count >= self.rate_limit_rpm:
            return GuardResult(
                allowed=False,
                error=LimitExceeded(
                    limit_type="rate",
                    value=count,
                    limit=self.rate_limit_rpm,
                    message=f"Rate limit exceeded. Retry in 60 seconds.",
                ),
            )
        return GuardResult(allowed=True)
```

### Alerting thresholds

Set up alerts when:
- Any user hits the cost cap more than 3 times in a day (potential probe attack)
- Any session hits the iteration limit (may indicate a stuck agent or adversarial input)
- Rate limit violations exceed 1% of total requests (possible coordinated attack)
- Total hourly spend exceeds 2x your expected baseline

### Limit tuning process

1. Deploy with conservative limits (consumer profile above).
2. Monitor false-positive rate: legitimate users hitting limits.
3. If false positives exceed 1% of requests, raise the affected limit by 25%.
4. Re-check the cost impact calculator after each increase.
5. Never raise a limit without recalculating the worst-case hourly cost.
