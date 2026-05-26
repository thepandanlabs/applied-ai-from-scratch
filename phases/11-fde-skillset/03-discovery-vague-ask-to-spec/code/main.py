#!/usr/bin/env python3
"""
AI Spec Writer

Takes rough discovery notes and uses Claude to structure them into
a 7-section AI spec. Flags missing or unconfirmed sections.

Usage:
    python main.py --notes notes.txt
    python main.py --notes notes.txt --output spec.json
    python main.py --interactive
"""
import json
import sys
import argparse
import re
from pathlib import Path
import anthropic

MODEL = "claude-3-5-haiku-20241022"

SPEC_SYSTEM_PROMPT = """You are an AI spec writer for a Forward-Deployed Engineering team.
Your job is to take rough discovery notes and structure them into a formal AI spec.

The AI spec has exactly 7 sections. Output each section on its own line starting with
the section number and name in all-caps, followed by the content.

Sections:
1. PROBLEM STATEMENT - Describe the pain in customer terms, not engineering terms.
2. SUCCESS METRIC - Must include: number, baseline, time horizon, measurement source.
   If notes don't contain a specific metric, suggest one and prefix with [SUGGESTED].
3. INPUT/OUTPUT CONTRACT - What goes in, what comes out, in what format.
4. DATA SOURCES - Owner (named person), system, format, access path.
   If unknown, write [UNKNOWN].
5. INTEGRATION POINTS - Where output lands, who acts on it, error handling.
6. RISKS AND UNKNOWNS - Unresolved questions that could affect the build.
7. OUT OF SCOPE - What this system will NOT do in version 1.

Rules:
- Do not invent facts. Only use information present in the notes.
- If a section has no information in the notes, write [UNKNOWN - must resolve before build].
- If you suggest a success metric, it must be plausible from the notes and flagged [SUGGESTED].
- Keep each section concise: 1-4 bullet points or sentences.
- End with a line: FLAGS: followed by any [SUGGESTED] or [UNKNOWN] items that must be resolved.
"""

SPEC_USER_TEMPLATE = """Here are the raw discovery notes:

---
{notes}
---

Please write the AI spec."""

SECTION_NAMES = [
    "PROBLEM STATEMENT",
    "SUCCESS METRIC",
    "INPUT/OUTPUT CONTRACT",
    "DATA SOURCES",
    "INTEGRATION POINTS",
    "RISKS AND UNKNOWNS",
    "OUT OF SCOPE",
]


def parse_spec(raw: str) -> dict:
    """Parse Claude's spec output into sections."""
    sections: dict[str, str] = {}
    flags: list[str] = []

    current_section = None
    current_lines: list[str] = []

    for line in raw.splitlines():
        stripped = line.strip()

        # Check if this line starts a new section
        matched_section = None
        for name in SECTION_NAMES:
            pattern = rf"^\d+\.\s+{re.escape(name)}"
            if re.match(pattern, stripped, re.IGNORECASE):
                matched_section = name
                break

        if matched_section:
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = matched_section
            # Capture text on the same line after the section heading
            rest = re.sub(rf"^\d+\.\s+{re.escape(matched_section)}\s*[-:]?\s*", "", stripped, flags=re.IGNORECASE)
            current_lines = [rest] if rest else []

        elif stripped.upper().startswith("FLAGS:"):
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
                current_section = None
            flag_text = stripped[6:].strip()
            if flag_text:
                flags.append(flag_text)

        else:
            if current_section:
                current_lines.append(stripped)
            elif stripped.startswith("-") or stripped.startswith("*"):
                flags.append(stripped.lstrip("-* "))

    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    # Collect inline flags from section content
    for name, content in sections.items():
        if "[SUGGESTED]" in content or "[UNKNOWN]" in content:
            flags.append(f"Section '{name}' has unresolved items.")

    return {"sections": sections, "flags": list(dict.fromkeys(flags))}


def call_claude(notes: str, client: anthropic.Anthropic) -> str:
    """Call Claude to generate the AI spec."""
    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SPEC_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": SPEC_USER_TEMPLATE.format(notes=notes)}
        ],
    )
    return message.content[0].text


def print_spec(parsed: dict) -> None:
    print("\n" + "=" * 55)
    print("AI SPEC")
    print("=" * 55)

    for i, name in enumerate(SECTION_NAMES, 1):
        content = parsed["sections"].get(name, "[UNKNOWN - must resolve before build]")
        print(f"\n{i}. {name}")
        for line in content.splitlines():
            if line.strip():
                print(f"   {line}")

    flags = parsed.get("flags", [])
    if flags:
        print("\n" + "=" * 55)
        print(f"FLAGS ({len(flags)} items to resolve before build)")
        print("=" * 55)
        for flag in flags:
            print(f"  * {flag}")
    else:
        print("\nNo flags. Spec is complete.")


def collect_notes_interactive() -> str:
    print("\n=== AI SPEC WRITER ===")
    print("Paste your discovery notes below.")
    print("Enter a blank line followed by 'END' when done.\n")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Spec Writer")
    parser.add_argument("--notes", metavar="FILE", help="Path to discovery notes file")
    parser.add_argument("--output", metavar="FILE", help="Export spec to JSON file")
    parser.add_argument("--markdown", metavar="FILE", help="Export spec to Markdown file")
    parser.add_argument("--interactive", action="store_true", help="Enter notes interactively")
    args = parser.parse_args()

    if args.notes:
        notes_path = Path(args.notes)
        if not notes_path.exists():
            print(f"Error: file not found: {args.notes}", file=sys.stderr)
            sys.exit(1)
        notes = notes_path.read_text()
    elif args.interactive:
        notes = collect_notes_interactive()
    else:
        parser.print_help()
        sys.exit(0)

    if not notes.strip():
        print("Error: notes are empty.", file=sys.stderr)
        sys.exit(1)

    print("\nGenerating AI spec from discovery notes...")
    client = anthropic.Anthropic()
    raw = call_claude(notes, client)
    parsed = parse_spec(raw)

    print_spec(parsed)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(
                {
                    "sections": parsed["sections"],
                    "flags": parsed["flags"],
                    "raw": raw,
                },
                f,
                indent=2,
            )
        print(f"\nSpec exported to {args.output}")

    if args.markdown:
        lines = ["# AI Spec\n"]
        for i, name in enumerate(SECTION_NAMES, 1):
            content = parsed["sections"].get(name, "[UNKNOWN - must resolve before build]")
            lines.append(f"## {i}. {name}\n")
            lines.append(content + "\n")
        if parsed["flags"]:
            lines.append("## Flags\n")
            for flag in parsed["flags"]:
                lines.append(f"- {flag}")
        with open(args.markdown, "w") as f:
            f.write("\n".join(lines))
        print(f"Markdown spec exported to {args.markdown}")


if __name__ == "__main__":
    main()
