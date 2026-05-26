# Multi-Turn Conversations and State

> The model remembers nothing. You remember everything. Every conversation is a fresh start where you hand the model its own history.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lesson 01 (request anatomy), Lesson 04 (context engineering)
**Time:** ~45 min
**Learning Objectives:**
- Explain why the Anthropic API is stateless and where conversation state lives
- Build a ConversationManager class that maintains message history across turns
- Implement session save and load using JSON
- Handle context window limits by truncating or summarizing history
- Identify the production failure modes of naive history management

---

## The Problem

You are building a customer support chatbot. A user asks a question, you get an answer, and the user follows up: "Can you explain that last part more?" Claude replies: "I don't have context about what you're referring to."

The model forgot everything from the previous turn. Your users think there is a bug.

There is no bug. The API is stateless by design. Every call to `client.messages.create()` is independent. The model does not have access to previous messages unless you explicitly include them in the request. The "memory" you experience in web UIs is client-side state that the UI sends back to the model on every turn.

This is not a limitation to work around. It is an architectural property that gives you complete control over what context the model sees and when. Once you internalize it, you can build conversations with precise control: summarize long histories, inject context selectively, persist sessions across restarts, fork conversations, and replay them.

---

## The Concept

### The Stateless API Model

Every call to the API is independent. Each request carries the full conversation history you want the model to see.

```
Turn 1                          Turn 2                          Turn 3
------                          ------                          ------

Client sends:                   Client sends:                   Client sends:
  system: "You are..."            system: "You are..."            system: "You are..."
  messages: [                     messages: [                     messages: [
    {user: "What is RAG?"}          {user: "What is RAG?"}          {user: "What is RAG?"}
  ]                                 {asst: "RAG is..."}             {asst: "RAG is..."}
                                    {user: "Give an example"}        {user: "Give an example"}
Model sees:                       ]                                 {asst: "Sure, imagine..."}
  1 message                                                          {user: "How do I build it?"}
                                Model sees:                        ]
                                  2 messages
                                                                Model sees:
                                                                  4 messages

The API has zero knowledge of Turn 1 when processing Turn 2.
YOU assembled that history and sent it.
```

### What State You Are Responsible For

```
┌────────────────────────────────────────────────────────────────────┐
│  YOUR APPLICATION (client-side state)                              │
│                                                                    │
│  - Message history: the list of user + assistant turns             │
│  - System prompt: role, constraints, output format                 │
│  - Session identity: which conversation is this?                   │
│  - Persistence: save to disk / database between restarts           │
│  - Truncation: what to do when history exceeds context window      │
│                                                                    │
└──────────────────────────────┬─────────────────────────────────────┘
                               |
                       Each API call:
                       system + messages[]
                               |
                               v
┌────────────────────────────────────────────────────────────────────┐
│  ANTHROPIC API (stateless)                                         │
│                                                                    │
│  - Processes what you send, exactly                                │
│  - Returns one assistant message                                   │
│  - Remembers nothing after the response                            │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Message Structure

The Anthropic API uses a simple alternating message format. Messages must alternate: user, assistant, user, assistant. The first message must be from the user.

```python
messages = [
    {"role": "user",      "content": "What is RAG?"},
    {"role": "assistant", "content": "RAG stands for Retrieval-Augmented Generation..."},
    {"role": "user",      "content": "Give me a concrete example."},
    {"role": "assistant", "content": "Sure. Imagine a customer support chatbot..."},
    {"role": "user",      "content": "How would I build that?"},
]
```

The system prompt is a separate parameter, not a message in the list.

### Context Window and Truncation

Every model has a context window limit (tokens). The full history must fit within that limit. When history grows too long, you have three options:

```
Option 1: Sliding window         Option 2: Summarize old turns     Option 3: Hard limit
─────────────────────────        ─────────────────────────────     ──────────────
Keep only the last N turns.      Compress old turns into a          Refuse new input when
Oldest turns are dropped.        summary injected into system       context is full.
                                 prompt. Lossy but preserves        Simple. Bad UX.
Simple and fast.                 key context.
Loses long-range context.        Requires an extra LLM call.
```

For production, Option 2 (summarize-and-compress) is usually best for long conversations. Option 1 is fine for short sessions.

---

## Build It

### Step 1: Install and Set Up

```python
# pip install anthropic
# export ANTHROPIC_API_KEY=sk-ant-...
import os
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
import anthropic
```

### Step 2: Session Data Structure

```python
@dataclass
class Message:
    role: str    # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_api_format(self) -> dict:
        """Convert to the format Anthropic's API expects."""
        return {"role": self.role, "content": self.content}


@dataclass
class Session:
    session_id: str
    system_prompt: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    model: str = "claude-3-5-haiku-20241022"
    max_tokens: int = 1024

    def message_count(self) -> int:
        return len(self.messages)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "created_at": self.created_at,
            "messages": [asdict(m) for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        messages = [Message(**m) for m in data.pop("messages", [])]
        session = cls(**data)
        session.messages = messages
        return session
```

### Step 3: ConversationManager

```python
class ConversationManager:
    """
    Manages multi-turn conversations with the Anthropic API.

    Responsibilities:
    - Maintains message history per session
    - Assembles the full message list for each API call
    - Handles session save/load
    - Enforces a max turn limit (sliding window truncation)
    """

    def __init__(
        self,
        max_history_turns: int = 20,
        save_dir: Optional[str] = None,
    ):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.sessions: dict[str, Session] = {}
        self.max_history_turns = max_history_turns  # max user+assistant turn pairs
        self.save_dir = save_dir

    def create_session(
        self,
        session_id: str,
        system_prompt: str,
        model: str = "claude-3-5-haiku-20241022",
    ) -> Session:
        """Create a new conversation session."""
        session = Session(
            session_id=session_id,
            system_prompt=system_prompt,
            model=model,
        )
        self.sessions[session_id] = session
        return session

    def send_message(self, session_id: str, user_message: str) -> str:
        """
        Send a user message and get a response.

        Flow:
        1. Add user message to history
        2. Apply sliding window if history too long
        3. Build API request with full history
        4. Call API
        5. Add assistant response to history
        6. Return assistant response text
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session '{session_id}' not found. Call create_session() first.")

        session = self.sessions[session_id]

        # Add user message to history
        session.messages.append(Message(role="user", content=user_message))

        # Apply sliding window: keep last N turn pairs (user + assistant = 1 pair)
        # We need to keep an even number of messages (pairs), then prepend any
        # leftover message so we always start with "user".
        max_messages = self.max_history_turns * 2
        if len(session.messages) > max_messages:
            # Drop oldest messages; ensure we start on a user message
            truncated = session.messages[-max_messages:]
            # If first message is assistant (truncation split a pair), drop it
            if truncated and truncated[0].role == "assistant":
                truncated = truncated[1:]
            session.messages = truncated

        # Build API message list (no timestamps, just role + content)
        api_messages = [m.to_api_format() for m in session.messages]

        # Call the API
        response = self.client.messages.create(
            model=session.model,
            max_tokens=session.max_tokens,
            system=session.system_prompt,
            messages=api_messages,
        )

        assistant_text = response.content[0].text

        # Add assistant response to history
        session.messages.append(Message(role="assistant", content=assistant_text))

        return assistant_text

    def get_history(self, session_id: str) -> list[Message]:
        """Return the full message history for a session."""
        if session_id not in self.sessions:
            raise ValueError(f"Session '{session_id}' not found.")
        return self.sessions[session_id].messages

    def save_session(self, session_id: str, path: Optional[str] = None) -> str:
        """Save a session to JSON. Returns the file path used."""
        if session_id not in self.sessions:
            raise ValueError(f"Session '{session_id}' not found.")

        if path is None:
            save_dir = self.save_dir or "/tmp"
            path = os.path.join(save_dir, f"session_{session_id}.json")

        session_data = self.sessions[session_id].to_dict()
        with open(path, "w") as f:
            json.dump(session_data, f, indent=2)
        return path

    def load_session(self, path: str) -> Session:
        """Load a session from JSON. Returns the loaded session."""
        with open(path) as f:
            data = json.load(f)
        session = Session.from_dict(data)
        self.sessions[session.session_id] = session
        return session
```

> **Real-world check:** A user completes a 30-message support conversation. The session is saved to disk. Two hours later they reopen the chat. When you load the session and they ask a new question, the model answers as if it remembers everything. How does that work if the API is stateless?

### Step 4: Run a Demo Conversation

```python
def run_demo():
    manager = ConversationManager(max_history_turns=10, save_dir="/tmp")

    # Create a session
    session = manager.create_session(
        session_id="demo-001",
        system_prompt=(
            "You are a concise Python tutor. "
            "Explain concepts clearly with short code examples. "
            "Remember what the student has already asked."
        ),
    )

    # Turn 1
    print("--- Turn 1 ---")
    reply = manager.send_message("demo-001", "What is a list comprehension?")
    print(f"Claude: {reply}\n")

    # Turn 2: follow-up depends on Turn 1
    print("--- Turn 2 ---")
    reply = manager.send_message("demo-001", "Can you show me a more complex example?")
    print(f"Claude: {reply}\n")

    # Turn 3: explicit reference to earlier turns
    print("--- Turn 3 ---")
    reply = manager.send_message("demo-001", "How does that compare to a regular for loop?")
    print(f"Claude: {reply}\n")

    # Save the session
    path = manager.save_session("demo-001")
    print(f"Session saved to: {path}")

    # Verify save/load round-trip
    manager2 = ConversationManager(max_history_turns=10)
    loaded = manager2.load_session(path)
    print(f"Session loaded: {loaded.message_count()} messages in history")

    # Continue the conversation after loading
    print("--- Turn 4 (after load) ---")
    reply = manager2.send_message("demo-001", "What is a generator expression and how is it different?")
    print(f"Claude: {reply}\n")

    return manager
```

---

## Use It

The Anthropic SDK does not provide a built-in ConversationManager class. You manage the messages list yourself. Here is the minimal SDK-native approach:

```python
import anthropic

client = anthropic.Anthropic()
messages = []  # this is your conversation state

def chat(user_input: str) -> str:
    messages.append({"role": "user", "content": user_input})
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system="You are a helpful assistant.",
        messages=messages,
    )
    reply = response.content[0].text
    messages.append({"role": "assistant", "content": reply})
    return reply

# Usage
print(chat("What is Python?"))
print(chat("What are its main use cases?"))
print(chat("How does it compare to JavaScript?"))
```

The ConversationManager you built in the previous section is a structured wrapper around exactly this pattern. It adds session identity, save/load, and history limits. The core mechanic is identical: you maintain a list, append to it, send it on every call.

**Streaming responses** are a common production requirement. The SDK supports them with a context manager:

```python
with client.messages.stream(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    system="You are a helpful assistant.",
    messages=messages,
) as stream:
    full_response = ""
    for text in stream.text_stream:
        print(text, end="", flush=True)
        full_response += text
    print()  # newline after streaming

# Append the full accumulated response to history
messages.append({"role": "assistant", "content": full_response})
```

Streaming does not change the history management logic. You still accumulate the full response and append it to your history before the next turn.

> **Perspective shift:** A product manager says: "Can't we just store the conversation on the server and have the API remember it automatically? Why do we have to send all that history every time?" How would you explain why the stateless design is actually an engineering advantage for production systems?

---

## Ship It

The reusable artifact is `outputs/skill-conversation-manager.md`. It documents the ConversationManager pattern, the sliding window and summarization strategies, and the production failure modes.

The runnable code is `code/main.py`. Run it with:

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python main.py
```

The demo runs a 4-turn conversation, saves the session to `/tmp/session_demo-001.json`, reloads it, and continues the conversation. Inspect the saved JSON to see the full message history.

---

## Evaluate It

Multi-turn conversations fail in ways that single-turn completions do not. Your evaluation needs to cover the history management layer, not just individual responses.

**What to measure:**

| Failure mode | How to detect | How to prevent |
|-------------|--------------|---------------|
| History not passed | Model answers as if Turn 1 never happened | Log the full messages list sent on each API call |
| Truncation drops critical context | Model forgets a constraint stated early in the conversation | Test conversations where critical info is in Turn 1, question is in Turn 20 |
| Role alternation violation | API returns a 400 error about message ordering | Assert messages alternate user/assistant before every API call |
| Context window overflow | API returns a 400 error about token limit | Count tokens before sending; truncate proactively |
| Save/load corruption | Loaded session produces wrong responses | Test round-trip: save, load, continue, verify model references earlier turns |

**Regression test pattern:**

```python
def test_history_persistence(manager):
    """Verify the model references earlier turns after session load."""
    manager.create_session("test-01", system_prompt="Be concise.")
    manager.send_message("test-01", "My favorite color is blue.")
    manager.send_message("test-01", "My lucky number is 7.")
    path = manager.save_session("test-01")

    manager2 = ConversationManager()
    manager2.load_session(path)
    reply = manager2.send_message("test-01", "What did I tell you about myself?")

    assert "blue" in reply.lower() or "7" in reply.lower(), (
        f"Model failed to reference earlier turns. Reply: {reply}"
    )
```

This test pattern verifies the end-to-end history chain, from save to load to inference.
