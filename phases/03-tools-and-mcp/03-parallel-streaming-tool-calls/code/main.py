"""
Lesson 03-03: Parallel and Streaming Tool Calls
Demonstrates concurrent tool execution with asyncio.gather and ThreadPoolExecutor.

Run:                           python main.py
Run async parallel demo:       python main.py --parallel
Run sync ThreadPoolExecutor:   python main.py --sync
Run streaming demo:            python main.py --stream
Compare sequential vs parallel: python main.py --compare
"""

import argparse
import asyncio
import concurrent.futures
import json
import time
from typing import Any

import anthropic

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_market_data",
        "description": (
            "Fetch current market data for a stock ticker. Returns price, volume, and change. "
            "Use when the user asks about stock price, market cap, or trading volume."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol, e.g. 'AAPL', 'MSFT', 'GOOGL'.",
                }
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_company_filings",
        "description": (
            "Retrieve recent financial filings for a company. Returns revenue, EPS, and guidance. "
            "Use when the user asks about earnings, revenue, or financial performance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol.",
                }
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_news_sentiment",
        "description": (
            "Get aggregated news sentiment for a company over the past 7 days. "
            "Returns a score from -1.0 (very negative) to 1.0 (very positive). "
            "Use when the user asks about news, analyst sentiment, or market perception."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol.",
                }
            },
            "required": ["ticker"],
        },
    },
]

# ---------------------------------------------------------------------------
# Async stub functions (with artificial latency to show parallelism)
# ---------------------------------------------------------------------------

async def get_market_data(ticker: str) -> dict:
    """Simulates a 1.2s market data API call."""
    await asyncio.sleep(1.2)
    return {
        "ticker": ticker,
        "price": 189.30,
        "change_pct": -0.8,
        "volume": 54_210_000,
        "market_cap_b": 2_890,
        "latency_s": 1.2,
    }


async def get_company_filings(ticker: str) -> dict:
    """Simulates a 0.9s filings API call."""
    await asyncio.sleep(0.9)
    return {
        "ticker": ticker,
        "quarter": "Q1 2026",
        "revenue_b": 124.3,
        "eps": 2.18,
        "yoy_revenue_growth_pct": 8.2,
        "guidance": "Q2 revenue $128-132B",
        "latency_s": 0.9,
    }


async def get_news_sentiment(ticker: str) -> dict:
    """Simulates a 1.4s news sentiment API call."""
    await asyncio.sleep(1.4)
    return {
        "ticker": ticker,
        "sentiment_score": 0.72,
        "sentiment_label": "positive",
        "article_count": 47,
        "top_topics": ["earnings beat", "AI features", "market share gains"],
        "latency_s": 1.4,
    }


ASYNC_FUNCTION_MAP = {
    "get_market_data":     get_market_data,
    "get_company_filings": get_company_filings,
    "get_news_sentiment":  get_news_sentiment,
}

# ---------------------------------------------------------------------------
# Sync stub functions (for ThreadPoolExecutor demo)
# ---------------------------------------------------------------------------

def get_market_data_sync(ticker: str) -> dict:
    time.sleep(1.2)
    return {"ticker": ticker, "price": 189.30, "change_pct": -0.8, "volume": 54_210_000}


def get_company_filings_sync(ticker: str) -> dict:
    time.sleep(0.9)
    return {"ticker": ticker, "quarter": "Q1 2026", "revenue_b": 124.3, "eps": 2.18}


def get_news_sentiment_sync(ticker: str) -> dict:
    time.sleep(1.4)
    return {"ticker": ticker, "sentiment_score": 0.72, "sentiment_label": "positive"}


SYNC_FUNCTION_MAP = {
    "get_market_data":     get_market_data_sync,
    "get_company_filings": get_company_filings_sync,
    "get_news_sentiment":  get_news_sentiment_sync,
}

# ---------------------------------------------------------------------------
# Parallel async dispatcher
# ---------------------------------------------------------------------------

async def dispatch_parallel_async(tool_uses: list, timeout_secs: float = 10.0) -> list[dict]:
    """
    Execute all tool_use blocks concurrently with asyncio.gather.
    Handles timeouts and exceptions per tool without failing the whole batch.
    """
    async def execute_one(tool_use) -> dict:
        try:
            fn = ASYNC_FUNCTION_MAP.get(tool_use.name)
            if fn is None:
                result = {"error": f"Unknown tool: {tool_use.name!r}"}
            else:
                result = await asyncio.wait_for(fn(**tool_use.input), timeout=timeout_secs)
        except asyncio.TimeoutError:
            result = {
                "error": f"Tool {tool_use.name!r} timed out after {timeout_secs}s",
                "hint": "Try requesting less data or retry.",
            }
        except Exception as e:
            result = {"error": str(e), "type": type(e).__name__}
        return {
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": json.dumps(result),
        }

    return list(await asyncio.gather(*[execute_one(tu) for tu in tool_uses]))


# ---------------------------------------------------------------------------
# Parallel sync dispatcher (ThreadPoolExecutor)
# ---------------------------------------------------------------------------

def dispatch_parallel_sync(tool_uses: list) -> list[dict]:
    """
    Execute all tool_use blocks concurrently using ThreadPoolExecutor.
    Use this in synchronous (non-async) codebases.
    """
    def execute_one(tool_use) -> dict:
        fn = SYNC_FUNCTION_MAP.get(tool_use.name)
        if fn is None:
            result = {"error": f"Unknown tool: {tool_use.name!r}"}
        else:
            result = fn(**tool_use.input)
        return {
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": json.dumps(result),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tool_uses)) as executor:
        futures = [executor.submit(execute_one, tu) for tu in tool_uses]
        return [f.result() for f in concurrent.futures.as_completed(futures)]


# ---------------------------------------------------------------------------
# Full async dispatch loop (parallel execution)
# ---------------------------------------------------------------------------

async def run_parallel_tools(user_message: str) -> str:
    """Full two-round-trip dispatch loop with parallel async tool execution."""
    messages = [{"role": "user", "content": user_message}]
    t0 = time.perf_counter()

    print(f"\n[user] {user_message}")

    # Round 1: get tool call request
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )

    if response.stop_reason == "end_turn":
        return response.content[0].text

    tool_uses = [b for b in response.content if b.type == "tool_use"]
    print(f"[api]  {len(tool_uses)} tool call(s) requested by LLM:")
    for tu in tool_uses:
        print(f"       - {tu.name}({tu.input})")

    messages.append({"role": "assistant", "content": response.content})

    # Execute all tools in parallel
    t1 = time.perf_counter()
    tool_results = await dispatch_parallel_async(tool_uses)
    t2 = time.perf_counter()
    print(f"[exec] {len(tool_uses)} tools executed in {t2-t1:.2f}s (parallel)")

    messages.append({"role": "user", "content": tool_results})

    # Round 2: get final answer
    final_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )

    total = time.perf_counter() - t0
    print(f"[done] Total: {total:.2f}s")

    return next((b.text for b in final_response.content if hasattr(b, "text")), "")


# ---------------------------------------------------------------------------
# Streaming demo
# ---------------------------------------------------------------------------

def run_streaming_demo(user_message: str) -> None:
    """
    Show streaming tool call detection using input_json_delta events.
    Prints each tool call as it completes during the stream.
    """
    print(f"\n[stream] Message: {user_message!r}")
    print("[stream] Streaming response...\n")

    tool_calls_in_progress: dict[str, dict] = {}

    with client.messages.stream(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        tools=TOOLS,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for event in stream:
            event_type = type(event).__name__

            if event_type == "ContentBlockStart":
                block = event.content_block
                if hasattr(block, "type") and block.type == "tool_use":
                    tool_calls_in_progress[block.id] = {
                        "id":               block.id,
                        "name":             block.name,
                        "accumulated_json": "",
                    }
                    print(f"  [stream start] {block.name} (id={block.id[:12]}...)")

            elif event_type == "InputJsonEvent":
                if hasattr(event, "partial_json") and event.partial_json:
                    for call_data in tool_calls_in_progress.values():
                        call_data["accumulated_json"] += event.partial_json

            elif event_type == "ContentBlockStop":
                for call_data in list(tool_calls_in_progress.values()):
                    if call_data["accumulated_json"] and not call_data.get("printed"):
                        try:
                            parsed = json.loads(call_data["accumulated_json"])
                            print(f"  [stream done]  {call_data['name']}({json.dumps(parsed)})")
                            call_data["printed"] = True
                        except json.JSONDecodeError:
                            pass

    final_msg = stream.get_final_message()
    tool_use_blocks = [b for b in final_msg.content if b.type == "tool_use"]
    print(f"\n[stream] Final: {len(tool_use_blocks)} tool call(s) complete")


# ---------------------------------------------------------------------------
# Sequential vs parallel latency comparison (no LLM, just the tool calls)
# ---------------------------------------------------------------------------

async def compare_sequential_vs_parallel(ticker: str = "AAPL") -> None:
    """
    Compare sequential vs parallel execution times for the 3 stub tools.
    Does NOT make an LLM API call - just shows the timing difference.
    """
    print(f"\n=== Sequential vs Parallel Comparison (ticker={ticker}) ===\n")

    # Simulate sequential execution (one at a time)
    print("Sequential execution:")
    t0 = time.perf_counter()
    r1 = await get_market_data(ticker)
    r2 = await get_company_filings(ticker)
    r3 = await get_news_sentiment(ticker)
    seq_time = time.perf_counter() - t0
    print(f"  market_data:     {r1['latency_s']:.1f}s")
    print(f"  company_filings: {r2['latency_s']:.1f}s")
    print(f"  news_sentiment:  {r3['latency_s']:.1f}s")
    print(f"  Total (seq):     {seq_time:.2f}s")

    print()

    # Parallel execution
    print("Parallel execution:")
    t0 = time.perf_counter()
    results = await asyncio.gather(
        get_market_data(ticker),
        get_company_filings(ticker),
        get_news_sentiment(ticker),
    )
    par_time = time.perf_counter() - t0
    print(f"  All 3 tools ran concurrently")
    print(f"  Slowest tool:    {max(r['latency_s'] for r in results):.1f}s")
    print(f"  Total (par):     {par_time:.2f}s")
    print(f"\n  Speedup: {seq_time / par_time:.1f}x")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 03-03: Parallel and Streaming Tool Calls")
    parser.add_argument("--parallel", action="store_true", help="Run async parallel dispatch (API call)")
    parser.add_argument("--sync",     action="store_true", help="Show ThreadPoolExecutor timing (no API)")
    parser.add_argument("--stream",   action="store_true", help="Streaming tool call detection (API call)")
    parser.add_argument("--compare",  action="store_true", help="Compare sequential vs parallel timing (no API)")
    parser.add_argument(
        "--message",
        default="Give me a comprehensive analysis of AAPL: market data, recent filings, and news sentiment.",
        help="User message for the API demos.",
    )
    args = parser.parse_args()

    if args.compare:
        asyncio.run(compare_sequential_vs_parallel())
        return

    if args.sync:
        print("\n=== ThreadPoolExecutor Parallel Dispatch ===")
        # Simulate 3 tool_use objects
        class FakeTU:
            def __init__(self, id_, name, input_):
                self.id, self.name, self.input = id_, name, input_

        fake_tool_uses = [
            FakeTU("toolu_001", "get_market_data",     {"ticker": "AAPL"}),
            FakeTU("toolu_002", "get_company_filings", {"ticker": "AAPL"}),
            FakeTU("toolu_003", "get_news_sentiment",  {"ticker": "AAPL"}),
        ]
        t0 = time.perf_counter()
        results = dispatch_parallel_sync(fake_tool_uses)
        elapsed = time.perf_counter() - t0
        print(f"  Executed {len(results)} tools in {elapsed:.2f}s (parallel, ThreadPoolExecutor)")
        for r in results:
            data = json.loads(r["content"])
            print(f"  - {r['tool_use_id']}: {json.dumps(data)[:60]}...")
        return

    if args.stream:
        run_streaming_demo(args.message)
        return

    if args.parallel:
        print("=== 03-03: Parallel Tool Calls ===")
        answer = asyncio.run(run_parallel_tools(args.message))
        print(f"\nFinal answer:\n{answer}")
        return

    # Default: show timing comparison (no API)
    print("=== 03-03: Parallel and Streaming Tool Calls ===")
    print("Default: timing comparison (no API call)")
    asyncio.run(compare_sequential_vs_parallel())
    print("\nTo run with live API:")
    print("  python main.py --parallel  (async)")
    print("  python main.py --sync      (ThreadPoolExecutor)")
    print("  python main.py --stream    (streaming detection)")


if __name__ == "__main__":
    main()
