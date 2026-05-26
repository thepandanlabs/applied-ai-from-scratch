"""
Lesson 01-08: Prompt Templates & Versioning
============================================
Demonstrates treating prompts as first-class versioned artifacts:

  - PromptTemplate: variable substitution + version metadata + fingerprint
  - PromptRegistry: lookup by name and version, drift detection
  - Compare against raw f-strings to show what breaks without structure
  - A/B test two prompt versions against the same input

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    python main.py
"""

import anthropic
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"


# ---------------------------------------------------------------------------
# PromptTemplate
# ---------------------------------------------------------------------------

@dataclass
class PromptTemplate:
    """
    A versioned, variable-substitutable prompt template.

    Fields:
        name        - Unique kebab-case identifier (e.g. 'ticket-classifier')
        version     - Semantic version string (e.g. '1.2')
        template    - Text with {variable} placeholders
        description - One-line description of what this prompt does
        variables   - Required variable names (auto-detected from template if omitted)
        author      - Who created or last modified this version
        created_at  - ISO 8601 timestamp (set automatically)
    """
    name: str
    version: str
    template: str
    description: str
    variables: list[str] = field(default_factory=list)
    author: str = "unknown"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self):
        # Auto-detect {variable} placeholders if not explicitly listed
        if not self.variables:
            found = re.findall(r"\{(\w+)\}", self.template)
            self.variables = sorted(set(found))

    def render(self, **kwargs) -> str:
        """
        Substitute variables into the template.

        Raises ValueError if a required variable is missing.
        Raises ValueError if an unexpected variable is provided.
        Returns the fully rendered prompt string.
        """
        missing = [v for v in self.variables if v not in kwargs]
        if missing:
            raise ValueError(
                f"Template '{self.name}' v{self.version} is missing required variables: "
                f"{missing}. Provided: {list(kwargs.keys())}"
            )

        extra = [k for k in kwargs if k not in self.variables]
        if extra:
            raise ValueError(
                f"Template '{self.name}' v{self.version} received unexpected variables: "
                f"{extra}. Expected: {self.variables}"
            )

        return self.template.format(**kwargs)

    def fingerprint(self) -> str:
        """
        12-char SHA-256 prefix of the template text.
        Use this to catch edits made without a version bump.
        """
        return hashlib.sha256(self.template.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict for storage or logging."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "variables": self.variables,
            "author": self.author,
            "created_at": self.created_at,
            "fingerprint": self.fingerprint(),
        }

    def __repr__(self) -> str:
        return f"PromptTemplate(name={self.name!r}, version={self.version!r}, fingerprint={self.fingerprint()!r})"


# ---------------------------------------------------------------------------
# PromptRegistry
# ---------------------------------------------------------------------------

class PromptRegistry:
    """
    In-memory registry for PromptTemplate instances.

    Key behaviors:
    - Templates are stored by (name, version) pair
    - Each name has a 'current' version pointer
    - Registering the same (name, version) with different content raises an error
    """

    def __init__(self):
        self._templates: dict[tuple[str, str], PromptTemplate] = {}
        self._current: dict[str, str] = {}  # name -> current version string

    def register(self, template: PromptTemplate, set_current: bool = True) -> None:
        """
        Add a template to the registry.

        Raises ValueError if (name, version) already exists with different content.
        Silently accepts re-registration with identical content (idempotent).
        """
        key = (template.name, template.version)

        if key in self._templates:
            existing = self._templates[key]
            if existing.fingerprint() != template.fingerprint():
                raise ValueError(
                    f"Conflict: '{template.name}' v{template.version} is already registered "
                    f"with fingerprint {existing.fingerprint()!r} but the new template has "
                    f"fingerprint {template.fingerprint()!r}. "
                    f"Bump the version to register a changed template."
                )
            return  # identical content: idempotent, no-op

        self._templates[key] = template
        if set_current:
            self._current[template.name] = template.version

    def get(self, name: str, version: str | None = None) -> PromptTemplate:
        """
        Retrieve a template by name and optional version.
        If version is None, returns the current version.
        """
        v = version or self._current.get(name)
        if v is None:
            raise KeyError(f"No template registered with name '{name}'")
        key = (name, v)
        if key not in self._templates:
            raise KeyError(f"Template '{name}' version '{v}' not found in registry")
        return self._templates[key]

    def render(self, name: str, version: str | None = None, **kwargs) -> str:
        """Look up a template and render it in one call."""
        return self.get(name, version).render(**kwargs)

    def list_versions(self, name: str) -> list[str]:
        """Return all registered versions for a given template name."""
        return sorted(v for (n, v) in self._templates if n == name)

    def current_version(self, name: str) -> str | None:
        """Return the current version string for a template, or None."""
        return self._current.get(name)

    def summary(self) -> None:
        """Print a summary of all registered templates."""
        names = sorted(set(n for (n, _) in self._templates))
        print(f"\nPrompt Registry ({len(self._templates)} templates across {len(names)} names)")
        print("-" * 60)
        for name in names:
            current = self._current.get(name, "none")
            versions = self.list_versions(name)
            t = self.get(name)
            print(f"  {name}")
            print(f"    Current: v{current} | All: {versions}")
            print(f"    Fingerprint: {t.fingerprint()} | Variables: {t.variables}")
            print(f"    Description: {t.description}")


# ---------------------------------------------------------------------------
# Demo prompts
# ---------------------------------------------------------------------------

def build_registry() -> PromptRegistry:
    """Build a registry with two ticket-classifier versions and one summarizer."""
    registry = PromptRegistry()

    registry.register(PromptTemplate(
        name="ticket-classifier",
        version="1.0",
        description="Classify a customer support ticket into one category.",
        template=(
            "You are a customer support classifier.\n"
            "Classify the following ticket into exactly one category.\n\n"
            "Ticket: {ticket_text}\n\n"
            "Categories: {categories}\n\n"
            "Respond with only the category name, nothing else."
        ),
        author="alice",
    ))

    registry.register(PromptTemplate(
        name="ticket-classifier",
        version="1.1",
        description="Classify a support ticket. Adds 'uncertain:' prefix for ambiguous cases.",
        template=(
            "You are a customer support classifier.\n"
            "Classify the following ticket into exactly one category.\n\n"
            "Ticket: {ticket_text}\n\n"
            "Categories: {categories}\n\n"
            "If the ticket clearly fits one category, respond with only the category name.\n"
            "If it is ambiguous, respond with 'uncertain: <best_guess>'."
        ),
        author="bob",
    ))

    registry.register(PromptTemplate(
        name="ticket-summarizer",
        version="1.0",
        description="Produce a one-sentence summary of a customer support ticket.",
        template=(
            "Summarize the following customer support ticket in exactly one sentence. "
            "Include the main problem and any urgency signals.\n\n"
            "Ticket: {ticket_text}"
        ),
        author="alice",
    ))

    return registry


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def call_model(prompt: str, max_tokens: int = 128) -> str:
    """Simple wrapper around the Anthropic messages API."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def classify_ticket(
    registry: PromptRegistry,
    ticket_text: str,
    version: str | None = None,
) -> dict:
    """
    Classify a ticket using the registry.
    Returns the classification result plus the metadata of the template used.
    """
    t = registry.get("ticket-classifier", version)
    prompt = t.render(
        ticket_text=ticket_text,
        categories="bug, billing, feature-request, account-access, general-question",
    )
    result = call_model(prompt, max_tokens=64)
    return {
        "result": result,
        "template": t.name,
        "version": t.version,
        "fingerprint": t.fingerprint(),
    }


# ---------------------------------------------------------------------------
# Demo: raw f-string vs. registry
# ---------------------------------------------------------------------------

def demo_fstring_problems() -> None:
    """Show what breaks with raw f-strings."""
    print("\n" + "=" * 65)
    print("DEMO 1: Raw f-String Problems")
    print("=" * 65)

    # Simulate what most teams start with
    PROMPT_V1 = "Classify this ticket: {ticket_text}\nCategories: {categories}"
    PROMPT_V2 = "Classify this ticket: {ticket_text}\nCategories: {categories}"
    # Someone accidentally made V2 identical to V1 - no way to tell
    # without diffing files and remembering which is which

    print("V1 and V2 look different but may be identical with no way to detect it.")
    print(f"V1 fingerprint (manual): {hashlib.sha256(PROMPT_V1.encode()).hexdigest()[:12]}")
    print(f"V2 fingerprint (manual): {hashlib.sha256(PROMPT_V2.encode()).hexdigest()[:12]}")
    print("\nProblem: version labels are just comments. The text is the truth.")
    print("If two devs edit 'V1' on different branches, you have two 'V1' prompts.")

    # Variable errors only appear at runtime
    try:
        result = PROMPT_V1.format(ticket_text="My login fails")
        # Oops: forgot categories
    except KeyError as e:
        print(f"\nRuntime KeyError (discovered in production): {e}")


def demo_registry(registry: PromptRegistry) -> None:
    """Show the registry providing versioning, fingerprinting, and variable safety."""
    print("\n" + "=" * 65)
    print("DEMO 2: Registry-Based Approach")
    print("=" * 65)

    registry.summary()

    # Attempt to register a duplicate version with different content
    print("\nTrying to register ticket-classifier v1.0 with different content...")
    try:
        registry.register(PromptTemplate(
            name="ticket-classifier",
            version="1.0",
            description="This has different content than the original v1.0.",
            template="Different template text {ticket_text} {categories}",
            author="charlie",
        ))
    except ValueError as e:
        print(f"Caught conflict: {e}")

    # Variable validation
    print("\nTrying to render with a missing variable...")
    try:
        registry.render("ticket-classifier", ticket_text="test")
    except ValueError as e:
        print(f"Caught missing variable: {e}")


def demo_ab_comparison(registry: PromptRegistry) -> None:
    """Run both versions on the same tickets and compare outputs."""
    print("\n" + "=" * 65)
    print("DEMO 3: A/B Comparison - v1.0 vs v1.1")
    print("=" * 65)

    test_tickets = [
        "My invoice shows a charge I do not recognize from last month.",
        "I cannot log in. Password reset emails are not arriving.",
        "Could you add dark mode to the app? It would really help.",
        "The app crashes when I try to export to CSV but only sometimes.",
    ]

    print(f"\n{'Ticket':<55} {'v1.0':<30} {'v1.1'}")
    print("-" * 115)

    for ticket in test_tickets:
        v1_result = classify_ticket(registry, ticket, version="1.0")
        v11_result = classify_ticket(registry, ticket, version="1.1")
        display = ticket[:52] + "..." if len(ticket) > 55 else ticket
        print(f"{display:<55} {v1_result['result']:<30} {v11_result['result']}")

    print(f"\nBoth versions using same registry, same variable substitution.")
    print(f"Difference is in how the model handles ambiguous cases.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Prompt Templates & Versioning")
    print("=" * 65)

    registry = build_registry()

    demo_fstring_problems()
    demo_registry(registry)
    demo_ab_comparison(registry)

    # Show registry export (what you would persist to a DB or config file)
    print("\n" + "=" * 65)
    print("Registry Export (JSON)")
    print("=" * 65)
    export = registry.export() if hasattr(registry, "export") else [
        t.to_dict() for t in [
            registry.get("ticket-classifier", "1.0"),
            registry.get("ticket-classifier", "1.1"),
            registry.get("ticket-summarizer", "1.0"),
        ]
    ]
    print(json.dumps(export, indent=2))
