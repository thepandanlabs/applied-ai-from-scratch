"""
Fallbacks and Model Failover for AI services.

Implements a FallbackChain with four tiers:
  1. Primary model (Claude, short timeout)
  2. Secondary model (OpenAI, longer timeout)
  3. Cache (in-memory, TTL-based)
  4. Degradation message (static; always returns something)

Usage:
    ANTHROPIC_API_KEY=sk-ant-... OPENAI_API_KEY=sk-... python main.py

    # With broken primary (timeout=0.001 forces fallback):
    ANTHROPIC_API_KEY=invalid OPENAI_API_KEY=sk-... python main.py
"""

import hashlib
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Timeout utility (POSIX only; works on Linux and macOS)
# ---------------------------------------------------------------------------


class CallTimeoutError(Exception):
    """Raised when a model call exceeds its per-model timeout."""
    pass


def _alarm_handler(signum, frame):
    raise CallTimeoutError("Model call timed out")


def call_with_timeout(fn, timeout: float) -> Any:
    """
    Execute fn and raise CallTimeoutError if it takes longer than timeout seconds.

    Uses POSIX SIGALRM. For Windows compatibility, replace with
    concurrent.futures.ThreadPoolExecutor with a future.result(timeout=timeout).
    """
    signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(max(1, int(timeout)))  # alarm takes integer seconds
    try:
        return fn()
    finally:
        signal.alarm(0)  # cancel the alarm


# ---------------------------------------------------------------------------
# Model config
# ---------------------------------------------------------------------------


@dataclass
class ModelConfig:
    """Configuration for a single model tier in the fallback chain."""
    provider: str    # "anthropic" or "openai"
    model: str       # provider-specific model ID
    timeout: float   # seconds; raise CallTimeoutError if exceeded
    max_tokens: int = 1024


# ---------------------------------------------------------------------------
# FallbackChain
# ---------------------------------------------------------------------------


class FallbackChain:
    """
    Tries AI models in priority order. Falls back to a response cache,
    then to a static degradation message.

    The chain always returns a response -- it never raises an exception to
    the caller. The 'tier' field in the result indicates which tier answered.

    Stats are tracked per tier for operational monitoring:
        chain.stats -> {"primary": N, "fallback": N, "cache": N, "degraded": N}
    """

    def __init__(
        self,
        models: list[ModelConfig],
        degradation_message: str = (
            "The AI assistant is temporarily unavailable. "
            "Please try again in a few minutes."
        ),
        cache_ttl: float = 300.0,
    ):
        if not models:
            raise ValueError("FallbackChain requires at least one model config")
        self.models = models
        self.degradation_message = degradation_message
        self.cache_ttl = cache_ttl
        self._cache: dict[str, dict] = {}
        self._stats: dict[str, int] = {
            "primary": 0,
            "fallback": 0,
            "cache": 0,
            "degraded": 0,
        }

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def generate(self, prompt: str) -> dict:
        """
        Try each model in order. Return the first successful response.

        Returns a dict with:
          text          - the response text
          tier          - which tier answered: primary / fallback / cache / degraded
          model         - model ID that answered (or "cache" / "none")
          latency_seconds - wall-clock time for the model call (0 for cache/degraded)
        """
        for i, config in enumerate(self.models):
            tier_name = "primary" if i == 0 else "fallback"
            try:
                start = time.monotonic()
                text = call_with_timeout(
                    lambda c=config: self._call_model(c, prompt),
                    timeout=config.timeout,
                )
                elapsed = time.monotonic() - start
                self._put_in_cache(prompt, text)
                self._stats[tier_name] += 1
                return {
                    "text": text,
                    "tier": tier_name,
                    "model": config.model,
                    "latency_seconds": round(elapsed, 3),
                }

            except Exception as e:
                print(
                    f"[FallbackChain] Tier {i+1} ({config.model}) failed: "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr,
                )
                continue

        # All models failed: try cache
        cached_text = self._get_from_cache(prompt)
        if cached_text is not None:
            self._stats["cache"] += 1
            return {
                "text": cached_text,
                "tier": "cache",
                "model": "cache",
                "latency_seconds": 0.0,
            }

        # Nothing worked: return degradation message
        self._stats["degraded"] += 1
        return {
            "text": self.degradation_message,
            "tier": "degraded",
            "model": "none",
            "latency_seconds": 0.0,
        }

    # ---------------------------------------------------------------------------
    # Cache helpers
    # ---------------------------------------------------------------------------

    def _cache_key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def _get_from_cache(self, prompt: str) -> str | None:
        entry = self._cache.get(self._cache_key(prompt))
        if entry and (time.monotonic() - entry["ts"]) < self.cache_ttl:
            return entry["text"]
        return None

    def _put_in_cache(self, prompt: str, text: str) -> None:
        self._cache[self._cache_key(prompt)] = {
            "text": text,
            "ts": time.monotonic(),
        }

    # ---------------------------------------------------------------------------
    # Model callers
    # ---------------------------------------------------------------------------

    def _call_model(self, config: ModelConfig, prompt: str) -> str:
        if config.provider == "anthropic":
            return self._call_anthropic(config, prompt)
        elif config.provider == "openai":
            return self._call_openai(config, prompt)
        else:
            raise ValueError(f"Unknown provider: {config.provider!r}")

    def _call_anthropic(self, config: ModelConfig, prompt: str) -> str:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    def _call_openai(self, config: ModelConfig, prompt: str) -> str:
        from openai import OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=config.model,
            max_tokens=config.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main():
    chain = FallbackChain(
        models=[
            ModelConfig(
                provider="anthropic",
                model="claude-3-5-haiku-20241022",
                timeout=10.0,
            ),
            ModelConfig(
                provider="openai",
                model="gpt-4o-mini",
                timeout=15.0,
            ),
        ],
        degradation_message=(
            "The AI assistant is temporarily unavailable. "
            "Please try again in a few minutes."
        ),
        cache_ttl=300.0,
    )

    prompts = [
        "Explain fallback chains in one sentence.",
        "Explain fallback chains in one sentence.",  # second call hits cache
        "What is the difference between a timeout and a 503 error?",
    ]

    for prompt in prompts:
        print(f"\nPrompt: {prompt[:60]}...")
        result = chain.generate(prompt)
        print(f"  Tier:    {result['tier']}")
        print(f"  Model:   {result['model']}")
        print(f"  Latency: {result['latency_seconds']:.3f}s")
        print(f"  Text:    {result['text'][:100]}...")

    print(f"\nStats: {chain.stats}")


if __name__ == "__main__":
    main()
