"""
Lesson 04-01: The Agent Loop: Raw, No Dependencies
Phase 04: Agents - Patterns That Survive Production

A complete agent loop in ~120 lines using only the anthropic SDK.
The loop: take a user goal, call Claude with tool schemas, check for
tool_use, execute tools, send tool_result back, repeat until end_turn.
"""

import anthropic
import json
import math

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Tool definitions (JSON Schema format, passed directly to the API)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "calculator",
        "description": (
            "Evaluate a mathematical expression. "
            "Input must be a valid Python math expression using standard operators "
            "and the math module (e.g. math.sqrt, math.pi)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "A Python-evaluable math expression, e.g. '144 * 17' or 'math.sqrt(144)'"
                }
            },
            "required": ["expression"]
        }
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for current information. "
            "Use this for facts that may have changed recently or are not in training data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string"
                }
            },
            "required": ["query"]
        }
    }
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def run_calculator(expression: str) -> str:
    """Safely evaluate a math expression."""
    try:
        # Restrict eval: only math module, no builtins
        result = eval(expression, {"__builtins__": {}, "math": math})
        return str(result)
    except Exception as e:
        return f"Calculator error: {e}"


def run_web_search(query: str) -> str:
    """Stub web search. Replace with a real search API in production."""
    return (
        f"[STUB] Search results for '{query}':\n"
        f"1. Example result: placeholder information about {query}.\n"
        f"2. Note: replace this stub with a real search API (e.g. Brave, Serper, Tavily)."
    )


# Tool registry: name -> callable(args_dict) -> str
TOOL_REGISTRY = {
    "calculator": lambda args: run_calculator(args["expression"]),
    "web_search": lambda args: run_web_search(args["query"]),
}


def execute_tools(tool_use_blocks: list) -> list[dict]:
    """
    Execute all tool_use content blocks and return a list of tool_result dicts.
    These go into a user message as: {"role": "user", "content": tool_results}
    """
    results = []
    for block in tool_use_blocks:
        tool_name = block.name
        tool_input = block.input
        tool_use_id = block.id

        if tool_name in TOOL_REGISTRY:
            output = TOOL_REGISTRY[tool_name](tool_input)
        else:
            output = f"Error: unknown tool '{tool_name}'"

        results.append({
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": output
        })
    return results


# ---------------------------------------------------------------------------
# The agent loop
# ---------------------------------------------------------------------------

def run_agent(goal: str, max_iterations: int = 10, verbose: bool = True) -> str:
    """
    Run an agent loop until stop_reason is end_turn or max_iterations is reached.

    Message history grows by 2 per tool-use turn:
      - assistant message (with tool_use blocks)
      - user message (with tool_result blocks)
    """
    messages = [{"role": "user", "content": goal}]
    system = (
        "You are a precise assistant with access to a calculator and web search. "
        "Use tools when needed. When you have the answer, respond directly."
    )

    for iteration in range(max_iterations):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=messages
        )

        if verbose:
            print(f"\n[Turn {iteration + 1}] stop_reason={response.stop_reason} "
                  f"| input_tokens={response.usage.input_tokens} "
                  f"| output_tokens={response.usage.output_tokens}")

        # Exit condition: model finished
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "(no text in final response)"

        # Tool use: dispatch and loop
        if response.stop_reason == "tool_use":
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if verbose:
                for block in tool_use_blocks:
                    print(f"  -> Tool call: {block.name}({json.dumps(block.input)})")

            # Append assistant message (must include all content blocks, not just tool_use)
            messages.append({"role": "assistant", "content": response.content})

            # Execute tools and collect results
            tool_results = execute_tools(tool_use_blocks)

            if verbose:
                for r in tool_results:
                    preview = r["content"][:80].replace("\n", " ")
                    print(f"  <- Tool result [{r['tool_use_id'][:8]}...]: {preview}")

            # Append user message with tool_result blocks
            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason (max_tokens, etc.)
        return f"Stopped with unexpected stop_reason: {response.stop_reason}"

    return f"Agent stopped after {max_iterations} iterations without reaching end_turn."


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("DEMO 1: Calculator tool")
    print("=" * 60)
    result = run_agent("What is 144 multiplied by 17, and then divided by 3?")
    print(f"\nFinal answer: {result}")

    print("\n" + "=" * 60)
    print("DEMO 2: No tools needed (end_turn in one call)")
    print("=" * 60)
    result = run_agent("What are the three main components of an agent loop?")
    print(f"\nFinal answer: {result}")

    print("\n" + "=" * 60)
    print("DEMO 3: Web search stub")
    print("=" * 60)
    result = run_agent("Search for the latest version of the Anthropic Python SDK and tell me what you find.")
    print(f"\nFinal answer: {result}")
