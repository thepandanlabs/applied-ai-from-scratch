---
name: runbook-coding-agent-deploy
description: Deployment and safety runbook for the coding automation agent capstone
version: "1.0"
phase: "12"
lesson: "04"
tags: [agents, coding-agent, hitl, audit-log, orchestrator-workers, safety]
---

# Runbook: Coding Automation Agent

## Environment Setup

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
export AGENT_CWD=/path/to/repo          # repo root; default: 4 levels above main.py
export AUDIT_LOG=agent_audit.jsonl      # audit log output path
```

## Running the Agent

### Interactive mode

```bash
python main.py
# Coding Agent - repo root: /path/to/repo
# Task: Find all lessons in Phase 04 missing a checks.json
# [PLAN] 3 steps ...
# [TOOL] list_files({'pattern': 'phases/04-agents/**/checks.json'})
# ...
```

### Single task

```bash
python main.py --task "Find all lessons in Phase 03 missing a Real-world check section"
```

### Demo mode (5 read-only evaluation tasks)

```bash
python main.py --demo
```

### Docker (repo mounted read-only)

```bash
docker build -t coding-agent ./code

docker run -it \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v /path/to/repo:/repo:ro \
  -v $(pwd)/data:/data \
  coding-agent python main.py --task "List all Python files in Phase 12"
```

## Allowed Directories Configuration

The agent operates within `AGENT_CWD`. The `_safe_abs_path()` function rejects any path that resolves outside this directory. To change the allowed root:

```bash
AGENT_CWD=/path/to/specific/phase python main.py
```

For production deployments that should be restricted to a subdirectory:
```bash
AGENT_CWD=/path/to/repo/phases/04-agents python main.py
```

## Command Allowlist for run_command

The current allowlist permits only read/test operations:

```python
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
```

To add a command (e.g. for a specific test script):
```python
re.compile(r"^python scripts/validate_checks\.py"),
```

Never add patterns that match `rm`, `git push`, `pip install`, or network commands.

## Approval Gate Configuration

The approval gate in `propose_change` is non-configurable by design: every file write requires human approval. For automated test pipelines where you want to auto-deny all writes:

```python
# In propose_change(), replace the input() call with:
if os.environ.get("AGENT_AUTO_DENY_WRITES", "false") == "true":
    decision = "no"
else:
    decision = input("Apply this change? (yes/no/view): ").strip().lower()
```

```bash
AGENT_AUTO_DENY_WRITES=true python main.py --demo
```

## Audit Log Format

Each line is a JSON object. Key event types:

```json
{"ts": "2025-05-26T10:00:00Z", "event": "task_start", "task": "Find missing checks.json..."}
{"ts": "2025-05-26T10:00:01Z", "tool": "list_files", "pattern": "phases/04-agents/**/checks.json", "count": 9}
{"ts": "2025-05-26T10:00:02Z", "tool": "read_file", "path": "phases/04-agents/01-the-agent-loop/docs/en.md", "chars": 12400, "truncated": true}
{"ts": "2025-05-26T10:00:10Z", "tool": "propose_change", "path": "phases/04-agents/02-workflows-vs-agents/checks.json", "is_new_file": true, "diff_line_count": 87}
{"ts": "2025-05-26T10:00:15Z", "tool": "write_file", "path": "phases/04-agents/02-workflows-vs-agents/checks.json", "approved": true}
{"ts": "2025-05-26T10:00:16Z", "event": "task_complete", "task": "...", "steps_executed": 4}
```

### Audit log queries

```bash
# Files read in last run
jq -r 'select(.tool == "read_file") | .path' agent_audit.jsonl

# All proposed changes
jq -r 'select(.tool == "propose_change") | [.path, .is_new_file] | @csv' agent_audit.jsonl

# Approved writes
jq -r 'select(.tool == "write_file" and .approved == true) | .path' agent_audit.jsonl

# File selection precision (reads vs approved writes)
READS=$(jq 'select(.tool == "read_file")' agent_audit.jsonl | wc -l)
WRITES=$(jq 'select(.tool == "write_file" and .approved == true)' agent_audit.jsonl | wc -l)
echo "Precision: $WRITES reads were writes out of $READS total"
```

## Rollback Procedure

All writes produce a git-trackable diff. Before running any write-capable task:

```bash
# Checkpoint the repo state
git stash push -m "before-agent-run-$(date +%Y%m%d-%H%M%S)"

# After the agent run, review changes
git diff

# Rollback if needed
git stash pop
```

For finer-grained rollback, check the audit log for which files were written and restore them individually:

```bash
git checkout HEAD -- phases/04-agents/02-workflows-vs-agents/checks.json
```

## Capability Boundary Documentation

### What this agent CAN do

- Read any file under `AGENT_CWD`
- List and glob files under `AGENT_CWD`
- Search for patterns in files under `AGENT_CWD`
- Propose file creation or modification (requires human approval)
- Run commands on the allowlist (tests and search operations)

### What this agent CANNOT do

- Write any file without explicit human approval
- Execute arbitrary shell commands (only allowlisted commands)
- Access paths outside `AGENT_CWD`
- Make network requests (no network tools)
- Modify git history
- Delete files (no delete tool)
- Access environment variables or secrets

### Extending capabilities safely

To add a new tool: define the tool schema, implement the tool function with appropriate validation, add it to `TOOL_REGISTRY`, and document its permission tier. Any tool that modifies state (writes files, runs commands) should follow the approval-gate pattern.
