---
name: skill-ai-project-git-workflow
description: Git conventions and .gitignore template for AI projects, with commit message patterns for tracking prompt changes as code
version: "1.0"
phase: "00"
lesson: "07"
tags: [git, versioning, prompts, workflow, gitignore]
---

# AI Project Git Workflow

Reference guide for version-controlling AI projects. Covers what to track, what to exclude, and how to write commit messages that make prompt regressions debuggable.

---

## The Core Rule

Prompt changes are code changes. Every edit to a prompt string is a behavioral deployment. If it is not in git with a meaningful commit message, you cannot:

- Diff what changed between the version that worked and the version that broke
- Roll back to a known-good prompt
- Measure whether a change improved or hurt your eval scores
- Attribute a regression to a specific commit

---

## .gitignore for AI Projects

```gitignore
# Python
__pycache__/
*.py[cod]
*.pyo
*.egg-info/
dist/
build/

# Virtual environments
.venv/
venv/
env/
.env/

# Secrets - NEVER commit
.env
*.env
secrets.json
credentials.json
config.local.py
*_key.txt

# API outputs that may contain PII
outputs/raw_responses/
outputs/eval_runs/
*.jsonl.gz

# Large files
model_weights/
*.bin
*.pt
*.onnx
*.safetensors

# OS and IDE
.DS_Store
Thumbs.db
.vscode/
.idea/
*.swp

# Logs
*.log
logs/
```

---

## What Goes in Git

| Track in git | Exclude from git |
|---|---|
| All `.py` files (code + prompts) | `.env` (API keys) |
| `prompts/` directory | `__pycache__/` |
| `evals/` directory | `.venv/` |
| `checks.json` | `outputs/raw_responses/` (may contain PII) |
| `requirements.txt` | `model_weights/` (too large) |
| `Dockerfile` | `*.log` |
| `.gitignore` itself | Any file with a secret in it |

**Decision rule:** If it regenerates automatically, contains secrets, or exceeds 50MB, exclude it. If you need it to reproduce a result, track it.

---

## Commit Message Patterns

Standard commit conventions do not capture the "why" of prompt changes. Use these patterns:

```bash
# Format: <type>: <what changed> - <behavioral intent>

# Prompt changes
git commit -m "prompt: add 'be concise' instruction - reduces preamble tokens 30%"
git commit -m "prompt: switch to numbered lists - improves scannability for support queries"
git commit -m "prompt: add chain-of-thought prefix - improves multi-step reasoning score 7->9"

# Eval changes
git commit -m "eval: add 10 contract questions, baseline score 6/10"
git commit -m "eval: expand to 50 questions - catches edge cases in date parsing"

# Config changes
git commit -m "config: increase max_tokens 512->1024 - fixes truncated summaries"
git commit -m "config: switch model haiku->sonnet for complex extraction task"

# Reverts
git commit -m "revert: undo chain-of-thought change - score dropped from 9 to 7 on short queries"
```

---

## Daily Workflow Commands

```bash
# Before any prompt edit, see what the current state is:
git status
git diff HEAD -- code/main.py

# After editing a prompt, review before committing:
git diff code/main.py   # see exactly what changed

# Stage and commit:
git add code/main.py
git commit -m "prompt: <what changed and why>"

# Tag a milestone (after running evals and hitting a score threshold):
git tag -a v1.2-cot-prompting -m "Score 9/10 on eval set. Deployed 2024-11-15."

# See the timeline of prompt changes:
git log --oneline --decorate

# Find the commit that caused a regression:
git log --oneline --since="1 week ago"
git show <hash>          # see the exact change
git checkout <hash>      # temporarily revert to test
git checkout main        # return to current

# See the exact code at a tagged version:
git show v1.0-baseline
git checkout v1.0-baseline   # test the baseline
git checkout main            # return
```

---

## Branch-Per-Experiment Pattern

Use branches when experimenting with significant prompt changes so you can compare against main without disrupting it:

```bash
# Start an experiment
git checkout -b experiment/rag-with-citations
# ... edit prompts, run evals ...
git commit -m "experiment: add citation instructions to RAG prompt"

# Compare experiment vs main on eval set
git checkout main
python evals/run_evals.py > results/main_score.txt
git checkout experiment/rag-with-citations
python evals/run_evals.py > results/experiment_score.txt
diff results/main_score.txt results/experiment_score.txt

# If the experiment wins, merge it:
git checkout main
git merge experiment/rag-with-citations
git tag -a v2.0-citations -m "Citations improved factuality score 6->8"
```

---

## Regression Debugging Protocol

When eval scores drop after a deploy, work through these steps:

1. `git log --oneline --since="last deploy date"` - list candidates
2. `git show <hash>` for each candidate - find the prompt change
3. `git checkout <hash>` - test the earlier version against your eval set
4. Compare scores: if earlier version passes, the regression is in the diff
5. `git checkout main` - return to current
6. `git revert <hash>` if needed - creates a new revert commit

---

## What NOT to Do

- **Never commit `.env` or any file with API keys.** Add them to `.gitignore` before the first commit. Removing secrets from git history after the fact is painful.
- **Never store raw API responses with user data in git.** They may contain PII. Keep them in `outputs/raw_responses/` which is gitignored.
- **Never use `git add .` without reviewing `git status` first.** Especially early in a project when .gitignore may be incomplete.
- **Never commit with the message "update prompt."** Six months later you cannot tell what it did or why it mattered.
