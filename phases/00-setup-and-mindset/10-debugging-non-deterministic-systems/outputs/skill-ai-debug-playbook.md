---
name: skill-ai-debug-playbook
description: Five-tool playbook for diagnosing any AI system failure, from logging setup to failure rate measurement
version: "1.0"
phase: "00"
lesson: "10"
tags: [debugging, logging, observability, non-deterministic]
---

# Skill: AI System Debug Playbook

When an AI system produces wrong output, use this playbook in order. Stop at the step that reveals the problem.

---

## Prerequisite: Is Logging On?

Before debugging anything, check if you have a log.

```python
# Check if ai_calls.jsonl exists and has records
from pathlib import Path
import json

log = Path("ai_calls.jsonl")
if not log.exists() or log.stat().st_size == 0:
    print("STOP: No log exists. Add DebugLogger before you can debug anything.")
    print("Every AI call must write: timestamp, model, prompt, response, latency, cost, error")
else:
    records = [json.loads(line) for line in log.open() if line.strip()]
    print(f"Log has {len(records)} records. Proceed.")
```

If there is no log, add it first. You cannot debug a probabilistic system without evidence.

---

## Tool 1: Retrieve the Failing Call

Find the exact prompt and response for the failure.

```python
records = [json.loads(line) for line in open("ai_calls.jsonl") if line.strip()]

# Option A: Find by timestamp
failing = [r for r in records if r["timestamp"].startswith("2026-05-26T14")]

# Option B: Find by response content
failing = [r for r in records if "wrong answer" in r["response"].lower()]

# Option C: Find all errors
failing = [r for r in records if r.get("error")]

for r in failing[:3]:
    print("Timestamp:", r["timestamp"])
    print("Prompt:   ", r["prompt"][:200])
    print("Response: ", r["response"][:200])
    print("Error:    ", r.get("error"))
    print()
```

---

## Tool 2: Reproduce with temperature=0

Re-run the exact failing prompt with temperature=0.0 to remove randomness.

```python
import anthropic, os

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

failed_record = failing[0]

response = client.messages.create(
    model=failed_record["model"],
    max_tokens=512,
    temperature=0.0,   # pin to deterministic
    messages=[{"role": "user", "content": failed_record["prompt"]}]
)
print("Reproduced:", response.content[0].text[:200])
```

Interpretation:
- Same failure at temperature=0 means the failure is systematic. Fix the prompt or model.
- Different result at temperature=0 means the failure is probabilistic. Measure the rate (Tool 4).

---

## Tool 3: Classify the Failure

Map the failure to its source before trying to fix it.

```
Symptom                              Type           Fix
-----------------------------------  -----------    --------------------------
rate_limit / 429 error               Integration    Back off, add retry logic
Connection timeout                   Integration    Check network, add timeout
Authentication / 401 error           Integration    Rotate API key
"I cannot / I'm unable" in response  Model          Rewrite prompt, reduce restriction
Response too short (<10 chars)       Model          Check max_tokens, prompt clarity
Wrong format (expected JSON, got text) Model        Add format instruction, use tools
Correct on simple inputs, wrong on complex Model    Increase model tier or add CoT
Correct sometimes, wrong sometimes   Model          Measure rate (Tool 4)
```

```python
def classify(record: dict) -> str:
    error = (record.get("error") or "").lower()
    response = record.get("response", "").lower()

    if "rate_limit" in error:
        return "integration:rate_limit"
    if "authentication" in error or "401" in error:
        return "integration:auth"
    if "connection" in error or "timeout" in error:
        return "integration:network"
    if any(p in response for p in ["i cannot", "i can't", "i'm unable"]):
        return "model:refusal"
    if record.get("error") is None and len(response) < 10:
        return "model:short_response"
    if record.get("error"):
        return "unknown:error"
    return "ok"

for r in records[:20]:
    print(classify(r), r["timestamp"])
```

---

## Tool 4: Measure Failure Rate

Count failures as a fraction of total calls. A single failure instance tells you nothing. A rate tells you everything.

```python
total = len(records)
errors = [r for r in records if r.get("error")]
refusals = [r for r in records if "i cannot" in r.get("response", "").lower()]
short = [r for r in records if not r.get("error") and len(r.get("response", "")) < 10]

print(f"Total calls:        {total}")
print(f"API errors:         {len(errors)}/{total} = {len(errors)/total:.1%}")
print(f"Refusals:           {len(refusals)}/{total} = {len(refusals)/total:.1%}")
print(f"Short responses:    {len(short)}/{total} = {len(short)/total:.1%}")
```

Thresholds (starting points, adjust for your use case):
- API error rate > 1%: investigate infrastructure
- Refusal rate > 2%: rewrite system prompt
- Any failure rate > 5%: do not deploy

---

## Tool 5: Separate Model Failures from Integration Failures

The fix depends on the source.

```
Integration failure → fix in your code
-----------------------------------------
Rate limit hit         Add exponential backoff + retry
Timeout                Increase timeout, add async
Auth error             Rotate key, check env var injection
Network error          Check VPC/firewall, use retry

Model failure → fix in your prompt or pipeline
-----------------------------------------
Refusal                Remove sensitive framing, clarify intent
Wrong format           Add explicit format instruction, use structured output
Hallucination          Add grounding context, lower temperature, use RAG
Inconsistency          Lower temperature, add consistency check in output validator
Low quality            Upgrade model tier, add chain-of-thought
```

```python
integration_failures = [r for r in records if r.get("error")]
model_failures = [
    r for r in records
    if not r.get("error") and (
        len(r.get("response", "")) < 10
        or "i cannot" in r.get("response", "").lower()
    )
]

print(f"Integration failures: {len(integration_failures)} - fix in infrastructure")
print(f"Model failures:       {len(model_failures)} - fix in prompt or pipeline")
```

---

## Quick Reference: The 5 Tools in Order

```
1. Log every call        ai_calls.jsonl: prompt + response + latency + cost + error
2. Retrieve the failure  Find exact record by timestamp or content search
3. Reproduce at temp=0   Same result = systematic; different = probabilistic
4. Classify by type      Integration vs. model vs. unknown
5. Measure the rate      Failure count / total calls. Fix by type, not by instance.
```

The sequence never changes. You always start with the log. You always end with a rate, not a single failure instance.

---

## Log Record Schema

Every record in `ai_calls.jsonl` must contain:

```json
{
  "timestamp": "2026-05-26T14:32:01Z",
  "model": "claude-3-5-haiku-20241022",
  "prompt": "the exact prompt string sent to the model",
  "response": "the exact response text returned",
  "latency_ms": 847,
  "input_tokens": 42,
  "output_tokens": 31,
  "cost_usd": 0.000197,
  "temperature": 1.0,
  "error": null
}
```

For errors, `response` is empty and `error` contains the exception message.
