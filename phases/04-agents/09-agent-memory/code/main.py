"""
Lesson 09: Agent Memory - Short-Term, Long-Term, When You Don't Need It

Demonstrates all three runtime memory types in a single agent session:
1. Short-term: sliding-window message list truncation
2. Long-term KV: dict-based user preference store
3. Long-term semantic: cosine-similarity fact retrieval

Run: python main.py
Requires: ANTHROPIC_API_KEY environment variable
"""

import math
import os
from collections import Counter
from dataclasses import dataclass, field

import anthropic

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class UserFacts:
    preferences: dict[str, str] = field(default_factory=dict)
    facts: dict[str, str] = field(default_factory=dict)


# In-process KV store. In production: swap for Redis or DynamoDB.
_KV_STORE: dict[str, UserFacts] = {}


# ---------------------------------------------------------------------------
# Short-term memory: sliding window truncation
# ---------------------------------------------------------------------------

def truncate_messages(
    messages: list[dict],
    max_turns: int = 10,
) -> list[dict]:
    """
    Keep the last max_turns pairs (user + assistant) from the message list.
    Always truncates at turn boundaries to avoid orphaned messages.
    """
    max_messages = max_turns * 2
    if len(messages) > max_messages:
        messages = messages[-max_messages:]
        # Ensure we start on a user message (never on an assistant message)
        while messages and messages[0]["role"] != "user":
            messages = messages[1:]
    return messages


# ---------------------------------------------------------------------------
# Long-term KV store
# ---------------------------------------------------------------------------

def load_user_facts(user_id: str) -> UserFacts:
    return _KV_STORE.get(user_id, UserFacts())


def save_user_facts(user_id: str, facts: UserFacts) -> None:
    _KV_STORE[user_id] = facts


def format_kv_context(facts: UserFacts) -> str:
    """Convert stored facts to an injectable text block."""
    lines = []
    if facts.preferences:
        lines.append("User preferences:")
        for k, v in facts.preferences.items():
            lines.append(f"  - {k}: {v}")
    if facts.facts:
        lines.append("Known user facts:")
        for k, v in facts.facts.items():
            lines.append(f"  - {k}: {v}")
    return "\n".join(lines) if lines else ""


# ---------------------------------------------------------------------------
# Long-term semantic store (mock embeddings)
# ---------------------------------------------------------------------------

def simple_embed(text: str) -> dict[str, float]:
    """
    Bag-of-words mock embedding. Replace with real embeddings in production
    (e.g., anthropic.embeddings or sentence-transformers).
    Returns a normalized term-frequency vector as a sparse dict.
    """
    words = text.lower().split()
    counts = Counter(words)
    norm = math.sqrt(sum(v ** 2 for v in counts.values()))
    if norm == 0:
        return {}
    return {w: c / norm for w, c in counts.items()}


def cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    return sum(a.get(w, 0.0) * b.get(w, 0.0) for w in b)


class SemanticStore:
    """
    Stores text facts indexed by embedding vector.
    Retrieves top-K most relevant facts for a given query.
    """

    def __init__(self) -> None:
        self._entries: list[tuple[str, dict[str, float]]] = []

    def add(self, text: str) -> None:
        if text:
            self._entries.append((text, simple_embed(text)))

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        if not self._entries:
            return []
        q_vec = simple_embed(query)
        scored = [
            (cosine_similarity(q_vec, vec), text)
            for text, vec in self._entries
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for score, text in scored[:top_k] if score > 0]


# ---------------------------------------------------------------------------
# MemoryManager: combines all three memory types
# ---------------------------------------------------------------------------

class MemoryManager:
    """
    Manages all three runtime memory types for a single user session.

    Usage:
        memory = MemoryManager(user_id="user-123")
        # each turn:
        reply = run_agent_turn(memory, user_message, system_prompt, client)
        # end of session:
        memory.save()
    """

    def __init__(self, user_id: str, max_turns: int = 10) -> None:
        self.user_id = user_id
        self.max_turns = max_turns
        self.kv: UserFacts = load_user_facts(user_id)
        self.semantic: SemanticStore = SemanticStore()
        self.messages: list[dict] = []

    def build_context_prefix(self, user_message: str) -> str:
        """
        Retrieve relevant memory and format it for injection.
        Called once per turn, before appending the user message.
        """
        kv_block = format_kv_context(self.kv)
        semantic_hits = self.semantic.retrieve(user_message, top_k=3)
        semantic_block = (
            "Recalled facts:\n" + "\n".join(f"  - {f}" for f in semantic_hits)
            if semantic_hits else ""
        )
        parts = [p for p in [kv_block, semantic_block] if p]
        return "\n\n".join(parts) if parts else ""

    def add_turn(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.messages = truncate_messages(self.messages, max_turns=self.max_turns)

    def set_preference(self, key: str, value: str) -> None:
        self.kv.preferences[key] = value

    def set_fact(self, key: str, value: str) -> None:
        self.kv.facts[key] = value

    def add_semantic_fact(self, text: str) -> None:
        self.semantic.add(text)

    def save(self) -> None:
        save_user_facts(self.user_id, self.kv)


# ---------------------------------------------------------------------------
# Agent turn runner
# ---------------------------------------------------------------------------

def run_agent_turn(
    memory: MemoryManager,
    user_message: str,
    system_prompt: str,
    client: anthropic.Anthropic,
) -> str:
    context_prefix = memory.build_context_prefix(user_message)

    augmented_message = user_message
    if context_prefix:
        augmented_message = (
            f"[Memory context - use this to inform your response]\n"
            f"{context_prefix}\n\n"
            f"[User message]\n{user_message}"
        )

    memory.add_turn("user", augmented_message)

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system=system_prompt,
        messages=memory.messages,
    )

    reply = response.content[0].text
    memory.add_turn("assistant", reply)

    # Log token usage per turn (key for cost tracking)
    usage = response.usage
    print(f"  [tokens: in={usage.input_tokens} out={usage.output_tokens}]")

    return reply


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = (
        "You are a helpful cooking assistant. "
        "When memory context is provided, use it to personalize your response. "
        "Be concise."
    )

    user_id = "demo-user-001"
    memory = MemoryManager(user_id=user_id, max_turns=5)

    # Seed the KV store with structured preferences
    memory.set_preference("diet", "vegetarian")
    memory.set_preference("units", "metric")

    # Seed the semantic store with some prior session facts
    memory.add_semantic_fact("User dislikes spicy food")
    memory.add_semantic_fact("User has a nut allergy")
    memory.add_semantic_fact("User prefers quick 30-minute recipes")
    memory.add_semantic_fact("User enjoys Mediterranean cuisine")
    memory.add_semantic_fact("User's favorite kitchen tool is a cast iron pan")

    conversation = [
        "What's a good high-protein breakfast?",
        "Can you suggest a lunch that takes under 30 minutes?",
        "I'm cooking dinner tonight for four people. Any ideas?",
        "What about a dessert that's not too sweet?",
        "Can you give me a shopping list for the dinner you suggested?",
        # Turn 6: original preferences are beyond max_turns=5 window
        # but KV store still has them
        "Actually, can you make sure all suggestions work for my dietary restrictions?",
    ]

    print("=" * 60)
    print("AGENT MEMORY DEMO")
    print("KV preferences:", dict(memory.kv.preferences))
    print("Semantic facts seeded:", memory.semantic._entries.__len__())
    print("=" * 60)

    for i, user_msg in enumerate(conversation, start=1):
        print(f"\nTurn {i}")
        print(f"User: {user_msg}")
        context = memory.build_context_prefix(user_msg)
        if context:
            print(f"[Memory injected]:\n{context}")
        reply = run_agent_turn(memory, user_msg, system_prompt, client)
        print(f"Agent: {reply[:300]}{'...' if len(reply) > 300 else ''}")
        print(f"[Message list length after truncation: {len(memory.messages)}]")

    memory.save()

    print("\n" + "=" * 60)
    print("Session ended. KV store saved.")
    print("Saved preferences:", dict(memory.kv.preferences))
    print("=" * 60)


if __name__ == "__main__":
    main()
