"""
L15: Human-in-the-Loop and Approval Gates
Demonstrates three HITL patterns: approval gate, interrupt-and-resume, confidence threshold.
"""

import json
import time
from pathlib import Path
import anthropic

client = anthropic.Anthropic()
MODEL = "claude-3-5-haiku-20241022"

# ---------------------------------------------------------------------------
# Tool Definitions with requires_approval flag
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "draft_email",
        "description": "Draft an email without sending it. Returns the draft for review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body text"},
            },
            "required": ["to", "subject", "body"],
        },
        "requires_approval": False,
    },
    {
        "name": "send_email",
        "description": "Send an email to the specified recipient.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
        "requires_approval": True,
    },
    {
        "name": "list_drafts",
        "description": "List all saved email drafts.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "requires_approval": False,
    },
]

# Strip the requires_approval flag before sending to API
API_TOOLS = [
    {k: v for k, v in tool.items() if k != "requires_approval"}
    for tool in TOOLS
]
APPROVAL_FLAGS: dict[str, bool] = {
    tool["name"]: tool.get("requires_approval", False) for tool in TOOLS
}


# ---------------------------------------------------------------------------
# Pattern 1: Approval Gate
# ---------------------------------------------------------------------------

def require_approval(tool_name: str, tool_input: dict) -> tuple[bool, dict]:
    """
    Present a proposed tool call to the human for approval.

    Returns:
        (approved, final_input): If approved, final_input is the args to use.
        If rejected, approved=False and final_input contains the rejection reason.
    """
    print("\n" + "=" * 55)
    print("  APPROVAL REQUIRED")
    print("=" * 55)
    print(f"  Tool:      {tool_name}")
    print(f"  Arguments: {json.dumps(tool_input, indent=4)}")
    print("=" * 55)
    print("  [a] Approve as-is")
    print("  [r] Reject (enter reason)")
    print("  [m] Modify (enter new JSON)")
    print("-" * 55)

    choice = input("  Decision: ").strip().lower()

    if choice in ("a", "approve", ""):
        print("  Approved.")
        return True, tool_input

    elif choice in ("r", "reject"):
        reason = input("  Rejection reason: ").strip()
        return False, {"rejection_reason": reason or "No reason given"}

    elif choice in ("m", "modify"):
        print("  Enter modified JSON arguments:")
        raw = input("  > ").strip()
        try:
            modified = json.loads(raw)
            print("  Modified input accepted.")
            return True, modified
        except json.JSONDecodeError:
            print("  Invalid JSON. Rejecting instead.")
            return False, {"rejection_reason": "Human provided invalid JSON in modify step"}

    else:
        print("  Unrecognized input. Rejecting.")
        return False, {"rejection_reason": "Unrecognized approval decision"}


def _run_tool_stub(tool_name: str, tool_input: dict) -> str:
    """Stub implementations of the tools (no real side effects)."""
    if tool_name == "draft_email":
        return (
            f"Draft saved:\n"
            f"  To: {tool_input.get('to')}\n"
            f"  Subject: {tool_input.get('subject')}\n"
            f"  Body: {tool_input.get('body')}"
        )
    elif tool_name == "send_email":
        return (
            f"[STUB] Email sent to {tool_input.get('to')} "
            f"with subject '{tool_input.get('subject')}'"
        )
    elif tool_name == "list_drafts":
        return "Drafts: [welcome_email_draft.txt, follow_up_draft.txt]"
    return f"[STUB] Executed {tool_name} with {tool_input}"


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """
    Execute a tool call, routing through the approval gate if required.
    """
    if APPROVAL_FLAGS.get(tool_name, False):
        approved, final_input = require_approval(tool_name, tool_input)
        if not approved:
            reason = final_input.get("rejection_reason", "Action rejected by human")
            return f"[GATE BLOCKED] {reason}. Please revise your plan."
        tool_input = final_input

    return _run_tool_stub(tool_name, tool_input)


def run_email_agent(user_request: str, max_turns: int = 10) -> None:
    """Run the email agent with an approval gate on send_email."""
    print(f"\nUser: {user_request}")
    messages = [{"role": "user", "content": user_request}]
    system = (
        "You are an email assistant. "
        "Always draft an email before sending it. "
        "Call draft_email first to compose the message, then send_email to deliver it. "
        "Every send_email call will require explicit human approval before it executes."
    )

    for turn in range(max_turns):
        response = client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=system,
            tools=API_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            final_text = next(
                (b.text for b in response.content if hasattr(b, "text")), "(done)"
            )
            print(f"\nAgent: {final_text}")
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    print(f"\n[Agent requests: {block.name}]")
                    result = execute_tool(block.name, block.input)
                    print(f"[Tool result: {result[:100]}{'...' if len(result) > 100 else ''}]")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------------------
# Pattern 2: Interrupt and Resume
# ---------------------------------------------------------------------------

STATE_FILE = Path("/tmp/agent_pending_action.json")


def save_pending_action(goal: str, action: dict, history: list) -> None:
    """Persist agent state to disk and signal that human review is needed."""
    state = {
        "goal": goal,
        "pending_action": action,
        "conversation_history": history,
        "created_at": time.time(),
        "decision": None,  # Human sets this to "approve" or "reject"
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))
    print(f"\n[AGENT PAUSED] State saved to: {STATE_FILE}")
    print("Review the file, set 'decision' to 'approve' or 'reject', then re-run.")


def load_pending_state() -> tuple[dict | None, str | None]:
    """Load pending state if it exists and has a human decision."""
    if not STATE_FILE.exists():
        return None, None

    state = json.loads(STATE_FILE.read_text())
    decision = state.get("decision")

    if decision is None:
        print("[AGENT] Pending action found. No decision yet.")
        return None, None

    # Consume the state file after reading
    STATE_FILE.unlink(missing_ok=True)
    return state, decision


def run_interruptible_agent(goal: str) -> None:
    """
    Demonstration of interrupt-and-resume.
    First run: agent reaches a decision point, saves state, exits.
    Second run (after human sets decision in the file): agent resumes.
    """
    # Check for a prior run waiting to resume
    saved_state, decision = load_pending_state()

    if saved_state:
        action = saved_state["pending_action"]
        if decision == "approve":
            print(f"[RESUME] Human approved action: {action['tool_name']}")
            result = _run_tool_stub(action["tool_name"], action["tool_input"])
            print(f"[RESULT] {result}")
            print("[AGENT] Task complete after human approval.")
        else:
            print(f"[RESUME] Human rejected the action. Agent would revise plan.")
        return

    # First run: compose the action and pause for review
    print(f"\nAgent starting: {goal}")
    messages = [{"role": "user", "content": goal}]
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system="You are an email assistant. Describe the email you would send without actually sending it.",
        messages=messages,
    )

    agent_plan = response.content[0].text if response.content else "Send a status update email."
    print(f"Agent plan: {agent_plan[:150]}")

    # Simulate reaching the send decision point
    proposed_action = {
        "tool_name": "send_email",
        "tool_input": {
            "to": "manager@company.com",
            "subject": "Status Update",
            "body": agent_plan[:200],
        },
    }
    save_pending_action(goal, proposed_action, messages)


# ---------------------------------------------------------------------------
# Pattern 3: Confidence Threshold
# ---------------------------------------------------------------------------

def confidence_gate(action: dict, confidence: float, threshold: float = 0.8) -> bool:
    """
    Returns True if the action should proceed autonomously.
    Returns False if it should be escalated to a human.
    """
    if confidence >= threshold:
        print(f"[CONFIDENCE GATE] confidence={confidence:.2f} >= {threshold:.2f}. Auto-approving.")
        return True
    else:
        print(f"[CONFIDENCE GATE] confidence={confidence:.2f} < {threshold:.2f}. Escalating.")
        print(f"  Action: {action}")
        decision = input("  Human decision [a]pprove/[r]eject: ").strip().lower()
        return decision in ("a", "approve")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("PATTERN 1: APPROVAL GATE (Email Agent)")
    print("=" * 60)
    print("Note: This demo will prompt for approval when send_email is called.")
    print("Type 'a' to approve, 'r' to reject.\n")

    run_email_agent("Send a welcome email to alex@example.com about our new product launch.")

    print("\n" + "=" * 60)
    print("PATTERN 2: INTERRUPT AND RESUME (Simulated)")
    print("=" * 60)
    # Simulate a first run
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    run_interruptible_agent("Send a weekly status report to the team.")
    print(f"\nState file contents:")
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        print(f"  Goal: {state['goal']}")
        print(f"  Pending action: {state['pending_action']['tool_name']}")
        print(f"  Decision: {state['decision']} (set to 'approve' or 'reject' to resume)")

    print("\n" + "=" * 60)
    print("PATTERN 3: CONFIDENCE THRESHOLD")
    print("=" * 60)
    test_actions = [
        ({"tool": "send_email", "to": "known@company.com"}, 0.92),
        ({"tool": "delete_record", "id": "user_12345"}, 0.61),
        ({"tool": "send_email", "to": "unknown@external.com", "amount": "$50,000"}, 0.43),
    ]
    for action, confidence in test_actions:
        print(f"\nAction: {action}")
        will_proceed = confidence_gate(action, confidence, threshold=0.75)
        print(f"Result: {'proceeding' if will_proceed else 'blocked'}")
