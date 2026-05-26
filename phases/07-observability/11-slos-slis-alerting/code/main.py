"""
SLO Monitor - Phase 07, Lesson 11
Tracks 6 AI-specific SLIs, computes error budget burn rate, and emits structured alerts.

Usage:
    python main.py

No external dependencies beyond Python stdlib.
"""

from __future__ import annotations

import dataclasses
import random
import time
from collections import deque
from enum import Enum
from typing import Optional


class AlertLevel(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclasses.dataclass
class RequestEvent:
    """A single LLM request event, recorded after the call completes."""
    ttft_ms: float
    total_latency_ms: float
    error: bool
    cache_hit: bool
    cost_usd: float
    eval_score: Optional[float] = None  # None if eval not run on this request
    timestamp: float = dataclasses.field(default_factory=time.time)


@dataclasses.dataclass
class SLOAlert:
    sli_name: str
    level: AlertLevel
    message: str
    current_value: float
    threshold: float
    breach_duration_seconds: float


@dataclasses.dataclass
class SLOStatus:
    availability: float
    ttft_p95_ms: float
    error_rate: float
    eval_score_mean: float
    cache_hit_rate: float
    cost_p95_usd: float
    alerts: list[SLOAlert]

    def to_dict(self) -> dict:
        return {
            "availability": self.availability,
            "ttft_p95_ms": self.ttft_p95_ms,
            "error_rate": self.error_rate,
            "eval_score_mean": self.eval_score_mean,
            "cache_hit_rate": self.cache_hit_rate,
            "cost_p95_usd": self.cost_p95_usd,
            "alert_count": len(self.alerts),
        }


class SLOMonitor:
    """
    Tracks the 6 AI-specific SLIs and emits alerts when thresholds are breached.

    SLI windows:
      - availability:   30 minutes (rolling)
      - ttft_p95:       15 minutes (rolling)
      - error_rate:     15 minutes (rolling)
      - eval_score:     24 hours (rolling, sampled requests only)
      - cache_hit_rate: 60 minutes (rolling)
      - cost_p95:       60 minutes (rolling)

    SLO targets (defaults, override in constructor):
      - availability >= 99.5%
      - ttft p95 <= 2000ms
      - error rate <= 1.0%
      - eval score mean >= 0.80
      - cache hit rate >= 40%
      - cost p95 <= $0.005
    """

    def __init__(
        self,
        availability_target: float = 0.995,
        ttft_p95_target_ms: float = 2000,
        error_rate_target: float = 0.01,
        eval_score_target: float = 0.80,
        cache_hit_rate_target: float = 0.40,
        cost_p95_target_usd: float = 0.005,
    ):
        self.targets = {
            "availability": availability_target,
            "ttft_p95_ms": ttft_p95_target_ms,
            "error_rate": error_rate_target,
            "eval_score_mean": eval_score_target,
            "cache_hit_rate": cache_hit_rate_target,
            "cost_p95_usd": cost_p95_target_usd,
        }
        # Rolling event buffers with time-based windowing
        self._events: deque[RequestEvent] = deque(maxlen=10_000)

        # Track when each SLI first entered breach state
        self._breach_start: dict[str, Optional[float]] = {k: None for k in self.targets}

    def record(self, event: RequestEvent) -> None:
        """Record a completed LLM request."""
        self._events.append(event)

    def _events_in_window(self, window_seconds: float) -> list[RequestEvent]:
        cutoff = time.time() - window_seconds
        return [e for e in self._events if e.timestamp >= cutoff]

    def _percentile(self, values: list[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = min(int(len(sorted_vals) * p / 100), len(sorted_vals) - 1)
        return sorted_vals[idx]

    def _compute_slis(self) -> dict[str, float]:
        now = time.time()

        events_30m = self._events_in_window(1800)   # availability
        events_15m = self._events_in_window(900)    # ttft, error_rate
        events_60m = self._events_in_window(3600)   # cache, cost
        events_24h = self._events_in_window(86400)  # eval score

        # Availability: fraction of requests that got a response (non-error)
        availability = (
            sum(1 for e in events_30m if not e.error) / len(events_30m)
            if events_30m else 1.0
        )

        # TTFT p95
        ttft_vals = [e.ttft_ms for e in events_15m if not e.error]
        ttft_p95 = self._percentile(ttft_vals, 95)

        # Error rate
        error_rate = (
            sum(1 for e in events_15m if e.error) / len(events_15m)
            if events_15m else 0.0
        )

        # Eval score mean (only requests where eval was run)
        eval_events = [e for e in events_24h if e.eval_score is not None]
        eval_mean = (
            sum(e.eval_score for e in eval_events) / len(eval_events)
            if eval_events else self.targets["eval_score_mean"]  # default OK if no data
        )

        # Cache hit rate
        cache_hit_rate = (
            sum(1 for e in events_60m if e.cache_hit) / len(events_60m)
            if events_60m else 0.0
        )

        # Cost p95
        cost_vals = [e.cost_usd for e in events_60m]
        cost_p95 = self._percentile(cost_vals, 95)

        return {
            "availability": availability,
            "ttft_p95_ms": ttft_p95,
            "error_rate": error_rate,
            "eval_score_mean": eval_mean,
            "cache_hit_rate": cache_hit_rate,
            "cost_p95_usd": cost_p95,
        }

    def check_slos(self) -> list[SLOAlert]:
        """Return list of active SLO alerts. Empty list means all SLIs are healthy."""
        slis = self._compute_slis()
        now = time.time()
        alerts: list[SLOAlert] = []

        # Check each SLI against its target
        checks = [
            ("availability", slis["availability"], self.targets["availability"],
             lambda v, t: v < t, "Availability {:.1%} is below SLO target {:.1%}"),
            ("ttft_p95_ms", slis["ttft_p95_ms"], self.targets["ttft_p95_ms"],
             lambda v, t: v > t, "TTFT p95 {:.0f}ms exceeds SLO target {:.0f}ms"),
            ("error_rate", slis["error_rate"], self.targets["error_rate"],
             lambda v, t: v > t, "Error rate {:.1%} exceeds SLO target {:.1%}"),
            ("eval_score_mean", slis["eval_score_mean"], self.targets["eval_score_mean"],
             lambda v, t: v < t, "Mean eval score {:.2f} is below SLO target {:.2f}"),
            ("cache_hit_rate", slis["cache_hit_rate"], self.targets["cache_hit_rate"],
             lambda v, t: v < t, "Cache hit rate {:.1%} is below SLO target {:.1%}"),
            ("cost_p95_usd", slis["cost_p95_usd"], self.targets["cost_p95_usd"],
             lambda v, t: v > t, "Cost p95 ${:.4f} exceeds SLO target ${:.4f}"),
        ]

        for sli_name, value, target, breached_fn, message_template in checks:
            if breached_fn(value, target):
                if self._breach_start[sli_name] is None:
                    self._breach_start[sli_name] = now
                breach_duration = now - self._breach_start[sli_name]

                # Escalate to CRITICAL after 15 minutes
                level = AlertLevel.CRITICAL if breach_duration > 900 else AlertLevel.WARNING
                message = message_template.format(value, target)

                alerts.append(SLOAlert(
                    sli_name=sli_name,
                    level=level,
                    message=message,
                    current_value=value,
                    threshold=target,
                    breach_duration_seconds=breach_duration,
                ))
            else:
                self._breach_start[sli_name] = None  # Reset breach timer

        return alerts

    def status(self) -> SLOStatus:
        """Return current SLO status with all SLI values and active alerts."""
        slis = self._compute_slis()
        alerts = self.check_slos()
        return SLOStatus(alerts=alerts, **slis)

    def print_status(self) -> None:
        s = self.status()
        print("\nSLO Status Report")
        print("-" * 50)
        print(f"availability:    {s.availability:.1%}  [target >= {self.targets['availability']:.1%}]")
        print(f"ttft_p95:        {s.ttft_p95_ms:.0f}ms  [target <= {self.targets['ttft_p95_ms']:.0f}ms]")
        print(f"error_rate:      {s.error_rate:.2%}  [target <= {self.targets['error_rate']:.1%}]")
        print(f"eval_score_mean: {s.eval_score_mean:.2f}  [target >= {self.targets['eval_score_mean']:.2f}]")
        print(f"cache_hit_rate:  {s.cache_hit_rate:.1%}  [target >= {self.targets['cache_hit_rate']:.1%}]")
        print(f"cost_p95:        ${s.cost_p95_usd:.4f}  [target <= ${self.targets['cost_p95_usd']:.4f}]")
        if s.alerts:
            print(f"\nActive alerts: {len(s.alerts)}")
            for a in s.alerts:
                print(f"  [{a.level.value}] {a.sli_name}: {a.message}")
        else:
            print("\nAll SLIs within target.")


def _generate_healthy_events(count: int = 100) -> list[RequestEvent]:
    """Generate realistic healthy traffic for demonstration."""
    events = []
    now = time.time()
    for i in range(count):
        events.append(RequestEvent(
            ttft_ms=random.gauss(400, 80),
            total_latency_ms=random.gauss(2000, 400),
            error=random.random() < 0.003,
            cache_hit=random.random() < 0.55,
            cost_usd=random.gauss(0.003, 0.0005),
            eval_score=random.gauss(0.87, 0.05) if random.random() < 0.1 else None,
            timestamp=now - random.uniform(0, 3600),
        ))
    return events


def _generate_degraded_events(count: int = 50) -> list[RequestEvent]:
    """Generate traffic showing SLO violations."""
    events = []
    now = time.time()
    for i in range(count):
        events.append(RequestEvent(
            ttft_ms=random.gauss(2500, 300),    # TTFT breach
            total_latency_ms=random.gauss(8000, 1000),
            error=random.random() < 0.03,       # Error rate at edge
            cache_hit=random.random() < 0.15,   # Cache hit rate breach
            cost_usd=random.gauss(0.007, 0.001), # Cost breach
            eval_score=random.gauss(0.72, 0.04) if random.random() < 0.1 else None,  # Eval breach
            timestamp=now - random.uniform(0, 900),  # Recent events (15 min window)
        ))
    return events


def main():
    print("=== Healthy System ===")
    monitor = SLOMonitor()
    for event in _generate_healthy_events(100):
        monitor.record(event)
    monitor.print_status()

    print("\n\n=== Degraded System ===")
    monitor2 = SLOMonitor()
    # Add some healthy historical events
    for event in _generate_healthy_events(50):
        monitor2.record(event)
    # Add recent degraded events
    for event in _generate_degraded_events(50):
        monitor2.record(event)
    # Simulate breach duration by backdating the breach start
    for key in monitor2._breach_start:
        monitor2._breach_start[key] = time.time() - 1200  # 20 min ago
    monitor2.print_status()


if __name__ == "__main__":
    main()
