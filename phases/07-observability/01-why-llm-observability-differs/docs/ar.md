# لماذا تختلف مراقبة LLM (Observability) عن غيرها

> رد بحالة 200 OK يحمل إجابة مهلوسة يبدو تمامًا مثل رد بحالة 200 OK يحمل إجابة صحيحة. مقاييس HTTP لا تستطيع التفريق بينهما.

**النوع:** تعلّم
**اللغات:** Python
**المتطلبات:** المرحلة 06 (التسليم/Shipping)، إلمام أساسي بالـ logging
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- شرح كيف تختلف مراقبة LLM عن مراقبة الخدمات التقليدية
- تسمية الحقول الثمانية الأساسية التي يجب أن يلتقطها كل سجل (log) لطلب LLM
- تحديد أنماط الفشل الأربعة التي تظهر فقط في الـ traces، لا في مقاييس HTTP
- بناء logger مُهيكل مبسّط يلتقط الإشارات الخاصة بـ LLM

---

## المشكلة

فريقك للتو أطلق مساعد دعم مدعومًا بالذكاء الاصطناعي. يرد في أقل من 200ms، يُرجع HTTP 200 على كل طلب، ولوحة Datadog لديك خضراء بالكامل. فريق الـ SRE راضٍ.

ثم يصلك بريد من عميل: "الذكاء الاصطناعي لديكم أخبرني أن اشتراكي يتجدد تلقائيًا في الأول من الشهر لكنه لا يفعل. فاتتني فترة الإلغاء." تبحث في سجلّاتك. تجد الطلب: status=200, latency=187ms. لا شيء غير ذلك. لا تستطيع إعادة بناء أي prompt أُرسل، ولا ما رد به النموذج، ولا أي إصدار من النموذج خدم الطلب، ولا كم token استُهلك، ولا ما إذا كانت الإجابة جاءت من الـ cache. أنت تصحّح هلوسة في الإنتاج (production) دون أي دليل.

هذه هي الفجوة الجوهرية: أدوات المراقبة التقليدية صُمّمت لخدمات حتمية (deterministic). تعطيها المُدخل نفسه، فتحصل على المُخرج نفسه، وأي انحراف يظهر في معدلات الأخطاء أو في قفزات زمن الاستجابة (latency). أنظمة LLM مختلفة. الـ prompt نفسه قد يُنتج استجابات مختلفة اختلافًا طفيفًا. الجودة تتدهور تدريجيًا، لا بشكل كارثي مفاجئ. التكلفة قد تتضاعف بين عشية وضحاها لأن قوالب الـ prompts حُدِّثت. رد 200 OK يخبرك أن طبقة HTTP عملت. لكنه لا يقول شيئًا عمّا إذا كانت الإجابة صحيحة، أو مستندة إلى مصدر (grounded)، أو آمنة.

تتطلب مراقبة LLM التقاط المحتوى الدلالي (semantic) للتفاعلات، لا مجرد مقاييس الشبكة. بدونها، لا تستطيع تصحيح الأعطال، ولا فرض الجودة، ولا التحكم في التكاليف في الإنتاج.

---

## المفهوم

### إشارات المراقبة: التقليدية مقابل LLM

تلتقط مراقبة أداء التطبيقات التقليدية (APM) ثلاث إشارات أساسية: زمن الاستجابة (latency)، ومعدل الأخطاء (error rate)، ومعدل الإنتاجية (throughput). هذه كافية حين تكون المُخرجات حتمية. أما لخدمات LLM فهي ضرورية لكنها غير كافية.

```
+---------------------------+----------------------------------------+
| TRADITIONAL APM           | LLM OBSERVABILITY (additional)         |
+---------------------------+----------------------------------------+
| HTTP status code          | model name + version                   |
| Response latency (ms)     | prompt version / template ID           |
| Requests per second       | input token count                      |
| Error rate (4xx, 5xx)     | output token count                     |
| CPU / memory usage        | cost per request (USD)                 |
| Uptime / availability     | cache hit / miss                       |
|                           | tool calls + their results             |
|                           | output quality signal (score, label)   |
+---------------------------+----------------------------------------+

Traditional APM answers: "Did the request succeed?"
LLM observability answers: "Was the answer correct, and at what cost?"
```

### أنماط الفشل الأربعة الخاصة بـ LLM

أنماط الفشل هذه غير مرئية لمراقبة طبقة HTTP:

**1. انحدار الـ Prompt (Prompt regression)** - تحديث قالب يغيّر سلوك النموذج. معدل الأخطاء يبقى 0%. يبدأ المستخدمون بالشكوى. بدون تتبع إصدار الـ prompt في سجلّاتك، لا تستطيع تحديد أي نشرة (deployment) أدخلت التغيير.

**2. انجراف النموذج (Model drift)** - مزوّد النموذج يُحدِّث الأوزان الأساسية بصمت. يتغير أسلوب المُخرجات ودقتها. تبقى مقاييس زمن الاستجابة والأخطاء دون تغيير. وحدها درجات الجودة الدلالية تكشف الانجراف.

**3. الأعطال المتسلسلة في الأدوات (Cascading tool failures)** - وكيل (agent) يستدعي الأداة A، التي تُرجع نتيجة مشوّهة، تتسبب في فشل الأداة B بصمت، مما يجعل الإجابة النهائية خاطئة. رد HTTP هو 200. الـ trace هو الأثر الوحيد الذي يُظهر سلسلة استدعاءات الأدوات.

**4. التكاليف الجامحة (Runaway costs)** - تغيير في قالب prompt يضاعف متوسط عدد الـ tokens. لا يُطلَق أي تنبيه لأن استهلاك الـ tokens ليس مقياسًا افتراضيًا في أدوات APM العامة. تتضاعف فاتورتك الشهرية قبل أن يلاحظ أحد.

### خط أنابيب الـ Logging

```
User Request
     |
     v
+----------+       +------------------+       +---------------+
| LLM Call |  -->  | Structured Logger | -->   | Log Backend   |
+----------+       +------------------+       | (stdout/OTLP/ |
     |             captures:                  |  Langfuse)    |
     v             - model                    +---------------+
LLM Response       - prompt_version
                   - input_tokens
                   - output_tokens
                   - cost_usd
                   - latency_ms
                   - cache_hit
                   - error (if any)
```

هذه الحقول الثمانية هي الحد الأدنى الصالح لسجل LLM. لكل حقل حالة استخدام في الإنتاج: model لتصحيح انجراف النموذج، prompt_version لتحديد مصدر الانحدار، عدّادات الـ tokens مع cost_usd لتنبيهات الميزانية، latency_ms لتتبّع الـ SLA، cache_hit لتحسين التكلفة، error لتصنيف الأعطال.

---

## البناء

سنبني `LLMLogger` مبسّطًا يغلّف أي استدعاء لـ Anthropic API ويُصدِر إدخال سجل مُهيكل يحتوي على الحقول الثمانية المطلوبة كلها.

### الخطوة 1: تثبيت المكتبات

```bash
pip install anthropic python-dotenv
```

### الخطوة 2: تعريف بنية سجل التسجيل

استخدم dataclass لفرض الحقول الثمانية المطلوبة. إذا غاب حقل، فلن يستطيع الـ logger إصدار سجل صالح.

```python
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional
import anthropic

@dataclass
class LLMLogRecord:
    """The 8 essential fields every LLM request log must capture."""
    model: str              # e.g. "claude-3-5-haiku-20241022"
    prompt_version: str     # e.g. "support-v2.1" - track this in your prompts
    input_tokens: int       # tokens consumed by the prompt
    output_tokens: int      # tokens consumed by the response
    cost_usd: float         # calculated from token counts and model pricing
    latency_ms: float       # wall-clock time from request to first byte of response
    cache_hit: bool         # True if response came from prompt cache
    error: Optional[str]    # None on success; error class name on failure
```

### الخطوة 3: بناء الـ logger المُهيكل

```python
# Token costs for Claude models (per million tokens, as of 2026)
# Source: https://www.anthropic.com/pricing
MODEL_COSTS = {
    "claude-3-5-haiku-20241022": {
        "input_per_m": 0.80,
        "output_per_m": 4.00,
        "cache_read_per_m": 0.08,
    },
    "claude-3-5-sonnet-20241022": {
        "input_per_m": 3.00,
        "output_per_m": 15.00,
        "cache_read_per_m": 0.30,
    },
}

def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
) -> float:
    """Calculate USD cost for an API call based on token counts."""
    pricing = MODEL_COSTS.get(model, MODEL_COSTS["claude-3-5-haiku-20241022"])
    input_cost = (input_tokens / 1_000_000) * pricing["input_per_m"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_per_m"]
    cache_cost = (cache_read_tokens / 1_000_000) * pricing["cache_read_per_m"]
    return round(input_cost + output_cost + cache_cost, 8)


class LLMLogger:
    """
    Minimal structured logger for LLM API calls.
    Wraps Anthropic API calls and emits JSON log records with the 8 required fields.
    """

    def __init__(self, output_file: Optional[str] = None):
        self.client = anthropic.Anthropic()
        self.output_file = output_file

    def call(
        self,
        prompt: str,
        prompt_version: str,
        model: str = "claude-3-5-haiku-20241022",
        system: str = "You are a helpful assistant.",
        max_tokens: int = 512,
    ) -> tuple[str, LLMLogRecord]:
        """
        Call the Anthropic API and return (response_text, log_record).
        Always emits a log record, even on failure.
        """
        start = time.monotonic()
        error = None
        response_text = ""
        input_tokens = 0
        output_tokens = 0
        cache_hit = False

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            # Prompt cache: Anthropic returns cache_read_input_tokens when cache is hit
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            cache_hit = cache_read > 0

        except anthropic.APIError as exc:
            error = type(exc).__name__

        latency_ms = (time.monotonic() - start) * 1000

        record = LLMLogRecord(
            model=model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=calculate_cost(model, input_tokens, output_tokens),
            latency_ms=round(latency_ms, 2),
            cache_hit=cache_hit,
            error=error,
        )

        self._emit(record)
        return response_text, record

    def _emit(self, record: LLMLogRecord) -> None:
        """Write the log record as a JSON line to stdout and optionally to a file."""
        line = json.dumps(asdict(record))
        print(line)
        if self.output_file:
            with open(self.output_file, "a") as f:
                f.write(line + "\n")
```

### الخطوة 4: شغّله وافحص المُخرَج

```python
def main():
    logger = LLMLogger(output_file="llm_requests.jsonl")

    # Simulate two requests with different prompt versions
    questions = [
        ("What is the capital of France?", "general-qa-v1"),
        ("Summarize quantum computing in one sentence.", "summary-v2"),
        ("INVALID PROMPT" * 10000, "stress-test-v1"),  # will succeed but use many tokens
    ]

    for prompt, version in questions:
        text, record = logger.call(
            prompt=prompt,
            prompt_version=version,
        )
        print(f"--- Response: {text[:80]}...")
        print(f"--- Cost: ${record.cost_usd:.6f} | Tokens: {record.input_tokens}in / {record.output_tokens}out")
        print()


if __name__ == "__main__":
    main()
```

مثال على المُخرَج (سطر لكل طلب، صادر بصيغة JSON مُهيكلة):

```json
{"model": "claude-3-5-haiku-20241022", "prompt_version": "general-qa-v1", "input_tokens": 18, "output_tokens": 11, "cost_usd": 0.0000588, "latency_ms": 412.3, "cache_hit": false, "error": null}
```

> **اختبار من الواقع:** يرى مديرك هذا فيقول: "عندنا Datadog أصلًا. يعرض زمن الاستجابة ومعدلات الأخطاء. لماذا نحتاج logger منفصلًا فقط لاستدعاءات LLM؟ أليس هذا تكرارًا؟" كيف تشرح ما يستطيع Datadog رؤيته وما لا يستطيع رؤيته عن خدمة LLM لديك؟

### الخطوة 5: تحقّق من مسار التقاط الأعطال

افتعل خطأً للتأكد من أن الـ logger يلتقطه بشكل صحيح:

```python
# This will raise an AuthenticationError or similar
import os
os.environ["ANTHROPIC_API_KEY"] = "sk-invalid-key"
bad_logger = LLMLogger()
text, record = bad_logger.call("Hello", prompt_version="test-v1")
assert record.error is not None, "Error field must be set on API failure"
assert record.input_tokens == 0, "Token counts must be zero on failure"
print(f"Captured error: {record.error}")
```

---

## الاستخدام

تلتقط أدوات APM العامة (Datadog وNew Relic وPrometheus) ما يحدث في طبقة نقل HTTP. إليك ما تراه كل أداة مقابل ما تحتاجه لمراقبة LLM:

```
+----------------------+------------------+-----------------------------+
| Signal               | Generic APM      | LLM Logger                  |
+----------------------+------------------+-----------------------------+
| HTTP status          | Yes              | Yes (via error field)        |
| Response latency     | Yes              | Yes (latency_ms)             |
| Request rate         | Yes              | Derivable from log volume    |
| Error rate           | Yes (HTTP only)  | Yes (semantic errors too)    |
| Cost per request     | No               | Yes (cost_usd)               |
| Token counts         | No               | Yes (input/output_tokens)    |
| Prompt version       | No               | Yes (prompt_version)         |
| Model version        | No               | Yes (model)                  |
| Cache effectiveness  | No               | Yes (cache_hit)              |
| Tool call chains     | No               | Needs OTel spans (L02-L03)   |
+----------------------+------------------+-----------------------------+
```

في الإنتاج، ستوجّه سجلّات JSONL هذه إلى مُجمِّع سجلّات (Elastic أو Loki أو CloudWatch Logs) وتبني لوحات (dashboards) فوقها. الدرسان 02 و03 من هذه المرحلة يستبدلان الـ logger الخام بصيغة JSON بـ spans من OpenTelemetry ويوجّهانها إلى Langfuse للحصول على قدرات استعلام وعرض أغنى.

> **نقلة في المنظور:** يقترح مهندس أقدم: "بدل logger مخصص، خلّينا نسجّل كائن استجابة الـ API الخام ونحلّله لاحقًا." ما مشاكل هذا النهج في نظام يعالج 10,000 طلب يوميًا، ومتى يكون مقبولًا فعلًا؟

---

## التسليم

يُنتج هذا الدرس دليلًا تمهيديًا قابلًا لإعادة الاستخدام في المراقبة يمكن لأي خدمة LLM تبنّيه.

**المُخرَج (Artifact):** `outputs/prompt-llm-observability-primer.md`

ملف `code/main.py` في هذا الدرس هو نقطة البداية لتسجيل طلبات LLM. انسخ `LLMLogger` و`LLMLogRecord` إلى خدمتك. عدّل `MODEL_COSTS` حين تضيف نماذج جديدة. صيغة مُخرَج JSONL بسيطة عن قصد: كائن JSON واحد لكل سطر، يسهل شحنه إلى أي مُجمِّع سجلّات.

---

## التقييم

نظام تسجيل يُسقِط السجلّات أو يلتقط بيانات خاطئة أسوأ من غياب التسجيل: فهو يخلق ثقة زائفة.

**الفحص 1: اكتمال المخطط (Schema completeness)**

بعد تشغيل 10 طلبات، تحقّق من ألّا يكون أي حقل null بينما يُفترض أن تكون له قيمة:

```python
import json

with open("llm_requests.jsonl") as f:
    records = [json.loads(line) for line in f]

required_fields = ["model", "prompt_version", "input_tokens", "output_tokens",
                   "cost_usd", "latency_ms", "cache_hit", "error"]

for i, record in enumerate(records):
    for field in required_fields:
        assert field in record, f"Record {i} missing field: {field}"

print(f"Schema check passed: {len(records)} records, all fields present")
```

**الفحص 2: دقة التكلفة**

قارن تكلفتك المحسوبة بقيمة وحدة تحكم Anthropic لطلب معروف:

```python
# After running a request, compare logger cost to actual API cost
# The Anthropic console shows per-request cost in the usage dashboard
# Tolerance: within 1% (rounding differences in token counting)
expected_cost = 0.000059  # from Anthropic console
actual_cost = records[0]["cost_usd"]
assert abs(expected_cost - actual_cost) / expected_cost < 0.01, \
    f"Cost calculation off: got {actual_cost}, expected {expected_cost}"
```

**الفحص 3: دقة قياس زمن الاستجابة**

تحقّق من أن زمن الاستجابة المسجَّل متّسق مع زمن استجابة الـ API الفعلي بمقارنة قياس ساعة الحائط (wall-clock) برؤوس (headers) الـ API نفسها:

```python
import anthropic, time

client = anthropic.Anthropic()
start = time.monotonic()
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=10,
    messages=[{"role": "user", "content": "Hi"}],
)
wall_ms = (time.monotonic() - start) * 1000

# Your logger's latency_ms should be within 50ms of wall_ms
# (overhead from JSON serialization and file write)
print(f"Wall clock: {wall_ms:.0f}ms")
print(f"Logger should capture: within 50ms of this value")
```

**الفحص 4: اكتمال التقاط الأخطاء**

تأكّد أن 100% من أخطاء الـ API ينتج عنها حقل `error` غير null، وأن عدّادات الـ tokens تساوي 0 عند الأعطال:

```python
error_records = [r for r in records if r["error"] is not None]
for r in error_records:
    assert r["input_tokens"] == 0, "Partial token data on error is misleading"
    assert r["output_tokens"] == 0, "Partial token data on error is misleading"
    assert r["cost_usd"] == 0.0, "Zero cost on errors: no tokens consumed"

print(f"Error capture check passed: {len(error_records)} error records validated")
```
