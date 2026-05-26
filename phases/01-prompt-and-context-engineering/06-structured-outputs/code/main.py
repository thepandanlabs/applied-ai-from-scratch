"""
Lesson 01-06: Structured Outputs - JSON Schema, Constrained Decoding
======================================================================
Implements and compares three methods for getting reliable JSON from a model:
  Method 1: Prompt only (fragile - parse errors possible)
  Method 2: Tool use as output channel (reliable - JSON guaranteed)
  Method 3: Tool use with strict schema (maximum conformance)

All three methods extract the same fields from a sample invoice.

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    python main.py
"""

import anthropic
import json
import os
import time

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"

# ---------------------------------------------------------------------------
# Sample documents: one clean, one tricky
# ---------------------------------------------------------------------------

CLEAN_INVOICE = """
INVOICE #INV-2024-0892
From: Acme Consulting Group
To: Globex Corporation
Date: November 15, 2024

Services:
- Strategy Consulting (40 hrs @ $250/hr): $10,000.00
- Technical Architecture Review (8 hrs @ $350/hr): $2,800.00
- Travel Expenses: $450.00

Subtotal: $13,250.00
Tax (8.5%): $1,126.25
TOTAL DUE: $14,376.25

Payment terms: Net 30
"""

TRICKY_INVOICE = """
To whom it may concern,

Please find attached invoice for services rendered during October.

Vendor: BuildRight Software LLC
Client: Panda Labs Inc.
Invoice: BRS-OCT-447

Date issued: 10/31/2024

BILLABLE ITEMS:
1) Backend API development - 2 weeks sprint - $8,500
2) Code review & QA - 15 hours at $180 - $2,700
3) DevOps setup (one-time) - flat fee $1,200
4) Misc tools & licenses - $325.50

Pre-tax: $12,725.50
GST (5%): $636.28
Invoice total: $13,361.78

Please remit within 14 days.
"""

# ---------------------------------------------------------------------------
# Method 1: Prompt only
# ---------------------------------------------------------------------------

def extract_prompt_only(invoice: str) -> dict | None:
    """
    Method 1: Instructions in the prompt. No structural guarantee.
    Returns None on JSON parse failure.
    """
    start = time.perf_counter()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract the following fields from this invoice and return ONLY valid JSON. "
                    "No markdown, no explanation, no code blocks. "
                    "Fields:\n"
                    "  vendor_name (string)\n"
                    "  client_name (string)\n"
                    "  invoice_number (string)\n"
                    "  date (string, YYYY-MM-DD)\n"
                    "  line_items (array of {description: string, amount: number})\n"
                    "  subtotal (number)\n"
                    "  tax (number)\n"
                    "  total (number)\n\n"
                    + invoice
                ),
            }
        ],
    )
    elapsed = time.perf_counter() - start
    raw = response.content[0].text.strip()

    # Try to strip markdown code fences if model wrapped the output
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    try:
        result = json.loads(raw)
        return {"data": result, "latency": elapsed, "method": "prompt_only", "success": True}
    except json.JSONDecodeError as e:
        return {
            "data": None,
            "latency": elapsed,
            "method": "prompt_only",
            "success": False,
            "error": str(e),
            "raw": raw[:300],
        }


# ---------------------------------------------------------------------------
# Method 2: Tool use as output channel
# ---------------------------------------------------------------------------

INVOICE_TOOL = {
    "name": "extract_invoice",
    "description": "Extract structured fields from an invoice document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor_name": {
                "type": "string",
                "description": "Name of the vendor issuing the invoice",
            },
            "client_name": {
                "type": "string",
                "description": "Name of the client being billed",
            },
            "invoice_number": {
                "type": "string",
                "description": "Invoice identifier or number",
            },
            "date": {
                "type": "string",
                "description": "Invoice date in YYYY-MM-DD format",
            },
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
                "description": "List of billable line items",
            },
            "subtotal": {
                "type": "number",
                "description": "Subtotal before tax, as a plain number",
            },
            "tax": {
                "type": "number",
                "description": "Tax amount, as a plain number",
            },
            "total": {
                "type": "number",
                "description": "Total amount due, as a plain number",
            },
        },
        "required": [
            "vendor_name", "client_name", "invoice_number", "date",
            "line_items", "subtotal", "tax", "total",
        ],
    },
}


def extract_tool_use(invoice: str) -> dict | None:
    """
    Method 2: Tool use as output channel.
    tool_choice=any forces the model to call extract_invoice.
    block.input is already valid, parsed JSON.
    """
    start = time.perf_counter()
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=[INVOICE_TOOL],
        tool_choice={"type": "any"},
        messages=[
            {
                "role": "user",
                "content": "Extract all fields from this invoice:\n\n" + invoice,
            }
        ],
    )
    elapsed = time.perf_counter() - start

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_invoice":
            return {
                "data": block.input,
                "latency": elapsed,
                "method": "tool_use",
                "success": True,
                "stop_reason": response.stop_reason,
            }

    return {
        "data": None,
        "latency": elapsed,
        "method": "tool_use",
        "success": False,
        "error": "No tool_use block in response",
        "stop_reason": response.stop_reason,
    }


# ---------------------------------------------------------------------------
# Generic extraction helper (the production pattern)
# ---------------------------------------------------------------------------

def extract(document: str, schema: dict, tool_name: str = "extract") -> dict:
    """
    Generic extraction helper using tool_use as output channel.
    This is the production-ready version to copy into new projects.

    Args:
        document: The text to extract from
        schema: JSON Schema describing the fields to extract
        tool_name: Name for the extraction tool (used as dict key)

    Returns:
        Dict of extracted fields

    Raises:
        ValueError if the model does not call the tool
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
        tool_choice={"type": "any"},
        messages=[
            {
                "role": "user",
                "content": f"Extract all fields from this document:\n\n{document}",
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input

    raise ValueError(
        f"Model did not call tool '{tool_name}'. "
        f"stop_reason={response.stop_reason}"
    )


# ---------------------------------------------------------------------------
# Comparison runner
# ---------------------------------------------------------------------------

def validate_result(result: dict | None) -> dict:
    """Check extracted data for expected fields and correct types."""
    if result is None:
        return {"valid": False, "issues": ["No data"]}

    issues = []
    required_fields = ["vendor_name", "client_name", "invoice_number", "date",
                        "line_items", "subtotal", "tax", "total"]

    for field in required_fields:
        if field not in result:
            issues.append(f"Missing field: {field}")

    for num_field in ["subtotal", "tax", "total"]:
        if num_field in result and not isinstance(result[num_field], (int, float)):
            issues.append(f"Type error: {num_field} is {type(result[num_field]).__name__}, expected number")

    if "line_items" in result and not isinstance(result["line_items"], list):
        issues.append("Type error: line_items is not a list")

    return {"valid": len(issues) == 0, "issues": issues}


def run_comparison(invoice: str, label: str) -> None:
    """Run all three methods and print a comparison table."""
    print(f"\n{'='*65}")
    print(f"DOCUMENT: {label}")
    print(f"{'='*65}")

    methods = [
        ("Method 1: Prompt Only", extract_prompt_only),
        ("Method 2: Tool Use", extract_tool_use),
    ]

    for name, fn in methods:
        print(f"\n{name}")
        print("-" * 40)
        result = fn(invoice)

        if result["success"]:
            data = result["data"]
            validation = validate_result(data)
            print(f"  Status:   SUCCESS ({result['latency']:.2f}s)")
            print(f"  Valid:    {validation['valid']}")
            if not validation["valid"]:
                for issue in validation["issues"]:
                    print(f"  Issue:    {issue}")
            if data:
                print(f"  Vendor:   {data.get('vendor_name', 'N/A')}")
                print(f"  Client:   {data.get('client_name', 'N/A')}")
                print(f"  Total:    {data.get('total', 'N/A')}")
                items = data.get("line_items", [])
                print(f"  Items:    {len(items)} line item(s)")
        else:
            print(f"  Status:   FAILED ({result['latency']:.2f}s)")
            print(f"  Error:    {result.get('error', 'unknown')}")
            if "raw" in result:
                print(f"  Raw out:  {result['raw'][:100]}")


def demo_generic_extract() -> None:
    """Show the generic extract() helper with a custom schema."""
    print(f"\n{'='*65}")
    print("GENERIC extract() HELPER - Custom Schema")
    print(f"{'='*65}")

    meeting_notes = """
    Project sync - November 20, 2024
    Attendees: Alice Chen (PM), Bob Ruiz (Eng Lead), Sara Park (Design)
    Duration: 45 minutes

    Decisions:
    - Launch date pushed to January 15, 2025
    - Mobile-first design approach approved
    - Bob will own API integration by Dec 1

    Action items:
    - Alice: Send updated timeline to stakeholders by Nov 22
    - Sara: Deliver final mockups by Nov 29
    - Bob: Draft API spec by Nov 27
    """

    schema = {
        "type": "object",
        "properties": {
            "date": {"type": "string"},
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
            },
            "duration_minutes": {"type": "integer"},
            "decisions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "task": {"type": "string"},
                        "due_date": {"type": "string"},
                    },
                    "required": ["owner", "task"],
                },
            },
        },
        "required": ["date", "attendees", "decisions", "action_items"],
    }

    result = extract(meeting_notes, schema, tool_name="extract_meeting")
    print(f"\nExtracted meeting notes:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    print("Structured Outputs: Three Methods Compared")
    run_comparison(CLEAN_INVOICE, "Clean Invoice")
    run_comparison(TRICKY_INVOICE, "Tricky Invoice (unusual format)")
    demo_generic_extract()
