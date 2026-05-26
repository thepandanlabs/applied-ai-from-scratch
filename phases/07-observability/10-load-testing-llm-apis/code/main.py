"""
LLM Load Tester - Phase 07, Lesson 10
Measures TTFT, total latency, error rate, and estimated cost for LLM API calls.

Usage:
    # Mock mode (no API key needed)
    python main.py --mock --concurrency 10 --requests 50

    # Real API mode (requires ANTHROPIC_API_KEY)
    ANTHROPIC_API_KEY=sk-ant-... python main.py --concurrency 5 --requests 20
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import os
import random
import statistics
import time
from typing import Optional


@dataclasses.dataclass
class LoadTestConfig:
    concurrency: int = 10
    total_requests: int = 50
    prompt: str = "Explain the tradeoffs between synchronous and asynchronous Python in 100 words."
    max_tokens: int = 150
    model: str = "claude-3-5-haiku-20241022"
    use_mock: bool = True
    timeout_seconds: float = 30.0


@dataclasses.dataclass
class RequestResult:
    request_id: int
    ttft_ms: float          # Time to first token (ms)
    total_latency_ms: float # Time to last token (ms)
    input_tokens: int
    output_tokens: int
    status: str             # "ok", "timeout", "rate_limited", "error"
    error_message: Optional[str] = None


@dataclasses.dataclass
class LoadTestReport:
    config: LoadTestConfig
    results: list[RequestResult]
    wall_time_seconds: float

    def _percentile(self, values: list[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = int(len(sorted_vals) * p / 100)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]

    def print_summary(self):
        total = len(self.results)
        ok = [r for r in self.results if r.status == "ok"]
        errors = [r for r in self.results if r.status != "ok"]
        timeouts = [r for r in self.results if r.status == "timeout"]
        rate_limits = [r for r in self.results if r.status == "rate_limited"]

        ttft_vals = [r.ttft_ms for r in ok]
        total_lat_vals = [r.total_latency_ms for r in ok]

        throughput = total / self.wall_time_seconds if self.wall_time_seconds > 0 else 0

        # Cost estimate (haiku pricing: $1/M input, $5/M output tokens)
        input_tokens = sum(r.input_tokens for r in ok)
        output_tokens = sum(r.output_tokens for r in ok)
        est_cost = (input_tokens * 0.000001) + (output_tokens * 0.000005)

        print("\nLLM Load Test Report")
        print("====================")
        print(f"Config: {total} requests, concurrency={self.config.concurrency}, mock={self.config.use_mock}")
        print(f"Duration: {self.wall_time_seconds:.1f}s  |  Throughput: {throughput:.1f} req/s")

        print("\nLatency (TTFT)")
        if ttft_vals:
            print(f"  p50:  {self._percentile(ttft_vals, 50):6.0f}ms")
            print(f"  p95:  {self._percentile(ttft_vals, 95):6.0f}ms")
            print(f"  p99:  {self._percentile(ttft_vals, 99):6.0f}ms")
        else:
            print("  No successful requests")

        print("\nLatency (Total)")
        if total_lat_vals:
            print(f"  p50:  {self._percentile(total_lat_vals, 50):6.0f}ms")
            print(f"  p95:  {self._percentile(total_lat_vals, 95):6.0f}ms")
            print(f"  p99:  {self._percentile(total_lat_vals, 99):6.0f}ms")
        else:
            print("  No successful requests")

        error_pct = len(errors) / total * 100 if total > 0 else 0
        print(f"\nErrors")
        print(f"  Total:       {len(errors):3d}  ({error_pct:.1f}%)")
        print(f"  Timeouts:    {len(timeouts):3d}")
        print(f"  Rate limits: {len(rate_limits):3d}")

        print(f"\nCost estimate ({'mock - est based on config' if self.config.use_mock else 'real API'})")
        print(f"  Input tokens:  ~{input_tokens:,}")
        print(f"  Output tokens: ~{output_tokens:,}")
        print(f"  Est. cost:     ${est_cost:.4f} (haiku pricing)")


class MockLLMClient:
    """Simulates LLM API latency without making real calls."""

    async def stream_request(self, prompt: str, max_tokens: int) -> RequestResult:
        req_id = random.randint(1000, 9999)
        start = time.perf_counter()

        # Simulate TTFT: 30-120ms
        await asyncio.sleep(random.uniform(0.03, 0.12))
        ttft_ms = (time.perf_counter() - start) * 1000

        # Simulate streaming: proportional to max_tokens
        output_tokens = random.randint(max_tokens // 2, max_tokens)
        stream_duration = output_tokens * 0.002  # ~2ms per output token
        await asyncio.sleep(stream_duration)
        total_ms = (time.perf_counter() - start) * 1000

        # Simulate occasional errors (2% rate limit, 1% timeout)
        rand = random.random()
        if rand < 0.01:
            return RequestResult(
                request_id=req_id, ttft_ms=0, total_latency_ms=total_ms,
                input_tokens=0, output_tokens=0, status="timeout",
                error_message="Simulated timeout"
            )
        if 0.01 <= rand < 0.03:
            return RequestResult(
                request_id=req_id, ttft_ms=0, total_latency_ms=total_ms,
                input_tokens=0, output_tokens=0, status="rate_limited",
                error_message="Simulated 429"
            )

        input_tokens = len(prompt) // 4
        return RequestResult(
            request_id=req_id,
            ttft_ms=ttft_ms,
            total_latency_ms=total_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            status="ok",
        )


class AnthropicStreamClient:
    """Real Anthropic streaming client that measures TTFT."""

    def __init__(self, api_key: str):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def stream_request(
        self, model: str, prompt: str, max_tokens: int, request_id: int
    ) -> RequestResult:
        start = time.perf_counter()
        ttft_ms: Optional[float] = None
        output_tokens = 0

        try:
            async with self.client.messages.stream(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            ) as stream:
                async for chunk in stream:
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - start) * 1000
                    # Count approximate output tokens from text chunks
                    if hasattr(chunk, "delta") and hasattr(chunk.delta, "text"):
                        output_tokens += len(chunk.delta.text) // 4

                final_message = await stream.get_final_message()
                total_ms = (time.perf_counter() - start) * 1000
                input_tokens = final_message.usage.input_tokens
                output_tokens = final_message.usage.output_tokens

            return RequestResult(
                request_id=request_id,
                ttft_ms=ttft_ms or total_ms,
                total_latency_ms=total_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                status="ok",
            )
        except Exception as e:
            total_ms = (time.perf_counter() - start) * 1000
            error_str = str(e)
            status = "rate_limited" if "429" in error_str else "error"
            return RequestResult(
                request_id=request_id,
                ttft_ms=0, total_latency_ms=total_ms,
                input_tokens=0, output_tokens=0,
                status=status, error_message=error_str[:100],
            )


class LLMLoadTester:
    def __init__(self, config: LoadTestConfig):
        self.config = config

    async def run(self) -> LoadTestReport:
        semaphore = asyncio.Semaphore(self.config.concurrency)
        results: list[RequestResult] = []
        mock_client = MockLLMClient()

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        real_client = AnthropicStreamClient(api_key) if (not self.config.use_mock and api_key) else None

        async def run_single(req_id: int) -> RequestResult:
            async with semaphore:
                if self.config.use_mock or real_client is None:
                    return await mock_client.stream_request(
                        self.config.prompt, self.config.max_tokens
                    )
                else:
                    return await real_client.stream_request(
                        self.config.model, self.config.prompt,
                        self.config.max_tokens, req_id
                    )

        print(f"Starting load test: {self.config.total_requests} requests, "
              f"concurrency={self.config.concurrency}, mock={self.config.use_mock}")

        start = time.perf_counter()
        tasks = [run_single(i) for i in range(self.config.total_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        wall_time = time.perf_counter() - start

        return LoadTestReport(
            config=self.config,
            results=list(results),
            wall_time_seconds=wall_time,
        )


async def main_async(args):
    config = LoadTestConfig(
        concurrency=args.concurrency,
        total_requests=args.requests,
        use_mock=args.mock,
        max_tokens=150,
    )
    tester = LLMLoadTester(config)
    report = await tester.run()
    report.print_summary()


def main():
    parser = argparse.ArgumentParser(description="LLM API load tester")
    parser.add_argument("--mock", action="store_true", default=True,
                        help="Use mock client (no API calls)")
    parser.add_argument("--no-mock", dest="mock", action="store_false",
                        help="Use real Anthropic API (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--concurrency", type=int, default=10,
                        help="Number of concurrent requests")
    parser.add_argument("--requests", type=int, default=50,
                        help="Total number of requests to send")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
