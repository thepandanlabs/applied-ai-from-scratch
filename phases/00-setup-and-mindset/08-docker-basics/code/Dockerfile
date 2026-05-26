FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements first so Docker caches the pip install layer.
# If only main.py changes, this layer is reused from cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY main.py .

# Never set ANTHROPIC_API_KEY here.
# Pass it at runtime: docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
CMD ["python", "main.py"]
