"""
L07: Build an MCP Server - Python
appliedaifromscratch.com | Phase 03

A complete MCP server for a product catalog database.
Exposes: search_products tool, get_product tool,
         product://catalog/{category} resource, product_summary prompt.

Run:
    pip install mcp
    python main.py                    # runs as stdio server
    mcp dev main.py                   # runs in the mcp inspector

Claude Desktop config (add to claude_desktop_config.json):
    {
      "mcpServers": {
        "product-catalog": {
          "command": "python",
          "args": ["/absolute/path/to/main.py"]
        }
      }
    }
"""

import json
import sqlite3
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("product-catalog")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_db: sqlite3.Connection | None = None


def get_db() -> sqlite3.Connection:
    """Create and seed an in-memory SQLite database."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          TEXT    PRIMARY KEY,
            name        TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            price_cents INTEGER NOT NULL,
            description TEXT,
            in_stock    INTEGER DEFAULT 1
        )
    """)
    products = [
        ("P001", "Mechanical Keyboard",   "electronics", 12999, "TKL, Cherry MX Brown switches", 1),
        ("P002", "USB-C Hub 7-port",       "electronics",  4999, "4K HDMI, 100W PD, SD card reader", 1),
        ("P003", "Standing Desk Mat",      "office",        3499, "Anti-fatigue foam, 36x24 inches", 1),
        ("P004", "Monitor Arm",            "office",        8999, "Gas spring, holds up to 32-inch dual monitors", 1),
        ("P005", "Wireless Headphones",    "electronics", 19999, "Active noise cancellation, 30hr battery", 0),
        ("P006", "Laptop Stand",           "office",        5999, "Aluminum, 6 adjustable height positions", 1),
        ("P007", "Webcam 4K",              "electronics", 14999, "Auto-focus, excellent low-light performance", 1),
        ("P008", "Cable Management Kit",   "office",        1299, "Velcro straps, adhesive clips, under-desk tray", 1),
        ("P009", "Desk Lamp LED",          "office",        4499, "3 color temps, USB-A charging port", 1),
        ("P010", "Wrist Rest Set",         "office",        2999, "Memory foam for keyboard and mouse", 1),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO products VALUES (?,?,?,?,?,?)", products
    )
    conn.commit()
    return conn


def db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = get_db()
    return _db


# ---------------------------------------------------------------------------
# Tool: search_products
# ---------------------------------------------------------------------------

@mcp.tool()
def search_products(query: str, limit: int = 10) -> list[dict]:
    """
    Search products by name or description.

    Returns in-stock products only. Uses parameterized queries to prevent
    SQL injection. Limit is clamped to 1-50.

    Args:
        query: Search term to match against product name or description
        limit: Maximum number of results to return (1-50, default 10)
    """
    if not query or not query.strip():
        return []

    safe_limit = max(1, min(50, limit))
    search_term = f"%{query.strip()}%"

    cursor = db().execute(
        """
        SELECT id, name, category, price_cents, description, in_stock
        FROM products
        WHERE (name LIKE ? OR description LIKE ?)
          AND in_stock = 1
        ORDER BY name
        LIMIT ?
        """,
        (search_term, search_term, safe_limit),
    )
    return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Tool: get_product
# ---------------------------------------------------------------------------

@mcp.tool()
def get_product(product_id: str) -> dict | None:
    """
    Get a single product by its ID.

    Returns the full product record, or null if not found.

    Args:
        product_id: The product ID (e.g. 'P001')
    """
    cursor = db().execute(
        "SELECT id, name, category, price_cents, description, in_stock "
        "FROM products WHERE id = ?",
        (product_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Resource: product://catalog/{category}
# ---------------------------------------------------------------------------

@mcp.resource("product://catalog/{category}")
def get_catalog_by_category(category: str) -> str:
    """
    Return in-stock products in a category as JSON.

    URI examples:
        product://catalog/electronics   - all electronics
        product://catalog/office        - all office products
        product://catalog/all           - full catalog

    Args:
        category: Product category, or 'all' for the full catalog
    """
    if category == "all":
        cursor = db().execute(
            "SELECT id, name, category, price_cents, description "
            "FROM products WHERE in_stock = 1 ORDER BY category, name"
        )
    else:
        cursor = db().execute(
            "SELECT id, name, category, price_cents, description "
            "FROM products WHERE category = ? AND in_stock = 1 ORDER BY name",
            (category,),
        )
    rows = [dict(r) for r in cursor.fetchall()]
    return json.dumps(rows, indent=2)


# ---------------------------------------------------------------------------
# Prompt: product_summary
# ---------------------------------------------------------------------------

@mcp.prompt()
def product_summary(product_id: str, style: str = "brief") -> str:
    """
    Generate a prompt to write a product summary.

    Args:
        product_id: The product ID to summarize (e.g. 'P001')
        style: 'brief' for a 1-2 sentence snippet, 'detailed' for a full description
    """
    product = get_product(product_id)
    if not product:
        return f"No product found with ID '{product_id}'. Please check the product ID."

    price = f"${product['price_cents'] / 100:.2f}"
    stock_status = "In stock" if product["in_stock"] else "Out of stock"

    base = (
        f"Product: {product['name']} (ID: {product['id']})\n"
        f"Category: {product['category']}\n"
        f"Price: {price}\n"
        f"Status: {stock_status}\n"
        f"Description: {product['description']}\n\n"
    )

    if style == "brief":
        instruction = (
            "Write a 1-2 sentence product summary suitable for a search result snippet. "
            "Lead with the most distinctive feature."
        )
    else:
        instruction = (
            "Write a detailed product description with:\n"
            "1. A compelling headline\n"
            "2. Key features as bullet points\n"
            "3. Ideal use case (who is this for?)\n"
            "4. A closing sentence on value for money"
        )

    return base + instruction


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Run as stdio server (for Claude Desktop or mcp dev)
    # Logs go to stderr; stdout is reserved for JSON-RPC messages
    import sys
    print("Starting product-catalog MCP server on stdio...", file=sys.stderr)
    mcp.run(transport="stdio")
