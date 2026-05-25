---
name: skill-agent-governor
description: AgentGovernor class with five stopping mechanisms for production agent loops
version: "1.0"
phase: "04"
lesson: "11"
tags: [agents, cost-control, safety, stopping-conditions, production]
---

# Agent Governor

## Default Thresholds

Adjust these for your workload. The defaults are conservative starting points.

```python
@dataclass
class GovernorConfig:
    max_iterations: int = 20
    max_tokens: int = 50_000           # total input + output tokens
    max_seconds: float = 120.0         # wall-clock timeout
    token_budget_usd: float = 0.50     # cost ceiling
    soft_stop_every_n: int = 5         # soft stop check frequency
    input_token_price: float = 0.001 / 1000   # $ per input token (Haiku)
    output_token_price: float = 0.005 / 1000  # $ per output token (Haiku)
```

## Minimal Integration

```python
governor = AgentGovernor(config)

while governor.should_continue():
    if governor.should_soft_stop(context_summary, client):
        break

    response = client.messages.create(...)
    governor.record_usage(response.usage.input_tokens, response.usage.output_tokens)
    print(governor.status())  # log each iteration

    # ... handle response ...
```

## Kill Switch (multi-threaded)

```python
governor = AgentGovernor(config)

# In background thread or signal handler:
governor.kill()

# Loop stops at next iteration boundary with stop_reason == "kill_switch"
```

## Kill Switch (async)

```python
try:
    result = await asyncio.wait_for(
        async_agent_loop(task, client),
        timeout=30.0
    )
except asyncio.TimeoutError:
    task.cancel()
    # Handle asyncio.CancelledError inside the loop
```

## Five Checks in Order

| # | Check | Triggered by | Stop reason |
|---|-------|-------------|-------------|
| 1 | Kill switch | `governor.kill()` from any thread | `kill_switch` |
| 2 | Max iterations | `iterations >= max_iterations` | `max_iterations (N)` |
| 3 | Token ceiling | `total_tokens >= max_tokens` | `max_tokens (N)` |
| 4 | Cost budget | `cost_usd >= token_budget_usd` | `token_budget_usd ($N)` |
| 5 | Timeout | `elapsed >= max_seconds` | `timeout (Ns)` |

Soft stop is separate and checked between the hard stops and the iteration body.

## Choosing Thresholds

| Task type | max_iterations | token_budget_usd | max_seconds |
|-----------|---------------|-----------------|-------------|
| Simple Q&A | 5 | $0.05 | 30 |
| Research (3-5 sources) | 15 | $0.25 | 90 |
| Research (10+ sources) | 30 | $1.00 | 300 |
| Long-running background | 100 | $5.00 | 1800 |

## Evaluation Checklist

- [ ] Loop stops exactly at max_iterations, never one over
- [ ] Cost check fires before loop body when budget is exceeded
- [ ] Kill switch stops loop within one iteration boundary (not immediately)
- [ ] Soft stop returns YES on clearly-complete contexts at least 8/10 times
- [ ] GovernorState.stop_reason is always set when the loop exits
- [ ] Partial output is returned on non-completion stops (not silent failure)
