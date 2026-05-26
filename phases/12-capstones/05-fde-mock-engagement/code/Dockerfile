FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Expose for optional FastAPI service mode
EXPOSE 8000

ENV ANTHROPIC_API_KEY=""

# Default: run demo mode. Override with docker run args.
CMD ["python", "main.py", "--demo"]
