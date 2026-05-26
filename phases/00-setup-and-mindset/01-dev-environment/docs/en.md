# Dev Environment: uv, Node, TypeScript

> One tool replaces four. Reproducible environments are not a nice-to-have; they are how you stop the "works on my machine" fire before it starts.

**Type:** Build
**Languages:** Both (Python + TypeScript)
**Prerequisites:** None
**Time:** ~45 min
**Learning Objectives:**
- Install uv and understand why it replaces pyenv, pip, venv, and pip-tools
- Initialize a Python project with `uv init`, add dependencies, and run scripts
- Set up Node.js with TypeScript and install the Anthropic SDK
- Verify your environment is correct before writing any AI code

---

## The Problem

You join a team building an AI feature. The repo has a `requirements.txt`, a `.python-version` file, and a `setup.cfg`. You clone it, run `pip install -r requirements.txt`, and immediately hit a conflict: the project needs Python 3.11, your system Python is 3.12, and one dependency pinned to an old version of `pydantic` breaks another. You spend 90 minutes debugging before you write a single line of business logic.

This is not a contrived scenario. It is the default experience when Python projects use the old four-tool stack: pyenv for Python version management, pip for installs, venv for isolation, and pip-tools for lockfiles. Four tools, four config files, four failure modes, and zero coordination between them.

The production AI stack needs a better foundation. Every lesson in this course runs on uv (Python) and Node/TypeScript. This lesson gets both set up in under 45 minutes, with a lockfile and a verified first API call as the exit condition.

---

## The Concept

### The Old Stack vs. The New Stack

The traditional Python setup uses four separate tools that have no native awareness of each other:

```
OLD STACK (4 tools, no coordination)
+----------+    +----------+    +---------+    +----------+
| pyenv    |    | venv     |    | pip     |    | pip-tools|
| (Python  |    | (isolat- |    | (install|    | (lock-   |
|  version)|    |  ation)  |    |  pkgs)  |    |  files)  |
+----------+    +----------+    +---------+    +----------+
     |               |               |               |
     v               v               v               v
.python-version  venv/ dir     requirements.txt  requirements.lock
                              (no pins = drift)   (optional, manual)

NEW STACK (1 tool, full coordination)
+------------------------------------------------------+
|                        uv                            |
|  version mgmt + isolation + install + lockfile       |
+------------------------------------------------------+
     |               |               |               |
     v               v               v               v
.python-version  .venv/ dir      pyproject.toml    uv.lock
                              (deps + metadata)  (auto-generated)
```

uv is written in Rust. Installs are 10-100x faster than pip because it resolves and downloads packages in parallel with an aggressive cache. The lockfile (`uv.lock`) is generated automatically on every `uv add` or `uv sync`, not as an afterthought.

### Project Layout After `uv init`

```
my-project/
├── .python-version    # e.g. "3.11"
├── .venv/             # isolated environment (auto-created)
├── pyproject.toml     # deps + project metadata (replaces setup.cfg + requirements.txt)
├── uv.lock            # exact pinned versions of all transitive deps
└── main.py            # or src/my_project/
```

### Node + TypeScript Layout

```
my-ts-project/
├── package.json       # deps + scripts
├── package-lock.json  # or pnpm-lock.yaml
├── tsconfig.json      # TypeScript compiler options
├── node_modules/      # installed packages
└── main.ts            # source
```

For lessons in this course, TypeScript code lives in `code/main.ts` alongside `code/main.py`. Both share the same `code/` directory.

---

## Build It

### Step 1: Install uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify
uv --version
# uv 0.5.x (or higher)
```

uv installs itself to `~/.cargo/bin/uv` (or `~/.local/bin/uv` on Linux). If `uv` is not found after install, add that directory to your PATH.

### Step 2: Create a Python Project

```bash
# Create a new project directory
mkdir ai-scratch && cd ai-scratch

# Initialize with uv (creates pyproject.toml, .python-version, main.py)
uv init

# Add the Anthropic SDK as a dependency
uv add anthropic

# uv automatically:
# 1. Creates .venv/ if it doesn't exist
# 2. Installs anthropic and its dependencies into .venv/
# 3. Writes the exact versions to uv.lock
# 4. Updates pyproject.toml with anthropic as a dependency
```

Inspect what was created:

```bash
cat pyproject.toml
# [project]
# name = "ai-scratch"
# version = "0.1.0"
# dependencies = ["anthropic>=0.40.0"]

cat .python-version
# 3.12  (or whatever uv detected)

ls -la uv.lock
# This file pins every transitive dependency exactly
```

### Step 3: Run a Python Script with uv

```bash
# Run without activating the venv first
uv run python main.py

# Or run any Python command
uv run python -c "import anthropic; print(anthropic.__version__)"
```

`uv run` is the key insight: you never need to `source .venv/bin/activate`. uv handles environment injection automatically. Every script in this course uses `uv run`.

> **Real-world check:** A teammate asks why you use `uv run python main.py` instead of just `python main.py`. They argue activating the venv once per terminal session is simpler. How would you explain what `uv run` actually does differently, and why it matters in a team with multiple projects on the same machine?

### Step 4: Set Up Node and TypeScript

```bash
# Check if Node is installed (need v20+)
node --version

# If not installed, use nvm (recommended):
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
nvm install 20
nvm use 20

# Initialize a Node project in the same directory
npm init -y

# Install the Anthropic TypeScript SDK
npm install @anthropic-ai/sdk

# Install TypeScript and ts-node for running .ts files directly
npm install --save-dev typescript ts-node @types/node

# Initialize TypeScript config
npx tsc --init
```

Verify the TypeScript setup:

```bash
# Create a minimal test file
echo 'import Anthropic from "@anthropic-ai/sdk"; console.log("SDK loaded:", typeof Anthropic);' > test-ts.ts
npx ts-node test-ts.ts
# SDK loaded: function
rm test-ts.ts
```

---

## Use It

`uv run` vs. activating a virtualenv is the core workflow shift. Here is the comparison:

```
ACTIVATE WORKFLOW (old)               UV RUN WORKFLOW (new)
--------------------                  -------------------
cd project-a                          cd project-a
source .venv/bin/activate             uv run python script.py
python script.py

cd ../project-b                       cd ../project-b
deactivate                            uv run python script.py
source .venv/bin/activate             # correct venv used automatically
python script.py
```

With `uv run`, the correct environment is always used, regardless of which project you are in. You cannot accidentally run code against the wrong venv.

```bash
# Add a new dependency (installs + updates pyproject.toml + uv.lock atomically)
uv add httpx

# Remove a dependency
uv remove httpx

# Sync environment to match uv.lock exactly (what CI/CD does)
uv sync

# Run with a specific Python version (uv installs it if missing)
uv run --python 3.11 python main.py

# Show the dependency tree
uv tree
```

> **Perspective shift:** pip's `requirements.txt` lists direct dependencies but not their exact transitive dependencies -- meaning the same file can install different versions of packages on different machines or at different points in time. `uv.lock` records every version of every package in the entire dependency graph, making environments bit-for-bit reproducible. This is the same guarantee Docker images give you, but for Python environments without the container overhead.

---

## Ship It

The artifact for this lesson is a reference card for uv commands and project layout.

See `outputs/skill-dev-environment.md`.

---

## Evaluate It

Your environment is correct when all of these pass:

```bash
# 1. uv version is current
uv --version
# Expected: uv 0.5.x or higher

# 2. Python version matches .python-version
uv run python --version
# Expected: Python 3.11.x or 3.12.x

# 3. Anthropic SDK imports cleanly
uv run python -c "import anthropic; print('anthropic', anthropic.__version__)"
# Expected: anthropic 0.40.x or higher (no ImportError)

# 4. uv.lock exists and is non-empty
wc -l uv.lock
# Expected: 100+ lines (transitive deps pinned)

# 5. Node SDK imports cleanly
node -e "const a = require('@anthropic-ai/sdk'); console.log('ts sdk loaded:', typeof a.default);"
# Expected: ts sdk loaded: function

# 6. TypeScript compiles
npx tsc --noEmit main.ts 2>&1 || echo "check tsconfig.json"
# Expected: no errors
```

If any check fails, the most common fixes:

- `uv: command not found` -- add `~/.cargo/bin` or `~/.local/bin` to PATH
- `ImportError: No module named anthropic` -- run `uv sync` to restore the lockfile state
- `node: command not found` -- complete the nvm installation and run `nvm use 20`
- TypeScript compile errors -- ensure `tsconfig.json` has `"moduleResolution": "node16"` or `"bundler"`
