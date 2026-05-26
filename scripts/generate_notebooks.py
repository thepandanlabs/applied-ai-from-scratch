#!/usr/bin/env python3
"""
Generate Colab-ready Jupyter notebooks from lesson source files.

Usage:
    python scripts/generate_notebooks.py --phase 02
    python scripts/generate_notebooks.py --all
"""

import argparse
import json
import re
import sys
from pathlib import Path

import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

REPO = "thepandanlabs/applied-ai-from-scratch"
COLAB_BASE = f"https://colab.research.google.com/github/{REPO}/blob/main"

# Map Python module names to pip package names
IMPORT_TO_PIP = {
    "anthropic": "anthropic",
    "openai": "openai",
    "numpy": "numpy",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "fastapi": "fastapi uvicorn",
    "uvicorn": "uvicorn",
    "langfuse": "langfuse",
    "ragas": "ragas",
    "braintrust": "braintrust",
    "rank_bm25": "rank-bm25",
    "tenacity": "tenacity",
    "sentence_transformers": "sentence-transformers",
    "sklearn": "scikit-learn",
    "scipy": "scipy",
    "pdfplumber": "pdfplumber",
    "PIL": "Pillow",
    "pydub": "pydub",
    "bleach": "bleach",
    "presidio_analyzer": "presidio-analyzer presidio-anonymizer",
    "presidio_anonymizer": "presidio-anonymizer",
    "structlog": "structlog",
    "litellm": "litellm",
    "peft": "peft transformers",
    "transformers": "transformers",
    "bitsandbytes": "bitsandbytes",
    "trl": "trl",
    "opentelemetry": "opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc",
    "mcp": "mcp",
    "httpx": "httpx",
    "aiohttp": "aiohttp",
    "tiktoken": "tiktoken",
    "pymupdf": "pymupdf",
    "fitz": "pymupdf",
}

# Lessons that run a service and can't execute end-to-end in Colab
SERVICE_LESSON_NAMES = {
    "02-wrapping-model-in-fastapi",
    "03-streaming-sse-async",
    "05-docker-image-ai-app",
    "11-deploying-managed-and-container",
    "14-capstone-deploy-rag-agent",
    "13-capstone",
}

# Lessons that benefit from GPU
GPU_LESSON_NAMES = {
    "04-lora-and-qlora",
    "08-serving-open-weight-model-vllm",
}


def detect_pip_packages(py_content: str) -> list[str]:
    """Extract pip packages from import statements in the Python file."""
    packages: set[str] = set()
    for line in py_content.splitlines():
        line = line.strip()
        if not (line.startswith("import ") or line.startswith("from ")):
            continue
        m = re.match(r'(?:from|import)\s+(\w+)', line)
        if m:
            mod = m.group(1)
            if mod in IMPORT_TO_PIP:
                # Each entry may be multiple packages separated by space
                for pkg in IMPORT_TO_PIP[mod].split():
                    packages.add(pkg)
    return sorted(packages)


def parse_en_md(md_path: Path) -> dict:
    """Parse docs/en.md and return title, metadata, and section bodies."""
    content = md_path.read_text(encoding="utf-8")

    # Title: first H1
    title_m = re.search(r'^# (.+)$', content, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else md_path.parent.parent.name

    # Metadata: lines of the form **Key:** value
    meta: dict[str, str] = {}
    for key in ["Type", "Languages", "Prerequisites", "Time", "Phase"]:
        m = re.search(rf'\*\*{key}\*\*:\s*(.+)', content)
        if m:
            meta[key.lower()] = m.group(1).strip()

    # Sections: split on ## headings
    sections: dict[str, str] = {}
    parts = re.split(r'^## (.+)$', content, flags=re.MULTILINE)
    # parts[0] = before first H2, then alternating heading/body
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections[heading] = body.strip()

    return {"title": title, "meta": meta, "sections": sections}


def split_main_py(py_path: Path) -> list[dict]:
    """
    Split main.py into logical sections using triple-line separator comments:
        # ---------------------------------------------------------------------------
        # Section Title
        # ---------------------------------------------------------------------------
    Also extracts the body of `if __name__ == "__main__":` as a final section.
    """
    content = py_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Find and extract the `if __name__ == "__main__":` block
    main_start = None
    for i, line in enumerate(lines):
        if re.match(r'^if __name__\s*==\s*["\']__main__["\']:', line):
            main_start = i
            break

    main_body = ""
    if main_start is not None:
        body_lines = []
        for line in lines[main_start + 1:]:
            if line.startswith("    ") or line.strip() == "":
                body_lines.append(line[4:] if line.startswith("    ") else "")
            elif line.strip() and not line.startswith(" "):
                break
        main_body = "\n".join(body_lines).strip()
        content = "\n".join(lines[:main_start]).rstrip()

    # Split on triple-line separator pattern
    # Matches: \n# ---...\n# Title\n# ---...\n
    parts = re.split(r'\n# -{40,}\n# ([^\n]+)\n# -{40,}\n', content)
    # parts[0] = preamble, parts[1,3,5,...] = titles, parts[2,4,6,...] = bodies

    sections = []
    preamble = parts[0].strip()
    if preamble:
        sections.append({"title": "Setup & Imports", "code": preamble})

    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            sections.append({"title": title, "code": body})

    if main_body:
        sections.append({"title": "Demo", "code": main_body})

    return sections


def extract_exercises(sections_md: dict) -> list[dict]:
    """Parse the Exercises section of docs/en.md into structured exercise dicts."""
    exercises_text = sections_md.get("Exercises", "")
    if not exercises_text:
        return []

    exercises = []
    for level in ["Easy", "Medium", "Hard"]:
        # Match **Easy:** or **Easy** followed by content until the next level heading
        m = re.search(
            rf'\*\*{level}[:\*]*\*?\*?\s*(.+?)(?=\n\*\*(?:Easy|Medium|Hard)|\Z)',
            exercises_text,
            re.DOTALL,
        )
        if m:
            text = re.sub(r'\n+', ' ', m.group(1)).strip()
            # Clean trailing markdown
            text = re.sub(r'\*+$', '', text).strip()
            if text:
                exercises.append({"level": level, "description": text})

    return exercises


def make_exercise_code(exercise: dict, py_sections: list[dict]) -> str:
    """
    Build a code cell for an exercise with generous hints.
    Extracts function names from the lesson for contextual hints.
    """
    level = exercise["level"]
    desc = exercise["description"]

    # Collect function names defined in this lesson
    func_names = []
    for section in py_sections:
        for m in re.finditer(r'^def (\w+)\(', section["code"], re.MULTILINE):
            name = m.group(1)
            if not name.startswith("_") and name not in func_names:
                func_names.append(name)

    lines = [f"# EXERCISE ({level}): {desc}", "#"]

    if func_names:
        preview = ", ".join(func_names[:4])
        lines.append(f"# Hint: The key functions from this lesson are: {preview}()")

    if level == "Easy":
        lines += [
            "# Hint: Start by calling one of the functions above with a small test input.",
            "# Hint: Check each function's docstring for expected arguments and return type.",
        ]
    elif level == "Medium":
        lines += [
            "# Hint: Modify or extend one of the core functions defined above.",
            "# Hint: Test with a few hand-crafted examples before running on the full dataset.",
        ]
    else:
        lines += [
            "# Hint: This exercise requires combining multiple functions from the lesson.",
            "# Hint: Write a small helper function first, then integrate it into the pipeline.",
            "# Hint: Compare your output against the demo output in the cell above.",
        ]

    lines += [
        "#",
        "# YOUR CODE HERE",
        f'raise NotImplementedError("Complete the {level} exercise")',
    ]

    return "\n".join(lines)


def make_service_warning() -> str:
    return (
        "> **Note:** This lesson builds a service that must run as a long-lived process. "
        "The cells below show the full implementation but cannot run end-to-end in Colab. "
        "To run this lesson: clone the repo locally and use `uvicorn main:app` or `docker compose up`."
    )


def make_gpu_note() -> str:
    return (
        "> **GPU Recommended:** This lesson trains a model adapter. "
        "Enable a free T4 GPU in Colab: **Runtime → Change runtime type → T4 GPU**. "
        "Without GPU, training will be very slow."
    )


def make_notebook(lesson_path: Path, phase_id: str) -> nbformat.NotebookNode | None:
    """Generate a Jupyter notebook for a single lesson."""
    py_path = lesson_path / "code" / "main.py"
    md_path = lesson_path / "docs" / "en.md"
    checks_path = lesson_path / "checks.json"

    if not py_path.exists() or not md_path.exists():
        return None

    lesson_slug = lesson_path.name
    is_service = lesson_slug in SERVICE_LESSON_NAMES
    is_gpu = lesson_slug in GPU_LESSON_NAMES

    parsed = parse_en_md(md_path)
    title = parsed["title"]
    meta = parsed["meta"]
    sections_md = parsed["sections"]
    py_sections = split_main_py(py_path)
    exercises = extract_exercises(sections_md)

    py_content = py_path.read_text(encoding="utf-8")
    packages = detect_pip_packages(py_content)

    nb_path = f"notebooks/phase-{phase_id}/{lesson_slug}.ipynb"
    colab_url = f"{COLAB_BASE}/{nb_path}"

    nb = new_notebook()
    cells = []

    # ── Cell 1: Header ──────────────────────────────────────────────────────
    prereqs = meta.get("prerequisites", "See lesson README")
    time_est = meta.get("time", "~60 minutes")
    lang = meta.get("languages", "Python")

    header = (
        f"# {title}\n\n"
        f"**Phase {phase_id}** · {time_est} · {lang}\n\n"
        f"**Prerequisites:** {prereqs}\n\n"
        f"[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({colab_url})\n\n"
        "---\n\n"
        "> This notebook is auto-generated from the "
        f"[Applied AI From Scratch](https://github.com/{REPO}) curriculum.  \n"
        "> Run cells top to bottom. Set your API key in the **Setup** cell below.\n"
    )
    if is_gpu:
        header += f"\n{make_gpu_note()}\n"
    if is_service:
        header += f"\n{make_service_warning()}\n"
    cells.append(new_markdown_cell(header))

    # ── Cell 2: Setup ───────────────────────────────────────────────────────
    pip_line = f"!pip install -q {' '.join(packages)}\n\n" if packages else ""
    # Determine which key variable the lesson uses
    needs_anthropic = "anthropic" in py_content.lower()
    needs_openai = "openai" in py_content.lower() and "anthropic" not in py_content.lower()

    if needs_anthropic:
        key_lines = (
            'try:\n'
            '    from google.colab import userdata\n'
            '    os.environ["ANTHROPIC_API_KEY"] = userdata.get("ANTHROPIC_API_KEY")\n'
            'except Exception:\n'
            '    pass  # Running locally — set ANTHROPIC_API_KEY before this cell\n'
        )
        check_var = '"ANTHROPIC_API_KEY"'
    else:
        key_lines = (
            'try:\n'
            '    from google.colab import userdata\n'
            '    os.environ["OPENAI_API_KEY"] = userdata.get("OPENAI_API_KEY")\n'
            'except Exception:\n'
            '    pass  # Running locally — set OPENAI_API_KEY before this cell\n'
        )
        check_var = '"OPENAI_API_KEY"'

    setup_code = (
        f"{pip_line}"
        "import os\n\n"
        f"{key_lines}\n"
        f'print("Setup complete. API key set:", bool(os.environ.get({check_var})))'
    )
    cells.append(new_code_cell(setup_code))

    # ── Cell 3: Lesson context from docs ────────────────────────────────────
    problem = sections_md.get("The Problem", "")
    concept = sections_md.get("The Concept", "")
    intro_parts = []
    if problem:
        # Truncate long sections
        snippet = problem[:700] + ("..." if len(problem) > 700 else "")
        intro_parts.append(f"## The Problem\n\n{snippet}")
    if concept:
        # Strip mermaid and ascii code fences — they don't render in notebooks
        concept_clean = re.sub(
            r'```(?:mermaid|ascii)[^`]+```', '', concept, flags=re.DOTALL
        ).strip()
        snippet = concept_clean[:600] + ("..." if len(concept_clean) > 600 else "")
        intro_parts.append(f"## The Concept\n\n{snippet}")
    if intro_parts:
        intro_parts.append("_Read the full lesson narrative in `docs/en.md` or on the course site._")
        cells.append(new_markdown_cell("\n\n".join(intro_parts)))

    # ── Cells 4-N: Implementation from main.py ──────────────────────────────
    cells.append(new_markdown_cell("## Implementation\n\nRun each cell in order:"))
    for section in py_sections:
        code = section["code"].strip()
        if not code:
            continue
        cells.append(new_markdown_cell(f"### {section['title']}"))
        cells.append(new_code_cell(code))

    # ── Exercise cells ───────────────────────────────────────────────────────
    if exercises:
        cells.append(new_markdown_cell(
            "---\n\n## Exercises\n\n"
            "Deepen your understanding by completing these exercises:"
        ))
        for exercise in exercises:
            cells.append(new_markdown_cell(f"### {exercise['level']} Exercise"))
            cells.append(new_code_cell(make_exercise_code(exercise, py_sections)))

    # ── Self-check from checks.json ──────────────────────────────────────────
    if checks_path.exists():
        try:
            raw = json.loads(checks_path.read_text(encoding="utf-8"))
            # Handle both raw array and {"checks": [...]} formats
            checks = raw if isinstance(raw, list) else raw.get("checks", [])
            if checks:
                sc = "---\n\n## Self-Check\n\nAnswer these without running code first:\n\n"
                for i, check in enumerate(checks, 1):
                    q = check.get("question", "")
                    opts = check.get("options", [])
                    sc += f"**{i}. {q}**\n\n"
                    for opt in opts:
                        sc += f"- {opt}\n"
                    sc += "\n"
                sc += "_Answers are in `checks.json` in the lesson directory._"
                cells.append(new_markdown_cell(sc))
        except (json.JSONDecodeError, KeyError):
            pass

    nb.cells = cells
    nb.metadata.update({
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.11.0",
        },
        "colab": {
            "provenance": [],
        },
    })

    return nb


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Colab notebooks from Applied AI From Scratch lesson sources"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--phase", metavar="NN", help="Phase ID to generate (e.g. 02)")
    group.add_argument("--all", action="store_true", help="Generate for all phases")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    phases_dir = repo_root / "phases"
    notebooks_dir = repo_root / "notebooks"

    # Collect matching phase directories
    phase_dirs: list[tuple[str, Path]] = []
    for d in sorted(phases_dir.iterdir()):
        if not d.is_dir():
            continue
        phase_id = d.name.split("-")[0]
        if args.phase and phase_id != args.phase.zfill(2):
            continue
        phase_dirs.append((phase_id, d))

    if not phase_dirs:
        print(f"No phases found for filter: {args.phase}", file=sys.stderr)
        sys.exit(1)

    generated = 0
    skipped = 0

    for phase_id, phase_dir in phase_dirs:
        out_dir = notebooks_dir / f"phase-{phase_id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        lesson_dirs = sorted(
            d for d in phase_dir.iterdir()
            if d.is_dir() and re.match(r'^\d{2}-', d.name)
        )
        for lesson_dir in lesson_dirs:
            nb = make_notebook(lesson_dir, phase_id)
            if nb is None:
                print(f"  Skip (no main.py): {lesson_dir.name}")
                skipped += 1
                continue

            out_path = out_dir / f"{lesson_dir.name}.ipynb"
            with open(out_path, "w", encoding="utf-8") as f:
                nbformat.write(nb, f)
            print(f"  OK  {out_path.relative_to(repo_root)}")
            generated += 1

    print(f"\nDone: {generated} generated, {skipped} skipped")


if __name__ == "__main__":
    main()
