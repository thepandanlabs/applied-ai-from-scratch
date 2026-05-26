"""
L10: MCP Resources and Prompts

Demonstrates the three MCP primitives: tools, resources, and prompts.
Extends the product database server with:
  - A static schema resource (docs://products/schema)
  - A dynamic product resource (product://{product_id})
  - A catalog resource (docs://products/catalog)
  - A sales analysis prompt template (analyze_sales)

Run this server with stdio transport and connect via MCP Inspector or
the test client at the bottom of this file.

Usage:
    # Start the server (for MCP Inspector or Claude Desktop):
    python main.py --server

    # Run the demo client (shows resource reads and prompt rendering):
    python main.py --client

    # Run smoke tests:
    python main.py --test
"""

import argparse
import asyncio
import json
import sys
from mcp.server import FastMCP

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

mcp = FastMCP("product-database")

PRODUCTS = {
    "p001": {"name": "Widget A", "price": 9.99, "stock": 142, "category": "hardware"},
    "p002": {"name": "Widget B", "price": 24.99, "stock": 8, "category": "hardware"},
    "p003": {"name": "Gadget X", "price": 149.00, "stock": 0, "category": "electronics"},
    "p004": {"name": "Gadget Y", "price": 89.00, "stock": 37, "category": "electronics"},
}

SALES = [
    {"product_id": "p001", "date": "2025-05-01", "units": 12, "revenue": 119.88},
    {"product_id": "p002", "date": "2025-05-01", "units": 3, "revenue": 74.97},
    {"product_id": "p001", "date": "2025-05-15", "units": 8, "revenue": 79.92},
    {"product_id": "p003", "date": "2025-05-20", "units": 1, "revenue": 149.00},
]

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_products(query: str) -> list[dict]:
    """Search products by name or category."""
    q = query.lower()
    return [
        {"id": k, **v}
        for k, v in PRODUCTS.items()
        if q in v["name"].lower() or q in v["category"].lower()
    ]


@mcp.tool()
def get_sales_summary() -> dict:
    """Get aggregated sales totals across all products."""
    total_revenue = sum(s["revenue"] for s in SALES)
    total_units = sum(s["units"] for s in SALES)
    by_product: dict[str, dict] = {}
    for sale in SALES:
        pid = sale["product_id"]
        if pid not in by_product:
            by_product[pid] = {"units": 0, "revenue": 0.0}
        by_product[pid]["units"] += sale["units"]
        by_product[pid]["revenue"] += sale["revenue"]
    return {
        "total_revenue": round(total_revenue, 2),
        "total_units": total_units,
        "by_product": by_product,
    }


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

DB_SCHEMA = """
Products table:
  product_id  TEXT PRIMARY KEY
  name        TEXT NOT NULL
  price       REAL NOT NULL
  stock       INTEGER NOT NULL
  category    TEXT NOT NULL

Sales table:
  id          INTEGER PRIMARY KEY
  product_id  TEXT REFERENCES products(product_id)
  date        TEXT  -- ISO 8601: YYYY-MM-DD
  units       INTEGER
  revenue     REAL
"""


@mcp.resource("docs://products/schema")
def get_schema() -> str:
    """The database schema for the product and sales tables."""
    return DB_SCHEMA


@mcp.resource("docs://products/catalog")
def get_catalog() -> str:
    """All products as JSON, suitable for injection into LLM context."""
    return json.dumps(
        [{"id": k, **v} for k, v in PRODUCTS.items()],
        indent=2,
    )


@mcp.resource("product://{product_id}")
def get_product_resource(product_id: str) -> str:
    """Product details as a formatted text block, addressed by URI template."""
    if product_id not in PRODUCTS:
        return f"Product {product_id} not found."
    p = PRODUCTS[product_id]
    return (
        f"Product: {p['name']}\n"
        f"ID: {product_id}\n"
        f"Price: ${p['price']:.2f}\n"
        f"Stock: {p['stock']} units\n"
        f"Category: {p['category']}\n"
        f"Status: {'In stock' if p['stock'] > 0 else 'Out of stock'}"
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@mcp.prompt()
def analyze_sales(time_period: str) -> str:
    """
    Generate a sales analysis prompt for a given time period.
    Returns a fully-formed prompt ready to send to an LLM.
    """
    sales_data = json.dumps(SALES, indent=2)
    return (
        f"Analyze the following sales data for {time_period}.\n\n"
        f"Sales records:\n{sales_data}\n\n"
        "Your analysis should cover:\n"
        "1. Total revenue and unit volume\n"
        "2. Best-performing product by revenue\n"
        "3. Any products with concerning stock levels (below 10 units)\n"
        "4. One actionable recommendation for the next period\n\n"
        "Be concise. Use bullet points for the findings."
    )


# ---------------------------------------------------------------------------
# Demo client
# ---------------------------------------------------------------------------

async def run_demo_client():
    """Connect to the server and demonstrate reading resources and prompts."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[__file__, "--server"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List resources
            resources = await session.list_resources()
            print("=== Available Resources ===")
            for r in resources.resources:
                print(f"  {r.uri}")
                if r.description:
                    print(f"    {r.description}")

            # Read static resource
            print("\n=== Schema Resource (docs://products/schema) ===")
            schema = await session.read_resource("docs://products/schema")
            print(schema.contents[0].text.strip())

            # Read dynamic resource via URI template
            print("\n=== Product Resource (product://p001) ===")
            product = await session.read_resource("product://p001")
            print(product.contents[0].text)

            # Read unknown product
            print("\n=== Product Resource (product://unknown) ===")
            unknown = await session.read_resource("product://unknown")
            print(unknown.contents[0].text)

            # List prompts
            prompts = await session.list_prompts()
            print("\n=== Available Prompts ===")
            for p in prompts.prompts:
                args = [f"{a.name} (required={a.required})" for a in (p.arguments or [])]
                print(f"  {p.name}: args = {args}")

            # Render the prompt
            print("\n=== Rendered Prompt: analyze_sales(time_period='May 2025') ===")
            rendered = await session.get_prompt(
                "analyze_sales",
                {"time_period": "May 2025"},
            )
            print(rendered.messages[0].content.text[:400])
            print("...(truncated)")


async def run_smoke_tests():
    """Verify all resources and prompts are registered and return expected content."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[__file__, "--server"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Resources present
            resources = await session.list_resources()
            uris = [r.uri for r in resources.resources]
            assert "docs://products/schema" in uris, f"Schema resource missing. Got: {uris}"
            assert "docs://products/catalog" in uris, f"Catalog resource missing. Got: {uris}"

            # Schema content
            schema = await session.read_resource("docs://products/schema")
            assert "Products table" in schema.contents[0].text, "Schema content wrong"

            # Dynamic resource: valid product
            p1 = await session.read_resource("product://p001")
            assert "Widget A" in p1.contents[0].text, "p001 content wrong"

            # Dynamic resource: invalid product
            pnone = await session.read_resource("product://does-not-exist")
            assert "not found" in pnone.contents[0].text.lower(), "Invalid product error message wrong"

            # Prompt registered
            prompts = await session.list_prompts()
            names = [p.name for p in prompts.prompts]
            assert "analyze_sales" in names, f"analyze_sales prompt missing. Got: {names}"

            # Prompt renders with argument substitution
            rendered = await session.get_prompt("analyze_sales", {"time_period": "Q2 2025"})
            assert "Q2 2025" in rendered.messages[0].content.text, "Prompt argument not substituted"

    print("All smoke tests passed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP resources and prompts demo")
    parser.add_argument("--server", action="store_true", help="Run as MCP server (stdio)")
    parser.add_argument("--client", action="store_true", help="Run demo client")
    parser.add_argument("--test", action="store_true", help="Run smoke tests")
    args = parser.parse_args()

    if args.server:
        mcp.run(transport="stdio")
    elif args.client:
        asyncio.run(run_demo_client())
    elif args.test:
        asyncio.run(run_smoke_tests())
    else:
        # Default: run demo client
        asyncio.run(run_demo_client())
