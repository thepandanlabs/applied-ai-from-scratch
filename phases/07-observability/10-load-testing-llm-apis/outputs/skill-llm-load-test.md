---
name: skill-llm-load-test
description: Asyncio load test runner that measures TTFT, total latency, error rate, and estimated cost for LLM API endpoints
version: "1.0"
phase: "07"
lesson: "10"
tags: [load-testing, performance, ttft, latency, rate-limits]
---

# LLM Load Test Runner

An asyncio-based load test runner built specifically for LLM APIs. Measures time-to-first-token (TTFT), total latency, error distribution, and estimated cost. Runs against a mock server by default so you can validate the harness before spending money.

## Protocol

1. Run mock first (`--mock`). Verify the output format and concurrency logic.
2. Run small real test: `--no-mock --concurrency 5 --requests 20`. Gets real latency numbers.
3. Run ramp test: 10, 25, 50 concurrency. Find the rate-limit threshold.
4. Record baseline. Set SLO thresholds based on p95 at your expected peak concurrency.

## Usage

```bash
# Validate harness (free)
python main.py --mock --concurrency 10 --requests 50

# Small real test (~$0.005)
ANTHROPIC_API_KEY=sk-ant-... python main.py --no-mock --concurrency 5 --requests 20

# Ramp test to find rate limit (~$0.05)
ANTHROPIC_API_KEY=sk-ant-... python main.py --no-mock --concurrency 25 --requests 100
```

## Key metrics

| Metric | Healthy target | Alert threshold |
|--------|---------------|-----------------|
| TTFT p50 | < 500ms | > 1500ms |
| TTFT p95 | < 1500ms | > 3000ms |
| Total latency p95 | < 8000ms | > 20000ms |
| Error rate | < 0.5% | > 2% |
| Rate limit rate | 0% | > 0.1% |

## Locust integration

For ramp-up testing with a web UI, copy `locustfile.py` from the lesson code directory and run:

```bash
locust -f locustfile.py --users 50 --spawn-rate 2 --run-time 120s --headless \
  -H https://api.anthropic.com
```

The spawn-rate of 2 users/second gives you a 25-second ramp to 50 users, which is realistic for traffic growth patterns.

## Cost controls

- Always set `max_tokens` to the minimum acceptable for your use case during load tests
- Use `--mock` for all harness development and CI validation
- Keep real API tests under 200 requests unless explicitly validating for a high-traffic launch
- Run real tests against `claude-3-5-haiku-20241022` to minimize test cost; latency patterns transfer to other models
