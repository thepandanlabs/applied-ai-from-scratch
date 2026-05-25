---
name: skill-hitl-approval-gate
description: Approval gate pattern with tool tagging for human-in-the-loop agent control
version: "1.0"
phase: "04"
lesson: "15"
tags: [agents, hitl, approval-gate, safety, human-in-the-loop]
---

# Skill: HITL Approval Gate

Use this skill when an agent has access to tools that are: irreversible, high-blast-radius, or require judgment about edge cases that cannot be fully specified in the system prompt.

---

## Tool Tagging Convention

Every tool definition gets a `requires_approval` flag. This is stripped before sending to the API but used by the executor.

```python
TOOLS = [
    {
        "name": "read_data",
        "description": "Read records. Safe, non-destructive.",
        "input_schema": {...},
        "requires_approval": False,   # read-only: no gate
    },
    {
        "name": "delete_record",
        "description": "Permanently delete a record.",
        "input_schema": {...},
        "requires_approval": True,    # destructive: gate required
    },
    {
        "name": "send_email",
        "description": "Send an email to a recipient.",
        "input_schema": {...},
        "requires_approval": True,    # external side-effect: gate required
    },
]

# Strip the flag before passing to the Anthropic API
API_TOOLS = [
    {k: v for k, v in tool.items() if k != "requires_approval"}
    for tool in TOOLS
]
APPROVAL_FLAGS = {t["name"]: t.get("requires_approval", False) for t in TOOLS}
```

**Tagging rules:**
- Read-only operations: `requires_approval: False`
- Write operations to internal state: judgment call (usually False for low-blast-radius)
- Writes to external systems (email, database, payment): `True`
- Deletes of any kind: `True`
- Any operation that cannot be undone in < 60 seconds: `True`

---

## Approval Gate Function

```python
def require_approval(tool_name: str, tool_input: dict) -> tuple[bool, dict]:
    """
    Present a proposed action to the human.
    Returns (approved, final_input).
    """
    print(f"\nAPPROVAL REQUIRED: {tool_name}")
    print(f"Arguments: {json.dumps(tool_input, indent=2)}")
    print("[a]pprove / [r]eject / [m]odify")

    choice = input("Decision: ").strip().lower()

    if choice in ("a", "approve", ""):
        return True, tool_input
    elif choice in ("r", "reject"):
        reason = input("Reason: ")
        return False, {"rejection_reason": reason}
    elif choice in ("m", "modify"):
        raw = input("Modified JSON: ")
        try:
            return True, json.loads(raw)
        except json.JSONDecodeError:
            return False, {"rejection_reason": "Invalid JSON in modify step"}
    else:
        return False, {"rejection_reason": "Unrecognized input"}
```

---

## Tool Executor Wrapper

```python
def execute_tool(tool_name: str, tool_input: dict) -> str:
    """
    Execute a tool, routing through the approval gate if required.
    Drop-in replacement for direct tool dispatch.
    """
    if APPROVAL_FLAGS.get(tool_name, False):
        approved, final_input = require_approval(tool_name, tool_input)
        if not approved:
            reason = final_input.get("rejection_reason", "Action rejected")
            return f"[GATE BLOCKED] {reason}. Please revise."
        tool_input = final_input

    return your_tool_dispatch(tool_name, tool_input)
```

---

## Interrupt and Resume Pattern

For async review cycles where human reviewers are not watching in real time.

```python
import json, time
from pathlib import Path

STATE_FILE = Path("/tmp/agent_pending_action.json")

def save_pending_action(goal: str, action: dict, history: list) -> None:
    """Save state and pause. Human sets 'decision' to 'approve'/'reject'."""
    state = {
        "goal": goal,
        "pending_action": action,
        "conversation_history": history,
        "created_at": time.time(),
        "decision": None,  # Human fills this in
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))

def load_and_resume() -> tuple[dict | None, str | None]:
    """Check for a pending human decision."""
    if not STATE_FILE.exists():
        return None, None
    state = json.loads(STATE_FILE.read_text())
    decision = state.get("decision")
    if decision is None:
        return None, None
    STATE_FILE.unlink(missing_ok=True)
    return state, decision
```

**At scale:** replace `STATE_FILE` with a database row. Use `thread_id` to support concurrent runs. LangGraph's `SqliteSaver` or `PostgresSaver` implements this pattern with `interrupt_before=["approval_node"]`.

---

## Confidence Threshold Pattern

For high-volume pipelines where most cases auto-approve.

```python
CONFIDENCE_THRESHOLD = 0.80  # tune per use case

def run_with_confidence_gate(action: dict, confidence: float) -> bool:
    """Returns True if action should proceed."""
    if confidence >= CONFIDENCE_THRESHOLD:
        return True  # auto-approve
    # Below threshold: escalate to human
    print(f"Low confidence ({confidence:.2f}) on: {action}")
    decision = input("[a]pprove / [r]eject: ").strip().lower()
    return decision in ("a", "approve")
```

**Calibration rule:** start with a threshold of 0.9 (escalate aggressively). Lower it only after you have confirmed that auto-approved cases have a near-zero error rate.

---

## Decision Matrix: Which HITL Pattern

```
Scenario                                         Pattern
-------------------------------------------------  --------------------
Real-time agent with interactive user            Approval Gate
Batch pipeline, human reviews next morning       Interrupt + Resume
High-volume routine ops, rare edge cases         Confidence Threshold
Compliance requires audit trail                  Interrupt + Resume (database-backed)
Agent controls financial transactions            Approval Gate (always)
Agent sends personalized emails at scale         Confidence Threshold + sampling
```

---

## What Requires an Approval Gate

Always require approval for:
- Database deletes or bulk updates
- Sending external communications (email, SMS, notifications)
- Financial transactions of any kind
- Modifications to access controls or permissions
- Any action the agent itself flags as irreversible

Never require approval for:
- Read-only operations
- Internal state updates with no external effect
- Computations and analysis steps
- Drafting content that has not yet been delivered
