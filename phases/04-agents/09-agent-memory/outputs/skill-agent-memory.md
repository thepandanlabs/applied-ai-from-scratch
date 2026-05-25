---
name: skill-agent-memory
description: MemoryManager pattern combining sliding-window short-term, KV long-term, and semantic long-term memory for production agents
version: "1.0"
phase: "04"
lesson: "09"
tags: [agents, memory, context-management, rag]
---

# Agent Memory Manager

## Decision Matrix: Which Memory Type to Use

```
+------------------+------------------------+----------------------------+
|                  |   IN-CONTEXT           |   EXTERNAL                 |
+------------------+------------------------+----------------------------+
| SHORT-TERM       | Message list           | (not applicable)           |
|                  | Use for: current       |                            |
|                  | session coherence      |                            |
+------------------+------------------------+----------------------------+
| LONG-TERM        | System prompt          | Key-value store            |
|                  | Use for: fixed rules,  | Use for: user prefs,       |
|                  | persona, constraints   | account data, settings     |
|                  |                        |                            |
|                  |                        | Semantic store             |
|                  |                        | Use for: large fact sets,  |
|                  |                        | retrieve by relevance      |
+------------------+------------------------+----------------------------+
```

**Routing rule:**
- Always need the fact this session? Use KV.
- Might need it? Use semantic.
- Only need it right now? Keep in message list.
- Never changes per user? Put in system prompt.

## MemoryManager Interface

```python
class MemoryManager:
    def __init__(self, user_id: str, max_turns: int = 10) -> None: ...

    def build_context_prefix(self, user_message: str) -> str:
        """Call before each turn. Returns injected context block."""

    def add_turn(self, role: str, content: str) -> None:
        """Append a message and apply sliding-window truncation."""

    def set_preference(self, key: str, value: str) -> None:
        """Store a structured preference in KV."""

    def add_semantic_fact(self, text: str) -> None:
        """Index a free-text fact for semantic retrieval."""

    def save(self) -> None:
        """Persist KV store to external storage at session end."""
```

## Per-Turn Agent Loop Pattern

```python
def run_agent_turn(memory, user_message, system_prompt, client):
    # 1. Retrieve relevant memory
    context_prefix = memory.build_context_prefix(user_message)

    # 2. Inject memory into the message
    augmented = user_message
    if context_prefix:
        augmented = f"[Memory context]\n{context_prefix}\n\n[User message]\n{user_message}"

    # 3. Append to message list (with truncation)
    memory.add_turn("user", augmented)

    # 4. Call the model
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system=system_prompt,
        messages=memory.messages,
    )

    reply = response.content[0].text
    memory.add_turn("assistant", reply)
    return reply
```

## Truncation Safety Rule

Always truncate at turn boundaries (user + assistant pairs). Never start the message list on an assistant message.

```python
def truncate_messages(messages, max_turns=10):
    max_messages = max_turns * 2
    if len(messages) > max_messages:
        messages = messages[-max_messages:]
        while messages and messages[0]["role"] != "user":
            messages = messages[1:]
    return messages
```

## Production Backend Swaps

| Component | Dev/Demo | Production |
|-----------|----------|------------|
| KV store | Python dict | Redis, DynamoDB |
| Embeddings | Bag-of-words mock | Anthropic embeddings, sentence-transformers |
| Vector search | Cosine over list | pgvector, Qdrant, Pinecone |
| Session storage | In-process | Persistent DB with user_id index |

## Evaluation Checklist

- [ ] After N turns, message list does not start with an assistant message
- [ ] KV preferences are available on turn N+1 even after truncation
- [ ] Semantic store retrieves at least 1 relevant fact in top-3 for 8/10 test queries
- [ ] Token count per turn is lower with semantic retrieval than with full history injection (when fact set > 50 entries)
