"""
L08: Serving an Open-Weight Model with vLLM
VLLMClient: OpenAI-compatible wrapper for vLLM inference servers.

Usage:
    python main.py                     # run with demo prompts against vLLM server
    python main.py --url http://...    # point at a remote vLLM server
    python main.py --compare           # compare vLLM vs Anthropic API latency
    python main.py --stream "prompt"   # stream a single prompt

Requires:
    - vLLM server running (see docker-compose.yml for local setup)
    - ANTHROPIC_API_KEY if using --compare mode
"""

import argparse
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Iterator, Optional

from openai import OpenAI


@dataclass
class VLLMConfig:
    base_url: str = "http://localhost:8000/v1"
    api_key: str = "dummy"           # vLLM doesn't require auth by default
    model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    max_tokens: int = 512
    temperature: float = 0.1
    timeout: float = 30.0


@dataclass
class CompletionResult:
    prompt: str
    output: str
    latency_s: float
    status: str
    tokens_out: int = 0


class VLLMClient:
    """
    Drop-in OpenAI-compatible client for vLLM servers.

    Swap the base_url and this client works with:
    - Local vLLM server (docker-compose up)
    - Remote vLLM server (GPU cloud instance)
    - OpenAI API directly (base_url=None, api_key=OPENAI_API_KEY)
    - Any OpenAI-compatible endpoint
    """

    def __init__(self, config: Optional[VLLMConfig] = None):
        self.config = config or VLLMConfig()
        self.client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout=self.config.timeout,
        )

    def health_check(self) -> bool:
        """Ping the vLLM server and verify it is responsive."""
        try:
            models = self.client.models.list()
            available = [m.id for m in models.data]
            print(f"  vLLM server online. Available models: {available}")
            return True
        except Exception as e:
            print(f"  vLLM server not reachable: {e}")
            return False

    def complete(self, prompt: str, system: str = "") -> str:
        """Single completion, blocking."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        return response.choices[0].message.content or ""

    def stream(self, prompt: str, system: str = "") -> Iterator[str]:
        """Streaming completion - yields token strings as they arrive."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        stream = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def timed_complete(
        self, prompt: str, system: str = ""
    ) -> CompletionResult:
        """Complete one prompt and record latency."""
        start = time.perf_counter()
        try:
            output = self.complete(prompt, system=system)
            latency = time.perf_counter() - start
            return CompletionResult(
                prompt=prompt,
                output=output,
                latency_s=round(latency, 3),
                status="ok",
                tokens_out=len(output.split()),
            )
        except Exception as e:
            latency = time.perf_counter() - start
            return CompletionResult(
                prompt=prompt,
                output="",
                latency_s=round(latency, 3),
                status=f"error: {e}",
            )

    def batch_complete(
        self,
        prompts: list[str],
        system: str = "",
        verbose: bool = True,
    ) -> list[CompletionResult]:
        """
        Run multiple prompts sequentially with latency tracking.

        Note: for true throughput benchmarking, use async clients with
        asyncio.gather - sequential calls do not exercise vLLM's
        continuous batching advantage.
        """
        results = []
        for i, prompt in enumerate(prompts):
            if verbose:
                print(f"  [{i + 1}/{len(prompts)}]", end=" ", flush=True)
            result = self.timed_complete(prompt, system=system)
            results.append(result)
            if verbose:
                print(f"{result.status} ({result.latency_s}s)")
        return results


def print_latency_stats(label: str, results: list[CompletionResult]) -> None:
    """Print latency summary statistics for a batch of results."""
    ok_results = [r for r in results if r.status == "ok"]
    if not ok_results:
        print(f"  {label}: no successful results")
        return

    latencies = [r.latency_s for r in ok_results]
    sorted_l = sorted(latencies)
    n = len(sorted_l)
    p50 = sorted_l[n // 2]
    p95 = sorted_l[min(int(n * 0.95), n - 1)]
    p99 = sorted_l[min(int(n * 0.99), n - 1)]

    print(f"\n  {label} ({len(ok_results)}/{len(results)} ok):")
    print(f"    Mean:    {statistics.mean(latencies):.3f}s")
    print(f"    Median:  {p50:.3f}s")
    print(f"    P95:     {p95:.3f}s")
    print(f"    P99:     {p99:.3f}s")
    print(f"    Min/Max: {min(latencies):.3f}s / {max(latencies):.3f}s")


def compare_with_anthropic(
    prompts: list[str],
    vllm_client: VLLMClient,
    system: str = "",
) -> None:
    """
    Side-by-side latency comparison: vLLM vs Anthropic API.
    Requires ANTHROPIC_API_KEY environment variable.
    """
    try:
        import anthropic as anthropic_sdk
    except ImportError:
        print("  anthropic package not installed. Run: pip install anthropic")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ANTHROPIC_API_KEY not set. Skipping Anthropic comparison.")
        return

    anthropic_client = anthropic_sdk.Anthropic(api_key=api_key)

    print("\n=== Anthropic API batch ===")
    anthropic_results = []
    for i, prompt in enumerate(prompts):
        print(f"  [{i + 1}/{len(prompts)}]", end=" ", flush=True)
        start = time.perf_counter()
        try:
            kwargs: dict = {
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system
            resp = anthropic_client.messages.create(**kwargs)
            latency = time.perf_counter() - start
            anthropic_results.append(CompletionResult(
                prompt=prompt,
                output=resp.content[0].text,
                latency_s=round(latency, 3),
                status="ok",
            ))
            print(f"ok ({latency:.3f}s)")
        except Exception as e:
            latency = time.perf_counter() - start
            anthropic_results.append(CompletionResult(
                prompt=prompt, output="", latency_s=round(latency, 3),
                status=f"error: {e}",
            ))
            print(f"error: {e}")

    print_latency_stats("Anthropic API", anthropic_results)

    print("\n=== vLLM batch ===")
    vllm_results = vllm_client.batch_complete(prompts, system=system)
    print_latency_stats("vLLM (sequential)", vllm_results)

    print("\n  NOTE: vLLM's throughput advantage is in CONCURRENT load.")
    print("  Sequential comparison shows API overhead, not batching benefit.")
    print("  For real comparison: run 50 concurrent requests with asyncio.gather.")


# Demo prompts for extraction task
DEMO_SYSTEM = (
    "Extract the date, invoice number, amount, and parties from this invoice text. "
    "Respond in JSON: {\"invoice_number\": ..., \"date\": ..., \"amount\": ..., "
    "\"vendor\": ..., \"client\": ...}"
)

DEMO_PROMPTS = [
    f"Invoice #{i:03d}: {vendor} billed {client} ${amount} on 2025-{month:02d}-{day:02d} for consulting services."
    for i, (vendor, client, amount, month, day) in enumerate([
        ("Acme Corp", "Beta LLC", "12,500", 1, 15),
        ("TechVentures", "GlobalRetail Inc", "8,750", 2, 3),
        ("DataSystems", "FinancePlus", "22,000", 2, 28),
        ("CloudOps", "MediaGroup", "5,400", 3, 10),
        ("InfoSec Partners", "HealthTech Co", "18,900", 3, 22),
    ], start=1)
]


def main():
    parser = argparse.ArgumentParser(
        description="vLLM client wrapper with OpenAI-compatible API."
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000/v1",
        help="vLLM server base URL (default: http://localhost:8000/v1)",
    )
    parser.add_argument(
        "--model",
        default="Qwen/Qwen2.5-1.5B-Instruct",
        help="Model name as registered on the vLLM server",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare vLLM vs Anthropic API latency",
    )
    parser.add_argument(
        "--stream",
        metavar="PROMPT",
        help="Stream a single prompt and print tokens as they arrive",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Check if vLLM server is reachable and list available models",
    )
    args = parser.parse_args()

    config = VLLMConfig(
        base_url=args.url,
        model=args.model,
    )
    client_obj = VLLMClient(config)

    if args.health:
        print(f"Checking vLLM server at {args.url}...")
        ok = client_obj.health_check()
        return 0 if ok else 1

    if args.stream:
        print(f"Streaming prompt: {args.stream[:80]}...\n")
        try:
            for token in client_obj.stream(args.stream):
                print(token, end="", flush=True)
            print()
        except Exception as e:
            print(f"\nError: {e}")
            print("Is the vLLM server running? See docker-compose.yml.")
            return 1
        return 0

    print(f"vLLM client demo - server: {args.url}")
    print(f"Model: {args.model}")

    if args.compare:
        compare_with_anthropic(DEMO_PROMPTS, client_obj, system=DEMO_SYSTEM)
    else:
        print(f"\nRunning {len(DEMO_PROMPTS)} demo prompts sequentially...")
        try:
            results = client_obj.batch_complete(
                DEMO_PROMPTS, system=DEMO_SYSTEM
            )
        except Exception as e:
            print(f"\nFailed to connect to vLLM server: {e}")
            print("Start the server first: docker compose up -d")
            print("(see code/docker-compose.yml)")
            return 1

        print_latency_stats("vLLM sequential", results)

        ok_results = [r for r in results if r.status == "ok"]
        if ok_results:
            print(f"\nSample output:\n  {ok_results[0].output[:200]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
