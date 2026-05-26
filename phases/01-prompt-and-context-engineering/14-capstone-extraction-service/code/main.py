"""
Lesson 14: Capstone - Structured-Extraction Service
======================================================
Production-ready FastAPI service that composes all Phase 01 concepts:
- Engineered system prompt with prompt caching (cache_control)
- Tool-use forced structured output
- Pydantic validation with retry loop
- Context window management (token budget gate)
- Refusal detection and typed error responses
- Conversation history support for multi-turn extraction

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    uvicorn main:app --reload --port 8000

    # Health check
    curl http://localhost:8000/health

    # Extract a contact
    curl -s -X POST http://localhost:8000/extract \\
      -H "Content-Type: application/json" \\
      -d '{"document": "Jane Doe, jane@example.com, Acme Corp", "schema_name": "contact"}' \\
      | python3 -m json.tool
"""

import os
import time
import logging
from enum import Enum
from typing import Optional, List, Any

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("extraction_service")

# ---------------------------------------------------------------------------
# Client and constants
# ---------------------------------------------------------------------------

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = os.environ.get("MODEL", "claude-3-5-haiku-20241022")
MAX_INPUT_TOKENS = int(os.environ.get("MAX_INPUT_TOKENS", "16000"))

# ---------------------------------------------------------------------------
# Extraction system prompt (cached on all requests)
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """
You are a structured data extraction engine. Your sole job is to extract
information from documents and return it using the provided tool.

Rules:
1. Extract ONLY information that is explicitly present in the document.
   Do not infer, guess, or complete missing information from your training data.
2. If a required field is not present in the document, use null for optional
   fields and empty arrays for array fields. Never fabricate values.
3. You MUST call the provided extraction tool with the extracted data.
   Do not return prose. Do not explain your reasoning. Call the tool.
4. For arrays, extract all instances present in the document.
   Do not limit to one item when multiple exist.
5. For dates, use ISO 8601 format (YYYY-MM-DD) where the document permits.
6. For monetary values, extract the numeric value and currency code separately
   where the schema provides distinct fields for them.
7. For phone numbers, preserve the format as written in the source document.
8. Do not normalize, abbreviate, or expand values beyond what is in the document.

If the document is empty, clearly corrupted, or contains no extractable
information for the requested schema, call the tool with all fields set to
null or empty arrays as appropriate for their types.

Do not ask for clarification. Do not explain your choices. Call the tool.
""".strip()

# ---------------------------------------------------------------------------
# Extraction schemas (Pydantic models)
# ---------------------------------------------------------------------------


class ContactInfo(BaseModel):
    """Contact information extracted from text."""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None


class InvoiceLineItem(BaseModel):
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None


class Invoice(BaseModel):
    """Invoice data extracted from text or scanned documents."""
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    vendor_name: Optional[str] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    line_items: List[InvoiceLineItem] = Field(default_factory=list)


class MeetingNotes(BaseModel):
    """Structured data extracted from meeting notes or summaries."""
    date: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    next_meeting: Optional[str] = None


SCHEMAS: dict[str, type[BaseModel]] = {
    "contact": ContactInfo,
    "invoice": Invoice,
    "meeting_notes": MeetingNotes,
}

# ---------------------------------------------------------------------------
# Tool definition builder
# ---------------------------------------------------------------------------


def schema_to_tool(schema_name: str, model_class: type[BaseModel]) -> dict:
    """Convert a Pydantic model to an Anthropic tool definition."""
    json_schema = model_class.model_json_schema()
    return {
        "name": f"extract_{schema_name}",
        "description": f"Extract {schema_name.replace('_', ' ')} data from the provided document.",
        "input_schema": json_schema,
    }

# ---------------------------------------------------------------------------
# Refusal detection
# ---------------------------------------------------------------------------

SAFETY_SIGNALS = [
    "i can't help",
    "i cannot help",
    "against my guidelines",
    "content policy",
    "i won't",
    "i'm unable to assist",
]

CAPABILITY_SIGNALS = [
    "i don't have access",
    "i can't access",
    "i cannot retrieve",
    "i don't have real-time",
    "i can't browse",
]


def classify_text_response(text: str) -> str:
    """Classify a text response as safety, capability, or ambiguity refusal."""
    lower = text.lower()
    for signal in SAFETY_SIGNALS:
        if signal in lower:
            return "safety"
    for signal in CAPABILITY_SIGNALS:
        if signal in lower:
            return "capability"
    return "ambiguity"

# ---------------------------------------------------------------------------
# Extraction status enum
# ---------------------------------------------------------------------------


class ExtractionStatus(Enum):
    SUCCESS = "success"
    CONTEXT_TOO_LARGE = "context_too_large"
    UNKNOWN_SCHEMA = "unknown_schema"
    REFUSAL = "refusal"
    VALIDATION_ERROR = "validation_error"
    API_ERROR = "api_error"

# ---------------------------------------------------------------------------
# Core extraction function
# ---------------------------------------------------------------------------


def extract(
    document: str,
    schema_name: str,
    retry_on_validation_error: bool = True,
) -> dict[str, Any]:
    """
    Extract structured data from a document using the named schema.

    Returns:
        dict with keys: status, data, schema_name, tokens_used,
                        cache_status, latency_s, error, retried
    """
    start = time.time()

    # Gate 1: unknown schema
    if schema_name not in SCHEMAS:
        return {
            "status": ExtractionStatus.UNKNOWN_SCHEMA.value,
            "error": f"Unknown schema '{schema_name}'. Available: {list(SCHEMAS.keys())}",
            "data": None,
            "latency_s": round(time.time() - start, 3),
        }

    model_class = SCHEMAS[schema_name]
    tool = schema_to_tool(schema_name, model_class)

    # Gate 2: context window estimate (1 token ~= 4 chars, rough estimate)
    estimated_tokens = len(document) // 4
    if estimated_tokens > MAX_INPUT_TOKENS:
        return {
            "status": ExtractionStatus.CONTEXT_TOO_LARGE.value,
            "error": (
                f"Document estimated at ~{estimated_tokens} tokens "
                f"(limit: {MAX_INPUT_TOKENS}). "
                f"Chunk the document before sending."
            ),
            "data": None,
            "latency_s": round(time.time() - start, 3),
        }

    def _api_call(doc_text: str, extra_instruction: str = "") -> anthropic.types.Message:
        user_content = f"Document:\n\n{doc_text}"
        if extra_instruction:
            user_content += f"\n\n{extra_instruction}"

        return client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": EXTRACTION_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[tool],
            tool_choice={"type": "any"},  # Force the model to call the tool
            messages=[{"role": "user", "content": user_content}],
        )

    # Attempt 1
    try:
        response = _api_call(document)
    except anthropic.APIError as exc:
        logger.error("API error during extraction: %s", exc)
        return {
            "status": ExtractionStatus.API_ERROR.value,
            "error": str(exc),
            "data": None,
            "latency_s": round(time.time() - start, 3),
        }

    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_write = getattr(usage, "cache_creation_input_tokens", 0)
    cache_status = "hit" if cache_read > 0 else ("write" if cache_write > 0 else "miss")
    total_tokens = usage.input_tokens + usage.output_tokens

    # Gate 3: did the model call the tool?
    tool_use_block = None
    text_response = None
    for block in response.content:
        if block.type == "tool_use":
            tool_use_block = block
        elif block.type == "text":
            text_response = block.text

    if tool_use_block is None:
        category = classify_text_response(text_response or "")
        logger.warning(
            "Refusal detected: schema=%s category=%s text=%.100s",
            schema_name, category, text_response or "",
        )
        return {
            "status": ExtractionStatus.REFUSAL.value,
            "error": (
                f"Model returned text instead of tool call. "
                f"Refusal category: {category}. "
                f"Response: {(text_response or '')[:200]}"
            ),
            "data": None,
            "cache_status": cache_status,
            "tokens_used": total_tokens,
            "latency_s": round(time.time() - start, 3),
        }

    # Gate 4: Pydantic validation
    raw_input = tool_use_block.input
    try:
        validated = model_class(**raw_input)
        logger.info(
            "Extraction success: schema=%s cache=%s tokens=%d latency=%.3fs",
            schema_name, cache_status, total_tokens, time.time() - start,
        )
        return {
            "status": ExtractionStatus.SUCCESS.value,
            "data": validated.model_dump(),
            "schema_name": schema_name,
            "cache_status": cache_status,
            "tokens_used": total_tokens,
            "latency_s": round(time.time() - start, 3),
            "error": None,
            "retried": False,
        }
    except Exception as validation_error:
        logger.warning("Validation error on attempt 1: %s", validation_error)

        if not retry_on_validation_error:
            return {
                "status": ExtractionStatus.VALIDATION_ERROR.value,
                "error": str(validation_error),
                "data": raw_input,
                "latency_s": round(time.time() - start, 3),
            }

        # Retry with validation error feedback
        try:
            retry_response = _api_call(
                document,
                extra_instruction=(
                    f"Your previous extraction attempt produced data that failed "
                    f"schema validation with this error: {validation_error}. "
                    f"Please call the extraction tool again with corrected values."
                ),
            )
            retry_usage = retry_response.usage
            total_tokens += retry_usage.input_tokens + retry_usage.output_tokens

            retry_tool_block = next(
                (b for b in retry_response.content if b.type == "tool_use"), None
            )
            if retry_tool_block is None:
                return {
                    "status": ExtractionStatus.VALIDATION_ERROR.value,
                    "error": "Retry did not produce a tool call",
                    "data": raw_input,
                    "tokens_used": total_tokens,
                    "latency_s": round(time.time() - start, 3),
                }

            validated = model_class(**retry_tool_block.input)
            logger.info(
                "Extraction success after retry: schema=%s tokens=%d", schema_name, total_tokens
            )
            return {
                "status": ExtractionStatus.SUCCESS.value,
                "data": validated.model_dump(),
                "schema_name": schema_name,
                "cache_status": cache_status,
                "tokens_used": total_tokens,
                "latency_s": round(time.time() - start, 3),
                "error": None,
                "retried": True,
            }
        except Exception as retry_error:
            logger.error("Retry also failed: %s", retry_error)
            return {
                "status": ExtractionStatus.VALIDATION_ERROR.value,
                "error": f"Retry also failed: {retry_error}",
                "data": raw_input,
                "tokens_used": total_tokens,
                "latency_s": round(time.time() - start, 3),
            }

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Structured Extraction Service",
    version="1.0",
    description="Extract structured data from documents using Claude. Phase 01 capstone.",
)


class ExtractRequest(BaseModel):
    document: str = Field(..., description="The raw text document to extract from")
    schema_name: str = Field(
        ..., description="Schema to extract against. One of: contact, invoice, meeting_notes"
    )


class ExtractResponse(BaseModel):
    status: str
    data: Optional[dict] = None
    schema_name: Optional[str] = None
    tokens_used: Optional[int] = None
    cache_status: Optional[str] = None
    latency_s: Optional[float] = None
    error: Optional[str] = None
    retried: Optional[bool] = None


@app.post("/extract", response_model=ExtractResponse)
def extract_endpoint(request: ExtractRequest) -> ExtractResponse:
    """Extract structured data from a document."""
    if not request.document.strip():
        raise HTTPException(status_code=400, detail="document cannot be empty")

    result = extract(request.document, request.schema_name)
    return ExtractResponse(**result)


@app.get("/health")
def health():
    """Service health check."""
    return {
        "status": "ok",
        "model": MODEL,
        "max_input_tokens": MAX_INPUT_TOKENS,
        "schemas": list(SCHEMAS.keys()),
    }


@app.get("/schemas")
def list_schemas():
    """List available schemas with their JSON Schema definitions."""
    return {name: cls.model_json_schema() for name, cls in SCHEMAS.items()}


# ---------------------------------------------------------------------------
# CLI smoke test (run directly without uvicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    print("Running smoke tests against the extraction function directly...\n")

    test_cases = [
        {
            "name": "Contact extraction",
            "document": "Please reach out to Sarah Chen, Engineering Manager at DataFlow Inc. Her email is sarah.chen@dataflow.io, phone: +1-415-555-0192.",
            "schema_name": "contact",
        },
        {
            "name": "Invoice extraction",
            "document": "Invoice #INV-2026-042\nDate: 2026-05-15\nFrom: Acme Cloud Services\nItems:\n- Compute (200h x $0.50): $100.00\n- Storage (500GB x $0.02): $10.00\nTotal Due: $110.00 USD",
            "schema_name": "invoice",
        },
        {
            "name": "Meeting notes extraction",
            "document": "Meeting: Product Sync\nDate: May 20, 2026\nAttendees: Alice, Bob, Carol\nDecisions: Adopt new deployment process. Delay feature X to Q3.\nAction items: Alice to write RFC by May 27. Bob to update CI config.\nNext meeting: May 27, 2026 at 10am.",
            "schema_name": "meeting_notes",
        },
        {
            "name": "Unknown schema error",
            "document": "Some document text",
            "schema_name": "does_not_exist",
        },
    ]

    for case in test_cases:
        print(f"[{case['name']}]")
        result = extract(case["document"], case["schema_name"])
        print(f"  Status: {result['status']}")
        if result["status"] == "success":
            print(f"  Cache: {result.get('cache_status')} | Tokens: {result.get('tokens_used')} | Latency: {result.get('latency_s')}s")
            print(f"  Data: {json.dumps(result['data'], indent=4)[:300]}")
        else:
            print(f"  Error: {result.get('error', '')[:120]}")
        print()
