"""
L07: Caching Deep-Dive - Prompt/Prefix and Semantic Caching
Phase 07 - Observability

Demonstrates:
- Anthropic prompt caching with cache_control breakpoints
- Cost comparison: with vs without prompt caching
- Semantic caching using sentence-transformers + cosine similarity
- Two-tier cache lookup: semantic miss -> model call with prompt cache
- Hit rate measurement for both layers
"""

import time
from dataclasses import dataclass, field
from typing import Optional

import anthropic
import numpy as np
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Prompt Cache Wrapper
# ---------------------------------------------------------------------------


def call_with_prompt_cache(
    user_message: str,
    system_prompt: str,
    model: str = "claude-3-5-haiku-20241022",
) -> tuple[str, dict]:
    """
    Claude API call with the system prompt marked for caching.

    The system prompt is sent with cache_control so Anthropic caches
    its KV state. The first call pays 125% of normal input token cost
    (cache write). Subsequent calls within 5 minutes pay 10% (cache read).

    Returns:
        (response_text, usage_dict) where usage_dict has:
        - input_tokens
        - output_tokens
        - cache_creation_input_tokens (> 0 on first call = cache write)
        - cache_read_input_tokens (> 0 on cache hit)
    """
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )

    text = response.content[0].text if response.content else ""
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_creation_input_tokens": getattr(
            response.usage, "cache_creation_input_tokens", 0
        ),
        "cache_read_input_tokens": getattr(
            response.usage, "cache_read_input_tokens", 0
        ),
    }
    return text, usage


def cache_hit_rate(usage_records: list[dict]) -> dict:
    """
    Summarize cache write/hit/miss stats from a list of usage dicts.
    """
    total = len(usage_records)
    hits = sum(1 for u in usage_records if u.get("cache_read_input_tokens", 0) > 0)
    writes = sum(
        1 for u in usage_records if u.get("cache_creation_input_tokens", 0) > 0
    )
    return {
        "total_calls": total,
        "cache_writes": writes,
        "cache_hits": hits,
        "cache_misses": total - hits - writes,
        "hit_rate": round(hits / total, 3) if total > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# Prompt Cache Cost Comparison
# ---------------------------------------------------------------------------


@dataclass
class CostComparison:
    calls: int
    system_prompt_tokens: int
    without_cache_usd: float
    with_cache_usd: float
    savings_usd: float
    savings_pct: float


def compare_prompt_cache_cost(
    system_prompt_tokens: int,
    calls: int,
    input_price_per_million: float = 0.80,
    cache_write_multiplier: float = 1.25,
    cache_read_multiplier: float = 0.10,
) -> CostComparison:
    """
    Estimate cost savings from prompt caching over N calls.

    Assumes:
    - 1 cache write (first call)
    - N-1 cache reads (all subsequent calls within TTL window)
    - The cache stays warm (calls within 5-minute TTL windows)
    """
    price_per_token = input_price_per_million / 1_000_000

    # Without caching: full price on every call
    without = calls * system_prompt_tokens * price_per_token

    # With caching: 1 write + N-1 reads
    write_cost = system_prompt_tokens * cache_write_multiplier * price_per_token
    read_cost = (calls - 1) * system_prompt_tokens * cache_read_multiplier * price_per_token
    with_cache = write_cost + read_cost

    savings = without - with_cache
    return CostComparison(
        calls=calls,
        system_prompt_tokens=system_prompt_tokens,
        without_cache_usd=round(without, 6),
        with_cache_usd=round(with_cache, 6),
        savings_usd=round(savings, 6),
        savings_pct=round(savings / without * 100, 1) if without > 0 else 0.0,
    )


# ---------------------------------------------------------------------------
# Semantic Cache
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    query: str
    answer: str
    embedding: np.ndarray
    ts: float = field(default_factory=time.time)
    hit_count: int = 0


class SemanticCache:
    """
    Pre-model cache that matches user queries by semantic similarity.

    Before calling the LLM, embed the query and check if any cached
    query has cosine similarity >= threshold. If yes, return the cached
    answer (zero model tokens consumed). If no, call the model and cache.

    Design notes:
    - Threshold 0.90-0.93 is a good starting point for FAQ content
    - TTL prevents stale answers (important if underlying facts change)
    - max_entries with LFU eviction keeps memory bounded
    - Use a labeled test set to validate your threshold before production
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        threshold: float = 0.92,
        ttl_seconds: Optional[float] = None,
        max_entries: int = 1000,
    ):
        self.model = SentenceTransformer(model_name)
        self.threshold = threshold
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._cache: list[CacheEntry] = []
        self._hits = 0
        self._misses = 0

    def _embed(self, text: str) -> np.ndarray:
        """Embed a single text string. Returns unit-normalized vector."""
        return self.model.encode([text], normalize_embeddings=True)[0]

    def _is_expired(self, entry: CacheEntry) -> bool:
        if self.ttl is None:
            return False
        return (time.time() - entry.ts) > self.ttl

    def _evict_expired(self) -> None:
        before = len(self._cache)
        self._cache = [e for e in self._cache if not self._is_expired(e)]

    def get(self, query: str) -> Optional[str]:
        """
        Return cached answer if semantic similarity >= threshold.
        Returns None on a miss.
        """
        self._evict_expired()
        if not self._cache:
            self._misses += 1
            return None

        query_vec = self._embed(query)
        cache_vecs = np.array([e.embedding for e in self._cache])
        # Dot product = cosine similarity because all vectors are unit-normalized
        scores = cache_vecs @ query_vec
        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])

        if best_score >= self.threshold:
            self._hits += 1
            self._cache[best_idx].hit_count += 1
            return self._cache[best_idx].answer

        self._misses += 1
        return None

    def put(self, query: str, answer: str) -> None:
        """Store a query/answer pair. Evicts LFU entry if at capacity."""
        self._evict_expired()
        if len(self._cache) >= self.max_entries:
            # Least-frequently-used eviction
            self._cache.sort(key=lambda e: e.hit_count)
            self._cache.pop(0)

        self._cache.append(
            CacheEntry(query=query, answer=answer, embedding=self._embed(query))
        )

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
            "threshold": self.threshold,
        }


# ---------------------------------------------------------------------------
# Two-Tier Cache Lookup
# ---------------------------------------------------------------------------


def smart_call(
    user_query: str,
    system_prompt: str,
    semantic_cache: SemanticCache,
    model: str = "claude-3-5-haiku-20241022",
) -> tuple[str, str]:
    """
    Two-tier lookup:
    1. Check semantic cache (zero model tokens if hit)
    2. Call model with prompt caching (reduced tokens on system prompt if hit)

    Returns (answer, source) where source is 'semantic_cache' or 'model'.
    """
    # Layer 1: semantic cache
    cached = semantic_cache.get(user_query)
    if cached is not None:
        return cached, "semantic_cache"

    # Layer 2: model call with prompt caching
    answer, _ = call_with_prompt_cache(user_query, system_prompt, model)

    # Store in semantic cache for future similar queries
    semantic_cache.put(user_query, answer)
    return answer, "model"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def demo_cost_comparison() -> None:
    """Show prompt cache cost savings at different call volumes."""
    print("=== Prompt Cache Cost Comparison ===\n")
    print(
        f"{'Scenario':<35} {'Calls':>6} {'Without':>12} {'With':>12} {'Save':>8} {'Save%':>7}"
    )
    print("-" * 84)

    scenarios = [
        ("Short system prompt (200 tok)", 200, 100),
        ("Medium system prompt (1000 tok)", 1000, 500),
        ("Long system prompt (2000 tok)", 2000, 1000),
        ("Large doc context (8000 tok)", 8000, 200),
    ]
    for label, tokens, calls in scenarios:
        c = compare_prompt_cache_cost(tokens, calls)
        print(
            f"{label:<35} {calls:>6} ${c.without_cache_usd:>10.4f} "
            f"${c.with_cache_usd:>10.4f} ${c.savings_usd:>6.4f} {c.savings_pct:>6.1f}%"
        )


def demo_semantic_cache() -> None:
    """
    Demonstrate semantic cache hit rates on FAQ-style queries.
    No API key needed - uses cached answers directly.
    """
    print("\n=== Semantic Cache Demo ===\n")

    cache = SemanticCache(threshold=0.92)

    # Seed the cache with canonical FAQ answers
    faqs = [
        ("How do I reset my password?", "Go to Settings > Security > Reset Password."),
        (
            "How do I cancel my subscription?",
            "Go to Settings > Billing > Cancel Subscription.",
        ),
        (
            "Where can I download my invoice?",
            "Go to Settings > Billing > Download Invoice.",
        ),
        (
            "How do I contact support?",
            "Email support@example.com or use the in-app chat.",
        ),
    ]
    for q, a in faqs:
        cache.put(q, a)

    # Test queries: mix of paraphrases (should hit) and novel queries (should miss)
    test_queries = [
        ("I forgot my password, how do I recover it?", True),   # should hit
        ("Password reset steps", True),                          # should hit
        ("Can I change my login credentials?", True),            # should hit
        ("How do I unsubscribe from billing?", True),            # should hit
        ("How do I export all my data?", False),                 # should miss
        ("What programming languages do you support?", False),   # should miss
    ]

    correct = 0
    for query, expected_hit in test_queries:
        result = cache.get(query)
        actual_hit = result is not None
        status = "PASS" if actual_hit == expected_hit else "FAIL"
        label = "HIT" if actual_hit else "MISS"
        correct += 1 if actual_hit == expected_hit else 0
        print(f"[{status}] {label:<4} | {query[:55]}")

    print(f"\nCorrect: {correct}/{len(test_queries)}")
    print(f"Cache stats: {cache.stats()}")


def demo_break_even() -> None:
    """Show the break-even analysis for a 2000-token system prompt."""
    print("\n=== Break-Even Analysis: 2000-token system prompt ===\n")
    print(
        "At Haiku pricing ($0.80/1M input), cache write = 125%, cache read = 10%\n"
    )
    for calls in [1, 2, 3, 5, 10, 50, 100, 1000]:
        c = compare_prompt_cache_cost(2000, calls)
        print(
            f"  {calls:>5} calls: without=${c.without_cache_usd:.6f} "
            f"with=${c.with_cache_usd:.6f} savings={c.savings_pct:.1f}%"
        )


if __name__ == "__main__":
    demo_cost_comparison()
    demo_semantic_cache()
    demo_break_even()
