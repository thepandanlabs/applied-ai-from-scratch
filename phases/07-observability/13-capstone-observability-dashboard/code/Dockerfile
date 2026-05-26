FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Create directories for runtime data
RUN mkdir -p /app/data /app/logs

# Environment defaults (override at runtime)
ENV SERVICE_NAME=rag-service
ENV DB_PATH=/app/data/cost_log.db
ENV LOG_PATH=/app/logs/app.jsonl
ENV ANTHROPIC_API_KEY=""
ENV LANGFUSE_PUBLIC_KEY=""
ENV LANGFUSE_SECRET_KEY=""
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
