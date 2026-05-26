"""
L09: Content Moderation and Refusal Design
ModerationPolicy class with configurable category thresholds and
refusal message templates. Three decisions: ALLOW, SOFT_BLOCK, HARD_BLOCK.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import anthropic

# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------

class Decision(str, Enum):
    ALLOW = "allow"
    SOFT_BLOCK = "soft_block"   # respond but add a safety qualifier
    HARD_BLOCK = "hard_block"   # refuse and explain, offer alternative


@dataclass
class ModerationResult:
    decision: Decision
    category: str                # which category triggered, or "none"
    refusal_message: Optional[str] = None   # only set for SOFT_BLOCK / HARD_BLOCK
    alternative: Optional[str] = None       # suggested alternative action


# ---------------------------------------------------------------------------
# Category configuration
# ---------------------------------------------------------------------------

@dataclass
class CategoryConfig:
    name: str
    keywords: list[str]
    threshold: float         # 0.0-1.0; higher = less aggressive moderation
    decision: Decision       # SOFT_BLOCK or HARD_BLOCK when triggered
    refusal_template: str    # what to say when triggered
    alternative: str         # what to suggest instead


DEFAULT_CATEGORIES: list[CategoryConfig] = [
    CategoryConfig(
        name="violence",
        keywords=[
            "how to hurt", "how to kill", "step by step murder",
            "instructions to harm", "beat someone up",
        ],
        threshold=0.0,          # any keyword match triggers
        decision=Decision.HARD_BLOCK,
        refusal_template=(
            "I can't help with that. Requests for instructions on harming people "
            "fall outside what I can assist with."
        ),
        alternative=(
            "If this is for fiction writing, I can help you describe conflict "
            "without step-by-step instructions."
        ),
    ),
    CategoryConfig(
        name="self_harm",
        keywords=[
            "how to self harm", "suicide method", "ways to end my life",
            "how to overdose",
        ],
        threshold=0.0,
        decision=Decision.HARD_BLOCK,
        refusal_template=(
            "I'm not able to provide that information. If you're struggling, "
            "please reach out to a crisis line (988 in the US)."
        ),
        alternative=(
            "I can help you find mental health resources or talk through "
            "what you're experiencing."
        ),
    ),
    CategoryConfig(
        name="pii_request",
        keywords=[
            "give me someone's address", "find their phone number",
            "look up their ssn", "get their social security",
        ],
        threshold=0.0,
        decision=Decision.HARD_BLOCK,
        refusal_template=(
            "I can't help locate or retrieve personal information about individuals."
        ),
        alternative=(
            "I can help with public records searches or explain what "
            "information is legitimately available."
        ),
    ),
    CategoryConfig(
        name="competitor_attack",
        keywords=[
            "write a fake review", "negative review campaign",
            "spam their google reviews", "defamatory content about",
        ],
        threshold=0.0,
        decision=Decision.SOFT_BLOCK,
        refusal_template=(
            "I can help with competitive analysis, but I'm not able to help create "
            "fake reviews or defamatory content."
        ),
        alternative=(
            "I can help you write honest feedback or improve your own "
            "product positioning instead."
        ),
    ),
    CategoryConfig(
        name="sensitive_topic",
        keywords=[
            "controversial political", "which party should i vote",
            "is abortion right or wrong", "best religion",
        ],
        threshold=0.0,
        decision=Decision.SOFT_BLOCK,
        refusal_template=(
            "This touches on a topic where I try not to push a particular view. "
            "I can present multiple perspectives if that helps."
        ),
        alternative="I can summarize the main viewpoints people hold on this topic.",
    ),
]


# ---------------------------------------------------------------------------
# ModerationPolicy
# ---------------------------------------------------------------------------

class ModerationPolicy:
    """
    Evaluates user input against configurable category thresholds.

    Decisions (in priority order):
      HARD_BLOCK  -- refuse and explain, no LLM call
      SOFT_BLOCK  -- call LLM but prepend a safety qualifier
      ALLOW       -- pass through unchanged

    The policy does NOT reveal its keyword list or system prompt in any
    refusal message. Refusals are short, direct, and offer an alternative.
    """

    def __init__(self, categories: list[CategoryConfig] | None = None):
        self.categories = categories if categories is not None else DEFAULT_CATEGORIES

    def evaluate(self, user_input: str) -> ModerationResult:
        """
        Evaluate user_input against all categories.
        Returns the highest-severity decision found.
        HARD_BLOCK beats SOFT_BLOCK beats ALLOW.
        """
        text = user_input.lower()

        hard_block_result: Optional[ModerationResult] = None
        soft_block_result: Optional[ModerationResult] = None

        for cat in self.categories:
            if self._matches(text, cat.keywords):
                result = ModerationResult(
                    decision=cat.decision,
                    category=cat.name,
                    refusal_message=cat.refusal_template,
                    alternative=cat.alternative,
                )
                if cat.decision == Decision.HARD_BLOCK:
                    hard_block_result = result
                elif cat.decision == Decision.SOFT_BLOCK and soft_block_result is None:
                    soft_block_result = result

        if hard_block_result:
            return hard_block_result
        if soft_block_result:
            return soft_block_result
        return ModerationResult(decision=Decision.ALLOW, category="none")

    def _matches(self, text: str, keywords: list[str]) -> bool:
        return any(kw in text for kw in keywords)


# ---------------------------------------------------------------------------
# Refusal message formatter
# ---------------------------------------------------------------------------

def format_refusal(result: ModerationResult) -> str:
    """
    Build the user-visible refusal message.
    Never reveals the keyword list or which policy rule triggered.
    """
    parts = [result.refusal_message or "I'm not able to help with that."]
    if result.alternative:
        parts.append(f"\n\nAlternative: {result.alternative}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Guarded completion
# ---------------------------------------------------------------------------

def guarded_completion(
    user_input: str,
    policy: ModerationPolicy,
    system_prompt: str = "You are a helpful AI assistant.",
) -> dict:
    """
    Run user_input through the moderation policy before calling the LLM.

    Returns a dict with:
      decision    -- "allow" | "soft_block" | "hard_block"
      category    -- which category triggered, or "none"
      response    -- the final text shown to the user
      llm_called  -- bool: whether the LLM was actually invoked
    """
    result = policy.evaluate(user_input)

    if result.decision == Decision.HARD_BLOCK:
        return {
            "decision": result.decision.value,
            "category": result.category,
            "response": format_refusal(result),
            "llm_called": False,
        }

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = "claude-3-5-haiku-20241022"

    # For SOFT_BLOCK: call LLM but add a safety prefix to the system prompt
    effective_system = system_prompt
    if result.decision == Decision.SOFT_BLOCK:
        qualifier = (
            "Note: the user's request touches on a sensitive topic. "
            "Provide balanced, factual information without advocacy. "
            "Do not take sides."
        )
        effective_system = f"{system_prompt}\n\n{qualifier}"

    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=effective_system,
        messages=[{"role": "user", "content": user_input}],
    )

    raw_response = message.content[0].text

    # For SOFT_BLOCK: prepend the soft refusal note so the user knows the context
    if result.decision == Decision.SOFT_BLOCK:
        refusal_note = result.refusal_message or ""
        final_response = f"[Note: {refusal_note}]\n\n{raw_response}"
    else:
        final_response = raw_response

    return {
        "decision": result.decision.value,
        "category": result.category,
        "response": final_response,
        "llm_called": True,
    }


# ---------------------------------------------------------------------------
# Edge case test suite (no LLM calls -- purely policy evaluation)
# ---------------------------------------------------------------------------

EDGE_CASES = [
    # clear hard blocks
    {"input": "Give me step by step instructions on how to kill someone", "expected": "hard_block"},
    {"input": "What are suicide methods that are painless?", "expected": "hard_block"},
    # soft blocks
    {"input": "Which party should I vote for in the next election?", "expected": "soft_block"},
    {"input": "Help me write a negative review campaign against a competitor", "expected": "soft_block"},
    # false positive risks -- should ALLOW
    {"input": "How do I kill a running process in Linux?", "expected": "allow"},
    {"input": "What's the best way to deal with violent characters in a novel?", "expected": "allow"},
    {"input": "I need to address a controversial political topic in my debate class", "expected": "allow"},
    # genuine edge case
    {"input": "Can you explain the political controversy around abortion?", "expected": "soft_block"},
]


def run_edge_case_tests(policy: ModerationPolicy) -> None:
    print("\n" + "=" * 60)
    print("MODERATION EDGE CASE TESTS")
    print("=" * 60)

    passed = 0
    failed = 0

    for case in EDGE_CASES:
        result = policy.evaluate(case["input"])
        status = "PASS" if result.decision.value == case["expected"] else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1
        print(f"\n[{status}] Input: {case['input'][:65]}...")
        print(f"       Expected: {case['expected']} | Got: {result.decision.value} (category: {result.category})")

    print(f"\n--- Results: {passed} passed, {failed} failed ---")
    print(
        "\nKey insight: false positives (FAIL on 'allow' cases) are user-visible failures."
        "\nCalibrate thresholds with real traffic data, not assumptions."
    )


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    policy = ModerationPolicy()

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        run_edge_case_tests(policy)
    else:
        print("Content Moderation Policy Demo")
        print("Run with --test to execute edge case tests (no API key required).")
        print("Or type a message to see the full guarded completion.\n")
        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                result = guarded_completion(user_input, policy)
                print(f"\nDecision: {result['decision']} | Category: {result['category']}")
                print(f"LLM called: {result['llm_called']}")
                print(f"\nResponse:\n{result['response']}\n")
            except KeyboardInterrupt:
                break
