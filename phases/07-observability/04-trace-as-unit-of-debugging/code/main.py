"""
The Trace as the Unit of Debugging -- Phase 07 Lesson 04
appliedaifromscratch.com

Demonstrates:
  1. TraceAnalyzer: detects 4 anomaly classes in JSONL trace logs
  2. debug_trace(): applies the 5-step trace review workflow
  3. Generating synthetic traces for testing the analyzer

Run:
    python main.py

No external dependencies needed for the analyzer.
For the Langfuse API integration, install: pip install langfuse
"""

import json
import os
import statistics
import tempfile
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# DATA MODEL
# ---------------------------------------------------------------------------


@dataclass
class TraceRecord:
    """A single trace record -- matches the LLMLogRecord schema from Lesson 01."""

    trace_id: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    cache_hit: bool
    error: Optional[str]
    # Content fields (optional -- only set when gen_ai.content.* events are captured)
    prompt_text: Optional[str] = None
    completion_text: Optional[str] = None


def load_traces(path: str) -> list[TraceRecord]:
    """Load trace records from a JSONL file."""
    records = []
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(
                    TraceRecord(
                        trace_id=data.get("trace_id", f"unknown-{i}"),
                        model=data.get("model", "unknown"),
                        prompt_version=data.get("prompt_version", "unknown"),
                        input_tokens=data.get("input_tokens", 0),
                        output_tokens=data.get("output_tokens", 0),
                        cost_usd=data.get("cost_usd", 0.0),
                        latency_ms=data.get("latency_ms", 0.0),
                        cache_hit=data.get("cache_hit", False),
                        error=data.get("error"),
                        prompt_text=data.get("prompt_text"),
                        completion_text=data.get("completion_text"),
                    )
                )
            except json.JSONDecodeError as exc:
                print(f"  Warning: skipping malformed line {i + 1}: {exc}")
    return records


# ---------------------------------------------------------------------------
# ANOMALY DETECTION
# ---------------------------------------------------------------------------


@dataclass
class Anomaly:
    trace_id: str
    anomaly_type: str  # "error" | "high_latency" | "high_cost" | "low_token_efficiency"
    severity: str      # "warning" | "critical"
    detail: str
    record: TraceRecord


class TraceAnalyzer:
    """
    Analyzes a batch of trace records for 4 anomaly classes:

    1. error            -- any span with a non-null error field
    2. high_latency     -- latency_ms exceeds threshold (default: 2x P95 baseline)
    3. high_cost        -- cost_usd exceeds threshold (default: 2x P95 baseline)
    4. low_token_efficiency -- output_tokens / input_tokens < threshold (default: 0.05)

    Low token efficiency is a signal for prompt bloat: a very large prompt
    that produces a tiny response, common when retrieval injects irrelevant context.
    """

    def __init__(
        self,
        records: list[TraceRecord],
        latency_threshold_ms: Optional[float] = None,
        cost_threshold_usd: Optional[float] = None,
        token_efficiency_threshold: float = 0.05,
    ):
        self.records = records
        self.token_efficiency_threshold = token_efficiency_threshold

        # Compute P95 baselines from successful records
        successful = [r for r in records if r.error is None and r.input_tokens > 0]

        if len(successful) >= 20:
            latency_vals = sorted(r.latency_ms for r in successful)
            cost_vals = sorted(r.cost_usd for r in successful)
            # P95 = 95th percentile
            p95_idx = int(len(successful) * 0.95)
            self.p95_latency = latency_vals[p95_idx]
            self.p95_cost = cost_vals[p95_idx]
        elif successful:
            self.p95_latency = max(r.latency_ms for r in successful)
            self.p95_cost = max(r.cost_usd for r in successful)
        else:
            self.p95_latency = 0.0
            self.p95_cost = 0.0

        # Use explicit thresholds if provided, else 2x P95 baseline
        self.latency_threshold = latency_threshold_ms or (self.p95_latency * 2)
        self.cost_threshold = cost_threshold_usd or (self.p95_cost * 2)

    def analyze(self) -> list[Anomaly]:
        """Scan all records and return anomalies, sorted by severity (critical first)."""
        anomalies: list[Anomaly] = []
        for record in self.records:
            anomalies.extend(self._check_record(record))
        return sorted(
            anomalies,
            key=lambda a: (a.severity == "critical", a.anomaly_type),
            reverse=True,
        )

    def _check_record(self, r: TraceRecord) -> list[Anomaly]:
        found: list[Anomaly] = []

        # Anomaly 1: error spans
        if r.error is not None:
            found.append(
                Anomaly(
                    trace_id=r.trace_id,
                    anomaly_type="error",
                    severity="critical",
                    detail=f"{r.error} | prompt_version={r.prompt_version} | model={r.model}",
                    record=r,
                )
            )

        # Anomaly 2: high latency
        if self.latency_threshold > 0 and r.latency_ms > self.latency_threshold:
            severity = (
                "critical" if r.latency_ms > self.latency_threshold * 2 else "warning"
            )
            found.append(
                Anomaly(
                    trace_id=r.trace_id,
                    anomaly_type="high_latency",
                    severity=severity,
                    detail=(
                        f"latency={r.latency_ms:.0f}ms "
                        f"(threshold={self.latency_threshold:.0f}ms) | "
                        f"prompt_version={r.prompt_version}"
                    ),
                    record=r,
                )
            )

        # Anomaly 3: high cost
        if self.cost_threshold > 0 and r.cost_usd > self.cost_threshold:
            found.append(
                Anomaly(
                    trace_id=r.trace_id,
                    anomaly_type="high_cost",
                    severity="warning",
                    detail=(
                        f"cost=${r.cost_usd:.6f} (threshold=${self.cost_threshold:.6f}) | "
                        f"tokens={r.input_tokens}in/{r.output_tokens}out"
                    ),
                    record=r,
                )
            )

        # Anomaly 4: low token efficiency
        if r.input_tokens > 100 and r.output_tokens > 0:
            efficiency = r.output_tokens / r.input_tokens
            if efficiency < self.token_efficiency_threshold:
                found.append(
                    Anomaly(
                        trace_id=r.trace_id,
                        anomaly_type="low_token_efficiency",
                        severity="warning",
                        detail=(
                            f"efficiency={efficiency:.3f} "
                            f"(threshold={self.token_efficiency_threshold:.3f}) | "
                            f"{r.input_tokens}in/{r.output_tokens}out"
                        ),
                        record=r,
                    )
                )

        return found

    def summary(self) -> dict:
        """Return a summary dict suitable for dashboards and health check endpoints."""
        anomalies = self.analyze()
        total = len(self.records)
        return {
            "total_traces": total,
            "error_count": sum(1 for r in self.records if r.error),
            "error_rate": sum(1 for r in self.records if r.error) / max(total, 1),
            "cache_hit_rate": sum(1 for r in self.records if r.cache_hit) / max(total, 1),
            "p95_latency_ms": round(self.p95_latency, 1),
            "p95_cost_usd": round(self.p95_cost, 8),
            "anomaly_count": len(anomalies),
            "critical_count": sum(1 for a in anomalies if a.severity == "critical"),
        }


# ---------------------------------------------------------------------------
# 5-STEP TRACE DEBUG WORKFLOW
# ---------------------------------------------------------------------------


def debug_trace(trace_id: str, records: list[TraceRecord]) -> None:
    """
    Apply the 5-step trace debug workflow to a specific trace.

    Step 1: Find the failing trace by ID
    Step 2: Expand the span tree (simplified for single-record traces)
    Step 3: Read prompt + response content
    Step 4: Check token counts and timing
    Step 5: Identify root cause category
    """
    record = next((r for r in records if r.trace_id == trace_id), None)
    if not record:
        print(f"Trace {trace_id} not found in loaded records")
        return

    print(f"\n{'='*60}")
    print(f"5-Step Trace Debug: {trace_id}")
    print(f"{'='*60}\n")

    # --- Step 1: Find ---
    print("STEP 1: Found trace")
    print(f"  model={record.model}")
    print(f"  prompt_version={record.prompt_version}")
    print(f"  error={'NONE' if not record.error else record.error}")
    print()

    # --- Step 2: Span tree ---
    print("STEP 2: Span tree")
    status = "ERROR" if record.error else "OK"
    print(f"  [root span]      status={status} | latency={record.latency_ms:.0f}ms")
    print(f"    [LLM call span] {record.model}")
    print(f"                    input={record.input_tokens} | output={record.output_tokens}")
    print(f"                    cache_hit={record.cache_hit}")
    print()

    # --- Step 3: Prompt + response ---
    print("STEP 3: Prompt + response content")
    if record.prompt_text:
        preview = record.prompt_text[:300].replace("\n", " ")
        print(f"  Prompt: {preview}...")
    else:
        print("  Prompt: not captured")
        print("  To enable: add gen_ai.content.prompt event in your instrumentation")

    if record.completion_text:
        preview = record.completion_text[:300].replace("\n", " ")
        print(f"  Response: {preview}...")
    else:
        print("  Response: not captured")
    print()

    # --- Step 4: Token counts and timing ---
    print("STEP 4: Token counts and timing")
    if record.input_tokens > 0:
        efficiency = record.output_tokens / record.input_tokens
        print(f"  input_tokens:    {record.input_tokens}")
        print(f"  output_tokens:   {record.output_tokens}")
        print(f"  token_efficiency: {efficiency:.3f}  (output/input; low = prompt bloat)")
        print(f"  cost_usd:        ${record.cost_usd:.6f}")
        print(f"  latency_ms:      {record.latency_ms:.0f}ms")
    else:
        print("  No token data (API call failed before tokens were counted)")
    print()

    # --- Step 5: Root cause ---
    print("STEP 5: Root cause category")
    if record.error:
        print(f"  CATEGORY: API/infrastructure failure")
        print(f"  EVIDENCE: error={record.error}")
        print("  NEXT STEP: check Anthropic status page; inspect retry logic")
    elif record.input_tokens > 0 and record.output_tokens / record.input_tokens < 0.05:
        print("  CATEGORY: Prompt bloat / low token efficiency")
        print(f"  EVIDENCE: efficiency={record.output_tokens / record.input_tokens:.3f}")
        print("  NEXT STEP: review context injection; check RAG retrieval quality")
    elif record.latency_ms > 10000:
        print("  CATEGORY: Model or tool latency spike")
        print(f"  EVIDENCE: latency={record.latency_ms:.0f}ms")
        print("  NEXT STEP: check Anthropic status page; review tool call timing")
    elif record.cost_usd > 0.01:
        print("  CATEGORY: Runaway cost")
        print(f"  EVIDENCE: cost=${record.cost_usd:.4f}")
        print("  NEXT STEP: check max_tokens setting; review prompt template for length")
    else:
        print("  CATEGORY: Unclear from metadata alone")
        print("  NEXT STEP: enable gen_ai.content.* events to capture prompt + response")
    print()


# ---------------------------------------------------------------------------
# SYNTHETIC TRACE GENERATOR (for testing)
# ---------------------------------------------------------------------------


def generate_synthetic_traces(n: int = 50) -> list[dict]:
    """
    Generate synthetic trace records for testing the TraceAnalyzer.
    Includes a mix of normal, error, high-latency, and low-efficiency traces.
    """
    import random

    random.seed(42)
    traces = []

    for i in range(n):
        trace_id = f"trace-{i:04d}"
        is_error = random.random() < 0.05  # 5% error rate
        is_high_latency = random.random() < 0.03  # 3% high latency
        is_low_efficiency = random.random() < 0.04  # 4% prompt bloat

        if is_error:
            traces.append({
                "trace_id": trace_id,
                "model": "claude-3-5-haiku-20241022",
                "prompt_version": "support-v2",
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "latency_ms": round(random.uniform(50, 200), 1),
                "cache_hit": False,
                "error": random.choice(["RateLimitError", "APITimeoutError", "OverloadedError"]),
            })
        elif is_high_latency:
            traces.append({
                "trace_id": trace_id,
                "model": "claude-3-5-haiku-20241022",
                "prompt_version": "support-v2",
                "input_tokens": random.randint(40, 200),
                "output_tokens": random.randint(50, 300),
                "cost_usd": round(random.uniform(0.0001, 0.001), 8),
                "latency_ms": round(random.uniform(8000, 20000), 1),
                "cache_hit": False,
                "error": None,
            })
        elif is_low_efficiency:
            traces.append({
                "trace_id": trace_id,
                "model": "claude-3-5-haiku-20241022",
                "prompt_version": "rag-v3",
                "input_tokens": random.randint(3000, 8000),
                "output_tokens": random.randint(5, 30),
                "cost_usd": round(random.uniform(0.003, 0.008), 8),
                "latency_ms": round(random.uniform(400, 1200), 1),
                "cache_hit": False,
                "error": None,
            })
        else:
            input_tokens = random.randint(30, 300)
            output_tokens = random.randint(50, 500)
            traces.append({
                "trace_id": trace_id,
                "model": "claude-3-5-haiku-20241022",
                "prompt_version": random.choice(["support-v2", "general-v1"]),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round((input_tokens * 0.80 + output_tokens * 4.0) / 1_000_000, 8),
                "latency_ms": round(random.uniform(200, 1500), 1),
                "cache_hit": random.random() < 0.3,
                "error": None,
            })

    return traces


# ---------------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== Trace Analyzer Demo ===\n")

    # Generate synthetic traces
    trace_data = generate_synthetic_traces(100)

    # Write to temp JSONL file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False
    ) as f:
        for t in trace_data:
            f.write(json.dumps(t) + "\n")
        tmppath = f.name

    print(f"Generated 100 synthetic traces -> {tmppath}\n")

    # Load and analyze
    records = load_traces(tmppath)
    analyzer = TraceAnalyzer(records, latency_threshold_ms=3000, cost_threshold_usd=0.005)

    # Print summary
    summary = analyzer.summary()
    print("=== Summary ===")
    for k, v in summary.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")
    print()

    # Show top anomalies
    anomalies = analyzer.analyze()
    print(f"=== Top Anomalies ({len(anomalies)} total) ===")
    for a in anomalies[:8]:
        icon = "CRIT" if a.severity == "critical" else "WARN"
        print(f"  [{icon}] {a.anomaly_type:<22} | trace={a.trace_id} | {a.detail}")
    print()

    # Run 5-step debug on first error trace
    error_traces = [r for r in records if r.error]
    if error_traces:
        print("=== Running 5-step debug on first error trace ===")
        debug_trace(error_traces[0].trace_id, records)

    # Run 5-step debug on first high-latency trace
    high_lat = [a for a in anomalies if a.anomaly_type == "high_latency"]
    if high_lat:
        print("=== Running 5-step debug on first high-latency trace ===")
        debug_trace(high_lat[0].trace_id, records)

    # Cleanup
    os.unlink(tmppath)

    print("\nKey insight: the trace is the artifact that connects a user complaint")
    print("to the exact prompt, response, and timing that caused it.")
    print("Without traces, you debug production AI with print() statements.")


if __name__ == "__main__":
    main()
