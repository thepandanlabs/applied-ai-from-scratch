---
name: skill-structured-output
description: Generic extraction helper using tool_use as an output channel, with a sample invoice schema and validation pattern for production JSON extraction.
version: "1.0"
phase: "01"
lesson: "06"
tags: [structured-output, tool-use, json-extraction, pydantic, schema]
---

# Skill: Structured Output via Tool Use

Production pattern for extracting reliable JSON from a model using tool_use as the output channel. Valid JSON is guaranteed because the model is forced to call a tool rather than generate free text.

## When to Use

- Any extraction task where downstream code parses the model's output
- Data pipelines processing documents, emails, transcripts, or reports
- Any place where a JSON parse failure would corrupt data or crash a pipeline

## Core Pattern

```python
import anthropic

client = anthropic.Anthropic()
MODEL = "claude-3-5-haiku-20241022"


def extract(document: str, schema: dict, tool_name: str = "extract") -> dict:
    """
    Extract structured data from `document` using tool_use as output channel.
    Returns a dict matching `schema`. Raises ValueError if extraction fails.
    """
    tool = {
        "name": tool_name,
        "description": "Extract structured data from the provided document.",
        "input_schema": schema,
    }

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        tools=[tool],
        tool_choice={"type": "any"},   # force a tool call
        messages=[
            {
                "role": "user",
                "content": f"Extract all fields from this document:\n\n{document}",
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input   # already parsed JSON

    raise ValueError(
        f"Model did not call tool '{tool_name}'. "
        f"stop_reason={response.stop_reason}"
    )
```

## Example: Invoice Extraction

```python
INVOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor_name": {"type": "string"},
        "client_name": {"type": "string"},
        "invoice_number": {"type": "string"},
        "date": {"type": "string", "description": "YYYY-MM-DD format"},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["description", "amount"],
            },
        },
        "subtotal": {"type": "number"},
        "tax": {"type": "number"},
        "total": {"type": "number"},
    },
    "required": [
        "vendor_name", "client_name", "invoice_number", "date",
        "line_items", "subtotal", "tax", "total",
    ],
}

result = extract(invoice_text, INVOICE_SCHEMA, tool_name="extract_invoice")
print(result["total"])   # guaranteed to be a number
```

## Adding Pydantic Validation

Wrap `extract()` in a Pydantic model to get type coercion and field validation:

```python
from pydantic import BaseModel

class LineItem(BaseModel):
    description: str
    amount: float

class Invoice(BaseModel):
    vendor_name: str
    client_name: str
    invoice_number: str
    date: str
    line_items: list[LineItem]
    subtotal: float
    tax: float
    total: float

raw = extract(invoice_text, INVOICE_SCHEMA)
invoice = Invoice(**raw)   # raises ValidationError if schema mismatch
```

## Verifying Tool Was Called

```python
# Always check stop_reason in production monitoring
assert response.stop_reason == "tool_use", (
    f"Expected tool_use, got {response.stop_reason}"
)
```

## Schema Design Tips

- Use `"type": "number"` for all monetary amounts (never `"type": "string"`)
- Add `"description"` to every field: the model reads it
- For dates, write `"description": "YYYY-MM-DD format"` in the field description
- Use `"required"` to list every field you cannot afford to miss
- For optional fields, omit them from `"required"` rather than using nullable types
