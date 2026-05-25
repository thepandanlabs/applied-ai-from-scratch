---
name: skill-parallelization
description: Fan-out/fan-in pattern for N independent LLM calls, plus voting pattern for confidence on a single decision
version: "1.0"
phase: "04"
lesson: "05"
tags: [parallelization, asyncio, fan-out, voting, concurrency]
---

# Skill: Parallelization

Two sub-patterns. Pick the one that matches your problem.

---

## Sub-pattern A: Sectioning (N independent tasks)

Use when: you have N inputs that each need an LLM call and there is no dependency between them.

### Async version (recommended for async codebases)

```python
import asyncio
import anthropic

async def process_single(client: anthropic.AsyncAnthropic, item: str, item_id: int) -> dict:
    """Replace the prompt and output schema for your use case."""
    message = await client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        messages=[
            {"role": "user", "content": f"[YOUR PROMPT HERE]\n\n{item}"}
        ]
    )
    return {"id": item_id, "output": message.content[0].text}


async def process_all_parallel(items: list[str]) -> list[dict]:
    """Fan-out all items, fan-in results."""
    client = anthropic.AsyncAnthropic()
    tasks = [process_single(client, item, i) for i, item in enumerate(items)]
    results = await asyncio.gather(*tasks)
    return list(results)


async def merge_results(results: list[dict]) -> str:
    """Synthesize all outputs into one final output."""
    client = anthropic.AsyncAnthropic()
    outputs_text = "\n\n".join(
        f"Item {r['id']}:\n{r['output']}"
        for r in sorted(results, key=lambda x: x["id"])
    )
    message = await client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": f"[YOUR MERGE PROMPT]\n\n{outputs_text}"
            }
        ]
    )
    return message.content[0].text


# Rate limiting: add a semaphore if hitting API limits
async def process_all_with_limit(items: list[str], max_concurrent: int = 5) -> list[dict]:
    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(max_concurrent)

    async def limited_call(item: str, item_id: int) -> dict:
        async with sem:
            return await process_single(client, item, item_id)

    tasks = [limited_call(item, i) for i, item in enumerate(items)]
    return list(await asyncio.gather(*tasks))
```

### Sync version (ThreadPoolExecutor)

Use when: your codebase is sync (Flask, scripts, Jupyter).

```python
import anthropic
from concurrent.futures import ThreadPoolExecutor

def process_single_sync(args: tuple) -> dict:
    client, item, item_id = args
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        messages=[{"role": "user", "content": f"[YOUR PROMPT HERE]\n\n{item}"}]
    )
    return {"id": item_id, "output": message.content[0].text}


def process_all_sync(items: list[str], max_workers: int = 10) -> list[dict]:
    client = anthropic.Anthropic()
    args = [(client, item, i) for i, item in enumerate(items)]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_single_sync, args))

    return results
```

---

## Sub-pattern B: Voting (N runs, 1 decision)

Use when: a single high-stakes decision needs confidence validation. Same prompt, N runs, majority wins.

```python
import asyncio
from collections import Counter
import anthropic


async def vote(text: str, n_votes: int = 3) -> str:
    """
    Run classification N times at temperature > 0.
    Returns majority label. Calls synthesize_tie() on a tie.

    Replace the classification prompt and labels for your task.
    """
    client = anthropic.AsyncAnthropic()

    async def single_vote(_: int) -> str:
        message = await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=64,
            temperature=0.7,
            messages=[{
                "role": "user",
                "content": (
                    "[YOUR CLASSIFICATION PROMPT]\n"
                    "Respond with only the label.\n\n"
                    f"Input: {text}"
                )
            }]
        )
        return message.content[0].text.strip().upper()

    votes = list(await asyncio.gather(*[single_vote(i) for i in range(n_votes)]))
    counts = Counter(votes)
    winner, count = counts.most_common(1)[0]

    if count > n_votes // 2:
        return winner
    else:
        return await synthesize_tie(text, votes)


async def synthesize_tie(text: str, votes: list[str]) -> str:
    """Model resolves a tie. Replace with human-in-loop for critical paths."""
    client = anthropic.AsyncAnthropic()
    message = await client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=64,
        messages=[{
            "role": "user",
            "content": (
                f"Multiple classifiers disagreed: {votes}. "
                f"Input: '{text}'. "
                "Give the single best label from the options shown."
            )
        }]
    )
    return message.content[0].text.strip().upper()
```

---

## Decision guide

```
Is the task: N independent inputs needing separate LLM calls?
    Yes --> Sub-pattern A: Sectioning
    No  --> Is it: 1 input where you want multiple perspectives?
                Yes --> Sub-pattern B: Voting
```

---

## Common pitfalls

- **Merger hallucination**: The synthesis step can introduce facts not in any individual output. Keep merger prompts tight and instruct the model to only use provided summaries.
- **Rate limit collisions**: If all N calls start at once and N > 20, you may hit API rate limits. Add a `Semaphore` (async) or reduce `max_workers` (threads).
- **Vote inflation**: If `temperature=0`, all votes will be identical and voting is meaningless. Temperature must be above 0 for voting to provide signal.
- **Tie cascades**: If synthesize_tie also produces ambiguous output, log the raw votes and treat as uncertain rather than forcing a label.
