"""
Lesson 12: Versioning Prompts, Models, and Configs in Production
Phase 06: Shipping

A VersionManifest ties together the three moving parts of a production AI service:
  - prompt_version: which prompt template is active
  - model_id: the pinned model identifier (never an alias)
  - config_hash: SHA-256 fingerprint of the service config dict

Usage:
    python main.py              # run the demo: register two versions, roll back
    uvicorn main:app --reload   # start the FastAPI service (requires manifests.yaml)
"""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import anthropic
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------

MANIFEST_FILE = Path("manifests.yaml")


@dataclass
class VersionManifest:
    """Records the exact combination of prompt, model, and config deployed together."""

    manifest_id: str   # e.g. "v1.2.0"
    prompt_version: str  # e.g. "v1.2"
    model_id: str      # e.g. "claude-3-5-haiku-20241022" - pinned, never alias
    config_hash: str   # first 8 hex chars of SHA-256 of the config dict
    deployed_at: str   # ISO-8601 UTC timestamp
    deployed_by: str = "local"
    notes: str = ""


def hash_config(config: dict) -> str:
    """
    Compute a short, stable SHA-256 hash of a config dict.
    Keys are sorted so insertion order does not affect the hash.
    Returns first 8 hex characters.
    """
    serialized = json.dumps(config, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]


def make_manifest(
    manifest_id: str,
    prompt_version: str,
    model_id: str,
    config: dict,
    deployed_by: str = "local",
    notes: str = "",
) -> VersionManifest:
    """Factory: builds a VersionManifest from raw inputs. Computes the config hash."""
    return VersionManifest(
        manifest_id=manifest_id,
        prompt_version=prompt_version,
        model_id=model_id,
        config_hash=hash_config(config),
        deployed_at=datetime.now(timezone.utc).isoformat(),
        deployed_by=deployed_by,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ManifestRegistry:
    """
    Loads, saves, and queries VersionManifest records from a YAML file.
    The YAML file is git-tracked alongside your code.
    """

    def __init__(self, path: Path = MANIFEST_FILE) -> None:
        self.path = path
        self._manifests: list[VersionManifest] = []
        self._current_id: Optional[str] = None
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        data = yaml.safe_load(self.path.read_text())
        if not data:
            return
        self._current_id = data.get("current")
        for entry in data.get("history", []):
            self._manifests.append(VersionManifest(**entry))

    def _save(self) -> None:
        data = {
            "current": self._current_id,
            "history": [asdict(m) for m in self._manifests],
        }
        self.path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=True))

    def register(self, manifest: VersionManifest) -> None:
        """Add a new manifest and mark it as current. Rejects model aliases."""
        model_lower = manifest.model_id.lower()
        if "latest" in model_lower or model_lower.endswith(("-turbo", "-preview")):
            raise ValueError(
                f"Model alias '{manifest.model_id}' is not allowed. "
                "Use a pinned model ID such as 'claude-3-5-haiku-20241022'."
            )
        self._manifests.append(manifest)
        self._current_id = manifest.manifest_id
        self._save()

    def current(self) -> Optional[VersionManifest]:
        """Return the currently active manifest."""
        if not self._current_id:
            return None
        return self.get(self._current_id)

    def get(self, manifest_id: str) -> Optional[VersionManifest]:
        """Retrieve a specific manifest by ID."""
        for m in self._manifests:
            if m.manifest_id == manifest_id:
                return m
        return None

    def history(self) -> list[VersionManifest]:
        """Return all manifests in registration order (oldest first)."""
        return list(self._manifests)


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def rollback(registry: ManifestRegistry, manifest_id: str) -> VersionManifest:
    """
    Roll back to a previous manifest by ID.

    This changes which manifest is marked as current. The caller must
    ensure the corresponding config is also restored - the manifest is
    an index, not a config backup.
    """
    target = registry.get(manifest_id)
    if target is None:
        available = [m.manifest_id for m in registry.history()]
        raise ValueError(
            f"Manifest '{manifest_id}' not found. Available: {available}"
        )
    registry._current_id = manifest_id
    registry._save()
    logger.info("Rolled back to manifest %s", manifest_id)
    logger.info("  prompt_version: %s", target.prompt_version)
    logger.info("  model_id:       %s", target.model_id)
    logger.info("  config_hash:    %s", target.config_hash)
    logger.info("  deployed_at:    %s", target.deployed_at)
    return target


# ---------------------------------------------------------------------------
# FastAPI integration
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log the active manifest at startup. Fail fast if none is registered."""
    registry = ManifestRegistry(MANIFEST_FILE)
    manifest = registry.current()

    if manifest is None:
        raise RuntimeError(
            "No active manifest found. "
            "Run 'python main.py' first to register a manifest."
        )

    logger.info("=== SERVICE STARTUP ===")
    logger.info("manifest_id:     %s", manifest.manifest_id)
    logger.info("prompt_version:  %s", manifest.prompt_version)
    logger.info("model_id:        %s", manifest.model_id)
    logger.info("config_hash:     %s", manifest.config_hash)
    logger.info("deployed_at:     %s", manifest.deployed_at)
    logger.info("deployed_by:     %s", manifest.deployed_by)
    if manifest.notes:
        logger.info("notes:           %s", manifest.notes)
    logger.info("=== STARTUP COMPLETE ===")

    app.state.manifest = manifest
    app.state.registry = registry

    yield

    logger.info("Service shutting down.")


app = FastAPI(title="Versioned AI Service", lifespan=lifespan)
_client = anthropic.Anthropic()


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
async def health():
    """Returns active manifest with every health check. First thing ops checks."""
    manifest = app.state.manifest
    return {
        "status": "ok",
        "manifest_id": manifest.manifest_id,
        "prompt_version": manifest.prompt_version,
        "model_id": manifest.model_id,
        "config_hash": manifest.config_hash,
        "deployed_at": manifest.deployed_at,
        "deployed_by": manifest.deployed_by,
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat endpoint. Uses the model ID from the active manifest.
    Logs which manifest served each request for traceability.
    """
    manifest = app.state.manifest

    try:
        response = _client.messages.create(
            model=manifest.model_id,
            max_tokens=512,
            messages=[{"role": "user", "content": request.message}],
        )
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "response": response.content[0].text,
        "manifest_id": manifest.manifest_id,
        "model_id": manifest.model_id,
        "prompt_tokens": response.usage.input_tokens,
        "completion_tokens": response.usage.output_tokens,
    }


@app.post("/rollback/{manifest_id}")
async def rollback_endpoint(manifest_id: str):
    """
    Roll back to a previous manifest by ID.
    In a real system this would require authentication.
    The service must restart to pick up the new active manifest.
    """
    registry = app.state.registry
    try:
        target = rollback(registry, manifest_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "rolled_back_to": target.manifest_id,
        "note": "Restart the service to activate the rolled-back manifest.",
    }


# ---------------------------------------------------------------------------
# Demo: run from command line to register manifests and test rollback
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    demo_path = Path("demo_manifests.yaml")
    registry = ManifestRegistry(demo_path)

    config_v1 = {
        "temperature": 0.3,
        "max_tokens": 512,
        "retries": 3,
        "system_prompt": "You are a helpful assistant. Be concise.",
    }
    config_v2 = {
        "temperature": 0.7,
        "max_tokens": 1024,
        "retries": 3,
        "system_prompt": "You are a helpful assistant. Be detailed and thorough.",
    }

    print("=== Registering v1.0.0 ===")
    m1 = make_manifest(
        manifest_id="v1.0.0",
        prompt_version="v1.0",
        model_id="claude-3-5-haiku-20241022",
        config=config_v1,
        deployed_by="alice",
        notes="Initial production deploy",
    )
    registry.register(m1)
    print(f"Registered: {m1.manifest_id}  config_hash={m1.config_hash}")

    print("\n=== Registering v1.1.0 ===")
    m2 = make_manifest(
        manifest_id="v1.1.0",
        prompt_version="v1.1",
        model_id="claude-3-5-haiku-20241022",
        config=config_v2,
        deployed_by="bob",
        notes="Higher temperature for more creative responses",
    )
    registry.register(m2)
    print(f"Registered: {m2.manifest_id}  config_hash={m2.config_hash}")

    print(f"\nCurrent manifest: {registry.current().manifest_id}")

    print("\n=== Testing alias rejection ===")
    try:
        bad = make_manifest(
            manifest_id="v1.2.0",
            prompt_version="v1.2",
            model_id="claude-haiku-latest",  # alias - should be rejected
            config=config_v1,
        )
        registry.register(bad)
        print("ERROR: alias was not rejected!")
        sys.exit(1)
    except ValueError as e:
        print(f"Correctly rejected alias: {e}")

    print("\n=== Rolling back to v1.0.0 ===")
    rollback(registry, "v1.0.0")
    print(f"Active after rollback: {registry.current().manifest_id}")

    print("\n=== Full History ===")
    for m in registry.history():
        marker = " <-- current" if m.manifest_id == registry.current().manifest_id else ""
        print(
            f"  {m.manifest_id:<10}  prompt={m.prompt_version}  "
            f"model={m.model_id}  config={m.config_hash}{marker}"
        )

    print(f"\nManifest file written to: {demo_path.absolute()}")
    print("Inspect it with: cat demo_manifests.yaml")
