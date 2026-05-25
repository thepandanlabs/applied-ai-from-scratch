"""
Lesson 12: Agent SDKs - Claude, OpenAI, LangGraph Tradeoffs

Implements the same 3-tool agent loop in all three approaches:
1. Raw Anthropic SDK (~80 lines of loop logic)
2. Claude Agent SDK pattern (simplified abstraction layer)
3. LangGraph-style StateGraph (stateful graph with typed state)

Compares line counts and structure for the same behavior.

Run: python main.py
Requires: ANTHROPIC_API_KEY environment variable
Note: The LangGraph implementation is a self-contained simulation.
      For real LangGraph, install: pip install langgraph
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# Mock tools (shared by all three implementations)
# ---------------------------------------------------------------------------

def mock_search(query: str) -> str:
    return (
        f"Search results for '{query}': "
        "WidgetCo ($500/mo, enterprise), QuickWidget ($49/mo, self-serve), "
        "WidgetPro ($99/mo, open-source)"
    )


def mock_get_webpage(url: str) -> str:
    if "widgetco" in url.lower():
        return "WidgetCo: Enterprise platform, minimum 10-seat contract, dedicated onboarding."
    if "quickwidget" in url.lower():
        return "QuickWidget: Self-serve, signup in 2 minutes, no sales call."
    return f"Page at {url}: content about widget solutions."


def mock_summarize(text: str) -> str:
    words = text.split()
    return " ".join(words[:20]) + ("..." if len(words) > 20 else "")


TOOL_DISPATCH = {
    "search": mock_search,
    "get_webpage": mock_get_webpage,
    "summarize": mock_summarize,
}

TOOL_DEFINITIONS = [
    {
        "name": "search",
        "description": "Search for information about companies, products, or topics.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_webpage",
        "description": "Retrieve the content of a webpage given its URL.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to retrieve"}},
            "required": ["url"],
        },
    },
    {
        "name": "summarize",
        "description": "Summarize a block of text into a shorter form.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to summarize"}},
            "required": ["text"],
        },
    },
]

SYSTEM_PROMPT = "You are a research agent. Use tools to gather and summarize information. Be concise."


def dispatch_tool(name: str, inputs: dict) -> str:
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return f"Error: unknown tool '{name}'"
    return fn(**inputs)


# ---------------------------------------------------------------------------
# Approach 1: Raw Anthropic SDK
# ---------------------------------------------------------------------------

def raw_sdk_loop(task: str, client: anthropic.Anthropic, max_iterations: int = 10) -> dict:
    """
    The complete agent loop written from scratch.
    You own: loop control, tool dispatch, message list, termination.
    """
    start = time.monotonic()
    messages = [{"role": "user", "content": task}]
    iterations = 0

    for _ in range(max_iterations):
        iterations += 1
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            final = next((b.text for b in response.content if b.type == "text"), "")
            return {
                "answer": final,
                "iterations": iterations,
                "elapsed_ms": int((time.monotonic() - start) * 1000),
                "approach": "Raw SDK",
            }

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

    return {
        "answer": "Max iterations reached.",
        "iterations": iterations,
        "elapsed_ms": int((time.monotonic() - start) * 1000),
        "approach": "Raw SDK",
    }


# ---------------------------------------------------------------------------
# Approach 2: Agents SDK abstraction layer
# (Simulated here; real Claude Agent SDK has the same interface concept)
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    name: str
    description: str
    fn: callable
    schema: dict


@dataclass
class AgentConfig:
    model: str
    system: str
    tools: list[ToolDefinition]
    max_iterations: int = 10


@dataclass
class AgentResult:
    final_message: str
    iterations: int
    elapsed_ms: int
    approach: str = "Agents SDK"


class SimpleAgentSDK:
    """
    Simplified simulation of what an Agent SDK provides:
    - Tool registration via ToolDefinition objects
    - Built-in loop handling
    - Automatic tool dispatch
    - Clean run() interface

    In production, replace with the real Claude Agent SDK or OpenAI Agents SDK.
    """

    def __init__(self, config: AgentConfig, client: anthropic.Anthropic) -> None:
        self.config = config
        self.client = client
        self._tool_map = {t.name: t for t in config.tools}
        self._tool_definitions = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.schema,
            }
            for t in config.tools
        ]

    def run(self, task: str) -> AgentResult:
        start = time.monotonic()
        messages = [{"role": "user", "content": task}]
        iterations = 0

        for _ in range(self.config.max_iterations):
            iterations += 1
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=1024,
                system=self.config.system,
                tools=self._tool_definitions,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                final = next((b.text for b in response.content if b.type == "text"), "")
                return AgentResult(
                    final_message=final,
                    iterations=iterations,
                    elapsed_ms=int((time.monotonic() - start) * 1000),
                )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_def = self._tool_map.get(block.name)
                        if tool_def:
                            result = tool_def.fn(**block.input)
                        else:
                            result = f"Unknown tool: {block.name}"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                messages.append({"role": "user", "content": tool_results})

        return AgentResult(
            final_message="Max iterations reached.",
            iterations=iterations,
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )


def agents_sdk_loop(task: str, client: anthropic.Anthropic) -> dict:
    """
    Same agent behavior as raw_sdk_loop, but using the SDK abstraction.
    You own: tool implementations, agent config.
    SDK owns: loop control, dispatch, message list.
    """
    agent = SimpleAgentSDK(
        config=AgentConfig(
            model="claude-3-5-haiku-20241022",
            system=SYSTEM_PROMPT,
            tools=[
                ToolDefinition("search", "Search for information.", mock_search,
                               {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
                ToolDefinition("get_webpage", "Retrieve webpage content.", mock_get_webpage,
                               {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}),
                ToolDefinition("summarize", "Summarize text.", mock_summarize,
                               {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}),
            ],
        ),
        client=client,
    )
    result = agent.run(task)
    return {
        "answer": result.final_message,
        "iterations": result.iterations,
        "elapsed_ms": result.elapsed_ms,
        "approach": "Agents SDK",
    }


# ---------------------------------------------------------------------------
# Approach 3: LangGraph-style (self-contained simulation)
# ---------------------------------------------------------------------------
# In production: pip install langgraph
# This simulation demonstrates the structural pattern without the dependency.

@dataclass
class AgentState:
    messages: list[dict] = field(default_factory=list)
    final_answer: str = ""
    iterations: int = 0


def langgraph_style_loop(task: str, client: anthropic.Anthropic) -> dict:
    """
    LangGraph-style implementation with explicit state, nodes, and routing.
    Same behavior, but structured as a state machine.

    In production LangGraph:
    - AgentState is a TypedDict with Annotated fields
    - Each function is a node registered on StateGraph
    - Routing uses add_conditional_edges
    - State is checkpointed to a store
    """
    start = time.monotonic()
    state = AgentState(messages=[{"role": "user", "content": task}])

    def call_llm_node(state: AgentState) -> AgentState:
        """Node: call the LLM with current state."""
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=state.messages,
        )
        state.messages.append({"role": "assistant", "content": response.content, "_stop_reason": response.stop_reason})
        state.iterations += 1
        return state

    def route_after_llm(state: AgentState) -> str:
        """Routing function: determine which node runs next."""
        last = state.messages[-1]
        stop_reason = last.get("_stop_reason", "")
        if stop_reason == "tool_use":
            return "call_tools"
        return "end"

    def call_tools_node(state: AgentState) -> AgentState:
        """Node: execute all tool calls from the last assistant message."""
        last = state.messages[-1]
        content = last.get("content", [])
        tool_results = []
        for block in content:
            if hasattr(block, "type") and block.type == "tool_use":
                result = dispatch_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        state.messages.append({"role": "user", "content": tool_results})
        return state

    def end_node(state: AgentState) -> AgentState:
        """Node: extract the final answer."""
        last_assistant = next(
            (m for m in reversed(state.messages) if m.get("role") == "assistant"),
            None
        )
        if last_assistant:
            content = last_assistant.get("content", [])
            state.final_answer = next(
                (b.text for b in content if hasattr(b, "type") and b.type == "text"),
                ""
            )
        return state

    # Graph execution (simulated - production uses StateGraph.compile().invoke())
    max_nodes = 20
    node_calls = 0
    while node_calls < max_nodes:
        state = call_llm_node(state)
        node_calls += 1
        route = route_after_llm(state)
        if route == "end":
            state = end_node(state)
            break
        state = call_tools_node(state)
        node_calls += 1

    return {
        "answer": state.final_answer or "No answer extracted.",
        "iterations": state.iterations,
        "elapsed_ms": int((time.monotonic() - start) * 1000),
        "approach": "LangGraph-style",
    }


# ---------------------------------------------------------------------------
# Decision rubric function
# ---------------------------------------------------------------------------

def choose_sdk(
    needs_resumable_state: bool = False,
    needs_human_in_loop: bool = False,
    branching_paths: int = 1,
    has_custom_loop_pattern: bool = False,
) -> str:
    """
    Return the recommended SDK given task characteristics.
    """
    if needs_resumable_state or needs_human_in_loop or branching_paths > 5:
        return "LangGraph"
    if has_custom_loop_pattern:
        return "Raw Anthropic SDK"
    return "Claude Agent SDK (or OpenAI Agents SDK)"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def count_code_lines(fn) -> int:
    """Count non-empty, non-comment lines in a function's source."""
    import inspect
    source = inspect.getsource(fn)
    lines = [
        l for l in source.splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    return len(lines)


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)
    task = "Research the top 3 widget competitors. For each, find their pricing and target customer. Write a brief comparison."

    print("=" * 70)
    print("AGENT SDK COMPARISON: Same task, three implementations")
    print(f"Task: {task}")
    print("=" * 70)

    results = []

    print("\n--- Approach 1: Raw Anthropic SDK ---")
    r1 = raw_sdk_loop(task, client)
    results.append(r1)
    print(f"Answer: {r1['answer'][:200]}...")
    print(f"Iterations: {r1['iterations']} | Elapsed: {r1['elapsed_ms']}ms")

    print("\n--- Approach 2: Agents SDK (abstraction layer) ---")
    r2 = agents_sdk_loop(task, client)
    results.append(r2)
    print(f"Answer: {r2['answer'][:200]}...")
    print(f"Iterations: {r2['iterations']} | Elapsed: {r2['elapsed_ms']}ms")

    print("\n--- Approach 3: LangGraph-style ---")
    r3 = langgraph_style_loop(task, client)
    results.append(r3)
    print(f"Answer: {r3['answer'][:200]}...")
    print(f"Iterations: {r3['iterations']} | Elapsed: {r3['elapsed_ms']}ms")

    print("\n--- Comparison ---")
    print(f"{'Approach':<25} {'Iterations':<12} {'Elapsed (ms)':<15}")
    print("-" * 55)
    for r in results:
        print(f"{r['approach']:<25} {r['iterations']:<12} {r['elapsed_ms']:<15}")

    print("\n--- Line counts (loop logic only) ---")
    print(f"Raw SDK loop:         {count_code_lines(raw_sdk_loop)} lines")
    print(f"Agents SDK loop:      {count_code_lines(agents_sdk_loop)} lines (+ SDK internals)")
    print(f"LangGraph-style loop: {count_code_lines(langgraph_style_loop)} lines")

    print("\n--- Decision rubric examples ---")
    scenarios = [
        ("Customer support bot (3 tools, linear)", False, False, 1, False),
        ("Approval workflow (finance)", True, True, 3, False),
        ("Custom streaming chat", False, False, 1, True),
        ("Multi-day background research job", True, False, 2, False),
        ("Research agent (3-5 tools)", False, False, 2, False),
    ]
    print(f"\n{'Scenario':<45} {'Recommendation'}")
    print("-" * 75)
    for scenario, resumable, human, branches, custom in scenarios:
        rec = choose_sdk(resumable, human, branches, custom)
        print(f"{scenario:<45} {rec}")

    print("\n" + "=" * 70)
    print("Key takeaway: Use the SDK that earns its complexity.")
    print("Most production agents need Agents SDK, not LangGraph.")
    print("=" * 70)


if __name__ == "__main__":
    main()
