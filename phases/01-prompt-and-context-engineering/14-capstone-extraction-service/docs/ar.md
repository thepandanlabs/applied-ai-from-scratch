# مشروع التتويج: خدمة الاستخراج المهيكل ومكتبة الـ Prompt

> المرحلة 01 في خدمة واحدة: كل مفهوم من prompt مهندس إلى نظام مُخزّن مؤقتًا، ومخرج مُتحقَّق منه (validated)، ومعالجة لطيفة لحالات الرفض.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** كل دروس المرحلة 01 (01-13)
**الوقت:** ~90 دقيقة
**أهداف التعلّم:**
- بناء خدمة FastAPI جاهزة للإنتاج تستقبل وثيقة ومخططًا (schema) وتُرجع JSON مهيكلًا
- تجميع مفاهيم المرحلة 01 في خط معالجة (pipeline) واحد متماسك: هندسة الـ system prompt، والمخرج المهيكل عبر استخدام الأدوات (tool-use)، والتحقّق بـ Pydantic مع إعادة المحاولة، والتخزين المؤقت للـ prompt، وإدارة نافذة السياق، وسجلّ المحادثة، ومعالجة الرفض
- تشغيل الخدمة واختبارها محليًّا باستخدام uvicorn و curl
- تنسيق مكتبة prompt قابلة لإعادة الاستخدام من أفضل أنماط المرحلة 01
- قراءة وتطبيق دليل تشغيل (runbook) إنتاجي لبدء الخدمة وتهيئتها وتتبّع أخطائها

---

## المشكلة

قضيتَ المرحلة 01 في تعلّم تقنيات فردية: كيف تهندس system prompt، وكيف تطلب مخرجًا مهيكلًا عبر استخدام الأدوات، وكيف تتحقّق وتعيد المحاولة، وكيف تخزّن مؤقتًا، وكيف تدير السياق. أوضح كل درس قطعة واحدة بمعزل.

الإنتاج لا يمنحك أبدًا قطعًا معزولة. خدمة استخراج حقيقية تحتاجها كلها دفعة واحدة: system prompt مهندس (مُخزّن مؤقتًا، لأنه مكلف) يُرسَل إلى نموذج يُرجع مخرجًا مهيكلًا (مُتحقَّقًا منه بـ Pydantic، مع إعادة المحاولة مرّة عند الفشل)، مع إدارة سياق ترفض بلطف الوثائق الكبيرة جدًّا، واكتشاف رفض يُرجع خطأً مفيدًا بدلًا من الانهيار في المراحل اللاحقة.

يبني مشروع التتويج هذا تلك الخدمة. إنه ليس عرضًا توضيحيًّا: إنه قابل للنشر (deployable). ستشغّله بـ `uvicorn`، وتطلبه بـ `curl`، وتقرأ دليل تشغيل يغطّي بدء التشغيل والتهيئة وما تفعله حين يتعطّل في الساعة الثانية صباحًا.

---

## المفهوم

### خط المعالجة الكامل

كل طلب `/extract` يمرّ عبر كل مكوّنات المرحلة 01 بالترتيب:

```
                    POST /extract
                    {document, schema_name}
                           |
             ┌─────────────▼─────────────┐
             │  1. CONTEXT CHECK         │
             │  Count tokens             │
             │  Reject if > max_tokens   │
             └─────────────┬─────────────┘
                           │
             ┌─────────────▼─────────────┐
             │  2. SYSTEM PROMPT         │
             │  Load from prompt library │
             │  cache_control: ephemeral │
             └─────────────┬─────────────┘
                           |
             ┌─────────────▼─────────────┐
             │  3. TOOL-USE CALL         │
             │  tools=[schema_as_tool]   │
             │  Model must call the tool │
             └─────────────┬─────────────┘
                           |
             ┌─────────────▼─────────────┐
             │  4. REFUSAL CHECK         │
             │  Classify response type   │
             │  Return typed error if    │
             │  model did not use tool   │
             └─────────────┬─────────────┘
                           |
             ┌─────────────▼─────────────┐
             │  5. PYDANTIC VALIDATION   │
             │  Parse tool call output   │
             │  Retry once on failure    │
             └─────────────┬─────────────┘
                           |
             ┌─────────────▼─────────────┐
             │  6. RETURN RESULT         │
             │  {data, schema, tokens,   │
             │   cache_status, latency}  │
             └───────────────────────────┘
```

### معمارية مكتبة الـ Prompt

مكتبة الـ prompt مجموعة منسّقة من الـ system prompts القابلة لإعادة الاستخدام، كلٌّ منها يخضع للإصدارات ومُوسَّم (tagged). تُحمّل الخدمة الـ prompts بالاسم عند بدء التشغيل. يتيح لك هذا تحديث الـ prompts من دون إعادة نشر الكود.

```
outputs/
  runbook-extraction-service.md    <- operational runbook
prompts/                           <- prompt library (in code dir)
  extraction-system.txt            <- system prompt for extraction
  extraction-schema-*.json         <- per-schema tool definitions
```

---

## البناء

### الخطوة 1: تخطيط المشروع والاعتماديات

```
code/
├── main.py             # FastAPI service
├── requirements.txt    # pinned dependencies
└── Dockerfile          # production container
```

```bash
# Install
pip install fastapi uvicorn anthropic pydantic
# Or with uv (recommended):
uv add fastapi uvicorn anthropic pydantic
```

### الخطوة 2: الـ System Prompt (مهندس ومُخزّن مؤقتًا)

الـ system prompt للاستخراج هو الأساس المستقرّ لكل طلب. وهو طويل بما يكفي للتخزين المؤقت ولا يتغيّر بين الطلبات، ما يجعله هدف تخزين مؤقت مثاليًّا.

```python
EXTRACTION_SYSTEM_PROMPT = """
You are a structured data extraction engine. Your sole job is to extract
information from documents and return it using the provided tool.

Rules:
1. Extract ONLY information that is explicitly present in the document.
   Do not infer, guess, or complete missing information.
2. If a required field is not present in the document, use null for optional
   fields. Never fabricate values.
3. You MUST call the provided extraction tool with the extracted data.
   Do not return prose. Do not explain. Call the tool.
4. For arrays, extract all instances present. Do not limit to one item.
5. For dates, use ISO 8601 format (YYYY-MM-DD) where possible.
6. For monetary values, extract the numeric value and the currency code
   as separate fields where the schema provides them.

If the document is empty, corrupted, or contains no extractable information
for the requested schema, call the tool with all fields set to null or
empty arrays as appropriate.

Do not ask for clarification. Do not explain your choices. Call the tool.
"""
```

هذا الـ prompt يتجاوز 200 كلمة. مُجتمعًا مع تعريفات الأدوات (tool definitions)، يتخطّى عتبة الـ 2048 token للتخزين المؤقت في Haiku.

### الخطوة 3: المخططات كتعريفات أدوات (Schemas as Tool Definitions)

تُعرَّف المخططات كتعريفات أدوات Anthropic. يُجبَر النموذج على استدعاء الأداة، ما يضمن مخرجًا مهيكلًا من دون أن يُطلب من النموذج إنتاج JSON كنصّ نثري.

```python
from pydantic import BaseModel, Field
from typing import Optional, List
import json


class ContactInfo(BaseModel):
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
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    vendor_name: Optional[str] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    line_items: List[InvoiceLineItem] = Field(default_factory=list)


class MeetingNotes(BaseModel):
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


def schema_to_tool(name: str, model_class: type[BaseModel]) -> dict:
    """Convert a Pydantic model to an Anthropic tool definition."""
    schema = model_class.model_json_schema()
    return {
        "name": f"extract_{name}",
        "description": f"Extract {name} data from the provided document.",
        "input_schema": schema,
    }
```

### الخطوة 4: دالّة الاستخراج الأساسية

```python
import os
import time
import anthropic
from enum import Enum
from dataclasses import dataclass

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
MAX_INPUT_TOKENS = 16000  # Leave headroom for output and tool definitions

SAFETY_SIGNALS = [
    "i can't help", "i cannot help", "against my guidelines",
    "content policy", "i won't", "i'm unable to assist",
]
CAPABILITY_SIGNALS = [
    "i don't have access", "i can't access", "i cannot retrieve",
    "i don't have real-time",
]


class ExtractionStatus(Enum):
    SUCCESS = "success"
    CONTEXT_TOO_LARGE = "context_too_large"
    UNKNOWN_SCHEMA = "unknown_schema"
    REFUSAL = "refusal"
    VALIDATION_ERROR = "validation_error"
    API_ERROR = "api_error"


def classify_text_response(text: str) -> str:
    """Classify a text response (when model did not use the tool)."""
    lower = text.lower()
    for signal in SAFETY_SIGNALS:
        if signal in lower:
            return "safety"
    for signal in CAPABILITY_SIGNALS:
        if signal in lower:
            return "capability"
    return "ambiguity"


def extract(
    document: str,
    schema_name: str,
    retry_on_validation_error: bool = True,
) -> dict:
    """
    Extract structured data from a document using the named schema.

    Returns a dict with keys:
      status, data, schema_name, tokens_used, cache_status, latency_s, error
    """
    start = time.time()

    # --- Gate 1: unknown schema ---
    if schema_name not in SCHEMAS:
        return {
            "status": ExtractionStatus.UNKNOWN_SCHEMA.value,
            "error": f"Unknown schema '{schema_name}'. Available: {list(SCHEMAS.keys())}",
            "data": None,
        }

    model_class = SCHEMAS[schema_name]
    tool = schema_to_tool(schema_name, model_class)

    # --- Gate 2: context window check ---
    # Rough estimate: 1 token ~= 4 characters
    estimated_tokens = len(document) // 4
    if estimated_tokens > MAX_INPUT_TOKENS:
        return {
            "status": ExtractionStatus.CONTEXT_TOO_LARGE.value,
            "error": (
                f"Document estimated at ~{estimated_tokens} tokens, "
                f"max is {MAX_INPUT_TOKENS}. Chunk the document before sending."
            ),
            "data": None,
        }

    def _call(doc: str, extra_instruction: str = "") -> anthropic.types.Message:
        user_content = f"Document:\n\n{doc}"
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
            tool_choice={"type": "any"},  # Force tool use
            messages=[{"role": "user", "content": user_content}],
        )

    # --- Attempt 1 ---
    try:
        response = _call(document)
    except anthropic.APIError as e:
        return {
            "status": ExtractionStatus.API_ERROR.value,
            "error": str(e),
            "data": None,
        }

    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_write = getattr(usage, "cache_creation_input_tokens", 0)

    if cache_read > 0:
        cache_status = "hit"
    elif cache_write > 0:
        cache_status = "write"
    else:
        cache_status = "miss"

    # --- Gate 3: refusal check ---
    # If the model returned text instead of a tool call, it refused
    tool_use_block = None
    text_response = None
    for block in response.content:
        if block.type == "tool_use":
            tool_use_block = block
        elif block.type == "text":
            text_response = block.text

    if tool_use_block is None:
        # Model did not call the tool
        refusal_category = classify_text_response(text_response or "")
        return {
            "status": ExtractionStatus.REFUSAL.value,
            "error": f"Model returned text instead of tool call. Category: {refusal_category}. Response: {(text_response or '')[:200]}",
            "data": None,
            "cache_status": cache_status,
            "tokens_used": usage.input_tokens + usage.output_tokens,
            "latency_s": round(time.time() - start, 3),
        }

    # --- Gate 4: Pydantic validation ---
    raw_input = tool_use_block.input
    try:
        validated = model_class(**raw_input)
        return {
            "status": ExtractionStatus.SUCCESS.value,
            "data": validated.model_dump(),
            "schema_name": schema_name,
            "cache_status": cache_status,
            "tokens_used": usage.input_tokens + usage.output_tokens,
            "latency_s": round(time.time() - start, 3),
            "error": None,
        }
    except Exception as validation_error:
        if not retry_on_validation_error:
            return {
                "status": ExtractionStatus.VALIDATION_ERROR.value,
                "error": str(validation_error),
                "data": raw_input,
                "latency_s": round(time.time() - start, 3),
            }

        # --- Retry with validation error feedback ---
        try:
            retry_response = _call(
                document,
                extra_instruction=(
                    f"Your previous extraction attempt failed validation with this error: "
                    f"{validation_error}. "
                    f"Please call the tool again with corrected values."
                ),
            )
            retry_tool_block = next(
                (b for b in retry_response.content if b.type == "tool_use"), None
            )
            if retry_tool_block is None:
                return {
                    "status": ExtractionStatus.VALIDATION_ERROR.value,
                    "error": "Retry did not produce a tool call",
                    "data": raw_input,
                    "latency_s": round(time.time() - start, 3),
                }
            validated = model_class(**retry_tool_block.input)
            return {
                "status": ExtractionStatus.SUCCESS.value,
                "data": validated.model_dump(),
                "schema_name": schema_name,
                "cache_status": cache_status,
                "tokens_used": (
                    usage.input_tokens + usage.output_tokens
                    + retry_response.usage.input_tokens
                    + retry_response.usage.output_tokens
                ),
                "latency_s": round(time.time() - start, 3),
                "error": None,
                "retried": True,
            }
        except Exception as retry_error:
            return {
                "status": ExtractionStatus.VALIDATION_ERROR.value,
                "error": f"Retry also failed: {retry_error}",
                "data": raw_input,
                "latency_s": round(time.time() - start, 3),
            }
```

> **اختبار من الواقع:** لماذا تستخدم tool_choice={"type": "any"} بدلًا من أن تطلب من النموذج إخراج JSON؟ لأن "any" تُجبر النموذج على استدعاء إحدى الأدوات المتوفّرة، ما يعني أن الاستجابة تأتي دائمًا عبر كتلة `tool_use` المهيكلة بدلًا من نصّ نثري. النموذج الذي يُرجع نصًّا نثريًّا يمكن أن يُنتج أي صيغة؛ أما النموذج الذي يستخدم أداة فيكون مقيّدًا بمخططك. هذا يقضي على فئة كاملة من إخفاقات التحليل (parsing failures).

### الخطوة 5: خدمة FastAPI

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel as PydanticBase

app = FastAPI(title="Extraction Service", version="1.0")


class ExtractRequest(PydanticBase):
    document: str
    schema_name: str


class ExtractResponse(PydanticBase):
    status: str
    data: dict | None = None
    schema_name: str | None = None
    tokens_used: int | None = None
    cache_status: str | None = None
    latency_s: float | None = None
    error: str | None = None


@app.post("/extract", response_model=ExtractResponse)
def extract_endpoint(request: ExtractRequest) -> ExtractResponse:
    if not request.document.strip():
        raise HTTPException(status_code=400, detail="document cannot be empty")
    result = extract(request.document, request.schema_name)
    return ExtractResponse(**result)


@app.get("/health")
def health():
    return {"status": "ok", "schemas": list(SCHEMAS.keys())}


@app.get("/schemas")
def list_schemas():
    return {
        name: cls.model_json_schema()
        for name, cls in SCHEMAS.items()
    }
```

---

## الاستخدام

### التشغيل محليًّا

```bash
# Start the service
uvicorn main:app --reload --port 8000

# Test health
curl http://localhost:8000/health

# List available schemas
curl http://localhost:8000/schemas

# Extract a contact
curl -s -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{
    "document": "Please contact Sarah Chen, Engineering Manager at DataFlow Inc. Her email is sarah.chen@dataflow.io and she can be reached at +1-415-555-0192.",
    "schema_name": "contact"
  }' | python3 -m json.tool

# Extract an invoice
curl -s -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{
    "document": "Invoice #INV-2026-0042\nDate: 2026-05-15\nVendor: Acme Cloud Services\nLine Items:\n- Compute hours (200h x $0.50): $100.00\n- Storage (500GB x $0.02): $10.00\nTotal: $110.00 USD",
    "schema_name": "invoice"
  }' | python3 -m json.tool
```

### شكل الاستجابة المتوقَّع

```json
{
  "status": "success",
  "data": {
    "name": "Sarah Chen",
    "email": "sarah.chen@dataflow.io",
    "phone": "+1-415-555-0192",
    "company": "DataFlow Inc.",
    "title": "Engineering Manager"
  },
  "schema_name": "contact",
  "tokens_used": 312,
  "cache_status": "hit",
  "latency_s": 0.81,
  "error": null
}
```

> **نقلة في المنظور:** لاحظ أن `cache_status` موجود في كل استجابة. في معظم الخدمات، تُخفى هذه البيانات الوصفية الداخلية عن استجابة الـ API. كشفها هنا متعمّد: يتيح لك التحقّق من عمل التخزين المؤقت من أمر curl بسيط من دون قراءة سجلّات أو استخدام لوحة رصد (observability dashboard). هذا هو مبدأ "ابنِه مرئيًّا" (build it visible): تكلفة إضافة حقل واحد إلى الاستجابة صفر، وقيمته في تتبّع الأخطاء على مدى الشهر الأول هائلة.

---

## التسليم

الأصل (artifact) لهذا الدرس هو `outputs/runbook-extraction-service.md`: دليل تشغيل إنتاجي يغطّي بدء التشغيل، والتهيئة، وتتبّع الأخطاء، وأنماط الفشل الشائعة.

انظر `outputs/runbook-extraction-service.md`.

---

## التقييم

### قائمة فحص اختبار الدخان (Smoke Test)

قبل اعتبار الخدمة جاهزة للإنتاج، نفّذ كل بند:

```bash
# 1. Health check returns 200
curl -s http://localhost:8000/health | grep '"status":"ok"'

# 2. Schemas endpoint lists all 3 schemas
curl -s http://localhost:8000/schemas | python3 -c "import sys,json; s=json.load(sys.stdin); print(list(s.keys()))"

# 3. Contact extraction succeeds
curl -s -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"document": "Jane Doe, jane@example.com, 555-1234, Acme Corp, CTO", "schema_name": "contact"}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); assert r['status']=='success', r"

# 4. Unknown schema returns useful error (not 500)
curl -s -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"document": "test", "schema_name": "nonexistent"}' \
  | python3 -c "import sys,json; r=json.load(sys.stdin); assert r['status']=='unknown_schema', r"

# 5. Empty document returns 400
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"document": "", "schema_name": "contact"}'
# Expected: 400

# 6. Cache hits on second request (verify cache_status changes)
# Run the contact extraction twice, second should show cache_status: "hit"
```

### قياس جودة الاستخراج

إرجاع الخدمة لـ `status: success` لا يعني أن الاستخراج صحيح. بل يعني أن الاستجابة اجتازت التحقّق من المخطّط (schema validation). لقياس جودة الاستخراج الفعلية:

1. ابنِ مجموعة بيانات ذهبية (golden dataset): 20-30 وثيقة بمخرجات متوقَّعة مُتحقَّق منها يدويًّا.
2. مرّر كل الوثائق عبر الخدمة.
3. قارن `data` بالمتوقَّع باستخدام معدّل التطابق على مستوى الحقل (field-level)، وليس التطابق التام للكائن كاملًا (التطابقات الجزئية ذات مغزى).
4. الهدف: دقّة >90% على مستوى الحقل على وثائق نظيفة وجيّدة البنية.

أنماط فشل شائعة افحصها أولًا:
- القيم النقدية: يجرّد النموذج رموز العملة أو يستخدم صيغة عشرية خاطئة
- أرقام الهاتف: يطبّع النموذج الصيغة (يزيل الشرطات، يضيف رمز الدولة)
- المصفوفات: يُرجع النموذج عنصرًا واحدًا بدلًا من كل النسخ الموجودة في الوثيقة
- null مقابل الغياب: يُرجع النموذج سلسلة فارغة بدلًا من null للحقول المفقودة
