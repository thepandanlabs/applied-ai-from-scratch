"""
Lesson 07: Git and Running the Lesson Repo
Phase 00: Setup and Mindset

Demonstrates the git workflow for AI projects:
  - Initializing a repo with the correct .gitignore
  - Committing a first Python script
  - Reviewing prompt changes with git diff before committing
  - Tagging working versions for rollback

Creates a demo repo at /tmp/ai_project_demo.
No API key required to run the git workflow parts.
"""

import os
import subprocess
import textwrap


# ---------------------------------------------------------------------------
# Shell helper
# ---------------------------------------------------------------------------

def run(cmd: str, check: bool = True, cwd: str | None = None) -> subprocess.CompletedProcess:
    """
    Run a shell command, print it, and return the result.

    Args:
        cmd: Shell command to run.
        check: If True, raise on non-zero exit code.
        cwd: Working directory for the command.
    """
    print(f"  $ {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.stdout:
        print(textwrap.indent(result.stdout.rstrip(), "    "))
    if result.stderr and result.returncode != 0:
        print(textwrap.indent(f"stderr: {result.stderr.rstrip()}", "    "))
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {cmd}")
    return result


# ---------------------------------------------------------------------------
# .gitignore template for AI projects
# ---------------------------------------------------------------------------

GITIGNORE_CONTENT = """\
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
*.egg-info/
dist/
build/

# Virtual environments (uv, venv, conda)
.venv/
venv/
env/
.env/

# Secrets - NEVER commit these
.env
*.env
secrets.json
credentials.json
config.local.py
*_key.txt

# API response outputs that may contain PII
outputs/raw_responses/
outputs/eval_runs/
*.jsonl.gz

# Large files (model weights, binary data)
model_weights/
*.bin
*.pt
*.onnx
*.safetensors

# OS generated files
.DS_Store
.DS_Store?
Thumbs.db
ehthumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo

# Logs
*.log
logs/
"""


# ---------------------------------------------------------------------------
# First script template
# ---------------------------------------------------------------------------

FIRST_SCRIPT_V1 = '''\
"""
First AI call - tracked in git so every prompt change is diffable.
Version 1: baseline prompt.
"""
import os
import anthropic

MODEL = "claude-3-5-haiku-20241022"

# Every change to this prompt is a behavioral change.
# Treat it like code: review the diff, commit with a meaningful message.
SYSTEM_PROMPT = """You are a concise assistant. Answer in 1-3 sentences.
Do not use preambles like \'Sure!\' or \'Great question!\'."""

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def ask(question: str) -> str:
    """Single-turn question answering."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text


if __name__ == "__main__":
    q = "What is a context window in an LLM?"
    print(f"Q: {q}")
    print(f"A: {ask(q)}")
'''

FIRST_SCRIPT_V2 = '''\
"""
First AI call - tracked in git so every prompt change is diffable.
Version 2: added numbered list instruction.
"""
import os
import anthropic

MODEL = "claude-3-5-haiku-20241022"

# Every change to this prompt is a behavioral change.
# Treat it like code: review the diff, commit with a meaningful message.
SYSTEM_PROMPT = """You are a concise assistant. Answer in 1-3 sentences.
Do not use preambles like \'Sure!\' or \'Great question!\'.
When listing items, use numbered lists, not bullet points."""

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def ask(question: str) -> str:
    """Single-turn question answering."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text


if __name__ == "__main__":
    q = "What is a context window in an LLM?"
    print(f"Q: {q}")
    print(f"A: {ask(q)}")
'''


# ---------------------------------------------------------------------------
# Workflow steps
# ---------------------------------------------------------------------------

def setup_repo(project_dir: str) -> None:
    """Create the project directory, initialize git, and configure user."""
    os.makedirs(project_dir, exist_ok=True)
    print(f"\n[1] Initialize git repo in {project_dir}")
    run("git init", cwd=project_dir)
    # Minimal local git config for the demo repo
    run('git config user.email "ai-engineer@example.com"', cwd=project_dir)
    run('git config user.name "AI Engineer"', cwd=project_dir)


def write_gitignore(project_dir: str) -> None:
    """Write the AI-project .gitignore."""
    path = os.path.join(project_dir, ".gitignore")
    with open(path, "w") as f:
        f.write(GITIGNORE_CONTENT)
    print(f"\n[2] Wrote .gitignore to {path}")


def commit_first_script(project_dir: str) -> None:
    """Write version 1 of the script and make the initial commit."""
    script_path = os.path.join(project_dir, "first_call.py")
    with open(script_path, "w") as f:
        f.write(FIRST_SCRIPT_V1)
    print(f"\n[3] Committed v1 script and .gitignore")
    run("git add .gitignore first_call.py", cwd=project_dir)
    run(
        'git commit -m "init: AI project scaffold with gitignore and first API call"',
        cwd=project_dir,
    )


def tag_version(project_dir: str, tag: str, message: str) -> None:
    """Tag the current HEAD with a meaningful version label."""
    run(f'git tag -a {tag} -m "{message}"', cwd=project_dir)
    print(f"  Tagged {tag}: {message}")


def show_prompt_diff_workflow(project_dir: str) -> None:
    """
    Demonstrate the core workflow:
      1. Edit the prompt (simulate a behavioral change)
      2. Review with git diff BEFORE committing
      3. Commit with a descriptive message
    """
    script_path = os.path.join(project_dir, "first_call.py")

    print("\n[5] Edit the prompt (simulate adding a numbered-list instruction)")
    with open(script_path, "w") as f:
        f.write(FIRST_SCRIPT_V2)

    print("\n[6] Review the diff BEFORE committing")
    print("     This is the moment to catch unintended changes.")
    run("git diff first_call.py", cwd=project_dir)

    print("\n[7] Stage and commit with a descriptive message")
    run("git add first_call.py", cwd=project_dir)
    run(
        'git commit -m '
        '"prompt: add numbered-list instruction to improve scanability"',
        cwd=project_dir,
    )


def show_regression_debugging(project_dir: str) -> None:
    """
    Show how to identify which commit changed behavior.
    This is the workflow you use when eval scores drop after a deploy.
    """
    print("\n[8] Finding which commit changed behavior")
    print("     Use git log to identify the commit, then git show to inspect it")
    run("git log --oneline --decorate", cwd=project_dir)
    print()
    print("     To see exactly what changed in a specific commit:")
    result = run("git log --oneline", cwd=project_dir, check=False)
    hashes = [line.split()[0] for line in result.stdout.strip().splitlines()]
    if len(hashes) >= 2:
        run(f"git show {hashes[0]} -- first_call.py", cwd=project_dir)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    project_dir = "/tmp/ai_project_demo"

    print("=" * 60)
    print("  AI Project Git Workflow Demo")
    print("=" * 60)

    # Clean up any previous demo run
    import shutil
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)

    setup_repo(project_dir)
    write_gitignore(project_dir)
    commit_first_script(project_dir)

    print("\n[4] Tag v1.0 as baseline before experimenting")
    tag_version(project_dir, "v1.0-baseline", "Baseline prompt, eval score 6/10")

    show_prompt_diff_workflow(project_dir)

    print("\n[7b] Tag v1.1 after the improvement")
    tag_version(
        project_dir,
        "v1.1-numbered-lists",
        "Added numbered-list instruction, eval score 7/10",
    )

    show_regression_debugging(project_dir)

    print("\n" + "=" * 60)
    print("  Key git commands for AI projects")
    print("=" * 60)
    commands = [
        ("Review prompt changes", "git diff HEAD -- first_call.py"),
        ("View log with tags", "git log --oneline --decorate"),
        ("See exact state at a tag", "git show v1.0-baseline"),
        ("Roll back to a tag", "git checkout v1.0-baseline"),
        ("Return to current", "git checkout main"),
        ("Create experiment branch", "git checkout -b experiment/cot-prompting"),
    ]
    for label, cmd in commands:
        print(f"  {label}:")
        print(f"    $ {cmd}")
    print()
    print("  Key insight:")
    print("  Prompt changes are code changes. git diff shows exactly")
    print("  what changed. git log lets you find when scores dropped.")
    print("  git revert lets you undo it. Without git, you have none of this.")


if __name__ == "__main__":
    main()
