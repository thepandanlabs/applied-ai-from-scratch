---
name: skill-multi-agent-supervisor
description: Supervisor prompt template and specialist dispatch pattern for multi-agent pipelines
version: "1.0"
phase: "04"
lesson: "13"
tags: [agents, multi-agent, supervisor, handoff, orchestration]
---

# Skill: Multi-Agent Supervisor

Use this skill when a task hits one of the three justified conditions for multi-agent architecture:
1. Task exceeds a single context window
2. Independent verification improves accuracy
3. Specialist parallelism genuinely speeds things up

If none of the three apply, use a single agent.

---

## Supervisor Prompt Template

```
You are a production supervisor for a [PIPELINE NAME] pipeline.
You receive a goal and the current pipeline state as JSON.
Decide which specialist to dispatch next.

Specialists available: [LIST YOUR SPECIALISTS]

Dispatch rules:
- [YOUR ORDERING RULES, e.g.: "Call researcher first. Call writer after researcher has output."]

Always respond with valid JSON only (no prose, no markdown fences):
{"specialist": "<name>", "task": "<specific task string>", "done": false}

When the pipeline is complete:
{"specialist": null, "task": null, "done": true}
```

**Customization points:**
- Replace `[PIPELINE NAME]` with your domain (e.g., "content production", "code review", "research")
- List exactly the specialists your pipeline uses
- Define explicit ordering rules so the supervisor does not have to infer them
- Keep the JSON schema strict: `specialist`, `task`, `done` only

---

## Specialist Dispatch Loop

```python
import json
import anthropic

client = anthropic.Anthropic()
MODEL = "claude-3-5-haiku-20241022"

def run_supervisor_pipeline(
    goal: str,
    supervisor_prompt: str,
    specialist_prompts: dict[str, str],
    max_steps: int = 8,
) -> dict:
    pipeline_state = {
        "goal": goal,
        "completed_steps": [],
        "outputs": {},
    }

    for step in range(max_steps):
        # Ask supervisor what to do next
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=supervisor_prompt,
            messages=[{"role": "user", "content": json.dumps(pipeline_state, indent=2)}],
        )

        raw = response.content[0].text.strip()
        # Strip markdown fences if the model adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        decision = json.loads(raw.strip())

        if decision.get("done"):
            break

        specialist = decision["specialist"]
        task = decision["task"]

        # Call the specialist with cumulative context
        specialist_response = client.messages.create(
            model=MODEL,
            max_tokens=800,
            system=specialist_prompts[specialist],
            messages=[{
                "role": "user",
                "content": f"Task: {task}\n\nContext:\n{json.dumps(pipeline_state['outputs'], indent=2)}",
            }],
        )

        # Accumulate: each specialist sees all prior outputs
        pipeline_state["outputs"][specialist] = specialist_response.content[0].text
        pipeline_state["completed_steps"].append({"specialist": specialist, "task": task})

    return pipeline_state
```

---

## Handoff Bundle Pattern

Use when specialists are sequential and each stage has a clear completion boundary.

```python
from dataclasses import dataclass, field

@dataclass
class HandoffBundle:
    goal: str
    stage: str = "start"
    outputs: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

# Each agent function signature:
def your_agent(bundle: HandoffBundle) -> HandoffBundle:
    # 1. Read what you need from bundle.outputs
    # 2. Do your work
    # 3. Write your output to bundle.outputs["your_key"]
    # 4. Update bundle.stage
    # 5. Append to bundle.notes
    # 6. Return the bundle
    return bundle
```

---

## When to Use Which Pattern

```
Condition                          Use
-----------------------------------------
Dynamic routing needed             Supervisor-Workers
Sequence is always the same        Handoffs
Tasks can run in parallel          Supervisor-Workers (dispatch simultaneously)
Each stage has a clear boundary    Handoffs
You want a simpler failure surface Handoffs
You want routing flexibility       Supervisor-Workers
```

---

## Context Passing Rules

1. Always pass the full accumulated outputs to each specialist, not just the immediately prior step.
2. Never pass raw message histories between agents. Serialize into a context bundle or a JSON state object.
3. The supervisor should receive pipeline state, not transcripts. State is smaller and more focused.
4. If a specialist needs to reference a specific prior output, use named keys (`outputs["researcher"]`), not positional references.

---

## Justification Checklist

Before building a multi-agent pipeline, confirm at least one is true:

- [ ] The task exceeds a single context window (~100K tokens for most tasks)
- [ ] Independent verification is required and a second LLM call will catch errors the first missed
- [ ] The task has separable parallel workstreams that would reduce wall-clock time meaningfully
- [ ] The single-agent version has been tested and found insufficient

If none are checked: use one agent.
