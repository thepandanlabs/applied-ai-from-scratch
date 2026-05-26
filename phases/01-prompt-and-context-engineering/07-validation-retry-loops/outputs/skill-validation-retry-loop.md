---
name: skill-validation-retry-loop
description: validated_completion function that retries structured extraction with Pydantic validation errors as feedback, achieving 2-3x higher success rate than blind retry.
version: "1.0"
phase: "01"
lesson: "07"
tags: [validation, retry, pydantic, structured-output, extraction, error-feedback]
---

# Skill: Validation + Retry Loop

A `validated_completion` function for structured extraction. Validates model output with Pydantic and, on failure, feeds the exact error back to the model for targeted correction. Significantly more effective than blind retry.

## When to Use

- Any extraction pipeline where the model's output must satisfy type or business constraints
- After Lesson 06 (Structured Outputs) - use this on top of the tool_use pattern
- When you see validation errors in production that retrying the same prompt does not fix

## Setup

```python
import anthropic
from pydantic import BaseModel
client = anthropic.Anthropic()
MODEL = "claude-3-5-haiku-20241022"
```

## Core Pattern

```python
def validated_completion(
    document: str,
    tool: dict,
    model_class: type[BaseModel],
    max_retries: int = 3,
) -> BaseModel | None:
    """
    Extract structured data, validate with Pydantic, and retry with
    error feedback on failure.

    Returns a validated model instance, or None if all retries fail.
    """
    messages = [
        {
            "role": "user",
            "content": f"Extract structured data from this document:\n\n{document}",
        }
    ]

    for attempt in range(1, max_retries + 1):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=[tool],
            tool_choice={"type": "any"},
            messages=messages,
        )

        extracted = None
        for block in response.content:
            if block.type == "tool_use":
                extracted = block.input
                break

        if extracted is None:
            return None  # model did not call the tool

        try:
            return model_class(**extracted)  # validation passes
        except Exception as e:
            if attempt == max_retries:
                return None  # exhausted retries

            # Feed the error back for targeted correction
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": (
                    f"Validation failed:\n\n{e}\n\n"
                    "Fix only the failing fields and call the tool again."
                ),
            })

    return None
```

## Example: With Pydantic Constraints

```python
from pydantic import BaseModel, field_validator
from typing import Literal

class RiskFinding(BaseModel):
    title: str
    severity: Literal["low", "medium", "high", "critical"]
    likelihood: float

    @field_validator("likelihood")
    @classmethod
    def likelihood_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(
                f"likelihood must be 0.0-1.0, got {v}. "
                "Write 0.75 not 75."
            )
        return v

class Assessment(BaseModel):
    asset: str
    risk_score: float  # 0.0 to 1.0
    findings: list[RiskFinding]
    action: Literal["monitor", "remediate", "escalate", "accept"]

# Define the tool matching the Pydantic model
ASSESSMENT_TOOL = {
    "name": "extract_assessment",
    "description": "Extract a structured risk assessment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "asset": {"type": "string"},
            "risk_score": {"type": "number", "description": "0.0 to 1.0"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "likelihood": {"type": "number", "description": "0.0 to 1.0"},
                    },
                    "required": ["title", "severity", "likelihood"],
                },
            },
            "action": {"type": "string", "enum": ["monitor", "remediate", "escalate", "accept"]},
        },
        "required": ["asset", "risk_score", "findings", "action"],
    },
}

result = validated_completion(
    document=report_text,
    tool=ASSESSMENT_TOOL,
    model_class=Assessment,
    max_retries=3,
)
```

## Alternative: instructor Library

```python
import instructor
from anthropic import Anthropic

patched = instructor.from_anthropic(Anthropic())

result = patched.messages.create(
    model=MODEL,
    max_tokens=1024,
    max_retries=3,
    response_model=Assessment,
    messages=[{"role": "user", "content": f"Extract: {document}"}],
)
```

instructor does the same thing as `validated_completion` with less boilerplate. Use instructor for greenfield work; use the manual implementation when you need control over the retry messages or fallback behavior.

## Fallback Strategies

When all retries are exhausted, choose one:

```python
result = validated_completion(doc, tool, MyModel)

if result is None:
    # Option 1: Raise - stops the pipeline, goes to error tracker
    raise ExtractionError(f"Extraction failed after {max_retries} retries")

    # Option 2: Dead-letter queue - save for manual review
    dead_letter_queue.append({"doc": doc, "timestamp": now()})

    # Option 3: Partial result - return unvalidated data flagged
    return {"data": None, "status": "extraction_failed", "doc_id": doc_id}
```

Never silently drop the failure. Always log and alert when the fallback count exceeds 1% of total extractions.
