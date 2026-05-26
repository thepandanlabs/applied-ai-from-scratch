"""
L09: MCP Transports - stdio, HTTP SSE, and Streamable HTTP

Demonstrates how to configure the same MCP server for all three transports.
Each transport section is self-contained. Run with different entry points
depending on which transport you want.

Usage:
    # stdio (Claude Desktop forks this process):
    python main.py

    # HTTP SSE:
    python main.py --transport sse

    # Streamable HTTP:
    python main.py --transport streamable
"""

import argparse
import sys
from mcp.server import FastMCP

# ---------------------------------------------------------------------------
# Shared server + tool definitions
# ---------------------------------------------------------------------------

mcp = FastMCP("product-lookup")

PRODUCTS = {
    "p001": {"name": "Widget A", "price": 9.99, "stock": 142},
    "p002": {"name": "Widget B", "price": 24.99, "stock": 8},
    "p003": {"name": "Gadget X", "price": 149.00, "stock": 0},
}


@mcp.tool()
def get_product(product_id: str) -> dict:
    """Look up a product by ID."""
    if product_id not in PRODUCTS:
        return {"error": f"Product {product_id} not found"}
    return PRODUCTS[product_id]


@mcp.tool()
def list_products() -> list[dict]:
    """List all available products with IDs, names, prices, and stock."""
    return [{"id": k, **v} for k, v in PRODUCTS.items()]


# ---------------------------------------------------------------------------
# Transport 1: stdio
# Claude Desktop forks this process and communicates via stdin/stdout.
# IMPORTANT: never print anything to stdout except MCP protocol messages.
# Use stderr for debug output: print("debug", file=sys.stderr)
# ---------------------------------------------------------------------------

def run_stdio():
    print("Starting MCP server with stdio transport", file=sys.stderr)
    mcp.run(transport="stdio")


# ---------------------------------------------------------------------------
# Transport 2: HTTP SSE
# Server runs as an HTTP process. Client connects to /sse endpoint.
# Supports remote deployment and multiple sequential clients.
# Not suitable for concurrent sessions or bidirectional streaming.
# ---------------------------------------------------------------------------

def run_sse(host: str = "0.0.0.0", port: int = 8080):
    print(f"Starting MCP server with SSE transport on {host}:{port}", file=sys.stderr)
    mcp.run(transport="sse", host=host, port=port)


# ---------------------------------------------------------------------------
# Transport 3: Streamable HTTP
# The 2025 production standard. Adds session management, reconnect support,
# and bidirectional streaming. Use this for any multi-client or production
# deployment.
# ---------------------------------------------------------------------------

def run_streamable(host: str = "0.0.0.0", port: int = 8080):
    """
    Streamable HTTP requires an ASGI server (uvicorn) and a session manager.
    The session manager assigns each client a session ID and handles reconnects.
    """
    try:
        import uvicorn
        from starlette.applications import Starlette
        from starlette.routing import Mount
        from mcp.server.streamable_http import StreamableHTTPSessionManager
    except ImportError:
        print(
            "ERROR: Streamable HTTP requires uvicorn and starlette.\n"
            "Install: pip install uvicorn starlette",
            file=sys.stderr,
        )
        sys.exit(1)

    # event_store=None uses an in-memory store.
    # Swap for a Redis-backed store in production for cross-process sessions.
    session_manager = StreamableHTTPSessionManager(
        app=mcp,
        event_store=None,
    )

    app = Starlette(
        routes=[
            Mount("/mcp", app=session_manager.asgi_app()),
        ]
    )

    print(
        f"Starting MCP server with Streamable HTTP transport on {host}:{port}/mcp",
        file=sys.stderr,
    )
    uvicorn.run(app, host=host, port=port)


# ---------------------------------------------------------------------------
# Transport decision helper (the USE IT section)
# ---------------------------------------------------------------------------

from dataclasses import dataclass


@dataclass
class DeploymentContext:
    remote: bool           # Server is on a different machine than the client
    multi_client: bool     # More than one client connects concurrently
    needs_streaming: bool  # Server pushes partial results or progress updates
    production: bool       # Deployed beyond local dev


def choose_transport(ctx: DeploymentContext) -> tuple[str, str]:
    """
    Returns (transport_name, reason).
    Use this at architecture time, not at runtime.
    """
    if not ctx.remote:
        return "stdio", (
            "Same-machine deployment. Client forks the server process via stdin/stdout."
        )

    if ctx.multi_client or ctx.production or ctx.needs_streaming:
        return "streamable_http", (
            "Remote + production or multi-client: Streamable HTTP provides "
            "session management, reconnect support, and bidirectional streaming."
        )

    return "sse", (
        "Remote but simple: HTTP SSE is sufficient for a single client or "
        "low-traffic remote deployment without streaming requirements."
    )


# ---------------------------------------------------------------------------
# Demo: show the decision function output for three typical contexts
# ---------------------------------------------------------------------------

def demo_decision_function():
    contexts = [
        (
            "Local Claude Desktop plugin",
            DeploymentContext(
                remote=False, multi_client=False, needs_streaming=False, production=False
            ),
        ),
        (
            "Simple remote deployment, one team",
            DeploymentContext(
                remote=True, multi_client=False, needs_streaming=False, production=False
            ),
        ),
        (
            "Hosted MCP server, multiple teams, long-running tools",
            DeploymentContext(
                remote=True, multi_client=True, needs_streaming=True, production=True
            ),
        ),
    ]

    print("\n=== Transport Decision Examples ===\n")
    for label, ctx in contexts:
        transport, reason = choose_transport(ctx)
        print(f"Context: {label}")
        print(f"  -> {transport}")
        print(f"     {reason}")
        print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP transport demo")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable", "demo"],
        default="demo",
        help="Which transport to run, or 'demo' to show the decision function",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if args.transport == "stdio":
        run_stdio()
    elif args.transport == "sse":
        run_sse(args.host, args.port)
    elif args.transport == "streamable":
        run_streamable(args.host, args.port)
    else:
        demo_decision_function()
