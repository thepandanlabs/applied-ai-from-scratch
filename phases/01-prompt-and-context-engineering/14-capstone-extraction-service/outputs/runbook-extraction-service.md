---
name: runbook-extraction-service
description: Production runbook for the Phase 01 structured extraction service - startup, configuration, testing, and debugging.
version: "1.0"
phase: "01"
lesson: "14"
tags: [capstone, fastapi, extraction, runbook, production]
---

# Extraction Service Runbook

## Service Overview

The extraction service accepts a document and a schema name, calls Claude with a cached system prompt and tool-use forced output, validates the result with Pydantic, and returns structured JSON.

Endpoint: `POST /extract`
Model: claude-3-5-haiku-20241022 (configurable via env)
Schemas: contact, invoice, meeting_notes

---

## Startup

### Local Development

```bash
# 1. Clone and enter the directory
cd phases/01-prompt-and-context-engineering/14-capstone-extraction-service/code

# 2. Install dependencies
pip install -r requirements.txt
# Or with uv:
uv pip install -r requirements.txt

# 3. Set required environment variable
export ANTHROPIC_API_KEY=sk-ant-...

# 4. Start the service
uvicorn main:app --reload --port 8000

# 5. Verify it is running
curl http://localhost:8000/health
```

Expected health response:
```json
{
  "status": "ok",
  "model": "claude-3-5-haiku-20241022",
  "max_input_tokens": 16000,
  "schemas": ["contact", "invoice", "meeting_notes"]
}
```

### Docker

```bash
# Build the image
docker build -t extraction-service:latest ./code

# Run with environment variable
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  extraction-service:latest

# With Docker Compose (create a compose.yml):
# services:
#   extraction:
#     image: extraction-service:latest
#     ports: ["8000:8000"]
#     environment:
#       ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
```

---

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | Anthropic API key. Never commit this value. |
| `MODEL` | `claude-3-5-haiku-20241022` | Claude model to use for extraction. |
| `MAX_INPUT_TOKENS` | `16000` | Maximum estimated input tokens. Documents above this are rejected with a 200 response (status: context_too_large). |

Note: Token estimation uses `len(document) // 4`. For precise token counting, use the Anthropic tokenizer. The rough estimate intentionally errs toward acceptance to avoid rejecting valid documents.

---

## Testing

### Smoke Tests (run after every deploy)

```bash
BASE="http://localhost:8000"

# 1. Health check
curl -sf $BASE/health > /dev/null && echo "PASS: health" || echo "FAIL: health"

# 2. Schema listing
curl -sf $BASE/schemas | python3 -c "
import sys, json
schemas = json.load(sys.stdin)
assert 'contact' in schemas and 'invoice' in schemas and 'meeting_notes' in schemas
print('PASS: schemas')
" || echo "FAIL: schemas"

# 3. Contact extraction
curl -sf -X POST $BASE/extract \
  -H "Content-Type: application/json" \
  -d '{"document": "Jane Doe, jane@example.com, 555-1234, Acme Corp, CTO", "schema_name": "contact"}' | \
  python3 -c "
import sys, json
r = json.load(sys.stdin)
assert r['status'] == 'success', f'Expected success, got: {r}'
assert r['data']['name'] == 'Jane Doe', f'Wrong name: {r[\"data\"]}'
print('PASS: contact extraction')
"

# 4. Unknown schema returns error (not 500)
curl -sf -X POST $BASE/extract \
  -H "Content-Type: application/json" \
  -d '{"document": "test", "schema_name": "nonexistent"}' | \
  python3 -c "
import sys, json
r = json.load(sys.stdin)
assert r['status'] == 'unknown_schema', f'Expected unknown_schema, got: {r}'
print('PASS: unknown schema error')
"

# 5. Empty document returns 400
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/extract \
  -H "Content-Type: application/json" \
  -d '{"document": "", "schema_name": "contact"}')
[ "$CODE" = "400" ] && echo "PASS: empty document rejected" || echo "FAIL: empty document returned $CODE"
```

### Cache Verification

Run the same extraction request twice in quick succession. The second response should have `cache_status: "hit"`.

```bash
PAYLOAD='{"document": "Contact: Alice Smith, alice@corp.com, Director of Engineering, TechCorp", "schema_name": "contact"}'

echo "First call (expect cache_status: write):"
curl -sf -X POST $BASE/extract \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" | python3 -c "import sys,json; r=json.load(sys.stdin); print(f\"  cache_status={r.get('cache_status')} tokens={r.get('tokens_used')}\")"

echo "Second call (expect cache_status: hit):"
curl -sf -X POST $BASE/extract \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" | python3 -c "import sys,json; r=json.load(sys.stdin); print(f\"  cache_status={r.get('cache_status')} tokens={r.get('tokens_used')}\")"
```

---

## Debugging

### Failure: `status: api_error`

The Anthropic API returned an error. Check:
1. Is `ANTHROPIC_API_KEY` set and valid? Verify: `curl -H "x-api-key: $ANTHROPIC_API_KEY" https://api.anthropic.com/v1/models`
2. Are you hitting rate limits? Check response headers for `x-ratelimit-*` fields.
3. Is the model name valid? Check the `MODEL` env variable against current Anthropic model IDs.

### Failure: `status: context_too_large`

The document exceeds `MAX_INPUT_TOKENS`. Options:
1. Increase `MAX_INPUT_TOKENS` (check your Anthropic tier's context limit first).
2. Pre-process the document: split it into chunks and call the service once per chunk.
3. Pre-filter the document to the relevant sections before sending.

### Failure: `status: refusal`

The model returned text instead of calling the extraction tool. The response includes a `refusal_category` field. Common causes:

| Category | Meaning | Fix |
|---|---|---|
| safety | Model triggered on document content | Review the document. If legitimate, check if the content can be presented differently. |
| capability | Model claiming inability | Should not occur with tool_choice: any. Check if the model ID is correct. |
| ambiguity | Model asked for clarification | Should not occur with tool_choice: any. Check if the system prompt was truncated. |

If `refusal` occurs frequently (>1% of requests), inspect the raw response text in the error field and check whether the system prompt is being sent correctly. Log the full response body in staging.

### Failure: `status: validation_error`

The model called the tool but the output failed Pydantic validation, and the retry also failed. The `data` field contains the raw unvalidated tool call input.

Steps:
1. Inspect `data` to see what the model produced.
2. Check whether the schema definition matches the model's JSON Schema output (use `/schemas` endpoint).
3. Common causes: type mismatch (float vs string for amounts), null handling differences.
4. If this occurs on specific document types, add those to a labeled test dataset and fix the system prompt to handle that pattern explicitly.

### Cache Not Working (`cache_status: miss` or `write` on every call)

1. Check that the model supports caching (Haiku requires 2048+ token prefixes; see Lesson 13).
2. Verify the system prompt has not been modified between calls. Any change invalidates the cache.
3. Check request interval: if calls are more than 5 minutes apart, the cache expires and every call is a write.
4. Use the Anthropic API usage response to confirm: `cache_read_input_tokens` should be non-zero on cache hits.

---

## Adding a New Schema

1. Define a new Pydantic model in `main.py`:

```python
class MyNewSchema(BaseModel):
    field_one: str
    field_two: Optional[int] = None
```

2. Register it in `SCHEMAS`:

```python
SCHEMAS["my_new_schema"] = MyNewSchema
```

3. Restart the service. The new schema is immediately available at `/extract`.

4. Add a smoke test for the new schema to your test suite before deploying to production.

---

## Cost Estimates

Approximate monthly cost using claude-3-5-haiku-20241022 with caching enabled.
Verify current pricing at https://www.anthropic.com/pricing before budgeting.

| Volume | System tokens (cached) | Est. monthly cost |
|---|---|---|
| 1,000 req/day | ~400 tokens (cached, 90% hit rate) | ~$2-5 |
| 10,000 req/day | ~400 tokens (cached, 90% hit rate) | ~$20-50 |
| 100,000 req/day | ~400 tokens (cached, 90% hit rate) | ~$200-500 |

Output tokens (200-400 per extraction) are not cached and are charged at standard output rates.

The system prompt cache reduces input token costs by ~85-90% at typical request volumes.
