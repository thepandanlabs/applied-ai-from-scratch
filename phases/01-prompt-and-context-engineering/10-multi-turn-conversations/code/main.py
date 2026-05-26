# Multi-Turn Conversations and State
# Lesson 10: Phase 01 - Prompt and Context Engineering
#
# pip install anthropic
# export ANTHROPIC_API_KEY=sk-ant-...

import os
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import anthropic


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """A single message in a conversation, with metadata."""
    role: str      # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)

    def to_api_format(self) -> dict:
        """Convert to the dict format the Anthropic API expects."""
        return {"role": self.role, "content": self.content}


@dataclass
class Session:
    """
    A conversation session: all state needed to continue a conversation
    after any number of turns, including across process restarts.
    """
    session_id: str
    system_prompt: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    model: str = "claude-3-5-haiku-20241022"
    max_tokens: int = 1024

    def message_count(self) -> int:
        """Total messages in history (both user and assistant)."""
        return len(self.messages)

    def turn_count(self) -> int:
        """Number of complete turns (user + assistant pairs)."""
        return sum(1 for m in self.messages if m.role == "user")

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
        messages_data = data.pop("messages", [])
        session = cls(**data)
        session.messages = [Message(**m) for m in messages_data]
        return session


# ---------------------------------------------------------------------------
# ConversationManager
# ---------------------------------------------------------------------------

class ConversationManager:
    """
    Manages multi-turn conversations with the Anthropic API.

    Key responsibility: the API is stateless. This class is the client-side
    state store. Every call to send_message() assembles the full history
    and sends it to the API.

    Features:
    - Multiple concurrent sessions (by session_id)
    - Sliding window truncation when history exceeds max_history_turns
    - Session save/load to JSON for persistence across restarts
    """

    def __init__(
        self,
        max_history_turns: int = 20,
        save_dir: Optional[str] = None,
    ):
        """
        Args:
            max_history_turns: Maximum number of user+assistant turn pairs to keep
                               in history. Older turns are dropped when exceeded.
            save_dir: Default directory for save_session(). Defaults to /tmp.
        """
        self.client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
        self.sessions: dict[str, Session] = {}
        self.max_history_turns = max_history_turns
        self.save_dir = save_dir or "/tmp"

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def create_session(
        self,
        session_id: str,
        system_prompt: str,
        model: str = "claude-3-5-haiku-20241022",
        max_tokens: int = 1024,
    ) -> Session:
        """
        Create a new conversation session.
        Raises ValueError if session_id already exists.
        """
        if session_id in self.sessions:
            raise ValueError(
                f"Session '{session_id}' already exists. "
                "Use a unique session_id or delete the existing session."
            )
        session = Session(
            session_id=session_id,
            system_prompt=system_prompt,
            model=model,
            max_tokens=max_tokens,
        )
        self.sessions[session_id] = session
        return session

    def delete_session(self, session_id: str) -> None:
        """Remove a session from memory (does not delete saved JSON files)."""
        self.sessions.pop(session_id, None)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def send_message(self, session_id: str, user_message: str) -> str:
        """
        Send a user message in a session and return the assistant response.

        Steps:
        1. Append user message to session history
        2. Apply sliding window if history is too long
        3. Build the API messages list from history
        4. Call the API (stateless: sends full history each time)
        5. Append assistant response to history
        6. Return assistant response text
        """
        session = self._get_session(session_id)

        # Step 1: append user turn
        session.messages.append(Message(role="user", content=user_message))

        # Step 2: sliding window truncation
        self._truncate_history(session)

        # Step 3: build API messages (no internal metadata, just role + content)
        api_messages = [m.to_api_format() for m in session.messages]

        # Step 4: call the API
        response = self.client.messages.create(
            model=session.model,
            max_tokens=session.max_tokens,
            system=session.system_prompt,
            messages=api_messages,
        )

        assistant_text = response.content[0].text

        # Step 5: append assistant turn
        session.messages.append(Message(role="assistant", content=assistant_text))

        return assistant_text

    def send_message_streaming(self, session_id: str, user_message: str) -> str:
        """
        Send a message and stream the response token by token.
        Returns the full accumulated response text.

        History management is identical to send_message().
        """
        session = self._get_session(session_id)
        session.messages.append(Message(role="user", content=user_message))
        self._truncate_history(session)

        api_messages = [m.to_api_format() for m in session.messages]

        full_response = ""
        with self.client.messages.stream(
            model=session.model,
            max_tokens=session.max_tokens,
            system=session.system_prompt,
            messages=api_messages,
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                full_response += text
        print()  # newline after streaming

        session.messages.append(Message(role="assistant", content=full_response))
        return full_response

    # ------------------------------------------------------------------
    # History access
    # ------------------------------------------------------------------

    def get_history(self, session_id: str) -> list[Message]:
        """Return all messages in a session's history."""
        return self._get_session(session_id).messages

    def print_history(self, session_id: str) -> None:
        """Print the conversation history in a readable format."""
        session = self._get_session(session_id)
        print(f"\n{'=' * 55}")
        print(f"Session: {session_id}  |  {session.turn_count()} turn(s)")
        print(f"{'=' * 55}")
        for msg in session.messages:
            role_label = "You  " if msg.role == "user" else "Claude"
            ts = time.strftime("%H:%M:%S", time.localtime(msg.timestamp))
            # Truncate long messages for display
            content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
            print(f"[{ts}] {role_label}: {content}")
        print()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_session(self, session_id: str, path: Optional[str] = None) -> str:
        """
        Save a session to a JSON file.
        Returns the path where the file was saved.
        """
        session = self._get_session(session_id)
        if path is None:
            path = os.path.join(self.save_dir, f"session_{session_id}.json")

        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None

        with open(path, "w") as f:
            json.dump(session.to_dict(), f, indent=2)
        return path

    def load_session(self, path: str) -> Session:
        """
        Load a session from a JSON file.
        The session is added to this manager's sessions dict.
        Returns the loaded Session object.
        """
        with open(path) as f:
            data = json.load(f)

        session = Session.from_dict(data)
        self.sessions[session.session_id] = session
        return session

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_session(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            raise ValueError(
                f"Session '{session_id}' not found. "
                "Call create_session() or load_session() first."
            )
        return self.sessions[session_id]

    def _truncate_history(self, session: Session) -> None:
        """
        Apply sliding window: keep only the most recent max_history_turns pairs.
        Ensures the history always starts with a "user" message (required by API).
        """
        max_messages = self.max_history_turns * 2  # pairs -> individual messages
        if len(session.messages) <= max_messages:
            return

        # Keep the most recent max_messages messages
        truncated = session.messages[-max_messages:]

        # The API requires messages to alternate user/assistant starting with user.
        # If truncation cuts the first pair in half, drop the orphaned assistant message.
        if truncated and truncated[0].role == "assistant":
            truncated = truncated[1:]

        dropped = len(session.messages) - len(truncated)
        session.messages = truncated
        print(f"  [History truncated: dropped {dropped} oldest message(s)]")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run_demo():
    """
    Demonstrates a multi-turn conversation with save/load persistence.
    The demo shows:
    1. A session continuing across turns where each turn builds on the last
    2. Explicit cross-turn reference ("what did I just say?")
    3. Save, load, and resume in a fresh ConversationManager instance
    """
    print("=" * 55)
    print("LESSON 10: MULTI-TURN CONVERSATIONS AND STATE")
    print("=" * 55)

    manager = ConversationManager(max_history_turns=10, save_dir="/tmp")

    # Create a session
    session = manager.create_session(
        session_id="demo-001",
        system_prompt=(
            "You are a concise Python tutor. "
            "Give short, clear explanations with brief code examples. "
            "Keep each response to 3-5 sentences maximum."
        ),
    )
    print(f"\nCreated session: {session.session_id}")

    # Turn 1
    print("\n--- Turn 1 ---")
    reply = manager.send_message("demo-001", "What is a list comprehension in Python?")
    print(f"User: What is a list comprehension in Python?")
    print(f"Claude: {reply}")

    # Turn 2: explicit follow-up to Turn 1
    print("\n--- Turn 2 ---")
    reply = manager.send_message("demo-001", "Can you show me a more complex example with a condition?")
    print(f"User: Can you show me a more complex example with a condition?")
    print(f"Claude: {reply}")

    # Turn 3: references both previous turns
    print("\n--- Turn 3 ---")
    reply = manager.send_message("demo-001", "How does that compare to a regular for loop in terms of performance?")
    print(f"User: How does that compare to a regular for loop in terms of performance?")
    print(f"Claude: {reply}")

    # Save the session
    path = manager.save_session("demo-001")
    print(f"\n[Session saved to: {path}]")

    # Inspect the saved JSON
    with open(path) as f:
        saved = json.load(f)
    print(f"[Saved: {len(saved['messages'])} messages in JSON file]")

    # Simulate a process restart by creating a fresh manager
    print("\n--- Simulating process restart ---")
    manager2 = ConversationManager(max_history_turns=10)
    loaded = manager2.load_session(path)
    print(f"[Loaded: session '{loaded.session_id}' with {loaded.message_count()} messages]")

    # Turn 4: continues after load; model should reference earlier context
    print("\n--- Turn 4 (after session reload) ---")
    reply = manager2.send_message(
        "demo-001",
        "Based on what we just covered, when would you NOT use a list comprehension?"
    )
    print(f"User: Based on what we just covered, when would you NOT use a list comprehension?")
    print(f"Claude: {reply}")

    # Show the full history
    manager2.print_history("demo-001")

    # Demonstrate minimal SDK-native pattern (no ConversationManager)
    print("\n" + "=" * 55)
    print("MINIMAL SDK-NATIVE PATTERN (for comparison)")
    print("=" * 55)
    run_minimal_pattern()


def run_minimal_pattern():
    """
    The raw SDK pattern: just a list.
    ConversationManager wraps exactly this.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    messages = []  # your entire conversation state

    def chat(user_input: str) -> str:
        messages.append({"role": "user", "content": user_input})
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system="Be brief.",
            messages=messages,
        )
        reply = response.content[0].text
        messages.append({"role": "assistant", "content": reply})
        return reply

    print("\nTurn 1:")
    print(f"User: Name one Python built-in function.")
    print(f"Claude: {chat('Name one Python built-in function.')}")

    print("\nTurn 2:")
    print(f"User: Give an example of how to use it.")
    print(f"Claude: {chat('Give an example of how to use it.')}")

    print(f"\n[Messages in history: {len(messages)}]")
    print("[Notice: 'it' in Turn 2 makes sense because Turn 1 is in the history]")


if __name__ == "__main__":
    run_demo()
