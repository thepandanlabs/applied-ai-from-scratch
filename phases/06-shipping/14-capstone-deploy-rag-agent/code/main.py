"""
Lesson 14: Capstone - Deploy a RAG Service Publicly
Phase 06: Shipping

Assembles all Phase 06 patterns into one production-ready service:
  - FastAPI with lifespan hook
  - Pydantic Settings for config
  - VersionManifest loaded at startup
  - Input validation
  - Streaming (SSE) endpoint
  - RAG pipeline (in-memory vector store)
  - Retry + circuit breaker resilience
  - Feature flag for prompt version routing
  - Background ingest endpoint
  - /health and /ready endpoints

Usage:
    # Register a manifest first (required before starting)
    python main.py register

    # Start the service
    uvicorn main:app --host 0.0.0.0 --port 8000

    # Or via Docker (see Dockerfile)
    docker build -t rag-capstone .
    docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... rag-capstone

Requires:
    ANTHROPIC_API_KEY environment variable (required)
    OPENAI_API_KEY environment variable (optional, for fallback)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Optional

import anthropic
import numpy as np
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MANIFEST_FILE = Path("manifests.yaml")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """All configuration from environment variables. Missing required values crash at startup."""

    anthropic_api_key: str
    openai_api_key: str = ""
    model_id: str = "claude-3-5-haiku-20241022"
    fallback_model_id: str = "gpt-4o-mini"
    max_tokens: int = 512
    temperature: float = 0.3
    top_k: int = 5
    max_retries: int = 3
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout_seconds: int = 60
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


# ---------------------------------------------------------------------------
# Version manifest (from Lesson 12)
# ---------------------------------------------------------------------------


@dataclass
class VersionManifest:
    manifest_id: str
    prompt_version: str
    model_id: str
    config_hash: str
    deployed_at: str
    deployed_by: str = "local"
    notes: str = ""


def hash_config(config: dict) -> str:
    serialized = json.dumps(config, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]


class ManifestRegistry:
    def __init__(self, path: Path = MANIFEST_FILE) -> None:
        self.path = path
        self._manifests: list[VersionManifest] = []
        self._current_id: Optional[str] = None
        if self.path.exists() and YAML_AVAILABLE:
            self._load()

    def _load(self) -> None:
        data = yaml.safe_load(self.path.read_text())
        if not data:
            return
        self._current_id = data.get("current")
        for entry in data.get("history", []):
            self._manifests.append(VersionManifest(**entry))

    def _save(self) -> None:
        if not YAML_AVAILABLE:
            raise RuntimeError("pyyaml is required to save manifests")
        data = {
            "current": self._current_id,
            "history": [asdict(m) for m in self._manifests],
        }
        self.path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=True))

    def register(self, manifest: VersionManifest) -> None:
        if "latest" in manifest.model_id.lower():
            raise ValueError(f"Model alias '{manifest.model_id}' not allowed. Use a pinned ID.")
        self._manifests.append(manifest)
        self._current_id = manifest.manifest_id
        self._save()

    def current(self) -> Optional[VersionManifest]:
        if not self._current_id:
            return None
        for m in self._manifests:
            if m.manifest_id == self._current_id:
                return m
        return None

    def rollback(self, manifest_id: str) -> VersionManifest:
        for m in self._manifests:
            if m.manifest_id == manifest_id:
                self._current_id = manifest_id
                self._save()
                return m
        available = [m.manifest_id for m in self._manifests]
        raise ValueError(f"Manifest '{manifest_id}' not found. Available: {available}")


# ---------------------------------------------------------------------------
# Feature flags (from Lesson 13)
# ---------------------------------------------------------------------------


class RolloutMode(str, Enum):
    SHADOW = "shadow"
    CANARY = "canary"
    AB = "ab"


@dataclass
class FeatureFlag:
    name: str
    rollout_pct: float
    mode: RolloutMode
    variant_a: str
    variant_b: str

    def _bucket(self, user_id: str) -> int:
        key = f"{self.name}:{user_id}"
        digest = hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()
        return int(digest[:8], 16) % 100

    def variant_for(self, user_id: str) -> str:
        return "b" if self._bucket(user_id) < self.rollout_pct else "a"

    def prompt_for(self, user_id: str) -> str:
        v = self.variant_for(user_id)
        return self.variant_b if v == "b" else self.variant_a


# ---------------------------------------------------------------------------
# Circuit breaker (from Lesson 07)
# ---------------------------------------------------------------------------


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, threshold: int = 5, timeout_seconds: int = 60) -> None:
        self.threshold = threshold
        self.timeout = timeout_seconds
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self._opened_at: Optional[float] = None

    def is_open(self) -> bool:
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at > self.timeout:
                self.state = CircuitState.HALF_OPEN
                return False
            return True
        return False

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self.state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning("Circuit breaker OPENED after %d failures", self.failure_count)


# ---------------------------------------------------------------------------
# RAG pipeline (simplified from Phase 02)
# ---------------------------------------------------------------------------


def embed_texts(texts: list[str], client: anthropic.Anthropic) -> list[list[float]]:
    """
    Embed texts using a simple hash-based mock for dev/test.
    In production, replace with a real embedding model.
    Note: anthropic does not provide an embedding API; use OpenAI or
    a local model (e.g., sentence-transformers) for real embeddings.
    """
    # Deterministic pseudo-embedding for demonstration
    # Replace with: openai_client.embeddings.create(model="text-embedding-3-small", input=texts)
    vectors = []
    for text in texts:
        h = hashlib.sha256(text.encode()).digest()
        vec = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
        vec = vec / (np.linalg.norm(vec) + 1e-8)
        # Pad or trim to 64 dimensions for consistency
        if len(vec) < 64:
            vec = np.pad(vec, (0, 64 - len(vec)))
        else:
            vec = vec[:64]
        vectors.append(vec.tolist())
    return vectors


def add_to_store(store: dict, text: str, vector: list[float], source: str = "unknown") -> str:
    chunk_id = str(uuid.uuid4())[:8]
    store[chunk_id] = {
        "text": text,
        "vector": np.array(vector, dtype=np.float32),
        "metadata": {"source": source},
    }
    return chunk_id


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


def retrieve(query: str, store: dict, top_k: int, client: anthropic.Anthropic) -> list[dict]:
    if not store:
        return []
    query_vec = np.array(embed_texts([query], client)[0], dtype=np.float32)
    scored = [
        {"id": cid, "text": entry["text"], "score": cosine_similarity(query_vec, entry["vector"]),
         "metadata": entry["metadata"]}
        for cid, entry in store.items()
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


SYSTEM_PROMPTS = {
    "v1.0": "You are a helpful assistant. Answer using only the provided context. Be concise.",
    "v1.1": (
        "You are a helpful assistant. Answer using only the provided context. "
        "Be concise and end your response with a one-line summary starting with 'In short:'"
    ),
}


def build_rag_prompt(query: str, chunks: list[dict]) -> str:
    if not chunks:
        context = "[No relevant context found. Answer based on general knowledge if appropriate.]"
    else:
        parts = [f"[Source {i+1}: {c['metadata'].get('source', 'unknown')}]\n{c['text']}"
                 for i, c in enumerate(chunks)]
        context = "\n\n---\n\n".join(parts)
    return f"Context:\n{context}\n\n---\n\nQuestion: {query}\n\nAnswer:"


# ---------------------------------------------------------------------------
# Resilience: call model with retry + circuit breaker + fallback
# ---------------------------------------------------------------------------


async def call_primary(
    settings: Settings, prompt: str, system: str, model_id: str
) -> str:
    """Async call to Claude. Raises anthropic.APIError on failure."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=model_id,
        max_tokens=settings.max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


async def call_fallback(settings: Settings, prompt: str, system: str) -> str:
    """Fallback: try OpenAI if available, else return a static message."""
    if settings.openai_api_key:
        try:
            import openai  # type: ignore
            client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.chat.completions.create(
                model=settings.fallback_model_id,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=settings.max_tokens,
            )
            return response.choices[0].message.content
        except Exception as exc:
            logger.error("Fallback model also failed: %s", exc)

    return (
        "The AI service is temporarily unavailable. "
        "Please try again in a few minutes."
    )


async def call_with_resilience(
    settings: Settings,
    cb: CircuitBreaker,
    prompt: str,
    system: str,
    model_id: str,
) -> str:
    """Primary model with retry + circuit breaker + fallback."""
    if cb.is_open():
        logger.warning("Circuit open - routing to fallback")
        return await call_fallback(settings, prompt, system)

    for attempt in range(settings.max_retries):
        try:
            result = await call_primary(settings, prompt, system, model_id)
            cb.record_success()
            return result
        except anthropic.RateLimitError:
            wait = 2 ** attempt
            logger.warning("Rate limit, retry in %ds (attempt %d/%d)", wait, attempt + 1, settings.max_retries)
            await asyncio.sleep(wait)
        except anthropic.APIError as exc:
            cb.record_failure()
            logger.error("API error (attempt %d): %s", attempt + 1, exc)
            if cb.is_open():
                return await call_fallback(settings, prompt, system)
            if attempt < settings.max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                raise

    return await call_fallback(settings, prompt, system)


# ---------------------------------------------------------------------------
# Service assembly
# ---------------------------------------------------------------------------

ROLLOUT_FLAG = FeatureFlag(
    name="prompt-v1.1-rollout",
    rollout_pct=10.0,
    mode=RolloutMode.SHADOW,
    variant_a="v1.0",
    variant_b="v1.1",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: load and validate all service state.
    Fail fast if anything is missing or misconfigured.
    """
    # 1. Load settings (raises ValidationError if ANTHROPIC_API_KEY missing)
    settings = Settings()
    logging.getLogger().setLevel(settings.log_level)

    # 2. Load version manifest (fail fast if not registered)
    registry = ManifestRegistry(MANIFEST_FILE)
    manifest = registry.current()
    if manifest is None:
        raise RuntimeError(
            "No active manifest found. "
            "Run: python main.py register"
        )

    # 3. Initialize circuit breaker
    cb = CircuitBreaker(
        threshold=settings.circuit_breaker_threshold,
        timeout_seconds=settings.circuit_breaker_timeout_seconds,
    )

    # 4. Initialize empty RAG store
    store: dict = {}

    # 5. Log startup state - every field must appear for runbook compliance
    logger.info("=== SERVICE STARTUP ===")
    logger.info("manifest_id:     %s", manifest.manifest_id)
    logger.info("prompt_version:  %s", manifest.prompt_version)
    logger.info("model_id:        %s", manifest.model_id)
    logger.info("config_hash:     %s", manifest.config_hash)
    logger.info("deployed_at:     %s", manifest.deployed_at)
    logger.info("deployed_by:     %s", manifest.deployed_by)
    logger.info("flag:            %s mode=%s pct=%.0f%%",
                ROLLOUT_FLAG.name, ROLLOUT_FLAG.mode, ROLLOUT_FLAG.rollout_pct)
    logger.info("=== STARTUP COMPLETE ===")

    # Store on app state
    app.state.settings = settings
    app.state.manifest = manifest
    app.state.registry = registry
    app.state.cb = cb
    app.state.store = store
    app.state.flag = ROLLOUT_FLAG

    yield

    logger.info("Service shutting down.")


app = FastAPI(
    title="RAG Capstone Service",
    description="Phase 06 capstone: all production patterns assembled",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=4096)


class IngestRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    source: str = Field(default="user-upload", max_length=256)


class RollbackRequest(BaseModel):
    manifest_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Health check. Returns manifest data. First thing ops checks in an incident."""
    manifest = app.state.manifest
    cb = app.state.cb
    return {
        "status": "ok",
        "manifest_id": manifest.manifest_id,
        "prompt_version": manifest.prompt_version,
        "model_id": manifest.model_id,
        "config_hash": manifest.config_hash,
        "deployed_at": manifest.deployed_at,
        "circuit_breaker": cb.state,
        "store_size": len(app.state.store),
    }


@app.get("/ready")
async def ready():
    """Readiness probe. Returns 503 if circuit breaker is open."""
    cb = app.state.cb
    if cb.is_open():
        raise HTTPException(status_code=503, detail="Circuit breaker open")
    return {"status": "ready"}


@app.post("/chat")
async def chat(request: ChatRequest):
    """Chat with the RAG service. Feature flag routes to prompt version."""
    settings = app.state.settings
    manifest = app.state.manifest
    flag = app.state.flag
    store = app.state.store
    cb = app.state.cb

    # Feature flag: select prompt version for this user
    prompt_version = flag.prompt_for(request.user_id)
    variant = flag.variant_for(request.user_id)
    system = SYSTEM_PROMPTS.get(prompt_version, SYSTEM_PROMPTS["v1.0"])

    # RAG: retrieve and build prompt
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    chunks = retrieve(request.message, store, top_k=settings.top_k, client=client)
    prompt = build_rag_prompt(request.message, chunks)

    # Shadow mode: run variant B in background without affecting response
    if flag.mode == RolloutMode.SHADOW and variant == "a":
        asyncio.create_task(
            _shadow_call(settings, manifest, flag, request, prompt, chunks)
        )

    # Call model with resilience
    response_text = await call_with_resilience(
        settings=settings,
        cb=cb,
        prompt=prompt,
        system=system,
        model_id=manifest.model_id,
    )

    return {
        "response": response_text,
        "manifest_id": manifest.manifest_id,
        "prompt_version": prompt_version,
        "variant": variant,
        "sources": [c["metadata"].get("source") for c in chunks],
    }


async def _shadow_call(settings, manifest, flag, request, prompt, chunks):
    """Background shadow: call variant B, log for comparison. Never shown to users."""
    system_b = SYSTEM_PROMPTS.get(flag.variant_b, SYSTEM_PROMPTS["v1.0"])
    try:
        result_b = await call_primary(settings, prompt, system_b, manifest.model_id)
        logger.info(
            "shadow_b flag=%s user=%s tokens=%d preview='%s'",
            flag.name, request.user_id, len(result_b.split()),
            result_b[:80].replace("\n", " "),
        )
    except Exception as exc:
        logger.warning("Shadow B call failed (non-blocking): %s", exc)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Streaming chat via Server-Sent Events. Tokens arrive as they are generated."""
    settings = app.state.settings
    manifest = app.state.manifest
    flag = app.state.flag
    store = app.state.store

    prompt_version = flag.prompt_for(request.user_id)
    system = SYSTEM_PROMPTS.get(prompt_version, SYSTEM_PROMPTS["v1.0"])

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    chunks = retrieve(request.message, store, top_k=settings.top_k, client=client)
    prompt = build_rag_prompt(request.message, chunks)

    async def token_stream() -> AsyncIterator[str]:
        async_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        try:
            async with async_client.messages.stream(
                model=manifest.model_id,
                max_tokens=settings.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield f"data: {json.dumps({'token': text})}\n\n"
            yield "data: [DONE]\n\n"
        except anthropic.APIError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        token_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/ingest")
async def ingest(request: IngestRequest, background_tasks: BackgroundTasks):
    """
    Ingest a text chunk into the RAG vector store.
    Returns immediately; embedding runs in the background.
    """
    background_tasks.add_task(
        _ingest_background,
        text=request.text,
        source=request.source,
        store=app.state.store,
        settings=app.state.settings,
    )
    return {"status": "accepted", "source": request.source}


def _ingest_background(text: str, source: str, store: dict, settings: Settings) -> None:
    """Background task: embed the text and add to the vector store."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    vector = embed_texts([text], client)[0]
    chunk_id = add_to_store(store, text, vector, source=source)
    logger.info("Ingested chunk %s from source '%s' (store size: %d)", chunk_id, source, len(store))


@app.get("/circuit-breaker")
async def circuit_breaker_status():
    """Returns circuit breaker state and failure count."""
    cb = app.state.cb
    return {
        "state": cb.state,
        "failure_count": cb.failure_count,
        "threshold": cb.threshold,
    }


@app.post("/rollback")
async def rollback(request: RollbackRequest):
    """
    Roll back to a previous manifest by ID.
    The service must restart to activate the rolled-back manifest.
    """
    registry = app.state.registry
    try:
        target = registry.rollback(request.manifest_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "rolled_back_to": target.manifest_id,
        "model_id": target.model_id,
        "note": "Restart the service to activate the rolled-back manifest.",
    }


# ---------------------------------------------------------------------------
# CLI: register a manifest before first start
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2 or sys.argv[1] != "register":
        print("Usage: python main.py register")
        print("  Registers the initial version manifest required to start the service.")
        sys.exit(1)

    print("Registering initial manifest...")
    registry = ManifestRegistry(MANIFEST_FILE)

    config = {
        "temperature": 0.3,
        "max_tokens": 512,
        "top_k": 5,
        "retries": 3,
    }

    manifest = VersionManifest(
        manifest_id="v1.0.0",
        prompt_version="v1.0",
        model_id="claude-3-5-haiku-20241022",
        config_hash=hash_config(config),
        deployed_at=datetime.now(timezone.utc).isoformat(),
        deployed_by="setup",
        notes="Initial production manifest",
    )

    try:
        registry.register(manifest)
        print(f"Manifest registered: {manifest.manifest_id}")
        print(f"  model_id:      {manifest.model_id}")
        print(f"  config_hash:   {manifest.config_hash}")
        print(f"  deployed_at:   {manifest.deployed_at}")
        print(f"\nManifest written to: {MANIFEST_FILE.absolute()}")
        print("\nNow start the service:")
        print("  uvicorn main:app --host 0.0.0.0 --port 8000")
    except Exception as exc:
        print(f"Registration failed: {exc}")
        sys.exit(1)
