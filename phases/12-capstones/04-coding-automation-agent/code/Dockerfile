FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Mount the repo as a read-only volume at /repo
# The agent writes to /data/agent_audit.jsonl
ENV AGENT_CWD=/repo
ENV AUDIT_LOG=/data/agent_audit.jsonl

# For interactive use: docker run -it -v /path/to/repo:/repo:ro -v $(pwd)/data:/data coding-agent python main.py
# For demo mode:       docker run    -v /path/to/repo:/repo:ro coding-agent python main.py --demo
CMD ["python", "main.py", "--demo"]
