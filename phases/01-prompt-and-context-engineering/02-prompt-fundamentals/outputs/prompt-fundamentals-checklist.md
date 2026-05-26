---
name: prompt-fundamentals-checklist
description: Six-principle checklist for authoring and reviewing prompts in production systems
version: "1.0"
phase: "01"
lesson: "02"
tags: [prompt-engineering, checklist, quality, consistency, templates]
---

# Prompt Fundamentals Checklist

Use this checklist when writing a new prompt or reviewing an existing one. Each principle has a diagnostic question. If you answer "no" or "not sure," fix it before shipping.

## The 6 Principles

### 1. Task Definition

**Question:** Can someone unfamiliar with your system read this prompt and know exactly what the model is supposed to produce?

- [ ] The task is specific, not generic ("summarize in 3 bullets" not "summarize")
- [ ] Success is defined: what does a correct output look like?
- [ ] The task scope is bounded: what is explicitly in-scope vs. out-of-scope?

**Red flag:** The task instruction could apply to multiple different outputs. If "summarize" could mean 1 sentence or 3 paragraphs, it's under-specified.

---

### 2. Role / Persona

**Question:** Is the model given a role that activates relevant knowledge and sets an implicit quality bar?

- [ ] The role is specific to the task ("You are a code reviewer" not "You are an assistant")
- [ ] The role aligns with the expected output quality and audience
- [ ] The role does not conflict with constraints elsewhere in the prompt

**Red flag:** No system prompt or role, or a generic "You are a helpful assistant" when the task is specialized.

---

### 3. Output Format

**Question:** Is the expected output structure fully specified?

- [ ] Format is named: JSON, markdown, numbered list, prose, etc.
- [ ] Length is bounded or specified: "exactly 3 bullets," "under 100 words," "1-2 sentences"
- [ ] Required fields or sections are listed explicitly
- [ ] Structural edge cases are handled: "if no deadline, write 'no deadline'"

**Red flag:** The output format is implied but not stated. "List the action items" implies a list but does not specify numbered vs. bullets, one line vs. multiple, with or without assignees.

---

### 4. Examples

**Question:** Is there at least one example of a correct output?

- [ ] At least one example of expected output is included
- [ ] The example covers the most important structural properties (format, length, field names)
- [ ] The example is realistic (matches actual input complexity)

**Red flag:** The format is described in words only. A single concrete example is almost always more reliable than a paragraph of description.

---

### 5. Constraints

**Question:** Are negative constraints explicit?

- [ ] Common failure modes are addressed with "do not" instructions
- [ ] Edge cases have explicit handling, not implicit expectations
- [ ] Output should not contain: disclaimers, caveats, apologies, marketing language (whichever apply)
- [ ] The model is told what to do when information is missing, ambiguous, or out of scope

**Red flag:** All instructions are positive ("do X") with no negative constraints ("do not Y"). Models default to helpful behaviors that include caveats, hedges, and extra context. These need to be explicitly suppressed when they're unwanted.

---

### 6. Tone

**Question:** Is the expected tone specified?

- [ ] Formality level is stated: formal, professional, casual, direct
- [ ] Assumed reader expertise is set: "general audience," "senior engineer," "non-technical stakeholder"
- [ ] Vocabulary constraints are noted if relevant: "use plain language," "avoid jargon"

**Red flag:** Tone is left to default model behavior. Defaults vary across tasks and can produce inconsistent register.

---

## Quick Scoring

Score each principle 0 (missing), 1 (partial), or 2 (complete):

| Principle | Score |
|-----------|-------|
| Task Definition | /2 |
| Role / Persona | /2 |
| Output Format | /2 |
| Examples | /2 |
| Constraints | /2 |
| Tone | /2 |
| **Total** | **/12** |

A score of 10+ is production-ready. Below 8: identify the lowest-scoring principles and fix them before shipping.

---

## PromptTemplate Snippet

```python
class PromptTemplate:
    def __init__(self, template: str, required_vars: list[str], name: str = ""):
        self.template = template
        self.required_vars = required_vars
        self.name = name

    def render(self, **kwargs) -> str:
        missing = [v for v in self.required_vars if v not in kwargs]
        if missing:
            raise ValueError(f"Missing required variables: {missing}")
        return self.template.format(**kwargs)
```

**Usage:**
```python
template = PromptTemplate(
    template="You are a {role}. {task}\n\nInput:\n{input}",
    required_vars=["role", "task", "input"],
    name="generic-task"
)
prompt = template.render(role="code reviewer", task="Review this function.", input=code)
```

---

## Prompt Review Checklist (Code Review)

When reviewing a prompt in a PR:

- [ ] Is the prompt stored as a named constant or template (not hardcoded inline)?
- [ ] Are all 6 principles present at >= partial?
- [ ] Are variable interpolations validated before rendering?
- [ ] Is the prompt tested against at least 5 representative inputs?
- [ ] Is output format checked programmatically (not just visually reviewed)?
