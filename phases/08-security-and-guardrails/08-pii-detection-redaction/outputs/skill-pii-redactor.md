---
name: skill-pii-redactor
description: PII detection and redaction reference with regex patterns for structured PII, pseudonymization strategy, and presidio integration guide. Use when designing data pipelines that process user input containing personal information.
version: "1.0"
phase: "08"
lesson: "08"
tags: [security, pii, privacy, gdpr, redaction, presidio, regex]
---

# Skill: PII Redactor

## Purpose

You are an applied AI privacy engineer. Use this skill when designing systems that process user-generated text, reviewing data pipelines for PII exposure, or implementing redaction before inputs enter a model or before outputs are logged.

---

## PII Category Reference

```
CATEGORY       DETECTION     EXAMPLE                  LABEL
----------------------------------------------------------------------
Email          Regex         alice@company.com         [EMAIL]
Phone (US)     Regex         (555) 867-5309            [PHONE]
SSN            Regex         123-45-6789               [SSN]
Credit card    Regex         4111111111111111          [CREDIT_CARD]
IP address     Regex         192.168.1.42              [IP_ADDRESS]
----------------------------------------------------------------------
Person name    NER / LLM     "John Smith"              [PERSON_NAME]
Street addr    NER / LLM     "123 Maple Street"        [STREET_ADDRESS]
Organization   NER / LLM     "Acme Medical Group"      [ORGANIZATION]
Medical info   LLM           "diagnosed with T2D"      [MEDICAL_INFO]
----------------------------------------------------------------------
```

Regex covers the easy 80%: structured PII with deterministic formats.
NER / LLM covers the hard 20%: contextual PII requiring semantic understanding.

---

## Regex Patterns

```python
import re
from dataclasses import dataclass

@dataclass
class PIIMatch:
    category: str
    original: str
    start: int
    end: int
    label: str

PII_PATTERNS = [
    ("credit_card", re.compile(
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|"
        r"(?:5[1-5][0-9]{2}|222[1-9]|22[3-9][0-9]|2[3-6][0-9]{2}|27[01][0-9]|2720)[0-9]{12}|"
        r"3[47][0-9]{13}|(?:6011|65[0-9]{2}|64[4-9][0-9])[0-9]{12})\b"
    ), "[CREDIT_CARD]"),

    ("ssn", re.compile(
        r"\b(?!000|666|9\d{2})\d{3}[-\s](?!00)\d{2}[-\s](?!0000)\d{4}\b"
    ), "[SSN]"),

    ("email", re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
    ), "[EMAIL]"),

    ("phone", re.compile(
        r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"
    ), "[PHONE]"),

    ("ip_address", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ), "[IP_ADDRESS]"),
]
```

---

## Redaction vs. Pseudonymization

| Approach | Pattern | When to use |
|----------|---------|-------------|
| Redaction | `alice@corp.com` -> `[EMAIL]` | Logs, external APIs, training data |
| Pseudonymization | `alice@corp.com` -> `email_0001` | Model context, anonymized datasets where coherence matters |

Pseudonymization requires a mapping table stored securely. The same original value always maps to the same pseudonym within a session.

---

## Apply Redaction Before and After the Model

```python
def safe_llm_call(user_input: str, redactor, client) -> str:
    # Redact input before it enters model context
    clean_input, input_report = redactor.redact_report(user_input)

    # Call the model with redacted input
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": clean_input}],
    )
    raw_output = response.content[0].text

    # Redact output before logging
    clean_output = redactor.redact(raw_output)
    return clean_output
```

---

## LLM Fallback Prompt

```python
LLM_PII_PROMPT = """Identify all PII in the text below.

Return JSON array only:
[{"type": "person_name|street_address|organization|medical_info|other_pii",
  "text": "exact substring",
  "reason": "one sentence"}]

Text:
"""

def llm_pii_detect(text: str, client) -> list[dict]:
    r = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": LLM_PII_PROMPT + text[:3000]}],
    )
    try:
        return json.loads(r.content[0].text.strip())
    except Exception:
        return []  # fail open: don't block on LLM error
```

---

## presidio (production recommendation)

For teams needing multi-language NER, regulatory compliance documentation, or audited libraries:

```python
# pip install presidio-analyzer presidio-anonymizer
# python -m spacy download en_core_web_lg
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

def presidio_redact(text: str) -> str:
    results = analyzer.analyze(text=text, language="en")
    return anonymizer.anonymize(text=text, analyzer_results=results).text
```

---

## Where to Apply Redaction

1. **User input** - before adding to model context
2. **Retrieved documents** - before inserting into RAG context
3. **Model output** - before logging to observability tools
4. **Logs and traces** - add redaction as a log processor step

---

## Evaluation

- **Recall**: run 50 strings with known PII, all must be detected
- **Precision**: run 50 benign strings (order IDs, zips), false positive rate must be < 1%
- **Consistency**: same PII value must produce the same pseudonym across a session
- **Log audit**: weekly sample of raw traces, zero PII should appear
