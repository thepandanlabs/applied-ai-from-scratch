---
name: skill-conversation-manager
description: Pattern guide for managing multi-turn conversation state with stateless LLM APIs - covers history management, truncation strategies, session persistence, and production failure modes.
version: "1.0"
phase: "01"
lesson: "10"
tags: [multi-turn, conversation, state-management, session, history, anthropic-sdk]
---

# Skill: Multi-Turn Conversation Manager

Use this skill when building any feature that requires conversation continuity: chatbots, support flows, interactive assistants, or anything where a user's second message depends on the first.

---

## The Core Pattern

The API is stateless. You maintain state. Every call sends the full history.

```python
import anthropic

client = anthropic.Anthropic()
messages = []  # ALL your state lives here

def chat(user_input: str) -> str:
    messages.append({"role": "user", "content": user_input})
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system="Your system prompt here.",
        messages=messages,
    )
    reply = response.content[0].text
    messages.append({"role": "assistant", "content": reply})
    return reply
```

This is the complete pattern. Everything else in this skill is production hardening around it.

---

## Message Format Requirements

The API requires:
1. Messages must alternate: user, assistant, user, assistant
2. The first message must be from the user
3. The system prompt is a separate parameter, not a message in the list

```python
# CORRECT
messages = [
    {"role": "user",      "content": "..."},
    {"role": "assistant", "content": "..."},
    {"role": "user",      "content": "..."},
]

# WRONG: starts with assistant
messages = [
    {"role": "assistant", "content": "..."},  # API will reject this
    {"role": "user",      "content": "..."},
]

# WRONG: two user messages in a row
messages = [
    {"role": "user", "content": "First question"},
    {"role": "user", "content": "Follow up"},   # API will reject this
]
```

---

## Truncation Strategies

When conversation history exceeds the context window, use one of these strategies:

### Strategy 1: Sliding Window (default for short sessions)

Keep only the last N turn pairs. Fast, no extra API calls.

```python
def truncate_sliding_window(messages: list, max_turns: int = 20) -> list:
    """Keep the most recent max_turns turn pairs."""
    max_messages = max_turns * 2
    if len(messages) <= max_messages:
        return messages
    truncated = messages[-max_messages:]
    # Ensure we start on a user message
    if truncated and truncated[0]["role"] == "assistant":
        truncated = truncated[1:]
    return truncated
```

### Strategy 2: Summarize and Compress (for long sessions)

Compress old turns into a summary injected into the system prompt. Preserves context at the cost of one extra LLM call.

```python
def summarize_and_compress(
    messages: list,
    system_prompt: str,
    client: anthropic.Anthropic,
    keep_recent: int = 6,  # keep last N messages uncompressed
) -> tuple[list, str]:
    """
    Compress old messages into a summary appended to the system prompt.
    Returns (recent_messages, updated_system_prompt).
    """
    if len(messages) <= keep_recent:
        return messages, system_prompt

    old_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # Build a transcript of old messages for summarization
    transcript = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in old_messages
    )

    summary_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system="Summarize the following conversation in 3-5 bullet points. Focus on facts stated and decisions made.",
        messages=[{"role": "user", "content": transcript}],
    )
    summary = summary_response.content[0].text

    updated_system = (
        f"{system_prompt}\n\n"
        f"Earlier conversation summary:\n{summary}"
    )
    return recent_messages, updated_system
```

---

## Session Persistence

### Save

```python
import json

def save_session(session_id: str, messages: list, system_prompt: str, path: str):
    data = {
        "session_id": session_id,
        "system_prompt": system_prompt,
        "messages": messages,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
```

### Load

```python
def load_session(path: str) -> dict:
    with open(path) as f:
        return json.load(f)

# Usage
data = load_session("session_001.json")
messages = data["messages"]
system_prompt = data["system_prompt"]
```

---

## Production Failure Modes

| Failure | Symptom | Fix |
|---------|---------|-----|
| History not sent | Model answers as if Turn 1 never happened | Log the full messages list before each API call during development |
| Role alternation broken | API 400 error about message ordering | Assert `messages[0]["role"] == "user"` and that roles alternate before every call |
| Context window exceeded | API 400 error about token limit | Count tokens with `client.count_tokens()` and truncate before sending |
| History grows unbounded | Memory grows over hours/days in a long-running process | Always set a max_history_turns limit |
| Session not saved after crash | User loses entire conversation context | Save after every turn in high-stakes flows |
| Stale system prompt after load | Context from old session bleeds into new session | Always restore system_prompt from the saved session data |

---

## Streaming Pattern

```python
full_response = ""
with client.messages.stream(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    system=system_prompt,
    messages=messages,
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
        full_response += text
print()

# History management is identical: append the full response
messages.append({"role": "assistant", "content": full_response})
```

Streaming does not change history management. Always append the full accumulated response before the next turn.

---

## Quick Reference

```
State lives: client-side (your code)
State format: list of {"role": ..., "content": ...} dicts
System prompt: separate parameter, not in messages list
Message order: must alternate user/assistant, starting with user
Truncation: sliding window (simple) or summarize (context-preserving)
Persistence: serialize messages list + system_prompt to JSON
Recovery: restore messages list from JSON on load
```
