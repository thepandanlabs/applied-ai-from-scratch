# تجهيز تطبيق: من OTel الخام إلى Langfuse/Phoenix

> كلٌّ من Langfuse وPhoenix يتحدّث OTLP. غيّر متغير بيئة واحدًا لتبديل الـ backends. لا تُعِد كتابة تجهيزك أبدًا.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 07-02 (أعراف GenAI في OpenTelemetry)، أساسيات FastAPI
**الوقت:** ~75 دقيقة
**أهداف التعلّم:**
- إضافة تتبّع OTel إلى خدمة FastAPI تستدعي Anthropic
- توجيه الـ traces إلى Langfuse (سحابي) وPhoenix (محلي) عبر OTLP
- فهم مساري التجهيز: OTel الخام مقابل التجهيز التلقائي (auto-instrumentation)
- نشر سياق التتبّع (trace context) عبر المهام الخلفية (background tasks)

---

## المشكلة

لديك خدمة FastAPI عاملة تستدعي Anthropic API. وتعلّمت أعراف gen_ai.*. الآن تحتاج فعلًا إلى إدخال الـ traces إلى backend تستطيع فيه الاستعلام عنها وبناء لوحات وتصحيح أعطال الإنتاج.

التحدي أن هناك مسارَي تجهيز يخدمان حاجات مختلفة: spans خام في OTel (تحكّم أقصى، وسمات gen_ai.* صحيحة) وLangfuse Python SDK (تكامل أبسط، وميزات خاصة بـ LLM، لكن أقل قابلية للنقل). اختيار المسار الخاطئ يعني إما هندسة مُفرِطة لخدمة بسيطة أو تجهيزًا ناقصًا لخدمة معقّدة. وكلا المسارين يتطلبان فهم كيفية انتشار سياق التتبّع عبر مسارات FastAPI غير المتزامنة (async)، والمهام الخلفية، وخطوط الأنابيب متعددة الخطوات.

---

## المفهوم

### مسارا التجهيز

```
Your FastAPI App + Anthropic Calls
          |
          +----------- Path A: Raw OTel SDK -----------------+
          |            opentelemetry-sdk                      |
          |            manual span creation                   |
          |            gen_ai.* attributes                    |
          |            OTLP export                           |
          |                                                    v
          |                                         Any OTLP Backend
          |                                         (Langfuse / Phoenix /
          |                                          Jaeger / Grafana Tempo)
          |
          +----------- Path B: Langfuse Python SDK ----------+
                       langfuse.Langfuse()                   |
                       trace / generation / span             |
                       decorator or context manager          |
                                                              v
                                                     Langfuse only
                                                     (cloud or self-hosted)
```

**المسار A (OTel الخام):** اكتب spans بسمات gen_ai.* يدويًا باستخدام OTel SDK. استخدم `OTLPSpanExporter` للتوجيه إلى أي backend متوافق مع OTel. قابلية نقل قصوى. أنت تتحكم في كل سمة. كود أكثر.

**المسار B (Langfuse SDK):** استخدم Langfuse Python SDK مباشرة. واجهة برمجية أبسط، ومفاهيم أصيلة لـ LLM (trace وgeneration وspan). يعمل مع Langfuse فقط. أقل قابلية للنقل لكنه أسرع إعدادًا.

**قاعدة عملية:** استخدم OTel الخام إذا كان فريق منصّتك يملك بنية المراقبة، أو إذا كنت قد تبدّل الـ backends. استخدم Langfuse SDK مباشرة إذا كنت فريقًا صغيرًا وLangfuse هو الـ backend الذي اخترته.

كلا المسارين يرسلان البيانات إلى الـ backends نفسها. Langfuse يقبل OTel الخام عبر OTLP وكذلك صيغة SDK الخاصة به.

### سياق التتبّع في تطبيق FastAPI غير المتزامن (Async)

```
HTTP Request arrives at FastAPI
         |
         v
+------------------+          OTel injects trace_id here
| @app.post("/ask")| -------> root span: "POST /ask"
|  async def ask() |
+------------------+
         |
         | (awaits)
         v
+------------------+
| call_claude()    | -------> child span: "claude-3-5-haiku-20241022 chat"
|                  |          parent_id = root span's span_id
+------------------+
         |
         | (background task)
         v
+------------------+
| log_interaction()| -------> child span: "log-interaction"
|  BackgroundTask  |          MUST explicitly propagate context
+------------------+          (background tasks break automatic propagation)
```

لا ترث المهام الخلفية في FastAPI سياق التتبّع الأبوي تلقائيًا لأنها تعمل بعد إرسال رد HTTP. يجب أن تلتقط السياق قبل الإرسال وأن تربطه في المهمة الخلفية.

---

## البناء

سنضيف تتبّع OTel إلى خدمة FastAPI تستدعي Anthropic API، مع توجيه الـ traces إلى وحدة التحكم أولًا، ثم إلى Langfuse.

### الخطوة 1: تثبيت المكتبات

```bash
pip install fastapi uvicorn anthropic opentelemetry-sdk \
    opentelemetry-instrumentation-fastapi \
    opentelemetry-exporter-otlp-proto-grpc \
    python-dotenv
```

### الخطوة 2: تهيئة الـ tracer لتصدير OTLP

تقرأ هذه التهيئة الـ OTLP endpoint من متغير بيئة، فتستطيع التبديل بين Langfuse وPhoenix وJaeger المحلي دون تغييرات في الكود.

```python
import os
from opentelemetry import trace, context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

def setup_tracer() -> trace.Tracer:
    """
    Configure OTel tracer.
    Uses OTLP export if OTEL_EXPORTER_OTLP_ENDPOINT is set, else console.
    """
    provider = TracerProvider()

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        headers_str = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers: dict[str, str] = {}
        if headers_str:
            for pair in headers_str.split(","):
                k, _, v = pair.partition("=")
                headers[k.strip()] = v.strip()

        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        print(f"OTel: exporting to {endpoint}")
    else:
        provider.add_span_processor(
            BatchSpanProcessor(ConsoleSpanExporter())
        )
        print("OTel: exporting to console (set OTEL_EXPORTER_OTLP_ENDPOINT to use a backend)")

    trace.set_tracer_provider(provider)
    return trace.get_tracer("appliedai.phase07.lesson03", "1.0.0")
```

### الخطوة 3: بناء خدمة FastAPI مع استدعاءات LLM مُجهَّزة

```python
import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional

import anthropic
from fastapi import BackgroundTasks, FastAPI
from opentelemetry.trace import SpanKind, Status, StatusCode
from pydantic import BaseModel

# --- Request / Response models ---

class AskRequest(BaseModel):
    question: str
    prompt_version: str = "default-v1"
    max_tokens: int = 512

class AskResponse(BaseModel):
    answer: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    trace_id: str  # return the trace ID so clients can look up the span

# --- App setup ---

_tracer: Optional[trace.Tracer] = None
_anthropic_client: Optional[anthropic.Anthropic] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tracer, _anthropic_client
    _tracer = setup_tracer()
    _anthropic_client = anthropic.Anthropic()
    yield

app = FastAPI(lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)  # auto-instruments HTTP spans

# --- LLM call with gen_ai.* spans ---

async def call_claude(
    tracer: trace.Tracer,
    client: anthropic.Anthropic,
    question: str,
    prompt_version: str,
    max_tokens: int,
) -> tuple[str, int, int]:
    """
    Call Anthropic API inside a gen_ai.* span.
    Returns (answer, input_tokens, output_tokens).
    """
    model = "claude-3-5-haiku-20241022"
    span_name = f"{model} chat"

    with tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("gen_ai.request.max_tokens", max_tokens)
        span.set_attribute("gen_ai.operation.name", "chat")
        # Custom extension: track prompt version alongside standard attrs
        span.set_attribute("ai.prompt_version", prompt_version)

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": question}],
            ),
        )

        span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)
        span.set_attribute("gen_ai.response.model", response.model)
        span.set_status(Status(StatusCode.OK))

        return (
            response.content[0].text,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
```

### الخطوة 4: مهمة خلفية مع نشر صريح للسياق

تعمل المهام الخلفية في FastAPI بعد إرسال رد HTTP. ولا يعبر النشر التلقائي للسياق في OTel هذا الحدّ. التقط السياق صراحةً قبل الإرسال.

```python
from opentelemetry.propagate import inject
from opentelemetry.context import attach, detach

def log_interaction_background(
    question: str,
    answer: str,
    tracer: trace.Tracer,
    parent_context,  # captured before response was sent
) -> None:
    """
    Background task that logs interaction details.
    Must attach parent_context to continue the trace tree.
    """
    token = attach(parent_context)
    try:
        with tracer.start_as_current_span("log-interaction") as span:
            span.set_attribute("interaction.question_len", len(question))
            span.set_attribute("interaction.answer_len", len(answer))
            # In production: write to database, push to eval queue, etc.
    finally:
        detach(token)

# --- FastAPI route ---

@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, background_tasks: BackgroundTasks):
    start = time.monotonic()

    # Capture the current trace context BEFORE the response is sent
    # (background tasks run after; context would otherwise be lost)
    current_context = context.get_current()

    answer, input_tokens, output_tokens = await call_claude(
        _tracer, _anthropic_client, req.question, req.prompt_version, req.max_tokens
    )

    latency_ms = (time.monotonic() - start) * 1000

    # Get the current trace ID to return to the client
    current_span = trace.get_current_span()
    trace_id = format(current_span.get_span_context().trace_id, "032x")

    background_tasks.add_task(
        log_interaction_background,
        req.question,
        answer,
        _tracer,
        current_context,
    )

    return AskResponse(
        answer=answer,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=round(latency_ms, 2),
        trace_id=trace_id,
    )
```

> **اختبار من الواقع:** يرسل مستخدم سؤالًا معقّدًا. بعد ثلاث ثوانٍ، تفشل المهمة الخلفية التي تسجّل التفاعل. حصل المستخدم على إجابة صحيحة. عند النظر إلى الـ trace في Langfuse، يكون span المهمة الخلفية مفقودًا. يقول زميلك: "لا بأس، المستخدم حصل على إجابته." ما المشكلة في spans المهام الخلفية المفقودة في الإنتاج، ومتى تصبح حرجة؟

---

## الاستخدام

Langfuse Python SDK هو المسار الأبسط حين يكون Langfuse هو الـ backend الذي اخترته. فهو يجرّد إدارة spans في OTel إلى مفاهيم أصيلة لـ LLM.

```python
# pip install langfuse anthropic
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context
import anthropic

langfuse = Langfuse()  # reads LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
client = anthropic.Anthropic()

@observe(as_type="generation")
def call_claude_langfuse(question: str, prompt_version: str) -> str:
    """
    The @observe decorator automatically creates a Langfuse generation record.
    LangFuse captures: input, output, token usage, latency, and model.
    """
    langfuse_context.update_current_observation(
        model="claude-3-5-haiku-20241022",
        metadata={"prompt_version": prompt_version},
    )
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text

@observe()
def handle_request(question: str, prompt_version: str) -> str:
    """The outer @observe creates a trace. The inner creates a generation."""
    return call_claude_langfuse(question, prompt_version)
```

**Langfuse SDK مقابل OTel الخام لحالة الاستخدام هذه:**

```
+-------------------------------+-----------------+--------------------+
| Capability                    | Raw OTel        | Langfuse SDK       |
+-------------------------------+-----------------+--------------------+
| Backend portability           | Any OTLP        | Langfuse only      |
| gen_ai.* compliance           | You control it  | Automatic          |
| LLM-native concepts           | DIY             | trace/generation   |
| Setup complexity              | Higher          | Lower              |
| Custom attributes             | Full control    | Via metadata dict  |
| Platform team integration     | Straightforward | Requires Langfuse  |
+-------------------------------+-----------------+--------------------+
```

> **نقلة في المنظور:** يقول مهندس في شركة ناشئة: "Langfuse SDK أبسط بكثير. لماذا قد يستخدم أحد OTel الخام لتتبّع LLM؟" متى يكون Langfuse SDK الخيار الصحيح، ومتى يستحق OTel الخام التعقيد الإضافي؟

---

## التسليم

يُنتج هذا الدرس مهارة تجهيز قابلة لإعادة الاستخدام في Langfuse لخدمات الذكاء الاصطناعي.

**المُخرَج (Artifact):** `outputs/skill-langfuse-instrumentation.md`

ملف `code/main.py` في هذا الدرس هو خدمة FastAPI كاملة بمسارَي تجهيز. لاستخدامه في مشروع حقيقي: انسخ دالة `setup_tracer()` ومغلِّف الـ span في `call_claude()` إلى خدمتك، واضبط متغيرات البيئة للـ backend الذي اخترته، واستخدم `FastAPIInstrumentor.instrument_app(app)` لتجهيز مسارات HTTP تلقائيًا. ويتطلب نشر السياق للمهام الخلفية نمط `attach(current_context)` الصريح المعروض في `log_interaction_background`.

---

## التقييم

التجهيز الذي يُسقِط spans بصمت هو أخطر نوع: فهو يجعل لوحاتك تبدو مكتملة بينما هي ليست كذلك.

**الفحص 1: اكتمال الـ trace**

لكل طلب HTTP إلى `/ask`، تحقّق من أن الـ trace يحتوي على كل الـ spans المتوقعة:

```bash
# With traces going to Langfuse, query the Langfuse API
# or check the Langfuse UI: each trace should show:
# - root span from FastAPI auto-instrumentation (HTTP layer)
# - "claude-3-5-haiku-20241022 chat" span (LLM call)
# - "log-interaction" span (background task)
# Missing any of these = context propagation failure
```

**الفحص 2: سمات gen_ai.* مُعبّأة**

تحقّق من أن كل span لاستدعاء LLM في الـ backend لديه قيمًا غير null للسمات الأربع المطلوبة:

```python
# Langfuse API check (pseudocode -- replace with actual Langfuse SDK calls)
from langfuse import Langfuse

lf = Langfuse()
traces = lf.fetch_traces(limit=10).data

for t in traces:
    for obs in lf.fetch_observations(trace_id=t.id).data:
        if obs.type == "GENERATION":
            assert obs.model is not None, f"Model missing on trace {t.id}"
            assert obs.usage.input is not None, "input_tokens missing"
            assert obs.usage.output is not None, "output_tokens missing"

print("All recent generation spans have required fields")
```

**الفحص 3: وجود spans المهام الخلفية**

افتعل تشغيل مهمة خلفية وتحقّق من ظهور span الخاص بها في الـ trace:

```python
import httpx

async def test_background_task_traced():
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/ask", json={
            "question": "Test question",
            "prompt_version": "test-v1"
        })
        assert resp.status_code == 200
        trace_id = resp.json()["trace_id"]
        print(f"Trace ID: {trace_id}")
        # In Langfuse UI: verify trace contains log-interaction span
        # It may take 1-2 seconds for the background task to complete
```

**الفحص 4: زمن الاستجابة يحتسب كل العمل**

ينبغي أن تكون مدة الـ trace الكلية (الـ span الجذري) مساوية تقريبًا لمجموع مُدد الـ spans الأبناء. وجود فجوة كبيرة يدل على عمل غير مُتتبَّع، مثل البرمجيات الوسيطة (middleware) أو عبء التسلسل (serialization) الذي ينبغي قياسه:

```python
# Compare HTTP response latency_ms (from AskResponse)
# to the span duration visible in Langfuse
# If they differ by more than 20%, some work is not being traced
print("Check: root span duration matches HTTP response latency_ms within 20%")
```
