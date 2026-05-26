# PII Detection and Redaction

> Regex catches structured PII. It misses contextual PII. Use regex for the easy 80%, LLM for the hard 20% in high-risk pipelines.

**Type:** Build
**Languages:** Python
**Prerequisites:** 08-01-owasp-llm-top-10, 08-04-sensitive-info-disclosure
**Time:** ~45 min
**Phase:** 08 - Security and Guardrails

## Learning Objectives

- List the PII categories detectable by regex vs. those requiring semantic understanding
- Build a PIIRedactor with patterns for email, phone, SSN, and credit card numbers
- Implement pseudonymization as an alternative to full redaction
- Add an LLM-based fallback for contextual PII that regex cannot catch
- Explain when to use presidio for production-grade PII detection

---

## MOTTO

PII in model context means PII in your logs, your traces, and potentially your model's training data. Redact before it enters.

---

## THE PROBLEM

Your company deploys an AI assistant for HR managers. Employees submit support tickets through the assistant. Within six weeks, three privacy incidents occur:

1. A ticket contains an employee's social security number (SSN). The assistant processes it, the SSN appears in your LLM observability traces, and your Langfuse dashboard now contains SSNs visible to your entire engineering team.

2. A manager pastes a performance review into the chat that includes names, salaries, and medical leave details. This context goes into the model's context window and appears verbatim in the generated summary that gets emailed to additional stakeholders.

3. An employee mentions "call me at my direct line: 555-867-5309" in a ticket. The model includes this phone number in a response summary that is logged to your data warehouse, which retains data for 7 years.

None of these incidents required a security breach. The data was processed by a system that treated every string as equally safe to retain. The fix is to detect and redact PII before it enters the model context and before it appears in logs.

Two approaches exist. Regex catches structured PII: SSN always looks like NNN-NN-NNNN, a credit card always follows the Luhn-detectable 16-digit pattern, an email always matches `[text]@[domain]`. It misses contextual PII: "call John at the downtown office" contains a name and an implicit location that no regex will catch.

---

## THE CONCEPT

### PII Categories and Detection Methods

```
CATEGORY         FORMAT            DETECTION METHOD     REDACTION TARGET
---------------------------------------------------------------------------
Email address    user@domain.com   Regex (reliable)     [EMAIL]
Phone number     +1-NNN-NNN-NNNN   Regex (reliable)     [PHONE]
US SSN           NNN-NN-NNNN       Regex (reliable)     [SSN]
Credit card      16 digits/groups  Regex + Luhn check   [CREDIT_CARD]
IP address       NNN.NNN.NNN.NNN   Regex (reliable)     [IP_ADDRESS]
---------------------------------------------------------------------------
Person name      "John Smith"      NER / LLM required   [NAME]
Street address   "123 Main St"     NER / LLM required   [ADDRESS]
Organization     "Acme Corp"       NER / LLM required   [ORG]
Medical info     Context-dependent LLM required          [MEDICAL]
---------------------------------------------------------------------------
```

### Redaction vs. Pseudonymization

Two strategies for handling detected PII:

```
REDACTION                         PSEUDONYMIZATION
---------------------------------------------------
Replace with label:               Replace with consistent fake:
  john.smith@corp.com               user_0042@example.com
  -> [EMAIL]                        name_007 (always the same for "John Smith")

Pros: simple, no data retained    Pros: context preserved for analysis
Cons: breaks conversational        Cons: mapping table must be stored securely
      context when the model
      needs to reference the
      entity again

Use for: logs, traces             Use for: model context where coherence matters
         external APIs                     anonymized datasets
         training data
```

### Where to Apply PII Redaction

```
User Input -> [PII Redact] -> Model Context -> Model -> Output -> [PII Redact] -> Response/Log
                                                                        |
                                                               Logs should never
                                                               contain original PII
```

Apply redaction at two points: before the input enters the model context (protect the model), and before the output is logged or stored (protect your data pipeline).

---

## BUILD IT

### Step 1: Regex patterns for structured PII

```python
# code/main.py
"""
PII Detection and Redaction - Phase 08 Lesson 08
appliedaifromscratch.com

Demonstrates: PIIRedactor with regex patterns and LLM fallback.
Regex handles structured PII (email, phone, SSN, credit card).
LLM handles contextual PII (names, addresses) in high-risk pipelines.

pip install anthropic
"""

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
from typing import Iterator


@dataclass
class PIIMatch:
    """A detected PII instance in text."""
    category: str          # e.g. "email", "ssn"
    original: str          # the matched text
    start: int             # character offset in original text
    end: int               # character offset in original text
    redacted_label: str    # e.g. "[EMAIL]"


# ---------------------------------------------------------------------------
# Regex patterns for structured PII
# ---------------------------------------------------------------------------
# Ordered by specificity: more specific patterns before less specific ones.

_PII_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # Credit card: 13-16 digits in groups (Visa, MC, Amex, Discover)
    # Must come before generic number patterns.
    (
        "credit_card",
        re.compile(
            r"\b(?:4[0-9]{12}(?:[0-9]{3})?|"           # Visa
            r"(?:5[1-5][0-9]{2}|222[1-9]|22[3-9][0-9]|2[3-6][0-9]{2}|27[01][0-9]|2720)[0-9]{12}|"  # Mastercard
            r"3[47][0-9]{13}|"                           # Amex
            r"(?:6011|65[0-9]{2}|64[4-9][0-9])[0-9]{12})\b",  # Discover
        ),
        "[CREDIT_CARD]",
    ),
    # US Social Security Number: NNN-NN-NNNN or NNN NN NNNN
    (
        "ssn",
        re.compile(r"\b(?!000|666|9\d{2})\d{3}[-\s](?!00)\d{2}[-\s](?!0000)\d{4}\b"),
        "[SSN]",
    ),
    # Email address
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL]",
    ),
    # Phone number: US formats +1-NNN-NNN-NNNN, (NNN) NNN-NNNN, NNN.NNN.NNNN
    (
        "phone",
        re.compile(
            r"(?:\+?1[-.\s]?)?"        # optional country code
            r"(?:\(?\d{3}\)?[-.\s]?)"  # area code
            r"\d{3}[-.\s]?\d{4}\b"
        ),
        "[PHONE]",
    ),
    # IPv4 address
    (
        "ip_address",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
            r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
        ),
        "[IP_ADDRESS]",
    ),
]
```

### Step 2: The PIIRedactor class

```python
class PIIRedactor:
    """
    Detects and redacts structured PII using regex patterns.
    Optionally falls back to an LLM for contextual PII detection.

    Usage:
        redactor = PIIRedactor()
        clean_text = redactor.redact("Contact john@acme.com or call 555-123-4567")
        # -> "Contact [EMAIL] or call [PHONE]"
    """

    def __init__(
        self,
        patterns: list[tuple[str, re.Pattern, str]] | None = None,
        pseudonymize: bool = False,
    ):
        """
        Args:
            patterns: List of (category, compiled_regex, label) tuples.
                      Defaults to _PII_PATTERNS.
            pseudonymize: If True, replace PII with consistent pseudonyms
                          instead of generic labels.
        """
        self._patterns = patterns if patterns is not None else _PII_PATTERNS
        self._pseudonymize = pseudonymize
        self._pseudo_map: dict[str, str] = {}  # original -> pseudonym
        self._counters: dict[str, int] = {}     # category -> count

    def detect(self, text: str) -> list[PIIMatch]:
        """
        Return all PII matches in text, sorted by start position.
        Does not modify the text.
        """
        matches: list[PIIMatch] = []
        for category, pattern, label in self._patterns:
            for m in pattern.finditer(text):
                matches.append(PIIMatch(
                    category=category,
                    original=m.group(),
                    start=m.start(),
                    end=m.end(),
                    redacted_label=label,
                ))
        # Sort by start position; for overlapping matches, keep the earlier one
        matches.sort(key=lambda m: (m.start, -len(m.original)))
        return self._remove_overlaps(matches)

    def redact(self, text: str) -> str:
        """
        Replace detected PII with labels or pseudonyms.
        Processes matches right-to-left to preserve character offsets.
        """
        matches = self.detect(text)
        # Process right-to-left so earlier replacements don't shift later offsets
        result = text
        for match in reversed(matches):
            replacement = self._get_replacement(match)
            result = result[:match.start] + replacement + result[match.end:]
        return result

    def redact_report(self, text: str) -> tuple[str, list[dict]]:
        """
        Return (redacted_text, list_of_redactions).
        The report shows what was found and replaced, useful for auditing.
        """
        matches = self.detect(text)
        redacted = self.redact(text)
        report = [
            {
                "category": m.category,
                "original": m.original[:4] + "****",  # show only first 4 chars in report
                "label": m.redacted_label,
                "position": (m.start, m.end),
            }
            for m in matches
        ]
        return redacted, report

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _get_replacement(self, match: PIIMatch) -> str:
        if not self._pseudonymize:
            return match.redacted_label

        # Pseudonymization: consistent mapping for the same original value
        if match.original not in self._pseudo_map:
            count = self._counters.get(match.category, 0) + 1
            self._counters[match.category] = count
            self._pseudo_map[match.original] = f"{match.category}_{count:04d}"
        return self._pseudo_map[match.original]

    @staticmethod
    def _remove_overlaps(matches: list[PIIMatch]) -> list[PIIMatch]:
        """Remove overlapping matches, keeping the first (leftmost) match."""
        result: list[PIIMatch] = []
        last_end = -1
        for m in matches:
            if m.start >= last_end:
                result.append(m)
                last_end = m.end
        return result
```

### Step 3: LLM fallback for contextual PII

```python
import anthropic
import json

LLM_PII_PROMPT = """You are a PII detection system. Identify all personally identifiable information in the following text.

Return a JSON array of detections. Each detection has:
- "type": one of [person_name, street_address, organization, medical_info, other_pii]
- "text": the exact substring containing PII
- "reason": one sentence explaining why this is PII

Return only the JSON array, no other text. Return [] if no PII is found.

Text to analyze:
"""


def llm_pii_check(
    text: str,
    client: anthropic.Anthropic,
) -> list[dict]:
    """
    Use Claude to detect contextual PII that regex cannot catch.
    Returns list of detected PII with type, text, and reason.

    Use for: names, addresses, organizational affiliations, medical information.
    Do not use for: structured PII (email, SSN) - regex is faster and cheaper.
    """
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": LLM_PII_PROMPT + text[:3000],
            }
        ],
    )

    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []  # fail open for PII detection (don't block legitimate requests)


def redact_with_llm_fallback(
    text: str,
    redactor: PIIRedactor,
    client: anthropic.Anthropic,
) -> tuple[str, list[dict]]:
    """
    Full PII redaction pipeline:
    1. Regex handles structured PII (fast, $0)
    2. LLM handles contextual PII (slow, API cost)

    Returns (fully_redacted_text, combined_detection_report).
    """
    # Step 1: regex redaction
    regex_redacted, regex_report = redactor.redact_report(text)

    # Step 2: LLM check on the regex-redacted text
    # Pass the already-redacted text so the LLM sees [EMAIL] not the actual email
    llm_detections = llm_pii_check(regex_redacted, client)

    # Step 3: replace LLM-detected spans in the regex-redacted text
    result = regex_redacted
    for detection in llm_detections:
        pii_text = detection.get("text", "")
        pii_type = detection.get("type", "other_pii").upper()
        if pii_text and pii_text in result:
            result = result.replace(pii_text, f"[{pii_type}]", 1)

    return result, regex_report + llm_detections
```

> **Real-world check:** Your PIIRedactor successfully redacts SSNs and emails. A user sends: "Please process the claim for Margaret Chen, born 1975, living near Riverside Drive." Your regex finds nothing - no SSN, no email, no phone. The LLM fallback detects "Margaret Chen" as a person name and "Riverside Drive" as an address fragment. But your system is deployed as a one-way log scrubber, not a user-facing chat. Calling the LLM for every log line costs $300/month and adds 500ms per line. What is the right tradeoff? For log scrubbing of high-volume, low-risk data, regex-only is appropriate. Add the LLM fallback only for the specific log categories that contain high-risk PII (HR tickets, medical records, legal documents). Segment by data sensitivity, not by volume.

---

## USE IT

### presidio for production-grade PII detection

Microsoft's `presidio` provides a full NER-based PII analyzer that handles names, addresses, and many structured types in one package:

```python
# pip install presidio-analyzer presidio-anonymizer
# python -m spacy download en_core_web_lg
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

def redact_with_presidio(text: str, language: str = "en") -> str:
    results = analyzer.analyze(text=text, language=language)
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized.text

# Example
text = "Send the results to john.doe@company.com or call (555) 123-4567."
print(redact_with_presidio(text))
# -> "Send the results to <EMAIL_ADDRESS> or call <PHONE_NUMBER>."
```

```
CUSTOM REGEX REDACTOR          PRESIDIO
-----------------------------------------------------
No dependencies (stdlib)       pip install + spacy model (~300MB)
Fast: regex only               Slower: NER model on CPU ~100ms
Catches structured PII only    Catches names, addresses, orgs
Works offline                  Works offline
Customizable patterns          Customizable recognizers + NLP pipeline
Zero ML overhead               ML-based NER (higher recall for names)
```

Presidio is the right choice when:
- You need to detect person names and addresses reliably
- Your data contains mixed languages (presidio supports 20+ languages)
- You want a battle-tested, audited library for compliance purposes

> **Perspective shift:** Your CISO asks "why can't we just instruct the model to never output PII in its responses? That seems simpler than a redaction pipeline." What does a model-level instruction miss that a code-level redactor catches? A model instruction affects output. It does not affect how PII is handled once it enters the model's context window. The SSN in the input is already in the model's context, already in your traces, already in your LLM observability dashboard. The redactor protects upstream of the model call. Additionally, model instructions can be bypassed via prompt injection. A code-level redactor runs outside the model and cannot be bypassed by manipulating the model's behavior.

---

## SHIP IT

The artifact for this lesson is `outputs/skill-pii-redactor.md`: a PII detection and redaction reference with regex patterns, pseudonymization strategy, and presidio integration guide.

---

## EVALUATE IT

**Recall test (structured PII):** Create a test set of 50 strings, each containing exactly one PII instance in a different format. Run through the redactor. Every instance must be detected. Any miss is a false negative. Expand or fix the corresponding regex pattern.

**Precision test:** Run 50 benign strings (order numbers, product codes, zip codes) through the redactor. Count false positives (non-PII flagged as PII). False positive rate above 1% creates friction. Add negative lookahead patterns to reduce over-matching on numbers.

**Pseudonymization consistency test:** Process the same email address in two different strings. The pseudonym must be identical in both cases. If not, the mapping is not deterministic. This matters when the model needs to maintain identity coherence across turns.

**Log audit:** Weekly, sample 10 raw log entries from your LLM observability system. If any contain SSN-format strings, email addresses, or phone numbers, your redaction pipeline has a gap. Identify which code path bypassed redaction and add a redaction call.

**Presidio vs. regex coverage:** Run both your regex redactor and presidio on the same 100-sentence test set. Compare recall. Any case where presidio catches PII that your regex missed is a candidate for adding a custom pattern or switching the pipeline to presidio.
