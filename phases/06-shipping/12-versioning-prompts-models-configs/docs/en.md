# Versioning Prompts, Models, and Configs in Production

> What runs in production right now? If you cannot answer that in ten seconds, you have a versioning problem.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lesson 06 (config and secrets), Lesson 02 (wrapping model in FastAPI)
**Time:** ~45 min
**Learning Objectives:**
- Identify the three moving parts of a production AI service and explain why each needs its own version
- Build a `VersionManifest` dataclass that ties prompt version, model ID, and config hash together
- Implement a YAML-based manifest registry with a rollback function
- Integrate manifest logging into FastAPI startup so every deployment is self-describing
- Explain why pinning model IDs (not aliases) prevents silent behavior changes

---

## The Problem

Your AI service was working fine last Tuesday. Today it is producing subtly different outputs. Nothing in your git history changed. No deployments happened. What broke?

The model provider quietly updated the endpoint behind `claude-haiku-latest`. Or your config file got a one-line edit that changed the system prompt temperature. Or a colleague updated the prompt template while you were asleep, and the change went live without any record of when or by whom.

AI services have three moving parts that code versioning does not capture:

1. The prompt template (changes frequently, often by non-engineers)
2. The model identifier (can change under you when you use aliases)
3. The service config (temperature, max tokens, retry limits, timeouts)

Any one of these changing silently can change output behavior in ways that look like model failures, user complaints, or eval regressions, when the real culprit is a config drift you cannot trace.

The fix is a version manifest: a single file that records the exact combination of all three that was deployed together. When something breaks, you look at the manifest, find the last known-good combination, and roll back. Without a manifest, rollback means guessing.

---

## The Concept

### Three Components, One Manifest

```
+-------------------+    +-------------------+    +-------------------+
|  PROMPT TEMPLATE  |    |    MODEL ID        |    |  SERVICE CONFIG   |
|                   |    |                    |    |                   |
|  version: v1.2    |    |  claude-3-5-haiku  |    |  hash: a4f9c2b1   |
|  commit: abc123   |    |  -20241022         |    |  temp: 0.3        |
|  author: alice    |    |  (pinned, not      |    |  max_tokens: 512  |
|                   |    |   an alias)        |    |  retries: 3       |
+-------------------+    +-------------------+    +-------------------+
          |                       |                         |
          +-------------------------------------------+-----+
                                  |
                    +-------------v-----------+
                    |    VERSION MANIFEST      |
                    |                          |
                    |  manifest_id: v1.2.0     |
                    |  prompt_version: v1.2    |
                    |  model_id: claude-3-5-   |
                    |    haiku-20241022        |
                    |  config_hash: a4f9c2b1   |
                    |  deployed_at: 2025-01-15 |
                    |  deployed_by: ci-bot     |
                    +--------------------------+
                                  |
                    +-------------v-----------+
                    |  MANIFEST REGISTRY       |
                    |  (YAML file, git-tracked)|
                    |                          |
                    |  current: v1.2.0         |
                    |  history: [v1.1.0, ...]  |
                    +--------------------------+
```

### Why Pin Model IDs, Not Aliases

Model aliases (`claude-haiku-latest`, `gpt-4-turbo`) are updated by providers without announcement. One day `claude-haiku-latest` routes to model version X. The next day it routes to model version Y. Your prompt was tuned against X. Version Y has different instruction-following behavior. Your evals start failing and you do not know why.

Pinned IDs solve this:

```
WRONG:  model: "claude-haiku-latest"       # silently changes
RIGHT:  model: "claude-3-5-haiku-20241022" # immutable
```

The manifest enforces pinning at registration time: if the model ID contains `-latest` or ends without a date suffix, the registry rejects it.

### Config Hash vs Config Values

Storing the full config in the manifest creates a long file that is hard to diff. Storing only the hash lets you answer "did the config change?" cheaply. When you need to inspect what changed, you look up the config file by its hash. The manifest is the index; the config file is the source of truth.

---

## Build It

### Step 1: The VersionManifest Dataclass

```python
# code/main.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class VersionManifest:
    """Records the exact combination of prompt, model, and config deployed together."""
    manifest_id: str           # e.g. "v1.2.0"
    prompt_version: str        # e.g. "v1.2" (matches git tag or semver)
    model_id: str              # e.g. "claude-3-5-haiku-20241022" (pinned, never alias)
    config_hash: str           # first 8 chars of SHA-256 of the config dict
    deployed_at: str           # ISO-8601 UTC timestamp
    deployed_by: str = "local" # person or CI system that deployed
    notes: str = ""            # optional release note


def hash_config(config: dict) -> str:
    """
    Compute a short, stable SHA-256 hash of a config dict.
    Keys are sorted so insertion order does not affect the hash.
    Returns first 8 hex characters.
    """
    serialized = json.dumps(config, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]
```

The dataclass is a plain value object. No ORM, no database. It is just data you can serialize to YAML and read back.

### Step 2: The Manifest Registry

```python
MANIFEST_FILE = Path("manifests.yaml")


class ManifestRegistry:
    """
    Loads, saves, and queries VersionManifest records from a YAML file.
    The YAML file is meant to be git-tracked alongside your code.
    """

    def __init__(self, path: Path = MANIFEST_FILE):
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
        """Add a new manifest and mark it as current."""
        if "latest" in manifest.model_id.lower():
            raise ValueError(
                f"Model alias '{manifest.model_id}' is not allowed. "
                "Use a pinned model ID like 'claude-3-5-haiku-20241022'."
            )
        self._manifests.append(manifest)
        self._current_id = manifest.manifest_id
        self._save()

    def current(self) -> Optional[VersionManifest]:
        """Return the currently active manifest."""
        if not self._current_id:
            return None
        for m in self._manifests:
            if m.manifest_id == self._current_id:
                return m
        return None

    def get(self, manifest_id: str) -> Optional[VersionManifest]:
        """Retrieve a specific manifest by ID."""
        for m in self._manifests:
            if m.manifest_id == manifest_id:
                return m
        return None

    def history(self) -> list[VersionManifest]:
        """Return all manifests in registration order."""
        return list(self._manifests)
```

### Step 3: Rollback Function

```python
def rollback(registry: ManifestRegistry, manifest_id: str) -> VersionManifest:
    """
    Roll back to a previous manifest by ID.
    This does NOT revert config files - it only changes which manifest
    is marked as current. The caller is responsible for loading the
    config that corresponds to the rolled-back manifest.

    Returns the manifest that is now active.
    """
    target = registry.get(manifest_id)
    if target is None:
        raise ValueError(
            f"Manifest '{manifest_id}' not found in registry. "
            f"Available: {[m.manifest_id for m in registry.history()]}"
        )
    registry._current_id = manifest_id
    registry._save()
    print(f"Rolled back to manifest {manifest_id}")
    print(f"  prompt_version: {target.prompt_version}")
    print(f"  model_id:       {target.model_id}")
    print(f"  config_hash:    {target.config_hash}")
    print(f"  deployed_at:    {target.deployed_at}")
    return target
```

> **Real-world check:** Your on-call engineer gets paged at 2 a.m. because AI responses suddenly got much longer and are confusing users. They check the git log: no code changes in 48 hours. They check the model provider status page: no incidents. How does having a version manifest change what they do in the next 5 minutes compared to not having one?

### Step 4: Creating a Manifest at Deploy Time

```python
def make_manifest(
    manifest_id: str,
    prompt_version: str,
    model_id: str,
    config: dict,
    deployed_by: str = "local",
    notes: str = "",
) -> VersionManifest:
    """
    Factory: builds a VersionManifest from raw inputs.
    Computes the config hash automatically.
    """
    return VersionManifest(
        manifest_id=manifest_id,
        prompt_version=prompt_version,
        model_id=model_id,
        config_hash=hash_config(config),
        deployed_at=datetime.now(timezone.utc).isoformat(),
        deployed_by=deployed_by,
        notes=notes,
    )


# Demo: register two versions and roll back
if __name__ == "__main__":
    registry = ManifestRegistry(Path("demo_manifests.yaml"))

    config_v1 = {"temperature": 0.3, "max_tokens": 512, "retries": 3}
    config_v2 = {"temperature": 0.7, "max_tokens": 1024, "retries": 3}

    m1 = make_manifest(
        manifest_id="v1.0.0",
        prompt_version="v1.0",
        model_id="claude-3-5-haiku-20241022",
        config=config_v1,
        deployed_by="alice",
        notes="Initial production deploy",
    )
    registry.register(m1)
    print(f"Registered: {m1.manifest_id} (config_hash={m1.config_hash})")

    m2 = make_manifest(
        manifest_id="v1.1.0",
        prompt_version="v1.1",
        model_id="claude-3-5-haiku-20241022",
        config=config_v2,
        deployed_by="bob",
        notes="Increased temperature for more creative responses",
    )
    registry.register(m2)
    print(f"Registered: {m2.manifest_id} (config_hash={m2.config_hash})")

    print(f"\nCurrent manifest: {registry.current().manifest_id}")

    print("\n--- Rolling back to v1.0.0 ---")
    active = rollback(registry, "v1.0.0")
    print(f"\nActive after rollback: {registry.current().manifest_id}")

    # Show the full history
    print("\n--- Full History ---")
    for m in registry.history():
        marker = " <-- current" if m.manifest_id == registry.current().manifest_id else ""
        print(f"  {m.manifest_id}  prompt={m.prompt_version}  model={m.model_id}  config={m.config_hash}{marker}")
```

---

## Use It

Integrate the manifest registry into a FastAPI service using the lifespan pattern so the active manifest is logged at every startup. This means every deployment is self-describing: any engineer can check the logs to know exactly what is running.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import anthropic
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log the active manifest at startup. Fail fast if none is registered."""
    registry = ManifestRegistry(Path("manifests.yaml"))
    manifest = registry.current()

    if manifest is None:
        raise RuntimeError(
            "No active manifest found. Register a manifest before starting the service."
        )

    logger.info("=== SERVICE STARTUP ===")
    logger.info(f"manifest_id:     {manifest.manifest_id}")
    logger.info(f"prompt_version:  {manifest.prompt_version}")
    logger.info(f"model_id:        {manifest.model_id}")
    logger.info(f"config_hash:     {manifest.config_hash}")
    logger.info(f"deployed_at:     {manifest.deployed_at}")
    logger.info(f"deployed_by:     {manifest.deployed_by}")
    if manifest.notes:
        logger.info(f"notes:           {manifest.notes}")
    logger.info("=== STARTUP COMPLETE ===")

    # Store manifest on app state so endpoints can access it
    app.state.manifest = manifest
    app.state.registry = registry

    yield

    logger.info("Service shutting down.")


app = FastAPI(title="AI Service", lifespan=lifespan)
client = anthropic.Anthropic()


@app.get("/health")
async def health():
    """Returns the active manifest with every health check response."""
    manifest = app.state.manifest
    return {
        "status": "ok",
        "manifest_id": manifest.manifest_id,
        "prompt_version": manifest.prompt_version,
        "model_id": manifest.model_id,
        "config_hash": manifest.config_hash,
    }


@app.post("/chat")
async def chat(request: dict):
    """
    Chat endpoint that logs which manifest served each request.
    In production you would also log this to your observability platform.
    """
    manifest = app.state.manifest
    user_message = request.get("message", "")

    response = client.messages.create(
        model=manifest.model_id,
        max_tokens=512,
        messages=[{"role": "user", "content": user_message}],
    )

    return {
        "response": response.content[0].text,
        "manifest_id": manifest.manifest_id,
        "model_id": manifest.model_id,
    }
```

> **Perspective shift:** A colleague argues: "We use git for versioning. Every config change is a commit. Why do we need a separate manifest file on top of git history?" What does the manifest give you that git does not, especially when configs come from environment variables, secrets managers, or are changed by operators at runtime rather than through code?

---

## Ship It

The artifact for this lesson is `outputs/skill-version-manifest.md`: a reusable version manifest template and deployment checklist you can adapt to any AI service.

To use the code from this lesson:

```bash
# Install deps
pip install pyyaml fastapi anthropic uvicorn

# Register your first manifest
python main.py

# Start the service (requires manifests.yaml to exist)
uvicorn main:app --reload

# Check what is running
curl http://localhost:8000/health
```

---

## Evaluate It

**Check 1: Startup logs are auditable.**
For any deployment in the last 30 days, you should be able to answer from logs alone: what model ID was running, what prompt version was active, and what config hash was in use. If you cannot, the manifest is not being logged at startup.

**Check 2: Rollback works under pressure.**
Time how long it takes an engineer who has not seen this code to roll back to a previous manifest. Target: under 2 minutes. If it takes longer, the registry API is too opaque or the manifest IDs are not descriptive enough.

**Check 3: Alias rejection works.**
Attempt to register a manifest with `model_id="claude-haiku-latest"`. The registry should raise a `ValueError`. This is a hard guard: aliases must never reach production.

**Check 4: Config hash catches drift.**
Change one value in your config dict (e.g., temperature from 0.3 to 0.31). Verify the config hash changes. This confirms the hash function is sensitive to the values that actually affect model behavior.

**Check 5: Health endpoint is trusted.**
In a production incident drill, the first question should be: "what is the manifest ID right now?" If the `/health` endpoint answers this, your team will check it first instead of guessing. Measure whether your team uses it.
