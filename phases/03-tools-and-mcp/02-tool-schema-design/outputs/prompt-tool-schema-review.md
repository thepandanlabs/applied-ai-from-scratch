---
name: prompt-tool-schema-review
description: Prompt that reviews a tool schema against the 5 rules of good schema design and returns structured improvement suggestions
version: "1.0"
phase: "03"
lesson: "02"
tags: [tools, schema-design, code-review, prompt, agent-computer-interface]
---

# Tool Schema Review Prompt

Feed this prompt to Claude or GPT-4 along with a tool schema JSON. It returns a structured review covering all 5 schema design rules, with specific rewrites for every problem found. Use it in code review before merging new tool schemas to production.

## System Prompt

```
You are an expert reviewer of LLM tool schemas (also called function definitions or tool definitions).

You will be given a JSON tool schema. Your job is to review it against the 5 rules of good tool schema design and return a structured report with specific, actionable rewrites.

The 5 rules:
1. ONE TOOL, ONE PURPOSE: The tool name and description should map to a single, clear verb-action. If the tool does more than one thing, flag it.
2. NATURAL-LANGUAGE PARAMETER NAMES: Parameter names should match the words a user or LLM would naturally use (e.g. 'customer_id' not 'cid', 'query' not 'q', 'max_results' not 'n'). Flag abbreviated or cryptic names.
3. REQUIRED vs OPTIONAL: Only fields that the tool cannot function without should be in 'required'. Optional fields must have default values documented in their description. Flag required fields that should be optional.
4. ENUM CONSTRAINTS: Any string parameter that accepts only a fixed set of values must use 'enum'. A string without 'enum' when values are categorical is a schema defect. Flag missing enums.
5. DESCRIPTIONS WITH EXAMPLES: Every parameter description must explain what the field does AND give at least one concrete example value. 'type: string, description: "query"' is not acceptable. Flag descriptions that lack examples or are just type names.

Respond ONLY with valid JSON in this exact format:
{
  "tool_name": "...",
  "overall_quality": "poor | fair | good | excellent",
  "first_call_success_estimate": "low | medium | high",
  "findings": [
    {
      "rule": 1,
      "severity": "HIGH | MEDIUM | LOW",
      "field": "parameter_name or 'tool_description' or 'tool_name'",
      "problem": "one sentence describing the problem",
      "rewrite": "the exact replacement text or JSON snippet"
    }
  ],
  "rewritten_schema": { ... }
}

Rules for the rewrite:
- Include EVERY finding, even LOW severity ones.
- The 'rewrite' field must be usable as a drop-in replacement: an exact string for descriptions, an exact JSON snippet for schema changes.
- 'rewritten_schema' must be a complete, corrected version of the input schema with all findings applied.
- If the schema is already excellent, return findings: [] and explain why in an 'overall_notes' field.
```

## Usage

### Python

```python
import anthropic
import json

client = anthropic.Anthropic()

REVIEW_SYSTEM_PROMPT = """..."""  # paste system prompt above

def review_tool_schema(schema: dict) -> dict:
    """
    Review a tool schema against the 5 design rules.
    Returns a structured report with findings and a rewritten schema.
    """
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=2048,
        system=REVIEW_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Review this tool schema:\n\n```json\n{json.dumps(schema, indent=2)}\n```"
        }],
    )

    return json.loads(response.content[0].text)


# Example: review a bad schema
bad_schema = {
    "name": "search",
    "description": "search products",
    "input_schema": {
        "type": "object",
        "properties": {
            "q":    {"type": "string"},
            "n":    {"type": "integer"},
            "sort": {"type": "string"},
            "f":    {"type": "string"},
        },
        "required": ["q", "n", "sort", "f"],
    }
}

report = review_tool_schema(bad_schema)
print(f"Quality: {report['overall_quality']}")
print(f"First-call success: {report['first_call_success_estimate']}")
print(f"Findings: {len(report['findings'])}")
for f in report["findings"]:
    print(f"  [{f['severity']}] Rule {f['rule']} - {f['field']}: {f['problem']}")
print("\nRewritten schema:")
print(json.dumps(report["rewritten_schema"], indent=2))
```

### In CI (GitHub Actions snippet)

```yaml
- name: Review tool schemas
  run: |
    python scripts/review_schemas.py --schemas tools/*.json --fail-on HIGH
```

```python
# scripts/review_schemas.py
import sys
import json
import glob
import argparse
from review_prompt import review_tool_schema  # the function above

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schemas", nargs="+")
    parser.add_argument("--fail-on", choices=["HIGH", "MEDIUM", "LOW"], default="HIGH")
    args = parser.parse_args()

    exit_code = 0
    for path in args.schemas:
        with open(path) as f:
            schema = json.load(f)
        report = review_tool_schema(schema)
        high_findings = [f for f in report["findings"] if f["severity"] == args.fail_on]
        if high_findings:
            print(f"FAIL: {path} has {len(high_findings)} {args.fail_on} severity finding(s)")
            exit_code = 1

    sys.exit(exit_code)
```

## Severity Definitions

- **HIGH**: Will cause incorrect or failed tool calls in production. Fix before merge.
  - Abbreviated parameter names that conflict with natural language
  - Missing required fields or extra required fields that should be optional
  - Categorical string parameters without enum constraints
- **MEDIUM**: Will cause degraded tool call quality. Fix before production launch.
  - Descriptions that name the type but give no example
  - Ambiguous tool descriptions that overlap with another tool
  - Optional parameters with no documented default value
- **LOW**: Best practice improvements. Fix when convenient.
  - Minor description clarity improvements
  - Parameter ordering (required before optional)
  - Redundant descriptions that restate the field name

## Example Output

Input schema: the bad "search" schema above

```json
{
  "tool_name": "search",
  "overall_quality": "poor",
  "first_call_success_estimate": "low",
  "findings": [
    {
      "rule": 1,
      "severity": "HIGH",
      "field": "tool_name",
      "problem": "Tool name 'search' is a generic verb without a noun. The LLM cannot distinguish it from other search tools.",
      "rewrite": "search_products"
    },
    {
      "rule": 2,
      "severity": "HIGH",
      "field": "q",
      "problem": "Parameter name 'q' is an abbreviation. The LLM may not map the user's words to this parameter reliably.",
      "rewrite": "query"
    },
    {
      "rule": 5,
      "severity": "HIGH",
      "field": "q",
      "problem": "Description is missing. The LLM has no signal for what format or content to put in this field.",
      "rewrite": "Natural-language search query. Examples: 'blue running shoes', 'waterproof jacket under $200'."
    }
  ]
}
```
