# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --upgrade pip

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: Runtime image
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY main.py .

# Environment variables (override in production via secrets manager or .env)
ENV GATEWAY_API_KEY=""
ENV CODE_SERVER_TOKEN=""
ENV INCIDENTS_SERVER_TOKEN=""
ENV METRICS_SERVER_TOKEN=""
ENV PYTHONUNBUFFERED=1

# Health check: run the test suite and verify all tests pass
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python main.py --test 2>&1 | grep -q "0 failed" || exit 1

# Default: run in MCP server mode (stdio transport for Claude Desktop)
# Override with: docker run ... python main.py --test  (for CI)
# Override with: docker run ... python main.py         (for demo)
ENTRYPOINT ["python", "main.py"]
CMD ["--server"]
