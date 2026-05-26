# Prompt Fundamentals

> Prompts are code. Vague instructions produce vague outputs because the model fills gaps with its priors.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lesson 01 (Request Anatomy), `pip install anthropic`
**Time:** ~45 min
**Learning Objectives:**
- Apply the 6 core prompt principles: task definition, role/persona, output format, examples, constraints, and tone
- Diagnose why a vague prompt produces inconsistent outputs
- Iteratively improve a prompt by applying each principle in sequence
- Build a reusable PromptTemplate class using f-strings
- Evaluate prompt quality by measuring output consistency across multiple runs

---

## THE PROBLEM

You write a prompt, it mostly works, you ship it. Three weeks later, users are reporting that 1 in 10 responses is formatted wrong, or too long, or in the wrong language, or just off. You tweak the prompt, redeploy, it's better for a week, then something else breaks.

The underlying problem: you wrote a prompt the way you write a Slack message. Casual, incomplete, relying on the recipient to fill in the gaps. With a colleague, that works because they share your context. With a language model, the gaps get filled with statistical priors from training data, which may or may not match what you meant.

Prompts are code. They have a job to do, they have inputs and outputs, they need to be explicit about what success looks like. A prompt that works 80% of the time is not a prompt that's almost working. It's a prompt that's broken 20% of the time.

---

## THE CONCEPT

### The 6 Prompt Principles

Six properties reliably distinguish prompts that produce consistent, production-quality outputs from prompts that produce variable results:

```
1. TASK DEFINITION   What exactly is the model supposed to do?
                     Be specific. "Summarize" is not a task definition.
                     "Summarize in 3 bullet points, one sentence each" is.

2. ROLE / PERSONA    Who is the model in this context?
                     Roles activate relevant training patterns and
                     set implicit quality bars.

3. OUTPUT FORMAT     What does the output look like structurally?
                     JSON, markdown, plain text, list? Specify it.
                     Include structure, length, and any required fields.

4. EXAMPLES          One or two examples of good outputs.
                     The most reliable way to communicate format and style.
                     Description alone is ambiguous. Examples are concrete.

5. CONSTRAINTS       What should the model NOT do?
                     Negative constraints often matter more than positive ones.
                     "Do not include disclaimers" eliminates a common failure mode.

6. TONE              Formal, casual, technical, plain language?
                     Tone affects vocabulary, sentence structure, and assumed
                     reader expertise. Specify it or get inconsistency.
```

### Prompt Anatomy: Before and After

```
BEFORE (vague):
┌──────────────────────────────────────────────────────┐
│ "Summarize this article."                            │
│                                                      │
│ Problems:                                            │
│  - Length undefined (3 words? 3 paragraphs?)         │
│  - Format undefined (prose? bullets? headline?)      │
│  - Audience undefined (expert? general public?)      │
│  - Tone undefined (formal? casual?)                  │
│  - No constraints (include opinions? caveats?)       │
└──────────────────────────────────────────────────────┘

AFTER (explicit):
┌──────────────────────────────────────────────────────┐
│ ROLE:    "You are an editor writing for a general    │
│           tech audience."                            │
│                                                      │
│ TASK:    "Summarize the article below in exactly     │
│           3 bullet points."                          │
│                                                      │
│ FORMAT:  "Each bullet: 1 sentence, under 20 words.  │
│           Start with a strong verb."                 │
│                                                      │
│ EXAMPLE: "- Reveals that X causes Y in production." │
│                                                      │
│ CONSTRAINT: "No marketing language. No caveats."    │
│                                                      │
│ TONE:    "Direct and factual."                       │
└──────────────────────────────────────────────────────┘
```

The "after" prompt takes 30 seconds longer to write and produces consistent outputs that need no cleanup.

---

## BUILD IT

### Iterative Prompt Improvement

The best way to internalize these principles is to start with a broken prompt and fix it step by step. Each step should be measurable.

**The task:** Extract action items from a meeting transcript. Simple enough to evaluate quickly, tricky enough to show variance.

**Step 0: The bad prompt.**

```python
import anthropic

client = anthropic.Anthropic()

TRANSCRIPT = """
Alex: We need to fix the login bug before the demo on Friday.
Sam: I'll look into it today. Also the dashboard is slow, we should profile it.
Alex: Good idea. Can you also update the README with the new setup steps?
Sam: Sure. Who's handling the client call at 3pm tomorrow?
Alex: I'll take it. Jordan should send the invoice by end of week.
"""

def run_prompt(prompt: str, transcript: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": f"{prompt}\n\n{transcript}"}]
    )
    return response.content[0].text

bad_prompt = "Extract the action items from this meeting."
print("BAD PROMPT OUTPUT:")
print(run_prompt(bad_prompt, TRANSCRIPT))
```

Run this 3 times. You'll get different formats, different levels of detail, sometimes a paragraph, sometimes a list, sometimes with assignees, sometimes without.

**Step 1: Add task definition.**

```python
prompt_v1 = """Extract all action items from the meeting transcript below.
An action item is a task that a specific person agreed to do."""
```

Better. Now add format.

**Step 2: Add output format.**

```python
prompt_v2 = """Extract all action items from the meeting transcript below.
An action item is a task that a specific person agreed to do.

Output as a numbered list. Each item: [PERSON]: [TASK] by [DEADLINE or 'no deadline']."""
```

**Step 3: Add role and constraint.**

```python
prompt_v3 = """You are a project manager's assistant. Your job is to extract
clear action items from meeting transcripts.

Extract all action items from the transcript below. An action item is a
task that a specific person explicitly agreed to do.

Output as a numbered list. Each item: [PERSON]: [TASK] by [DEADLINE or 'no deadline'].
Do not include items that were discussed but not assigned.
Do not add commentary or explanation."""
```

**Step 4: Add an example.**

```python
prompt_v4 = """You are a project manager's assistant. Your job is to extract
clear action items from meeting transcripts.

Extract all action items from the transcript below. An action item is a
task that a specific person explicitly agreed to do.

Output as a numbered list. Each item: [PERSON]: [TASK] by [DEADLINE or 'no deadline'].
Do not include items that were discussed but not assigned.
Do not add commentary or explanation.

Example output format:
1. Sam: Fix the login bug by Friday
2. Alex: Schedule client kickoff call by no deadline

Transcript:
"""
```

> **Real-world check:** You apply all 6 principles to a prompt, but outputs still vary 1 in 10 times. The format looks right 9/10 times but the 10th run omits the deadline field. What is the most likely remaining gap, and how would you close it?

The most likely gap is that the constraint is stated as a positive instruction ("include deadline") but not as a negative one ("never omit the deadline field"). The model treats missing information differently from prohibited information. Add: "If no deadline is mentioned, always write 'no deadline'. Never leave the deadline field blank." Explicit handling of the edge case eliminates the variance that only shows up under specific input conditions.

---

## USE IT

### PromptTemplate: Treating Prompts Like Code

Once you have a working prompt, you need to parameterize it so it can be reused with different inputs. The simplest version is an f-string. The production version is a class that validates inputs and renders the template.

```python
class PromptTemplate:
    """
    A simple prompt template that validates required variables before rendering.
    Treats prompts as parameterized code artifacts, not ad-hoc strings.
    """

    def __init__(self, template: str, required_vars: list[str]):
        self.template = template
        self.required_vars = required_vars

    def render(self, **kwargs) -> str:
        missing = [v for v in self.required_vars if v not in kwargs]
        if missing:
            raise ValueError(f"Missing required variables: {missing}")
        return self.template.format(**kwargs)


# Define the template once, reuse with different inputs
action_item_template = PromptTemplate(
    template="""You are a project manager's assistant. Extract action items from meeting transcripts.

An action item is a task that a specific person explicitly agreed to do.

Output as a numbered list. Format: [PERSON]: [TASK] by [DEADLINE or 'no deadline'].
Do not include discussed-but-unassigned items. Do not add commentary.

Example:
1. Sam: Fix the login bug by Friday
2. Alex: Schedule client call by no deadline

Transcript:
{transcript}

Tone: {tone}""",
    required_vars=["transcript", "tone"]
)

# Render and run
prompt = action_item_template.render(
    transcript=TRANSCRIPT,
    tone="direct and factual"
)

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=512,
    messages=[{"role": "user", "content": prompt}]
)
print(response.content[0].text)
```

The template approach gives you version control (templates are strings you can store), testability (render() is a pure function), and parameterization (swap inputs without touching the logic).

> **Perspective shift:** A colleague says "I just hardcode my prompts in the API call. Templates seem like over-engineering." When does this attitude start causing real problems in production?

It starts causing problems the moment you have more than one place the prompt is used, or more than one person who might modify it. Hardcoded prompts get copied and diverge silently. When a prompt needs to change (model behavior shifts, requirements change, a bug is found), you have to find every copy. Templates make the prompt a single source of truth with a defined interface. The "over-engineering" cost is 10 lines of code. The cost of not doing it is tracked through support tickets six months later.

---

## SHIP IT

The artifact this lesson produces is a prompt quality checklist. See `outputs/prompt-fundamentals-checklist.md`.

The checklist walks through all 6 principles with diagnostic questions for each. Use it during prompt authoring and code review to catch gaps before they become production bugs.

---

## EVALUATE IT

Prompt quality is measurable. The metric is output consistency: given the same task with different input data, do outputs follow the same structure every time?

**Consistency test.** Run your final prompt against 10 different meeting transcripts (or generate synthetic ones). Score each output: does it match the specified format? Does it include all required fields? A well-written prompt should hit the format correctly on 10/10 runs. If you're at 8/10, find the 2 failures and identify which principle they violate.

**Ablation test.** Take your best prompt and remove one principle at a time. Run each ablated version 5 times. Measure how much variance increases. This tells you which principles are doing the most work for your specific task. Common finding: output format and constraints account for most of the stability.

**New input stress test.** Give your prompt input that is significantly different from what you designed for: an unusually short transcript, a transcript with no clear assignees, a transcript in a different domain. Where does it break? The breakages reveal missing constraints or an over-specific task definition.

**Template rendering coverage.** Unit-test your PromptTemplate class: missing required variable raises ValueError, all variables present renders without error, rendered output contains the variable values at the right positions. Template bugs are logic bugs, not prompt bugs.
