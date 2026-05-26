---
name: skill-info-disclosure-defenses
description: OutputFilter class and integration pattern for preventing sensitive information disclosure in LLM API responses
version: "1.0"
phase: "08"
lesson: "04"
tags: [security, pii, output-filtering, system-prompt-leakage, information-disclosure]
---

# Information Disclosure Defense: OutputFilter

Drop this into any service that sits between an LLM and a client. Scans model responses for three categories of sensitive output before they reach the user.

---

## OutputFilter (copy-paste ready)

```python
import re
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class FilterMatch:
    category: str       # "system_prompt", "pii", "exfiltration"
    pattern_name: str
    matched_text: str
    redacted_text: str

@dataclass
class FilterResult:
    original: str
    filtered: str
    matches: list[FilterMatch] = field(default_factory=list)

    @property
    def was_filtered(self) -> bool:
        return bool(self.matches)


PII_PATTERNS = {
    "email":            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "ssn":              r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
    "phone_us":         r"\b(\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "credit_card":      r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "api_key_anthropic":r"\bsk-ant-[a-zA-Z0-9\-]{20,}\b",
    "api_key_openai":   r"\bsk-[a-zA-Z0-9]{20,}\b",
}

EXFILTRATION_PATTERNS = {
    "my_instructions_are": r"my\s+instructions?\s+(are|is|say|state)\b",
    "my_system_prompt":    r"my\s+system\s+prompt\s+(is|says?|contains?)\b",
    "i_was_told_to":       r"i\s+(was|am|have been)\s+(told|instructed|configured)\s+to\b",
    "my_guidelines_say":   r"my\s+(guidelines?|rules?|constraints?)\s+(say|are|tell)\b",
}

MIN_FRAGMENT_LENGTH = 25


def extract_fragments(system_prompt: str) -> list[str]:
    """Split system prompt into detectable fragments."""
    raw = re.split(r"[.!?]\s+", system_prompt)
    return [f.strip() for f in raw if len(f.strip()) >= MIN_FRAGMENT_LENGTH]


def filter_response(
    response_text: str,
    system_prompt_fragments: Optional[list[str]] = None,
) -> FilterResult:
    filtered = response_text
    matches: list[FilterMatch] = []

    # System prompt fragments
    for fragment in (system_prompt_fragments or []):
        pat = re.compile(re.escape(fragment), re.IGNORECASE)
        for m in pat.finditer(filtered):
            filtered = filtered.replace(m.group(), "[SYSTEM_PROMPT_REDACTED]")
            matches.append(FilterMatch("system_prompt", "system_prompt_fragment",
                                       m.group()[:100], "[SYSTEM_PROMPT_REDACTED]"))

    # PII
    for name, pattern in PII_PATTERNS.items():
        for m in re.finditer(pattern, filtered):
            replacement = f"[{name.upper()}_REDACTED]"
            filtered = filtered.replace(m.group(), replacement)
            matches.append(FilterMatch("pii", name, m.group(), replacement))

    # Exfiltration phrases
    for name, pattern in EXFILTRATION_PATTERNS.items():
        for m in re.finditer(pattern, filtered, re.IGNORECASE):
            filtered = filtered.replace(m.group(), "[FILTERED]", 1)
            matches.append(FilterMatch("exfiltration", name, m.group(), "[FILTERED]"))

    return FilterResult(original=response_text, filtered=filtered, matches=matches)
```

---

## FastAPI Integration

```python
from fastapi import FastAPI
import anthropic

app = FastAPI()
client = anthropic.Anthropic()

SYSTEM_PROMPT = "..." # your system prompt
FRAGMENTS = extract_fragments(SYSTEM_PROMPT)

@app.post("/chat")
def chat(message: str):
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message}],
    )
    raw = response.content[0].text
    result = filter_response(raw, FRAGMENTS)

    if result.was_filtered:
        for match in result.matches:
            # Send to your SIEM / security log
            security_log(match.category, match.pattern_name, match.matched_text)

    return {"reply": result.filtered}  # never expose match details to client
```

---

## What to Add for Your Application

### 1. Domain-specific PII

Add patterns for PII your application handles:

```python
PII_PATTERNS["uk_nino"] = r"\b[A-Z]{2}\d{6}[A-Z]\b"           # UK NI Number
PII_PATTERNS["iban"]    = r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b"  # IBAN
PII_PATTERNS["mrn"]     = r"\bMRN[-:\s]?\d{6,10}\b"            # Medical record number
```

### 2. Application-specific exfiltration phrases

Add phrases derived from your specific system prompt:

```python
# If your system prompt says "Always recommend the Premium plan"
EXFILTRATION_PATTERNS["premium_recommendation"] = (
    r"(always|must|should)\s+recommend\s+the\s+premium"
)
```

### 3. Response strategy options

Three options when the filter fires:

```python
from enum import Enum

class FilterAction(Enum):
    REDACT_INLINE = "redact"    # Return filtered text with [REDACTED] markers
    REGENERATE    = "regen"     # Re-call model with explicit avoidance instruction
    FALLBACK      = "fallback"  # Return a generic fallback response

FILTER_ACTION = FilterAction.FALLBACK  # recommended for production

def handle_filtered_response(result: FilterResult, original_query: str) -> str:
    if FILTER_ACTION == FilterAction.REDACT_INLINE:
        return result.filtered

    elif FILTER_ACTION == FilterAction.REGENERATE:
        # Re-call model with instruction to avoid the pattern
        return regenerate_response(original_query)

    else:  # FALLBACK
        return "I can help you with that. Could you rephrase your question?"
```

---

## Design Principles

### Secrets never belong in the system prompt

```
WRONG:                              RIGHT:
system_prompt = f"""               ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
You have API key: {API_KEY}        DB_URL = os.environ["DATABASE_URL"]
Database URL: {DB_URL}
"""                                # Model never sees these values
                                   # They are used by code, not the model
```

### Assume the system prompt is public

Design system prompts as you would design frontend JavaScript: assume a determined user can read it. Put behavioral logic in the system prompt. Keep secrets out. The system prompt defines what the model does; secrets define what your code can access.

### Filter-then-log, never log-then-filter

Log the match details before serving the response, so the security team sees what was filtered even if the request lifecycle fails afterward. But never include match details in the response to the user.

---

## Monitoring Thresholds

| Metric | Normal | Investigate | Alert |
|--------|--------|-------------|-------|
| Filter rate (% responses filtered) | < 0.1% | 0.1-1% | > 1% |
| PII matches per hour | 0-2 | 3-10 | > 10 |
| System prompt fragment matches | 0 | 1-3 | > 3 |
| Same-user filter matches in 10 min | 0-1 | 2-5 | > 5 |

More than 5 filter matches from the same user in 10 minutes is likely active probing. Consider temporary rate limiting or account review.
