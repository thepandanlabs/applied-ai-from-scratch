---
name: skill-context-engineering
description: Context assembly guide covering layer ordering, primacy/recency bias, token budgeting, and the lost-in-middle problem
version: "1.0"
phase: "01"
lesson: "04"
tags: [context-engineering, rag, retrieval, context-window, token-budget]
---

# Skill: Context Engineering

The model reads everything you send, but it does not weight everything equally. Position and volume determine salience. This skill covers how to arrange context for maximum signal.

## The Core Insight

**Primacy bias:** Content at the start of the context (system prompt) is weighted heavily as the authoritative frame.

**Recency bias:** Content at the end of the context (the final user message) is weighted heavily as the most immediate signal.

**Lost in middle:** Content sandwiched between long blocks of other content is most likely to be underweighted. This is measurable: the same document at position 1 or 10 in a list performs differently from the same document at position 5.

---

## The 4-Layer Context Order

Arrange content in this order for RAG and retrieval tasks:

```
Layer 1: Task instructions          -> System prompt (primacy)
Layer 2: Retrieved documents        -> First part of final user message
Layer 3: Conversation history       -> Earlier messages (trimmed)
Layer 4: Current user query         -> End of final user message (recency)
```

---

## Assembly Function

```python
def assemble_context(
    query: str,
    documents: list[str],
    history: list[dict],
    instructions: str,
    total_budget: int = 4000,
) -> tuple[str, list[dict]]:
    """
    Returns (system_prompt, messages_array) with explicit layer ordering.
    documents: ordered by relevance (most relevant first).
    history: ordered chronologically (oldest first).
    """
    document_budget = int(total_budget * 0.55)
    history_budget  = int(total_budget * 0.30)

    # Layer 1: instructions in system prompt
    system = instructions

    # Layer 2: documents (truncate by relevance order)
    docs = truncate_by_budget(documents, document_budget)
    docs_block = format_documents(docs) if docs else ""

    # Layer 3: history (most recent turns that fit)
    trimmed = truncate_history_recent(history, history_budget)

    # Layer 4: query at end of final user message
    final = f"{docs_block}\n\nQUESTION: {query}" if docs_block else f"QUESTION: {query}"

    messages = list(trimmed) + [{"role": "user", "content": final}]
    return system, messages


def truncate_by_budget(items: list[str], max_tokens: int) -> list[str]:
    result, count = [], 0
    for item in items:
        t = len(item) // 4  # rough token estimate
        if count + t > max_tokens:
            break
        result.append(item)
        count += t
    return result


def truncate_history_recent(history: list[dict], max_tokens: int) -> list[dict]:
    result, count = [], 0
    for turn in reversed(history):
        t = len(turn["content"]) // 4
        if count + t > max_tokens:
            break
        result.insert(0, turn)
        count += t
    while result and result[0]["role"] != "user":
        result = result[1:]
    return result


def format_documents(docs: list[str]) -> str:
    return "RELEVANT DOCUMENTS:\n\n" + "\n\n---\n\n".join(
        f"[Doc {i+1}]\n{doc}" for i, doc in enumerate(docs)
    )
```

---

## Token Budget Guidelines

| Layer | Typical allocation | Notes |
|-------|--------------------|-------|
| Instructions (system) | 5-10% | Dense, always included |
| Retrieved documents | 45-60% | Core content, trim by relevance |
| Conversation history | 20-30% | Trim oldest first, keep anchor turns |
| Current query | 5-10% | Always included, keep short |
| Output headroom | 10-20% | Reserve for `max_tokens` |

Adjust allocations based on task type:
- Summarization: more document budget, less history
- Multi-turn chat: more history budget, fewer documents
- Single-shot Q&A: mostly documents, minimal history

---

## Fixing the Lost-in-Middle Problem

When you have many documents, position the most relevant one at the start or end of the document block:

```python
def reorder_for_attention(docs: list[str]) -> list[str]:
    """
    Put highest-relevance documents at positions that benefit from attention:
    first (primacy) or last (recency). Middle positions get less attention.
    For 5+ documents, put the top doc last (closest to the query).
    """
    if len(docs) <= 2:
        return docs
    # Move the most relevant doc (index 0) to the end
    return docs[1:] + [docs[0]]
```

---

## History Truncation: Preserve Anchor Turns

When trimming history, the most recent turns are usually the most relevant. But sometimes early turns contain critical context (user stated their role, account type, constraints). Preserve these:

```python
def truncate_history_with_anchor(
    history: list[dict],
    max_tokens: int,
    anchor_turns: int = 2   # preserve this many turns from the start
) -> list[dict]:
    """Keep the first N turns (anchor) plus the most recent turns that fit."""
    if len(history) <= anchor_turns:
        return history

    anchor = history[:anchor_turns]
    anchor_tokens = sum(len(t["content"]) // 4 for t in anchor)
    remaining_budget = max_tokens - anchor_tokens

    result, count = [], 0
    for turn in reversed(history[anchor_turns:]):
        t = len(turn["content"]) // 4
        if count + t > remaining_budget:
            break
        result.insert(0, turn)
        count += t

    return anchor + result
```

---

## Production Checklist

- [ ] Instructions are in the system prompt, not buried in the user message
- [ ] Documents are ordered by relevance before assembly
- [ ] History is trimmed from the oldest end, not truncated randomly
- [ ] The current query is the last thing in the final user message
- [ ] Token usage is logged per call to calibrate budget allocations
- [ ] Lost-in-middle is tested: check that answers degrade when relevant doc is at position 5+ in a long list
- [ ] Budget is calibrated for your specific task type (more docs vs. more history)
