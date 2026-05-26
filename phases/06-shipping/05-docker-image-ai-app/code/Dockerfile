# Production Dockerfile for a Python FastAPI AI service.
#
# Multi-stage build:
#   build stage  -- installs system deps and Python packages (includes gcc etc.)
#   runtime stage -- copies only the installed packages into a slim image
#
# Key ordering rule: COPY requirements.txt + RUN pip install BEFORE COPY . .
# This ensures the pip install layer is cached on code-only changes.

# ----- BUILD STAGE -----
FROM python:3.12-slim AS build

WORKDIR /app

# Install system dependencies needed to compile Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# LAYER ORDER MATTERS: copy requirements first so pip install is cached
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ----- RUNTIME STAGE -----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Minimal runtime system dependency: curl is needed for the HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from build stage (no gcc, no build tools in runtime image)
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Create a non-root user for the service process
RUN useradd -m -u 1000 appuser

# Copy application code (changes most frequently -- keep this layer last)
COPY main.py .

# Switch to non-root user before the process starts
USER appuser

# Non-secret configuration: these values are safe to bake into the image.
# Secrets (API keys) are NEVER set here -- inject them at runtime with --env.
ENV PORT=8000 \
    WORKERS=1 \
    LOG_LEVEL=info \
    MODEL=claude-3-5-haiku-20241022 \
    MAX_TOKENS=1024

EXPOSE 8000

# Docker will restart the container if this check fails 3 times.
# The /health endpoint returns 200 without making an API call.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Inject ANTHROPIC_API_KEY at runtime:
#   docker run --env ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY ai-app:latest
CMD uvicorn main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers ${WORKERS} \
    --log-level ${LOG_LEVEL}
