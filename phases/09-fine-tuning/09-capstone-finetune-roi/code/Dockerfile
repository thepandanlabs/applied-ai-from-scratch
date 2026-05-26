FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy pipeline code
COPY main.py .

# Requires ANTHROPIC_API_KEY at runtime
# docker run -e ANTHROPIC_API_KEY=... finetune-roi python main.py

CMD ["python", "main.py", "--stage", "all"]
