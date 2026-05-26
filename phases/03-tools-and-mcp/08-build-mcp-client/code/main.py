"""
L08: Build an MCP Client
appliedaifromscratch.com | Phase 03

A generic MCP client that auto-discovers tools from any MCP server and
wires them into the Anthropic agent loop. No hardcoded tool schemas.

Connects to the product catalog server from L07.

Run:
    pip install mcp anthropic
    python main.py

    # Or point at a different server:
    SERVER_SCRIPT=../07-build-mcp-server/code/main.py python main.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ---------------------------------------------------------------------------
# Schema conversion
# ---------------------------------------------------------------------------

def mcp_to_anthropic_schema(mcp_tool) -> dict:
    """
    Convert an MCP tool definition to an Anthropic tool schema.

    The only difference: MCP uses 'inputSchema' (camelCase),
    Anthropic uses 'input_schema' (snake_case).
    Everything else (name, description, properties, required) is identical.
    """
    return {
        "name": mcp_tool.name,
        "description": mcp_tool.description or f"Tool: {mcp_tool.name}",
        "input_schema": mcp_tool.inputSchema,
    }


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

async def discover_tools(session: ClientSession) -> list[dict]:
    """
    Call tools/list on the MCP server and convert to Anthropic schemas.

    This is the key step that makes the agent generic: no tool schemas
    are hardcoded. The server is the source of truth.
    """
    result = await session.list_tools()
    return [mcp_to_anthropic_schema(t) for t in result.tools]


# ---------------------------------------------------------------------------
# Tool routing
# ---------------------------------------------------------------------------

async def call_tool(session: ClientSession, name: str, args: dict) -> str:
    """
    Route a tool call to the MCP server and return the result as a string.

    MCP tool results are a list of content blocks. This flattens text
    blocks into a single string for the Anthropic tool_result message.
    """
    result = await session.call_tool(name, args)

    if result.isError:
        # Propagate the error as a string so the LLM can handle it
        error_text = "\n".join(
            getattr(block, "text", str(block)) for block in result.content
        )
        return f"Tool error: {error_text}"

    parts = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
        elif hasattr(block, "data"):
            # Binary content - encode as base64 string representation
            parts.append(f"[binary data: {len(block.data)} bytes]")
    return "\n".join(parts) if parts else "(no output)"


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

async def run_agent(
    user_message: str,
    server_script: str,
    verbose: bool = True,
) -> str:
    """
    Run an Anthropic agent that auto-discovers tools from an MCP server.

    Steps:
    1. Start the server as a subprocess via stdio transport
    2. Initialize the MCP connection
    3. Discover tools (tools/list -> Anthropic schemas)
    4. Run the standard agent loop, routing tool calls through the MCP client

    Args:
        user_message: The user's initial question or request
        server_script: Absolute path to the MCP server Python file
        verbose: Print tool calls and results to stdout
    """
    client = anthropic.Anthropic()

    server_params = StdioServerParameters(
        command="python",
        args=[server_script],
        env=None,  # inherit current environment
    )

    if verbose:
        print(f"\nConnecting to MCP server: {server_script}")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:

            # Step 1: Initialize
            await session.initialize()
            if verbose:
                print("Connection established.")

            # Step 2: Discover tools
            tools = await discover_tools(session)
            if verbose:
                tool_names = [t["name"] for t in tools]
                print(f"Discovered {len(tools)} tools: {tool_names}\n")

            # Step 3: Agent loop
            messages = [{"role": "user", "content": user_message}]

            for turn in range(10):  # safety limit - prevent infinite loops
                response = client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=2048,
                    tools=tools,
                    messages=messages,
                )

                if verbose:
                    print(f"[Turn {turn + 1}] stop_reason: {response.stop_reason}")

                # Terminal condition
                if response.stop_reason == "end_turn":
                    final_text = ""
                    for block in response.content:
                        if hasattr(block, "text"):
                            final_text += block.text
                    return final_text

                # Tool use
                if response.stop_reason == "tool_use":
                    # Add assistant's response to history
                    messages.append(
                        {"role": "assistant", "content": response.content}
                    )

                    # Process each tool call
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            if verbose:
                                args_str = json.dumps(block.input, separators=(",", ":"))
                                print(f"  -> {block.name}({args_str})")

                            result_text = await call_tool(
                                session, block.name, block.input
                            )

                            if verbose:
                                preview = result_text[:120].replace("\n", " ")
                                print(f"  <- {preview}{'...' if len(result_text) > 120 else ''}")

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            })

                    # Add tool results to history
                    messages.append({"role": "user", "content": tool_results})

                else:
                    # Unexpected stop reason
                    if verbose:
                        print(f"Unexpected stop_reason: {response.stop_reason}")
                    break

    return "(agent loop ended without a final response)"


# ---------------------------------------------------------------------------
# Multi-server routing
# ---------------------------------------------------------------------------

async def run_agent_multi_server(
    user_message: str,
    servers: dict[str, str],
    verbose: bool = True,
) -> str:
    """
    Run an agent connected to multiple MCP servers simultaneously.

    Each server is identified by a namespace prefix.
    Tools are namespaced to avoid collisions: server_name__tool_name.

    Args:
        user_message: The user's request
        servers: Dict mapping server name to script path
                 e.g. {"catalog": "/path/to/catalog/main.py"}
        verbose: Print discovery and tool call info
    """
    client = anthropic.Anthropic()

    # Connect to all servers and discover their tools
    all_tools: list[dict] = []
    sessions: dict[str, tuple] = {}  # server_name -> (context manager handles)

    # NOTE: For production use, manage contexts properly.
    # This demo connects sequentially for clarity.

    async def collect_tools_from_server(
        name: str, script: str
    ) -> tuple[list[dict], ClientSession, object]:
        server_params = StdioServerParameters(command="python", args=[script])
        ctx = stdio_client(server_params)
        read, write = await ctx.__aenter__()
        session_ctx = ClientSession(read, write)
        session = await session_ctx.__aenter__()
        await session.initialize()
        result = await session.list_tools()
        tools = [
            {
                "name": f"{name}__{t.name}",  # namespace to avoid collisions
                "description": f"[{name}] {t.description or t.name}",
                "input_schema": t.inputSchema,
            }
            for t in result.tools
        ]
        if verbose:
            print(f"Server '{name}': {len(tools)} tools")
        return tools, session, (ctx, session_ctx)

    # For this demo, just use the first server
    # Full multi-server requires managing multiple async contexts
    if len(servers) == 1:
        name, script = next(iter(servers.items()))
        return await run_agent(user_message, script, verbose=verbose)

    print("Multi-server routing: connecting to first server only in this demo.")
    name, script = next(iter(servers.items()))
    return await run_agent(user_message, script, verbose=verbose)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def find_server_script() -> str:
    """Find the L07 server script relative to this file."""
    # Check environment variable first
    if "SERVER_SCRIPT" in os.environ:
        return os.environ["SERVER_SCRIPT"]

    # Try common relative paths
    this_dir = Path(__file__).parent
    candidates = [
        this_dir / ".." / "07-build-mcp-server" / "code" / "main.py",
        this_dir.parent / "07-build-mcp-server" / "code" / "main.py",
    ]
    for path in candidates:
        resolved = path.resolve()
        if resolved.exists():
            return str(resolved)

    # Fallback: let the user set it
    print("ERROR: Could not find the L07 server script.")
    print("Set SERVER_SCRIPT environment variable to the absolute path of main.py")
    print("from lesson 07-build-mcp-server.")
    sys.exit(1)


async def main():
    print("=" * 65)
    print("L08: MCP Client Demo")
    print("=" * 65)

    server_script = find_server_script()

    # Test 1: Product search
    print("\n--- Test 1: Product search ---")
    result = await run_agent(
        "What wireless electronics do you carry? List name, price, and a brief description.",
        server_script=server_script,
    )
    print(f"\nFinal answer:\n{result}")

    # Test 2: Specific product lookup
    print("\n\n--- Test 2: Specific product lookup ---")
    result = await run_agent(
        "Tell me about product P007. What is it and how much does it cost?",
        server_script=server_script,
    )
    print(f"\nFinal answer:\n{result}")

    # Test 3: Category resource + tool in one query
    print("\n\n--- Test 3: Office products under $50 ---")
    result = await run_agent(
        "What office products are available for under $50? "
        "Show me the options sorted by price.",
        server_script=server_script,
    )
    print(f"\nFinal answer:\n{result}")

    print("\n" + "=" * 65)
    print("Demo complete.")
    print("=" * 65)


# ---------------------------------------------------------------------------
# Schema conversion test (no server needed)
# ---------------------------------------------------------------------------

def test_schema_conversion():
    """Verify the MCP -> Anthropic schema conversion without a live server."""

    class MockMcpTool:
        name = "search_products"
        description = "Search products by name or description."
        inputSchema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        }

    tool = MockMcpTool()
    converted = mcp_to_anthropic_schema(tool)

    assert converted["name"] == "search_products"
    assert converted["description"] == "Search products by name or description."
    assert "input_schema" in converted        # Anthropic key
    assert "inputSchema" not in converted     # MCP key should be gone
    assert converted["input_schema"]["required"] == ["query"]

    print("Schema conversion test passed.")
    print(f"Converted schema:\n{json.dumps(converted, indent=2)}")


if __name__ == "__main__":
    # Run schema conversion test first (no server needed)
    print("Running schema conversion test...")
    test_schema_conversion()

    print("\nRunning agent demo (requires ANTHROPIC_API_KEY and L07 server)...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure:")
        print("  1. ANTHROPIC_API_KEY is set")
        print("  2. The L07 server is accessible (pip install mcp in that environment)")
        print("  3. Or set SERVER_SCRIPT=/absolute/path/to/07-build-mcp-server/code/main.py")
