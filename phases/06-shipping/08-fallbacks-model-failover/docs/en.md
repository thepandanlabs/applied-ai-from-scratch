# Fallbacks and Model Failover

> Users tolerate slow. They do not tolerate gone.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 06 lessons 05-07 (Docker, config, resilience)
**Time:** ~45 min
**Learning Objectives:**
- Build a `FallbackChain` that tries models in order with per-model timeout
- Distinguish timeout-based failover from error-based failover
- Configure a fallback chain with Claude as primary and OpenAI as secondary
- Implement a cached response fallback as the last resort before a degradation message
- Articulate the cost and quality tradeoffs of each fallback tier

---

## The Problem

Your primary AI model is unavailable. Maybe the Anthropic API is having an incident. Maybe your account hit its rate limit and the next request slot is 20 minutes away. Maybe the model is responding but taking 45 seconds per request, which is functionally unavailable for a user-facing product.

The naive response is to return an HTTP 500 and hope users try again. In a user-facing product, that is catastrophic: a competitor with a working service gets every user who hit your 500. In an internal tool, it means engineers stop trusting the AI features and route around them. Either way, you have trained your users that the AI is unreliable.

The production response is a fallback chain: primary model fails, try secondary model. Secondary model fails, try a cached response from a previous successful request on the same or similar query. Cached response unavailable, return a graceful degradation message that explains the situation and tells the user what to do. At every tier, the user gets a response. The quality degrades, but the service never goes silent.

---

## The Concept

### The Fallback Chain

```
User Request
     |
     v
[1] Primary: Claude (claude-3-5-haiku-20241022)
     |  timeout=10s; errors: network, 5xx, 429
     v (on failure or timeout)
[2] Secondary: OpenAI (gpt-4o-mini)
     |  timeout=15s; errors: network, 5xx, 429
     v (on failure or timeout)
[3] Cache: Return a cached response if one exists for this query (or similar)
     |  cache hit: return immediately; cache miss: continue
     v (on cache miss)
[4] Degradation: Return a static message explaining the outage
     |  always succeeds; always returns something
     v
Response to User
```

Each tier has its own timeout. The primary model gets the shortest timeout because it is the fastest. The secondary may get a longer timeout because it is the fallback and latency expectations are already compromised. The cache and degradation tiers are instantaneous.

### Two Types of Failover

Not all failures should trigger a fallback. Understanding the distinction determines when to skip tiers.

```
TIMEOUT-BASED FAILOVER                ERROR-BASED FAILOVER
-----------------------------         -----------------------------
Primary takes > 10s                   Primary returns 500 / 503
  -> try secondary                      -> try secondary

Primary takes > 10s                   Primary returns 429 (rate limited)
  -> secondary also slow                 -> try secondary (different
  -> try cache                             provider, different limit)
  -> degrade

SKIP SECONDARY WHEN:                  NEVER SKIP TO DEGRADE FOR:
  - 401 (auth error; secondary        - Network timeout
    likely has same key issue)         - 503 (server unavailable)
  - 400 (bad request; same            - 429 (rate limited)
    request will fail everywhere)
```

### Cost and Quality Tradeoffs

| Tier | Latency | Quality | Cost |
|------|---------|---------|------|
| Claude (primary) | ~2-5s | Highest for most tasks | Lower per token |
| GPT-4o-mini (secondary) | ~3-8s | Good; slightly different style | Similar per token |
| Cached response | <10ms | Same as when it was generated | Free |
| Degradation message | <1ms | None (static text) | Free |

The secondary model is typically more expensive or slower than the primary. Falling back to it is always better than returning an error, but you should track fallback rate as a metric. If you are falling back more than 1-2% of requests, fix the primary, not the fallback.

---

## Build It

### Step 1: The FallbackChain Class

```python
import time
import hashlib
from typing import Any
from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """Configuration for a single model in the fallback chain."""
    provider: str          # "anthropic" or "openai"
    model: str             # model ID
    timeout: float         # seconds before trying the next tier
    max_tokens: int = 1024


class FallbackChain:
    """
    Tries models in priority order until one succeeds or all fail.

    Tiers:
      1+ model configs (tried in order)
      Last-resort: simple in-memory response cache
      Final fallback: static degradation message
    """

    def __init__(
        self,
        models: list[ModelConfig],
        degradation_message: str = (
            "The AI service is temporarily unavailable. "
            "Please try again in a few minutes."
        ),
        cache_ttl: float = 300.0,  # seconds
    ):
        self.models = models
        self.degradation_message = degradation_message
        self.cache_ttl = cache_ttl
        self._cache: dict[str, dict] = {}  # {cache_key: {text, timestamp}}
        self._stats = {"primary": 0, "fallback": 0, "cache": 0, "degraded": 0}
```

### Step 2: Cache Key and Lookup

```python
    def _cache_key(self, prompt: str) -> str:
        """SHA-256 hash of the prompt. Identical prompts share a cache entry."""
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def _get_from_cache(self, prompt: str) -> str | None:
        """Return cached response if it exists and has not expired."""
        key = self._cache_key(prompt)
        entry = self._cache.get(key)
        if entry and (time.time() - entry["timestamp"]) < self.cache_ttl:
            return entry["text"]
        return None

    def _put_in_cache(self, prompt: str, text: str) -> None:
        """Cache a successful response with the current timestamp."""
        key = self._cache_key(prompt)
        self._cache[key] = {"text": text, "timestamp": time.time()}
```

### Step 3: Per-Provider Call with Timeout

```python
import signal

class TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError("Model call timed out")


def call_with_timeout(fn, timeout: float) -> Any:
    """
    Call fn and raise TimeoutError if it takes longer than timeout seconds.
    Uses POSIX signals (Unix only). For cross-platform use, run in a thread.
    """
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(int(timeout))
    try:
        return fn()
    finally:
        signal.alarm(0)  # cancel the alarm
```

### Step 4: The Generate Method

```python
    def generate(self, prompt: str) -> dict:
        """
        Try each model tier in order. Fall back to cache, then to a
        degradation message. Always returns a dict with 'text' and 'tier'.
        """
        for i, model_config in enumerate(self.models):
            try:
                start = time.time()
                text = call_with_timeout(
                    lambda: self._call_model(model_config, prompt),
                    timeout=model_config.timeout,
                )
                elapsed = time.time() - start

                self._put_in_cache(prompt, text)
                tier = "primary" if i == 0 else "fallback"
                self._stats[tier] += 1

                return {
                    "text": text,
                    "tier": tier,
                    "model": model_config.model,
                    "latency_seconds": elapsed,
                }

            except Exception as e:
                print(f"[tier {i+1}: {model_config.model}] failed: {e}")
                continue  # try next tier

        # No model succeeded: try cache
        cached = self._get_from_cache(prompt)
        if cached:
            self._stats["cache"] += 1
            return {
                "text": cached,
                "tier": "cache",
                "model": "cache",
                "latency_seconds": 0.0,
            }

        # Final fallback: degradation message
        self._stats["degraded"] += 1
        return {
            "text": self.degradation_message,
            "tier": "degraded",
            "model": "none",
            "latency_seconds": 0.0,
        }
```

> **Real-world check:** Your CTO looks at the fallback chain and says: "If we fall back to GPT-4o-mini when Claude is down, we are paying OpenAI for requests we normally send to Anthropic. Why should we pay for both providers just for a failover that might happen once a month?" What is the cost argument for maintaining the secondary model relationship?

### Step 5: The Model Caller

```python
    def _call_model(self, config: ModelConfig, prompt: str) -> str:
        """Route the call to the appropriate provider SDK."""
        if config.provider == "anthropic":
            return self._call_anthropic(config, prompt)
        elif config.provider == "openai":
            return self._call_openai(config, prompt)
        else:
            raise ValueError(f"Unknown provider: {config.provider}")

    def _call_anthropic(self, config: ModelConfig, prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    def _call_openai(self, config: ModelConfig, prompt: str) -> str:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model=config.model,
            max_tokens=config.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
```

---

## Use It

Wire the `FallbackChain` into the FastAPI service and expose the tier information in the response so callers know which model served them:

```python
from fastapi import FastAPI
from settings import get_settings
from fallback_chain import FallbackChain, ModelConfig

app = FastAPI()
settings = get_settings()

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
        "Our AI assistant is temporarily unavailable. "
        "Please try again in a few minutes or contact support."
    ),
    cache_ttl=300.0,
)


@app.post("/generate")
def generate(prompt: str):
    result = chain.generate(prompt)
    return {
        "text": result["text"],
        "model": result["model"],
        "tier": result["tier"],       # primary / fallback / cache / degraded
        "latency": result["latency_seconds"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "chain_stats": chain.stats}
```

The `tier` field in the response is operational signal. If clients start logging it, your ops team can see when fallback rate climbs, before a user files a support ticket.

> **Perspective shift:** A teammate argues that exposing `tier` in the API response is a mistake because "users should not know which model answered their question -- it might make them distrust the fallback." What is the counterargument for transparency, and who should see the tier information even if end users do not?

---

## Ship It

The reusable artifact for this lesson is `outputs/skill-model-fallback-chain.md`: a `FallbackChain` template with the four-tier pattern and the operational metrics you should track. Drop it into any service that calls an AI model.

To use it:
1. Copy `code/main.py` (or extract the `FallbackChain` class) into your service.
2. Configure the `models` list with your primary and secondary providers.
3. Set `cache_ttl` based on how long responses remain valid for your use case (static content: hours; personalized content: shorter or zero).
4. In your API layer, log the `tier` field on every response. Alert when `fallback_rate > 0.02` (2% of requests falling back indicates a primary model problem).

---

## Evaluate It

**Check 1: Fallback triggers on timeout.**
Set the primary model's timeout to 0.001 seconds. Every request should fall through to the secondary model. Verify `result["tier"] == "fallback"`.

```python
chain = FallbackChain(
    models=[
        ModelConfig(provider="anthropic", model="claude-3-5-haiku-20241022", timeout=0.001),
        ModelConfig(provider="openai", model="gpt-4o-mini", timeout=15.0),
    ]
)
result = chain.generate("Hello")
assert result["tier"] == "fallback", f"Expected fallback, got {result['tier']}"
```

**Check 2: Cache hit on repeated prompt.**
Send the same prompt twice. The second call should return `tier="cache"` with near-zero latency.

```python
result1 = chain.generate("What is 2+2?")
result2 = chain.generate("What is 2+2?")
assert result2["tier"] == "cache"
assert result2["latency_seconds"] < 0.01
```

**Check 3: Degradation message as last resort.**
Set all model timeouts to 0.001 seconds and clear the cache. All tiers fail. The result should be `tier="degraded"` with the static degradation message.

**Check 4: Fallback rate metric.**
Run 100 requests through the chain with a broken primary (timeout=0.001). Check `chain.stats`. The `fallback` count should be approximately 100, `primary` count should be 0.

```python
for _ in range(100):
    chain.generate("test prompt")
assert chain.stats["primary"] == 0
assert chain.stats["fallback"] + chain.stats["cache"] + chain.stats["degraded"] == 100
```
