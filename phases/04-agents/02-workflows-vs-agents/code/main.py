"""
Lesson 04-02: Workflows vs Agents: When NOT to Use an Agent
Phase 04: Agents - Patterns That Survive Production

Implements the same task two ways:
  - As a fixed workflow (1 LLM call, deterministic, cheap)
  - As an agent (multiple LLM calls, flexible, expensive)

Shows the cost/latency difference and a decision function for classifying tasks.
"""

import anthropic
import json
import time
from dataclasses import dataclass

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Implementation A: Fixed Workflow (correct for structured tasks)
# ---------------------------------------------------------------------------

def summarize_review_workflow(review: str) -> dict:
    """
    Fixed workflow: one structured prompt, one API call.
    The LLM executes all steps in a single call.
    Python controls the flow. Output is structured JSON.
    """
    prompt = f"""Analyze this product review and return a JSON object with exactly these fields:
- sentiment: "positive" | "negative" | "neutral" | "mixed"
- themes: list of 2-4 key themes mentioned
- summary: one sentence capturing the main point

Review:
{review}

Return only valid JSON, no explanation, no markdown code fences."""

    start = time.time()
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )
    elapsed = time.time() - start

    result = json.loads(response.content[0].text)
    result["_meta"] = {
        "approach": "workflow",
        "api_calls": 1,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_ms": round(elapsed * 1000)
    }
    return result


# ---------------------------------------------------------------------------
# Implementation B: Agent (incorrect for this task, shown for comparison)
# ---------------------------------------------------------------------------

ANALYSIS_TOOLS = [
    {
        "name": "extract_sentiment",
        "description": "Determine the overall sentiment of a text passage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to analyze"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "extract_themes",
        "description": "Extract 2-4 key themes from a text passage, returned as a comma-separated list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to analyze"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "write_summary",
        "description": "Write a one-sentence summary of a text passage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to summarize"}
            },
            "required": ["text"]
        }
    }
]


def _tool_extract_sentiment(text: str) -> str:
    resp = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=32,
        messages=[{"role": "user", "content": f"Sentiment of this text (one word: positive/negative/neutral/mixed):\n{text}"}]
    )
    return resp.content[0].text.strip()


def _tool_extract_themes(text: str) -> str:
    resp = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        messages=[{"role": "user", "content": f"List 2-4 key themes, comma-separated, no explanation:\n{text}"}]
    )
    return resp.content[0].text.strip()


def _tool_write_summary(text: str) -> str:
    resp = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=64,
        messages=[{"role": "user", "content": f"Write one sentence summarizing the main point:\n{text}"}]
    )
    return resp.content[0].text.strip()


AGENT_TOOL_REGISTRY = {
    "extract_sentiment": lambda args: _tool_extract_sentiment(args["text"]),
    "extract_themes": lambda args: _tool_extract_themes(args["text"]),
    "write_summary": lambda args: _tool_write_summary(args["text"]),
}


def summarize_review_agent(review: str) -> dict:
    """
    Agent approach: the LLM decides which tools to call and in what order.
    Wrong for this task. Steps are fixed. This adds unnecessary loops and cost.
    """
    messages = [
        {"role": "user", "content": f"Analyze this product review. Extract the sentiment, key themes, and write a one-sentence summary:\n\n{review}"}
    ]
    system = "You are a review analyst. Use the available tools to extract sentiment, themes, and a summary from the review."

    start = time.time()
    api_calls = 1  # count the first orchestration call
    total_input = 0
    total_output = 0
    turns = 0

    for _ in range(10):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system=system,
            tools=ANALYSIS_TOOLS,
            messages=messages
        )
        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens
        turns += 1

        if response.stop_reason == "end_turn":
            elapsed = time.time() - start
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text = block.text
                    break
            return {
                "result": final_text,
                "_meta": {
                    "approach": "agent",
                    "api_calls": api_calls,
                    "turns": turns,
                    "input_tokens": total_input,
                    "output_tokens": total_output,
                    "latency_ms": round((time.time() - start) * 1000)
                }
            }

        if response.stop_reason == "tool_use":
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for b in tool_blocks:
                api_calls += 1  # each tool call makes an LLM call in this implementation
                output = AGENT_TOOL_REGISTRY[b.name](b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": output})
            messages.append({"role": "user", "content": results})

    elapsed = time.time() - start
    return {
        "result": "max iterations reached",
        "_meta": {"approach": "agent", "api_calls": api_calls, "turns": turns,
                  "input_tokens": total_input, "output_tokens": total_output,
                  "latency_ms": round(elapsed * 1000)}
    }


# ---------------------------------------------------------------------------
# Decision framework: classify tasks before building
# ---------------------------------------------------------------------------

@dataclass
class TaskProfile:
    """Profile a task before choosing its architecture."""
    fixed_steps: bool                  # Can you enumerate every step before it runs?
    predictable_branches: bool         # Are all branch conditions known before execution?
    needs_realtime_decisions: bool     # Must the LLM see intermediate results to decide next steps?
    state_spans_sessions: bool         # Does task state persist across multiple conversations?
    multiple_specialized_goals: bool   # Does it require coordination across distinct sub-agents?


def should_use_agent(profile: TaskProfile) -> str:
    """
    Returns 'workflow' | 'agent' | 'multi-agent'.
    Encode this decision in design review, not after shipping.
    """
    if profile.state_spans_sessions or profile.multiple_specialized_goals:
        return "multi-agent"

    if profile.fixed_steps and profile.predictable_branches:
        return "workflow"

    if profile.needs_realtime_decisions:
        return "agent"

    # Default to workflow when in doubt
    return "workflow"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

SAMPLE_REVIEW = """
I've been using this laptop for three months now and have mixed feelings.
The battery life is excellent - I get a full 10 hours on a single charge, which is great
for travel. The display is also stunning with vibrant colors. However, the keyboard feels
mushy and lacks proper feedback, making long typing sessions uncomfortable. The fan
noise is another issue - it kicks in frequently even for light tasks. Customer support
was responsive when I had a setup issue, which I appreciated. Overall, good hardware
choices but some quality control issues in the input department.
"""

if __name__ == "__main__":
    print("=" * 60)
    print("APPROACH A: Fixed Workflow")
    print("=" * 60)
    workflow_result = summarize_review_workflow(SAMPLE_REVIEW)
    meta = workflow_result.pop("_meta")
    print(json.dumps(workflow_result, indent=2))
    print(f"\nMetrics: {meta['api_calls']} API call(s) | "
          f"{meta['input_tokens']} in / {meta['output_tokens']} out tokens | "
          f"{meta['latency_ms']}ms")

    print("\n" + "=" * 60)
    print("APPROACH B: Agent Loop")
    print("=" * 60)
    agent_result = summarize_review_agent(SAMPLE_REVIEW)
    meta = agent_result.pop("_meta")
    print(f"Result: {agent_result.get('result', '')[:200]}")
    print(f"\nMetrics: {meta['api_calls']} API call(s) | "
          f"{meta['turns']} turns | "
          f"{meta['input_tokens']} in / {meta['output_tokens']} out tokens | "
          f"{meta['latency_ms']}ms")

    print("\n" + "=" * 60)
    print("DECISION FRAMEWORK: Classify tasks before building")
    print("=" * 60)

    examples = [
        ("Document summarization", TaskProfile(True, True, False, False, False)),
        ("Customer support triage", TaskProfile(False, False, True, False, False)),
        ("Research assistant", TaskProfile(False, False, True, True, True)),
        ("Data validation pipeline", TaskProfile(True, True, False, False, False)),
        ("Debugging assistant", TaskProfile(False, False, True, False, False)),
    ]

    for name, profile in examples:
        decision = should_use_agent(profile)
        print(f"  {name:<35} -> {decision}")
