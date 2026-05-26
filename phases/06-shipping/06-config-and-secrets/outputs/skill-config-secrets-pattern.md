---
name: skill-config-secrets-pattern
description: Typed pydantic-settings Settings class implementing the 3-tier config resolution pattern with fail-fast startup validation and secret separation
version: "1.0"
phase: "06"
lesson: "06"
tags: [config, secrets, pydantic-settings, fastapi, twelve-factor]
---

# Skill: Config and Secrets Pattern

Use this template when adding typed configuration to any Python AI service.

## The Pattern

```
Environment Variables  (highest priority - runtime secrets and overrides)
        |
        v
  .env file           (local dev convenience - never commit real keys)
        |
        v
Code defaults         (lowest priority - safe non-secret values)
```

## Settings Template

```python
# settings.py
import sys
from functools import lru_cache
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # SECRETS: no defaults, must be injected via environment
    anthropic_api_key: str = Field(..., description="Anthropic API key")

    # MODEL CONFIG: non-secret, version-controllable
    model: str = Field(default="claude-3-5-haiku-20241022")
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)

    # SERVICE CONFIG
    port: int = Field(default=8000, ge=1024, le=65535)
    log_level: str = Field(default="info")
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

## Fail-Fast Startup Validation

Add this to the top of `main.py`, before the FastAPI app is constructed:

```python
from pydantic import ValidationError
from settings import get_settings

try:
    _settings = get_settings()
except ValidationError as e:
    print(f"[STARTUP ERROR] Invalid configuration:\n{e}", file=sys.stderr)
    sys.exit(1)
```

## FastAPI Integration

```python
from fastapi import Depends
from settings import Settings, get_settings

@app.post("/generate")
def generate(prompt: str, settings: Settings = Depends(get_settings)):
    # All config comes from validated Settings -- no os.environ.get() here
    ...
```

## .env.example (commit this)

```
# Copy to .env for local development. Never commit .env.
ANTHROPIC_API_KEY=your-key-here
MODEL=claude-3-5-haiku-20241022
MAX_TOKENS=1024
LOG_LEVEL=info
```

## .gitignore additions

```
.env
.env.*
!.env.example
```

## Config vs. Secrets Decision Table

| Value | Type | Where it lives |
|-------|------|----------------|
| `ANTHROPIC_API_KEY` | Secret | Runtime env var only; never in Dockerfile ENV |
| `MODEL` | Config | Dockerfile ENV default + runtime override |
| `MAX_TOKENS` | Config | Code default + runtime override |
| `DATABASE_URL` | Secret (contains password) | Runtime env var or secret store |
| `LOG_LEVEL` | Config | Code default + runtime override |
| `PORT` | Config | Dockerfile ENV default |

## When to Reach for a Secret Store

| Situation | Recommendation |
|-----------|----------------|
| Single service, one API key | Environment variable is enough |
| Keys need to rotate automatically | AWS Secrets Manager or Vault |
| Compliance requires audit trail of who accessed what secret | AWS Secrets Manager or Vault |
| Multi-service Docker Swarm | Docker secrets (mounted as files) |
| Multi-cloud or on-prem with complex access policies | HashiCorp Vault |
