# Load Testing LLM APIs

> Run the test before the traffic does. Production load tests are called incidents.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 07 Lessons 01-09 (observability, routing), Phase 06 (shipping basics)
**Time:** ~45 min
**Learning Objectives:**
- Explain why standard HTTP load testing tools need adapting for LLM APIs
- Implement an asyncio load test runner that collects TTFT, total latency, error rate, and cost
- Interpret a load test summary report to identify bottlenecks
- Use locust for a realistic ramp-up scenario
- Understand the cost-safety protocol for load testing against real APIs

---

## The Problem

Your team ships a new AI feature. Traffic ramps up post-launch. At 50 concurrent users, response times jump from 2s to 18s and some requests start returning 429 errors. The on-call engineer has never seen this failure mode.

Standard HTTP load testers like k6 or wrk will tell you requests/sec and error rate. But LLM APIs have three properties that make standard load testing misleading:

First, response times are variable by 10-100x depending on output length. A 50-token response takes 1s; a 2,000-token response takes 20s. Treating these as the same "request" in a p99 measurement hides the actual latency distribution.

Second, streaming responses mean time-to-first-token (TTFT) is a distinct metric from total latency. Users perceive TTFT as responsiveness. A 500ms TTFT with a 15s total is a very different experience from a 5s TTFT with an 8s total.

Third, rate limits interact with concurrency in non-obvious ways. The Anthropic API enforces limits on tokens-per-minute, not just requests-per-minute. A burst of long-context requests can hit the token limit before the request limit.

You need a load test that measures the right things and does not bankrupt you in the process.

---

## The Concept

### Concurrent Request Timing

```
Time (seconds) -->

req-01  |====QUEUE===|=TTFT=|=========STREAM=========|  done at t=12
req-02  |====QUEUE===|=TTFT=|======STREAM======|        done at t=9
req-03  |====QUEUE===|==TTFT==|============STREAM============|  done at t=16
req-04            |=QUEUE=|=TTFT=|====STREAM====|            done at t=11
req-05            |=QUEUE=|==TTFT==|=========STREAM=========| done at t=15

         ^ concurrency starts here
                     ^ first token for each request (TTFT = queue + model startup)
                                   ^ streaming output (cost of output tokens)

Rate limit window (1 minute):
[####################] 40% token budget used by req-01..05
[########] 20% more from req-06..10
[##############################] Rate limit hit at req-17 -> 429
```

Key observations:
- TTFT is what the user sees first. It includes network time, queuing at the API, and model initialization.
- Total latency = TTFT + streaming time. Streaming time depends on output length.
- Rate limit hits are invisible until they happen. Run the test in phases: 10 req, then 25, then 50.

### What to Measure

| Metric | Why it matters | How to collect |
|--------|---------------|----------------|
| TTFT p50/p95 | User-perceived responsiveness | Timestamp at first chunk |
| Total latency p50/p95 | End-to-end wait time | Timestamp at last chunk |
| Error rate | Rate limit and server errors | Count non-200 responses |
| Requests/sec throughput | Sustainable concurrency level | Total req / test duration |
| Estimated cost | Budget impact of this traffic | Sum input+output tokens x price |

---

## Build It

Install dependencies:

```bash
pip install anthropic httpx
```

The `LLMLoadTester` class fires N concurrent requests, collects TTFT and total latency for each, and prints a summary report. It targets a mock server by default so you can validate the test harness before spending money.

```python
import asyncio
from load_tester import LLMLoadTester, LoadTestConfig

config = LoadTestConfig(
    concurrency=10,
    total_requests=50,
    prompt="Explain the tradeoffs between synchronous and asynchronous Python in 100 words.",
    max_tokens=150,
    use_mock=True,   # set False to hit the real Anthropic API
)

async def run():
    tester = LLMLoadTester(config)
    report = await tester.run()
    report.print_summary()

asyncio.run(run())
```

Expected output (mock mode):

```
LLM Load Test Report
====================
Config: 50 requests, concurrency=10, mock=True
Duration: 2.3s  |  Throughput: 21.7 req/s

Latency (TTFT)
  p50:    45ms
  p95:    89ms
  p99:   112ms

Latency (Total)
  p50:   210ms
  p95:   388ms
  p99:   451ms

Errors
  Total:      0  (0.0%)
  Timeouts:   0
  Rate limits: 0

Cost estimate (real API)
  Input tokens:  ~3,000
  Output tokens: ~7,500
  Est. cost:     $0.011 (haiku pricing)
```

> **Real-world check:** Why run against a mock server first? Because the load test harness itself has bugs on first write. If you run 500 requests against the real API to discover that your concurrency logic has a deadlock, you just spent $5 to find a bug you could have found for free. The mock validates your measurement code, your error handling, and your concurrency model. Only run against the real API once the mock run produces clean results.

Run in mock mode:

```bash
python code/main.py --mock --concurrency 10 --requests 50
```

Then run a small real test (validates actual latency numbers):

```bash
ANTHROPIC_API_KEY=your_key python code/main.py --concurrency 5 --requests 20
```

---

## Use It

Locust provides a web UI, ramp-up curves, and distributed load generation when you outgrow the async runner:

```python
from locust import HttpUser, task, between
import json

class LLMUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def query(self):
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": "Summarize AI in one sentence."}],
            "max_tokens": 100,
        }
        headers = {"x-api-key": self.environment.host}
        with self.client.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={"anthropic-version": "2023-06-01", **headers},
            catch_response=True,
            name="llm_query",
        ) as resp:
            if resp.status_code == 429:
                resp.failure("rate_limited")
            elif resp.status_code != 200:
                resp.failure(f"http_{resp.status_code}")
```

Run with: `locust -f locustfile.py --users 20 --spawn-rate 2 --run-time 60s --headless`

> **Perspective shift:** Locust's ramp-up (spawn-rate) is the most important parameter for LLM load tests, not peak concurrency. Starting 20 users simultaneously hits the API before it has warmed up any connection pools or pre-allocated any context. Ramping up 2 users per second gives you a realistic picture of what happens as traffic grows and lets you identify the concurrency level where rate limits start appearing, rather than just the level where everything is already broken.

---

## Ship It

The artifact for this lesson is `outputs/skill-llm-load-test.md`: a load test runner script and locust configuration you can copy into any service to validate LLM API capacity before a launch or traffic spike.

---

## Evaluate It

**Baseline before you need it:** Run the load test at 10, 25, and 50 concurrency before your launch. Record p95 TTFT and total latency at each level. This is your performance baseline.

**Rate limit discovery:** Increase concurrency until you see your first 429. The concurrency level just below that threshold is your safe operating limit. Set your auto-scaling triggers at 70% of that limit.

**Cost per test run:** The small real-API test (20 requests at concurrency 5) should cost under $0.01 with Haiku. If it costs more, check that `max_tokens` is set conservatively. Run the large test (concurrency 50, 200 requests) only when validating for a high-traffic launch, and budget for it explicitly.

**Alert thresholds:** Set an alert if p95 TTFT exceeds 3x your baseline. A sudden latency spike at the same traffic level usually means the API provider is having an incident, not that your code changed.
