"""
Lesson 10: Planning - ReAct, Plan-and-Execute

Demonstrates two planning patterns for multi-step agent tasks:
1. ReAct: interleaved Thought/Action/Observation with thought logging
2. Plan-and-Execute: planner call followed by executor loop

Both patterns applied to a "find and compare 3 competitors" research task.

Run: python main.py
Requires: ANTHROPIC_API_KEY environment variable
"""

import os
from dataclasses import dataclass, field

import anthropic

# ---------------------------------------------------------------------------
# Mock tools (replace with real search/web tools in production)
# ---------------------------------------------------------------------------

MOCK_SEARCH_DB = {
    "competitors widget market": [
        "WidgetCo - enterprise widget platform, $500/mo, founded 2019",
        "QuickWidget - self-serve widgets, $49/mo, founded 2021",
        "WidgetPro - open-source widgets, free tier, paid from $99/mo",
    ],
    "widgetco pricing": "WidgetCo: Enterprise plan $500/mo, Business $250/mo, no free tier. Contact sales for volume.",
    "quickwidget pricing": "QuickWidget: Starter $49/mo, Growth $149/mo, Scale $399/mo. 14-day free trial.",
    "widgetpro pricing": "WidgetPro: Open source free. Cloud hosted: Starter $99/mo, Pro $299/mo.",
    "widgetco features": "WidgetCo: advanced analytics, SSO, SLA guarantees, dedicated support, custom integrations.",
    "quickwidget features": "QuickWidget: drag-and-drop builder, 50+ templates, API access, basic analytics.",
    "widgetpro features": "WidgetPro: full API, self-hostable, plugin ecosystem, community support, enterprise add-ons.",
}


def mock_search(query: str) -> str:
    """Mock search tool. Returns relevant results from the mock database."""
    query_lower = query.lower()
    for key, value in MOCK_SEARCH_DB.items():
        if any(word in query_lower for word in key.split()):
            if isinstance(value, list):
                return "\n".join(value)
            return value
    return f"No results found for: {query}"


def mock_get_webpage(url: str) -> str:
    """Mock webpage retrieval."""
    domain = url.lower().replace("https://", "").replace("http://", "").split("/")[0]
    if "widgetco" in domain:
        return "WidgetCo - Enterprise Widget Platform. Trusted by Fortune 500 companies. Starting at $500/month."
    if "quickwidget" in domain:
        return "QuickWidget - The fastest way to add widgets. Self-serve, no sales call needed. Free trial available."
    if "widgetpro" in domain:
        return "WidgetPro - Open Source Widget Framework. Deploy anywhere. Free forever, with optional cloud hosting."
    return f"Page content for {url}: No mock data available."


# Tool registry
TOOLS = [
    {
        "name": "search",
        "description": "Search for information about companies, products, pricing, and features.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_webpage",
        "description": "Retrieve the content of a webpage given its URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to retrieve"}
            },
            "required": ["url"],
        },
    },
]

TOOL_FN = {
    "search": mock_search,
    "get_webpage": mock_get_webpage,
}


# ---------------------------------------------------------------------------
# ReAct pattern
# ---------------------------------------------------------------------------

REACT_SYSTEM_PROMPT = """You are a research agent. You have access to search and webpage retrieval tools.

IMPORTANT: Before every tool call, you MUST output a line starting exactly with "Thought:" that explains:
- What you know so far
- What you are about to do and why
- What you expect to find

Format:
Thought: [your reasoning]
[then call the tool]

If you have enough information to produce a final answer without calling more tools, output:
Thought: I have all the information I need. I will now write the final answer.
[then write your answer]

Be systematic. Work through the task step by step. Do not skip competitors."""


@dataclass
class ThoughtTrace:
    iteration: int
    thought: str
    action: str | None = None
    observation: str | None = None


def extract_thought(text: str) -> str | None:
    """Extract the first Thought: line from a model response."""
    for line in text.splitlines():
        if line.strip().lower().startswith("thought:"):
            return line.strip()[len("thought:"):].strip()
    return None


def call_tool(block: anthropic.types.ToolUseBlock) -> str:
    """Dispatch a tool_use block to the appropriate mock function."""
    fn = TOOL_FN.get(block.name)
    if fn is None:
        return f"Unknown tool: {block.name}"
    return fn(**block.input)


def react_loop(
    task: str,
    client: anthropic.Anthropic,
    max_iterations: int = 12,
) -> tuple[str, list[ThoughtTrace]]:
    """
    Run a ReAct loop on the given task.
    Returns the final answer and a list of ThoughtTrace entries for debugging.
    """
    messages = [{"role": "user", "content": task}]
    trace: list[ThoughtTrace] = []

    for iteration in range(max_iterations):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=REACT_SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        current_thought = None
        for block in response.content:
            if block.type == "text":
                thought = extract_thought(block.text)
                if thought:
                    current_thought = thought

        if response.stop_reason == "end_turn":
            final_text = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            trace.append(ThoughtTrace(
                iteration=iteration + 1,
                thought=current_thought or "Final answer generated.",
                action=None,
                observation=None,
            ))
            return final_text, trace

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = call_tool(block)
                    action_str = f"{block.name}(query='{block.input.get('query', block.input.get('url', ''))}')"
                    trace.append(ThoughtTrace(
                        iteration=iteration + 1,
                        thought=current_thought or "",
                        action=action_str,
                        observation=str(result)[:200],
                    ))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })
            messages.append({"role": "user", "content": tool_results})

    return "Max iterations reached.", trace


# ---------------------------------------------------------------------------
# Plan-and-Execute pattern
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """You are a planning agent. Your job is to create a numbered execution plan for a research task.

Output ONLY a numbered list of concrete steps. No prose, no headers, no explanations.
Each step should be one specific action (search, retrieve a page, compare data, write output).

Example format:
1. Search for the top competitors in the X market
2. Retrieve pricing page for Competitor A
3. Retrieve pricing page for Competitor B
4. Compare pricing across all competitors
5. Write final comparison

Keep the plan to 6-10 steps. Be specific."""

EXECUTOR_SYSTEM_PROMPT = """You are an execution agent. You are given one specific step to complete.
Use the available tools to complete that step. Be thorough.
If prior context is provided, use it to avoid repeating work."""


def parse_plan(plan_text: str) -> list[str]:
    """Extract numbered steps from a planner response."""
    steps = []
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped and stripped[0].isdigit() and "." in stripped:
            step_text = stripped.split(".", 1)[1].strip()
            if step_text:
                steps.append(step_text)
    return steps


def execute_step(
    step: str,
    prior_context: str,
    client: anthropic.Anthropic,
) -> str:
    """Execute a single plan step, handling tool calls."""
    user_content = f"Step to complete: {step}"
    if prior_context:
        user_content += f"\n\nContext from previous steps:\n{prior_context}"

    messages = [{"role": "user", "content": user_content}]

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system=EXECUTOR_SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
    )

    if response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = call_tool(block)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })
        messages.append({"role": "user", "content": tool_results})

        final = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            system=EXECUTOR_SYSTEM_PROMPT,
            messages=messages,
        )
        return next((b.text for b in final.content if b.type == "text"), "")

    return next((b.text for b in response.content if b.type == "text"), "")


def plan_and_execute(
    task: str,
    client: anthropic.Anthropic,
) -> dict[str, str]:
    """
    Two-phase execution:
    1. Planner call: generate numbered plan
    2. Executor loop: execute each step sequentially
    Returns a dict of step results.
    """
    # Phase 1: planning
    plan_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system=PLANNER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": task}],
    )
    plan_text = plan_response.content[0].text
    steps = parse_plan(plan_text)

    print(f"Generated plan ({len(steps)} steps):")
    for i, step in enumerate(steps, 1):
        print(f"  {i}. {step}")

    # Phase 2: execution
    results: dict[str, str] = {}
    for i, step in enumerate(steps, 1):
        print(f"\nExecuting step {i}: {step}")
        prior = "\n".join(f"Step {k}: {v[:150]}" for k, v in results.items())
        result = execute_step(step, prior, client)
        results[f"step_{i}"] = result
        print(f"  Result: {result[:120]}{'...' if len(result) > 120 else ''}")

    return results


# ---------------------------------------------------------------------------
# Demo: run both patterns on the same task
# ---------------------------------------------------------------------------

RESEARCH_TASK = (
    "Find and compare 3 competitors to our widget product. "
    "For each competitor, find: their pricing, their key features, and their target customer. "
    "Produce a comparison table at the end."
)


def print_separator(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    # --- ReAct ---
    print_separator("PATTERN 1: ReAct")
    print(f"Task: {RESEARCH_TASK}\n")

    react_answer, react_trace = react_loop(RESEARCH_TASK, client)

    print("\n--- Thought Trace ---")
    for entry in react_trace:
        print(f"  [Iter {entry.iteration}] Thought: {entry.thought[:100]}")
        if entry.action:
            print(f"           Action: {entry.action}")
        if entry.observation:
            print(f"           Observation: {entry.observation[:80]}...")

    print(f"\n--- Final Answer (ReAct) ---\n{react_answer[:600]}")

    # --- Plan-and-Execute ---
    print_separator("PATTERN 2: Plan-and-Execute")
    print(f"Task: {RESEARCH_TASK}\n")

    pe_results = plan_and_execute(RESEARCH_TASK, client)

    print("\n--- Step Results Summary ---")
    for key, value in pe_results.items():
        print(f"  {key}: {value[:80]}...")

    print_separator("COMPARISON")
    print(f"ReAct iterations: {len(react_trace)}")
    print(f"Plan-and-Execute steps: {len(pe_results)}")
    print("\nKey tradeoffs:")
    print("  ReAct:             adaptive, emergent, auditable via thought log")
    print("  Plan-and-Execute:  inspectable plan, resumable, rigid if task changes")


if __name__ == "__main__":
    main()
