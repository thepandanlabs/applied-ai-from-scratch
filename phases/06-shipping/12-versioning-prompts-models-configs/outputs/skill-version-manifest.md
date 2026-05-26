---
name: skill-version-manifest
description: Reusable version manifest template and deployment checklist for AI services - ties prompt version, model ID, and config hash into a single traceable artifact
version: "1.0"
phase: "06"
lesson: "12"
tags: [versioning, deployment, manifest, rollback, production]
---

# Version Manifest - AI Service Deployment Template

Use this template to record every production deployment of an AI service. The manifest ties together the three moving parts: prompt template version, model ID, and service config hash.

---

## manifests.yaml Template

```yaml
current: v1.0.0
history:
  - manifest_id: v1.0.0
    prompt_version: v1.0
    model_id: claude-3-5-haiku-20241022
    config_hash: a4f9c2b1
    deployed_at: "2025-01-15T09:00:00+00:00"
    deployed_by: alice
    notes: Initial production deploy
```

Rules:
- `manifest_id`: semantic version or date-based tag (e.g. `v1.0.0`, `2025-01-15`)
- `prompt_version`: matches your prompt template git tag or file version comment
- `model_id`: full pinned ID only - never `*-latest`, `*-preview`, or `*-turbo` aliases
- `config_hash`: first 8 hex chars of SHA-256 of the config dict (keys sorted)
- `deployed_at`: ISO-8601 UTC
- `deployed_by`: person name or CI system name

---

## Deployment Checklist

Before every production deploy:

- [ ] `model_id` is a pinned ID, not an alias
- [ ] `prompt_version` matches what is in the prompt template file
- [ ] `config_hash` was recomputed from the current config dict (not copied from a previous entry)
- [ ] `manifests.yaml` is committed to git alongside the deploy
- [ ] The service logs the active manifest at startup (check logs after first request)
- [ ] `/health` endpoint returns the manifest ID
- [ ] Rollback procedure tested: `POST /rollback/{previous_manifest_id}` returns 200

---

## Rollback Procedure

1. Identify the last known-good manifest ID from the history:
   ```bash
   cat manifests.yaml | grep manifest_id
   ```

2. Call the rollback endpoint:
   ```bash
   curl -X POST http://your-service/rollback/v1.0.0
   ```

3. Restart the service to activate the rolled-back manifest:
   ```bash
   # Railway: redeploy from dashboard or CLI
   # Docker: docker restart <container>
   # Kubernetes: kubectl rollout restart deployment/<name>
   ```

4. Verify the correct manifest is active:
   ```bash
   curl http://your-service/health
   # Should return: "manifest_id": "v1.0.0"
   ```

5. Confirm with the config file that the `config_hash` matches what you expect:
   ```python
   import hashlib, json
   config = {...}  # the v1.0.0 config values
   hash_val = hashlib.sha256(
       json.dumps(config, sort_keys=True).encode()
   ).hexdigest()[:8]
   print(hash_val)  # must match the config_hash in the manifest
   ```

---

## Config Hash Helper

```python
import hashlib
import json

def hash_config(config: dict) -> str:
    """Stable SHA-256 hash of a config dict. Reproducible across restarts."""
    serialized = json.dumps(config, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]

# Example
config = {"temperature": 0.3, "max_tokens": 512, "retries": 3}
print(hash_config(config))  # e.g. "a4f9c2b1"
```

---

## Model ID Pinning Reference

| Provider | Alias (do not use) | Pinned ID (use this) |
|----------|--------------------|----------------------|
| Anthropic | `claude-haiku-latest` | `claude-3-5-haiku-20241022` |
| Anthropic | `claude-sonnet-latest` | `claude-3-5-sonnet-20241022` |
| OpenAI | `gpt-4-turbo` | `gpt-4-turbo-2024-04-09` |
| OpenAI | `gpt-4o` | `gpt-4o-2024-11-20` |

Check your provider's model versions page before each deploy. Update the pinned ID when you intentionally upgrade.

---

## FastAPI Startup Log Format

Every service using this pattern should log at startup:

```
INFO: === SERVICE STARTUP ===
INFO: manifest_id:     v1.0.0
INFO: prompt_version:  v1.0
INFO: model_id:        claude-3-5-haiku-20241022
INFO: config_hash:     a4f9c2b1
INFO: deployed_at:     2025-01-15T09:00:00+00:00
INFO: deployed_by:     alice
INFO: notes:           Initial production deploy
INFO: === STARTUP COMPLETE ===
```

When investigating an incident, search your log aggregator for `=== SERVICE STARTUP ===` to find when deployments happened and what was running at any point in time.
