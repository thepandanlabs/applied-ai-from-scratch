---
name: skill-tool-permission-policy
description: Helps enforce least-privilege tool access for AI agents using a permission policy layer. Use when designing agent tool manifests, auditing agent blast radius, or implementing human-in-the-loop gates for WRITE and EXECUTE level actions.
version: "1.0"
phase: "08"
lesson: "05"
tags: [security, agents, owasp-llm06, excessive-agency, tool-permissioning, human-in-the-loop]
---

# Skill: Tool Permission Policy

## Purpose

You are an applied AI security advisor specializing in agent safety and the principle of least privilege. Use this skill when a user needs to audit which tools their agent can access, design a permission manifest, or add human approval gates for dangerous actions.

---

## Core Mental Model

Every tool an agent can call has a blast radius. Assign permission levels based on that blast radius, then enforce them in code - not in the system prompt.

```
READ    - zero side effects, fully reversible
          search, query, list, read
WRITE   - reversible with effort
          create, update, insert, edit
EXECUTE - hard to reverse
          send email, call external API, deploy
ADMIN   - potentially permanent
          delete, drop, revoke, bulk export
```

**The rule:** autonomous execution only for READ. Gate on WRITE and EXECUTE. Block ADMIN entirely.

---

## Policy Implementation Template

```python
from enum import IntEnum
from dataclasses import dataclass
from typing import Callable

class PermissionLevel(IntEnum):
    READ = 1
    WRITE = 2
    EXECUTE = 3
    ADMIN = 4

@dataclass
class ToolSpec:
    name: str
    level: PermissionLevel
    description: str
    handler: Callable[..., str]

class PolicyViolation(Exception):
    pass

class ToolPermissionPolicy:
    def __init__(self, tools, max_autonomous_level=PermissionLevel.READ, gate_fn=None):
        self._tools = {t.name: t for t in tools}
        self._max_auto = max_autonomous_level
        self._gate_fn = gate_fn or self._stdin_gate

    def execute(self, tool_name: str, args: dict) -> str:
        if tool_name not in self._tools:
            raise PolicyViolation(f"Unknown tool: {tool_name!r}")
        spec = self._tools[tool_name]
        if spec.level == PermissionLevel.ADMIN:
            raise PolicyViolation(f"{tool_name} is ADMIN level - blocked unconditionally")
        if spec.level > self._max_auto:
            if not self._gate_fn(tool_name, args):
                raise PolicyViolation(f"{tool_name} denied at approval gate")
        return spec.handler(**args)

    @staticmethod
    def _stdin_gate(tool, args):
        return input(f"Approve {tool}({args})? [y/N] ").strip().lower() == "y"
```

---

## Tool Manifest Design Checklist

When designing the tool manifest for a new agent:

1. **List every tool the task could plausibly need** - be exhaustive
2. **Assign a permission level to each** - use blast radius, not convenience
3. **Remove any tool not strictly required** - if the task is "summarize", send_email should not be in the manifest
4. **Verify no ADMIN tool is exposed to the model** - never include ADMIN in get_tool_schemas()
5. **Set max_autonomous_level to READ** unless the task explicitly requires higher
6. **Document the gate implementation** - stdin is for development only

---

## Common Manifest Patterns

### Read-only research agent
```python
tools = [
    ToolSpec("search_kb", READ, "Search knowledge base", search_kb),
    ToolSpec("get_document", READ, "Retrieve a document by ID", get_doc),
    ToolSpec("list_results", READ, "List recent records", list_results),
]
policy = ToolPermissionPolicy(tools, max_autonomous_level=PermissionLevel.READ)
```

### Customer service agent (write allowed with gate)
```python
tools = [
    ToolSpec("search_kb",     READ,    "Search KB",            search_kb),
    ToolSpec("get_ticket",    READ,    "Get ticket by ID",     get_ticket),
    ToolSpec("update_ticket", WRITE,   "Update ticket status", update_ticket),
    ToolSpec("send_reply",    EXECUTE, "Send reply to user",   send_reply),
]
policy = ToolPermissionPolicy(
    tools,
    max_autonomous_level=PermissionLevel.WRITE,
    gate_fn=slack_approval_gate,  # EXECUTE requires Slack approval
)
```

---

## Integrating with the Agent Loop

Replace direct tool dispatch with policy.execute():

```python
# Before (Phase 04 pattern - no permission check):
result = TOOL_REGISTRY[tool_name](**args)

# After (Phase 08 pattern - policy enforced):
try:
    result = policy.execute(tool_name, args)
except PolicyViolation as e:
    result = f"[BLOCKED] {e}"  # return denial to model
```

Return denials to the model as tool_result with is_error=True so the model can explain the limitation to the user.

---

## Production Gate Implementations

### Slack approval
```python
def slack_gate(tool_name: str, args: dict) -> bool:
    post_to_slack(f"Approval needed: {tool_name}\n{json.dumps(args)}")
    return poll_approval_db(tool_name, timeout_seconds=120)
```

### Signed URL approval (async)
```python
def url_gate(tool_name: str, args: dict) -> bool:
    token = create_approval_token(tool_name, args, ttl=300)
    send_email_with_link(OPERATOR_EMAIL, f"/approve?token={token}")
    return wait_for_approval(token, timeout=300)
```

---

## Audit Log Requirements

Every tool call - approved or denied - must be logged with:
- Timestamp (UTC)
- Tool name and permission level
- Args (sanitize PII before logging)
- Outcome (APPROVED_AUTO, APPROVED_GATE, DENIED_GATE, DENIED_ADMIN, DENIED_UNKNOWN)
- Session ID (to correlate multi-turn conversations)

Store audit logs separately from application logs. They are a security artifact, not a debug trace.

---

## Diagnosing Excessive Agency

Signs your agent has too much permission:

- Any ADMIN tool can be called without a gate
- The manifest contains tools not needed for the declared task
- Gate denials are rare (< 1% of WRITE+ calls) - suggests gates are rubber-stamped
- A single task spans multiple permission levels in one agent
- The system prompt says "don't do X" for a tool that is in the manifest

Remediation: audit the manifest quarterly. Remove unused tools. Split agents that span READ through EXECUTE into separate scoped agents.
