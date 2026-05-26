# Config and Secrets Management

> A service that reads bad config at startup is a service that tells you about it immediately. A service that reads bad config at request time makes you discover it at 2 a.m.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 06 lesson 05 (Docker image), Pydantic basics
**Time:** ~45 min
**Learning Objectives:**
- Implement a typed `Settings` class using pydantic-settings that loads from environment variables with defaults
- Explain the 3-tier config resolution order and why it exists
- Distinguish config (non-secret, version-controlled) from secrets (API keys, tokens, never committed)
- Integrate the `Settings` class into a FastAPI service with fail-fast validation at startup
- Name three secret store options and describe when to reach for each

---

## The Problem

A production AI service has at least a dozen configuration values: the model name, max tokens, temperature, timeout, retry count, rate limit, service port, log level, and the API key. Where do these values live?

Most teams end up with a combination of hardcoded constants, environment variable reads scattered across six files, a config YAML that only works in staging, and an `.env` file that nobody can quite remember the correct format of. When the production service silently uses a default model because a staging environment variable was not set in production, the degradation is invisible until a user complains that responses are wrong. When a misconfigured timeout causes every request to hang for 30 seconds, nobody immediately suspects the config layer.

The deeper problem is that configuration is validated at the wrong time. In most codebases, a missing required value only errors when the code path that reads it runs. A missing `ANTHROPIC_API_KEY` might not surface until the first real user request at 2 p.m. on a Tuesday. A `MAX_TOKENS` value set to a string instead of an integer might only fail on requests that exceed the model's default limit. Fail-fast validation at startup eliminates this entire class of production surprise: the service either starts correctly configured or it refuses to start at all.

---

## The Concept

### The 3-Tier Config Resolution Order

Every well-structured service has config that flows from three sources, with each tier able to override the tier below it.

```
Tier 3 (highest priority): Environment Variables
    ANTHROPIC_API_KEY=sk-ant-...
    LOG_LEVEL=debug

          overrides
              |
              v

Tier 2 (medium priority): Config File (YAML or TOML)
    model: claude-3-5-haiku-20241022
    max_tokens: 1024
    timeout_seconds: 30

          overrides
              |
              v

Tier 1 (lowest priority): Defaults in Code
    model = "claude-3-5-haiku-20241022"
    max_tokens = 1024
    timeout_seconds = 30
    log_level = "info"
```

This order exists because:
- Defaults in code ensure the service works without any external configuration (useful for testing and local development).
- A config file lets you version-control non-secret settings per environment (staging vs. production model variants, different timeouts).
- Environment variables let orchestrators (Kubernetes, ECS, Docker) override specific values without touching files, and provide the only safe mechanism for secrets.

### Config vs. Secrets

Not all configuration is equal. The distinction determines where values are stored and who can see them.

```
CONFIG (non-secret)                    SECRETS
- Safe to commit to version control    - Never commit to version control
- Safe to bake into Docker image ENV   - Injected at runtime only
- Readable by anyone on the team       - Access-controlled; audited
                                       
Examples:                              Examples:
  model name                             ANTHROPIC_API_KEY
  max_tokens                             OPENAI_API_KEY
  log level                              DATABASE_URL (contains password)
  port                                   JWT_SECRET
  timeout                                STRIPE_SECRET_KEY
  retry count
```

### Secret Stores: When to Reach for Each

| Store | When to use it |
|-------|----------------|
| Environment variables + CI secrets | Default for most teams. Simple, supported everywhere. |
| Docker secrets | Multi-service Docker Swarm deployments. Secrets mounted as files, not env vars. |
| AWS Secrets Manager | AWS-native services that need rotation, audit trail, or dynamic credentials. |
| HashiCorp Vault | Multi-cloud or on-prem; fine-grained policies; dynamic database credentials. |

Start with environment variables. Reach for a dedicated secret store when you need rotation, audit logs, or access policies that env vars cannot provide.

---

## Build It

### Step 1: Install pydantic-settings

```bash
uv add pydantic-settings
# or: pip install pydantic-settings
```

`pydantic-settings` extends Pydantic to read field values from environment variables automatically. Each field's name maps to an uppercase environment variable of the same name.

### Step 2: The Settings Class

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Typed configuration for the AI service.

    Resolution order (highest to lowest priority):
      1. Environment variables (e.g., ANTHROPIC_API_KEY=sk-...)
      2. .env file (if env_file is set and the file exists)
      3. Default values defined below

    Validation runs at instantiation time (startup), not at request time.
    A missing required field or a wrong type raises ValidationError immediately.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- SECRETS (required, no defaults, must be injected via environment) ---
    anthropic_api_key: str = Field(..., description="Anthropic API key")

    # --- MODEL CONFIG ---
    model: str = Field(
        default="claude-3-5-haiku-20241022",
        description="Claude model ID to use for generation",
    )
    max_tokens: int = Field(
        default=1024,
        ge=1,
        le=8192,
        description="Maximum tokens in the model response",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Sampling temperature (0.0 = deterministic)",
    )

    # --- SERVICE CONFIG ---
    port: int = Field(default=8000, ge=1024, le=65535)
    log_level: str = Field(default="info")
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
```

Three things to notice:
1. `anthropic_api_key` has no default (`...` is Pydantic's "required" marker). The service refuses to start if this is missing.
2. Numeric fields have `ge` (greater-or-equal) and `le` (less-or-equal) constraints. A string like `"fast"` for `max_tokens` raises a `ValidationError` at startup, not at runtime.
3. `SettingsConfigDict(env_file=".env")` enables local development with a `.env` file without touching environment variables. In CI and production, the `.env` file does not exist and environment variables take over.

### Step 3: Load Settings Once

```python
# settings.py
from functools import lru_cache

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Load settings once and cache the result.
    Calling get_settings() multiple times returns the same object.
    Use lru_cache so the settings are only parsed once per process.
    """
    return Settings()
```

`lru_cache` ensures the environment is read and validated exactly once. Without it, every call to `get_settings()` re-reads and re-validates the environment, which wastes time and, more importantly, can cause subtle bugs if environment variables change mid-process (which they should not, but sometimes do in tests).

### Step 4: Validate at Startup

```python
# main.py
import sys
from pydantic import ValidationError
from settings import get_settings

try:
    settings = get_settings()
except ValidationError as e:
    print(f"Configuration error - service will not start:\n{e}", file=sys.stderr)
    sys.exit(1)
```

This is fail-fast. The process exits with code 1 and a clear error message before binding a port, before loading model weights, before accepting any connections. Kubernetes and Docker will log the error and report the container as failed rather than "running but broken."

> **Real-world check:** Your ops team asks: "If the settings validation catches a missing API key at startup, how does that help us compared to the service starting and then failing on the first real request?" What is the concrete operational difference, and why does it matter more during a deployment rollout?

---

## Use It

With the `Settings` class in place, FastAPI's dependency injection connects config to your route handlers cleanly:

```python
from fastapi import FastAPI, Depends
import anthropic
from settings import Settings, get_settings

app = FastAPI()


def get_client(settings: Settings = Depends(get_settings)) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


@app.post("/generate")
def generate(
    prompt: str,
    settings: Settings = Depends(get_settings),
    client: anthropic.Anthropic = Depends(get_client),
):
    msg = client.messages.create(
        model=settings.model,
        max_tokens=settings.max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return {"text": msg.content[0].text}
```

Every route handler receives the same validated `Settings` object. No scattered `os.environ.get()` calls. No type coercion in business logic. The config contract is defined once in `Settings` and enforced before the service starts.

The equivalent using raw `os.environ.get()` (what most codebases actually look like):

```python
# What NOT to do: scattered, untyped, unvalidated
model = os.environ.get("MODEL", "claude-3-5-haiku-20241022")
max_tokens = int(os.environ.get("MAX_TOKENS", "1024"))  # crashes if set to "fast"
api_key = os.environ.get("ANTHROPIC_API_KEY")  # None if missing, crashes at API call
timeout = os.environ.get("TIMEOUT_SECONDS", "30")  # string, not int; used wrong later
```

> **Perspective shift:** A teammate points out that using `Depends(get_settings)` in every route is repetitive and suggests storing `settings` as a module-level global instead. What are the tradeoffs, and in which situation would the module-level global approach actually cause a bug?

---

## Ship It

The reusable artifact for this lesson is `outputs/skill-config-secrets-pattern.md`: a `Settings` class template and the 3-tier resolution pattern you can drop into any new Python AI service.

To use it:
1. Copy `code/settings.py` into your service.
2. Add your service-specific fields following the CONFIG vs. SECRETS pattern.
3. Create a `.env.example` file (committed) with placeholder values. Create `.env` (never committed, in `.gitignore`) for local development.
4. In `main.py`, call `get_settings()` at startup inside a `try/except ValidationError` block.

---

## Evaluate It

**Check 1: Fail-fast validation.**
Start the service with a missing required field. The process should exit immediately with a non-zero exit code and a clear error message identifying the missing field. It should not start a web server or accept connections.

```bash
unset ANTHROPIC_API_KEY
python main.py
# Expected: ValidationError on ANTHROPIC_API_KEY, exit code 1
```

**Check 2: Type validation.**
Set a numeric field to an invalid value and verify startup fails with a type error, not a runtime crash later.

```bash
MAX_TOKENS=not-a-number python main.py
# Expected: ValidationError on max_tokens, exit code 1
```

**Check 3: Override precedence.**
Set a value in `.env` and override it with an environment variable. The environment variable should win.

```bash
echo "MODEL=claude-opus-4-5" > .env
MODEL=claude-3-5-haiku-20241022 python -c "from settings import get_settings; s = get_settings(); print(s.model)"
# Expected: claude-3-5-haiku-20241022  (env var wins over .env file)
```

**Check 4: No secrets in version control.**
Verify `.env` is in `.gitignore` and a `.env.example` with placeholder values is committed instead.

```bash
git status .env
# Expected: .env should not appear (it is gitignored)
cat .env.example
# Expected: ANTHROPIC_API_KEY=your-key-here (placeholder, not a real key)
```
