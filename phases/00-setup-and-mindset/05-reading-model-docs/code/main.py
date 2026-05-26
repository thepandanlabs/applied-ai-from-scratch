"""
Lesson 05: Reading Model Docs - Context Windows, Pricing, Limits
Phase 00: Setup and Mindset

Reads a hardcoded model spec dict and computes:
  - Max document size you can fit in the context window
  - Cost per 1000 requests at typical token budgets
  - Days until deprecation

No API key required.
"""

from datetime import date, datetime

# ---------------------------------------------------------------------------
# Model spec dicts
# Source: https://www.anthropic.com/pricing  (verify before shipping)
# ---------------------------------------------------------------------------

HAIKU_SPEC = {
    "model_id": "claude-3-5-haiku-20241022",
    "context_window_tokens": 200_000,
    "max_output_tokens": 8_192,
    "pricing": {
        "input_per_million": 0.80,
        "output_per_million": 4.00,
        "cache_read_per_million": 0.08,
        "cache_write_per_million": 1.00,
    },
    "rate_limits": {
        "rpm": 50,
        "tpm": 50_000,
        "rpday": 1_000,
    },
    "deprecation_date": "2025-12-01",
    "modalities": ["text"],
    "knowledge_cutoff": "2024-07",
}

SONNET_SPEC = {
    "model_id": "claude-sonnet-4-5",
    "context_window_tokens": 200_000,
    "max_output_tokens": 64_000,
    "pricing": {
        "input_per_million": 3.00,
        "output_per_million": 15.00,
        "cache_read_per_million": 0.30,
        "cache_write_per_million": 3.75,
    },
    "rate_limits": {
        "rpm": 50,
        "tpm": 80_000,
        "rpday": 5_000,
    },
    "deprecation_date": None,
    "modalities": ["text", "vision"],
    "knowledge_cutoff": "2024-04",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOKENS_PER_WORD = 1.33  # rough approximation for English prose


def max_document_words(spec: dict, reserved_for_output: int = 1000) -> int:
    """
    How many words fit in a single request?

    We subtract a system prompt budget and the reserved output tokens
    so the returned number is a safe estimate for the document payload.
    """
    system_prompt_tokens = 200
    usable_input_tokens = (
        spec["context_window_tokens"]
        - reserved_for_output
        - system_prompt_tokens
    )
    return int(usable_input_tokens / TOKENS_PER_WORD)


def max_output_words(spec: dict) -> int:
    """Hard cap on response length regardless of context window size."""
    return int(spec["max_output_tokens"] / TOKENS_PER_WORD)


def cost_per_request(
    spec: dict,
    avg_input_tokens: int,
    avg_output_tokens: int,
    cache_hit_rate: float = 0.0,
) -> float:
    """
    Estimated USD cost for one API request.

    Args:
        spec: Model spec dict.
        avg_input_tokens: Tokens in the prompt (system + user).
        avg_output_tokens: Tokens in the response.
        cache_hit_rate: Fraction of input tokens served from cache (0.0 to 1.0).

    Returns:
        Estimated cost in USD.
    """
    pricing = spec["pricing"]
    fresh_input = avg_input_tokens * (1 - cache_hit_rate)
    cached_input = avg_input_tokens * cache_hit_rate

    input_cost = (fresh_input / 1_000_000) * pricing["input_per_million"]
    cache_cost = (cached_input / 1_000_000) * pricing["cache_read_per_million"]
    output_cost = (avg_output_tokens / 1_000_000) * pricing["output_per_million"]

    return input_cost + cache_cost + output_cost


def cost_per_thousand_requests(
    spec: dict,
    avg_input_tokens: int,
    avg_output_tokens: int,
    cache_hit_rate: float = 0.0,
) -> float:
    """Scale a per-request cost to 1,000 requests."""
    return cost_per_request(spec, avg_input_tokens, avg_output_tokens, cache_hit_rate) * 1_000


def days_until_deprecation(spec: dict) -> int | None:
    """
    Days until this model version stops accepting requests.

    Returns None if no deprecation date is set.
    Returns a negative number if the date has already passed.
    """
    if not spec.get("deprecation_date"):
        return None
    dep_date = datetime.strptime(spec["deprecation_date"], "%Y-%m-%d").date()
    today = date.today()
    return (dep_date - today).days


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_model_report(spec: dict) -> None:
    """Print a production-readiness summary for one model spec."""
    print(f"\n{'='*62}")
    print(f"  {spec['model_id']}")
    print(f"{'='*62}")

    max_words = max_document_words(spec)
    max_out = max_output_words(spec)

    print(f"\nCapacity")
    print(f"  Context window : {spec['context_window_tokens']:>10,} tokens  (input budget)")
    print(f"  Max output     : {spec['max_output_tokens']:>10,} tokens  (response cap)")
    print(f"  Max doc size   : ~{max_words:>8,} words   (~{max_words/250:.0f} pages)")
    print(f"  Max output     : ~{max_out:>8,} words")
    print()

    # Cost estimates at three usage tiers
    short_req_cost = cost_per_thousand_requests(spec, 500, 200)
    long_req_cost = cost_per_thousand_requests(spec, 5_000, 500)
    cached_req_cost = cost_per_thousand_requests(spec, 5_000, 500, cache_hit_rate=0.8)

    print(f"Pricing (per 1,000 requests)")
    print(f"  Short prompts  (~500 in / 200 out tokens)   : ${short_req_cost:.2f}")
    print(f"  Long prompts   (~5k in  / 500 out tokens)   : ${long_req_cost:.2f}")
    print(f"  Long + 80% cache hit (same lengths)         : ${cached_req_cost:.2f}")
    savings_pct = (1 - cached_req_cost / long_req_cost) * 100
    print(f"  Cache savings  : {savings_pct:.0f}% reduction")
    print()

    rl = spec["rate_limits"]
    print(f"Rate limits")
    print(f"  RPM   : {rl['rpm']}")
    print(f"  TPM   : {rl['tpm']:,}")
    print(f"  RPDAY : {rl.get('rpday', 'unlimited')}")
    print()

    days = days_until_deprecation(spec)
    if days is None:
        dep_msg = "No deprecation date set"
    elif days < 0:
        dep_msg = f"ALREADY DEPRECATED ({abs(days)} days ago) - migrate immediately"
    elif days < 90:
        dep_msg = f"WARNING: {days} days remaining - plan migration now"
    elif days < 180:
        dep_msg = f"{days} days remaining - schedule migration"
    else:
        dep_msg = f"{days} days remaining"
    print(f"Deprecation: {dep_msg}")

    print(f"\nModalities : {', '.join(spec['modalities'])}")
    print(f"Knowledge  : cutoff {spec.get('knowledge_cutoff', 'unknown')}")


def compare_for_long_output(spec_a: dict, spec_b: dict) -> None:
    """
    Print a focused comparison showing which model supports longer outputs.
    Useful when your use case requires generating long documents.
    """
    print(f"\n{'='*62}")
    print("  Long-output comparison")
    print(f"{'='*62}")
    for spec in [spec_a, spec_b]:
        print(f"\n  {spec['model_id']}")
        print(f"    Max output : {spec['max_output_tokens']:,} tokens "
              f"(~{max_output_words(spec):,} words)")
        cost = cost_per_thousand_requests(spec, 5_000, spec["max_output_tokens"])
        print(f"    Cost at max output (1k req): ${cost:.2f}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print_model_report(HAIKU_SPEC)
    print_model_report(SONNET_SPEC)
    compare_for_long_output(HAIKU_SPEC, SONNET_SPEC)

    print("\n\nKey insight:")
    print("  A 200k context window with an 8k max output means you can READ")
    print("  a 196k-token document but only WRITE an 8k-token response.")
    print("  Context window and max output are separate, independent limits.")
