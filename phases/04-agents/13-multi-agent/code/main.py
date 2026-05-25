"""
L13: Multi-Agent Supervisor Pattern
Demonstrates supervisor-workers and handoff patterns for a blog post pipeline.
"""

import json
from dataclasses import dataclass, field
import anthropic

client = anthropic.Anthropic()
MODEL = "claude-3-5-haiku-20241022"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SUPERVISOR_PROMPT = """You are a production supervisor for a blog post pipeline.
You receive a goal and the current pipeline state as JSON.
Decide which specialist to dispatch next.

Specialists available: researcher, writer, reviewer

Rules:
- Call researcher first (always).
- Call writer after researcher has produced output.
- Call reviewer after writer has produced a draft.
- After reviewer has run, set done to true.

Always respond with valid JSON only (no prose, no markdown fences):
{"specialist": "researcher" | "writer" | "reviewer", "task": "<specific task>", "done": false}

When pipeline is complete:
{"specialist": null, "task": null, "done": true}"""

SPECIALIST_PROMPTS = {
    "researcher": (
        "You are a research specialist. Given a topic and task, produce 3-5 factual "
        "bullet points with supporting context. Be concise and accurate. No prose intro."
    ),
    "writer": (
        "You are a writing specialist. Given research notes and a task, write a focused "
        "blog section (150-200 words). Use the research. Do not invent facts."
    ),
    "reviewer": (
        "You are a review specialist. Given a draft and research notes, output a brief "
        "assessment: what is strong, what needs fixing (if anything). Be specific and brief."
    ),
}


# ---------------------------------------------------------------------------
# Part 1: Supervisor-Workers Pattern
# ---------------------------------------------------------------------------

def call_specialist(specialist_name: str, task: str, context: dict) -> str:
    """Call a specialist agent with the given task and accumulated context."""
    system = SPECIALIST_PROMPTS[specialist_name]
    user_content = f"Task: {task}\n\nContext from prior steps:\n{json.dumps(context, indent=2)}"
    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text


def parse_supervisor_json(raw: str) -> dict:
    """Parse supervisor JSON, stripping markdown fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def run_supervisor(goal: str, max_steps: int = 6) -> dict:
    """
    Run the supervisor-workers pipeline.

    The supervisor receives full pipeline state on every call and returns
    a JSON routing decision. Each specialist receives all prior outputs.
    """
    pipeline_state = {
        "goal": goal,
        "completed_steps": [],
        "outputs": {},
    }

    for step in range(max_steps):
        supervisor_input = json.dumps(pipeline_state, indent=2)
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=SUPERVISOR_PROMPT,
            messages=[{"role": "user", "content": supervisor_input}],
        )

        raw = response.content[0].text
        try:
            decision = parse_supervisor_json(raw)
        except json.JSONDecodeError as e:
            print(f"[supervisor] JSON parse error at step {step}: {e}")
            print(f"[supervisor] Raw output: {raw[:200]}")
            break

        if decision.get("done"):
            print(f"[supervisor] Pipeline complete after {step} steps.")
            break

        specialist = decision["specialist"]
        task = decision["task"]
        print(f"Step {step + 1}: -> [{specialist}] {task[:70]}...")

        output = call_specialist(specialist, task, pipeline_state["outputs"])

        # Accumulate outputs so later specialists see all prior work
        pipeline_state["outputs"][specialist] = output
        pipeline_state["completed_steps"].append({
            "specialist": specialist,
            "task": task,
        })

    return pipeline_state


# ---------------------------------------------------------------------------
# Part 2: Handoff Pattern
# ---------------------------------------------------------------------------

@dataclass
class HandoffBundle:
    """Context bundle passed between agents in a handoff pipeline."""
    goal: str
    stage: str = "start"
    outputs: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def researcher_agent(bundle: HandoffBundle) -> HandoffBundle:
    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=SPECIALIST_PROMPTS["researcher"],
        messages=[{
            "role": "user",
            "content": f"Goal: {bundle.goal}\nTask: Research this topic thoroughly.",
        }],
    )
    bundle.outputs["research"] = response.content[0].text
    bundle.stage = "researched"
    bundle.notes.append("Researcher: complete")
    return bundle


def writer_agent(bundle: HandoffBundle) -> HandoffBundle:
    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=SPECIALIST_PROMPTS["writer"],
        messages=[{
            "role": "user",
            "content": (
                f"Goal: {bundle.goal}\n"
                f"Research notes:\n{bundle.outputs.get('research', '')}\n"
                "Task: Write the blog section based on the research above."
            ),
        }],
    )
    bundle.outputs["draft"] = response.content[0].text
    bundle.stage = "drafted"
    bundle.notes.append("Writer: complete")
    return bundle


def reviewer_agent(bundle: HandoffBundle) -> HandoffBundle:
    response = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SPECIALIST_PROMPTS["reviewer"],
        messages=[{
            "role": "user",
            "content": (
                f"Research notes:\n{bundle.outputs.get('research', '')}\n\n"
                f"Draft:\n{bundle.outputs.get('draft', '')}\n\n"
                "Task: Review the draft against the research. Flag any issues."
            ),
        }],
    )
    bundle.outputs["review"] = response.content[0].text
    bundle.stage = "reviewed"
    bundle.notes.append("Reviewer: complete")
    return bundle


def run_handoff_pipeline(goal: str) -> HandoffBundle:
    """
    Run the handoff pipeline: researcher -> writer -> reviewer.
    Each agent receives the accumulated bundle from the previous stage.
    """
    bundle = HandoffBundle(goal=goal)
    bundle = researcher_agent(bundle)
    print(f"[handoff] Stage: {bundle.stage}")
    bundle = writer_agent(bundle)
    print(f"[handoff] Stage: {bundle.stage}")
    bundle = reviewer_agent(bundle)
    print(f"[handoff] Stage: {bundle.stage}")
    return bundle


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    GOAL = "Why do multi-agent AI systems often fail in production despite working well in demos"

    print("=" * 60)
    print("PATTERN 1: SUPERVISOR-WORKERS")
    print("=" * 60)
    result = run_supervisor(GOAL)
    print("\n--- Supervisor Pipeline Outputs ---")
    for specialist, output in result["outputs"].items():
        print(f"\n[{specialist.upper()}]:")
        print(output[:400] + ("..." if len(output) > 400 else ""))

    print("\n" + "=" * 60)
    print("PATTERN 2: HANDOFF CHAIN")
    print("=" * 60)
    bundle = run_handoff_pipeline(GOAL)
    print("\n--- Handoff Pipeline Outputs ---")
    for stage, output in bundle.outputs.items():
        print(f"\n[{stage.upper()}]:")
        print(output[:400] + ("..." if len(output) > 400 else ""))
    print(f"\nNotes: {bundle.notes}")
