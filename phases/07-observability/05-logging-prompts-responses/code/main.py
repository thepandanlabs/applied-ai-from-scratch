"""
L05: Logging Prompts, Responses, and Tool Calls
Phase 07 - Observability

Demonstrates:
- PII detection and redaction for email, phone, SSN, credit card
- Prompt hashing for deduplication without PII storage
- Structured JSONL logging with LLMRequestLogger
- structlog integration for production use
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

import anthropic
import structlog

# ---------------------------------------------------------------------------
# PII Detection
# ---------------------------------------------------------------------------

PII_PATTERNS = [
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL]"),
    (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE]"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
    (r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b", "[CARD]"),
]


def scrub_pii(text: str) -> tuple[str, list[str]]:
    """
    Replace PII patterns with placeholders.

    Returns:
        (scrubbed_text, list of PII type names found)
    """
    found: list[str] = []
    result = text
    for pattern, replacement in PII_PATTERNS:
        matches = re.findall(pattern, result)
        if matches:
            found.append(replacement.strip("[]").lower())
            result = re.sub(pattern, replacement, result)
    return result, found


def hash_prompt(prompt: str) -> str:
    """
    SHA-256 hash of the prompt, truncated to 16 hex chars (64 bits).
    Use as a log-safe prompt identifier for deduplication.
    Collision probability is negligible at any realistic call volume.
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Log Entry Schema
# ---------------------------------------------------------------------------


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
    response_preview: str  # first N chars only
    tool_calls: list[str]  # names only, not arg values
    user_id: Optional[str]
    error: Optional[str]
    pii_detected: list[str]  # which PII types were detected in prompt
    level: str = "info"
    # Full prompt only stored on error, in the restricted error log
    _full_prompt: str = field(default="", repr=False)


# ---------------------------------------------------------------------------
# LLMRequestLogger
# ---------------------------------------------------------------------------


class LLMRequestLogger:
    """
    Structured JSONL logger for LLM requests.

    Design decisions:
    - Scrubs PII from prompt before logging (not stored in main log)
    - Hashes prompt for deduplication fingerprint
    - Full prompt written only to error log, only when an error occurs
    - Tool call names logged, arg values are not
    - Response truncated to first N chars to limit storage
    """

    def __init__(
        self,
        log_path: str = "llm_requests.jsonl",
        error_log_path: str = "llm_errors.jsonl",
        response_preview_chars: int = 200,
    ):
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
        """
        Log a single LLM request.

        Returns the log entry (useful for callers that need to inspect it,
        e.g., in tests or metrics collection).
        """
        prompt_hash = hash_prompt(prompt)
        _, pii_found = scrub_pii(prompt)

        # Log tool call names only - never the arg values
        tool_names = [tc.get("name", "unknown") for tc in (tool_calls or [])]

        entry = LLMLogEntry(
            ts=datetime.now(timezone.utc).isoformat(),
            model=model,
            prompt_hash=prompt_hash,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            latency_ms=round(latency_ms, 2),
            response_preview=response[: self.preview_chars],
            tool_calls=tool_names,
            user_id=user_id,
            error=error,
            pii_detected=pii_found,
            level="error" if error else "info",
            _full_prompt=prompt,
        )

        self._write(entry)
        return entry

    def _write(self, entry: LLMLogEntry) -> None:
        """
        Write to main JSONL log.
        On error: also write full prompt to restricted error log.
        """
        # Exclude the private _full_prompt field from the main log
        d = {k: v for k, v in asdict(entry).items() if not k.startswith("_")}
        line = json.dumps(d, ensure_ascii=False)

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        # Error log includes the full prompt - keep this log with restricted
        # access and a short retention policy (7-30 days)
        if entry.error:
            error_record = {
                "ts": entry.ts,
                "prompt_hash": entry.prompt_hash,
                "error": entry.error,
                "full_prompt": entry._full_prompt,
            }
            with open(self.error_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(error_record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# API wrapper using the manual logger
# ---------------------------------------------------------------------------

llm_logger = LLMRequestLogger()
client = anthropic.Anthropic()


def call_with_logging(
    prompt: str,
    user_id: Optional[str] = None,
    model: str = "claude-3-5-haiku-20241022",
) -> str:
    """Make a Claude API call and log the result via LLMRequestLogger."""
    start = time.monotonic()
    error_msg = None
    response_text = ""
    usage = None
    tool_calls_raw: list[dict] = []

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = response.content[0].text if response.content else ""
        usage = response.usage
        tool_calls_raw = [
            {"name": b.name, "schema": list(b.input.keys())}
            for b in response.content
            if b.type == "tool_use"
        ]
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"

    latency_ms = (time.monotonic() - start) * 1000

    llm_logger.log(
        model=model,
        prompt=prompt,
        response=response_text,
        input_tokens=getattr(usage, "input_tokens", 0),
        output_tokens=getattr(usage, "output_tokens", 0),
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0),
        latency_ms=latency_ms,
        tool_calls=tool_calls_raw,
        user_id=user_id,
        error=error_msg,
    )

    if error_msg:
        raise RuntimeError(error_msg)
    return response_text


# ---------------------------------------------------------------------------
# structlog integration
# ---------------------------------------------------------------------------


def configure_structlog() -> None:
    """Configure structlog for JSON output. Call once at app startup."""
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


_slog = structlog.get_logger("llm")


def call_with_structlog(
    prompt: str,
    user_id: Optional[str] = None,
    model: str = "claude-3-5-haiku-20241022",
) -> str:
    """Same logging contract as call_with_logging, but via structlog."""
    start = time.monotonic()
    prompt_hash = hash_prompt(prompt)
    _, pii_found = scrub_pii(prompt)

    bound = _slog.bind(prompt_hash=prompt_hash, user_id=user_id)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - start) * 1000
        text = response.content[0].text if response.content else ""

        bound.info(
            "llm_request",
            model=model,
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


# ---------------------------------------------------------------------------
# Demo / smoke test
# ---------------------------------------------------------------------------


def demo() -> None:
    """Run a quick smoke test to verify the logger works."""
    print("=== LLMRequestLogger Demo ===\n")

    # 1. PII scrubbing
    test_prompt = "My email is jane@example.com and my phone is 415-555-0192."
    scrubbed, found = scrub_pii(test_prompt)
    print(f"Original : {test_prompt}")
    print(f"Scrubbed : {scrubbed}")
    print(f"PII found: {found}\n")

    # 2. Prompt hashing (deterministic)
    p = "What is the capital of France?"
    h1 = hash_prompt(p)
    h2 = hash_prompt(p)
    assert h1 == h2, "Hash must be deterministic"
    print(f"Prompt hash (stable): {h1}\n")

    # 3. Simulate a logged call (offline - no actual API call needed for demo)
    logger = LLMRequestLogger(
        log_path="/tmp/llm_requests_demo.jsonl",
        error_log_path="/tmp/llm_errors_demo.jsonl",
    )
    entry = logger.log(
        model="claude-3-5-haiku-20241022",
        prompt="Hello, my SSN is 123-45-6789. Summarize the French Revolution.",
        response="The French Revolution was a period of radical political and societal change...",
        input_tokens=42,
        output_tokens=18,
        latency_ms=312.4,
        user_id="user_abc123",
    )
    print(f"Log entry level  : {entry.level}")
    print(f"PII detected     : {entry.pii_detected}")
    print(f"Prompt hash      : {entry.prompt_hash}")
    print(f"Response preview : {entry.response_preview[:60]}...")

    # Verify main log does not contain the raw SSN
    with open("/tmp/llm_requests_demo.jsonl") as f:
        raw = f.read()
    assert "123-45-6789" not in raw, "SSN must not appear in main log"
    print("\nVerification: SSN not in main log - PASS")

    # 4. Simulate an error log
    error_entry = logger.log(
        model="claude-3-5-haiku-20241022",
        prompt="Translate: jane@example.com needs help",
        response="",
        input_tokens=0,
        output_tokens=0,
        latency_ms=50.0,
        error="RateLimitError: 429 Too Many Requests",
    )
    print(f"\nError entry level: {error_entry.level}")
    with open("/tmp/llm_errors_demo.jsonl") as f:
        err_raw = f.read()
    assert "full_prompt" in err_raw, "Error log must contain full_prompt"
    print("Verification: full_prompt in error log - PASS")

    print("\nAll demo checks passed. Check /tmp/llm_requests_demo.jsonl for output.")


if __name__ == "__main__":
    demo()
