"""
Lesson 01-05: Context-Window Management
========================================
Demonstrates a ContextManager class that:
- Counts tokens using the Anthropic SDK before each API call
- Enforces a named-region budget (system, history, docs, query, output reserve)
- Truncates oldest messages when the budget is exceeded
- Falls back to summarization when truncation would lose critical early context

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    python main.py
"""

import os
from dataclasses import dataclass

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"


# ---------------------------------------------------------------------------
# Budget dataclass
# ---------------------------------------------------------------------------

@dataclass
class ContextBudget:
    """
    Token budget for a single request, divided into named regions.
    All values in tokens. Tune per deployment.
    """
    model_limit: int = 200_000       # Claude 3.5 Haiku context limit
    system_max: int = 2_000          # cap on system prompt size
    history_max: int = 40_000        # rolling conversation history
    docs_max: int = 8_000            # retrieved documents / tool outputs
    query_max: int = 2_000           # current user message
    output_reserve: int = 4_000      # never touch: reserved for model output

    @property
    def total_input_max(self) -> int:
        """Maximum tokens allowed in the input."""
        return self.model_limit - self.output_reserve

    def fits(self, token_count: int) -> bool:
        """Return True if the given token count is within the input budget."""
        return token_count <= self.total_input_max


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

def count_message_tokens(system: str, messages: list[dict]) -> int:
    """
    Count tokens for a system prompt + messages array using the Anthropic
    token-counting API. Does NOT make a completion call.
    """
    if not messages:
        return 0
    response = client.messages.count_tokens(
        model=MODEL,
        system=system,
        messages=messages,
    )
    return response.input_tokens


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class ContextManager:
    """
    Manages conversation history within a token budget.

    Strategies:
    - Default: drop oldest messages (user+assistant pairs) until budget fits
    - summarize_when_full=True: compress oldest block into a summary note

    Usage:
        cm = ContextManager(system_prompt="You are a helpful assistant.")
        cm.add_user("Hello, my name is Sarah.")
        response_text = cm.complete()
        cm.add_assistant(response_text)
    """

    def __init__(
        self,
        system_prompt: str,
        budget: ContextBudget | None = None,
        summarize_when_full: bool = False,
        verbose: bool = True,
    ):
        self.system = system_prompt
        self.budget = budget or ContextBudget()
        self.summarize_when_full = summarize_when_full
        self.verbose = verbose
        self.messages: list[dict] = []
        self._drops_total = 0

    def add_user(self, content: str) -> None:
        """Append a user message to the history."""
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        """Append an assistant message to the history."""
        self.messages.append({"role": "assistant", "content": content})

    def token_count(self) -> int:
        """Return the current total input token count."""
        return count_message_tokens(self.system, self.messages)

    def budget_utilization(self) -> float:
        """Return current token fill as a fraction of the input budget (0.0-1.0)."""
        return self.token_count() / self.budget.total_input_max

    def enforce_budget(self) -> int:
        """
        Trim oldest messages until the request fits the budget.
        Returns the number of messages dropped or summarized.
        """
        dropped = 0
        while self.messages and not self.budget.fits(self.token_count()):
            if self.summarize_when_full and len(self.messages) >= 6:
                compressed = self._summarize_oldest_block(block_size=4)
                dropped += compressed
                # After summarizing, re-check; if still over budget, drop pairs
                if not self.budget.fits(self.token_count()):
                    continue
                break
            else:
                # Drop the oldest user+assistant pair (or single message)
                remove_count = min(2, len(self.messages))
                self.messages = self.messages[remove_count:]
                dropped += remove_count

        self._drops_total += dropped
        return dropped

    def _summarize_oldest_block(self, block_size: int = 4) -> int:
        """
        Summarize the oldest `block_size` messages into a single user note.
        Replaces the block with one condensed message.
        Returns the net reduction in message count.
        """
        if len(self.messages) < block_size + 1:
            return 0

        block = self.messages[:block_size]
        rest = self.messages[block_size:]

        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in block
        )

        if self.verbose:
            print(f"  [ContextManager] Summarizing {block_size} messages into 1...")

        summary_response = client.messages.create(
            model=MODEL,
            max_tokens=400,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize this conversation segment in 2-3 sentences. "
                        "Preserve all key facts: names, numbers, decisions, constraints.\n\n"
                        + transcript
                    ),
                }
            ],
        )
        summary_text = summary_response.content[0].text

        summary_message = {
            "role": "user",
            "content": f"[Earlier conversation summary: {summary_text}]",
        }

        self.messages = [summary_message] + rest
        # Net reduction: replaced block_size with 1
        return block_size - 1

    def complete(self, max_tokens: int = 1024) -> str:
        """
        Enforce budget, then send the request.
        Returns the assistant's response text.
        """
        dropped = self.enforce_budget()
        if dropped > 0 and self.verbose:
            print(f"  [ContextManager] Budget enforced: dropped/compressed {dropped} messages "
                  f"({self.token_count()} tokens, "
                  f"{self.budget_utilization():.1%} of budget)")

        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=self.system,
            messages=self.messages,
        )
        return response.content[0].text

    def stats(self) -> dict:
        """Return a snapshot of current context stats."""
        tokens = self.token_count()
        return {
            "messages": len(self.messages),
            "tokens": tokens,
            "budget_utilization": f"{tokens / self.budget.total_input_max:.1%}",
            "total_drops": self._drops_total,
        }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_sliding_window():
    """
    Show the sliding-window strategy: oldest messages are dropped when the
    context fills. Fast, but forgets early facts.
    """
    print("\n" + "=" * 60)
    print("DEMO 1: Sliding Window (drop oldest)")
    print("=" * 60)

    # Use a tiny budget to trigger truncation quickly in a demo
    tight_budget = ContextBudget(
        model_limit=200_000,
        output_reserve=4_000,
        history_max=2_000,   # very tight for demo purposes
    )
    # Override total_input_max for demo by setting a small model_limit
    tight_budget_demo = ContextBudget(model_limit=10_000, output_reserve=1_000)

    cm = ContextManager(
        system_prompt="You are a helpful project planning assistant.",
        budget=tight_budget_demo,
        summarize_when_full=False,
        verbose=True,
    )

    turns = [
        "My name is Sarah and my project budget is $50,000.",
        "The deadline is end of Q3.",
        "We have a team of 5 engineers and 2 designers.",
        "The primary deliverable is a mobile app.",
        "What are the main risks for a project like this?",
    ]

    for user_msg in turns:
        print(f"\nUSER: {user_msg}")
        cm.add_user(user_msg)
        tokens = cm.token_count()
        response = cm.complete(max_tokens=200)
        cm.add_assistant(response)
        print(f"ASSISTANT: {response[:150]}...")
        print(f"  Stats: {cm.stats()}")

    # Now check if early facts survived
    print("\nUSER: What was my name and budget again?")
    cm.add_user("What was my name and budget again?")
    final = cm.complete(max_tokens=200)
    cm.add_assistant(final)
    print(f"ASSISTANT: {final}")
    print(f"\nFinal stats: {cm.stats()}")


def demo_summarization():
    """
    Show the summarization strategy: oldest messages are compressed, not dropped.
    Slower (extra API call) but preserves early facts.
    """
    print("\n" + "=" * 60)
    print("DEMO 2: Summarization Fallback (compress oldest block)")
    print("=" * 60)

    tight_budget_demo = ContextBudget(model_limit=10_000, output_reserve=1_000)

    cm = ContextManager(
        system_prompt="You are a helpful project planning assistant.",
        budget=tight_budget_demo,
        summarize_when_full=True,
        verbose=True,
    )

    turns = [
        "My name is Sarah and my project budget is $50,000.",
        "The deadline is end of Q3.",
        "We have a team of 5 engineers and 2 designers.",
        "The primary deliverable is a mobile app.",
        "What are the main risks for a project like this?",
    ]

    for user_msg in turns:
        print(f"\nUSER: {user_msg}")
        cm.add_user(user_msg)
        response = cm.complete(max_tokens=200)
        cm.add_assistant(response)
        print(f"ASSISTANT: {response[:150]}...")
        print(f"  Stats: {cm.stats()}")

    print("\nUSER: What was my name and budget again?")
    cm.add_user("What was my name and budget again?")
    final = cm.complete(max_tokens=200)
    cm.add_assistant(final)
    print(f"ASSISTANT: {final}")
    print(f"\nFinal stats: {cm.stats()}")


def demo_token_counting():
    """
    Show token counting vs. character-count estimation.
    """
    print("\n" + "=" * 60)
    print("DEMO 3: Token Counting vs. Character Estimation")
    print("=" * 60)

    samples = [
        "Hello, how are you today?",
        "Implement a binary search tree with insert, delete, and search operations in Python.",
        "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
        "日本語のテキストはトークン化が異なります。",  # Japanese text
    ]

    print(f"{'Sample':<60} {'Chars':>6} {'Est(chars/4)':>12} {'Actual tokens':>13}")
    print("-" * 95)
    for sample in samples:
        chars = len(sample)
        estimated = chars // 4
        actual = count_message_tokens(
            system="",
            messages=[{"role": "user", "content": sample}],
        )
        display = sample[:57] + "..." if len(sample) > 60 else sample
        print(f"{display:<60} {chars:>6} {estimated:>12} {actual:>13}")


if __name__ == "__main__":
    print("Context-Window Management: Three Demonstrations")
    demo_token_counting()
    demo_sliding_window()
    demo_summarization()
