"""
Lesson 05-03: Trace Review and Failure Taxonomy
A trace logging decorator, a TraceStore, and a CLI trace viewer.

Run with: python main.py
Run demo pipeline: python main.py --run-pipeline
View traces: python main.py --view
View failures only: python main.py --view --failures
"""

import time
import uuid
import json
import argparse
import functools
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# TraceStore: accumulates steps for the current trace
# ---------------------------------------------------------------------------

class TraceStore:
    """
    Collects trace steps for one pipeline execution and writes to a JSON lines file.

    Usage:
        store = TraceStore("traces.jsonl")
        store.start_trace({"query": "..."})
        # run pipeline steps (decorated with @trace_step(store, "step_name"))
        store.end_trace(output="...", failure=False)
    """

    def __init__(self, output_path: str = "traces.jsonl"):
        self.output_path = output_path
        self._current_trace_id: str | None = None
        self._steps: list[dict] = []
        self._start_time: float | None = None
        self._input: dict = {}

    def start_trace(self, input_data: dict) -> str:
        """Start a new trace. Returns the trace_id."""
        self._current_trace_id = str(uuid.uuid4())[:8]
        self._steps = []
        self._start_time = time.monotonic()
        self._input = input_data
        return self._current_trace_id

    def add_step(
        self,
        name: str,
        input: dict,
        output: Any,
        latency_ms: int,
        error: dict | None,
    ) -> None:
        """Add a completed step to the current trace."""
        self._steps.append(
            {
                "name": name,
                "input": _safe_serialize(input),
                "output": _safe_serialize(output),
                "latency_ms": latency_ms,
                "error": error,
            }
        )

    def end_trace(
        self,
        output: Any,
        failure: bool = False,
        failure_step: str | None = None,
        notes: str = "",
    ) -> dict:
        """
        Finalize the current trace and write to the output file.
        Returns the trace dict.
        """
        total_ms = int((time.monotonic() - self._start_time) * 1000)
        trace = {
            "trace_id": self._current_trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input": self._input,
            "steps": self._steps,
            "output": _safe_serialize(output),
            "total_latency_ms": total_ms,
            "failure": failure,
            "failure_step": failure_step,
            "notes": notes,
        }
        with open(self.output_path, "a") as f:
            f.write(json.dumps(trace) + "\n")
        return trace


def _safe_serialize(obj: Any, max_len: int = 500) -> Any:
    """Serialize an object safely for JSON logging."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return str(obj)[:max_len] if isinstance(obj, str) else obj
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(item) for item in obj[:10]]  # cap list length
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in list(obj.items())[:20]}
    return str(obj)[:max_len]


# ---------------------------------------------------------------------------
# Trace decorator
# ---------------------------------------------------------------------------

def trace_step(store: TraceStore, step_name: str) -> Callable:
    """
    Decorator that logs a function call as a named step in the current trace.

    Usage:
        @trace_step(store, "retrieve")
        def retrieve(query: str) -> list[str]:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.monotonic()
            error = None
            output = None
            try:
                output = fn(*args, **kwargs)
            except Exception as e:
                error = {
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc()[-500:],
                }
                raise
            finally:
                latency_ms = int((time.monotonic() - start) * 1000)
                store.add_step(
                    name=step_name,
                    input={"args": [_safe_serialize(a) for a in args], "kwargs": kwargs},
                    output=output,
                    latency_ms=latency_ms,
                    error=error,
                )
            return output
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Mock pipeline (replace with your real system)
# ---------------------------------------------------------------------------

# Simulated knowledge base chunks for a support bot
KNOWLEDGE_BASE = {
    "return policy": [
        "Digital downloads are non-refundable once accessed.",
        "Physical products can be returned within 30 days with original receipt.",
        "Contact support@company.com for refund requests.",
    ],
    "shipping": [
        "Standard shipping takes 5-7 business days.",
        "Express shipping takes 2-3 business days for an additional $15.",
        "International shipping is available to 50+ countries.",
    ],
    "account": [
        "You can reset your password via the login page.",
        "Account deletion requests take 30 days to process.",
        "Two-factor authentication is available in Security Settings.",
    ],
}

# Simulated failure scenarios
FAILURE_SCENARIOS = {
    "What is the refund process for digital products?": {
        "failure": False,
        "expected_chunks": ["Digital downloads are non-refundable once accessed."],
    },
    "Can I get my money back?": {
        "failure": True,
        "failure_step": "retrieval_failure",
        "expected_chunks": [],  # ambiguous query, retrieval returns wrong chunks
    },
    "How long does shipping take?": {
        "failure": False,
        "expected_chunks": ["Standard shipping takes 5-7 business days."],
    },
    "Delete my account immediately": {
        "failure": True,
        "failure_step": "reasoning_failure",
        "expected_chunks": ["Account deletion requests take 30 days to process."],
    },
    "What is the return policy for software licenses?": {
        "failure": True,
        "failure_step": "hallucination",
        "expected_chunks": ["Digital downloads are non-refundable once accessed."],
    },
}


def build_pipeline(store: TraceStore):
    """Build the 3-step pipeline with trace decorators attached."""

    @trace_step(store, "retrieve")
    def retrieve(query: str) -> list[str]:
        """Retrieve relevant chunks from the knowledge base."""
        time.sleep(0.05)  # simulate latency
        query_lower = query.lower()
        for key, chunks in KNOWLEDGE_BASE.items():
            if key in query_lower:
                return chunks[:3]
        # Fallback: return first item from each section (simulates retrieval failure)
        return [chunks[0] for chunks in KNOWLEDGE_BASE.values()][:2]

    @trace_step(store, "rerank")
    def rerank(query: str, chunks: list[str]) -> list[str]:
        """Rerank chunks by relevance (simulated: keep top 2)."""
        time.sleep(0.02)  # simulate latency
        return chunks[:2]

    @trace_step(store, "generate")
    def generate(query: str, chunks: list[str]) -> str:
        """Generate a response using the query and context chunks."""
        time.sleep(0.1)  # simulate latency
        # Simulate: system picks the right answer from context
        if chunks:
            return f"Based on our policy: {chunks[0]}"
        return "I don't have information about that."

    return retrieve, rerank, generate


def run_pipeline(query: str, store: TraceStore) -> tuple[str, dict]:
    """Run the full 3-step pipeline for one query."""
    retrieve, rerank, generate = build_pipeline(store)

    trace_id = store.start_trace({"query": query})
    try:
        chunks = retrieve(query)
        top_chunks = rerank(query, chunks)
        answer = generate(query, top_chunks)
    except Exception as e:
        trace = store.end_trace(
            output=None,
            failure=True,
            failure_step="error",
            notes=str(e),
        )
        return "", trace

    # Determine if this trace should be flagged as a failure
    scenario = FAILURE_SCENARIOS.get(query, {})
    is_failure = scenario.get("failure", False)
    failure_step = scenario.get("failure_step") if is_failure else None

    trace = store.end_trace(
        output=answer,
        failure=is_failure,
        failure_step=failure_step,
    )
    return answer, trace


# ---------------------------------------------------------------------------
# CLI trace viewer
# ---------------------------------------------------------------------------

def view_traces(traces_path: str, filter_failures: bool = False) -> None:
    """Print a table of traces, optionally filtering to failures only."""
    path = Path(traces_path)
    if not path.exists():
        print(f"No traces file found at {traces_path}. Run --run-pipeline first.")
        return

    with open(path) as f:
        traces = [json.loads(line) for line in f if line.strip()]

    if filter_failures:
        traces = [t for t in traces if t["failure"]]
        print(f"\nFailed traces ({len(traces)} total):\n")
    else:
        print(f"\nAll traces ({len(traces)} total):\n")

    if not traces:
        print("  (none)")
        return

    for t in traces:
        flag = "[FAIL]" if t["failure"] else "[PASS]"
        query = t["input"].get("query", str(t["input"]))[:60]
        print(f"{flag} {t['trace_id']} | {t['total_latency_ms']}ms | {query}")
        for step in t["steps"]:
            err_suffix = f" ERROR: {step['error']['message'][:60]}" if step["error"] else ""
            print(f"       {step['name']:<12} {step['latency_ms']}ms{err_suffix}")
        if t["failure"] and t["failure_step"]:
            print(f"       >> Failure step: {t['failure_step']}")
        print()

    # Aggregate stats
    total = len(traces)
    failures = sum(1 for t in traces if t["failure"])
    avg_latency = sum(t["total_latency_ms"] for t in traces) / total if total else 0
    print(f"Summary: {total-failures}/{total} passed | avg latency: {avg_latency:.0f}ms")

    if failures > 0:
        from collections import Counter
        failure_types = Counter(
            t["failure_step"] for t in traces if t["failure"] and t["failure_step"]
        )
        print(f"\nFailure taxonomy:")
        for failure_type, count in failure_types.most_common():
            print(f"  {failure_type:<25} {count}")


def view_single_trace(trace_id: str, traces_path: str) -> None:
    """Print the full step-by-step breakdown for a single trace."""
    with open(traces_path) as f:
        traces = [json.loads(line) for line in f if line.strip()]

    match = next((t for t in traces if t["trace_id"] == trace_id), None)
    if not match:
        print(f"Trace {trace_id} not found.")
        return

    print(f"\nTrace: {match['trace_id']}")
    print(f"Time:  {match['timestamp']}")
    print(f"Input: {match['input']}")
    print(f"Total: {match['total_latency_ms']}ms | Failure: {match['failure']}")
    if match.get("failure_step"):
        print(f"Failed at: {match['failure_step']}")
    print()

    for i, step in enumerate(match["steps"], 1):
        print(f"  Step {i}: {step['name']}")
        print(f"    Input:   {str(step['input'])[:100]}")
        print(f"    Output:  {str(step['output'])[:100]}")
        print(f"    Latency: {step['latency_ms']}ms")
        if step["error"]:
            print(f"    ERROR:   {step['error']['message']}")
        print()

    print(f"Final output: {match['output']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

TRACES_PATH = "traces.jsonl"

TEST_QUERIES = list(FAILURE_SCENARIOS.keys())


def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 05-03: Trace review and failure taxonomy")
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Run the demo pipeline on test queries and write traces",
    )
    parser.add_argument(
        "--view",
        action="store_true",
        help="View all traces",
    )
    parser.add_argument(
        "--failures",
        action="store_true",
        help="Filter to failure traces only (use with --view)",
    )
    parser.add_argument(
        "--trace-id",
        type=str,
        default=None,
        help="Show full breakdown for a specific trace ID",
    )
    parser.add_argument(
        "--traces-file",
        type=str,
        default=TRACES_PATH,
        help=f"Path to traces file (default: {TRACES_PATH})",
    )
    args = parser.parse_args()

    if args.run_pipeline:
        print(f"Running pipeline on {len(TEST_QUERIES)} test queries...")
        store = TraceStore(args.traces_file)
        for query in TEST_QUERIES:
            answer, trace = run_pipeline(query, store)
            status = "FAIL" if trace["failure"] else "PASS"
            print(f"  [{status}] {query[:55]:<55} -> {answer[:40]}")
        print(f"\nTraces written to {args.traces_file}")
        print("Run with --view to inspect results.")
        return

    if args.trace_id:
        view_single_trace(args.trace_id, args.traces_file)
        return

    if args.view or args.failures:
        view_traces(args.traces_file, filter_failures=args.failures)
        return

    # Default: run pipeline + view
    print("Running demo pipeline and viewing traces...\n")
    store = TraceStore(args.traces_file)
    for query in TEST_QUERIES:
        run_pipeline(query, store)
    view_traces(args.traces_file)


if __name__ == "__main__":
    main()
