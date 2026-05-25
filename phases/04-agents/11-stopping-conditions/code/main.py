"""
Lesson 11: Stopping Conditions, Cost Governors, Kill Switches

Implements an AgentGovernor class with five stopping mechanisms:
1. Max iterations (hard stop at N)
2. Token budget (track usage, stop at cost ceiling)
3. Wall-clock timeout (stop if elapsed > N seconds)
4. Soft stop (ask LLM 'do you have enough?' every N iterations)
5. Kill switch (threading.Event set from outside the loop)

Run: python main.py
Requires: ANTHROPIC_API_KEY environment variable
"""

import os
import threading
import time
from dataclasses import dataclass, field

import anthropic


# ---------------------------------------------------------------------------
# Configuration and state
# ---------------------------------------------------------------------------

@dataclass
class GovernorConfig:
    max_iterations: int = 20
    max_tokens: int = 50_000           # total input + output tokens
    max_seconds: float = 120.0         # wall-clock timeout in seconds
    token_budget_usd: float = 0.50     # approximate cost ceiling in USD
    soft_stop_every_n: int = 5         # run soft stop check every N iterations
    # claude-3-5-haiku-20241022 pricing (approximate, update as needed)
    input_token_price: float = 0.001 / 1000    # $ per input token
    output_token_price: float = 0.005 / 1000   # $ per output token


@dataclass
class GovernorState:
    iterations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    start_time: float = field(default_factory=time.monotonic)
    stop_reason: str | None = None

    def cost_usd(self, cfg: GovernorConfig) -> float:
        return (
            self.total_input_tokens * cfg.input_token_price
            + self.total_output_tokens * cfg.output_token_price
        )

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.start_time

    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


# ---------------------------------------------------------------------------
# AgentGovernor
# ---------------------------------------------------------------------------

class AgentGovernor:
    """
    Wraps any agent loop and enforces five stopping conditions.

    Usage:
        governor = AgentGovernor(config)
        while governor.should_continue():
            if governor.should_soft_stop(context, client):
                break
            # ... run one loop iteration ...
            governor.record_usage(input_tokens, output_tokens)
    """

    def __init__(self, config: GovernorConfig | None = None) -> None:
        self.config = config or GovernorConfig()
        self.state = GovernorState()
        self._kill_switch = threading.Event()

    def kill(self) -> None:
        """
        Set the kill switch. Can be called from any thread.
        The loop will stop at the next iteration boundary.
        """
        self._kill_switch.set()

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Call after each API response to accumulate token counts."""
        self.state.total_input_tokens += input_tokens
        self.state.total_output_tokens += output_tokens
        self.state.iterations += 1

    def should_continue(self) -> bool:
        """
        Run all hard-stop checks. Returns False with stop_reason set if
        any check fails. Call at the top of every loop iteration.
        """
        cfg = self.config
        s = self.state

        # Check 1: kill switch (external cancellation)
        if self._kill_switch.is_set():
            s.stop_reason = "kill_switch"
            return False

        # Check 2: max iterations
        if s.iterations >= cfg.max_iterations:
            s.stop_reason = f"max_iterations ({cfg.max_iterations})"
            return False

        # Check 3: token count ceiling
        if s.total_tokens() >= cfg.max_tokens:
            s.stop_reason = f"max_tokens ({cfg.max_tokens:,})"
            return False

        # Check 4: cost budget
        if s.cost_usd(cfg) >= cfg.token_budget_usd:
            s.stop_reason = f"token_budget_usd (${cfg.token_budget_usd:.2f})"
            return False

        # Check 5: wall-clock timeout
        if s.elapsed_seconds() >= cfg.max_seconds:
            s.stop_reason = f"timeout ({cfg.max_seconds:.0f}s)"
            return False

        return True

    def should_soft_stop(
        self,
        context: str,
        client: anthropic.Anthropic,
    ) -> bool:
        """
        Ask the model whether it has enough to answer.
        Only runs every soft_stop_every_n iterations to keep it cheap.
        Returns True if the model says the task is complete.
        """
        s = self.state
        if s.iterations == 0:
            return False
        if s.iterations % self.config.soft_stop_every_n != 0:
            return False

        check_response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=10,
            system=(
                "You are a task completion evaluator. "
                "Reply with exactly one word: YES or NO. "
                "Only say YES if the accumulated context is genuinely sufficient "
                "to produce a complete and useful answer."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Task context summary:\n{context[:500]}\n\n"
                        "Do you have enough information to produce a complete answer?"
                    ),
                }
            ],
        )
        # Count these tokens against the budget too
        self.state.total_input_tokens += check_response.usage.input_tokens
        self.state.total_output_tokens += check_response.usage.output_tokens

        answer = check_response.content[0].text.strip().upper()
        if answer.startswith("YES"):
            self.state.stop_reason = "soft_stop (model said done)"
            return True
        return False

    def status(self) -> str:
        """Return a one-line status string for logging."""
        cfg = self.config
        s = self.state
        return (
            f"iter={s.iterations}/{cfg.max_iterations} | "
            f"tokens={s.total_tokens():,}/{cfg.max_tokens:,} | "
            f"cost=${s.cost_usd(cfg):.4f}/${cfg.token_budget_usd:.2f} | "
            f"elapsed={s.elapsed_seconds():.1f}s/{cfg.max_seconds:.0f}s"
        )


# ---------------------------------------------------------------------------
# Mock tools for demo
# ---------------------------------------------------------------------------

def mock_search(query: str) -> str:
    return f"Search results for '{query}': [result 1, result 2, result 3]"


def mock_read_page(url: str) -> str:
    time.sleep(0.1)  # Simulate network latency
    return f"Page content from {url}: [detailed content about the topic]"


TOOLS = [
    {
        "name": "search",
        "description": "Search for information.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "read_page",
        "description": "Read a webpage.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
]

TOOL_FN = {"search": mock_search, "read_page": mock_read_page}


# ---------------------------------------------------------------------------
# Governed agent loop
# ---------------------------------------------------------------------------

def governed_agent_loop(
    task: str,
    client: anthropic.Anthropic,
    config: GovernorConfig | None = None,
    governor: AgentGovernor | None = None,
) -> tuple[str, GovernorState]:
    """
    A governed agent loop. All five stopping conditions are checked each iteration.

    Pass an external governor to share a kill switch across threads.
    """
    if governor is None:
        governor = AgentGovernor(config)

    messages = [{"role": "user", "content": task}]
    context_summary = f"Task: {task}"
    final_answer = ""

    print(f"\nStarting governed loop | Config: max_iter={governor.config.max_iterations}, "
          f"budget=${governor.config.token_budget_usd:.2f}, "
          f"timeout={governor.config.max_seconds:.0f}s")

    while governor.should_continue():
        # Soft stop check (cheap before each iteration once every N turns)
        if governor.should_soft_stop(context_summary, client):
            print(f"  [Governor] Soft stop: {governor.state.stop_reason}")
            final_answer = "[Soft stop: model determined task is complete with available context]"
            break

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system="You are a research agent. Use tools to gather information. Be systematic.",
            tools=TOOLS,
            messages=messages,
        )

        governor.record_usage(
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        print(f"  [Governor] {governor.status()}")

        if response.stop_reason == "end_turn":
            final_answer = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            governor.state.stop_reason = "completed"
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    fn = TOOL_FN.get(block.name, lambda **_: "unknown tool")
                    result = fn(**block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })
                    context_summary += f" | {block.name}({block.input}): {str(result)[:80]}"
            messages.append({"role": "user", "content": tool_results})

    if not governor.state.stop_reason:
        governor.state.stop_reason = "unknown"

    if not final_answer:
        final_answer = (
            f"[Stopped: {governor.state.stop_reason}] "
            f"Partial context: {context_summary[:200]}"
        )

    return final_answer, governor.state


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_max_iterations(client: anthropic.Anthropic) -> None:
    print("\n" + "=" * 60)
    print("DEMO 1: Max iterations (hard stop at 3)")
    print("=" * 60)
    config = GovernorConfig(max_iterations=3, max_seconds=60, token_budget_usd=5.0)
    answer, state = governed_agent_loop(
        "Research the history of widget manufacturing in detail.",
        client,
        config=config,
    )
    print(f"\nStop reason: {state.stop_reason}")
    print(f"Iterations used: {state.iterations}")
    print(f"Tokens used: {state.total_tokens():,}")


def demo_token_budget(client: anthropic.Anthropic) -> None:
    print("\n" + "=" * 60)
    print("DEMO 2: Token budget ($0.05 ceiling)")
    print("=" * 60)
    config = GovernorConfig(max_iterations=50, max_seconds=60, token_budget_usd=0.05)
    answer, state = governed_agent_loop(
        "Research everything about competitive pricing strategies.",
        client,
        config=config,
    )
    print(f"\nStop reason: {state.stop_reason}")
    print(f"Cost: ${state.cost_usd(config):.4f}")


def demo_kill_switch(client: anthropic.Anthropic) -> None:
    print("\n" + "=" * 60)
    print("DEMO 3: Kill switch (cancelled after 3s from external thread)")
    print("=" * 60)

    config = GovernorConfig(max_iterations=50, max_seconds=120, token_budget_usd=5.0)
    governor = AgentGovernor(config)

    def cancel_after_delay(seconds: float) -> None:
        time.sleep(seconds)
        print(f"\n  [External thread] Sending kill signal after {seconds}s...")
        governor.kill()

    cancel_thread = threading.Thread(target=cancel_after_delay, args=(3.0,), daemon=True)
    cancel_thread.start()

    answer, state = governed_agent_loop(
        "Research the complete history of software development methodologies.",
        client,
        governor=governor,
    )
    print(f"\nStop reason: {state.stop_reason}")
    print(f"Elapsed: {state.elapsed_seconds():.1f}s")
    print(f"Iterations completed before kill: {state.iterations}")


def demo_soft_stop(client: anthropic.Anthropic) -> None:
    print("\n" + "=" * 60)
    print("DEMO 4: Soft stop (LLM asked every 2 iterations)")
    print("=" * 60)
    config = GovernorConfig(
        max_iterations=20,
        max_seconds=60,
        token_budget_usd=1.0,
        soft_stop_every_n=2,
    )
    answer, state = governed_agent_loop(
        "What are the three main widget competitors and their pricing?",
        client,
        config=config,
    )
    print(f"\nStop reason: {state.stop_reason}")


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    # Run all four governor demos
    demo_max_iterations(client)
    demo_token_budget(client)
    demo_kill_switch(client)
    demo_soft_stop(client)

    print("\n" + "=" * 60)
    print("All governor demos complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
