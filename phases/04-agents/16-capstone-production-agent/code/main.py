"""
L16 Capstone: Production Codebase Assistant Agent

Integrates all Phase 04 patterns:
1. Router: classifies intent before the main agent loop
2. Governor: max 15 iterations, 50K tokens, 3 minutes
3. Tool executor: retry + structured error messages
4. HITL gate: suggest_fix requires human approval
5. ReAct reasoning: Thought: logged before every tool call
6. Short-term memory: sliding window of last 10 turns
7. Tracing: per-turn span with turn number, tool, tokens, elapsed time
"""

import contextlib
import json
import time
import uuid
from dataclasses import dataclass, field

import anthropic

client = anthropic.Anthropic()
MODEL = "claude-3-5-haiku-20241022"


# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "search_files",
        "description": "Search for files or code patterns in the codebase by keyword or pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term or code pattern"},
                "file_type": {
                    "type": "string",
                    "description": "Optional file extension filter, e.g. .py or .ts",
                },
            },
            "required": ["query"],
        },
        "requires_approval": False,
    },
    {
        "name": "read_file",
        "description": "Read the full contents of a specific file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the project root",
                },
            },
            "required": ["path"],
        },
        "requires_approval": False,
    },
    {
        "name": "run_tests",
        "description": "Run the test suite or a specific test file and return results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Test file path or directory to run",
                },
            },
            "required": ["target"],
        },
        "requires_approval": False,
    },
    {
        "name": "suggest_fix",
        "description": "Propose a code change as a diff. Requires human approval before any application.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Target file path"},
                "change_description": {"type": "string", "description": "What the change does and why"},
                "proposed_diff": {"type": "string", "description": "The proposed code change in diff format"},
            },
            "required": ["file", "change_description", "proposed_diff"],
        },
        "requires_approval": True,
    },
]

# Strip the requires_approval flag before sending to the Anthropic API
API_TOOLS = [
    {k: v for k, v in tool.items() if k != "requires_approval"}
    for tool in TOOLS
]
APPROVAL_FLAGS: dict[str, bool] = {
    tool["name"]: tool.get("requires_approval", False) for tool in TOOLS
}

AGENT_SYSTEM_PROMPT = """You are a codebase assistant. You help engineers search, read, test, and improve code.

Before every tool call, write a Thought: line explaining your reasoning.
Format strictly as: "Thought: [your reasoning]"
Then make the tool call.

After all necessary tools have run, write: "Answer: [your conclusion]"

Rules:
- Only call tools relevant to the user's question
- If a tool returns an error, acknowledge it explicitly and adjust your approach
- Never call suggest_fix without first calling read_file on the relevant file
- If the task cannot be completed within available tools, say so clearly with an Answer:"""

ROUTER_PROMPT = """Classify this user request into exactly one category.
Return only the single category word, nothing else. No punctuation, no explanation.

Categories:
- search (finding files, functions, patterns, or symbols in the codebase)
- read (viewing contents of a specific file)
- test (running or checking test results)
- suggest (proposing a fix, refactor, or code change)
- general (anything else)"""


# ---------------------------------------------------------------------------
# Governor
# ---------------------------------------------------------------------------

@dataclass
class Governor:
    max_iterations: int = 15
    max_tokens: int = 50_000
    max_seconds: float = 180.0
    iterations: int = 0
    tokens_used: int = 0
    start_time: float = field(default_factory=time.time)

    def tick(self, tokens_in: int = 0, tokens_out: int = 0) -> None:
        self.iterations += 1
        self.tokens_used += tokens_in + tokens_out

    def check(self) -> tuple[bool, str]:
        """Returns (ok, reason). ok=False means the agent must stop."""
        if self.iterations >= self.max_iterations:
            return False, f"iteration limit reached ({self.iterations}/{self.max_iterations})"
        if self.tokens_used >= self.max_tokens:
            return False, f"token budget exceeded ({self.tokens_used:,}/{self.max_tokens:,})"
        elapsed = time.time() - self.start_time
        if elapsed >= self.max_seconds:
            return False, f"time limit reached ({elapsed:.0f}s/{self.max_seconds:.0f}s)"
        return True, ""

    def stats(self) -> dict:
        return {
            "iterations": self.iterations,
            "tokens_used": self.tokens_used,
            "elapsed_s": round(time.time() - self.start_time, 2),
        }


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

@dataclass
class AgentTrace:
    request_id: str
    user_input: str
    start_time: float = field(default_factory=time.time)
    spans: list = field(default_factory=list)
    outcome: str = "in_progress"
    total_tokens: int = 0

    def add_span(self, turn: int, tool: str | None, tokens_in: int,
                 tokens_out: int, elapsed_ms: float, thought: str | None = None,
                 approved: bool | None = None) -> None:
        self.spans.append({
            "turn": turn,
            "tool": tool,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "elapsed_ms": round(elapsed_ms, 1),
            "thought": thought,
            "approved": approved,
        })
        self.total_tokens += tokens_in + tokens_out

    def finish(self, outcome: str) -> None:
        self.outcome = outcome
        duration = (time.time() - self.start_time) * 1000
        print(
            f"\n[trace] request_id={self.request_id} outcome={outcome} "
            f"turns={len(self.spans)} total_tokens={self.total_tokens} "
            f"duration={duration:.0f}ms"
        )

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "user_input": self.user_input,
            "outcome": self.outcome,
            "total_tokens": self.total_tokens,
            "duration_ms": round((time.time() - self.start_time) * 1000, 1),
            "spans": self.spans,
        }


@contextlib.contextmanager
def trace_turn(trace: AgentTrace, turn: int):
    """Context manager that measures elapsed time for a single agent turn."""
    span_data: dict = {"start": time.time(), "tool": None, "tokens_in": 0,
                       "tokens_out": 0, "thought": None, "approved": None}
    yield span_data
    elapsed_ms = (time.time() - span_data["start"]) * 1000
    trace.add_span(
        turn=turn,
        tool=span_data["tool"],
        tokens_in=span_data["tokens_in"],
        tokens_out=span_data["tokens_out"],
        elapsed_ms=elapsed_ms,
        thought=span_data["thought"],
        approved=span_data["approved"],
    )
    print(
        f"  [span] turn={turn} tool={span_data['tool'] or 'none'} "
        f"tok_in={span_data['tokens_in']} tok_out={span_data['tokens_out']} "
        f"elapsed={elapsed_ms:.0f}ms"
    )


# ---------------------------------------------------------------------------
# Tool Executor with Retry and HITL Gate
# ---------------------------------------------------------------------------

def require_approval(tool_name: str, tool_input: dict) -> tuple[bool, dict]:
    """Synchronous approval gate for tools tagged requires_approval=True."""
    print("\n" + "=" * 55)
    print("  APPROVAL REQUIRED")
    print("=" * 55)
    print(f"  Tool: {tool_name}")
    print(f"  Arguments:\n{json.dumps(tool_input, indent=4)}")
    print("=" * 55)
    choice = input("  [a]pprove / [r]eject: ").strip().lower()

    if choice in ("a", "approve", ""):
        return True, tool_input
    reason = input("  Rejection reason: ").strip()
    return False, {"rejection_reason": reason or "Rejected by reviewer"}


def _stub_tool(tool_name: str, tool_input: dict) -> str:
    """Stub implementations with mocked responses (no real filesystem access needed)."""
    if tool_name == "search_files":
        query = tool_input.get("query", "")
        file_type = tool_input.get("file_type", "")
        return (
            f"Search results for '{query}'{' (' + file_type + ')' if file_type else ''}:\n"
            f"  - src/auth/login.py (line 42: {query})\n"
            f"  - src/utils/helpers.py (line 17: {query})\n"
            f"  - tests/test_auth.py (line 88: {query})\n"
            f"3 files found."
        )
    elif tool_name == "read_file":
        path = tool_input.get("path", "unknown")
        return (
            f"Contents of {path}:\n\n"
            f"def authenticate(username, password):\n"
            f"    # TODO: add rate limiting\n"
            f"    user = db.find_user(username)\n"
            f"    if user and user.check_password(password):\n"
            f"        return generate_token(user)\n"
            f"    return None\n"
        )
    elif tool_name == "run_tests":
        target = tool_input.get("target", ".")
        return (
            f"Test run: {target}\n"
            f"....\n"
            f"4 passed, 0 failed, 0 errors in 0.43s"
        )
    elif tool_name == "suggest_fix":
        return (
            f"Fix for {tool_input.get('file')} recorded.\n"
            f"Description: {tool_input.get('change_description')}\n"
            f"Diff:\n{tool_input.get('proposed_diff', '')[:200]}"
        )
    return f"[STUB] {tool_name} executed with {tool_input}"


def execute_tool(tool_name: str, tool_input: dict, max_retries: int = 2) -> tuple[str, bool]:
    """
    Execute a tool with retry and HITL gate.

    Returns:
        (result_string, approved): approved is None for non-gated tools,
        True/False for gated tools.
    """
    approved = None

    # HITL Gate
    if APPROVAL_FLAGS.get(tool_name, False):
        gate_approved, final_input = require_approval(tool_name, tool_input)
        approved = gate_approved
        if not gate_approved:
            reason = final_input.get("rejection_reason", "Rejected")
            return f"[GATE BLOCKED] {reason}. Please revise your approach.", False
        tool_input = final_input

    # Execute with retry
    for attempt in range(max_retries + 1):
        try:
            result = _stub_tool(tool_name, tool_input)
            return result, approved if approved is not None else True
        except Exception as e:
            if attempt == max_retries:
                return (
                    f"[TOOL ERROR] {tool_name} failed after {max_retries + 1} attempts. "
                    f"Last error: {type(e).__name__}: {e}. "
                    f"Adjust your approach.",
                    False,
                )
            time.sleep(0.5 * (attempt + 1))  # Simple backoff

    return f"[TOOL ERROR] {tool_name} failed.", False


# ---------------------------------------------------------------------------
# Memory: Sliding Window
# ---------------------------------------------------------------------------

def trim_history(messages: list[dict], max_turns: int = 10) -> list[dict]:
    """
    Retain the original user message plus the most recent max_turns messages.
    This ensures the agent always has its original goal plus recent context.
    """
    if len(messages) <= max_turns + 1:
        return messages
    return [messages[0]] + messages[-(max_turns):]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def route_request(user_input: str) -> str:
    """Classify the user's intent into one of five categories."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=10,
        system=ROUTER_PROMPT,
        messages=[{"role": "user", "content": user_input}],
    )
    return response.content[0].text.strip().lower()


# ---------------------------------------------------------------------------
# Main Agent Loop
# ---------------------------------------------------------------------------

def run_agent(user_input: str, max_turns: int = 20) -> dict:
    """
    Run the production codebase assistant agent.

    Returns a result dict with: completed, final_response, governor_stats, trace.
    """
    request_id = str(uuid.uuid4())[:8]
    governor = Governor()
    trace = AgentTrace(request_id=request_id, user_input=user_input)

    print(f"\n[agent] request_id={request_id}")

    # Route the request
    intent = route_request(user_input)
    print(f"[router] intent={intent}")

    messages = [{"role": "user", "content": user_input}]
    final_response = None

    for turn in range(max_turns):
        # Check governor before each turn
        ok, reason = governor.check()
        if not ok:
            msg = (
                f"I was unable to complete your request within the resource budget. "
                f"Reason: {reason}. "
                f"Here is what I found so far in {governor.iterations} steps."
            )
            print(f"\n[governor] STOP: {reason}")
            trace.finish("budget_exceeded")
            return {
                "completed": False,
                "final_response": msg,
                "governor_stats": governor.stats(),
                "trace": trace.spans,
                "intent": intent,
            }

        with trace_turn(trace, turn) as span:
            # Trim memory: keep original message + last 10 turns
            messages_to_send = trim_history(messages)

            response = client.messages.create(
                model=MODEL,
                max_tokens=1500,
                system=AGENT_SYSTEM_PROMPT,
                tools=API_TOOLS,
                messages=messages_to_send,
            )

            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            span["tokens_in"] = tokens_in
            span["tokens_out"] = tokens_out
            governor.tick(tokens_in, tokens_out)

            # Extract Thought: from text content
            for block in response.content:
                if hasattr(block, "text"):
                    text = block.text
                    if "thought:" in text.lower():
                        lines = text.split("\n")
                        for line in lines:
                            if line.lower().startswith("thought:"):
                                span["thought"] = line[8:].strip()
                                print(f"  Thought: {span['thought'][:100]}")
                                break

            if response.stop_reason == "end_turn":
                # Extract final answer
                for block in response.content:
                    if hasattr(block, "text"):
                        final_response = block.text
                span["tool"] = None
                trace.finish("completed")
                return {
                    "completed": True,
                    "final_response": final_response,
                    "governor_stats": governor.stats(),
                    "trace": trace.spans,
                    "intent": intent,
                }

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        span["tool"] = block.name
                        print(f"  [tool_call] {block.name}({json.dumps(block.input)[:80]}...)")

                        result, approved = execute_tool(block.name, block.input)

                        if APPROVAL_FLAGS.get(block.name, False):
                            span["approved"] = approved

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})

    trace.finish("max_turns_reached")
    return {
        "completed": False,
        "final_response": "Maximum turns reached without completing the task.",
        "governor_stats": governor.stats(),
        "trace": trace.spans,
        "intent": intent,
    }


# ---------------------------------------------------------------------------
# Regression Eval Harness
# ---------------------------------------------------------------------------

GOLDEN_SET = [
    {
        "id": "search-01",
        "input": "Find all files that import the logging module",
        "expected_tools": ["search_files"],
        "expected_final_tool": "search_files",
        "should_complete": True,
    },
    {
        "id": "read-01",
        "input": "Show me the contents of src/auth/login.py",
        "expected_tools": ["read_file"],
        "expected_final_tool": "read_file",
        "should_complete": True,
    },
    {
        "id": "test-01",
        "input": "Run the tests in tests/test_auth.py and tell me if they pass",
        "expected_tools": ["run_tests"],
        "expected_final_tool": "run_tests",
        "should_complete": True,
    },
    {
        "id": "multi-01",
        "input": "Search for files with TODO comments, then show me the first result",
        "expected_tools": ["search_files", "read_file"],
        "expected_final_tool": "read_file",
        "should_complete": True,
    },
]


def eval_agent_run(agent_result: dict, expected: dict) -> dict:
    """Score one agent run against a golden case."""
    actual_tools = [s.get("tool") for s in agent_result.get("trace", []) if s.get("tool")]

    # Metric 1: did the expected tools appear in the trace?
    tool_coverage = sum(
        1 for t in expected["expected_tools"] if t in actual_tools
    ) / max(len(expected["expected_tools"]), 1)

    # Metric 2: was the final tool call correct?
    last_tool = actual_tools[-1] if actual_tools else None
    final_tool_match = last_tool == expected["expected_final_tool"]

    # Metric 3: did the agent complete (or not) as expected?
    completion_ok = agent_result.get("completed", False) == expected["should_complete"]

    # Weighted score
    score = (tool_coverage * 0.5) + (0.3 if final_tool_match else 0.0) + (0.2 if completion_ok else 0.0)

    return {
        "id": expected["id"],
        "score": round(score, 3),
        "tool_coverage": round(tool_coverage, 3),
        "final_tool_match": final_tool_match,
        "completion_ok": completion_ok,
        "actual_tools": actual_tools,
        "pass": score >= 0.8,
    }


def run_regression_eval(golden_set: list = GOLDEN_SET) -> dict:
    """Run all golden cases and report pass rate and mean score."""
    print("\n" + "=" * 60)
    print("REGRESSION EVAL")
    print("=" * 60)
    results = []

    for case in golden_set:
        print(f"\nCase: {case['id']}")
        print(f"Input: {case['input']}")
        agent_result = run_agent(case["input"])
        scored = eval_agent_run(agent_result, case)
        results.append(scored)
        status = "PASS" if scored["pass"] else "FAIL"
        print(
            f"[{status}] score={scored['score']:.2f} "
            f"tools={scored['actual_tools']} "
            f"coverage={scored['tool_coverage']:.2f}"
        )

    pass_rate = sum(1 for r in results if r["pass"]) / len(results)
    mean_score = sum(r["score"] for r in results) / len(results)

    print(f"\nPass rate: {pass_rate:.0%} | Mean score: {mean_score:.3f}")
    return {"pass_rate": pass_rate, "mean_score": mean_score, "results": results}


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("PRODUCTION CODEBASE ASSISTANT")
    print("=" * 60)
    print("Available commands:")
    print("  1. Run a single query")
    print("  2. Run the regression eval suite")
    print()

    choice = input("Choice [1/2] (default: 1): ").strip()

    if choice == "2":
        run_regression_eval()
    else:
        user_input = input("Query: ").strip()
        if not user_input:
            user_input = "Search for any files that contain authentication logic"

        result = run_agent(user_input)
        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"Completed: {result['completed']}")
        print(f"Intent: {result['intent']}")
        print(f"Governor stats: {result['governor_stats']}")
        print(f"\nFinal response:\n{result.get('final_response', '(none)')}")
        print(f"\nTrace spans: {len(result['trace'])}")
        for span in result["trace"]:
            print(
                f"  turn={span['turn']} tool={span['tool'] or 'none'} "
                f"elapsed={span['elapsed_ms']}ms"
            )
