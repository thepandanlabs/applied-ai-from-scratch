"""
L14: Agent Failure Modes - MAST Taxonomy
Demonstrates a FailureDetector that analyzes agent message history for MAST violations.
"""

import json
from collections import Counter
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# MAST Data Structures
# ---------------------------------------------------------------------------

@dataclass
class MASTFlag:
    category: str   # MEMORY | ACTION | SUPERVISION | TASK
    rule: str       # short name for the rule that fired
    detail: str     # human-readable description
    turn: int       # which turn in the history triggered this flag


@dataclass
class FailureDetectorResult:
    flags: list = field(default_factory=list)
    healthy: bool = True

    def add_flag(self, flag: MASTFlag) -> None:
        self.flags.append(flag)
        self.healthy = False

    def summary(self) -> str:
        if self.healthy:
            return "No MAST failures detected."
        lines = [
            f"[{f.category}] {f.rule} (turn {f.turn}): {f.detail}"
            for f in self.flags
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# FailureDetector
# ---------------------------------------------------------------------------

class FailureDetector:
    """
    Analyzes agent message history and flags potential MAST failures.

    MAST categories:
    - Memory: agent repeats actions, forgets prior work, contradicts itself
    - Action: wrong tool, malformed arguments, ignored errors
    - Supervision: no stopping condition, no budget, runs indefinitely
    - Task: misunderstood goal, satisficing, false completion
    """

    REPEAT_THRESHOLD = 2          # Same tool+args appearing this many times flags Memory
    TOKEN_WARNING_THRESHOLD = 40_000  # Approx token estimate above this flags Supervision
    MAX_TURNS_THRESHOLD = 15      # Turn count above this checks for missing stop signal

    FALSE_COMPLETION_PHRASES = [
        "task complete",
        "i have completed",
        "successfully completed",
        "task is done",
        "i've finished",
        "all done",
        "have been completed",
    ]

    def analyze(self, history: list[dict]) -> FailureDetectorResult:
        result = FailureDetectorResult()
        self._check_memory(history, result)
        self._check_action(history, result)
        self._check_supervision(history, result)
        self._check_task(history, result)
        return result

    def _check_memory(self, history: list[dict], result: FailureDetectorResult) -> None:
        """Detect repeated identical tool calls."""
        # Collect (turn_index, signature) for every tool call
        tool_calls = []
        for i, msg in enumerate(history):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        sig = json.dumps(
                            {"name": block.get("name"), "input": block.get("input")},
                            sort_keys=True,
                        )
                        tool_calls.append((i, sig, block.get("name", "unknown")))

        # Count signatures and flag those exceeding the threshold
        counts = Counter(sig for _, sig, _ in tool_calls)
        reported = set()
        for turn, sig, name in tool_calls:
            if counts[sig] > self.REPEAT_THRESHOLD and sig not in reported:
                result.add_flag(MASTFlag(
                    category="MEMORY",
                    rule="repeated_tool_call",
                    detail=f"Tool '{name}' called {counts[sig]} times with identical arguments",
                    turn=turn,
                ))
                reported.add(sig)

    def _check_action(self, history: list[dict], result: FailureDetectorResult) -> None:
        """Detect malformed tool arguments and ignored tool errors."""
        error_keywords = ["error", "failed", "exception", "bad request", "null", "not found", "400", "500"]

        for i, msg in enumerate(history):
            # Check tool results for errors, then check the following turn
            role = msg.get("role", "")
            if role == "tool" or (
                role == "user" and isinstance(msg.get("content"), list) and
                any(isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in msg.get("content", []))
            ):
                content_str = json.dumps(msg.get("content", "")).lower()
                has_error = any(kw in content_str for kw in error_keywords)

                if has_error and i + 1 < len(history):
                    next_content = str(history[i + 1].get("content", "")).lower()
                    completion_words = ["done", "complete", "finished", "success", "task complete", "successfully"]
                    if any(word in next_content for word in completion_words):
                        result.add_flag(MASTFlag(
                            category="ACTION",
                            rule="error_ignored",
                            detail=(
                                "Tool returned an error response but the following turn "
                                "declares completion or success"
                            ),
                            turn=i,
                        ))

            # Check for null fields in tool call arguments
            if role == "assistant":
                content = msg.get("content", "")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_input = block.get("input", {})
                            if isinstance(tool_input, dict):
                                null_fields = [k for k, v in tool_input.items() if v is None]
                                if null_fields:
                                    result.add_flag(MASTFlag(
                                        category="ACTION",
                                        rule="null_tool_argument",
                                        detail=(
                                            f"Tool '{block.get('name', 'unknown')}' called with "
                                            f"null required fields: {null_fields}"
                                        ),
                                        turn=i,
                                    ))

    def _check_supervision(self, history: list[dict], result: FailureDetectorResult) -> None:
        """Detect missing stop signals and unbounded resource usage."""
        turn_count = len(history)

        if turn_count > self.MAX_TURNS_THRESHOLD:
            terminal_signals = ["stop", "complete", "done", "finish", "escalate", "hand off", "cannot proceed"]
            last_few_content = " ".join(
                str(msg.get("content", "")) for msg in history[-3:]
            ).lower()
            has_terminal = any(sig in last_few_content for sig in terminal_signals)

            if not has_terminal:
                result.add_flag(MASTFlag(
                    category="SUPERVISION",
                    rule="no_stop_signal",
                    detail=(
                        f"Agent ran {turn_count} turns with no terminal action "
                        "detected in the last 3 turns"
                    ),
                    turn=turn_count - 1,
                ))

        # Approximate token usage
        total_chars = sum(len(str(msg.get("content", ""))) for msg in history)
        approx_tokens = total_chars // 4
        if approx_tokens > self.TOKEN_WARNING_THRESHOLD:
            result.add_flag(MASTFlag(
                category="SUPERVISION",
                rule="token_budget_exceeded",
                detail=(
                    f"Estimated token usage ~{approx_tokens:,} exceeds "
                    f"threshold of {self.TOKEN_WARNING_THRESHOLD:,}"
                ),
                turn=turn_count - 1,
            ))

    def _check_task(self, history: list[dict], result: FailureDetectorResult) -> None:
        """Detect false completion signals."""
        for i, msg in enumerate(history):
            if msg.get("role") != "assistant":
                continue
            content = str(msg.get("content", "")).lower()

            for phrase in self.FALSE_COMPLETION_PHRASES:
                if phrase in content:
                    if i > 0:
                        prev_content = str(history[i - 1].get("content", ""))
                        # Flag if the preceding context was very short or contained an error
                        if len(prev_content) < 50 or "error" in prev_content.lower():
                            result.add_flag(MASTFlag(
                                category="TASK",
                                rule="false_completion",
                                detail=(
                                    f"Completion phrase '{phrase}' follows a short or "
                                    f"error response at turn {i - 1}"
                                ),
                                turn=i,
                            ))
                    break  # One flag per assistant turn


# ---------------------------------------------------------------------------
# Sample Transcripts
# ---------------------------------------------------------------------------

HEALTHY_TRANSCRIPT = [
    {
        "role": "user",
        "content": "Find the top 3 Python testing frameworks and summarize each.",
    },
    {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "name": "web_search",
                "input": {"query": "top Python testing frameworks 2024"},
            }
        ],
    },
    {
        "role": "tool",
        "content": [
            {
                "type": "tool_result",
                "content": (
                    "pytest: most popular, feature-rich. "
                    "unittest: built-in stdlib. "
                    "hypothesis: property-based testing."
                ),
            }
        ],
    },
    {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "name": "web_search",
                "input": {"query": "pytest vs hypothesis use cases comparison"},
            }
        ],
    },
    {
        "role": "tool",
        "content": [
            {
                "type": "tool_result",
                "content": (
                    "pytest is general-purpose. hypothesis generates test inputs automatically "
                    "for property-based testing. Both integrate with each other."
                ),
            }
        ],
    },
    {
        "role": "assistant",
        "content": (
            "Summary of top 3 Python testing frameworks: "
            "1. pytest - most widely used, rich plugin ecosystem. "
            "2. unittest - built into stdlib, xUnit style. "
            "3. hypothesis - property-based, generates edge cases automatically. "
            "Research complete."
        ),
    },
]

FAILED_TRANSCRIPT = [
    {
        "role": "user",
        "content": "Send a welcome email to the new user.",
    },
    # Action failure: null 'to' field
    {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "name": "send_email",
                "input": {"to": None, "subject": "Welcome!", "body": "Hello and welcome."},
            }
        ],
    },
    {
        "role": "tool",
        "content": [
            {
                "type": "tool_result",
                "content": "Error: 'to' field is required and cannot be null. Request rejected.",
            }
        ],
    },
    # Memory failure: same broken call repeated
    {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "name": "send_email",
                "input": {"to": None, "subject": "Welcome!", "body": "Hello and welcome."},
            }
        ],
    },
    {
        "role": "tool",
        "content": [
            {
                "type": "tool_result",
                "content": "Error: 'to' field is required and cannot be null. Request rejected.",
            }
        ],
    },
    # Memory failure: same broken call a third time
    {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "name": "send_email",
                "input": {"to": None, "subject": "Welcome!", "body": "Hello and welcome."},
            }
        ],
    },
    {
        "role": "tool",
        "content": [
            {
                "type": "tool_result",
                "content": "Error: 400 Bad Request",
            }
        ],
    },
    # Task failure: false completion after error + Action failure: error ignored
    {
        "role": "assistant",
        "content": "I have completed the email sending task successfully.",
    },
]


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    detector = FailureDetector()

    print("=" * 60)
    print("TRANSCRIPT 1: Healthy Agent")
    print("=" * 60)
    result = detector.analyze(HEALTHY_TRANSCRIPT)
    print(result.summary())

    print()
    print("=" * 60)
    print("TRANSCRIPT 2: Seeded Failures (Memory + Action + Task)")
    print("=" * 60)
    result = detector.analyze(FAILED_TRANSCRIPT)
    print(result.summary())
    print(f"\nTotal flags: {len(result.flags)}")
    print(f"Healthy: {result.healthy}")

    print()
    print("=" * 60)
    print("FLAG BREAKDOWN")
    print("=" * 60)
    if not result.healthy:
        by_category: dict[str, list] = {}
        for flag in result.flags:
            by_category.setdefault(flag.category, []).append(flag)
        for category, flags in sorted(by_category.items()):
            print(f"\n{category}:")
            for f in flags:
                print(f"  [{f.rule}] turn {f.turn}: {f.detail}")
