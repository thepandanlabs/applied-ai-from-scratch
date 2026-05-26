# Logging Prompts, Responses, and Tool Calls

> Log what you need to debug. Redact what you must not store. Never confuse the two.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 07 Lessons 01-04 (Observability fundamentals, OpenTelemetry, Langfuse, traces)
**Time:** ~45 min
**Learning Objectives:**
- Identify which fields to log, which to redact, and the production reasoning behind each decision
- Implement PII detection and redaction for common patterns: email, phone, SSN
- Build a structured JSONL logger for LLM requests using Python's standard library
- Replace the raw logger with `structlog` for consistent, parseable output
- Apply the prompt-hashing pattern to get deduplication without storing full prompt text

---

## The Problem

Your LLM feature ships. Three weeks later, a user reports that the assistant returned something wrong. You open your logs. They look like this:

```
2026-04-12 14:23:01 INFO - LLM call completed
2026-04-12 14:23:02 INFO - LLM call completed
2026-04-12 14:23:02 INFO - LLM call completed
```

No model name. No prompt. No response. No tokens. No latency. You cannot reproduce the failure. You cannot tell which call failed. You cannot even tell which model was used.

The obvious fix: log everything. But a different team logs everything and gets a GDPR audit. Their logs contain user emails, phone numbers, and in one case a Social Security Number a user pasted into a prompt. Legal issues follow.

The right answer is neither extreme. You need structured, machine-readable logs that capture what you need to debug and optimize, with PII fields either scrubbed or never stored in the first place. This lesson builds that logger from scratch, then wires it into `structlog` for production.

---

## The Concept

### What to Log and What Not to Log

```
+---------------------------+-------------+------------------------------------------+
| Field                     | Log?        | Reason                                   |
+---------------------------+-------------+------------------------------------------+
| model name/version        | YES         | Needed for cost attribution, regression  |
| prompt hash (SHA-256)     | YES         | Dedup without storing PII                |
| full prompt text          | ON ERROR ONLY| PII risk at scale; log only on failure  |
| response (truncated, Nch) | YES         | Enough to verify output type             |
| input token count         | YES         | Cost, rate-limit debugging               |
| output token count        | YES         | Cost, output verbosity tracking          |
| cache tokens              | YES         | Cache hit rate measurement               |
| latency ms (total)        | YES         | Performance baseline                     |
| time to first token ms    | YES         | UX metric for streaming endpoints        |
| tool call names           | YES         | Workflow debugging, capability usage     |
| tool call arg schemas     | YES         | Understand which fields were passed      |
| tool call arg VALUES      | REDACT      | May contain API keys, credentials, PII   |
| user ID (opaque hash)     | YES         | Per-user cost/usage; not the email       |
| user email / name         | NO          | PII - use hashed user_id instead         |
| SSN, phone, credit card   | NO          | PII - redact before any storage          |
| API keys                  | NEVER       | Credentials; never in logs               |
| error type + message      | YES         | Debugging; strip any PII from message    |
+---------------------------+-------------+------------------------------------------+
```

### The Prompt-Hash Pattern

The key insight: you want deduplication and a debug trail without storing PII at scale.

```
Full prompt text  -->  SHA-256 hash  -->  Store the hash in every log line
                  |
                  +--> If an error occurs, log the full prompt to a SEPARATE
                       error log with a short TTL and restricted access
```

This gives you:
- The ability to detect when the same prompt fires thousands of times (cache miss storm)
- Debuggability when something goes wrong (error log has the full text)
- No PII in your main log stream

### PII Detection Patterns

```
Pattern          Regex                                   Example match
-----------      --------------------------------------  ---------------------
Email            [a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.\w+ jane@example.com
Phone (US)       \b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b      415-555-0192
SSN              \b\d{3}-\d{2}-\d{4}\b                  123-45-6789
Credit card      \b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4} 4111 1111 1111 1111
```

These patterns catch common cases. They are not exhaustive. For healthcare or finance, use a dedicated PII detection library (Presidio, AWS Comprehend Medical). For most SaaS products, these four patterns cover 90%+ of accidental PII in prompts.

### Structured Logging: JSONL vs Unstructured

```
UNSTRUCTURED (hard to parse, hard to query):
  2026-04-12 14:23:01 INFO LLM call: claude-3-5-haiku-20241022 | 234 tokens | 412ms

STRUCTURED JSONL (machine-readable, queryable with jq or any log aggregator):
  {"ts":"2026-04-12T14:23:01Z","model":"claude-3-5-haiku-20241022","input_tokens":189,
   "output_tokens":45,"latency_ms":412,"prompt_hash":"a3f2...","level":"info"}
```

One line per request. Each line is valid JSON. You can pipe to `jq`, ingest into Loki, CloudWatch, or Datadog with zero transformation.

---

## Build It

### Step 1: PII Scrubber

```python
import re
from typing import Optional

# Common PII patterns - extend for your domain
PII_PATTERNS = [
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL]'),
    (r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]'),
    (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]'),
    (r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b', '[CARD]'),
]

def scrub_pii(text: str) -> tuple[str, list[str]]:
    """
    Replace PII patterns with placeholders.
    Returns (scrubbed_text, list_of_pattern_types_found).
    """
    found: list[str] = []
    result = text
    for pattern, replacement in PII_PATTERNS:
        matches = re.findall(pattern, result)
        if matches:
            found.append(replacement.strip('[]').lower())
            result = re.sub(pattern, replacement, result)
    return result, found
```

### Step 2: Prompt Hasher

```python
import hashlib

def hash_prompt(prompt: str) -> str:
    """
    SHA-256 hash of the prompt text.
    Use this as the log-safe identifier for the prompt.
    """
    return hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:16]
```

We truncate to 16 hex chars (64 bits): collision probability is negligible for any realistic call volume, and it keeps log lines short.

### Step 3: The LLMRequestLogger

```python
import json
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class LLMLogEntry:
    ts: str
    model: str
    prompt_hash: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: float
    response_preview: str          # first 200 chars only
    tool_calls: list[str]          # names only, not args
    user_id: Optional[str]
    error: Optional[str]
    pii_detected: list[str]        # which PII types were found in prompt
    level: str = 'info'
    # Full prompt stored ONLY on error, in a separate restricted log
    _full_prompt: str = field(default='', repr=False)


class LLMRequestLogger:
    """
    Structured JSONL logger for LLM requests.
    Scrubs PII from prompts before logging.
    Logs full prompt text only when an error occurs.
    """

    def __init__(self, log_path: str = 'llm_requests.jsonl',
                 error_log_path: str = 'llm_errors.jsonl',
                 response_preview_chars: int = 200):
        self.log_path = log_path
        self.error_log_path = error_log_path
        self.preview_chars = response_preview_chars

    def log(
        self,
        model: str,
        prompt: str,
        response: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        tool_calls: Optional[list[dict]] = None,
        user_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> LLMLogEntry:
        """Log a single LLM request. Returns the log entry for callers that need it."""
        # Hash the prompt, detect PII (don't store the full prompt in normal logs)
        prompt_hash = hash_prompt(prompt)
        _, pii_found = scrub_pii(prompt)

        # Extract tool call names only
        tool_names = [tc.get('name', 'unknown') for tc in (tool_calls or [])]

        entry = LLMLogEntry(
            ts=datetime.now(timezone.utc).isoformat(),
            model=model,
            prompt_hash=prompt_hash,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            latency_ms=round(latency_ms, 2),
            response_preview=response[:self.preview_chars],
            tool_calls=tool_names,
            user_id=user_id,
            error=error,
            pii_detected=pii_found,
            level='error' if error else 'info',
            _full_prompt=prompt,
        )

        self._write(entry)
        return entry

    def _write(self, entry: LLMLogEntry) -> None:
        """Write to JSONL. On error, also write full prompt to restricted error log."""
        # Build the dict to log - exclude internal _full_prompt field
        d = {k: v for k, v in asdict(entry).items() if not k.startswith('_')}

        line = json.dumps(d, ensure_ascii=False)

        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

        # On error: write full prompt to the restricted error log
        if entry.error:
            error_record = {
                'ts': entry.ts,
                'prompt_hash': entry.prompt_hash,
                'error': entry.error,
                'full_prompt': entry._full_prompt,  # only here, only on error
            }
            with open(self.error_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(error_record, ensure_ascii=False) + '\n')
```

> **Real-world check:** A colleague says: "Why bother hashing the prompt? If the logs are behind our VPN, only internal engineers can see them." What's the flaw in this reasoning, and what happens six months later when your company buys another company and merges log pipelines?

### Step 4: Wire It to a Real API Call

```python
import anthropic
import time

llm_logger = LLMRequestLogger()
client = anthropic.Anthropic()

def call_with_logging(
    prompt: str,
    user_id: Optional[str] = None,
    model: str = "claude-3-5-haiku-20241022",
) -> str:
    """Make a Claude API call and log the result."""
    start = time.monotonic()
    error_msg = None
    response_text = ''
    usage = None
    tool_calls_raw = []

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = response.content[0].text if response.content else ''
        usage = response.usage
        # Collect tool calls if any
        tool_calls_raw = [
            {"name": b.name, "schema": list(b.input.keys())}
            for b in response.content
            if b.type == "tool_use"
        ]
    except Exception as e:
        error_msg = type(e).__name__ + ': ' + str(e)

    latency_ms = (time.monotonic() - start) * 1000

    llm_logger.log(
        model=model,
        prompt=prompt,
        response=response_text,
        input_tokens=getattr(usage, 'input_tokens', 0),
        output_tokens=getattr(usage, 'output_tokens', 0),
        cache_read_tokens=getattr(usage, 'cache_read_input_tokens', 0),
        cache_write_tokens=getattr(usage, 'cache_creation_input_tokens', 0),
        latency_ms=latency_ms,
        tool_calls=tool_calls_raw,
        user_id=user_id,
        error=error_msg,
    )

    if error_msg:
        raise RuntimeError(error_msg)
    return response_text
```

---

## Use It

`structlog` gives you the same structured output with less boilerplate, plus log-level filtering, processors, and drop-in compatibility with any log aggregator.

```python
import structlog
import logging

# Configure once at app startup
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger("llm")

def call_with_structlog(prompt: str, user_id: Optional[str] = None) -> str:
    """Same logging, but via structlog."""
    start = time.monotonic()
    prompt_hash = hash_prompt(prompt)
    _, pii_found = scrub_pii(prompt)

    bound = log.bind(prompt_hash=prompt_hash, user_id=user_id)

    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - start) * 1000
        text = response.content[0].text if response.content else ''

        bound.info(
            "llm_request",
            model="claude-3-5-haiku-20241022",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=round(latency_ms, 2),
            response_preview=text[:200],
            pii_detected=pii_found,
        )
        return text

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        bound.error(
            "llm_request_failed",
            error=type(e).__name__,
            latency_ms=round(latency_ms, 2),
            pii_detected=pii_found,
        )
        raise
```

**What structlog adds over the manual JSONL approach:**

| Feature | Manual JSONL | structlog |
|---|---|---|
| Structured output | Yes | Yes |
| Log level filtering | Manual | Built-in |
| Context binding (bind per request) | Manual | bind() |
| Pluggable processors | Manual | Built-in pipeline |
| Testing support | Manual | capture_logs() fixture |
| Async support | Manual | Built-in |

> **Perspective shift:** A platform engineer reviews your PR and says: "We already have application logs going to CloudWatch. Why add another logging library? Can't we just use print() with json.dumps()?" When does that argument hold, and when does it break down as the system scales?

---

## Ship It

**Artifact:** `outputs/skill-llm-request-logger.md`

This lesson produces a `LLMRequestLogger` class and a PII scrubber you can drop into any Python service. The logger writes JSONL that works with any log aggregator. The error log pattern (full prompt only on failure) is the production-safe approach for teams with compliance requirements.

Copy `code/main.py` into your project. Set `log_path` to a path your log shipper watches. Set `error_log_path` to a path with restricted access and a short retention policy (7-30 days, not the same as your main logs).

---

## Evaluate It

**Verification 1: PII does not appear in the main log**

After running `call_with_logging` with a prompt containing an email address, verify the main log does not contain the email:

```bash
grep -c '@' llm_requests.jsonl   # should be 0
grep 'EMAIL' llm_requests.jsonl  # should show [EMAIL] placeholder
```

**Verification 2: Full prompt appears in error log on failure**

Trigger a failure (e.g., pass an invalid model name). Check that:
- `llm_requests.jsonl` contains `"level":"error"` and `"error":"..."` but not the full prompt
- `llm_errors.jsonl` contains the full prompt text alongside the error

**Verification 3: Same prompt produces the same hash**

```python
h1 = hash_prompt("What is the capital of France?")
h2 = hash_prompt("What is the capital of France?")
assert h1 == h2, "Hash must be deterministic"
```

**Verification 4: Token cost is visible**

Parse the JSONL log and sum `input_tokens` and `output_tokens` across all entries. This is the foundation of the cost accounting lesson (L06). If you can sum tokens from logs, you can build cost dashboards.

```bash
jq -s '[.[].input_tokens] | add' llm_requests.jsonl
jq -s '[.[].output_tokens] | add' llm_requests.jsonl
```
