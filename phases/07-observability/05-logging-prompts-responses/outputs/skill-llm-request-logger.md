---
name: skill-llm-request-logger
description: Structured JSONL logger for LLM requests with PII scrubbing, prompt hashing, and error-only full-prompt storage
version: "1.0"
phase: "07"
lesson: "05"
tags: [logging, observability, pii, structured-logs, jsonl]
---

# Skill: LLM Request Logger

## Purpose

You are an applied AI engineering advisor. When a user needs to log LLM requests safely in production - without creating PII liability - use this skill to design and implement their logging strategy.

---

## Core Pattern

```
LLM Request
  |
  +-- Hash prompt (16-char SHA-256) --> store in every log line
  |
  +-- Scrub PII from prompt ----------> log scrubbed version on error only
  |
  +-- Log to main JSONL:
  |     ts, model, prompt_hash, input_tokens, output_tokens,
  |     cache_tokens, latency_ms, response_preview (200 chars),
  |     tool_call_names (not values), user_id (opaque), pii_detected[]
  |
  +-- On error: log to RESTRICTED error log:
        ts, prompt_hash, error, full_prompt_text
        (short TTL, restricted access, not shipped to main aggregator)
```

---

## What to Log vs What Not to Log

| Field | Log? | Reason |
|---|---|---|
| model name | YES | Cost attribution, regression detection |
| prompt hash | YES | Dedup without PII storage |
| full prompt text | ON ERROR ONLY | PII risk at scale |
| response preview (200 chars) | YES | Enough to verify output type |
| input/output token counts | YES | Cost accounting |
| cache token counts | YES | Cache hit measurement |
| latency ms | YES | Performance baseline |
| tool call names | YES | Workflow debugging |
| tool call arg values | REDACT | May contain credentials or PII |
| user ID (opaque hash) | YES | Per-user cost; not the email |
| user email/name | NO | PII |
| SSN, phone, credit card | NO | PII - scrub before any log |
| API keys | NEVER | Credentials |
| error type + message | YES | Debugging; strip PII from message |

---

## PII Scrubber

```python
import re

PII_PATTERNS = [
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL]'),
    (r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]'),
    (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]'),
    (r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b', '[CARD]'),
]

def scrub_pii(text: str) -> tuple[str, list[str]]:
    found = []
    result = text
    for pattern, replacement in PII_PATTERNS:
        if re.search(pattern, result):
            found.append(replacement.strip('[]').lower())
            result = re.sub(pattern, replacement, result)
    return result, found
```

For healthcare or finance: use Presidio or AWS Comprehend Medical for comprehensive PII detection. The regex patterns above cover 90%+ of accidental PII in general SaaS prompts.

---

## Prompt Hashing

```python
import hashlib

def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:16]
```

16 hex chars = 64 bits. Collision probability is negligible at any realistic LLM call volume. The same prompt always produces the same hash: use this to detect cache miss storms (the same hash firing thousands of times per minute) or to correlate error log entries back to main log entries.

---

## Quick Verification Checklist

After deploying the logger, verify:

1. PII not in main log: `grep -c '@' llm_requests.jsonl` should return 0 if emails are in prompts
2. Full prompt in error log on failure: check `llm_errors.jsonl` after an intentional error
3. Hash is deterministic: same prompt always produces same hash across restarts
4. Token counts are non-zero: if they are 0, the usage field is not being read correctly
5. Log is valid JSONL: `jq . llm_requests.jsonl > /dev/null` should exit 0

---

## Extending for Production

- Ship main log to CloudWatch Logs, Loki, or Datadog with a log forwarder (Fluent Bit, Vector)
- Set error log retention to 7-30 days with restricted IAM/IAP access
- Add `trace_id` field to correlate LLM log entries with OpenTelemetry traces (Phase 07 L03)
- Add `feature_name` field to break down costs by product feature (Phase 07 L06)
- For async endpoints: use `asyncio.create_task()` to write logs without blocking the response path
