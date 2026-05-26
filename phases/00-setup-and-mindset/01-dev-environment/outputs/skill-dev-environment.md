---
name: skill-dev-environment
description: Reference card for uv commands, Python project layout, and Node/TypeScript setup for applied AI engineering
version: "1.0"
phase: "00"
lesson: "01"
tags: [uv, python, typescript, environment, setup]
---

# Dev Environment Reference Card

## uv: Core Commands

### Project Lifecycle

```bash
uv init                         # create new project (pyproject.toml + .venv)
uv init --name my-project       # with explicit project name
uv add anthropic                # add dependency (installs + updates uv.lock)
uv add anthropic==0.40.0        # add pinned version
uv add --dev pytest             # add dev-only dependency
uv remove anthropic             # remove dependency
uv sync                         # install all deps from uv.lock (CI/CD)
uv sync --frozen                # error if uv.lock would change (strict CI)
uv tree                         # show full dependency tree
```

### Running Code

```bash
uv run python main.py           # run with correct venv, no activation needed
uv run python -m pytest         # run module
uv run --python 3.11 python main.py  # run with specific Python version
uv run -- python main.py --arg  # pass args after --
```

### Python Version Management

```bash
uv python install 3.11          # install a Python version
uv python list                  # list available Python versions
uv python pin 3.11              # write .python-version file
```

### Tool Management (replaces pipx)

```bash
uv tool install ruff             # install CLI tool globally
uv tool run ruff check .         # run tool without installing globally
uvx ruff check .                 # shorthand for uv tool run
```

---

## Standard Project Layout (Python)

```
my-project/
├── .python-version     # single line: "3.12"
├── .venv/              # auto-managed, do not commit
├── pyproject.toml      # project metadata + dependencies
├── uv.lock             # COMMIT THIS - exact pinned versions
├── src/
│   └── my_project/
│       ├── __init__.py
│       └── main.py
└── tests/
    └── test_main.py
```

Key rule: commit `uv.lock`, never commit `.venv/`.

Add to `.gitignore`:
```
.venv/
__pycache__/
*.pyc
.env
```

---

## Standard pyproject.toml

```toml
[project]
name = "my-project"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
]

[tool.ruff.lint]
select = ["E", "F", "I"]
```

---

## Node + TypeScript Setup

```bash
# Install nvm (Node version manager)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
nvm install 20 && nvm use 20

# Project init
npm init -y
npm install @anthropic-ai/sdk
npm install --save-dev typescript ts-node @types/node

# Initialize TypeScript config
npx tsc --init
```

### Minimal tsconfig.json for this course

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "Node16",
    "moduleResolution": "Node16",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "./dist"
  },
  "include": ["**/*.ts"],
  "exclude": ["node_modules", "dist"]
}
```

### Run TypeScript

```bash
# Development (no compile step)
npx ts-node main.ts

# Production (compile then run)
npx tsc && node dist/main.js
```

---

## Environment Verification Checklist

```bash
uv --version                    # uv 0.5.x+
uv run python --version         # Python 3.11.x or 3.12.x
uv run python -c "import anthropic; print(anthropic.__version__)"
node --version                  # v20.x or higher
npx ts-node --version           # ts-node 10.x+
echo $ANTHROPIC_API_KEY | head -c 20   # should show sk-ant-...
```

All six must succeed before writing AI code.

---

## Common Errors and Fixes

| Error | Fix |
|-------|-----|
| `uv: command not found` | Add `~/.cargo/bin` or `~/.local/bin` to PATH |
| `ImportError: No module named anthropic` | Run `uv sync` |
| `ModuleNotFoundError` in uv run | Check pyproject.toml has the dep listed |
| `node: command not found` | Complete nvm install, run `nvm use 20` |
| `Cannot find module '@anthropic-ai/sdk'` | Run `npm install` |
| TS error: `moduleResolution` | Set `"moduleResolution": "Node16"` in tsconfig.json |
| `ANTHROPIC_API_KEY` not found | Check `.env` file exists and `python-dotenv` is loading it |
