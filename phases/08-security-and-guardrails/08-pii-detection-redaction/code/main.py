"""
PII Detection and Redaction - Phase 08 Lesson 08
appliedaifromscratch.com

Demonstrates:
  - Regex-based detection for structured PII (email, phone, SSN, credit card, IP)
  - Redaction (replace with labels) and pseudonymization (replace with consistent fakes)
  - LLM-based fallback for contextual PII (names, addresses)
  - Full pipeline combining both approaches

Run:
    python main.py

Requires:
    pip install anthropic  (for LLM fallback demo only)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

import anthropic


# ===========================================================================
# PII data types
# ===========================================================================

@dataclass
class PIIMatch:
    """One detected PII instance."""
    category: str       # "email", "ssn", "phone", "credit_card", "ip_address"
    original: str       # exact matched text
    start: int          # character offset in source text
    end: int            # character offset (exclusive)
    label: str          # replacement label, e.g. "[EMAIL]"


# ===========================================================================
# Regex patterns for structured PII
# ===========================================================================
# Order matters: more specific patterns must come before less specific ones.
# Credit card patterns before generic digit sequences; SSN before generic
# NNN-NN-NNNN-looking numbers.

_STRUCTURED_PII_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # -- Credit card numbers (must come before phone to avoid overlap) --
    # Visa (13 or 16 digits), Mastercard, Amex (15 digits), Discover
    (
        "credit_card",
        re.compile(
            r"\b(?:"
            r"4[0-9]{12}(?:[0-9]{3})?"                           # Visa
            r"|(?:5[1-5][0-9]{2}|222[1-9]|22[3-9][0-9]|2[3-6][0-9]{2}|27[01][0-9]|2720)[0-9]{12}"  # Mastercard
            r"|3[47][0-9]{13}"                                    # Amex
            r"|(?:6011|65[0-9]{2}|64[4-9][0-9])[0-9]{12}"       # Discover
            r")\b"
        ),
        "[CREDIT_CARD]",
    ),
    # -- US Social Security Number: NNN-NN-NNNN --
    # Excludes invalid SSN prefixes (000, 666, 900-999)
    (
        "ssn",
        re.compile(
            r"\b(?!000|666|9\d{2})\d{3}"   # area number
            r"[-\s](?!00)\d{2}"             # group number
            r"[-\s](?!0000)\d{4}\b"         # serial number
        ),
        "[SSN]",
    ),
    # -- Email address --
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL]",
    ),
    # -- Phone numbers: US and international formats --
    # Matches: +1-555-867-5309, (555) 867-5309, 555.867.5309, 5558675309
    (
        "phone",
        re.compile(
            r"(?:\+?1[-.\s]?)?"             # optional country code +1
            r"(?:\(?\d{3}\)?[-.\s]?)"       # area code
            r"\d{3}[-.\s]?\d{4}\b"
        ),
        "[PHONE]",
    ),
    # -- IPv4 address --
    (
        "ip_address",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
        "[IP_ADDRESS]",
    ),
]


# ===========================================================================
# PIIRedactor
# ===========================================================================

class PIIRedactor:
    """
    Detects and redacts structured PII using regex patterns.

    Two modes:
      - Redaction: replace with generic label ([EMAIL], [SSN], etc.)
      - Pseudonymization: replace with consistent fake (email_0001, ssn_0002, etc.)

    Pseudonymization preserves referential consistency across a conversation:
    the same email always maps to the same pseudonym within a session.

    Usage:
        r = PIIRedactor()
        print(r.redact("Call me at 555-123-4567 or email hi@example.com"))
        # -> "Call me at [PHONE] or email [EMAIL]"

        r2 = PIIRedactor(pseudonymize=True)
        print(r2.redact("Email jane@corp.com or jane@corp.com again"))
        # -> "Email email_0001 or email_0001 again" (consistent mapping)
    """

    def __init__(
        self,
        patterns: list[tuple[str, re.Pattern, str]] | None = None,
        pseudonymize: bool = False,
    ):
        self._patterns = patterns if patterns is not None else _STRUCTURED_PII_PATTERNS
        self._pseudonymize = pseudonymize
        self._pseudo_map: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def detect(self, text: str) -> list[PIIMatch]:
        """Find all PII instances. Returns matches sorted by position, no overlaps."""
        all_matches: list[PIIMatch] = []
        for category, pattern, label in self._patterns:
            for m in pattern.finditer(text):
                all_matches.append(PIIMatch(
                    category=category,
                    original=m.group(),
                    start=m.start(),
                    end=m.end(),
                    label=label,
                ))
        all_matches.sort(key=lambda x: (x.start, -(x.end - x.start)))
        return _remove_overlaps(all_matches)

    def redact(self, text: str) -> str:
        """Return text with all PII replaced by labels or pseudonyms."""
        matches = self.detect(text)
        # Process right-to-left to preserve offsets after replacements
        result = text
        for m in reversed(matches):
            result = result[:m.start] + self._replacement(m) + result[m.end:]
        return result

    def redact_report(self, text: str) -> tuple[str, list[dict]]:
        """
        Return (redacted_text, detection_report).
        Report shows what was detected (first 4 chars shown, rest masked).
        """
        matches = self.detect(text)
        redacted = self.redact(text)
        report = [
            {
                "category": m.category,
                "preview": m.original[:4] + "****" if len(m.original) > 4 else "****",
                "label": m.label,
                "position": (m.start, m.end),
            }
            for m in matches
        ]
        return redacted, report

    def _replacement(self, match: PIIMatch) -> str:
        if not self._pseudonymize:
            return match.label
        if match.original not in self._pseudo_map:
            n = self._counters.get(match.category, 0) + 1
            self._counters[match.category] = n
            self._pseudo_map[match.original] = f"{match.category}_{n:04d}"
        return self._pseudo_map[match.original]


def _remove_overlaps(matches: list[PIIMatch]) -> list[PIIMatch]:
    """Keep the leftmost match when two spans overlap."""
    result: list[PIIMatch] = []
    last_end = -1
    for m in matches:
        if m.start >= last_end:
            result.append(m)
            last_end = m.end
    return result


# ===========================================================================
# LLM fallback for contextual PII
# ===========================================================================

_LLM_PII_PROMPT = """You are a PII detection system. Identify all personally identifiable information in the text below.

Return a JSON array. Each entry has:
- "type": one of [person_name, street_address, organization, medical_info, other_pii]
- "text": the exact substring in the text that contains PII
- "reason": one sentence explaining why this is PII

Return only the JSON array, no other text. Return [] if no PII is found.

Text:
"""


def llm_pii_detect(text: str, client: anthropic.Anthropic) -> list[dict]:
    """
    Use Claude to detect contextual PII that regex cannot catch:
    person names, street addresses, organizations, medical information.

    Returns a list of detections. Returns [] on error (fail open:
    we do not want to block legitimate requests because the LLM errored).
    """
    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            messages=[
                {"role": "user", "content": _LLM_PII_PROMPT + text[:3000]}
            ],
        )
        raw = response.content[0].text.strip()
        return json.loads(raw)
    except Exception:
        return []


def redact_with_llm_fallback(
    text: str,
    redactor: PIIRedactor,
    client: anthropic.Anthropic,
) -> tuple[str, list[dict]]:
    """
    Two-stage PII redaction:
    Stage 1: regex handles structured PII (fast, free)
    Stage 2: LLM handles contextual PII on the already-redacted text

    Returns (fully_redacted_text, combined_detection_report).
    """
    # Stage 1: regex
    stage1_text, regex_report = redactor.redact_report(text)

    # Stage 2: LLM on the partially-redacted text
    # Passing stage1_text means the LLM never sees the actual SSN/email values
    llm_detections = llm_pii_detect(stage1_text, client)

    result = stage1_text
    for detection in llm_detections:
        pii_text = detection.get("text", "")
        pii_type = detection.get("type", "pii").upper()
        if pii_text and pii_text in result:
            result = result.replace(pii_text, f"[{pii_type}]", 1)

    return result, regex_report + llm_detections


# ===========================================================================
# Demo
# ===========================================================================

def demo_regex_redaction():
    print("=" * 60)
    print("Demo: Regex-based PII redaction")
    print("=" * 60)

    test_cases = [
        "Contact me at alice.smith@company.com for details.",
        "My SSN is 123-45-6789 and phone is (555) 867-5309.",
        "Card number: 4111111111111111, expires 12/27.",
        "Request came from IP 192.168.1.42 at 3pm.",
        "Call me at +1 800.555.0199 or 800-555-0100.",
        "No PII here: order number 78234, zip code 94102.",
    ]

    redactor = PIIRedactor()
    for text in test_cases:
        redacted = redactor.redact(text)
        print(f"\n  Input   : {text}")
        print(f"  Redacted: {redacted}")


def demo_pseudonymization():
    print("\n" + "=" * 60)
    print("Demo: Pseudonymization (consistent fake identifiers)")
    print("=" * 60)

    texts = [
        "Alice emailed help@example.com and cc'd help@example.com.",
        "Bob called 555-123-4567. Alice also has 555-123-4567 on file.",
        "New contact: carol@test.org and david@test.org.",
    ]

    redactor = PIIRedactor(pseudonymize=True)
    for text in texts:
        redacted = redactor.redact(text)
        print(f"\n  Input   : {text}")
        print(f"  Pseudo  : {redacted}")

    print("\n  Pseudonym map:")
    for original, pseudo in redactor._pseudo_map.items():
        masked = original[:3] + "****"
        print(f"    {masked:20s} -> {pseudo}")


def demo_detection_report():
    print("\n" + "=" * 60)
    print("Demo: Detection report")
    print("=" * 60)

    text = (
        "Patient John Doe, SSN 234-56-7890, "
        "email jdoe@hospital.org, phone 312-555-9876. "
        "Admitted from IP 10.0.0.5."
    )
    redactor = PIIRedactor()
    redacted, report = redactor.redact_report(text)

    print(f"\n  Input   : {text}")
    print(f"  Redacted: {redacted}")
    print("\n  Detections:")
    for r in report:
        print(f"    {r['category']:12s} | preview={r['preview']:12s} | pos={r['position']}")


def demo_llm_fallback():
    """Requires ANTHROPIC_API_KEY."""
    print("\n" + "=" * 60)
    print("Demo: LLM fallback for contextual PII")
    print("=" * 60)

    text = (
        "Please process the expense report for Sarah Johnson. "
        "She works at Acme Medical Group downtown and lives near Maple Street. "
        "Her employee ID is 78234."
    )

    print(f"\n  Input: {text}")

    client = anthropic.Anthropic()
    redactor = PIIRedactor()
    redacted, report = redact_with_llm_fallback(text, redactor, client)

    print(f"  Redacted: {redacted}")
    print(f"\n  Combined detections ({len(report)} total):")
    for item in report:
        if "category" in item:  # regex detection
            print(f"    [regex] {item['category']:12s} | {item['preview']}")
        else:  # LLM detection
            print(f"    [llm]   {item.get('type','?'):12s} | {item.get('text','?')[:30]} | {item.get('reason','')[:50]}")


if __name__ == "__main__":
    demo_regex_redaction()
    demo_pseudonymization()
    demo_detection_report()

    # Uncomment to run LLM fallback demo (requires ANTHROPIC_API_KEY):
    # demo_llm_fallback()
