---
name: skill-prompt-template-system
description: PromptTemplate and PromptRegistry classes for versioning, variable substitution, and fingerprint-based drift detection of production prompts.
version: "1.0"
phase: "01"
lesson: "08"
tags: [prompt-management, versioning, templates, registry, prompt-engineering]
---

# Skill: Prompt Template System

A `PromptTemplate` and `PromptRegistry` for treating prompts as first-class versioned artifacts. Provides variable substitution, version history, fingerprint-based drift detection, and a single source of truth for every prompt in your system.

## When to Use

- Any system with more than 3 prompts, or prompts shared across services
- When you need to A/B test prompt versions against an eval set
- When you need to answer "what prompt was running when this regression happened?"

## PromptTemplate

```python
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PromptTemplate:
    name: str          # kebab-case, e.g. 'ticket-classifier'
    version: str       # semantic, e.g. '1.2'
    template: str      # text with {variable} placeholders
    description: str   # one-line description
    variables: list[str] = field(default_factory=list)
    author: str = "unknown"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self):
        if not self.variables:
            found = re.findall(r"\{(\w+)\}", self.template)
            self.variables = sorted(set(found))

    def render(self, **kwargs) -> str:
        missing = [v for v in self.variables if v not in kwargs]
        if missing:
            raise ValueError(f"Missing variables for '{self.name}': {missing}")
        extra = [k for k in kwargs if k not in self.variables]
        if extra:
            raise ValueError(f"Unexpected variables for '{self.name}': {extra}")
        return self.template.format(**kwargs)

    def fingerprint(self) -> str:
        return hashlib.sha256(self.template.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "variables": self.variables,
            "author": self.author,
            "created_at": self.created_at,
            "fingerprint": self.fingerprint(),
        }
```

## PromptRegistry

```python
class PromptRegistry:
    def __init__(self):
        self._templates: dict[tuple[str, str], PromptTemplate] = {}
        self._current: dict[str, str] = {}

    def register(self, template: PromptTemplate, set_current: bool = True) -> None:
        key = (template.name, template.version)
        if key in self._templates:
            existing = self._templates[key]
            if existing.fingerprint() != template.fingerprint():
                raise ValueError(
                    f"'{template.name}' v{template.version} already registered with "
                    f"different content. Bump the version number."
                )
            return  # idempotent: same content already registered
        self._templates[key] = template
        if set_current:
            self._current[template.name] = template.version

    def get(self, name: str, version: str | None = None) -> PromptTemplate:
        v = version or self._current.get(name)
        if not v:
            raise KeyError(f"No template named '{name}'")
        key = (name, v)
        if key not in self._templates:
            raise KeyError(f"Template '{name}' v'{v}' not found")
        return self._templates[key]

    def render(self, name: str, version: str | None = None, **kwargs) -> str:
        return self.get(name, version).render(**kwargs)

    def list_versions(self, name: str) -> list[str]:
        return sorted(v for (n, v) in self._templates if n == name)

    def current_version(self, name: str) -> str | None:
        return self._current.get(name)
```

## Usage Pattern

```python
registry = PromptRegistry()

registry.register(PromptTemplate(
    name="ticket-classifier",
    version="1.1",
    description="Classify support tickets, marks ambiguous results.",
    template=(
        "Classify this ticket into one category.\n\n"
        "Ticket: {ticket_text}\n\n"
        "Categories: {categories}\n\n"
        "If ambiguous, respond 'uncertain: <best_guess>'."
    ),
    author="alice",
))

# Render using current version
prompt = registry.render(
    "ticket-classifier",
    ticket_text="My invoice is wrong",
    categories="bug, billing, feature-request, account-access",
)

# Always log this metadata with your API call
t = registry.get("ticket-classifier")
print(f"Using: {t.name} v{t.version} fingerprint={t.fingerprint()}")
```

## CI Drift Check

Add to your test suite to catch template edits without version bumps:

```python
EXPECTED_FINGERPRINTS = {
    ("ticket-classifier", "1.1"): "a3f9c2d10b44",
    ("ticket-summarizer", "1.0"): "b87e1c3a9f20",
}

def test_no_prompt_drift(registry: PromptRegistry):
    for (name, version), expected_fp in EXPECTED_FINGERPRINTS.items():
        t = registry.get(name, version)
        assert t.fingerprint() == expected_fp, (
            f"{name} v{version} fingerprint changed without a version bump. "
            f"Expected {expected_fp}, got {t.fingerprint()}."
        )
```

## What to Log With Every API Call

```python
import logging

logger = logging.getLogger(__name__)

def call_with_logging(registry, name, **kwargs):
    t = registry.get(name)
    prompt = t.render(**kwargs)
    response = client.messages.create(...)
    logger.info({
        "prompt_name": t.name,
        "prompt_version": t.version,
        "prompt_fingerprint": t.fingerprint(),
        "input_tokens": response.usage.input_tokens,
    })
    return response
```
