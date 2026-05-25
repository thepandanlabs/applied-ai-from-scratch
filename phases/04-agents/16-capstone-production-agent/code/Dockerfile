# Multi-stage build: production codebase assistant agent
# Stage 1: dependency install
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: runtime image
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="codebase-assistant"
LABEL org.opencontainers.image.description="Production agent: search, read, test, suggest fixes"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy agent source
COPY main.py .

# Environment variables (set at runtime via --env or .env file)
# ANTHROPIC_API_KEY   - required
# AGENT_MAX_ITER      - default 15
# AGENT_MAX_TOKENS    - default 50000
# AGENT_MAX_SECONDS   - default 180

# Non-root user for security
RUN useradd --create-home --no-log-init agentuser
USER agentuser

# Entrypoint: CLI mode
ENTRYPOINT ["python", "main.py"]
