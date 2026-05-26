---
marp: true
theme: applied-ai
class: title
paginate: true
footer: 'Applied AI From Scratch · Phase 07'
---

# Phase 07: Observability, Cost & Reliability
## See what's happening, know what it costs, prove it works

Phase 07 of 13 · 13 lessons · ~14 hours

<!-- SPEAKER: Welcome to Phase 07. In Phase 06 we shipped it. Now we have to see it. A 200 OK with a hallucinated answer looks identical to a correct one at the HTTP layer. This phase gives you the instrumentation to know the difference. Time: ~5 min -->

---

## Who this is for

You are a **working software engineer** who:

- Has an AI service running in production (or about to ship one)
- Cannot tell whether it's working well, degrading, or burning money
- Wants a full observability stack: traces, cost dashboards, SLO alerts

**What you will NOT get:**
- Generic APM tutorials rebranded as "AI observability"
- Vendor lock-in: everything exports to open standards
- Theory without code: every concept ships a working instrument

<!-- SPEAKER: Anchor the gap. They have a service. They cannot see inside it at the semantic layer. That is the single problem this phase solves. -->

---

## Prerequisites

- Phase 06: Shipping (FastAPI service, Docker, retries)
- Basic Python: decorators, context managers, dataclasses
- Familiarity with any tracing tool (even just reading logs counts)

**Tools introduced:**
- OpenTelemetry Python SDK (`opentelemetry-sdk`, `opentelemetry-exporter-otlp`)
- Langfuse (hosted or self-hosted)
- Phoenix (local, open-source)
- LiteLLM (model gateway)
- Locust (load testing)

<!-- SPEAKER: If anyone has not done Phase 06, they can still follow along. The patterns are standalone. Point out the two backend choices: Langfuse for teams, Phoenix for local/offline. -->

---

## What you will build

| Artifact | Lesson |
|----------|--------|
| OTel-instrumented model wrapper | 07-02, 07-03 |
| Langfuse + Phoenix trace viewers | 07-03 |
| Structured prompt/response logger | 07-05 |
| Per-request cost calculator | 07-06 |
| Semantic cache with similarity threshold | 07-07 |
| Latency profiler (TTFT + p95) | 07-08 |
| LiteLLM model gateway config | 07-09 |
| Locust load test script | 07-10 |
| SLO burn-rate alert function | 07-11 |
| Chaos injection test suite | 07-12 |
| Capstone: full observability + cost dashboard | 07-13 |

<!-- SPEAKER: Each row is a standalone reusable file. The capstone wires them all together over the Phase 06 service. -->

---

## The through-line: the semantic blind spot

A 200 OK with a hallucinated answer looks identical to a correct one at the HTTP layer.

LLM observability requires capturing what web APM never tracks:

- Token counts (input and output)
- Model version and finish reason
- Prompt content and response content
- Semantic quality of the answer
- Per-request API cost

> **Key insight:** Traditional monitoring tells you the service is up. LLM observability tells you the service is right.

<!-- SPEAKER: This is the single sentence that justifies the entire phase. Write it on the board if facilitating in person. Everything else is implementation of this insight. -->

---

## The full observability stack

<div class="mermaid">
flowchart LR
    A[AI Service] --> B[OTel SDK]
    B --> C[OTLP Exporter]
    C --> D[Langfuse]
    C --> E[Phoenix]
    A --> F[Structured Logger]
    F --> G[Log store]
    A --> H[Cost Tracker]
    H --> I[Cost Dashboard]
    D --> J[Trace viewer]
    D --> K[Quality scores]
    D --> L[SLO alerts]
</div>

<!-- SPEAKER: Walk left to right. The service emits three streams: OTel spans, structured logs, cost events. All three feed different dashboards. This diagram reappears at the capstone fully wired. -->

---
<!-- _class: section -->

# Lesson 01
## Why LLM Observability Differs

---

## L01: The problem

Your AI service returns 200 OK. Latency looks fine. Error rate is zero.

**But:**
- The model confidently cited a paper that does not exist
- It ignored the user's language and replied in English
- It repeated the same sentence three times
- It used the stale prompt you forgot to update

None of these show up in your existing dashboards.

> **Key insight:** A 200 OK proves the HTTP layer worked. It says nothing about whether the answer was correct.

<!-- SPEAKER: Ask: has anyone in the room shipped a bug that looked like a success in their monitoring? Always yes. That is L01. Time: ~3 min -->

---

## L01: Traditional vs LLM observability

```ascii
Traditional web            LLM service
─────────────────────      ─────────────────────────────
HTTP status code           HTTP status + semantic quality
Latency                    Latency + TTFT
Error rate                 Error rate + hallucination rate
Throughput (req/s)         Throughput + token throughput
Cost (infra only)          Cost (infra + per-token API cost)
────────────────────────────────────────────────────────
Missing: model version, prompt content, finish reason,
         input/output token split, quality score
```

<!-- SPEAKER: The right column is everything you need to add. This phase builds each row. -->

---
<!-- _class: section -->

# Lesson 02
## OpenTelemetry GenAI Conventions

---

## L02: The problem

Every observability vendor uses different attribute names.

- Vendor A: `tokens_used`, `model_name`, `prompt_text`
- Vendor B: `llm.token_count`, `llm.model`, `llm.prompt`
- Vendor C: custom schema, no export

Result: you instrument once, then rewrite every time you switch backends.

> **Key insight:** The `gen_ai.*` OTel semantic conventions are the one schema all major backends export to. Write once, export anywhere.

<!-- SPEAKER: This is why standards matter. The audience writes one set of span attributes and Langfuse, Phoenix, and Braintrust all understand it. Time: ~3 min -->

---

## L02: The `gen_ai.*` span attributes

```ascii
Attribute                         Example value
────────────────────────────────  ──────────────────────────────
gen_ai.system                     "anthropic"
gen_ai.request.model              "claude-opus-4-7"
gen_ai.request.max_tokens         512
gen_ai.usage.input_tokens         340
gen_ai.usage.output_tokens        128
gen_ai.response.finish_reason     "end_turn"
gen_ai.response.id                "msg_01XYZ..."
────────────────────────────────────────────────────────────────
Derived (you compute):
  cost = (input * input_price + output * output_price) / 1_000_000
  quality_score = eval result (Phase 05)
```

<!-- SPEAKER: These are the six attributes you must set on every model call span. The derived fields are not in the OTel spec but you add them as custom attributes. -->

---
<!-- _class: section -->

# Lesson 03
## Instrument an App: Raw OTel to Langfuse/Phoenix

---

## L03: The problem

You have a model call. You have no idea how long it takes, how many tokens it uses, or what prompt it received in production.

Adding an OTel span takes seven lines. Most teams never add those seven lines.

<!-- SPEAKER: The friction is low. The return is high. This is the lesson where they actually do it. Time: ~4 min -->

---
<!-- _class: code -->

## L03: Raw OTel span around a model call

```python
from opentelemetry import trace
tracer = trace.get_tracer("ai-service")

def call_model(prompt: str, model: str) -> str:
    with tracer.start_as_current_span("gen_ai.chat") as span:
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.request.model", model)
        response = client.messages.create(
            model=model, max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        span.set_attribute("gen_ai.usage.input_tokens",
                           response.usage.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens",
                           response.usage.output_tokens)
        return response.content[0].text
```

<!-- SPEAKER: Walk line by line. The span name `gen_ai.chat` follows the OTel convention. The attributes are the six from L02. Everything else is the existing model call. Net addition: 7 lines. -->

---
<!-- _class: code -->

## L03: Langfuse `@observe` decorator

```python
from langfuse.decorators import observe, langfuse_context

@observe()
def call_model(prompt: str) -> str:
    langfuse_context.update_current_observation(
        input=prompt,
        model="claude-opus-4-7",
    )
    response = client.messages.create(
        model="claude-opus-4-7", max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )
    langfuse_context.update_current_observation(
        output=response.content[0].text,
        usage={"input": response.usage.input_tokens,
               "output": response.usage.output_tokens}
    )
    return response.content[0].text
```

<!-- SPEAKER: The decorator is more ergonomic for Langfuse-first teams. It handles trace creation, span nesting, and flushing automatically. Phoenix uses a similar pattern but runs locally on port 6006 with no API key. -->

---

## L03: Langfuse vs Phoenix

```ascii
Feature              Langfuse              Phoenix (Arize)
───────────────────  ────────────────────  ──────────────────────
Hosted option        Yes (free tier)       No (local only)
Self-hosted          Yes (Docker)          Yes (pip install)
API key required     Yes                   No
Prompt versioning    Yes                   No
Dataset capture      Yes                   No
Eval scoring         Yes                   Yes
Best for             Teams, prod           Local dev, offline
```

> **Key insight:** Use Phoenix to get started in five minutes. Switch to Langfuse when you need prompt versioning and team access.

<!-- SPEAKER: Neither is wrong. The OTel layer you add in L03 works with both. The switch costs one config line, not a rewrite. -->

---
<!-- _class: section -->

# Lesson 04
## The Trace as the Unit of Debugging

---

## L04: The problem

Something is wrong with a user's request. You have logs. Lots of logs.

But you cannot tell: was it the retrieval step that returned bad chunks? The prompt that truncated context? The model that hallucinated? The output parser that stripped the answer?

A trace answers this in 30 seconds. Logs take 30 minutes.

<!-- SPEAKER: This is a debugging productivity argument. Traces give you a timeline of every span in a request. You can see exactly which span took 4 seconds and what it received. Time: ~3 min -->

---

## L04: A trace is one request end to end

<div class="mermaid">
flowchart LR
    A[Trace: user request] --> B[Span: retrieval 120ms]
    A --> C[Span: gen_ai.chat 2400ms]
    A --> D[Span: output parse 8ms]
    C --> E[Span: tool_call: search 340ms]
    C --> F[Span: tool_call: calculator 22ms]
    B -->|bad chunks| G[Root cause found]
</div>

<!-- SPEAKER: The trace shows the retrieval span returned poor chunks. That is the root cause. Without traces, you are reading flat logs and guessing. The tool calls are child spans of the model span. -->

---

## L04: Good trace vs bad trace

```ascii
Good trace                         Bad trace
────────────────────────────────   ────────────────────────────────
retrieval   120ms  [3 chunks]      retrieval   118ms  [1 chunk]
gen_ai.chat 2200ms [end_turn]      gen_ai.chat 2410ms [end_turn]
output_parse   8ms [ok]            output_parse   9ms [ok]
────────────────────────────────   ────────────────────────────────
Quality score: 0.91                Quality score: 0.31
User feedback: thumbs up           User feedback: thumbs down

Root cause in bad trace: retrieval returned 1 chunk instead of 3.
Prompt had insufficient context. Model hallucinated the missing info.
```

<!-- SPEAKER: The bad trace has the same latency and the same finish reason. Only the chunk count and quality score differ. Without those fields on the span, you cannot find this. -->

---
<!-- _class: section -->

# Lesson 05
## Logging Prompts, Responses, Tool Calls

---

## L05: The problem

A user reports a bug. You open your logs. You see:

```
INFO  2026-05-26 14:32:11  model call complete  latency=2341ms
```

That log tells you nothing about what was sent or what came back.

You need the prompt. You need the response. You need the tool calls. All structured, all queryable.

<!-- SPEAKER: This is the minimum viable log for an AI service. The timestamp and latency are table stakes. The payload is what makes it debuggable. Time: ~3 min -->

---

## L05: What to log and what to skip

```ascii
LOG THIS                           NEVER LOG THIS
────────────────────────────────   ────────────────────────────────
Full system prompt (version hash)  User PII (name, email, DOB)
User message (anonymized)          Credit card numbers in prompts
Response text                      Auth tokens in tool call args
Token counts (input/output)        Passwords, API keys
Model version                      Health data
Tool call name + args              Any field from GDPR "special"
Finish reason                      category list
user_id (opaque, not email)
session_id
```

> **Key insight:** Log the semantic content, not the personal content. Use opaque IDs, not raw PII.

<!-- SPEAKER: Most teams either log nothing or log everything. Both are wrong. This table is the policy. If legal asks, show them this slide. -->

---
<!-- _class: section -->

# Lesson 06
## Cost Engineering: Token Accounting and Dashboards

---

## L06: The problem

Your AI feature launches. Traffic grows by 10x. Your billing grows by 50x.

Nobody set a budget. Nobody built a cost dashboard. The bill arrives before the alert does.

Token costs compound fast: a complex agent with tool calls can spend $0.50 per request. At 10,000 requests per day, that is $5,000 per day.

<!-- SPEAKER: This is the observability failure that gets engineers fired. Cost is not an ops problem. It is an engineering design decision that starts at the model call. Time: ~4 min -->

---
<!-- _class: code -->

## L06: Per-request cost calculation

```python
PRICES = {
    "claude-opus-4-7":          {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5-20251001": {"input":  0.80, "output":  4.00},
}

def request_cost(model: str, input_tok: int, output_tok: int) -> float:
    p = PRICES[model]
    return (input_tok * p["input"] + output_tok * p["output"]) / 1_000_000

# Example: 500 input + 200 output on Haiku
cost = request_cost("claude-haiku-4-5-20251001", 500, 200)
# => $0.000480 per request
# => $0.48 per 1,000 requests
# => $14.40 per 30,000 requests/day
```

<!-- SPEAKER: The math is two multiplications and a division. The insight is doing it per-request, not looking at it monthly. Attach this result to every span as a custom attribute. -->

---

## L06: The cost dashboard you need

```ascii
Daily burn by endpoint
─────────────────────────────────────────────────────
/chat          ████████████████████  $42.10  (68%)
/summarize     ████████              $16.20  (26%)
/classify      ██                     $3.80   (6%)
─────────────────────────────────────────────────────
Total today:   $62.10   Budget: $80.00   Burn: 78%

Cost per 1k requests (7-day rolling)
─────────────────────────────────────
Mon  $0.41   Tue  $0.43   Wed  $0.44
Thu  $0.50 ▲  Fri  $0.48   Sat  $0.39
─────────────────────────────────────
Thu spike: new system prompt added 2x tokens. Rolled back Fri.
```

<!-- SPEAKER: The Thursday spike is a real failure mode: an engineer updated the system prompt and doubled the input tokens. Cost dashboard caught it in hours, not on the next bill. -->

---
<!-- _class: section -->

# Lesson 07
## Caching Deep-Dive: Prompt/Prefix + Semantic

---

## L07: The problem

You are calling the same model with the same system prompt 50,000 times per day.

You are paying for the same input tokens 50,000 times per day.

Two caching strategies cut this. Most teams use neither.

<!-- SPEAKER: This is pure money. Prompt cache hits on Anthropic reduce input token cost by ~90%. Semantic caching adds another layer for repeated user questions. Time: ~4 min -->

---

## L07: Two caching strategies

```ascii
Strategy          How it works                   Savings
──────────────    ─────────────────────────────  ──────────────
Prompt/prefix     Provider caches repeated       ~90% on
cache             prefix (system prompt).        input tokens
                  Send same prefix each call.    Provider-native.

Semantic          Embed the user query.          0-80% depending
cache             Find nearest cached response.  on query repeat
                  Return if similarity > 0.92.   rate. You build it.
──────────────────────────────────────────────────────────────────
Combine both: prefix cache on the system prompt, semantic cache on
the user query. Stack the savings.
```

<!-- SPEAKER: Prefix cache is free: just structure your API call to put the static system prompt first and never change it mid-session. Semantic cache is code you write and maintain. -->

---
<!-- _class: code -->

## L07: Semantic cache implementation

```python
class SemanticCache:
    def __init__(self, threshold=0.92):
        self.entries = []
        self.threshold = threshold

    def get(self, query: str) -> str | None:
        q_emb = embed(query)
        for emb, response in self.entries:
            if cosine_similarity(q_emb, emb) >= self.threshold:
                return response
        return None

    def set(self, query: str, response: str):
        self.entries.append((embed(query), response))
```

> **Key insight:** The threshold is a quality knob. Lower it and you serve more cache hits, but some answers will be wrong for slightly different questions. 0.92 is a conservative starting point.

<!-- SPEAKER: When semantic cache hurts: stale answers (question asked before policy changed), false positives (similar questions with different correct answers). Always add a TTL and a manual invalidation path. -->

---
<!-- _class: section -->

# Lesson 08
## Latency: p50/p95/p99, TTFT, Where Time Goes

---

## L08: The problem

Average latency is 2.1 seconds. Looks fine.

p95 latency is 11 seconds. One in twenty users waits 11 seconds.

You optimized for the wrong metric, shipped, and your top users churned. They were the heavy users who hit the long tail.

<!-- SPEAKER: This is the most common latency mistake. Averages hide the tail. p95 is what your SLO should be written against. TTFT is what users feel. Time: ~4 min -->

---

## L08: Request lifecycle breakdown

```ascii
Request lifecycle
─────────────────────────────────────────────────────
Network in     │▓▓│                           ~20ms
Auth + routing │▓│                            ~10ms
Cache check    │▓│                            ~5ms
Model call     │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│    ~2400ms  TTFT here
Streaming out  │▓▓▓▓▓▓▓▓│                    ~800ms
─────────────────────────────────────────────────────
Total p50      ~3.2s     (p95: ~6s if cache miss)

TTFT = time to first token = when user sees first character
     = network + auth + cache + model KV lookup
     Streaming cuts perceived latency even if total is same.
```

<!-- SPEAKER: Point out: the model call dominates. The only way to cut it is: (1) smaller model, (2) cache hit, (3) streaming. Streaming does not reduce total latency but it transforms the user experience from "wait 3s" to "answer appearing in 0.4s". -->

---

## L08: p50/p95/p99 matter more than average

```ascii
Percentile  Latency   Meaning
──────────  ────────  ──────────────────────────────────────────
p50         2.1s      Half of requests finish in 2.1s or less
p75         3.4s      75% finish in 3.4s or less
p95         6.8s      95% finish in 6.8s (SLO lives here)
p99         14.2s     1 in 100 waits 14 seconds
────────────────────────────────────────────────────────────────
Average     2.6s      Hides the tail entirely

Write SLOs against p95, not average.
Alert when p95 > 3x your p50.
```

<!-- SPEAKER: If you only remember one thing from this lesson: set your SLO on p95, not average. Your worst 5% of users are real users who will churn. -->

---
<!-- _class: section -->

# Lesson 09
## Model Routing and LLM Gateways

---

## L09: The problem

You call one model from fifteen places in your codebase. The model is deprecated. You update fifteen call sites.

Or: you want to route simple classification tasks to a cheap model and complex reasoning to a frontier model. There is no central place to add that logic.

Or: your primary model is down. Requests fail until you manually swap the client.

A gateway solves all three.

<!-- SPEAKER: The gateway is the single most high-leverage infrastructure piece in a production AI service. One line of config changes the routing for the entire system. Time: ~4 min -->

---

## L09: LiteLLM gateway routing

<div class="mermaid">
flowchart LR
    A[App] --> B[LiteLLM Gateway]
    B --> C{Route?}
    C -->|simple task| D[claude-haiku]
    C -->|complex task| E[claude-opus]
    C -->|claude down| F[gpt-4o fallback]
    B --> G[Auth + rate limit]
    B --> H[Cost logger]
    B --> I[Cache check]
</div>

<!-- SPEAKER: The app never knows which model it hits. The gateway handles auth, routing, fallback, cost logging, and cache. Swap models in config, not in code. -->

---
<!-- _class: section -->

# Lesson 10
## Load Testing LLM APIs

---

## L10: The problem

Your service works perfectly for one user.

You launch. Ten users hit it simultaneously. p95 latency goes to 45 seconds. Two requests time out. One user gets a rate limit error with a raw stack trace.

You never load tested. You had no idea what concurrency looked like.

> **Key insight:** LLM APIs are slow and expensive. Load test before launch. Ten concurrent users is a different problem from one.

<!-- SPEAKER: This lesson is short because the failure mode is obvious in hindsight. But almost no one does it before launch. The lesson is: do it. Time: ~3 min -->

---

## L10: What to measure under load

```ascii
Metric                  Healthy      Warning      Critical
──────────────────────  ──────────   ──────────   ──────────
p95 latency             < 5s         5-10s        > 10s
Error rate              < 0.5%       0.5-2%       > 2%
Concurrent users        10           25           50+
Token throughput        stable       degrading    dropping
Rate limit errors       0            1-5/min      > 5/min
────────────────────────────────────────────────────────────
Tool: Locust (Python) or k6 (JS)
Start: 1 user, ramp to 20 over 60s, hold for 120s
```

<!-- SPEAKER: The token throughput row is unique to LLM APIs. The provider has per-minute token limits, not just request limits. You can hit token rate limits before request rate limits. -->

---
<!-- _class: section -->

# Lesson 11
## SLOs, SLIs and Alerting for AI Features

---

## L11: The problem

Your team argues about whether the AI feature is "good enough." No one has defined what good enough means in a number.

A bug report says the AI is "getting worse." You have no baseline to check against.

You get paged at 2am. The alert says "CPU high." The actual problem is quality score degradation. CPU is fine.

SLOs fix all three.

<!-- SPEAKER: This is the governance lesson. SLOs move quality from "vibes" to measurement. They also give engineering the language to push back on unrealistic product requirements. Time: ~4 min -->

---
<!-- _class: code -->

## L11: SLO burn-rate check

```python
SLO_TARGETS = {
    "quality_score": 0.80,
    "p95_latency_s": 3.0,
    "error_rate":    0.01,
}

def check_slo_burn(window_metrics: dict) -> list[str]:
    violations = []
    for metric, target in SLO_TARGETS.items():
        actual = window_metrics.get(metric, 0)
        if metric == "quality_score" and actual < target:
            violations.append(
                f"Quality below SLO: {actual:.2f} < {target}"
            )
        elif metric != "quality_score" and actual > target:
            violations.append(
                f"{metric} above SLO: {actual} > {target}"
            )
    return violations
```

<!-- SPEAKER: Run this function on a rolling 30-minute window. If it returns violations, fire an alert. The quality_score SLI requires your eval pipeline from Phase 05. This is why evaluation is Phase 05 and shipping/observability are 06/07. -->

---

## L11: AI SLIs are harder than web SLIs

```ascii
Web SLI             Measurement        AI SLI equivalent
──────────────────  ─────────────────  ─────────────────────────────
HTTP error rate     Exact (4xx/5xx)    Semantic error rate (harder)
Latency p95         Exact (ms)         TTFT + total (both matter)
Availability        Binary (up/down)   Degraded mode vs fully down
Throughput          req/s              req/s + tokens/s
Cost per request    Infra only         Infra + API tokens
────────────────────────────────────────────────────────────────────
New SLI for AI:     Quality score      Requires eval pipeline
                    Hallucination rate Requires ground truth
                    Cache hit rate     Requires cache instrumentation
```

<!-- SPEAKER: The quality score SLI is the hard one. It requires running your eval harness against sampled production traffic. Phase 05 built the eval harness. Phase 07 connects it to production sampling. -->

---
<!-- _class: section -->

# Lesson 12
## Chaos and Failure Injection

---

## L12: The problem

Your fallback logic looks correct in code review. You deploy it. Two weeks later the primary model has a 10-minute outage.

The fallback fails silently. Users see errors. You find out because a user emails support.

You never tested the fallback under real failure conditions.

<!-- SPEAKER: Every failure mode in Phase 06 (retries, fallbacks, circuit breakers) needs a chaos test to prove it works. Code review is not sufficient for failure path validation. Time: ~3 min -->

---

## L12: Four failure modes to inject

```ascii
Failure mode          Inject with                    Verify
─────────────────     ────────────────────────────   ──────────────────────
API timeout           mock: raise Timeout()          fallback triggers
Rate limit hit        mock: return 429 response      backoff + retry
Empty response        mock: return content=[]        error message shown
Malformed JSON        mock: return "not json"        parser handles safely
────────────────────────────────────────────────────────────────────────────
Key invariants:
  - User never sees a raw stack trace
  - Cost not double-charged on retry
  - Fallback model logged separately from primary
  - Circuit breaker opens after N consecutive failures
```

> **Key insight:** If you have not injected a failure and watched the system recover, the recovery code is untested.

<!-- SPEAKER: Use `unittest.mock.patch` to replace the model client with a mock that raises. Run the full request flow. Assert on the response the user receives, not on internal state. -->

---
<!-- _class: section -->

# Lesson 13
## Capstone: Full Observability + Cost Dashboard

---

## L13: What you wire together

Take the Phase 06 production service. Add:

1. OTel instrumentation on every model call (L02-L03)
2. Langfuse traces with quality scores from Phase 05 evals (L04)
3. Structured logging for prompts and responses (L05)
4. Per-request cost tracking and daily burn dashboard (L06)
5. Semantic cache with hit rate metric (L07)
6. TTFT and p95 latency tracking (L08)
7. LiteLLM gateway for routing and fallback (L09)
8. Locust load test at 20 concurrent users (L10)
9. SLO burn-rate alert running on a 30-minute window (L11)
10. Chaos test suite for the four failure modes (L12)

<!-- SPEAKER: The capstone is integration, not new concepts. Each item is already built. The work is wiring them into one coherent service and running the load test to confirm the SLOs hold. Time: ~5 min -->

---

## L13: The complete observability stack, wired

<div class="mermaid">
flowchart LR
    A[User request] --> B[LiteLLM Gateway]
    B --> C[Semantic Cache]
    C -->|hit| D[Cached response]
    C -->|miss| E[Model call]
    E --> F[OTel span]
    E --> G[Cost tracker]
    F --> H[Langfuse]
    G --> I[Cost dashboard]
    H --> J[SLO monitor]
    J -->|violation| K[Alert]
    E --> L[Structured log]
</div>

<!-- SPEAKER: This is the through-line diagram from slide 6, now fully labeled with lesson numbers. Every box was built in one lesson. The capstone proves they compose. -->

---
<!-- _class: section -->

# Discussion

---

## Discussion prompts

> **Facilitator prompt:** Your service has a 200 OK rate of 99.9% and p95 latency of 2.1 seconds. A user reports that answers have been wrong for the past week. What instrumentation would you look at first? What would you add if you do not have it?

> **Facilitator prompt:** You get a surprise bill: API costs tripled this month. You have no per-request cost data. Walk through how you would diagnose this. What would you instrument first?

> **Facilitator prompt:** What threshold would you set for a semantic cache on a customer-facing legal Q&A product? How does that differ from a casual chat product?

> **Facilitator prompt:** Your team wants to write an SLO for "AI quality." What SLI would you propose? How would you measure it? What would a burn-rate alert look like?

> **Facilitator prompt:** You have 30 minutes before a launch. Which one observability item from this phase do you add first, and why?

<!-- SPEAKER: Pick 2-3 based on the room. The first and last tend to generate the most debate. Allow 5-8 minutes per question. -->

---

## Exercises

**Easy:** Add an OTel span to an existing model call in your codebase. Set all six `gen_ai.*` attributes. Export to Phoenix locally. Verify the span appears in the UI.

**Easy:** Write a `request_cost()` function for two models. Run it against a saved set of token counts. Build a CSV cost log for 100 hypothetical requests.

**Medium:** Implement the `SemanticCache` class. Test it with 20 queries where five are near-duplicates. Measure cache hit rate and confirm no false positives at threshold 0.92.

**Medium:** Define three SLIs for a service you own or can describe. Write the `check_slo_burn()` function for those three SLIs. Write a test that verifies violations fire correctly.

**Hard:** Wire Langfuse tracing + the cost tracker + a SLO burn alert into a FastAPI service from Phase 06. Load test at 20 concurrent users with Locust. Confirm the SLO holds. Submit the Locust HTML report and the Langfuse trace link.

<!-- SPEAKER: The hard exercise is the capstone for solo learners. Timebox it to 3-4 hours. The Locust report is objective evidence the system held up. -->

---

## Further reading

- **OpenTelemetry Semantic Conventions for GenAI:** `opentelemetry.io/docs/specs/semconv/gen-ai/` - the canonical attribute list, updated as models evolve
- **Langfuse docs: Tracing:** `langfuse.com/docs/tracing` - prompt versioning, dataset capture, and the Python decorator pattern
- **Arize Phoenix:** `docs.arize.com/phoenix` - local-first, open-source, no API key required; best for development and offline environments
- **LiteLLM docs:** `docs.litellm.ai` - provider-agnostic gateway, routing rules, fallback config, and cost tracking
- **Google SRE Book, Chapter 4: SLOs:** `sre.google/sre-book/service-level-objectives` - the canonical SLO/SLI/error-budget framework, applied to AI features

<!-- SPEAKER: The OTel spec is living: check it when a new model provider launches. The SRE Book chapter is short and worth reading in full. -->

---

## What's next: Phase 08

**Phase 08: Security and Guardrails**

You have a service running. You can see it. Now you have to harden it.

- Prompt injection and jailbreaks: how attacks work, how to detect them
- Input and output guardrails: what to block, what to allow, how to test
- PII detection and redaction before content reaches the model
- Secret scanning in prompts and responses
- Rate limiting, abuse detection, and threat modeling for AI APIs
- Red-teaming your own service

> **Key insight:** Phase 07 tells you when something went wrong. Phase 08 prevents the wrong things from happening at all.

<!-- SPEAKER: Security builds directly on observability. You need traces (L04) and structured logs (L05) to detect attacks. Phase 08 is Phase 07 plus adversarial inputs. -->

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
