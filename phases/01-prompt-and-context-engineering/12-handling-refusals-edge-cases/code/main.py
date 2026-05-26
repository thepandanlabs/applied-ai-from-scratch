"""
Lesson 12: Handling Refusals and Edge Cases
============================================
Demonstrates:
- Classifying model responses as safety / capability / ambiguity / success
- Targeted recovery strategies per refusal type
- Production monitoring pattern for refusal rates

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python main.py
"""

import os
import datetime
from enum import Enum
from dataclasses import dataclass
from collections import Counter

import anthropic

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"


# ---------------------------------------------------------------------------
# Refusal classification
# ---------------------------------------------------------------------------


class RefusalType(Enum):
    SUCCESS = "success"
    SAFETY = "safety"
    CAPABILITY = "capability"
    AMBIGUITY = "ambiguity"
    UNKNOWN = "unknown"


@dataclass
class RefusalResult:
    refusal_type: RefusalType
    raw_response: str
    confidence: str  # "high" | "medium" | "low"
    suggested_fix: str


SAFETY_SIGNALS = [
    "i can't help with",
    "i cannot help with",
    "i'm not able to help with",
    "i won't be able to",
    "that could cause harm",
    "that could be dangerous",
    "i'm unable to assist with",
    "content policy",
    "violates",
    "against my guidelines",
]

CAPABILITY_SIGNALS = [
    "i don't have access to",
    "i don't have real-time",
    "i can't access the internet",
    "i can't browse",
    "i don't have the ability to run",
    "i cannot execute",
    "i can't retrieve",
    "i don't have information after",
    "my knowledge cutoff",
    "i'm not able to access",
]

AMBIGUITY_SIGNALS = [
    "could you clarify",
    "could you specify",
    "could you provide more",
    "what do you mean by",
    "i need more context",
    "i need more information",
    "i'm not sure what you mean",
    "could you be more specific",
    "please clarify",
    "what exactly are you",
]


def classify_refusal(response_text: str) -> RefusalResult:
    """
    Classify a model response as success or a specific refusal type.
    Priority: safety > capability > ambiguity > unknown > success.
    """
    text_lower = response_text.lower()

    for signal in SAFETY_SIGNALS:
        if signal in text_lower:
            return RefusalResult(
                refusal_type=RefusalType.SAFETY,
                raw_response=response_text,
                confidence="high",
                suggested_fix=(
                    "Reframe the request to make the legitimate use case explicit. "
                    "If this is a false positive, add context about the professional "
                    "or educational purpose."
                ),
            )

    for signal in CAPABILITY_SIGNALS:
        if signal in text_lower:
            return RefusalResult(
                refusal_type=RefusalType.CAPABILITY,
                raw_response=response_text,
                confidence="high",
                suggested_fix=(
                    "Provide the required data directly in the prompt. "
                    "Example: instead of 'look up the current price', say "
                    "'the current price is $X; given this, calculate...'"
                ),
            )

    for signal in AMBIGUITY_SIGNALS:
        if signal in text_lower:
            return RefusalResult(
                refusal_type=RefusalType.AMBIGUITY,
                raw_response=response_text,
                confidence="high",
                suggested_fix=(
                    "Add a concrete example of expected output, OR add: "
                    "'If anything is unclear, make a reasonable assumption "
                    "and state it explicitly.'"
                ),
            )

    # Heuristic: very short responses from a system expecting structured output
    if len(response_text.strip()) < 30:
        return RefusalResult(
            refusal_type=RefusalType.UNKNOWN,
            raw_response=response_text,
            confidence="low",
            suggested_fix="Inspect the raw response. Unexpected format or silent failure.",
        )

    return RefusalResult(
        refusal_type=RefusalType.SUCCESS,
        raw_response=response_text,
        confidence="high",
        suggested_fix="",
    )


# ---------------------------------------------------------------------------
# Recovery loop
# ---------------------------------------------------------------------------


def call_with_fallback(
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 2,
) -> dict:
    """
    Call the model with targeted recovery on refusal detection.
    Returns audit trail of all attempts.
    """
    attempts = []
    current_system = system_prompt
    current_user = user_prompt
    text = ""
    result = None

    for attempt in range(max_retries + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=current_system,
            messages=[{"role": "user", "content": current_user}],
        )
        text = response.content[0].text
        result = classify_refusal(text)

        attempts.append({
            "attempt": attempt + 1,
            "refusal_type": result.refusal_type.value,
            "response_preview": text[:200],
        })

        if result.refusal_type == RefusalType.SUCCESS:
            return {
                "success": True,
                "response": text,
                "attempts": attempts,
            }

        if attempt == max_retries:
            break

        # Apply targeted recovery
        if result.refusal_type == RefusalType.CAPABILITY:
            current_user = (
                f"{current_user}\n\n"
                "Note: Do not attempt to access external resources. "
                "Work only with the information provided in this message."
            )
        elif result.refusal_type == RefusalType.AMBIGUITY:
            current_user = (
                f"{current_user}\n\n"
                "If anything is unclear, make a reasonable assumption, "
                "state your assumption explicitly at the top of your response, "
                "then complete the task."
            )
        elif result.refusal_type == RefusalType.SAFETY:
            # Do not auto-retry safety refusals
            break

    return {
        "success": False,
        "response": text,
        "refusal_type": result.refusal_type.value if result else "unknown",
        "suggested_fix": result.suggested_fix if result else "",
        "attempts": attempts,
    }


# ---------------------------------------------------------------------------
# Production monitoring
# ---------------------------------------------------------------------------


class RefusalMonitor:
    """
    Tracks refusal rates per prompt_id in-process.
    In production, emit these as metrics to your observability backend.
    """

    def __init__(self):
        self.counts: Counter = Counter()
        self.examples: dict[str, list] = {t.value: [] for t in RefusalType}

    def record(self, result: RefusalResult, prompt_id: str = "") -> None:
        key = result.refusal_type.value
        self.counts[key] += 1
        if len(self.examples[key]) < 5:
            self.examples[key].append({
                "prompt_id": prompt_id,
                "preview": result.raw_response[:100],
                "ts": datetime.datetime.utcnow().isoformat(),
            })

    def report(self) -> dict:
        total = sum(self.counts.values())
        if total == 0:
            return {"total": 0}
        return {
            "total": total,
            "rates": {k: round(v / total, 3) for k, v in self.counts.items()},
            "raw_counts": dict(self.counts),
        }


monitor = RefusalMonitor()


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------


TEST_CASES = [
    {
        "name": "Ambiguity: missing format spec",
        "system": "You are a data extractor. Extract structured data from text.",
        "user": "Extract the key information from this: John Smith, 45, works at Acme Corp.",
    },
    {
        "name": "Capability: implicit web access",
        "system": "You are a financial analyst.",
        "user": "What is the current stock price of Apple?",
    },
    {
        "name": "Capability: fixed by providing data",
        "system": "You are a financial analyst.",
        "user": (
            "Apple's stock price as of market close today was $189.43. "
            "Given this price and a P/E ratio of 28, what is the implied "
            "earnings per share? Show the calculation."
        ),
    },
    {
        "name": "Normal: well-formed extraction request",
        "system": (
            "You are a data extractor. Extract structured data from text. "
            "Return a JSON object with fields: name (string), age (integer), "
            "company (string). Return ONLY the JSON object, no explanation."
        ),
        "user": "Extract: John Smith, 45, works at Acme Corp.",
    },
]


def run_tests():
    print("=" * 60)
    print("REFUSAL DETECTION + RECOVERY TEST SUITE")
    print(f"Model: {MODEL}")
    print("=" * 60)

    for case in TEST_CASES:
        print(f"\n[TEST] {case['name']}")
        print(f"  User: {case['user'][:80]}")

        result = call_with_fallback(
            system_prompt=case["system"],
            user_prompt=case["user"],
        )

        status = "SUCCESS" if result["success"] else "REFUSAL (unresolved)"
        attempts = len(result["attempts"])
        print(f"  Status: {status}")
        print(f"  Attempts: {attempts}")

        if not result["success"]:
            print(f"  Refusal type: {result.get('refusal_type', 'n/a')}")
            print(f"  Suggested fix: {result.get('suggested_fix', '')[:120]}")
        else:
            print(f"  Response: {result['response'][:120]}")

        # Record in monitor
        final_type = result.get("refusal_type", "success") if not result["success"] else "success"
        monitor.record(
            RefusalResult(
                refusal_type=RefusalType(final_type),
                raw_response=result["response"],
                confidence="high",
                suggested_fix="",
            ),
            prompt_id=case["name"],
        )

    print("\n" + "=" * 60)
    print("REFUSAL MONITOR REPORT")
    print("=" * 60)
    report = monitor.report()
    print(f"Total calls: {report['total']}")
    if "rates" in report:
        for k, v in report["rates"].items():
            if v > 0:
                pct = v * 100
                print(f"  {k}: {pct:.0f}% ({report['raw_counts'][k]} calls)")


if __name__ == "__main__":
    run_tests()
