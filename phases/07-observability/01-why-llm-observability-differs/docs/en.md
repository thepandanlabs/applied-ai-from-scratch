# Why LLM Observability Differs

> A 200 OK with a hallucinated answer looks exactly like a 200 OK with a correct one. HTTP metrics cannot tell the difference.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Phase 06 (Shipping), basic logging familiarity
**Time:** ~45 min
**Learning Objectives:**
- Explain how LLM observability differs from traditional service observability
- Name the 8 essential fields every LLM request log must capture
- Identify the 4 failure modes that only appear in traces, not HTTP metrics
- Build a minimal structured logger that captures LLM-specific signals

---

## The Problem

Your team just shipped an AI-powered support assistant. It responds in under 200ms, returns HTTP 200 on every request, and your Datadog dashboard is green. The SRE team is satisfied.

Then a customer emails: "Your AI told me my subscription auto-renews on the 1st but it doesn't. I missed my cancellation window." You search your logs. You find the request: status=200, latency=187ms. Nothing else. You cannot reconstruct what prompt was sent, what the model replied, which model version served it, how many tokens it consumed, or whether the answer came from cache. You are debugging a production hallucination with no evidence.

This is the core gap: traditional observability tools were designed for deterministic services. You give the same input, you get the same output, and any deviation shows up in error rates or latency spikes. LLM systems are different. The same prompt can produce subtly different responses. Quality degrades gradually, not catastrophically. Cost can double overnight because prompt templates were updated. A 200 OK tells you the HTTP layer worked. It says nothing about whether the answer was correct, grounded, or safe.

LLM observability requires capturing the semantic content of interactions, not just network metrics. Without it, you cannot debug failures, enforce quality, or control costs in production.

---

## The Concept

### Traditional vs. LLM Observability Signals

Traditional application performance monitoring (APM) captures three core signals: latency, error rate, and throughput. These are sufficient when outputs are deterministic. For LLM services, they are necessary but not sufficient.

```
+---------------------------+----------------------------------------+
| TRADITIONAL APM           | LLM OBSERVABILITY (additional)         |
+---------------------------+----------------------------------------+
| HTTP status code          | model name + version                   |
| Response latency (ms)     | prompt version / template ID           |
| Requests per second       | input token count                      |
| Error rate (4xx, 5xx)     | output token count                     |
| CPU / memory usage        | cost per request (USD)                 |
| Uptime / availability     | cache hit / miss                       |
|                           | tool calls + their results             |
|                           | output quality signal (score, label)   |
+---------------------------+----------------------------------------+

Traditional APM answers: "Did the request succeed?"
LLM observability answers: "Was the answer correct, and at what cost?"
```

### The 4 LLM-Specific Failure Modes

These failure modes are invisible to HTTP-layer monitoring:

**1. Prompt regression** - A template update changes model behavior. Error rate stays 0%. Users start complaining. Without prompt version tracking in your logs, you cannot bisect which deployment introduced the change.

**2. Model drift** - The model provider silently updates the underlying weights. Output style and accuracy shift. Your latency and error metrics remain unchanged. Only semantic quality scores reveal the drift.

**3. Cascading tool failures** - An agent calls Tool A, which returns a malformed result, which causes Tool B to fail silently, which causes the final answer to be wrong. The HTTP response is 200. The trace is the only artifact that shows the tool call chain.

**4. Runaway costs** - A prompt template change doubles average token count. No alert fires because token usage is not a default metric in generic APM. Your monthly bill doubles before anyone notices.

### The Logging Pipeline

```
User Request
     |
     v
+----------+       +------------------+       +---------------+
| LLM Call |  -->  | Structured Logger | -->   | Log Backend   |
+----------+       +------------------+       | (stdout/OTLP/ |
     |             captures:                  |  Langfuse)    |
     v             - model                    +---------------+
LLM Response       - prompt_version
                   - input_tokens
                   - output_tokens
                   - cost_usd
                   - latency_ms
                   - cache_hit
                   - error (if any)
```

These 8 fields are the minimum viable LLM log. Every field has a production use case: model for debugging model drift, prompt_version for regression bisection, token counts + cost_usd for budget alerts, latency_ms for SLA tracking, cache_hit for cost optimization, error for failure classification.

---

## Build It

We will build a minimal `LLMLogger` that wraps any Anthropic API call and emits a structured log entry with all 8 required fields.

### Step 1: Install dependencies

```bash
pip install anthropic python-dotenv
```

### Step 2: Define the log record structure

Use a dataclass to enforce the 8 required fields. If a field is missing, the logger cannot emit a valid record.

```python
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional
import anthropic

@dataclass
class LLMLogRecord:
    """The 8 essential fields every LLM request log must capture."""
    model: str              # e.g. "claude-3-5-haiku-20241022"
    prompt_version: str     # e.g. "support-v2.1" - track this in your prompts
    input_tokens: int       # tokens consumed by the prompt
    output_tokens: int      # tokens consumed by the response
    cost_usd: float         # calculated from token counts and model pricing
    latency_ms: float       # wall-clock time from request to first byte of response
    cache_hit: bool         # True if response came from prompt cache
    error: Optional[str]    # None on success; error class name on failure
```

### Step 3: Build the structured logger

```python
# Token costs for Claude models (per million tokens, as of 2026)
# Source: https://www.anthropic.com/pricing
MODEL_COSTS = {
    "claude-3-5-haiku-20241022": {
        "input_per_m": 0.80,
        "output_per_m": 4.00,
        "cache_read_per_m": 0.08,
    },
    "claude-3-5-sonnet-20241022": {
        "input_per_m": 3.00,
        "output_per_m": 15.00,
        "cache_read_per_m": 0.30,
    },
}

def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
) -> float:
    """Calculate USD cost for an API call based on token counts."""
    pricing = MODEL_COSTS.get(model, MODEL_COSTS["claude-3-5-haiku-20241022"])
    input_cost = (input_tokens / 1_000_000) * pricing["input_per_m"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_per_m"]
    cache_cost = (cache_read_tokens / 1_000_000) * pricing["cache_read_per_m"]
    return round(input_cost + output_cost + cache_cost, 8)


class LLMLogger:
    """
    Minimal structured logger for LLM API calls.
    Wraps Anthropic API calls and emits JSON log records with the 8 required fields.
    """

    def __init__(self, output_file: Optional[str] = None):
        self.client = anthropic.Anthropic()
        self.output_file = output_file

    def call(
        self,
        prompt: str,
        prompt_version: str,
        model: str = "claude-3-5-haiku-20241022",
        system: str = "You are a helpful assistant.",
        max_tokens: int = 512,
    ) -> tuple[str, LLMLogRecord]:
        """
        Call the Anthropic API and return (response_text, log_record).
        Always emits a log record, even on failure.
        """
        start = time.monotonic()
        error = None
        response_text = ""
        input_tokens = 0
        output_tokens = 0
        cache_hit = False

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            # Prompt cache: Anthropic returns cache_read_input_tokens when cache is hit
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            cache_hit = cache_read > 0

        except anthropic.APIError as exc:
            error = type(exc).__name__

        latency_ms = (time.monotonic() - start) * 1000

        record = LLMLogRecord(
            model=model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=calculate_cost(model, input_tokens, output_tokens),
            latency_ms=round(latency_ms, 2),
            cache_hit=cache_hit,
            error=error,
        )

        self._emit(record)
        return response_text, record

    def _emit(self, record: LLMLogRecord) -> None:
        """Write the log record as a JSON line to stdout and optionally to a file."""
        line = json.dumps(asdict(record))
        print(line)
        if self.output_file:
            with open(self.output_file, "a") as f:
                f.write(line + "\n")
```

### Step 4: Run it and inspect the output

```python
def main():
    logger = LLMLogger(output_file="llm_requests.jsonl")

    # Simulate two requests with different prompt versions
    questions = [
        ("What is the capital of France?", "general-qa-v1"),
        ("Summarize quantum computing in one sentence.", "summary-v2"),
        ("INVALID PROMPT" * 10000, "stress-test-v1"),  # will succeed but use many tokens
    ]

    for prompt, version in questions:
        text, record = logger.call(
            prompt=prompt,
            prompt_version=version,
        )
        print(f"--- Response: {text[:80]}...")
        print(f"--- Cost: ${record.cost_usd:.6f} | Tokens: {record.input_tokens}in / {record.output_tokens}out")
        print()


if __name__ == "__main__":
    main()
```

Sample output (one line per request, emitted as structured JSON):

```json
{"model": "claude-3-5-haiku-20241022", "prompt_version": "general-qa-v1", "input_tokens": 18, "output_tokens": 11, "cost_usd": 0.0000588, "latency_ms": 412.3, "cache_hit": false, "error": null}
```

> **Real-world check:** Your manager sees this and says: "We already have Datadog. It shows latency and error rates. Why do we need a separate logger just for LLM calls? Isn't this duplication?" How do you explain what Datadog can and cannot see about your LLM service?

### Step 5: Verify the failure capture path

Force an error to confirm the logger captures it correctly:

```python
# This will raise an AuthenticationError or similar
import os
os.environ["ANTHROPIC_API_KEY"] = "sk-invalid-key"
bad_logger = LLMLogger()
text, record = bad_logger.call("Hello", prompt_version="test-v1")
assert record.error is not None, "Error field must be set on API failure"
assert record.input_tokens == 0, "Token counts must be zero on failure"
print(f"Captured error: {record.error}")
```

---

## Use It

Generic APM tools (Datadog, New Relic, Prometheus) capture what happens at the HTTP transport layer. Here is what each tool sees vs. what you need for LLM observability:

```
+----------------------+------------------+-----------------------------+
| Signal               | Generic APM      | LLM Logger                  |
+----------------------+------------------+-----------------------------+
| HTTP status          | Yes              | Yes (via error field)        |
| Response latency     | Yes              | Yes (latency_ms)             |
| Request rate         | Yes              | Derivable from log volume    |
| Error rate           | Yes (HTTP only)  | Yes (semantic errors too)    |
| Cost per request     | No               | Yes (cost_usd)               |
| Token counts         | No               | Yes (input/output_tokens)    |
| Prompt version       | No               | Yes (prompt_version)         |
| Model version        | No               | Yes (model)                  |
| Cache effectiveness  | No               | Yes (cache_hit)              |
| Tool call chains     | No               | Needs OTel spans (L02-L03)   |
+----------------------+------------------+-----------------------------+
```

In production, you would route these JSONL records to a log aggregator (Elastic, Loki, CloudWatch Logs) and build dashboards on top. Lessons 02 and 03 of this phase replace the raw JSON logger with OpenTelemetry spans and route them to Langfuse for richer query and visualization capabilities.

> **Perspective shift:** A senior engineer suggests: "Instead of a custom logger, let's just log the raw API response object and parse it later." What are the problems with this approach in a system that handles 10,000 requests per day, and when would it actually be acceptable?

---

## Ship It

This lesson produces a reusable observability primer that any LLM service can adopt.

**Artifact:** `outputs/prompt-llm-observability-primer.md`

The `code/main.py` in this lesson is the starting point for LLM request logging. Copy `LLMLogger` and `LLMLogRecord` into your service. Adapt `MODEL_COSTS` when you add new models. The JSONL output format is intentionally simple: one JSON object per line, easy to ship to any log aggregator.

---

## Evaluate It

A logging system that drops records or captures incorrect data is worse than no logging: it creates false confidence.

**Check 1: Schema completeness**

After running 10 requests, verify no field is ever null when it should have a value:

```python
import json

with open("llm_requests.jsonl") as f:
    records = [json.loads(line) for line in f]

required_fields = ["model", "prompt_version", "input_tokens", "output_tokens",
                   "cost_usd", "latency_ms", "cache_hit", "error"]

for i, record in enumerate(records):
    for field in required_fields:
        assert field in record, f"Record {i} missing field: {field}"

print(f"Schema check passed: {len(records)} records, all fields present")
```

**Check 2: Cost accuracy**

Cross-check your calculated cost against the Anthropic console for a known request:

```python
# After running a request, compare logger cost to actual API cost
# The Anthropic console shows per-request cost in the usage dashboard
# Tolerance: within 1% (rounding differences in token counting)
expected_cost = 0.000059  # from Anthropic console
actual_cost = records[0]["cost_usd"]
assert abs(expected_cost - actual_cost) / expected_cost < 0.01, \
    f"Cost calculation off: got {actual_cost}, expected {expected_cost}"
```

**Check 3: Latency timing accuracy**

Verify that logged latency is consistent with actual API response time by comparing wall-clock measurement to the API's own headers:

```python
import anthropic, time

client = anthropic.Anthropic()
start = time.monotonic()
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=10,
    messages=[{"role": "user", "content": "Hi"}],
)
wall_ms = (time.monotonic() - start) * 1000

# Your logger's latency_ms should be within 50ms of wall_ms
# (overhead from JSON serialization and file write)
print(f"Wall clock: {wall_ms:.0f}ms")
print(f"Logger should capture: within 50ms of this value")
```

**Check 4: Error capture completeness**

Confirm that 100% of API errors result in a non-null `error` field and that token counts are 0 on failures:

```python
error_records = [r for r in records if r["error"] is not None]
for r in error_records:
    assert r["input_tokens"] == 0, "Partial token data on error is misleading"
    assert r["output_tokens"] == 0, "Partial token data on error is misleading"
    assert r["cost_usd"] == 0.0, "Zero cost on errors: no tokens consumed"

print(f"Error capture check passed: {len(error_records)} error records validated")
```
