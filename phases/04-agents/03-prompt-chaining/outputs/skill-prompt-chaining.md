---
name: skill-prompt-chaining
description: Reusable gated prompt chain template with per-step retry logic and type-safe step wiring
version: "1.0"
phase: "04"
lesson: "03"
tags: [prompt-chaining, workflows, gates, retry, pipeline]
---

# Skill: Prompt Chaining

A gated prompt chain where each step is a separate LLM call.
Output of step N is input to step N+1. A gate between steps halts the chain when quality is insufficient.

## Usage

```python
chain = (
    Chain()
    .add_step("extract", my_extract_fn, retries=1)
    .add_gate("quality_check", my_gate_fn)
    .add_step("transform", my_transform_fn, retries=1)
    .add_step("finalize", my_finalize_fn)
)

result = chain.run(initial_input)
if isinstance(result, ChainError):
    print(f"Chain halted: {result}")
else:
    # result is the output of the final step
    process(result)
```

## Full Template

```python
import anthropic
import time
from dataclasses import dataclass
from typing import Callable, Any

client = anthropic.Anthropic()


@dataclass
class ChainError:
    """Returned when a gate fails or all retries are exhausted."""
    step: str
    reason: str

    def __str__(self) -> str:
        return f"Chain halted at '{self.step}': {self.reason}"


class Step:
    def __init__(self, name: str, fn: Callable, retries: int = 0, is_gate: bool = False):
        self.name = name
        self.fn = fn
        self.retries = retries
        self.is_gate = is_gate


class Chain:
    """
    Composable prompt chain with gate support and per-step retry logic.

    Rules:
    - Each step receives the output of the previous step as its only argument
    - A gate receives the current value and returns None (pass) or ChainError (halt)
    - Retries use exponential backoff (2^attempt seconds)
    - If all retries are exhausted, a ChainError is returned
    """
    def __init__(self):
        self._steps: list[Step] = []

    def add_step(self, name: str, fn: Callable, retries: int = 0) -> "Chain":
        self._steps.append(Step(name, fn, retries=retries))
        return self

    def add_gate(self, name: str, fn: Callable) -> "Chain":
        self._steps.append(Step(name, fn, is_gate=True))
        return self

    def run(self, initial_input: Any) -> Any | ChainError:
        value = initial_input

        for step in self._steps:
            attempt = 0
            last_error = None

            while attempt <= step.retries:
                try:
                    result = step.fn(value)

                    if step.is_gate:
                        if result is not None:
                            return result  # Gate failed: halt chain
                        break  # Gate passed: continue with unchanged value

                    value = result
                    break

                except Exception as e:
                    last_error = e
                    attempt += 1
                    if attempt <= step.retries:
                        wait = 2 ** attempt
                        print(f"  [retry {attempt}/{step.retries}] '{step.name}' failed: {e}. Retrying in {wait}s...")
                        time.sleep(wait)

            else:
                return ChainError(
                    step.name,
                    f"All {step.retries + 1} attempts failed. Last error: {last_error}"
                )

        return value
```

## Writing Step Functions

Each step function takes one argument (the output of the previous step) and returns one value (the input for the next step).

```python
def step_extract(text: str) -> list[str]:
    """Returns a list of extracted items."""
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": f"Extract key points as a JSON array:\n{text}"}]
    )
    import json
    return json.loads(response.content[0].text)


def step_draft(items: list[str]) -> str:
    """Takes extracted items, returns draft text."""
    items_text = "\n".join(f"- {item}" for item in items)
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": f"Write a summary using ONLY these points:\n{items_text}"}]
    )
    return response.content[0].text
```

## Writing Gate Functions

A gate receives the current value and returns `None` (pass) or `ChainError` (halt).

```python
def gate_extraction_quality(items: list[str]) -> ChainError | None:
    """Halt if fewer than 3 substantive items were extracted."""
    substantive = [i for i in items if isinstance(i, str) and len(i.strip()) > 20]
    if len(substantive) < 3:
        return ChainError(
            "gate_extraction_quality",
            f"Only {len(substantive)} substantive items found. Need at least 3."
        )
    return None  # Pass
```

## Type-Bridging Between Steps

When consecutive steps have incompatible types, use a lambda wrapper:

```python
# step_extract returns list[str], but step_draft also needs the topic
topic = "Machine Learning"

chain = (
    Chain()
    .add_step("extract", lambda text: step_extract(text))
    .add_gate("quality", gate_extraction_quality)
    .add_step("draft",   lambda items: step_draft(items, topic))  # captures topic via closure
    .add_step("polish",  step_polish)
)
```

## Checklist Before Shipping

- [ ] Each step function has a single, focused system prompt
- [ ] Each step's input is ONLY what it needs (not the full context from step 1)
- [ ] Gates check measurable properties (count, length, schema) not LLM-judged quality
- [ ] All LLM calls in steps catch JSON parse errors and return clean defaults
- [ ] Retry counts are set based on expected flakiness (0 for polishing, 1-2 for extraction)
- [ ] ChainError messages are descriptive enough to act on without re-reading the code
- [ ] The chain is tested step-by-step in isolation before testing end-to-end

## When to Add a Gate

Add a gate when:
- The downstream step will produce confident-sounding garbage if given bad input
- The failure mode is silent (polished hallucination looks better than raw hallucination)
- You can express the quality check as a measurable property (count, length, schema match)

Do not add an LLM-judged gate unless the property cannot be measured structurally. LLM gates add latency, cost, and their own failure modes.
