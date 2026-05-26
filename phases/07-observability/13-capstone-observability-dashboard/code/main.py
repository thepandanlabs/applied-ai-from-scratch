"""
Observability Module - Phase 07, Lesson 13 (Capstone)
Drop-in observability layer for any FastAPI LLM service.

Components:
  - OpenTelemetry tracing with gen_ai.* attributes
  - Structured JSONL logging with PII field scrubbing
  - Cost accounting to SQLite
  - Latency profiling (TTFT + total)
  - SLO monitor (6 AI SLIs)
  - ASCII dashboard (stdout, configurable refresh)

Usage:
    python main.py --demo         # Standalone demo with simulated traffic
    uvicorn main:app --port 8080  # FastAPI service mode
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from collections import deque
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ObsConfig:
    service_name: str = "llm-service"
    db_path: str = "cost_log.db"
    log_path: str = "app.jsonl"
    langfuse_enabled: bool = False
    dashboard_enabled: bool = True
    pii_fields: list[str] = dataclasses.field(
        default_factory=lambda: ["email", "phone", "ssn", "credit_card"]
    )
    # SLO targets
    availability_target: float = 0.995
    ttft_p95_target_ms: float = 2000.0
    error_rate_target: float = 0.01
    eval_score_target: float = 0.80
    cache_hit_rate_target: float = 0.40
    cost_p95_target_usd: float = 0.005


# ---------------------------------------------------------------------------
# PII Scrubber
# ---------------------------------------------------------------------------

class PIIScrubber:
    """Removes PII from log fields before writing to disk."""

    PATTERNS = {
        "email": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
        "phone": re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "credit_card": re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
    }

    def scrub(self, text: str) -> str:
        for pattern_name, pattern in self.PATTERNS.items():
            text = pattern.sub(f"[{pattern_name.upper()}_REDACTED]", text)
        return text


# ---------------------------------------------------------------------------
# Structured Logger
# ---------------------------------------------------------------------------

class StructuredLogger:
    def __init__(self, log_path: str, service_name: str, pii_scrubber: PIIScrubber):
        self.log_path = log_path
        self.service_name = service_name
        self.scrubber = pii_scrubber
        self._lock = threading.Lock()

    def log(self, level: str, event: str, **fields) -> None:
        # Scrub string fields that might contain PII
        scrubbed = {}
        for k, v in fields.items():
            if isinstance(v, str):
                scrubbed[k] = self.scrubber.scrub(v)
            else:
                scrubbed[k] = v

        record = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "service": self.service_name,
            "event": event,
            **scrubbed,
        }
        line = json.dumps(record)
        with self._lock:
            with open(self.log_path, "a") as f:
                f.write(line + "\n")

    def info(self, event: str, **fields):
        self.log("INFO", event, **fields)

    def warning(self, event: str, **fields):
        self.log("WARNING", event, **fields)

    def error(self, event: str, **fields):
        self.log("ERROR", event, **fields)


# ---------------------------------------------------------------------------
# Cost Accountant
# ---------------------------------------------------------------------------

class CostAccountant:
    """Records per-call LLM costs to SQLite with hourly rollups."""

    # Input/output pricing per token (USD) - update when pricing changes
    MODEL_PRICING = {
        "claude-3-5-haiku-20241022": {"input": 0.000001, "output": 0.000005},
        "claude-sonnet-4-5":        {"input": 0.000003, "output": 0.000015},
    }

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    model TEXT NOT NULL,
                    operation TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    cache_read_tokens INTEGER DEFAULT 0,
                    cost_usd REAL,
                    ttft_ms REAL,
                    total_latency_ms REAL,
                    error INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def record_call(
        self,
        model: str,
        operation: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        ttft_ms: float,
        total_latency_ms: float,
        error: bool = False,
    ) -> float:
        pricing = self.MODEL_PRICING.get(model, {"input": 0.000003, "output": 0.000015})
        cost = (
            (input_tokens - cache_read_tokens) * pricing["input"]
            + cache_read_tokens * pricing["input"] * 0.1  # cache read is 10% of input price
            + output_tokens * pricing["output"]
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO llm_calls
                   (ts, model, operation, input_tokens, output_tokens,
                    cache_read_tokens, cost_usd, ttft_ms, total_latency_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (time.time(), model, operation, input_tokens, output_tokens,
                 cache_read_tokens, cost, ttft_ms, total_latency_ms, int(error)),
            )
        return cost

    def hourly_cost(self) -> float:
        cutoff = time.time() - 3600
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE ts >= ?",
                (cutoff,)
            ).fetchone()
        return row[0] if row else 0.0

    def recent_costs(self, window_seconds: float = 3600) -> list[float]:
        cutoff = time.time() - window_seconds
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT cost_usd FROM llm_calls WHERE ts >= ?",
                (cutoff,)
            ).fetchall()
        return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Latency Profiler
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class LatencyStats:
    ttft_p50_ms: float
    ttft_p95_ms: float
    total_p50_ms: float
    total_p95_ms: float
    sample_count: int


class LatencyProfiler:
    def __init__(self, window_seconds: float = 900):  # 15 min
        self.window_seconds = window_seconds
        self._samples: deque = deque(maxlen=10_000)

    def record(self, ttft_ms: float, total_ms: float, ts: Optional[float] = None):
        self._samples.append((ts or time.time(), ttft_ms, total_ms))

    def _recent(self) -> list[tuple]:
        cutoff = time.time() - self.window_seconds
        return [(t, ttft, total) for t, ttft, total in self._samples if t >= cutoff]

    def _percentile(self, vals: list[float], p: float) -> float:
        if not vals:
            return 0.0
        sorted_vals = sorted(vals)
        idx = min(int(len(sorted_vals) * p / 100), len(sorted_vals) - 1)
        return sorted_vals[idx]

    def stats(self) -> LatencyStats:
        recent = self._recent()
        ttfts = [r[1] for r in recent]
        totals = [r[2] for r in recent]
        return LatencyStats(
            ttft_p50_ms=self._percentile(ttfts, 50),
            ttft_p95_ms=self._percentile(ttfts, 95),
            total_p50_ms=self._percentile(totals, 50),
            total_p95_ms=self._percentile(totals, 95),
            sample_count=len(recent),
        )


# ---------------------------------------------------------------------------
# SLO Monitor (simplified, from Lesson 11)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class SLISnapshot:
    availability: float
    ttft_p95_ms: float
    error_rate: float
    eval_score_mean: float
    cache_hit_rate: float
    cost_p95_usd: float
    active_alerts: int

    def overall_status(self) -> str:
        return "ALERT" if self.active_alerts > 0 else "OK"


class SimpleSLOMonitor:
    def __init__(self, config: ObsConfig):
        self.config = config
        self._events: deque = deque(maxlen=5_000)

    @dataclasses.dataclass
    class Event:
        ts: float
        error: bool
        ttft_ms: float
        total_ms: float
        cost_usd: float
        cache_hit: bool
        eval_score: Optional[float] = None

    def record(self, **kwargs):
        self._events.append(self.Event(ts=time.time(), **kwargs))

    def _window(self, seconds: float) -> list:
        cutoff = time.time() - seconds
        return [e for e in self._events if e.ts >= cutoff]

    def _pct(self, vals: list[float], p: float) -> float:
        if not vals:
            return 0.0
        s = sorted(vals)
        return s[min(int(len(s) * p / 100), len(s) - 1)]

    def snapshot(self) -> SLISnapshot:
        e30m = self._window(1800)
        e15m = self._window(900)
        e60m = self._window(3600)
        e24h = self._window(86400)

        avail = sum(1 for e in e30m if not e.error) / len(e30m) if e30m else 1.0
        ttft_p95 = self._pct([e.ttft_ms for e in e15m if not e.error], 95)
        err_rate = sum(1 for e in e15m if e.error) / len(e15m) if e15m else 0.0
        scored = [e for e in e24h if e.eval_score is not None]
        eval_mean = sum(e.eval_score for e in scored) / len(scored) if scored else self.config.eval_score_target
        cache_rate = sum(1 for e in e60m if e.cache_hit) / len(e60m) if e60m else 0.0
        cost_p95 = self._pct([e.cost_usd for e in e60m], 95)

        # Count alerts
        alerts = 0
        if avail < self.config.availability_target: alerts += 1
        if ttft_p95 > self.config.ttft_p95_target_ms: alerts += 1
        if err_rate > self.config.error_rate_target: alerts += 1
        if eval_mean < self.config.eval_score_target: alerts += 1
        if cache_rate < self.config.cache_hit_rate_target: alerts += 1
        if cost_p95 > self.config.cost_p95_target_usd: alerts += 1

        return SLISnapshot(
            availability=avail,
            ttft_p95_ms=ttft_p95,
            error_rate=err_rate,
            eval_score_mean=eval_mean,
            cache_hit_rate=cache_rate,
            cost_p95_usd=cost_p95,
            active_alerts=alerts,
        )


# ---------------------------------------------------------------------------
# Trace Context (replaces full OTel for standalone demo)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class LLMCallContext:
    operation: str
    user_id: Optional[str]
    _start: float = dataclasses.field(default_factory=time.perf_counter)
    _ttft: Optional[float] = None
    _obs: Any = None

    def record_ttft(self):
        if self._ttft is None:
            self._ttft = (time.perf_counter() - self._start) * 1000

    def record(self, response: Any, error: bool = False, eval_score: Optional[float] = None):
        total_ms = (time.perf_counter() - self._start) * 1000
        ttft_ms = self._ttft or total_ms

        # Extract usage from response (supports both real and mock)
        try:
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            model = response.model if hasattr(response, "model") else "claude-3-5-haiku-20241022"
        except Exception:
            input_tokens = 50
            output_tokens = 100
            cache_read_tokens = 0
            model = "claude-3-5-haiku-20241022"

        cache_hit = cache_read_tokens > 0

        if self._obs:
            # Record to all components
            cost = self._obs.cost_accountant.record_call(
                model=model,
                operation=self.operation,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                ttft_ms=ttft_ms,
                total_latency_ms=total_ms,
                error=error,
            )
            self._obs.latency_profiler.record(ttft_ms, total_ms)
            self._obs.slo_monitor.record(
                error=error,
                ttft_ms=ttft_ms,
                total_ms=total_ms,
                cost_usd=cost,
                cache_hit=cache_hit,
                eval_score=eval_score,
            )
            self._obs.logger.info(
                "llm_call",
                operation=self.operation,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_hit=cache_hit,
                ttft_ms=round(ttft_ms, 1),
                total_ms=round(total_ms, 1),
                cost_usd=round(cost, 6),
                error=error,
            )


# ---------------------------------------------------------------------------
# ASCII Dashboard
# ---------------------------------------------------------------------------

class ASCIIDashboard:
    def __init__(self, obs: "ObservabilityModule", refresh_seconds: float = 5):
        self.obs = obs
        self.refresh_seconds = refresh_seconds
        self._start = time.time()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _uptime(self) -> str:
        elapsed = int(time.time() - self._start)
        h, m = divmod(elapsed // 60, 60)
        return f"{h}h {m:02d}m" if h > 0 else f"{elapsed // 60}m {elapsed % 60:02d}s"

    def render(self) -> str:
        snap = self.obs.slo_monitor.snapshot()
        lat = self.obs.latency_profiler.stats()
        cost_hr = self.obs.cost_accountant.hourly_cost()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        status = snap.overall_status()
        w = 52

        lines = [
            "+" + "-" * w + "+",
            f"|  {self.obs.config.service_name} Observability Dashboard".ljust(w) + " |",
            f"|  {now}  |  uptime: {self._uptime()}".ljust(w) + " |",
            "+" + "-" * w + "+",
            f"|  Requests (15m): {lat.sample_count:4d}   |  Error rate: {snap.error_rate:.1%}".ljust(w) + " |",
            f"|  TTFT p50:  {lat.ttft_p50_ms:5.0f}ms  |  TTFT p95:  {lat.ttft_p95_ms:5.0f}ms".ljust(w) + " |",
            f"|  Total p50: {lat.total_p50_ms:5.0f}ms  |  Total p95: {lat.total_p95_ms:5.0f}ms".ljust(w) + " |",
            f"|  Cost/hr:  ${cost_hr:6.4f}   |  Cache hits: {snap.cache_hit_rate:.0%}".ljust(w) + " |",
            f"|  Eval score: {snap.eval_score_mean:.2f}      |  SLO status: {status}".ljust(w) + " |",
            "+" + "-" * w + "+",
        ]
        if snap.active_alerts > 0:
            lines.append(f"|  ALERTS: {snap.active_alerts} active".ljust(w) + " |")
        else:
            lines.append(f"|  ALERTS: none".ljust(w) + " |")
        lines.append("+" + "-" * w + "+")
        return "\n".join(lines)

    def _loop(self):
        while self._running:
            print("\033[2J\033[H" + self.render(), flush=True)
            time.sleep(self.refresh_seconds)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False


# ---------------------------------------------------------------------------
# Main Observability Module
# ---------------------------------------------------------------------------

class ObservabilityModule:
    def __init__(self, config: ObsConfig = ObsConfig()):
        self.config = config
        self.scrubber = PIIScrubber()
        self.logger = StructuredLogger(config.log_path, config.service_name, self.scrubber)
        self.cost_accountant = CostAccountant(config.db_path)
        self.latency_profiler = LatencyProfiler()
        self.slo_monitor = SimpleSLOMonitor(config)
        self._dashboard = ASCIIDashboard(self)

    @contextmanager
    def trace_llm_call(self, operation: str, user_id: Optional[str] = None):
        ctx = LLMCallContext(operation=operation, user_id=user_id, _obs=self)
        try:
            yield ctx
        except Exception as e:
            ctx.record(None, error=True)
            raise

    def start_dashboard(self, refresh_seconds: float = 5):
        self._dashboard.refresh_seconds = refresh_seconds
        self._dashboard.start()

    def stop_dashboard(self):
        self._dashboard.stop()


# ---------------------------------------------------------------------------
# FastAPI application (for service mode)
# ---------------------------------------------------------------------------

try:
    from fastapi import FastAPI, Request
    from pydantic import BaseModel

    app = FastAPI(title="RAG Service with Observability")
    obs = ObservabilityModule(ObsConfig(
        service_name="rag-service",
        db_path="/tmp/cost_log.db",
        log_path="/tmp/app.jsonl",
    ))

    class QueryRequest(BaseModel):
        question: str
        user_id: Optional[str] = None

    @app.on_event("startup")
    def startup():
        obs.start_dashboard(refresh_seconds=5)

    @app.post("/query")
    def query(req: QueryRequest):
        with obs.trace_llm_call(operation="rag_query", user_id=req.user_id) as ctx:
            # In a real service, this would call the Anthropic API
            # Here we simulate for demo purposes
            import time as _time
            _time.sleep(0.4)
            ctx.record_ttft()
            _time.sleep(0.8)

            from unittest.mock import MagicMock
            mock_response = MagicMock()
            mock_response.usage.input_tokens = 250
            mock_response.usage.output_tokens = 180
            mock_response.usage.cache_read_input_tokens = 120
            mock_response.model = "claude-3-5-haiku-20241022"
            ctx.record(mock_response)

        return {"answer": f"This is a simulated answer to: {req.question}"}

except ImportError:
    app = None


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------

def run_demo():
    """Simulates 60 seconds of traffic and renders the dashboard."""
    import random

    config = ObsConfig(
        service_name="demo-rag-service",
        db_path=":memory:",
        log_path="/dev/null",
    )
    # Patch SQLite in-memory mode
    config.db_path = "/tmp/demo_cost_log.db"

    obs = ObservabilityModule(config)
    obs.start_dashboard(refresh_seconds=3)

    print("Generating simulated traffic for 15 seconds...")
    for i in range(80):
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.usage.input_tokens = random.randint(100, 500)
        mock_resp.usage.output_tokens = random.randint(50, 300)
        mock_resp.usage.cache_read_input_tokens = random.randint(0, 80)
        mock_resp.model = "claude-3-5-haiku-20241022"

        with obs.trace_llm_call(operation="demo_query") as ctx:
            time.sleep(random.uniform(0.05, 0.15))
            ctx.record_ttft()
            time.sleep(random.uniform(0.1, 0.5))
            error = random.random() < 0.02
            ctx.record(
                mock_resp,
                error=error,
                eval_score=random.gauss(0.87, 0.05) if random.random() < 0.1 else None,
            )
        time.sleep(0.1)

    time.sleep(5)
    obs.stop_dashboard()
    print("\nDemo complete.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Run demo with simulated traffic")
    args = parser.parse_args()

    if args.demo:
        run_demo()
    else:
        print("Run with --demo for standalone demo, or use 'uvicorn main:app' for FastAPI mode.")
        print("Requires: pip install -r requirements.txt")


if __name__ == "__main__":
    main()
