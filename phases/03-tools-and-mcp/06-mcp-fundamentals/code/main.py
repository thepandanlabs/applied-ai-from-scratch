"""
L06: MCP Fundamentals - Tools, Resources, Prompts, Sampling
appliedaifromscratch.com | Phase 03

Demonstrates the MCP wire protocol by hand (pure Python dicts + JSON-RPC),
then shows the equivalent server using the official mcp SDK.

Run:
    uv run main.py
    # or: python main.py
"""

import json
from typing import Any


# ---------------------------------------------------------------------------
# Part 1: Raw MCP protocol - no SDK
# This is what the mcp SDK generates under the hood.
# ---------------------------------------------------------------------------

# The server definition: what a real GitHub MCP server would declare
MCP_SERVER_DEFINITION = {
    "serverInfo": {
        "name": "github-mcp-server",
        "version": "1.0.0",
    },
    "capabilities": {
        "tools": {"listChanged": False},
        "resources": {"subscribe": False, "listChanged": False},
        "prompts": {"listChanged": False},
        "sampling": {},
    },
    "tools": [
        {
            "name": "create_issue",
            "description": "Create a GitHub issue in a repository",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "Repository owner"},
                    "repo": {"type": "string", "description": "Repository name"},
                    "title": {"type": "string", "description": "Issue title"},
                    "body": {
                        "type": "string",
                        "description": "Issue body in markdown (optional)",
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Labels to apply",
                    },
                },
                "required": ["owner", "repo", "title"],
            },
        },
        {
            "name": "list_pull_requests",
            "description": "List open pull requests for a repository",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "description": "Filter by PR state",
                    },
                },
                "required": ["owner", "repo"],
            },
        },
    ],
    "resources": [
        {
            "uri": "repo://owner/repo/README.md",
            "name": "Repository README",
            "description": "The root README for a repository",
            "mimeType": "text/markdown",
        },
        {
            "uri": "repo://owner/repo/issues",
            "name": "Open Issues",
            "description": "List of open issues for a repository as JSON",
            "mimeType": "application/json",
        },
    ],
    "prompts": [
        {
            "name": "summarize_pr",
            "description": "Generate a summary of a pull request",
            "arguments": [
                {
                    "name": "pr_number",
                    "description": "PR number to summarize",
                    "required": True,
                },
                {
                    "name": "include_diff",
                    "description": "Include diff in summary (true/false)",
                    "required": False,
                },
            ],
        }
    ],
}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 message builders
# ---------------------------------------------------------------------------

def make_request(method: str, params: dict, id: int) -> dict:
    """Build a JSON-RPC 2.0 request object."""
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params}


def make_response(result: Any, id: int) -> dict:
    """Build a JSON-RPC 2.0 response object."""
    return {"jsonrpc": "2.0", "id": id, "result": result}


def make_error_response(code: int, message: str, id: int) -> dict:
    """Build a JSON-RPC 2.0 error response."""
    return {
        "jsonrpc": "2.0",
        "id": id,
        "error": {"code": code, "message": message},
    }


def make_notification(method: str, params: dict) -> dict:
    """Build a JSON-RPC 2.0 notification (no id, no response expected)."""
    return {"jsonrpc": "2.0", "method": method, "params": params}


# ---------------------------------------------------------------------------
# Simulated MCP server (handles dispatches in-process)
# ---------------------------------------------------------------------------

class SimulatedMCPServer:
    """
    Processes JSON-RPC MCP messages in-process.
    Simulates what an actual stdio-based server process would do.
    """

    def __init__(self, definition: dict):
        self.definition = definition
        self._initialized = False

    def dispatch(self, message: dict) -> dict | None:
        """Process a message, return response or None for notifications."""
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params", {})

        # Notification: no response
        if msg_id is None:
            if method == "notifications/initialized":
                self._initialized = True
            return None

        # Method dispatch
        if method == "initialize":
            return make_response(
                {
                    "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                    "capabilities": self.definition["capabilities"],
                    "serverInfo": self.definition["serverInfo"],
                },
                id=msg_id,
            )

        if not self._initialized:
            return make_error_response(-32002, "Server not initialized", id=msg_id)

        if method == "tools/list":
            return make_response({"tools": self.definition["tools"]}, id=msg_id)

        if method == "resources/list":
            return make_response({"resources": self.definition["resources"]}, id=msg_id)

        if method == "prompts/list":
            return make_response({"prompts": self.definition["prompts"]}, id=msg_id)

        if method == "tools/call":
            return self._handle_tool_call(params, msg_id)

        if method == "resources/read":
            return self._handle_resource_read(params, msg_id)

        if method == "prompts/get":
            return self._handle_prompt_get(params, msg_id)

        return make_error_response(-32601, f"Method not found: {method}", id=msg_id)

    def _handle_tool_call(self, params: dict, msg_id: int) -> dict:
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "create_issue":
            issue_number = 42
            result_text = json.dumps({
                "issue_number": issue_number,
                "url": f"https://github.com/{args['owner']}/{args['repo']}/issues/{issue_number}",
                "title": args["title"],
                "state": "open",
            })
            return make_response(
                {"content": [{"type": "text", "text": result_text}], "isError": False},
                id=msg_id,
            )

        if name == "list_pull_requests":
            result_text = json.dumps([
                {"number": 7, "title": "Add rate limiting", "state": "open"},
                {"number": 8, "title": "Fix null pointer in auth handler", "state": "open"},
            ])
            return make_response(
                {"content": [{"type": "text", "text": result_text}], "isError": False},
                id=msg_id,
            )

        return make_error_response(-32602, f"Unknown tool: {name}", id=msg_id)

    def _handle_resource_read(self, params: dict, msg_id: int) -> dict:
        uri = params.get("uri", "")

        if "README" in uri:
            parts = uri.replace("repo://", "").split("/")
            owner, repo = parts[0], parts[1]
            content = f"# {repo}\n\nMaintained by {owner}.\n\nSee [docs](docs/) for usage."
            return make_response(
                {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": content}]},
                id=msg_id,
            )

        if "issues" in uri:
            issues = [
                {"number": 12, "title": "Improve error messages"},
                {"number": 15, "title": "Add pagination to search"},
            ]
            return make_response(
                {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(issues),
                        }
                    ]
                },
                id=msg_id,
            )

        return make_error_response(-32602, f"Unknown resource: {uri}", id=msg_id)

    def _handle_prompt_get(self, params: dict, msg_id: int) -> dict:
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "summarize_pr":
            pr_number = args.get("pr_number", "?")
            include_diff = args.get("include_diff", "false").lower() == "true"
            text = (
                f"Summarize pull request #{pr_number}. "
                "Focus on what changed, why it was changed, and any risks. "
            )
            if include_diff:
                text += "Include a section on the specific code changes."

            return make_response(
                {
                    "description": "PR summary prompt",
                    "messages": [
                        {"role": "user", "content": {"type": "text", "text": text}}
                    ],
                },
                id=msg_id,
            )

        return make_error_response(-32602, f"Unknown prompt: {name}", id=msg_id)


# ---------------------------------------------------------------------------
# Demo: full initialization + capability negotiation + all 4 primitives
# ---------------------------------------------------------------------------

def pp(label: str, obj: dict) -> None:
    """Pretty-print a message with a label."""
    print(f"\n{label}:")
    print(json.dumps(obj, indent=2))


def run_raw_protocol_demo():
    print("=" * 65)
    print("Part 1: Raw MCP Protocol (no SDK)")
    print("=" * 65)

    server = SimulatedMCPServer(MCP_SERVER_DEFINITION)

    # --- Initialization handshake ---
    init_req = make_request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {"sampling": {}},
        "clientInfo": {"name": "demo-host", "version": "1.0"},
    }, id=1)
    pp("[Host -> Server] initialize", init_req)

    init_resp = server.dispatch(init_req)
    pp("[Server -> Host] initialize response", init_resp)

    init_notify = make_notification("notifications/initialized", {})
    pp("[Host -> Server] initialized notification (no response)", init_notify)
    server.dispatch(init_notify)  # returns None

    # --- Primitive 1: Tools ---
    tools_req = make_request("tools/list", {}, id=2)
    tools_resp = server.dispatch(tools_req)
    pp("[Host] tools/list response", tools_resp)

    tool_call = make_request("tools/call", {
        "name": "create_issue",
        "arguments": {
            "owner": "acme",
            "repo": "backend",
            "title": "Fix auth token expiry",
            "body": "Token expiry is hardcoded to 1 hour.",
        },
    }, id=3)
    pp("[Host -> Server] tools/call create_issue", tool_call)
    tool_result = server.dispatch(tool_call)
    pp("[Server -> Host] tools/call result", tool_result)

    # --- Primitive 2: Resources ---
    resources_req = make_request("resources/list", {}, id=4)
    resources_resp = server.dispatch(resources_req)
    pp("[Host] resources/list response", resources_resp)

    resource_read = make_request("resources/read", {
        "uri": "repo://acme/backend/README.md"
    }, id=5)
    pp("[Host -> Server] resources/read", resource_read)
    resource_result = server.dispatch(resource_read)
    pp("[Server -> Host] resources/read result", resource_result)

    # --- Primitive 3: Prompts ---
    prompts_req = make_request("prompts/list", {}, id=6)
    prompts_resp = server.dispatch(prompts_req)
    pp("[Host] prompts/list response", prompts_resp)

    prompt_get = make_request("prompts/get", {
        "name": "summarize_pr",
        "arguments": {"pr_number": "17", "include_diff": "true"},
    }, id=7)
    pp("[Host -> Server] prompts/get summarize_pr", prompt_get)
    prompt_result = server.dispatch(prompt_get)
    pp("[Server -> Host] prompts/get result", prompt_result)

    # --- Primitive 4: Sampling (server → host) ---
    # Sampling is server-initiated: the server sends this to the HOST.
    # In a real setup, the host processes it and returns an LLM response.
    sampling_req = make_request("sampling/createMessage", {
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": "Summarize: PR #17 adds rate limiting to the auth endpoint.",
                },
            }
        ],
        "maxTokens": 200,
    }, id=8)
    pp("[Server -> Host] sampling/createMessage (server-initiated inference)", sampling_req)
    # The host would respond with the LLM's output:
    sampling_resp = make_response(
        {
            "role": "assistant",
            "content": {
                "type": "text",
                "text": (
                    "PR #17 introduces rate limiting on the authentication endpoint "
                    "to prevent brute-force attacks. The change adds a sliding window "
                    "counter per IP with a 100 req/min ceiling."
                ),
            },
            "model": "claude-3-5-haiku-20241022",
            "stopReason": "end_turn",
        },
        id=8,
    )
    pp("[Host -> Server] sampling response (LLM result)", sampling_resp)

    print("\n" + "=" * 65)
    print("Raw protocol demo complete.")
    print("=" * 65)


# ---------------------------------------------------------------------------
# Part 2: SDK version - same capabilities, ~30 lines
# ---------------------------------------------------------------------------

def show_sdk_version():
    print("\n" + "=" * 65)
    print("Part 2: SDK Version (mcp FastMCP)")
    print("=" * 65)

    sdk_code = '''
# Install: pip install mcp
# This is the same GitHub MCP server in ~30 lines using FastMCP.

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("github-mcp-server")

@mcp.tool()
def create_issue(owner: str, repo: str, title: str, body: str = "") -> dict:
    """Create a GitHub issue in a repository."""
    return {
        "issue_number": 42,
        "url": f"https://github.com/{owner}/{repo}/issues/42",
        "title": title,
        "state": "open",
    }

@mcp.tool()
def list_pull_requests(owner: str, repo: str, state: str = "open") -> list:
    """List pull requests for a repository."""
    return [
        {"number": 7, "title": "Add rate limiting", "state": state},
        {"number": 8, "title": "Fix null pointer in auth", "state": state},
    ]

@mcp.resource("repo://{owner}/{repo}/README.md")
def get_readme(owner: str, repo: str) -> str:
    """Read a repository README."""
    return f"# {repo}\\n\\nMaintained by {owner}."

@mcp.resource("repo://{owner}/{repo}/issues")
def get_issues(owner: str, repo: str) -> str:
    """Get open issues as JSON."""
    import json
    return json.dumps([
        {"number": 12, "title": "Improve error messages"},
        {"number": 15, "title": "Add pagination"},
    ])

@mcp.prompt()
def summarize_pr(pr_number: str, include_diff: bool = False) -> str:
    """Generate a prompt to summarize a pull request."""
    base = f"Summarize pull request #{pr_number}. Focus on what changed and why."
    if include_diff:
        base += " Include a section on the specific code changes."
    return base

if __name__ == "__main__":
    mcp.run(transport="stdio")
'''
    print(sdk_code)

    # Try importing the SDK and show actual tool list if available
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
        mcp = FastMCP("github-mcp-server-demo")

        @mcp.tool()
        def create_issue(owner: str, repo: str, title: str, body: str = "") -> dict:
            """Create a GitHub issue."""
            return {"issue_number": 42, "title": title, "state": "open"}

        @mcp.resource("repo://{owner}/{repo}/README.md")
        def get_readme(owner: str, repo: str) -> str:
            """Read a repository README."""
            return f"# {repo}\n\nMaintained by {owner}."

        @mcp.prompt()
        def summarize_pr(pr_number: str, include_diff: bool = False) -> str:
            """Summarize a PR."""
            return f"Summarize PR #{pr_number}."

        print("mcp SDK is installed. Server defined successfully.")
        print("Run with: mcp.run(transport='stdio') to start the server.")
        print("Connect with: mcp dev <server_script.py>")

    except ImportError:
        print("mcp SDK not installed. Install with: pip install mcp")
        print("The code above would run as-is after installation.")


# ---------------------------------------------------------------------------
# Primitive summary
# ---------------------------------------------------------------------------

def print_primitives_summary():
    print("\n" + "=" * 65)
    print("MCP Primitive Summary")
    print("=" * 65)

    rows = [
        ("Tools", "Host -> Server", "LLM / agent", "Action execution, on-demand data"),
        ("Resources", "Host -> Server", "Host or LLM", "Read structured data by URI"),
        ("Prompts", "Host -> Server", "Host or LLM", "Load reusable prompt templates"),
        ("Sampling", "Server -> Host", "MCP Server", "Server-side LLM inference"),
    ]

    print(f"\n{'Primitive':<12} {'Direction':<20} {'Initiator':<18} {'Primary Use'}")
    print("-" * 80)
    for row in rows:
        print(f"{row[0]:<12} {row[1]:<20} {row[2]:<18} {row[3]}")


if __name__ == "__main__":
    run_raw_protocol_demo()
    show_sdk_version()
    print_primitives_summary()
