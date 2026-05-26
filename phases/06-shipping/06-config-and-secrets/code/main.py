"""
Config and Secrets Management for a FastAPI AI Service.

Demonstrates the 3-tier config resolution pattern using pydantic-settings:
  1. Defaults in code (lowest priority)
  2. .env file (if present)
  3. Environment variables (highest priority)

Secrets (ANTHROPIC_API_KEY) are required with no defaults.
Non-secret config has typed defaults and validation constraints.

Usage:
    # Fail-fast demo (missing required secret):
    python main.py

    # Normal startup:
    ANTHROPIC_API_KEY=sk-... uvicorn main:app --reload

    # Override a default:
    ANTHROPIC_API_KEY=sk-... MAX_TOKENS=512 uvicorn main:app --reload
"""

import sys

import anthropic
from fastapi import Depends, FastAPI, HTTPException
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache


# ---------------------------------------------------------------------------
# Settings definition
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """
    Typed configuration for the AI service.

    Resolution order (highest wins):
      1. Environment variables
      2. .env file (only if it exists; missing .env is not an error)
      3. Default values below

    Validation runs at instantiation (startup). A misconfigured service fails
    immediately with a clear error rather than silently using wrong values.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # SECRETS: no defaults; must be provided via environment or .env file
    anthropic_api_key: str = Field(..., description="Anthropic API key (required)")

    # MODEL CONFIG: non-secret, safe to commit or bake into Docker ENV
    model: str = Field(
        default="claude-3-5-haiku-20241022",
        description="Claude model ID",
    )
    max_tokens: int = Field(
        default=1024,
        ge=1,
        le=8192,
        description="Max tokens in model response",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Sampling temperature",
    )

    # SERVICE CONFIG
    port: int = Field(default=8000, ge=1024, le=65535)
    log_level: str = Field(default="info")
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Load and validate settings once, cache the result.

    The lru_cache ensures environment variables are read and validated
    exactly once per process. Subsequent calls return the cached object.
    """
    return Settings()


# ---------------------------------------------------------------------------
# Fail-fast startup validation
# ---------------------------------------------------------------------------

# Validate config before binding a port or accepting connections.
# The service exits immediately with a clear error if required values are missing
# or if any value fails its type/range constraints.
try:
    _startup_settings = get_settings()
    print(f"Config loaded: model={_startup_settings.model}, "
          f"max_tokens={_startup_settings.max_tokens}, "
          f"port={_startup_settings.port}")
except ValidationError as e:
    print(f"[STARTUP ERROR] Configuration is invalid. Service will not start.\n{e}",
          file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="AI Service", version="1.0")


def get_client(settings: Settings = Depends(get_settings)) -> anthropic.Anthropic:
    """Dependency that creates the Anthropic client from validated settings."""
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


@app.get("/health")
def health(settings: Settings = Depends(get_settings)):
    """Health check: returns 200 with current config summary (no secrets)."""
    return {
        "status": "ok",
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "log_level": settings.log_level,
    }


@app.get("/config")
def config(settings: Settings = Depends(get_settings)):
    """
    Returns non-secret config for debugging.
    Never expose secrets here -- only safe-to-log values.
    """
    return {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "temperature": settings.temperature,
        "timeout_seconds": settings.timeout_seconds,
        "max_retries": settings.max_retries,
        "log_level": settings.log_level,
        # anthropic_api_key is intentionally omitted
    }


@app.post("/generate")
def generate(
    prompt: str,
    settings: Settings = Depends(get_settings),
    client: anthropic.Anthropic = Depends(get_client),
):
    """
    Generate a response using settings loaded from the environment.

    All config values come from the validated Settings object.
    No os.environ.get() calls in business logic.
    """
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be empty")

    msg = client.messages.create(
        model=settings.model,
        max_tokens=settings.max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return {
        "text": msg.content[0].text,
        "model": msg.model,
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
    }


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=_startup_settings.port, reload=True)
