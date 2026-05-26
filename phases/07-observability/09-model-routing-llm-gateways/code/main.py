"""
Model Router - Phase 07, Lesson 09
Routes LLM requests to the cheapest model that can handle the task correctly.

Usage:
    python main.py

No API calls are made in this demo. The router evaluates rules and returns
(model_id, reason) tuples. Integrate with your LLM client of choice.
"""

from __future__ import annotations

import dataclasses
from typing import Literal


ModelId = Literal[
    "claude-3-5-haiku-20241022",
    "claude-sonnet-4-5",
]

# Approximate cost per token (USD) for input tokens only.
# Update these when Anthropic adjusts pricing.
MODEL_COSTS: dict[ModelId, float] = {
    "claude-3-5-haiku-20241022": 0.000001,   # $1 / 1M tokens
    "claude-sonnet-4-5":        0.000003,   # $3 / 1M tokens
}


@dataclasses.dataclass
class RoutingRule:
    name: str
    description: str

    def matches(
        self,
        prompt_tokens: int,
        complexity: str | None,
        cost_budget: float | None,
    ) -> tuple[bool, ModelId, str]:
        """Return (matched, model_id, reason)."""
        raise NotImplementedError


@dataclasses.dataclass
class ExplicitComplexityRule(RoutingRule):
    """If the caller says complexity=high, use Sonnet."""

    def matches(self, prompt_tokens, complexity, cost_budget):
        if complexity == "high":
            return True, "claude-sonnet-4-5", "explicit_complexity_high"
        return False, "claude-3-5-haiku-20241022", ""


@dataclasses.dataclass
class LargeContextRule(RoutingRule):
    """Prompts over 6,000 tokens need Sonnet for reliable recall."""
    token_threshold: int = 6_000

    def matches(self, prompt_tokens, complexity, cost_budget):
        if prompt_tokens > self.token_threshold:
            return True, "claude-sonnet-4-5", "large_context"
        return False, "claude-3-5-haiku-20241022", ""


@dataclasses.dataclass
class BudgetConstraintRule(RoutingRule):
    """If the caller has a tight cost budget, use Haiku."""
    haiku_cost_per_token: float = MODEL_COSTS["claude-3-5-haiku-20241022"]

    def matches(self, prompt_tokens, complexity, cost_budget):
        if cost_budget is None:
            return False, "claude-3-5-haiku-20241022", ""
        # Estimate cost for this prompt on Haiku
        estimated_haiku_cost = prompt_tokens * self.haiku_cost_per_token
        # If even Haiku exceeds budget, still use Haiku (caller handles the error)
        if cost_budget < estimated_haiku_cost * 3:
            return True, "claude-3-5-haiku-20241022", "budget_constraint"
        return False, "claude-3-5-haiku-20241022", ""


@dataclasses.dataclass
class MediumPromptRule(RoutingRule):
    """Prompts over 1,500 tokens without a budget constraint go to Sonnet."""
    token_threshold: int = 1_500

    def matches(self, prompt_tokens, complexity, cost_budget):
        if prompt_tokens > self.token_threshold:
            return True, "claude-sonnet-4-5", "medium_to_large_prompt"
        return False, "claude-3-5-haiku-20241022", ""


class ModelRouter:
    """
    Routes LLM requests to the cheapest model that can handle the task.

    Rules are evaluated in order. The first matching rule wins.
    If no rule matches, the default_model is used.

    Args:
        default_budget: Maximum cost (USD) per request before forcing Haiku.
            Set to None to disable budget enforcement as a default.
        default_model: Model to use when no rule matches.
    """

    def __init__(
        self,
        default_budget: float | None = None,
        default_model: ModelId = "claude-3-5-haiku-20241022",
    ):
        self.default_budget = default_budget
        self.default_model = default_model
        self.rules: list[RoutingRule] = [
            ExplicitComplexityRule(
                name="explicit_complexity",
                description="Caller explicitly flags complexity=high",
            ),
            LargeContextRule(
                name="large_context",
                description="Prompts over 6000 tokens use Sonnet",
                token_threshold=6_000,
            ),
            BudgetConstraintRule(
                name="budget_constraint",
                description="Tight cost budget forces Haiku",
            ),
            MediumPromptRule(
                name="medium_prompt",
                description="Prompts 1500-6000 tokens use Sonnet",
                token_threshold=1_500,
            ),
        ]
        print(f"ModelRouter initialized with {len(self.rules)} routing rules")

    def _estimate_tokens(self, prompt: str) -> int:
        """Rough token estimate: 4 characters per token."""
        return max(1, len(prompt) // 4)

    def route(
        self,
        prompt: str,
        complexity: str | None = None,
        cost_budget: float | None = None,
    ) -> tuple[ModelId, str]:
        """
        Route a request to the appropriate model.

        Args:
            prompt: The full prompt text (system + user combined).
            complexity: Optional hint from the caller. Pass "high" for tasks
                that require multi-hop reasoning or long-form synthesis.
            cost_budget: Maximum acceptable cost (USD) for this single call.
                If None, uses the router's default_budget.

        Returns:
            (model_id, reason) - model to call, and why this model was chosen.
        """
        effective_budget = cost_budget if cost_budget is not None else self.default_budget
        prompt_tokens = self._estimate_tokens(prompt)

        for rule in self.rules:
            matched, model, reason = rule.matches(prompt_tokens, complexity, effective_budget)
            if matched:
                return model, reason

        return self.default_model, "default_no_rule_matched"

    def estimate_cost(self, model: ModelId, prompt_tokens: int, output_tokens: int = 150) -> float:
        """Estimate the cost of a call in USD."""
        cost_per_token = MODEL_COSTS[model]
        return (prompt_tokens + output_tokens) * cost_per_token


def main():
    router = ModelRouter(default_budget=0.01)

    test_cases = [
        {
            "label": "Simple Q&A",
            "prompt": "What is the capital of France?",
            "complexity": None,
            "cost_budget": 0.001,
        },
        {
            "label": "High-complexity task",
            "prompt": "Analyze the strategic implications of this document in detail.",
            "complexity": "high",
            "cost_budget": None,
        },
        {
            "label": "Large context",
            "prompt": "x" * 7_000,  # ~7000 chars = ~1750 tokens
            "complexity": None,
            "cost_budget": None,
        },
        {
            "label": "Budget constrained",
            "prompt": "Summarize this paragraph.",
            "complexity": None,
            "cost_budget": 0.001,
        },
    ]

    total_routed_cost = 0.0
    total_unrouted_cost = 0.0

    for tc in test_cases:
        prompt_tokens = router._estimate_tokens(tc["prompt"])
        model, reason = router.route(
            prompt=tc["prompt"],
            complexity=tc.get("complexity"),
            cost_budget=tc.get("cost_budget"),
        )
        cost = router.estimate_cost(model, prompt_tokens)
        unrouted_cost = router.estimate_cost("claude-sonnet-4-5", prompt_tokens)

        total_routed_cost += cost
        total_unrouted_cost += unrouted_cost

        print(f"\nRouting test: {tc['label']}")
        print(f"  Prompt tokens (est): {prompt_tokens}")
        print(f"  Routed to: {model} ({reason})")
        print(f"  Estimated cost: ${cost:.6f}")

    savings_pct = (1 - total_routed_cost / total_unrouted_cost) * 100
    print(f"\nCost analysis:")
    print(f"  Without routing (all sonnet): ${total_unrouted_cost:.6f}")
    print(f"  With routing:                  ${total_routed_cost:.6f}")
    print(f"  Savings: {savings_pct:.1f}%")


if __name__ == "__main__":
    main()
