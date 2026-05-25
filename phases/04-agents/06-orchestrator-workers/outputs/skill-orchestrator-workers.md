---
name: skill-orchestrator-workers
description: LLM orchestrator that plans and dispatches specialist workers, then synthesizes their outputs into a final result
version: "1.0"
phase: "04"
lesson: "06"
tags: [orchestrator, workers, multi-agent, specialization, planning]
---

# Skill: Orchestrator-Workers

Use when: a task requires multiple distinct competencies that degrade when combined in a single prompt.

---

## Orchestrator system prompt template

```
You are a [domain] orchestrator. Your job is to decompose a complex
goal into a list of subtasks, each assigned to a specialist worker.

Available worker types:
- [worker_type_1]: [what it does, what format it outputs]
- [worker_type_2]: [what it does, what format it outputs]
- [worker_type_3]: [what it does, what format it outputs]

Return a JSON object with this exact structure:
{
  "goal_summary": "one sentence restatement of the goal",
  "subtasks": [
    {
      "id": "t1",
      "worker_type": "[worker_type_1]",
      "task": "[specific task description]",
      "depends_on": []
    },
    {
      "id": "t2",
      "worker_type": "[worker_type_2]",
      "task": "[specific task description]",
      "depends_on": ["t1"]
    }
  ]
}

Return only valid JSON. No markdown formatting, no code blocks.
```

---

## Worker dispatch pattern

```python
import json
from dataclasses import dataclass
import anthropic

# Define your worker system prompts here
WORKER_SYSTEMS: dict[str, str] = {
    "worker_type_1": "You are a [role]. Your job is [specific focus]. Format: [output format].",
    "worker_type_2": "You are a [role]. Your job is [specific focus]. Format: [output format].",
    "worker_type_3": "You are a [role]. Your job is [specific focus]. Format: [output format].",
}


@dataclass
class WorkerResult:
    task_id: str
    worker_type: str
    output: str
    valid: bool
    error: str = ""


class Orchestrator:
    def __init__(self, orchestrator_system: str, worker_systems: dict[str, str]):
        self.client = anthropic.Anthropic()
        self.orchestrator_system = orchestrator_system
        self.worker_systems = worker_systems

    def plan(self, goal: str) -> dict:
        message = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=self.orchestrator_system,
            messages=[{"role": "user", "content": f"Goal: {goal}"}]
        )
        return json.loads(message.content[0].text)

    def dispatch_worker(self, worker_type: str, task: str, context: str = "") -> WorkerResult:
        if worker_type not in self.worker_systems:
            return WorkerResult("", worker_type, "", False, f"Unknown worker type: {worker_type}")

        user_content = f"Task: {task}"
        if context:
            user_content += f"\n\nContext:\n{context}"

        message = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system=self.worker_systems[worker_type],
            messages=[{"role": "user", "content": user_content}]
        )
        output = message.content[0].text
        valid = len(output.strip()) > 50
        return WorkerResult("", worker_type, output, valid, "" if valid else "Output too short")

    def execute(self, goal: str, plan: dict) -> dict[str, WorkerResult]:
        results: dict[str, WorkerResult] = {}
        for subtask in plan["subtasks"]:
            context = "\n\n".join(
                f"[{dep}]:\n{results[dep].output}"
                for dep in subtask.get("depends_on", [])
                if dep in results and results[dep].valid
            )
            result = self.dispatch_worker(subtask["worker_type"], subtask["task"], context)
            result.task_id = subtask["id"]
            results[subtask["id"]] = result
        return results

    def synthesize(self, goal: str, results: dict[str, WorkerResult], plan: dict) -> str:
        valid_outputs = [
            f"=== {t['id']} ({t['worker_type']}) ===\n{results[t['id']].output}"
            for t in plan["subtasks"]
            if t["id"] in results and results[t["id"]].valid
        ]
        failed = [
            f"{t['id']} ({t['worker_type']})"
            for t in plan["subtasks"]
            if t["id"] not in results or not results[t["id"]].valid
        ]
        gap_note = f"\nFailed subtasks: {', '.join(failed)}. Acknowledge gaps." if failed else ""

        message = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    f"Original goal: {goal}\n\n"
                    f"Worker outputs:\n" + "\n\n".join(valid_outputs) +
                    f"{gap_note}\n\n"
                    "Synthesize into a cohesive final output. "
                    "Use only the provided worker outputs. Do not add new facts."
                )
            }]
        )
        return message.content[0].text

    def run(self, goal: str) -> str:
        plan = self.plan(goal)
        results = self.execute(goal, plan)
        return self.synthesize(goal, results, plan)
```

---

## Adding a new worker type

1. Add a new key to `WORKER_SYSTEMS` with a focused system prompt.
2. Add the new worker type to the orchestrator system prompt's "Available worker types" section.
3. The orchestrator will automatically dispatch to it when appropriate.

---

## Worker system prompt checklist

Good worker prompts have:
- A clear role statement ("You are a...")
- A specific scope ("Your only job is...")
- An explicit output format ("Format: bullet points / structured sections / plain prose")
- A prohibition on out-of-scope work ("Do not analyze / Do not add new facts")

---

## Sequential vs. parallel execution

```python
# Sequential: tasks with depends_on run after their dependencies complete (default above)

# Parallel: tasks with empty depends_on can run concurrently
import asyncio

async def execute_parallel(self, goal: str, plan: dict) -> dict[str, WorkerResult]:
    results = {}
    # Group tasks by dependency level
    ready = [t for t in plan["subtasks"] if not t.get("depends_on")]
    # Run ready tasks concurrently; add dependent tasks as deps complete
    # (implement with asyncio.gather for groups at each level)
    ...
```

---

## Common pitfalls

- **Synthesis hallucination**: The synthesis call adds new information not in any worker output. Fix: add "Use only the provided worker outputs" to the synthesis prompt.
- **Plan parsing failure**: The orchestrator wraps JSON in markdown code blocks. Fix: add "Return only valid JSON. No markdown formatting, no code blocks" to the system prompt.
- **Worker type mismatch**: The orchestrator invents a worker type not in your registry. Fix: enumerate allowed worker types explicitly in the orchestrator system prompt.
- **Skipping failed workers**: If a worker fails and its output is dependency for another worker, the downstream worker receives incomplete context. Always check `valid` before passing to dependents.
