"""
Lesson 04-06: Pattern: Orchestrator-Workers
Decompose complex goals into specialist workers with an LLM orchestrator.
"""

import json
from dataclasses import dataclass, field

import anthropic

# ---------------------------------------------------------------------------
# WORKER SYSTEM PROMPTS
# ---------------------------------------------------------------------------

WORKER_SYSTEMS = {
    "data_collector": """You are a market data collector. Your only job is to gather and
organize factual information relevant to the task. Present data as structured lists or
tables. Do not analyze or interpret. Do not editorialize.
Format: Use bullet points for data points. Include approximate figures when exact ones
are unavailable, and mark them as estimates.""",

    "analyst": """You are a strategic analyst. Your job is to interpret data and draw
defensible conclusions. Be specific: cite data points. Identify the top 2-3 strategic
implications. Do not write narrative prose. Use structured sections.
Format: ## Finding, then bullet points with supporting evidence.""",

    "writer": """You are a business writer for an executive audience. Write clearly,
concisely, and without jargon. Use only the information provided to you. Do not add
facts or statistics not in your input. 3 paragraphs maximum.
Format: Plain prose, no headers, no bullets.""",
}

# ---------------------------------------------------------------------------
# ORCHESTRATOR SYSTEM PROMPT
# ---------------------------------------------------------------------------

ORCHESTRATOR_SYSTEM = """You are a research orchestrator. Your job is to decompose a complex
research goal into a list of subtasks, each assigned to a specialist worker.

Available worker types:
- data_collector: gathers and organizes factual data and statistics
- analyst: interprets data and draws strategic conclusions
- writer: produces polished narrative content for an executive audience

Return a JSON object with this exact structure:
{
  "goal_summary": "one sentence restatement of the goal",
  "subtasks": [
    {
      "id": "t1",
      "worker_type": "data_collector",
      "task": "Collect key market size, growth rate, and competitor count data for [domain]",
      "depends_on": []
    },
    {
      "id": "t2",
      "worker_type": "analyst",
      "task": "Analyze the market data to identify strategic opportunities and risks",
      "depends_on": ["t1"]
    },
    {
      "id": "t3",
      "worker_type": "writer",
      "task": "Write a 3-paragraph executive summary of the market position",
      "depends_on": ["t1", "t2"]
    }
  ]
}

Return only valid JSON. No markdown formatting, no code blocks."""


# ---------------------------------------------------------------------------
# RAW IMPLEMENTATION
# ---------------------------------------------------------------------------

def orchestrate_plan(goal: str) -> dict:
    """Call the orchestrator to produce a work plan."""
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system=ORCHESTRATOR_SYSTEM,
        messages=[{"role": "user", "content": f"Goal: {goal}"}]
    )
    return json.loads(message.content[0].text)


def run_worker(worker_type: str, task: str, context: str = "") -> str:
    """Run a single worker with its specialized system prompt."""
    client = anthropic.Anthropic()

    user_content = f"Task: {task}"
    if context:
        user_content += f"\n\nContext from previous work:\n{context}"

    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system=WORKER_SYSTEMS[worker_type],
        messages=[{"role": "user", "content": user_content}]
    )
    return message.content[0].text


def execute_plan(goal: str, plan: dict) -> dict:
    """Execute subtasks in dependency order."""
    completed: dict[str, str] = {}

    for subtask in plan["subtasks"]:
        context_parts = [
            f"[{dep}]:\n{completed[dep]}"
            for dep in subtask.get("depends_on", [])
            if dep in completed
        ]
        context = "\n\n".join(context_parts)

        print(f"  Running {subtask['worker_type']} ({subtask['id']})...")
        output = run_worker(
            worker_type=subtask["worker_type"],
            task=subtask["task"],
            context=context
        )
        completed[subtask["id"]] = output
        print(f"  Done: {output[:80].replace(chr(10), ' ')}...")

    return completed


def synthesize_report(goal: str, completed: dict, plan: dict) -> str:
    """Final orchestrator call: synthesize all worker outputs."""
    client = anthropic.Anthropic()

    all_outputs = "\n\n".join(
        f"=== {task['id']} ({task['worker_type']}) ===\n{completed[task['id']]}"
        for task in plan["subtasks"]
        if task["id"] in completed
    )

    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Original goal: {goal}\n\n"
                    f"Worker outputs:\n{all_outputs}\n\n"
                    "Synthesize these outputs into a cohesive final report. "
                    "Integrate the data, analysis, and writing. "
                    "Resolve any contradictions. Keep it under 400 words."
                )
            }
        ]
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# REFACTORED: Worker dataclass + Orchestrator class
# ---------------------------------------------------------------------------

@dataclass
class WorkerResult:
    task_id: str
    worker_type: str
    output: str
    valid: bool
    error: str = ""


class Orchestrator:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self.worker_systems = WORKER_SYSTEMS

    def plan(self, goal: str) -> dict:
        """Generate a work plan for the given goal."""
        message = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=ORCHESTRATOR_SYSTEM,
            messages=[{"role": "user", "content": f"Goal: {goal}"}]
        )
        return json.loads(message.content[0].text)

    def dispatch_worker(self, worker_type: str, task: str, context: str = "") -> WorkerResult:
        """Dispatch one worker and validate its output."""
        if worker_type not in self.worker_systems:
            return WorkerResult(
                task_id="",
                worker_type=worker_type,
                output="",
                valid=False,
                error=f"Unknown worker type: {worker_type}"
            )

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

        # Validation: non-empty, minimum substantive length
        valid = len(output.strip()) > 50
        error = "" if valid else "Output too short - likely a failed response"

        return WorkerResult(
            task_id="",
            worker_type=worker_type,
            output=output,
            valid=valid,
            error=error
        )

    def execute(self, goal: str, plan: dict) -> dict[str, WorkerResult]:
        """Execute the plan, collecting WorkerResult per task."""
        results: dict[str, WorkerResult] = {}

        for subtask in plan["subtasks"]:
            context_parts = [
                f"[{dep}]:\n{results[dep].output}"
                for dep in subtask.get("depends_on", [])
                if dep in results and results[dep].valid
            ]
            context = "\n\n".join(context_parts)

            print(f"  Dispatching {subtask['worker_type']} ({subtask['id']})...")
            result = self.dispatch_worker(
                worker_type=subtask["worker_type"],
                task=subtask["task"],
                context=context
            )
            result.task_id = subtask["id"]
            results[subtask["id"]] = result

            if not result.valid:
                print(f"  WARNING: {subtask['id']} produced invalid output: {result.error}")
            else:
                print(f"  OK: {result.output[:80].replace(chr(10), ' ')}...")

        return results

    def synthesize(self, goal: str, results: dict[str, WorkerResult], plan: dict) -> str:
        """Synthesize valid worker outputs, noting any gaps."""
        valid_outputs = []
        failed_tasks = []

        for task in plan["subtasks"]:
            tid = task["id"]
            if tid in results and results[tid].valid:
                valid_outputs.append(
                    f"=== {tid} ({task['worker_type']}) ===\n{results[tid].output}"
                )
            else:
                failed_tasks.append(f"{tid} ({task['worker_type']})")

        all_outputs = "\n\n".join(valid_outputs)

        gap_note = ""
        if failed_tasks:
            gap_note = (
                f"\nNote: The following subtasks failed: {', '.join(failed_tasks)}. "
                "Acknowledge these gaps in the report."
            )

        message = self.client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    f"Original goal: {goal}\n\n"
                    f"Worker outputs:\n{all_outputs}"
                    f"{gap_note}\n\n"
                    "Synthesize into a cohesive final report under 400 words."
                )
            }]
        )
        return message.content[0].text

    def run(self, goal: str) -> str:
        """Full pipeline: plan, execute, synthesize."""
        print(f"\nGoal: {goal}")
        print("Step 1: Planning...")
        plan = self.plan(goal)
        print(f"  Plan: {[t['id'] + ':' + t['worker_type'] for t in plan['subtasks']]}")

        print("Step 2: Executing workers...")
        results = self.execute(goal, plan)

        print("Step 3: Synthesizing...")
        return self.synthesize(goal, results, plan)


# ---------------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    goal = (
        "Produce a market research brief on the B2B SaaS project management tools market. "
        "Include market size and growth data, analysis of competitive dynamics, "
        "and a written executive summary suitable for a board presentation."
    )

    print("=" * 60)
    print("DEMO 1: Raw orchestrator-workers pipeline")
    print("=" * 60)

    plan = orchestrate_plan(goal)
    print(f"Plan generated: {len(plan['subtasks'])} subtasks")
    completed = execute_plan(goal, plan)
    report = synthesize_report(goal, completed, plan)
    print("\n--- Final Report (raw pipeline) ---")
    print(report)

    print("\n" + "=" * 60)
    print("DEMO 2: Orchestrator class with validation")
    print("=" * 60)

    orch = Orchestrator()
    report2 = orch.run(goal)
    print("\n--- Final Report (class version) ---")
    print(report2)
