"""
Lesson 02: API Keys, Providers, and the 2026 Model Landscape

Demonstrates:
- Safe API key loading with python-dotenv
- ModelConfig dataclass with cost estimation
- A cost-aware model selector
- Proper error handling for authentication failures

Run with: uv run python main.py
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv
import anthropic


# ---------------------------------------------------------------------------
# ModelConfig
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    """Metadata for a single model, used for cost-aware routing."""
    provider: str
    model_id: str
    tier: str                       # "fast", "balanced", "powerful"
    input_cost_per_1m: float        # USD per 1M input tokens
    output_cost_per_1m: float       # USD per 1M output tokens
    context_window: int             # max tokens (input + output combined)
    notes: str = ""

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Return estimated USD cost for a single call."""
        input_cost = (input_tokens / 1_000_000) * self.input_cost_per_1m
        output_cost = (output_tokens / 1_000_000) * self.output_cost_per_1m
        return input_cost + output_cost

    def monthly_cost(self, input_tokens: int, output_tokens: int, calls_per_day: int) -> float:
        """Return estimated monthly cost at a given volume."""
        return self.estimate_cost(input_tokens, output_tokens) * calls_per_day * 30


# ---------------------------------------------------------------------------
# Model catalog (prices approximate as of 2026 -- verify before budgeting)
# ---------------------------------------------------------------------------

MODEL_CATALOG: dict[str, ModelConfig] = {
    "claude-haiku": ModelConfig(
        provider="anthropic",
        model_id="claude-3-5-haiku-20241022",
        tier="fast",
        input_cost_per_1m=0.80,
        output_cost_per_1m=4.00,
        context_window=200_000,
        notes="Best for classification, extraction, routing, high-volume tasks",
    ),
    "claude-sonnet": ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-5",
        tier="balanced",
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
        context_window=200_000,
        notes="Production workhorse for most AI features",
    ),
    "claude-opus": ModelConfig(
        provider="anthropic",
        model_id="claude-opus-4-5",
        tier="powerful",
        input_cost_per_1m=15.00,
        output_cost_per_1m=75.00,
        context_window=200_000,
        notes="Complex reasoning, long document synthesis, research",
    ),
    "gpt-4o-mini": ModelConfig(
        provider="openai",
        model_id="gpt-4o-mini",
        tier="fast",
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
        context_window=128_000,
        notes="OpenAI fast tier, very low cost",
    ),
    "gpt-4o": ModelConfig(
        provider="openai",
        model_id="gpt-4o",
        tier="balanced",
        input_cost_per_1m=2.50,
        output_cost_per_1m=10.00,
        context_window=128_000,
        notes="OpenAI production standard",
    ),
    "gemini-flash": ModelConfig(
        provider="gemini",
        model_id="gemini-2.0-flash",
        tier="fast",
        input_cost_per_1m=0.10,
        output_cost_per_1m=0.40,
        context_window=1_000_000,
        notes="Extremely fast and cheap with very long context window",
    ),
}


# ---------------------------------------------------------------------------
# Model selector
# ---------------------------------------------------------------------------

ROUTING_TABLE: dict[tuple[str, str], str] = {
    ("classification", "high"): "claude-haiku",
    ("classification", "low"): "claude-haiku",
    ("extraction", "high"): "claude-haiku",
    ("extraction", "low"): "claude-haiku",
    ("summarization", "high"): "claude-haiku",
    ("summarization", "low"): "claude-sonnet",
    ("generation", "high"): "claude-sonnet",
    ("generation", "low"): "claude-sonnet",
    ("reasoning", "high"): "claude-sonnet",
    ("reasoning", "low"): "claude-opus",
}


def select_model(task_type: str, token_volume: str = "low") -> ModelConfig:
    """
    Return a ModelConfig for the given task type and volume.
    token_volume: "high" = many calls per day, "low" = few calls per day.
    """
    key = ROUTING_TABLE.get((task_type, token_volume), "claude-sonnet")
    return MODEL_CATALOG[key]


# ---------------------------------------------------------------------------
# Key loading
# ---------------------------------------------------------------------------

def load_and_verify_key() -> str | None:
    """Load ANTHROPIC_API_KEY from .env and environment, return it or None."""
    load_dotenv()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("WARNING: ANTHROPIC_API_KEY not set.")
        print("  Create a .env file with: ANTHROPIC_API_KEY=sk-ant-...")
        return None
    masked = key[:8] + "..." + key[-4:]
    print(f"OK: ANTHROPIC_API_KEY loaded ({masked})")
    return key


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Lesson 02: API Keys and Model Landscape ===\n")

    # 1. Load the key
    api_key = load_and_verify_key()

    # 2. Print cost comparison table
    print("\n--- Model Tier Cost Comparison ---")
    print(f"{'Model':20} {'Tier':10} {'$/1M in':>10} {'$/1M out':>10} {'Context':>12}")
    print("-" * 65)
    for name, config in MODEL_CATALOG.items():
        print(
            f"{name:20} {config.tier:10} "
            f"${config.input_cost_per_1m:>9.2f} "
            f"${config.output_cost_per_1m:>9.2f} "
            f"{config.context_window:>12,}"
        )

    # 3. Show cost analysis for a real-world scenario
    print("\n--- Monthly Cost Estimate: 500 users/day, 1K in + 300 out tokens ---")
    for name in ["claude-haiku", "claude-sonnet", "claude-opus"]:
        config = MODEL_CATALOG[name]
        monthly = config.monthly_cost(1000, 300, 500)
        print(f"  {name:20}: ${monthly:,.2f}/month")

    # 4. Show routing decisions
    print("\n--- Model Selection Routing ---")
    for task in ["classification", "summarization", "reasoning"]:
        for vol in ["high", "low"]:
            config = select_model(task, vol)
            print(f"  {task:15} + {vol:4} volume -> {config.model_id}")

    # 5. Test authentication error handling
    print("\n--- Authentication Error Handling ---")
    saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        client = anthropic.Anthropic()
        client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=8,
            messages=[{"role": "user", "content": "ping"}],
        )
    except anthropic.AuthenticationError as e:
        print(f"OK: AuthenticationError caught as expected.")
        print(f"   Message: {str(e)[:80]}")
    finally:
        if saved_key:
            os.environ["ANTHROPIC_API_KEY"] = saved_key

    # 6. Make a real API call if key is available
    if api_key:
        print("\n--- Live API Call (fast tier) ---")
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=64,
            messages=[{
                "role": "user",
                "content": "Classify as POSITIVE, NEGATIVE, or NEUTRAL: 'The API responded correctly.' Reply with only the label."
            }],
        )
        label = response.content[0].text.strip()
        print(f"Classification result: {label}")
        print(f"Tokens used: {response.usage.input_tokens} in / {response.usage.output_tokens} out")
        actual_cost = MODEL_CATALOG["claude-haiku"].estimate_cost(
            response.usage.input_tokens, response.usage.output_tokens
        )
        print(f"Actual cost: ${actual_cost:.6f}")
    else:
        print("\nSkipping live API call (no key set).")


if __name__ == "__main__":
    main()
