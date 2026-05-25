"""
Lesson 04-03: Pattern: Prompt Chaining
Phase 04: Agents - Patterns That Survive Production

A 3-step prompt chain with a gate between steps 1 and 2.
Each step is a separate client.messages.create() call.
Output of step N is input to step N+1.

Steps:
  1. Extract key facts from a source article
  2. [GATE] Check if extraction found enough data
  3. Draft a knowledge base section from the facts
  4. Polish the prose to match house style
"""

import anthropic
import json
import time
from dataclasses import dataclass
from typing import Callable, Any

client = anthropic.Anthropic()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChainError:
    """Returned by a gate when input quality is insufficient."""
    step: str
    reason: str

    def __str__(self) -> str:
        return f"Chain halted at '{self.step}': {self.reason}"


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

def step_extract_facts(article: str) -> list[str]:
    """
    Step 1: Extract specific, verifiable facts from the article.
    Returns a list of fact strings. Returns empty list if parsing fails.
    """
    prompt = f"""Extract the key facts from this article. Return a JSON array of strings.
Each string is one specific, verifiable fact stated in the article.
Do not include vague themes, opinions, or inferences.
Include between 3 and 8 facts. Return only the JSON array, no explanation or markdown.

Article:
{article}"""

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except (json.JSONDecodeError, IndexError, ValueError):
        return []


def gate_check_extraction(facts: list[str]) -> ChainError | None:
    """
    Gate between step 1 and step 2.
    Returns ChainError if extraction is insufficient. Returns None if it passes.

    Checks:
    - At least 3 facts found
    - At least 3 facts are substantive (>20 characters)
    """
    if len(facts) < 3:
        return ChainError(
            "gate_after_extract",
            f"Insufficient extraction: {len(facts)} facts found, need at least 3. "
            "Source article may lack substantive content."
        )

    substantive = [f for f in facts if isinstance(f, str) and len(f.strip()) > 20]
    if len(substantive) < 3:
        return ChainError(
            "gate_after_extract",
            f"Extraction quality too low: {len(substantive)} substantive facts found. "
            "Facts appear vague, empty, or too short to be useful."
        )

    return None  # Gate passes


def step_draft_section(facts: list[str], topic: str) -> str:
    """
    Step 2: Write a draft knowledge base section from extracted facts.
    Input is ONLY the extracted facts - not the original article.
    This enforces grounding: the draft can only use what was explicitly extracted.
    """
    facts_text = "\n".join(f"- {f}" for f in facts)
    prompt = f"""Write a knowledge base section about '{topic}' using ONLY these facts:

{facts_text}

Requirements:
- 2-3 paragraphs
- Professional, neutral tone
- Do not add any information not explicitly listed in the facts above
- Do not use bullet points in the output
- Do not reference the source article or the fact list directly"""

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


def step_polish_prose(draft: str) -> str:
    """
    Step 3: Polish the draft to match house style.
    Input is ONLY the draft - not the facts or original article.
    The editor's job is prose quality, not content decisions.
    """
    prompt = f"""Polish this text to professional knowledge base style.

Rules:
- Use active voice where possible
- Remove filler phrases: "it is worth noting", "it should be mentioned", "in conclusion", "overall"
- Tighten sentences without losing meaning
- Do not add new information
- Do not change the facts
- Keep the same paragraph structure

Text to polish:
{draft}"""

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Raw chain orchestration (no class)
# ---------------------------------------------------------------------------

def run_chain_raw(article: str, topic: str, verbose: bool = True) -> str | ChainError:
    """
    Run the 3-step chain with gate. Each step is a separate API call.
    Returns polished section on success, ChainError on gate failure.
    """
    if verbose:
        print("[1/3] Extracting facts...")
    facts = step_extract_facts(article)
    if verbose:
        print(f"      Found {len(facts)} facts: {facts[:2]}{'...' if len(facts) > 2 else ''}")

    error = gate_check_extraction(facts)
    if error:
        if verbose:
            print(f"      GATE FAILED: {error}")
        return error
    if verbose:
        print("      Gate passed.")

    if verbose:
        print("[2/3] Drafting section...")
    draft = step_draft_section(facts, topic)
    if verbose:
        print(f"      Draft: {len(draft)} chars")

    if verbose:
        print("[3/3] Polishing prose...")
    polished = step_polish_prose(draft)
    if verbose:
        print(f"      Polished: {len(polished)} chars")

    return polished


# ---------------------------------------------------------------------------
# Chain class with retry logic
# ---------------------------------------------------------------------------

class Step:
    def __init__(self, name: str, fn: Callable, retries: int = 0, is_gate: bool = False):
        self.name = name
        self.fn = fn
        self.retries = retries
        self.is_gate = is_gate


class Chain:
    """
    A composable prompt chain with per-step retry logic and gate support.
    Each step receives the output of the previous step as its input.
    Gates receive the current value and return None (pass) or ChainError (fail).
    """
    def __init__(self):
        self._steps: list[Step] = []

    def add_step(self, name: str, fn: Callable, retries: int = 0) -> "Chain":
        self._steps.append(Step(name, fn, retries=retries))
        return self

    def add_gate(self, name: str, fn: Callable) -> "Chain":
        self._steps.append(Step(name, fn, is_gate=True))
        return self

    def run(self, initial_input: Any) -> Any | ChainError:
        value = initial_input

        for step in self._steps:
            attempt = 0
            last_error = None

            while attempt <= step.retries:
                try:
                    result = step.fn(value)

                    if step.is_gate:
                        if result is not None:  # Gate returned a ChainError
                            return result
                        break  # Gate passed, value unchanged

                    value = result
                    break  # Success

                except Exception as e:
                    last_error = e
                    attempt += 1
                    if attempt <= step.retries:
                        wait = 2 ** attempt
                        print(f"  [retry {attempt}/{step.retries}] '{step.name}' failed: {e}. Retrying in {wait}s...")
                        time.sleep(wait)

            else:
                return ChainError(
                    step.name,
                    f"All {step.retries + 1} attempts failed. Last error: {last_error}"
                )

        return value


def build_content_chain(article: str, topic: str) -> str | ChainError:
    """
    Same pipeline as run_chain_raw, but using the Chain class.
    Note: lambda wrappers handle type-bridging between steps.
    """
    chain = (
        Chain()
        .add_step("extract_facts",  lambda x: step_extract_facts(x),            retries=1)
        .add_gate("quality_gate",                gate_check_extraction)
        .add_step("draft_section",  lambda x: step_draft_section(x, topic),      retries=1)
        .add_step("polish_prose",               step_polish_prose,                retries=0)
    )
    return chain.run(article)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

GOOD_ARTICLE = """
The James Webb Space Telescope (JWST) launched on December 25, 2021, after more than
20 years of development. The telescope cost approximately $10 billion and is operated
jointly by NASA, the European Space Agency, and the Canadian Space Agency.

JWST is positioned at the second Lagrange point (L2), approximately 1.5 million
kilometers from Earth. Its primary mirror is 6.5 meters in diameter, composed of
18 hexagonal gold-plated beryllium segments. The telescope observes primarily in
the infrared spectrum, which allows it to see through dust clouds and observe the
early universe.

In its first year of operation, JWST produced images of the Carina Nebula, the
Stephan's Quintet galaxy group, and the atmosphere of exoplanet WASP-96b. Scientists
used JWST data to confirm the presence of carbon dioxide in an exoplanet atmosphere
for the first time.
"""

THIN_ARTICLE = """
Space exploration is interesting. Scientists learn things from telescopes.
The universe is big and there are many things to discover.
"""

if __name__ == "__main__":
    print("=" * 60)
    print("RAW CHAIN - Good article (should pass gate)")
    print("=" * 60)
    result = run_chain_raw(GOOD_ARTICLE, "James Webb Space Telescope")
    if isinstance(result, ChainError):
        print(f"Error: {result}")
    else:
        print(f"\nFinal output:\n{result}")

    print("\n" + "=" * 60)
    print("RAW CHAIN - Thin article (should fail gate)")
    print("=" * 60)
    result = run_chain_raw(THIN_ARTICLE, "Space Exploration")
    if isinstance(result, ChainError):
        print(f"Gate correctly rejected: {result}")
    else:
        print(f"Warning: gate passed when it should have failed.\n{result}")

    print("\n" + "=" * 60)
    print("CHAIN CLASS - Good article with retry support")
    print("=" * 60)
    result = build_content_chain(GOOD_ARTICLE, "James Webb Space Telescope")
    if isinstance(result, ChainError):
        print(f"Error: {result}")
    else:
        print(f"Final output ({len(result)} chars):\n{result[:300]}...")
