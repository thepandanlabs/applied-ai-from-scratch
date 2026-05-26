"""
Excessive Agency and Tool Permissioning - Phase 08 Lesson 05
appliedaifromscratch.com

Demonstrates: OWASP LLM06 mitigation via ToolPermissionPolicy.
Enforces per-tool permission levels and human approval gates.

Run:
    python main.py

Requires:
    pip install anthropic
"""

from __future__ import annotations

import json
import datetime
from enum import IntEnum
from dataclasses import dataclass
from typing import Callable

import anthropic


# ---------------------------------------------------------------------------
# Permission levels
# ---------------------------------------------------------------------------

class PermissionLevel(IntEnum):
    """
    Ordered permission levels. Higher value = more dangerous.

    READ    - zero side effects, fully reversible (search, query)
    WRITE   - reversible with effort (create, update)
    EXECUTE - hard to reverse (send email, call external API)
    ADMIN   - potentially permanent (delete, drop table, revoke access)
    """
    READ = 1
    WRITE = 2
    EXECUTE = 3
    ADMIN = 4


# ---------------------------------------------------------------------------
# Tool specification
# ---------------------------------------------------------------------------

@dataclass
class ToolSpec:
    """One entry in the agent's tool manifest."""
    name: str
    level: PermissionLevel
    description: str
    handler: Callable[..., str]


class PolicyViolation(Exception):
    """Raised when a tool call is blocked by the permission policy."""
    pass


# ---------------------------------------------------------------------------
# Permission policy
# ---------------------------------------------------------------------------

class ToolPermissionPolicy:
    """
    Enforces least-privilege tool access for an agent.

    Every tool call goes through this policy before execution.
    The model never runs tools directly.

    Args:
        tools: The tool manifest for this agent.
        max_autonomous_level: Tools at or below this level run without approval.
        gate_fn: Called for tools above max_autonomous_level.
                 Returns True to approve, False to deny.
                 Defaults to stdin prompt.
    """

    def __init__(
        self,
        tools: list[ToolSpec],
        max_autonomous_level: PermissionLevel = PermissionLevel.READ,
        gate_fn: Callable[[str, dict], bool] | None = None,
    ):
        self._tools: dict[str, ToolSpec] = {t.name: t for t in tools}
        self._max_auto = max_autonomous_level
        self._gate_fn = gate_fn or self._default_gate
        self._audit_log: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, tool_name: str, args: dict) -> str:
        """
        Execute a tool call through the permission policy.

        Returns the tool result string on success.
        Raises PolicyViolation if the call is blocked.
        """
        if tool_name not in self._tools:
            self._log(tool_name, args, "DENIED_UNKNOWN")
            raise PolicyViolation(
                f"Unknown tool: {tool_name!r}. Not in manifest. "
                "Available tools: " + ", ".join(self._tools.keys())
            )

        spec = self._tools[tool_name]

        # ADMIN tools never run autonomously under any circumstance
        if spec.level == PermissionLevel.ADMIN:
            self._log(tool_name, args, "DENIED_ADMIN")
            raise PolicyViolation(
                f"Tool {tool_name!r} is ADMIN level. "
                "Autonomous ADMIN actions are not permitted by policy. "
                "Escalate to a human operator via your ticketing system."
            )

        # Tools above the autonomous ceiling require human gate approval
        if spec.level > self._max_auto:
            approved = self._gate_fn(tool_name, args)
            if not approved:
                self._log(tool_name, args, "DENIED_GATE")
                raise PolicyViolation(
                    f"Tool {tool_name!r} ({spec.level.name} level) requires human "
                    "approval and the request was denied. "
                    "The requested action was not performed."
                )
            self._log(tool_name, args, "APPROVED_GATE")
        else:
            self._log(tool_name, args, "APPROVED_AUTO")

        # Execute the tool
        return spec.handler(**args)

    def get_tool_schemas(self) -> list[dict]:
        """
        Return Anthropic-format tool schemas for all non-ADMIN tools.
        ADMIN tools are never exposed to the model.
        """
        schemas = []
        for spec in self._tools.values():
            if spec.level == PermissionLevel.ADMIN:
                continue  # never expose ADMIN tools to the model
            schemas.append({
                "name": spec.name,
                "description": f"[{spec.level.name}] {spec.description}",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            })
        return schemas

    def audit_log(self) -> list[dict]:
        """Return a copy of the full audit log for this session."""
        return list(self._audit_log)

    def print_audit_log(self) -> None:
        """Pretty-print the audit log to stdout."""
        print("\n=== Audit Log ===")
        for entry in self._audit_log:
            status = "OK " if "APPROVED" in entry["outcome"] else "ERR"
            print(
                f"  [{status}] {entry['ts'][:19]} | "
                f"{entry['tool']:20s} | {entry['level']:8s} | {entry['outcome']}"
            )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _log(self, tool: str, args: dict, outcome: str) -> None:
        level = self._tools[tool].level.name if tool in self._tools else "UNKNOWN"
        self._audit_log.append({
            "ts": datetime.datetime.utcnow().isoformat(),
            "tool": tool,
            "level": level,
            "args": args,
            "outcome": outcome,
        })

    @staticmethod
    def _default_gate(tool_name: str, args: dict) -> bool:
        """
        Default gate: ask the operator via stdin.

        In production, replace with:
        - Slack approval workflow
        - Web UI confirmation dialog
        - Ticketing system (PagerDuty, Linear)
        - Time-boxed async approval queue
        """
        print(f"\n[APPROVAL REQUIRED]")
        print(f"  Tool    : {tool_name}")
        print(f"  Args    : {json.dumps(args, indent=4)}")
        answer = input("  Approve? [y/N] ").strip().lower()
        return answer == "y"


# ---------------------------------------------------------------------------
# Agent loop with policy enforcement
# ---------------------------------------------------------------------------

def run_agent_with_policy(
    user_task: str,
    policy: ToolPermissionPolicy,
    max_turns: int = 5,
) -> str:
    """
    A minimal agent loop that enforces the permission policy on every tool call.

    Key property: the model never executes a tool directly.
    Every call goes through policy.execute(), which checks permission level,
    fires the gate if needed, logs the outcome, and only then runs the handler.
    """
    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": user_task}]
    tool_schemas = policy.get_tool_schemas()

    for turn in range(max_turns):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            tools=tool_schemas,
            messages=messages,
        )

        # Model finished without requesting a tool
        if response.stop_reason == "end_turn":
            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(text_blocks)

        # Collect and process tool calls
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        tool_results = []

        for call in tool_calls:
            print(f"\n[Agent requesting tool] {call.name}({json.dumps(call.input)})")
            try:
                result = policy.execute(call.name, call.input)
                print(f"[Tool result] {result[:120]}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": result,
                })
            except PolicyViolation as e:
                # Return the denial reason to the model so it can explain to the user
                denial_msg = str(e)
                print(f"[Policy violation] {denial_msg}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "is_error": True,
                    "content": denial_msg,
                })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return "Agent reached maximum turns without completing the task."


# ---------------------------------------------------------------------------
# Mock tool handlers
# ---------------------------------------------------------------------------

def search_kb(query: str = "") -> str:
    return (
        f"[KB search: '{query}']\n"
        "Found 3 articles: 'Refund Policy', 'Return Window', 'Exceptions'.\n"
        "Top result: Refunds are processed within 5 business days."
    )


def send_email(to: str = "", subject: str = "", body: str = "") -> str:
    return f"[Email sent to {to!r} | subject: {subject!r}]"


def update_record(table: str = "", record_id: str = "", updates: str = "") -> str:
    return f"[Updated {table} record {record_id}: {updates}]"


def delete_records(table: str = "", condition: str = "") -> str:
    # This handler should never be called - ADMIN level blocks it
    return f"[DELETED rows from {table} WHERE {condition}]"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_policy_enforcement():
    """Demonstrate all four permission outcomes without a live API call."""
    print("=" * 60)
    print("Demo: ToolPermissionPolicy enforcement (no API call)")
    print("=" * 60)

    tools = [
        ToolSpec("search_kb",     PermissionLevel.READ,    "Search knowledge base",    search_kb),
        ToolSpec("update_record", PermissionLevel.WRITE,   "Update a database record", update_record),
        ToolSpec("send_email",    PermissionLevel.EXECUTE, "Send email",               send_email),
        ToolSpec("delete_records",PermissionLevel.ADMIN,   "Delete database records",  delete_records),
    ]

    # Gate function: auto-deny for demo purposes
    policy = ToolPermissionPolicy(
        tools=tools,
        max_autonomous_level=PermissionLevel.READ,
        gate_fn=lambda tool, args: False,  # always deny in demo
    )

    # 1. READ - should pass without gate
    print("\n1. READ tool (search_kb) - expect: APPROVED_AUTO")
    result = policy.execute("search_kb", {"query": "refund policy"})
    print(f"   Result: {result[:80]}")

    # 2. WRITE - above autonomous ceiling, gate fires and denies
    print("\n2. WRITE tool (update_record) - expect: DENIED_GATE")
    try:
        policy.execute("update_record", {"table": "orders", "record_id": "42", "updates": "status=closed"})
    except PolicyViolation as e:
        print(f"   Blocked: {str(e)[:100]}")

    # 3. EXECUTE - above autonomous ceiling, gate fires and denies
    print("\n3. EXECUTE tool (send_email) - expect: DENIED_GATE")
    try:
        policy.execute("send_email", {"to": "user@example.com", "subject": "Hi", "body": "..."})
    except PolicyViolation as e:
        print(f"   Blocked: {str(e)[:100]}")

    # 4. ADMIN - unconditionally blocked, gate never fires
    print("\n4. ADMIN tool (delete_records) - expect: DENIED_ADMIN")
    try:
        policy.execute("delete_records", {"table": "users", "condition": "1=1"})
    except PolicyViolation as e:
        print(f"   Blocked: {str(e)[:100]}")

    # 5. Unknown tool
    print("\n5. Unknown tool (drop_table) - expect: DENIED_UNKNOWN")
    try:
        policy.execute("drop_table", {"table": "users"})
    except PolicyViolation as e:
        print(f"   Blocked: {str(e)[:100]}")

    policy.print_audit_log()


def demo_agent(task: str = "Search for our refund policy and summarize it in one sentence."):
    """Run the agent loop with a READ-only tool manifest."""
    print("\n" + "=" * 60)
    print("Demo: Agent loop with ToolPermissionPolicy")
    print(f"Task: {task}")
    print("=" * 60)

    tools = [
        ToolSpec("search_kb", PermissionLevel.READ, "Search the knowledge base", search_kb),
    ]
    policy = ToolPermissionPolicy(tools=tools, max_autonomous_level=PermissionLevel.READ)

    result = run_agent_with_policy(task, policy)
    print(f"\nFinal answer: {result}")
    policy.print_audit_log()


if __name__ == "__main__":
    # Run policy enforcement demo (no API key needed)
    demo_policy_enforcement()

    # Uncomment to run the live agent demo (requires ANTHROPIC_API_KEY)
    # demo_agent()
