FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Audit log persists to /data volume
ENV AUDIT_LOG_FILE=/data/audit_log.jsonl
ENV HITL_THRESHOLD=50

# For interactive mode, run: docker run -it support-agent python main.py
# For test mode:             docker run support-agent python main.py --test
CMD ["python", "main.py"]
