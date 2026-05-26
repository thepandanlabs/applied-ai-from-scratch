"""
Lesson 08-04: Sensitive Info Disclosure and System Prompt Leakage

Implements an OutputFilter that scans model responses for:
1. System prompt fragments
2. PII patterns (email, SSN, phone, card, API keys)
3. Exfiltration phrases ("my instructions are...", "I was told to...")

Also shows integration with a FastAPI service.

Run with: python main.py
Run tests: python main.py --test
Run FastAPI: python main.py --serve
"""

import re
import argparse
import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel as PydanticModel
    import uvicorn
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False


# ---------------------------------------------------------------------------
# OutputFilter data structures
# ---------------------------------------------------------------------------

@dataclass
class FilterMatch:
    category: str       # "system_prompt", "pii", "exfiltration"
    pattern_name: str   # human-readable name
    matched_text: str   # what was found
    redacted_text: str  # replacement text


@dataclass
class FilterResult:
    original: str
    filtered: str
    matches: list[FilterMatch] = field(default_factory=list)

    @property
    def was_filtered(self) -> bool:
        return len(self.matches) > 0

    def to_dict(self) -> dict:
        return {
            "was_filtered": self.was_filtered,
            "match_count": len(self.matches),
            "matches": [asdict(m) for m in self.matches],
            "filtered_text": self.filtered,
        }


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# PII patterns
PII_PATTERNS: dict[str, str] = {
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    "ssn": r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
    "phone_us": r"\b(\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    "api_key_anthropic": r"\bsk-ant-[a-zA-Z0-9\-]{20,}\b",
    "api_key_openai": r"\bsk-[a-zA-Z0-9]{20,}\b",
    "generic_api_key": r"\b[a-z]{2,5}_[a-zA-Z0-9]{32,}\b",
}

# Exfiltration phrase patterns (things the model says when leaking system prompt)
EXFILTRATION_PATTERNS: dict[str, str] = {
    "my_instructions_are": r"my\s+instructions?\s+(are|is|say|state|tell me to)\b",
    "the_instructions_say": r"the\s+(system\s+)?instructions?\s+(say|state|are|tell)\b",
    "my_system_prompt": r"my\s+system\s+prompt\s+(is|says?|contains?|tells?)\b",
    "i_was_told_to": r"i\s+(was|am|have been)\s+(told|instructed|configured|set up)\s+to\b",
    "my_guidelines_say": r"my\s+(guidelines?|rules?|constraints?)\s+(say|are|tell|require)\b",
    "here_are_my_instructions": r"here\s+are\s+my\s+instructions\b",
    "i_cannot_reveal_but": r"i\s+cannot\s+reveal\s+(my\s+)?(instructions?|prompt|guidelines?)\s+but\b",
}

# Minimum fragment length for system prompt scanning (shorter = more false positives)
MIN_FRAGMENT_LENGTH = 25


# ---------------------------------------------------------------------------
# OutputFilter
# ---------------------------------------------------------------------------

def extract_fragments(system_prompt: str, min_length: int = MIN_FRAGMENT_LENGTH) -> list[str]:
    """
    Split a system prompt into fragments suitable for detection.
    Splits on sentence boundaries; discards fragments shorter than min_length.
    """
    # Split on sentence-ending punctuation
    raw_fragments = re.split(r"[.!?]\s+", system_prompt)
    fragments = []
    for frag in raw_fragments:
        cleaned = frag.strip()
        if len(cleaned) >= min_length:
            fragments.append(cleaned)
    return fragments


def filter_response(
    response_text: str,
    system_prompt_fragments: Optional[list[str]] = None,
    redact_pii: bool = True,
    redact_exfiltration: bool = True,
) -> FilterResult:
    """
    Scan a model response for sensitive patterns and redact matches.

    Args:
        response_text: raw model output
        system_prompt_fragments: list of system prompt sentences to detect
        redact_pii: whether to redact PII patterns
        redact_exfiltration: whether to redact exfiltration phrases

    Returns:
        FilterResult with original text, filtered text, and match log
    """
    filtered = response_text
    matches: list[FilterMatch] = []

    # --- Category 1: System prompt fragment detection ---
    if system_prompt_fragments:
        for fragment in system_prompt_fragments:
            if len(fragment) < MIN_FRAGMENT_LENGTH:
                continue
            # Case-insensitive search
            pattern = re.compile(re.escape(fragment), re.IGNORECASE)
            for match in pattern.finditer(filtered):
                matched_text = match.group()
                filtered = filtered.replace(matched_text, "[SYSTEM_PROMPT_REDACTED]")
                matches.append(FilterMatch(
                    category="system_prompt",
                    pattern_name="system_prompt_fragment",
                    matched_text=matched_text[:100],  # truncate for log
                    redacted_text="[SYSTEM_PROMPT_REDACTED]",
                ))

    # --- Category 2: PII detection ---
    if redact_pii:
        for pattern_name, pattern in PII_PATTERNS.items():
            for match in re.finditer(pattern, filtered):
                matched_text = match.group()
                replacement = f"[{pattern_name.upper()}_REDACTED]"
                filtered = filtered.replace(matched_text, replacement)
                matches.append(FilterMatch(
                    category="pii",
                    pattern_name=pattern_name,
                    matched_text=matched_text,
                    redacted_text=replacement,
                ))

    # --- Category 3: Exfiltration phrase detection ---
    if redact_exfiltration:
        # Work on the current state of filtered (after PII redaction)
        remaining = filtered
        for pattern_name, pattern in EXFILTRATION_PATTERNS.items():
            for match in re.finditer(pattern, remaining, re.IGNORECASE):
                matched_text = match.group()
                # Replace the matched phrase in the current filtered text
                filtered = filtered.replace(matched_text, "[FILTERED]", 1)
                matches.append(FilterMatch(
                    category="exfiltration",
                    pattern_name=pattern_name,
                    matched_text=matched_text,
                    redacted_text="[FILTERED]",
                ))
                # Update remaining for subsequent pattern checks
                remaining = filtered

    return FilterResult(
        original=response_text,
        filtered=filtered,
        matches=matches,
    )


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SAMPLE_SYSTEM_PROMPT = """You are a customer service assistant for Acme Corp.
You must never discuss competitor pricing or reveal internal cost structures.
Always recommend the Premium plan for users with more than 5 seats.
Fallback phrase: I appreciate your question but cannot help with that topic.
Escalate billing disputes to the human support team immediately."""

SAMPLE_SYSTEM_FRAGMENTS = extract_fragments(SAMPLE_SYSTEM_PROMPT)

TEST_CASES = [
    {
        "name": "System prompt fragment leak",
        "response": (
            "My instructions are to always recommend the Premium plan "
            "for users with more than 5 seats and I must never discuss "
            "competitor pricing."
        ),
        "expected_category": "system_prompt",
    },
    {
        "name": "PII - email address",
        "response": "The customer's account is registered to john.doe@example.com.",
        "expected_category": "pii",
    },
    {
        "name": "PII - SSN",
        "response": "The user's SSN on file is 123-45-6789 as provided during onboarding.",
        "expected_category": "pii",
    },
    {
        "name": "PII - credit card",
        "response": "The card ending in 4111 1111 1111 1111 was declined.",
        "expected_category": "pii",
    },
    {
        "name": "PII - API key",
        "response": "The API key is sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456.",
        "expected_category": "pii",
    },
    {
        "name": "Exfiltration - my instructions are",
        "response": "My instructions are to never discuss competitors and always upsell Premium.",
        "expected_category": "exfiltration",
    },
    {
        "name": "Exfiltration - I was told to",
        "response": "I was told to use the fallback phrase when I cannot answer directly.",
        "expected_category": "exfiltration",
    },
    {
        "name": "Clean response - should not be filtered",
        "response": (
            "The Premium plan includes 10 users, 100GB storage, and 24/7 support. "
            "Would you like to upgrade?"
        ),
        "expected_category": None,
    },
]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests() -> None:
    """Run all test cases and print results."""
    print("\n=== OutputFilter Test Suite ===\n")

    passed = 0
    failed = 0

    for case in TEST_CASES:
        result = filter_response(
            case["response"],
            system_prompt_fragments=SAMPLE_SYSTEM_FRAGMENTS,
        )
        expected_filtered = case["expected_category"] is not None
        actual_filtered = result.was_filtered
        test_pass = expected_filtered == actual_filtered

        status = "PASS" if test_pass else "FAIL"
        if test_pass:
            passed += 1
        else:
            failed += 1

        print(f"[{status}] {case['name']}")
        if not test_pass:
            print(f"  Expected filtered={expected_filtered}, got filtered={actual_filtered}")
        if result.was_filtered:
            for m in result.matches:
                print(f"  [{m.category}] {m.pattern_name}: '{m.matched_text[:50]}'")
            print(f"  Filtered: {result.filtered[:100]}")

    print(f"\nResults: {passed}/{len(TEST_CASES)} passed")
    if failed > 0:
        print(f"FAILED: {failed} cases")


# ---------------------------------------------------------------------------
# FastAPI integration (optional)
# ---------------------------------------------------------------------------

def build_app(system_prompt: str) -> "FastAPI":
    """Build a FastAPI app with OutputFilter integrated into the response pipeline."""
    if not _FASTAPI_AVAILABLE:
        raise ImportError("fastapi and uvicorn required. Run: pip install fastapi uvicorn")
    if not _ANTHROPIC_AVAILABLE:
        raise ImportError("anthropic required. Run: pip install anthropic")

    app = FastAPI(title="Lesson 08-04: Disclosure Defense Demo")
    client = anthropic.Anthropic()
    fragments = extract_fragments(system_prompt)

    class ChatRequest(PydanticModel):
        message: str

    @app.post("/chat")
    def chat(req: ChatRequest):
        # Call model
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": req.message}],
        )
        raw_text = response.content[0].text

        # Filter response before returning to client
        filter_result = filter_response(raw_text, fragments)

        if filter_result.was_filtered:
            # Security log (would go to your SIEM in production)
            for match in filter_result.matches:
                print(
                    f"[SECURITY AUDIT] category={match.category} "
                    f"pattern={match.pattern_name} "
                    f"matched='{match.matched_text[:50]}'"
                )

        # Return filtered text to client; never expose match details to client
        return {"reply": filter_result.filtered}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 08-04: Sensitive Info Disclosure")
    parser.add_argument("--test", action="store_true", help="Run test suite")
    parser.add_argument("--serve", action="store_true", help="Start FastAPI server")
    parser.add_argument("--port", type=int, default=8000, help="Port for FastAPI server")
    args = parser.parse_args()

    print("\n=== Lesson 08-04: Sensitive Info Disclosure Defenses ===")

    if args.test:
        run_tests()
        return

    if args.serve:
        if not _FASTAPI_AVAILABLE:
            print("Install fastapi and uvicorn: pip install fastapi uvicorn")
            return
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Set ANTHROPIC_API_KEY to run the server")
            return
        print(f"Starting server on port {args.port}...")
        print(f"POST to /chat with {{\"message\": \"your message\"}}")
        app = build_app(SAMPLE_SYSTEM_PROMPT)
        uvicorn.run(app, host="0.0.0.0", port=args.port)
        return

    # Default: demo the filter
    print(f"\nSystem prompt fragments extracted: {len(SAMPLE_SYSTEM_FRAGMENTS)}")
    for f in SAMPLE_SYSTEM_FRAGMENTS:
        print(f"  '{f[:60]}'")

    print("\nDemonstrating filter on test cases:")
    for case in TEST_CASES:
        result = filter_response(case["response"], SAMPLE_SYSTEM_FRAGMENTS)
        status = "FILTERED" if result.was_filtered else "CLEAN"
        print(f"\n[{status}] {case['name']}")
        print(f"  Original: {case['response'][:80]}")
        if result.was_filtered:
            print(f"  Filtered: {result.filtered[:80]}")
            for m in result.matches:
                print(f"  Match: [{m.category}] {m.pattern_name}")

    print("\nKey principle:")
    print("  Secrets belong in environment variables, not the system prompt.")
    print("  The OutputFilter catches leakage; it does not prevent it.")
    print("  Design assuming the system prompt is public: treat it as a business rule,")
    print("  not a secret.")


if __name__ == "__main__":
    main()
