"""
Lesson 01-02: Prompt Fundamentals
Phase 01: Prompt and Context Engineering

Demonstrates iterative prompt improvement using the 6 core principles:
task definition, role/persona, output format, examples, constraints, tone.
Also introduces PromptTemplate for reusable, parameterized prompts.
"""

import anthropic

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

TRANSCRIPT = """
Alex: We need to fix the login bug before the demo on Friday.
Sam: I'll look into it today. Also the dashboard is slow, we should profile it.
Alex: Good idea. Can you also update the README with the new setup steps?
Sam: Sure. Who's handling the client call at 3pm tomorrow?
Alex: I'll take it. Jordan should send the invoice by end of week.
"""

# ---------------------------------------------------------------------------
# PromptTemplate: reusable, validated prompt templates
# ---------------------------------------------------------------------------

class PromptTemplate:
    """
    A prompt template that validates required variables before rendering.
    Treats prompts as parameterized code artifacts, not ad-hoc strings.
    """

    def __init__(self, template: str, required_vars: list[str], name: str = ""):
        self.template = template
        self.required_vars = required_vars
        self.name = name

    def render(self, **kwargs) -> str:
        """Render the template with provided variables. Raises ValueError if any required var is missing."""
        missing = [v for v in self.required_vars if v not in kwargs]
        if missing:
            raise ValueError(
                f"Template '{self.name}': missing required variables: {missing}"
            )
        return self.template.format(**kwargs)

    def __repr__(self) -> str:
        return f"PromptTemplate(name={self.name!r}, vars={self.required_vars})"


# ---------------------------------------------------------------------------
# The 4 prompt versions: progressively better
# ---------------------------------------------------------------------------

PROMPT_V0 = "Extract the action items from this meeting."

PROMPT_V1 = """Extract all action items from the meeting transcript below.
An action item is a task that a specific person agreed to do."""

PROMPT_V2 = """Extract all action items from the meeting transcript below.
An action item is a task that a specific person agreed to do.

Output as a numbered list. Each item: [PERSON]: [TASK] by [DEADLINE or 'no deadline']."""

PROMPT_V3 = """You are a project manager's assistant. Your job is to extract
clear action items from meeting transcripts.

Extract all action items from the transcript below. An action item is a
task that a specific person explicitly agreed to do.

Output as a numbered list. Each item: [PERSON]: [TASK] by [DEADLINE or 'no deadline'].
Do not include items that were discussed but not assigned.
Do not add commentary or explanation."""

PROMPT_V4_TEMPLATE = PromptTemplate(
    template="""You are a project manager's assistant. Your job is to extract
clear action items from meeting transcripts.

Extract all action items from the transcript below. An action item is a
task that a specific person explicitly agreed to do.

Output as a numbered list. Format each item as:
[PERSON]: [TASK] by [DEADLINE or 'no deadline']

Rules:
- Include only explicitly assigned tasks
- If no deadline is mentioned, write 'no deadline' - never leave the field blank
- Do not add commentary, headers, or explanation

Example output:
1. Sam: Fix the login bug by Friday
2. Alex: Schedule client kickoff call by no deadline
3. Jordan: Send the invoice by end of week

Transcript:
{transcript}

Tone: {tone}""",
    required_vars=["transcript", "tone"],
    name="action-items-v4"
)


# ---------------------------------------------------------------------------
# Helper: run a prompt and return response
# ---------------------------------------------------------------------------

def run_prompt(prompt: str, model: str = "claude-3-5-haiku-20241022") -> str:
    """Run a prompt against the model. Returns the text output."""
    response = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def run_with_transcript(prompt_prefix: str, transcript: str) -> str:
    """Run a prompt with an appended transcript."""
    full_prompt = f"{prompt_prefix}\n\n{transcript}"
    return run_prompt(full_prompt)


# ---------------------------------------------------------------------------
# Demo 1: Show variance with the bad prompt
# ---------------------------------------------------------------------------

def demo_bad_prompt() -> None:
    print("=" * 60)
    print("DEMO 1: Vague prompt - run 3 times, notice variance")
    print("=" * 60)

    for i in range(3):
        result = run_with_transcript(PROMPT_V0, TRANSCRIPT)
        print(f"\nRun {i+1}:\n{result}")
        print("-" * 40)


# ---------------------------------------------------------------------------
# Demo 2: Iterative improvement
# ---------------------------------------------------------------------------

def demo_iterative_improvement() -> None:
    print("\n" + "=" * 60)
    print("DEMO 2: Iterative improvement - same transcript, 4 prompts")
    print("=" * 60)

    prompts = [
        ("v0 - vague",                         PROMPT_V0),
        ("v1 - task definition",               PROMPT_V1),
        ("v2 - + output format",               PROMPT_V2),
        ("v3 - + role, constraint",            PROMPT_V3),
    ]

    for label, prompt in prompts:
        result = run_with_transcript(prompt, TRANSCRIPT)
        print(f"\n[{label}]\n{result}\n" + "-" * 40)


# ---------------------------------------------------------------------------
# Demo 3: PromptTemplate in action
# ---------------------------------------------------------------------------

def demo_template() -> None:
    print("\n" + "=" * 60)
    print("DEMO 3: PromptTemplate - v4 with example and edge case handling")
    print("=" * 60)

    prompt = PROMPT_V4_TEMPLATE.render(
        transcript=TRANSCRIPT,
        tone="direct and factual"
    )
    result = run_prompt(prompt)
    print(f"\nOutput:\n{result}")

    # Show what happens with a transcript that has no deadlines
    no_deadline_transcript = """
    Jordan: Someone should look into the latency spike.
    Riley: I can do that.
    Jordan: Great. Also we should document the deployment process.
    Riley: I'll handle it.
    """
    prompt2 = PROMPT_V4_TEMPLATE.render(
        transcript=no_deadline_transcript,
        tone="direct and factual"
    )
    result2 = run_prompt(prompt2)
    print(f"\nNo-deadline transcript output:\n{result2}")


# ---------------------------------------------------------------------------
# Demo 4: Template validation
# ---------------------------------------------------------------------------

def demo_template_validation() -> None:
    print("\n" + "=" * 60)
    print("DEMO 4: Template validation - missing variable raises clear error")
    print("=" * 60)

    try:
        PROMPT_V4_TEMPLATE.render(transcript=TRANSCRIPT)  # missing 'tone'
    except ValueError as e:
        print(f"Caught expected error: {e}")

    # Show a valid render
    rendered = PROMPT_V4_TEMPLATE.render(
        transcript="Short transcript.",
        tone="casual"
    )
    print(f"\nValid render (first 100 chars): {rendered[:100]}...")


# ---------------------------------------------------------------------------
# Demo 5: Consistency test - same prompt, 5 runs
# ---------------------------------------------------------------------------

def demo_consistency_test() -> None:
    print("\n" + "=" * 60)
    print("DEMO 5: Consistency test - v4 prompt, 5 runs")
    print("Expected: same structured format every time")
    print("=" * 60)

    prompt = PROMPT_V4_TEMPLATE.render(
        transcript=TRANSCRIPT,
        tone="direct and factual"
    )

    for i in range(3):  # 3 runs to keep demo fast; use 5-10 in real evaluation
        result = run_prompt(prompt)
        # Simple structural check: does it start with '1.'?
        starts_with_number = result.strip().startswith("1.")
        print(f"\nRun {i+1} (starts with '1.': {starts_with_number}):\n{result}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Lesson 01-02: Prompt Fundamentals")
    print("Select a demo to run:\n")
    print("  1. Vague prompt variance (3 runs)")
    print("  2. Iterative improvement (4 prompt versions)")
    print("  3. PromptTemplate in action")
    print("  4. Template validation")
    print("  5. Consistency test")
    print("  all. Run all demos\n")

    choice = input("Choice: ").strip().lower()

    if choice == "1":
        demo_bad_prompt()
    elif choice == "2":
        demo_iterative_improvement()
    elif choice == "3":
        demo_template()
    elif choice == "4":
        demo_template_validation()
    elif choice == "5":
        demo_consistency_test()
    elif choice == "all":
        demo_bad_prompt()
        demo_iterative_improvement()
        demo_template()
        demo_template_validation()
        demo_consistency_test()
    else:
        print("Running demo 3 (PromptTemplate) as default...")
        demo_template()
