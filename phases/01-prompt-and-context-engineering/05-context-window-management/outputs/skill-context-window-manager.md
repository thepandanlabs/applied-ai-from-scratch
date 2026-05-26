---
name: skill-context-window-manager
description: Drop-in ContextManager class that enforces a named-region token budget, truncates oldest messages, and optionally summarizes early context to prevent silent data loss.
version: "1.0"
phase: "01"
lesson: "05"
tags: [context-window, token-budget, truncation, summarization, multi-turn]
---

# Skill: Context-Window Manager

A `ContextManager` class for multi-turn applications. Counts tokens before every API call, enforces a named-region budget, and drops or summarizes old messages to keep requests within limits.

## When to Use

- Any multi-turn chat or agent loop where conversations can exceed 10 turns
- Systems with large system prompts or injected documents (RAG, tool outputs)
- Production deployments where silent context loss would cause user-visible bugs

## Setup

```python
import anthropic
from dataclasses import dataclass

client = anthropic.Anthropic()
MODEL = "claude-3-5-haiku-20241022"
```

## The Budget Dataclass

```python
@dataclass
class ContextBudget:
    model_limit: int = 200_000
    output_reserve: int = 4_000

    @property
    def total_input_max(self) -> int:
        return self.model_limit - self.output_reserve

    def fits(self, token_count: int) -> bool:
        return token_count <= self.total_input_max
```

Tune `model_limit` to match your model. Set `output_reserve` equal to your `max_tokens` value.

## The ContextManager

```python
class ContextManager:
    def __init__(
        self,
        system_prompt: str,
        budget: ContextBudget | None = None,
        summarize_when_full: bool = False,
    ):
        self.system = system_prompt
        self.budget = budget or ContextBudget()
        self.summarize_when_full = summarize_when_full
        self.messages: list[dict] = []

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def token_count(self) -> int:
        if not self.messages:
            return 0
        result = client.messages.count_tokens(
            model=MODEL,
            system=self.system,
            messages=self.messages,
        )
        return result.input_tokens

    def enforce_budget(self) -> int:
        dropped = 0
        while self.messages and not self.budget.fits(self.token_count()):
            if self.summarize_when_full and len(self.messages) >= 6:
                dropped += self._summarize_oldest_block()
                break
            else:
                remove = min(2, len(self.messages))
                self.messages = self.messages[remove:]
                dropped += remove
        return dropped

    def _summarize_oldest_block(self, block_size: int = 4) -> int:
        if len(self.messages) < block_size + 1:
            return 0
        block = self.messages[:block_size]
        rest = self.messages[block_size:]
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in block
        )
        resp = client.messages.create(
            model=MODEL,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    "Summarize this conversation in 2-3 sentences. "
                    "Preserve all key facts: names, numbers, decisions.\n\n"
                    + transcript
                ),
            }],
        )
        summary = resp.content[0].text
        self.messages = [
            {"role": "user", "content": f"[Earlier conversation summary: {summary}]"}
        ] + rest
        return block_size - 1

    def complete(self, max_tokens: int = 1024) -> str:
        self.enforce_budget()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=self.system,
            messages=self.messages,
        )
        return resp.content[0].text
```

## Usage Pattern

```python
cm = ContextManager(
    system_prompt="You are a helpful assistant.",
    summarize_when_full=True,   # set False for stateless sessions
)

user_input = "Hello, my name is Sarah."
cm.add_user(user_input)
response = cm.complete()
cm.add_assistant(response)
print(response)
```

## Configuration Guide

| Setting | Default | When to change |
|---|---|---|
| `model_limit` | 200,000 | Match to your deployed model |
| `output_reserve` | 4,000 | Set equal to your `max_tokens` |
| `summarize_when_full` | False | Set True when early context must survive |
| `block_size` in `_summarize_oldest_block` | 4 | Increase for more aggressive compression |

## Monitoring Hook

```python
# Log budget utilization on every call
utilization = cm.token_count() / cm.budget.total_input_max
print(f"Context fill: {utilization:.1%}")
# Alert in production if this exceeds 0.80
```
