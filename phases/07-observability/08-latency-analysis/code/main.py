"""
L08: Latency - p50/p95/p99, TTFT, and Where Time Goes
Phase 07 - Observability

Demonstrates:
- TTFT (time-to-first-token) measurement with streaming API
- Percentile computation: p50, p75, p90, p95, p99
- LatencyProfiler: accumulates measurements, identifies bottleneck
- Why p99 matters more than mean for user retention
- Per-feature latency breakdown
"""

import random
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

import anthropic

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# TTFT Measurement
# ---------------------------------------------------------------------------


def stream_with_ttft(
    prompt: str,
    model: str = "claude-3-5-haiku-20241022",
) -> tuple[str, float, float]:
    """
    Stream a response and measure TTFT and total latency.

    TTFT = time from request start to receipt of the first text chunk.
    Total = time from request start to receipt of the last text chunk.

    Returns:
        (full_response_text, ttft_ms, total_latency_ms)
    """
    start = time.monotonic()
    ttft_ms: Optional[float] = None
    chunks: list[str] = []

    with client.messages.stream(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text_chunk in stream.text_stream:
            if ttft_ms is None:
                # First chunk received
                ttft_ms = (time.monotonic() - start) * 1000
            chunks.append(text_chunk)

    total_ms = (time.monotonic() - start) * 1000
    return "".join(chunks), ttft_ms or total_ms, total_ms


# ---------------------------------------------------------------------------
# Percentile Calculator
# ---------------------------------------------------------------------------


@dataclass
class PercentileReport:
    count: int
    p50_ms: float
    p75_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    mean_ms: float


def compute_percentiles(latencies_ms: list[float]) -> PercentileReport:
    """
    Compute latency percentiles using linear interpolation.

    This is the standard method used by most observability tools
    (Prometheus, Datadog, OpenTelemetry histogram approximations).
    """
    if not latencies_ms:
        raise ValueError("Cannot compute percentiles of empty list")

    sorted_vals = sorted(latencies_ms)
    n = len(sorted_vals)

    def percentile(p: float) -> float:
        idx = (p / 100) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return round(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac, 2)

    return PercentileReport(
        count=n,
        p50_ms=percentile(50),
        p75_ms=percentile(75),
        p90_ms=percentile(90),
        p95_ms=percentile(95),
        p99_ms=percentile(99),
        min_ms=round(sorted_vals[0], 2),
        max_ms=round(sorted_vals[-1], 2),
        mean_ms=round(statistics.mean(sorted_vals), 2),
    )


# ---------------------------------------------------------------------------
# LatencyProfiler
# ---------------------------------------------------------------------------


def _format_stats(s: PercentileReport) -> str:
    return (
        f"  min={s.min_ms:>7.0f}ms  "
        f"p50={s.p50_ms:>7.0f}ms  "
        f"p95={s.p95_ms:>7.0f}ms  "
        f"p99={s.p99_ms:>7.0f}ms  "
        f"max={s.max_ms:>7.0f}ms  "
        f"mean={s.mean_ms:>7.0f}ms"
    )


class LatencyProfiler:
    """
    Accumulates TTFT and total latency measurements across LLM calls.
    Computes percentile reports and identifies bottleneck components.

    Key insight: TTFT determines whether users perceive the app as responsive.
    Total latency determines when they can act on the full response.
    Track both separately.
    """

    def __init__(self):
        self._ttft: list[float] = []
        self._total: list[float] = []
        self._by_feature: dict[str, list[tuple[float, float]]] = defaultdict(list)

    def record(
        self,
        ttft_ms: float,
        total_ms: float,
        feature: str = "default",
    ) -> None:
        """Record a single measurement. Call this after each LLM request."""
        assert ttft_ms <= total_ms, "TTFT cannot exceed total latency"
        self._ttft.append(ttft_ms)
        self._total.append(total_ms)
        self._by_feature[feature].append((ttft_ms, total_ms))

    def report(self) -> str:
        """Render an ASCII latency report with bottleneck analysis."""
        if not self._ttft:
            return "No measurements recorded."

        ttft_stats = compute_percentiles(self._ttft)
        total_stats = compute_percentiles(self._total)
        gen_times = [t - f for f, t in zip(self._ttft, self._total)]
        gen_stats = compute_percentiles(gen_times)

        lines: list[str] = []
        lines.append("=" * 65)
        lines.append("LATENCY PROFILER REPORT")
        lines.append("=" * 65)
        lines.append(f"Measurements: {ttft_stats.count}")

        lines.append("\n-- Time-to-First-Token (TTFT) --")
        lines.append(_format_stats(ttft_stats))

        lines.append("\n-- Total Latency --")
        lines.append(_format_stats(total_stats))

        lines.append("\n-- Generation Time (Total minus TTFT) --")
        lines.append(_format_stats(gen_stats))

        # p99 breakdown
        lines.append("\n-- Bottleneck Analysis (p99) --")
        t_p99 = total_stats.p99_ms
        ttft_p99 = ttft_stats.p99_ms
        ttft_share = ttft_p99 / t_p99 * 100 if t_p99 > 0 else 0
        gen_share = 100 - ttft_share
        lines.append(
            f"  p99 total : {t_p99:.0f}ms"
        )
        lines.append(
            f"  TTFT share: {ttft_share:.0f}%  "
            f"  Generation share: {gen_share:.0f}%"
        )
        if ttft_share > 60:
            lines.append("  Bottleneck: network + prefill (reduce prompt length or use edge PoP)")
        elif gen_share > 60:
            lines.append("  Bottleneck: generation (reduce max_tokens or add explicit length limit)")
        else:
            lines.append("  Balanced: both TTFT and generation contribute roughly equally")

        # Mean vs p99 ratio - a key indicator of tail severity
        if total_stats.mean_ms > 0:
            ratio = total_stats.p99_ms / total_stats.mean_ms
            lines.append(f"\n  p99/mean ratio: {ratio:.1f}x")
            if ratio > 5:
                lines.append(
                    "  WARNING: p99 is >5x mean. Significant tail latency."
                    " Investigate outlier causes."
                )
            elif ratio > 3:
                lines.append(
                    "  NOTICE: p99 is 3-5x mean. Some users experience"
                    " substantially slower responses."
                )
            else:
                lines.append("  Tail looks controlled (p99 < 3x mean).")

        # Per-feature breakdown
        if len(self._by_feature) > 1:
            lines.append("\n-- Per-Feature p99 Total Latency --")
            lines.append(
                f"  {'Feature':<25} {'n':>5}  "
                f"{'p50':>8}  {'p95':>8}  {'p99':>8}"
            )
            lines.append("  " + "-" * 55)
            for feat, recs in sorted(
                self._by_feature.items(),
                key=lambda x: -compute_percentiles([r[1] for r in x[1]]).p99_ms,
            ):
                totals = [r[1] for r in recs]
                s = compute_percentiles(totals)
                lines.append(
                    f"  {feat:<25} {s.count:>5}  "
                    f"{s.p50_ms:>7.0f}ms  {s.p95_ms:>7.0f}ms  {s.p99_ms:>7.0f}ms"
                )

        lines.append("\n" + "=" * 65)
        return "\n".join(lines)

    def violations(self, threshold_ms: float = 5000.0) -> list[dict]:
        """
        Return calls that exceeded the latency threshold.
        Use to feed SLO dashboards or paging alerts.
        """
        return [
            {"index": i, "ttft_ms": ttft, "total_ms": total}
            for i, (ttft, total) in enumerate(zip(self._ttft, self._total))
            if total > threshold_ms
        ]

    def slo_compliance(self, threshold_ms: float = 3000.0) -> dict:
        """
        Compute SLO compliance: what fraction of calls were under threshold_ms.
        """
        total = len(self._total)
        compliant = sum(1 for t in self._total if t <= threshold_ms)
        return {
            "threshold_ms": threshold_ms,
            "total_calls": total,
            "compliant_calls": compliant,
            "slo_pct": round(compliant / total * 100, 2) if total > 0 else 0.0,
            "violated_calls": total - compliant,
        }


# ---------------------------------------------------------------------------
# Synthetic workload demo (no API key needed)
# ---------------------------------------------------------------------------


def _make_synthetic_latencies(n: int = 200, seed: int = 42) -> list[tuple[float, float]]:
    """
    Simulate realistic LLM latency distribution:
    - 75% of calls: fast warm path (200-1500ms total)
    - 15% of calls: moderate (1500-3500ms total)
    - 7%  of calls: slow (3500-6000ms total)
    - 3%  of calls: tail (6000-12000ms total)

    TTFT is always 15-35% of total latency for streaming.
    """
    rng = random.Random(seed)
    records = []
    for _ in range(n):
        r = rng.random()
        if r < 0.75:
            total = rng.uniform(200, 1500)
        elif r < 0.90:
            total = rng.uniform(1500, 3500)
        elif r < 0.97:
            total = rng.uniform(3500, 6000)
        else:
            total = rng.uniform(6000, 12000)
        ttft = total * rng.uniform(0.15, 0.35)
        records.append((ttft, total))
    return records


def demo() -> None:
    """Run the latency profiler on synthetic data."""
    print("=== LatencyProfiler Demo (Synthetic Data) ===\n")
    print(
        "Using synthetic latency distribution to demonstrate percentile analysis."
    )
    print("(No API key needed for this demo.)\n")

    profiler = LatencyProfiler()
    records = _make_synthetic_latencies(200)

    features = ["chat", "search", "summarize", "classify"]
    for i, (ttft, total) in enumerate(records):
        feature = features[i % len(features)]
        profiler.record(ttft_ms=ttft, total_ms=total, feature=feature)

    print(profiler.report())

    # SLO compliance check
    slo = profiler.slo_compliance(threshold_ms=3000.0)
    print(f"\nSLO Compliance (<3s): {slo['slo_pct']:.1f}% "
          f"({slo['compliant_calls']}/{slo['total_calls']} calls)")

    # Verify percentile ordering
    ttft_vals = [r[0] for r in records]
    stats = compute_percentiles(ttft_vals)
    assert stats.p50_ms <= stats.p95_ms <= stats.p99_ms <= stats.max_ms, \
        "Percentiles must be monotonically increasing"
    print("\nPercentile ordering assertion: PASS")

    # Show the mean vs p99 gap that justifies tracking p99
    total_vals = [r[1] for r in records]
    s = compute_percentiles(total_vals)
    print(f"\nKey finding: mean={s.mean_ms:.0f}ms vs p99={s.p99_ms:.0f}ms "
          f"({s.p99_ms/s.mean_ms:.1f}x)")
    print("This gap is why mean latency misleads and p99 is the user retention metric.")


if __name__ == "__main__":
    demo()
