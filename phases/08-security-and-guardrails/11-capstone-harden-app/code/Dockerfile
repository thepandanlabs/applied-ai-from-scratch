# Production Dockerfile for a security-hardened Python FastAPI AI service.
#
# Multi-stage build:
#   build stage  -- installs system deps and Python packages
#   runtime stage -- copies only installed packages into a slim image
#
# NEVER bake secrets into the image. Inject ANTHROPIC_API_KEY at runtime.

# ----- BUILD STAGE -----
FROM python:3.12-slim AS build

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Layer order: requirements first so pip install is cached on code-only changes
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ----- RUNTIME STAGE -----
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from build stage (no gcc in runtime image)
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Non-root user for the service process
RUN useradd -m -u 1000 appuser

# Application code (changes most frequently -- keep this layer last)
COPY main.py .

USER appuser

# Non-secret configuration only. Secrets are injected at runtime with --env.
ENV PORT=8000 \
    WORKERS=1 \
    LOG_LEVEL=info \
    MODEL=claude-3-5-haiku-20241022 \
    MAX_TOKENS=1024 \
    INPUT_TOKEN_LIMIT=4000 \
    RATE_LIMIT_RPM=20 \
    SESSION_COST_CAP=2.00

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Inject ANTHROPIC_API_KEY at runtime:
#   docker run --env ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY hardened-ai:latest
CMD uvicorn main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers ${WORKERS} \
    --log-level ${LOG_LEVEL}
