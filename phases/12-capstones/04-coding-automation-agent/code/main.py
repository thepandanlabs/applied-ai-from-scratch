"""
Capstone 12-04: Coding Automation Agent on a Real Repo
Phase 12: Capstones

An orchestrator-workers coding agent that operates on the curriculum repo.
Tools: read_file, list_files, search_files, propose_change (with diff + approval), run_command.
Every tool call is logged to agent_audit.jsonl.
No file is written without explicit human approval.

Usage:
    uv pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...

    # Interactive: agent asks what task to perform
    python main.py

    # Run a specific task
    python main.py --task "Find all lessons in Phase 04 missing a checks.json"

    # Demo mode: runs all 5 evaluation tasks
    python main.py --demo
"""

import difflib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL = "claude-3-5-haiku-20241022"
AUDIT_LOG = os.environ.get("AUDIT_LOG", "agent_audit.jsonl")

# Repo root: 4 levels above this file (phases/12-capstones/04-coding-automation-agent/code/)
CWD = os.environ.get(
    "AGENT_CWD",
    str(Path(__file__).resolve().parents[4])
)

# Maximum characters returned per file read (prevents context overflow)
MAX_FILE_CHARS = 8000

# Allowed commands: only test/search operations, no builds or deploys
ALLOWED_COMMAND_PATTERNS = [
    re.compile(r"^python -m pytest"),
    re.compile(r"^python -m flake8"),
    re.compile(r"^grep "),
    re.compile(r"^find \. "),
    re.compile(r"^python main\.py --test"),
    re.compile(r"^ls "),
    re.compile(r"^cat "),
    re.compile(r"^wc "),
]

# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def write_audit(event: dict) -> None:
    entry = {"ts": datetime.utcnow().isoformat() + "Z", **event}
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _safe_abs_path(relative_path: str) -> str | None:
    """Resolve path under CWD. Return None if outside CWD (path traversal)."""
    abs_path = os.path.normpath(os.path.join(CWD, relative_path))
    if not abs_path.startswith(os.path.normpath(CWD)):
        return None
    return abs_path


def read_file(path: str) -> str:
    abs_path = _safe_abs_path(path)
    if abs_path is None:
        write_audit({"tool": "read_file", "path": path, "error": "path_traversal_blocked"})
        return "Error: path traversal outside allowed root is not permitted."

    try:
        content = Path(abs_path).read_text(encoding="utf-8", errors="ignore")
        truncated = len(content) > MAX_FILE_CHARS
        result = content[:MAX_FILE_CHARS]
        write_audit({
            "tool": "read_file",
            "path": path,
            "chars": len(content),
            "truncated": truncated,
        })
        if truncated:
            result += f"\n\n[TRUNCATED: file is {len(content)} chars, showing first {MAX_FILE_CHARS}]"
        return result
    except FileNotFoundError:
        write_audit({"tool": "read_file", "path": path, "error": "not_found"})
        return f"File not found: {path}"
    except Exception as e:
        write_audit({"tool": "read_file", "path": path, "error": str(e)})
        return f"Error reading {path}: {e}"


def list_files(pattern: str = "**/*.md") -> str:
    try:
        matches = sorted(
            str(p.relative_to(CWD))
            for p in Path(CWD).glob(pattern)
            if p.is_file()
        )
        write_audit({"tool": "list_files", "pattern": pattern, "count": len(matches)})
        if not matches:
            return f"(no files match pattern: {pattern})"
        if len(matches) > 100:
            return "\n".join(matches[:100]) + f"\n[... {len(matches) - 100} more files not shown]"
        return "\n".join(matches)
    except Exception as e:
        write_audit({"tool": "list_files", "pattern": pattern, "error": str(e)})
        return f"Error listing files: {e}"


def search_files(pattern: str, file_glob: str = "**/*.md") -> str:
    results: list[str] = []
    error_count = 0
    try:
        for p in sorted(Path(CWD).glob(file_glob)):
            if not p.is_file():
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        rel = str(p.relative_to(CWD))
                        results.append(f"{rel}:{i}: {line.strip()}")
            except Exception:
                error_count += 1
                continue

        write_audit({
            "tool": "search_files",
            "pattern": pattern,
            "file_glob": file_glob,
            "matches": len(results),
        })
        if not results:
            return f"(no matches for pattern '{pattern}' in {file_glob})"
        if len(results) > 50:
            return "\n".join(results[:50]) + f"\n[... {len(results) - 50} more matches]"
        return "\n".join(results)
    except Exception as e:
        return f"Search error: {e}"


def propose_change(path: str, new_content: str, reason: str) -> str:
    abs_path = _safe_abs_path(path)
    if abs_path is None:
        write_audit({"tool": "propose_change", "path": path, "error": "path_traversal_blocked"})
        return "Error: path traversal outside allowed root."

    # Build diff
    try:
        existing = Path(abs_path).read_text(encoding="utf-8") if Path(abs_path).exists() else ""
    except Exception:
        existing = ""

    is_new = not Path(abs_path).exists()
    diff_lines = list(difflib.unified_diff(
        existing.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    ))
    diff_text = "".join(diff_lines) or "(new file, no diff)"

    print(f"\n{'='*60}")
    print(f"[PROPOSE CHANGE] {path}")
    print(f"Reason: {reason}")
    print(f"{'- new file -' if is_new else 'Diff preview:'}")
    print(diff_text[:3000])
    if len(diff_text) > 3000:
        print(f"[... diff truncated, {len(diff_lines)} total lines]")
    print("=" * 60)

    write_audit({
        "tool": "propose_change",
        "path": path,
        "reason": reason,
        "is_new_file": is_new,
        "diff_line_count": len(diff_lines),
    })

    try:
        decision = input("Apply this change? (yes/no/view): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        decision = "no"

    if decision == "view":
        print("\n--- Full new content ---")
        print(new_content)
        print("--- End of content ---")
        try:
            decision = input("Apply this change? (yes/no): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            decision = "no"

    if decision in ("yes", "y"):
        Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
        Path(abs_path).write_text(new_content, encoding="utf-8")
        write_audit({"tool": "write_file", "path": path, "approved": True})
        return f"File written: {path}"

    write_audit({"tool": "write_file", "path": path, "approved": False})
    return f"Change proposal denied for: {path}"


def run_command(command: str) -> str:
    # Check against allowlist
    allowed = any(p.match(command) for p in ALLOWED_COMMAND_PATTERNS)
    if not allowed:
        write_audit({"tool": "run_command", "command": command, "error": "not_in_allowlist"})
        return (
            f"Command not in allowlist: '{command}'. "
            "Allowed: pytest, flake8, grep, find, ls, cat, wc, python main.py --test"
        )

    write_audit({"tool": "run_command", "command": command})
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=CWD,
        )
        output = result.stdout + result.stderr
        if len(output) > 3000:
            output = output[:3000] + "\n[... output truncated]"
        return f"Exit code: {result.returncode}\n{output}"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 30s"
    except Exception as e:
        return f"Error running command: {e}"


# ---------------------------------------------------------------------------
# Tool definitions (JSON Schema)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "read_file",
        "description": (
            "Read a file's content. Path is relative to repo root. "
            f"Maximum {MAX_FILE_CHARS} characters returned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root, e.g. phases/04-agents/01-the-agent-loop/docs/en.md"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files matching a glob pattern relative to repo root. Returns up to 100 file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern, e.g. 'phases/04-agents/**/checks.json' or 'phases/**/*.py'"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "search_files",
        "description": "Search for a regex pattern in files matching a glob. Returns matching lines with file:line format.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern":   {"type": "string", "description": "Regex pattern to search for, e.g. 'Real-world check' or 'import anthropic'"},
                "file_glob": {"type": "string", "description": "Glob to filter files. Examples: '**/*.md', '**/*.py'. Default: **/*.md"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "propose_change",
        "description": (
            "Propose writing or modifying a file. "
            "Shows a diff preview and requires explicit human approval before writing. "
            "Use this for any file creation or modification."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":        {"type": "string", "description": "Relative file path to write"},
                "new_content": {"type": "string", "description": "Complete new file content"},
                "reason":      {"type": "string", "description": "Why this change is needed"},
            },
            "required": ["path", "new_content", "reason"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Run an allowed command. Only test/search commands are permitted: "
            "python -m pytest, python -m flake8, grep, find, ls, cat, wc, python main.py --test"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
            },
            "required": ["command"],
        },
    },
]

TOOL_REGISTRY: dict[str, Any] = {
    "read_file":      lambda args: read_file(args["path"]),
    "list_files":     lambda args: list_files(args.get("pattern", "**/*.md")),
    "search_files":   lambda args: search_files(args["pattern"], args.get("file_glob", "**/*.md")),
    "propose_change": lambda args: propose_change(args["path"], args["new_content"], args["reason"]),
    "run_command":    lambda args: run_command(args["command"]),
}

# ---------------------------------------------------------------------------
# Orchestrator: task decomposition
# ---------------------------------------------------------------------------

ORCHESTRATOR_SYSTEM = """You are a coding task planner for a software repository.

Given a task description, produce a step-by-step plan for a coding agent to execute.
Be specific: name which files or patterns to read/search and what the final output should be.
Consider: what context does the agent need to read first? What format must outputs follow?

Respond with JSON only:
{"steps": ["step 1: ...", "step 2: ...", ...], "expected_output": "description of what done looks like"}

Do not execute any steps. Only plan."""

WORKER_SYSTEM = """You are a coding agent operating on a software repository.
You have tools to read, search, and propose changes to files.

RULES:
1. Read files before proposing changes to them.
2. Read a reference example before generating new content that must match a format.
3. Before using propose_change, confirm you have read the target file (or confirm it is new).
4. Keep reads targeted: read what you need for the current step, not everything.
5. If you are uncertain about the task, report what you found rather than guessing.

Complete the assigned step, then report what you did and what you found."""


def plan_task(task: str) -> dict:
    """Orchestrator pass: decompose task into steps."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=ORCHESTRATOR_SYSTEM,
        messages=[{"role": "user", "content": f"Task: {task}"}],
    )
    raw = next((b.text for b in response.content if hasattr(b, "text")), "{}")
    raw_clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    try:
        return json.loads(raw_clean)
    except Exception:
        return {"steps": [task], "expected_output": "task completion"}


# ---------------------------------------------------------------------------
# Worker: execute tool loop
# ---------------------------------------------------------------------------

def execute_tool(name: str, args: dict) -> str:
    if name in TOOL_REGISTRY:
        try:
            return TOOL_REGISTRY[name](args)
        except Exception as e:
            return f"Tool error: {e}"
    return f"Unknown tool: {name}"


def run_worker_step(step: str, context: str, history: list, client: anthropic.Anthropic) -> str:
    """Run the worker agent for one step. Returns the step result as text."""
    user_msg = f"Context from previous steps:\n{context}\n\nCurrent step: {step}"
    history.append({"role": "user", "content": user_msg})

    for _ in range(10):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=WORKER_SYSTEM,
            tools=TOOLS,
            messages=history,
        )
        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "(no output)")
            history.append({"role": "assistant", "content": response.content})
            return text

        if response.stop_reason == "tool_use":
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            history.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in tool_blocks:
                print(f"\n  [TOOL] {block.name}({json.dumps(block.input)[:80]})")
                result = execute_tool(block.name, block.input)
                print(f"  [RESULT] {result[:100]}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            history.append({"role": "user", "content": tool_results})
            continue

        return f"Unexpected stop: {response.stop_reason}"

    return "Worker reached iteration limit."


# ---------------------------------------------------------------------------
# Main agent runner
# ---------------------------------------------------------------------------

def run_agent(task: str) -> dict:
    """Run the full orchestrator-workers agent for a task. Returns summary dict."""
    client = anthropic.Anthropic()
    write_audit({"event": "task_start", "task": task})

    print(f"\n{'='*60}")
    print(f"TASK: {task}")
    print("=" * 60)

    # Orchestrator pass
    plan = plan_task(task)
    steps = plan.get("steps", [task])
    expected = plan.get("expected_output", "")

    print(f"\nPLAN ({len(steps)} steps):")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step}")
    print(f"Expected: {expected}\n")

    write_audit({"event": "plan", "steps": steps, "expected": expected})

    # Worker passes
    history: list = []
    context = f"Task: {task}\nExpected output: {expected}"
    step_results = []

    for i, step in enumerate(steps, 1):
        print(f"\n--- Step {i}/{len(steps)}: {step} ---")
        result = run_worker_step(step, context, history, client)
        step_results.append({"step": step, "result": result})
        context += f"\nStep {i} result: {result[:500]}"
        print(f"Step {i} complete: {result[:200]}")

    write_audit({"event": "task_complete", "task": task, "steps_executed": len(steps)})

    return {
        "task": task,
        "plan": steps,
        "step_results": step_results,
        "summary": step_results[-1]["result"] if step_results else "(no steps executed)",
    }


# ---------------------------------------------------------------------------
# Demo tasks for evaluation
# ---------------------------------------------------------------------------

DEMO_TASKS = [
    "Find all lessons in phases/04-agents that do not have a checks.json file.",
    "Find all .md files in phases/04-agents that contain the phrase 'Real-world check'.",
    "List all Python files in phases/12-capstones and report which ones import 'anthropic'.",
    "Count the total number of lesson folders across all phases (folders matching phases/NN-*/NN-*/).",
    "Read phases/12-capstones/01-production-rag-assistant/checks.json and summarize what topics are covered.",
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Coding Agent - repo root: {CWD}")
    print(f"Audit log: {AUDIT_LOG}")

    if "--demo" in sys.argv:
        print(f"\nRunning {len(DEMO_TASKS)} demo tasks (read-only, no writes)...\n")
        for task in DEMO_TASKS:
            result = run_agent(task)
            print(f"\nSUMMARY: {result['summary'][:300]}\n")
    elif "--task" in sys.argv:
        idx = sys.argv.index("--task")
        if idx + 1 < len(sys.argv):
            task = sys.argv[idx + 1]
            result = run_agent(task)
            print(f"\nFINAL: {result['summary']}")
        else:
            print("Error: --task requires a task description argument")
            sys.exit(1)
    else:
        print("\nInteractive mode. Type your task (or 'quit' to exit).")
        while True:
            try:
                task = input("\nTask: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break
            if task.lower() in ("quit", "exit", "q"):
                break
            if task:
                result = run_agent(task)
                print(f"\nResult: {result['summary']}")
