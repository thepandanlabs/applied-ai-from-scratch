"""
Lesson 03-02: Tool Schema Design
Demonstrate schema quality progression (bad -> better -> good) and tool call validation.

Run: python main.py
Run validation demo: python main.py --validate
Run Pydantic demo:   python main.py --pydantic
"""

import argparse
import json
from typing import Any, Optional

import anthropic

# ---------------------------------------------------------------------------
# Three versions of the same tool schema (bad -> better -> good)
# ---------------------------------------------------------------------------

# Version 1: Bad - abbreviated names, no descriptions, all required, no constraints
SCHEMA_V1 = {
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
    },
}

# Version 2: Better - natural names, basic descriptions, fewer required
SCHEMA_V2 = {
    "name": "search_products",
    "description": "Search the product catalog.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results. Default 10.",
            },
            "sort_by": {
                "type": "string",
                "description": "Sort order. Options: relevance, price_asc, price_desc, newest.",
            },
            "filters": {
                "type": "object",
                "description": "Optional filters.",
            },
        },
        "required": ["query"],
    },
}

# Version 3: Good - enum constraints, examples in descriptions, sensible defaults
SCHEMA_V3 = {
    "name": "search_products",
    "description": (
        "Search the product catalog by keyword. "
        "Use this when the user wants to find, browse, or look up products. "
        "Do not use for order lookups or account information."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Natural-language search query. "
                    "Examples: 'blue running shoes', 'waterproof jacket under $200', 'size 10 boots'."
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum items to return. Default: 10. Range: 1 to 50.",
            },
            "sort_by": {
                "type": "string",
                "enum": ["relevance", "price_asc", "price_desc", "newest"],
                "description": (
                    "Sort order. Default: 'relevance'. "
                    "Use 'price_asc' for cheapest-first, 'price_desc' for most-expensive-first, "
                    "'newest' for recently added items."
                ),
            },
            "filters": {
                "type": "object",
                "description": (
                    "Optional filter criteria. All keys optional. "
                    "Example: {\"min_price\": 20, \"max_price\": 150, \"category\": \"footwear\", \"in_stock\": true}."
                ),
                "properties": {
                    "min_price": {"type": "number",  "description": "Minimum price in USD."},
                    "max_price": {"type": "number",  "description": "Maximum price in USD."},
                    "category":  {"type": "string",  "description": "Product category, e.g. 'footwear'."},
                    "in_stock":  {"type": "boolean", "description": "If true, return only in-stock items."},
                },
            },
        },
        "required": ["query"],
    },
}

# ---------------------------------------------------------------------------
# Stub function
# ---------------------------------------------------------------------------

def search_products(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
    filters: Optional[dict] = None,
) -> dict:
    """Stub: returns fake product search results."""
    products = [
        {"id": "P001", "name": "Blue Trail Runners", "price": 89.99,  "in_stock": True,  "category": "footwear"},
        {"id": "P002", "name": "Blue Road Runners",  "price": 119.99, "in_stock": True,  "category": "footwear"},
        {"id": "P003", "name": "Blue Casual Sneakers","price": 59.99, "in_stock": False, "category": "footwear"},
        {"id": "P004", "name": "Waterproof Jacket",   "price": 179.99,"in_stock": True,  "category": "outerwear"},
        {"id": "P005", "name": "Running Socks 3-pack","price": 14.99, "in_stock": True,  "category": "accessories"},
    ]

    # Apply filters if provided
    if filters:
        if filters.get("min_price"):
            products = [p for p in products if p["price"] >= filters["min_price"]]
        if filters.get("max_price"):
            products = [p for p in products if p["price"] <= filters["max_price"]]
        if filters.get("category"):
            products = [p for p in products if p["category"] == filters["category"]]
        if filters.get("in_stock"):
            products = [p for p in products if p["in_stock"]]

    # Apply sort
    sort_key = {"relevance": None, "price_asc": lambda x: x["price"],
                "price_desc": lambda x: -x["price"], "newest": None}.get(sort_by)
    if sort_key:
        products = sorted(products, key=sort_key)

    return {
        "query": query,
        "total": len(products),
        "results": products[:max_results],
        "sort_by": sort_by,
    }


# ---------------------------------------------------------------------------
# Tool call validator
# ---------------------------------------------------------------------------

def validate_tool_call(tool_input: dict, schema: dict) -> list[str]:
    """
    Validates a tool_input dict against the input_schema from a tool definition.
    Returns a list of error strings. Empty list means the call is valid.
    """
    errors: list[str] = []
    input_schema = schema.get("input_schema", {})
    properties = input_schema.get("properties", {})
    required_fields = input_schema.get("required", [])

    for field in required_fields:
        if field not in tool_input:
            errors.append(f"Missing required field: '{field}'")

    type_map = {
        "string":  str,
        "integer": int,
        "number":  (int, float),
        "boolean": bool,
        "object":  dict,
        "array":   list,
    }

    for field, value in tool_input.items():
        if field not in properties:
            errors.append(f"Unknown field: '{field}'")
            continue

        prop_schema = properties[field]
        expected_type = prop_schema.get("type")

        if expected_type in type_map:
            expected_python_type = type_map[expected_type]
            if not isinstance(value, expected_python_type):
                errors.append(
                    f"Field '{field}': expected {expected_type}, "
                    f"got {type(value).__name__} ({value!r})"
                )

        if "enum" in prop_schema and value not in prop_schema["enum"]:
            errors.append(
                f"Field '{field}': value {value!r} not in allowed values {prop_schema['enum']}"
            )

    return errors


# ---------------------------------------------------------------------------
# Schema comparison demo (no API call)
# ---------------------------------------------------------------------------

def run_validation_demo() -> None:
    """Show how the validator catches errors from bad-schema-style calls."""
    test_calls = [
        {
            "label": "V1-style call (abbreviated names, wrong types)",
            "input": {"q": "blue shoes", "n": 10, "sort": "newest", "f": "{}"},
        },
        {
            "label": "V2-style call (right names but invalid sort_by)",
            "input": {"query": "blue shoes", "max_results": 10, "sort_by": "ascending"},
        },
        {
            "label": "V3-style call (correct)",
            "input": {"query": "blue running shoes", "max_results": 10, "sort_by": "price_asc"},
        },
        {
            "label": "Missing required field",
            "input": {"max_results": 5, "sort_by": "newest"},
        },
        {
            "label": "Wrong type for max_results",
            "input": {"query": "shoes", "max_results": "ten"},
        },
    ]

    print("\n=== Tool Call Validation Demo ===\n")
    print(f"Schema under test: {SCHEMA_V3['name']}")
    print()

    for test in test_calls:
        errors = validate_tool_call(test["input"], SCHEMA_V3)
        status = "VALID" if not errors else f"INVALID ({len(errors)} error(s))"
        print(f"Call: {test['label']}")
        print(f"  Input:  {json.dumps(test['input'])}")
        print(f"  Status: {status}")
        for e in errors:
            print(f"    - {e}")
        print()


# ---------------------------------------------------------------------------
# Pydantic schema generation demo
# ---------------------------------------------------------------------------

def run_pydantic_demo() -> None:
    """Show Pydantic-generated schema vs hand-written V3 schema."""
    try:
        from pydantic import BaseModel, Field
    except ImportError:
        print("Install pydantic: pip install pydantic")
        return

    class ProductFilters(BaseModel):
        min_price: Optional[float] = Field(None, description="Minimum price in USD.")
        max_price: Optional[float] = Field(None, description="Maximum price in USD.")
        category:  Optional[str]   = Field(None, description="Product category, e.g. 'footwear'.")
        in_stock:  Optional[bool]  = Field(None, description="If true, return only in-stock items.")

    class SearchProductsInput(BaseModel):
        query: str = Field(
            description=(
                "Natural-language search query. "
                "Examples: 'blue running shoes', 'waterproof jacket under $200'."
            )
        )
        max_results: int = Field(
            default=10, ge=1, le=50,
            description="Maximum items to return. Default: 10. Range: 1 to 50."
        )
        sort_by: str = Field(
            default="relevance",
            description="Sort order. One of: relevance, price_asc, price_desc, newest."
        )
        filters: Optional[ProductFilters] = Field(
            None,
            description=(
                "Optional filters. Example: {min_price: 20, max_price: 150, category: 'footwear'}."
            )
        )

    schema = SearchProductsInput.model_json_schema()
    schema.pop("title", None)
    tool_schema = {
        "name": "search_products",
        "description": (
            "Search the product catalog by keyword. "
            "Use when the user wants to find, browse, or look up products."
        ),
        "input_schema": schema,
    }

    print("\n=== Pydantic-Generated Schema ===")
    print(json.dumps(tool_schema, indent=2))

    # Validate a call using Pydantic directly
    print("\n=== Pydantic Validation ===")
    good_input = {"query": "blue shoes", "max_results": 10, "sort_by": "price_asc"}
    bad_input  = {"query": "blue shoes", "max_results": 100}  # exceeds le=50

    try:
        validated = SearchProductsInput.model_validate(good_input)
        print(f"Good input: VALID -> {validated.model_dump()}")
    except Exception as e:
        print(f"Good input: INVALID -> {e}")

    try:
        validated = SearchProductsInput.model_validate(bad_input)
        print(f"Bad input:  VALID -> {validated.model_dump()}")
    except Exception as e:
        print(f"Bad input:  INVALID -> {e}")


# ---------------------------------------------------------------------------
# Live schema comparison via API
# ---------------------------------------------------------------------------

def run_schema_comparison(user_message: str) -> None:
    """
    Call the LLM with V1 and V3 schemas on the same message.
    Print what tool_input the LLM generates for each.
    """
    client = anthropic.Anthropic()

    print(f"\n[user] {user_message}")
    print()

    for label, schema in [("V1 (bad schema)", SCHEMA_V1), ("V3 (good schema)", SCHEMA_V3)]:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            tools=[schema],
            messages=[{"role": "user", "content": user_message}],
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if tool_uses:
            tu = tool_uses[0]
            errors = validate_tool_call(tu.input, schema)
            status = "VALID" if not errors else f"INVALID ({len(errors)} error)"
            print(f"  {label}")
            print(f"    Tool called: {tu.name}")
            print(f"    Input:       {json.dumps(tu.input)}")
            print(f"    Validation:  {status}")
            for e in errors:
                print(f"      - {e}")
        else:
            text = next((b.text for b in response.content if hasattr(b, "text")), "no text")
            print(f"  {label}: No tool call. Response: {text[:80]}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 03-02: Tool Schema Design")
    parser.add_argument("--validate", action="store_true", help="Run validation demo (no API call)")
    parser.add_argument("--pydantic", action="store_true", help="Run Pydantic schema demo (no API call)")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare V1 vs V3 schema via live API call",
    )
    parser.add_argument(
        "--message",
        default="Find blue running shoes under $100, sorted by price.",
        help="User message for API comparison demo.",
    )
    args = parser.parse_args()

    if args.validate:
        run_validation_demo()
        return

    if args.pydantic:
        run_pydantic_demo()
        return

    if args.compare:
        print("=== 03-02: Schema Comparison (V1 vs V3) ===")
        run_schema_comparison(args.message)
        return

    # Default: run validation demo + show schema diff summary
    print("=== 03-02: Tool Schema Design ===")
    print("\nRunning validation demo (no API call required)...")
    run_validation_demo()
    print("\nTo compare V1 vs V3 via live API: python main.py --compare")
    print("To see Pydantic schema generation:  python main.py --pydantic")


if __name__ == "__main__":
    main()
