# Multi-stage Dockerfile for the RAG Service
# Stage 1 (builder): install all dependencies including dev tools
# Stage 2 (runtime): copy only what's needed, run as non-root user
#
# Build:  docker build -t rag-service .
# Run:    docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... rag-service
#
# For local embeddings (no API key needed):
#   docker run -p 8000:8000 -e USE_LOCAL_EMBEDDINGS=true rag-service

# ---------------------------------------------------------------------------
# Stage 1: Builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies into a virtual environment
RUN python -m venv /venv && \
    /venv/bin/pip install --upgrade pip --quiet && \
    /venv/bin/pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /venv /venv

# Copy application code
COPY main.py .

# Set PATH to use venv
ENV PATH="/venv/bin:$PATH"

# Application config (can be overridden at runtime via -e flags)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO \
    PORT=8000 \
    TOP_K=5 \
    CHUNK_SIZE=400 \
    CHUNK_OVERLAP=50 \
    MAX_RETRIES=3 \
    USE_LOCAL_EMBEDDINGS=false \
    EMBED_MODEL=text-embedding-3-small \
    CHAT_MODEL=gpt-4o-mini \
    LOCAL_EMBED_MODEL=all-MiniLM-L6-v2

# Use non-root user
USER appuser

EXPOSE 8000

# Health check: the service exposes /health for readiness probes
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start the FastAPI server
# Use --workers 1 for development; increase for production
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "warning"]
