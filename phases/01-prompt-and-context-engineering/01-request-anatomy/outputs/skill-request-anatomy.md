---
name: skill-request-anatomy
description: Reference card for the three-role conversation structure, alternation rules, and common failure modes in the Anthropic Messages API
version: "1.0"
phase: "01"
lesson: "01"
tags: [prompt-engineering, messages-api, roles, conversation, system-prompt]
---

# Skill: Request Anatomy

The Anthropic Messages API takes a list of messages and a system parameter. The model reads the full payload on every call. There is no session, no memory, no state outside what you send.

## The Three Roles

| Role | Where it goes | What it controls |
|------|--------------|-----------------|
| `system` | Top-level parameter (not in messages) | Model behavior, persona, constraints |
| `user` | `messages` array | Human input, external data, tool results |
| `assistant` | `messages` array | Previous model outputs, prefilled responses |

## The Alternating Rule

Messages must alternate: `user`, `assistant`, `user`, `assistant`, ...

- First message must be `user`
- Two consecutive messages with the same role is an API error
- The model generates the next `assistant` turn

## Minimal Valid Request

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    system="Your system prompt here.",
    messages=[
        {"role": "user", "content": "Your user message here."}
    ]
)

print(response.content[0].text)
```

## Multi-Turn Template

```python
messages = []

# Turn 1
messages.append({"role": "user", "content": user_input})
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    system=system_prompt,
    messages=messages
)
messages.append({"role": "assistant", "content": response.content[0].text})

# Turn 2 (repeat pattern)
messages.append({"role": "user", "content": next_user_input})
response = client.messages.create(...)
messages.append({"role": "assistant", "content": response.content[0].text})
```

## Response Object

```python
response.content[0].text    # The text output (most common case)
response.stop_reason        # "end_turn" | "max_tokens" | "stop_sequence"
response.usage.input_tokens  # Tokens sent (all messages + system)
response.usage.output_tokens # Tokens generated
```

## Common Failure Modes

**"The model forgot what I said."**
You removed or truncated the turn that contained the information. The messages array is the only memory. Check what you send on every call.

**"The model ignores my system prompt."**
The system parameter is applied but can be overridden by strong user-turn instructions. Keep system prompt instructions specific and consistent with the user turns.

**"API error: messages must alternate."**
Two consecutive messages with the same role. Validate your messages array before sending. Common cause: error handling code appends a user message without appending the corresponding assistant response first.

**"The model finished mid-sentence."**
`stop_reason` is `max_tokens`. Increase `max_tokens` or shorten your prompt.

## Validation Function

```python
def validate_messages(messages: list) -> list[str]:
    errors = []
    if not messages:
        return ["messages array is empty"]
    if messages[0]["role"] != "user":
        errors.append(f"First message must be 'user', got '{messages[0]['role']}'")
    for i in range(1, len(messages)):
        if messages[i]["role"] == messages[i-1]["role"]:
            errors.append(f"Consecutive '{messages[i]['role']}' at index {i-1}, {i}")
    return errors
```

## Context Window Checklist

- [ ] Is the information you need in the messages array on this call?
- [ ] Are turns in the correct order (oldest first)?
- [ ] Is `max_tokens` large enough for the expected response?
- [ ] Are you logging `usage.input_tokens` to track growth?
- [ ] If truncating history, have you preserved critical early context?
