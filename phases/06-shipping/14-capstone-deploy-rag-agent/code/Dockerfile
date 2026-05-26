FROM python:3.12-slim

# Create a non-root user for security
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install dependencies before copying application code
# This layer is cached as long as requirements.txt does not change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Copy the version manifest - required for service startup
# If manifests.yaml does not exist, run: python main.py register
COPY manifests.yaml .

# Switch to non-root user
USER appuser

# Expose the service port
EXPOSE 8000

# Health check - verifies the service responds before marking it healthy
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Start the service with production settings:
# - workers=1 keeps the in-memory store consistent (use Redis for multi-worker)
# - log-level=info matches the app's logging config
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
