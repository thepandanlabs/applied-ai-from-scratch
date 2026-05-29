# تسجيل الـ Prompts والاستجابات واستدعاءات الأدوات

> سجّل ما تحتاجه للتصحيح. واحجب ما لا يجوز تخزينه (redact). ولا تخلط بين الاثنين أبدًا.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** المرحلة 07 الدروس 01-04 (أساسيات المراقبة، OpenTelemetry، Langfuse، الـ traces)
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- تحديد أي الحقول تُسجَّل، وأيها يُحجَب، والمنطق الإنتاجي وراء كل قرار
- تنفيذ كشف وحجب الـ PII للأنماط الشائعة: البريد الإلكتروني، الهاتف، رقم الضمان الاجتماعي (SSN)
- بناء logger مُهيكل بصيغة JSONL لطلبات LLM باستخدام مكتبة Python القياسية
- استبدال الـ logger الخام بـ `structlog` للحصول على مُخرَج متّسق وقابل للتحليل (parseable)
- تطبيق نمط تجزئة الـ prompt (prompt-hashing) للحصول على إزالة التكرار (deduplication) دون تخزين نص الـ prompt كاملًا

---

## المشكلة

تُطلَق ميزة LLM لديك. بعد ثلاثة أسابيع، يبلّغ مستخدم أن المساعد أرجع شيئًا خاطئًا. تفتح سجلّاتك. تبدو هكذا:

```
2026-04-12 14:23:01 INFO - LLM call completed
2026-04-12 14:23:02 INFO - LLM call completed
2026-04-12 14:23:02 INFO - LLM call completed
```

لا اسم نموذج. لا prompt. لا استجابة. لا tokens. لا زمن استجابة. لا تستطيع إعادة إنتاج العطل. لا تستطيع معرفة أي استدعاء فشل. لا تستطيع حتى معرفة أي نموذج استُخدم.

الإصلاح البديهي: سجّل كل شيء. لكن فريقًا آخر يسجّل كل شيء فيتعرّض لتدقيق GDPR. سجلّاتهم تحتوي على بُرُد المستخدمين وأرقام هواتفهم، وفي حالة واحدة رقم ضمان اجتماعي (Social Security Number) لصقه مستخدم في prompt. تتبع ذلك مسائل قانونية.

الجواب الصحيح ليس أيًّا من الطرفين. تحتاج سجلّات مُهيكلة قابلة للقراءة آليًا تلتقط ما تحتاجه للتصحيح والتحسين، مع حقول الـ PII إما مُنظَّفة (scrubbed) أو غير مُخزَّنة من الأساس. يبني هذا الدرس ذلك الـ logger من الصفر، ثم يوصّله بـ `structlog` للإنتاج.

---

## المفهوم

### ماذا تُسجِّل وماذا لا تُسجِّل

```
+---------------------------+-------------+------------------------------------------+
| Field                     | Log?        | Reason                                   |
+---------------------------+-------------+------------------------------------------+
| model name/version        | YES         | Needed for cost attribution, regression  |
| prompt hash (SHA-256)     | YES         | Dedup without storing PII                |
| full prompt text          | ON ERROR ONLY| PII risk at scale; log only on failure  |
| response (truncated, Nch) | YES         | Enough to verify output type             |
| input token count         | YES         | Cost, rate-limit debugging               |
| output token count        | YES         | Cost, output verbosity tracking          |
| cache tokens              | YES         | Cache hit rate measurement               |
| latency ms (total)        | YES         | Performance baseline                     |
| time to first token ms    | YES         | UX metric for streaming endpoints        |
| tool call names           | YES         | Workflow debugging, capability usage     |
| tool call arg schemas     | YES         | Understand which fields were passed      |
| tool call arg VALUES      | REDACT      | May contain API keys, credentials, PII   |
| user ID (opaque hash)     | YES         | Per-user cost/usage; not the email       |
| user email / name         | NO          | PII - use hashed user_id instead         |
| SSN, phone, credit card   | NO          | PII - redact before any storage          |
| API keys                  | NEVER       | Credentials; never in logs               |
| error type + message      | YES         | Debugging; strip any PII from message    |
+---------------------------+-------------+------------------------------------------+
```

### نمط تجزئة الـ Prompt (Prompt-Hash)

الفكرة الجوهرية: تريد إزالة التكرار وأثرًا للتصحيح دون تخزين الـ PII على نطاق واسع.

```
Full prompt text  -->  SHA-256 hash  -->  Store the hash in every log line
                  |
                  +--> If an error occurs, log the full prompt to a SEPARATE
                       error log with a short TTL and restricted access
```

يمنحك هذا:
- القدرة على كشف متى يُطلَق الـ prompt نفسه آلاف المرات (عاصفة إخفاقات cache)
- قابلية التصحيح حين يحدث خطأ ما (سجل الأخطاء يحتوي على النص الكامل)
- خلوّ مجرى سجلّك الرئيسي من الـ PII

### أنماط كشف الـ PII

```
Pattern          Regex                                   Example match
-----------      --------------------------------------  ---------------------
Email            [a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.\w+ jane@example.com
Phone (US)       \b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b      415-555-0192
SSN              \b\d{3}-\d{2}-\d{4}\b                  123-45-6789
Credit card      \b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4} 4111 1111 1111 1111
```

تلتقط هذه الأنماط الحالات الشائعة. وهي ليست شاملة. للرعاية الصحية أو المالية، استخدم مكتبة مخصصة لكشف الـ PII (Presidio أو AWS Comprehend Medical). ولمعظم منتجات الـ SaaS، تغطي هذه الأنماط الأربعة أكثر من 90% من الـ PII العَرَضي في الـ prompts.

### التسجيل المُهيكل: JSONL مقابل غير المُهيكل

```
UNSTRUCTURED (hard to parse, hard to query):
  2026-04-12 14:23:01 INFO LLM call: claude-3-5-haiku-20241022 | 234 tokens | 412ms

STRUCTURED JSONL (machine-readable, queryable with jq or any log aggregator):
  {"ts":"2026-04-12T14:23:01Z","model":"claude-3-5-haiku-20241022","input_tokens":189,
   "output_tokens":45,"latency_ms":412,"prompt_hash":"a3f2...","level":"info"}
```

سطر واحد لكل طلب. كل سطر JSON صالح. تستطيع توجيهه عبر الأنبوب (pipe) إلى `jq`، أو إدخاله إلى Loki أو CloudWatch أو Datadog دون أي تحويل.

---

## البناء

### الخطوة 1: مُنظِّف الـ PII (PII Scrubber)

```python
import re
from typing import Optional

# Common PII patterns - extend for your domain
PII_PATTERNS = [
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL]'),
    (r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]'),
    (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]'),
    (r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b', '[CARD]'),
]

def scrub_pii(text: str) -> tuple[str, list[str]]:
    """
    Replace PII patterns with placeholders.
    Returns (scrubbed_text, list_of_pattern_types_found).
    """
    found: list[str] = []
    result = text
    for pattern, replacement in PII_PATTERNS:
        matches = re.findall(pattern, result)
        if matches:
            found.append(replacement.strip('[]').lower())
            result = re.sub(pattern, replacement, result)
    return result, found
```

### الخطوة 2: مُجزِّئ الـ Prompt (Prompt Hasher)

```python
import hashlib

def hash_prompt(prompt: str) -> str:
    """
    SHA-256 hash of the prompt text.
    Use this as the log-safe identifier for the prompt.
    """
    return hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:16]
```

نقتطع إلى 16 خانة hex (64 بت): احتمال التصادم (collision) مُهمَل لأي حجم استدعاءات واقعي، وهذا يبقي أسطر السجل قصيرة.

### الخطوة 3: الـ LLMRequestLogger

```python
import json
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class LLMLogEntry:
    ts: str
    model: str
    prompt_hash: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: float
    response_preview: str          # first 200 chars only
    tool_calls: list[str]          # names only, not args
    user_id: Optional[str]
    error: Optional[str]
    pii_detected: list[str]        # which PII types were found in prompt
    level: str = 'info'
    # Full prompt stored ONLY on error, in a separate restricted log
    _full_prompt: str = field(default='', repr=False)


class LLMRequestLogger:
    """
    Structured JSONL logger for LLM requests.
    Scrubs PII from prompts before logging.
    Logs full prompt text only when an error occurs.
    """

    def __init__(self, log_path: str = 'llm_requests.jsonl',
                 error_log_path: str = 'llm_errors.jsonl',
                 response_preview_chars: int = 200):
        self.log_path = log_path
        self.error_log_path = error_log_path
        self.preview_chars = response_preview_chars

    def log(
        self,
        model: str,
        prompt: str,
        response: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        tool_calls: Optional[list[dict]] = None,
        user_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> LLMLogEntry:
        """Log a single LLM request. Returns the log entry for callers that need it."""
        # Hash the prompt, detect PII (don't store the full prompt in normal logs)
        prompt_hash = hash_prompt(prompt)
        _, pii_found = scrub_pii(prompt)

        # Extract tool call names only
        tool_names = [tc.get('name', 'unknown') for tc in (tool_calls or [])]

        entry = LLMLogEntry(
            ts=datetime.now(timezone.utc).isoformat(),
            model=model,
            prompt_hash=prompt_hash,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            latency_ms=round(latency_ms, 2),
            response_preview=response[:self.preview_chars],
            tool_calls=tool_names,
            user_id=user_id,
            error=error,
            pii_detected=pii_found,
            level='error' if error else 'info',
            _full_prompt=prompt,
        )

        self._write(entry)
        return entry

    def _write(self, entry: LLMLogEntry) -> None:
        """Write to JSONL. On error, also write full prompt to restricted error log."""
        # Build the dict to log - exclude internal _full_prompt field
        d = {k: v for k, v in asdict(entry).items() if not k.startswith('_')}

        line = json.dumps(d, ensure_ascii=False)

        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

        # On error: write full prompt to the restricted error log
        if entry.error:
            error_record = {
                'ts': entry.ts,
                'prompt_hash': entry.prompt_hash,
                'error': entry.error,
                'full_prompt': entry._full_prompt,  # only here, only on error
            }
            with open(self.error_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(error_record, ensure_ascii=False) + '\n')
```

> **اختبار من الواقع:** يقول زميل: "لماذا نتكبّد عناء تجزئة الـ prompt؟ إذا كانت السجلّات خلف الـ VPN لدينا، فلن يراها إلا المهندسون الداخليون." ما الخلل في هذا المنطق، وماذا يحدث بعد ستة أشهر حين تشتري شركتك شركة أخرى وتُدمَج خطوط أنابيب السجلّات؟

### الخطوة 4: وصّله باستدعاء API حقيقي

```python
import anthropic
import time

llm_logger = LLMRequestLogger()
client = anthropic.Anthropic()

def call_with_logging(
    prompt: str,
    user_id: Optional[str] = None,
    model: str = "claude-3-5-haiku-20241022",
) -> str:
    """Make a Claude API call and log the result."""
    start = time.monotonic()
    error_msg = None
    response_text = ''
    usage = None
    tool_calls_raw = []

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = response.content[0].text if response.content else ''
        usage = response.usage
        # Collect tool calls if any
        tool_calls_raw = [
            {"name": b.name, "schema": list(b.input.keys())}
            for b in response.content
            if b.type == "tool_use"
        ]
    except Exception as e:
        error_msg = type(e).__name__ + ': ' + str(e)

    latency_ms = (time.monotonic() - start) * 1000

    llm_logger.log(
        model=model,
        prompt=prompt,
        response=response_text,
        input_tokens=getattr(usage, 'input_tokens', 0),
        output_tokens=getattr(usage, 'output_tokens', 0),
        cache_read_tokens=getattr(usage, 'cache_read_input_tokens', 0),
        cache_write_tokens=getattr(usage, 'cache_creation_input_tokens', 0),
        latency_ms=latency_ms,
        tool_calls=tool_calls_raw,
        user_id=user_id,
        error=error_msg,
    )

    if error_msg:
        raise RuntimeError(error_msg)
    return response_text
```

---

## الاستخدام

يمنحك `structlog` المُخرَج المُهيكل نفسه بقالب أقل (boilerplate)، إضافة إلى ترشيح حسب مستوى السجل (log-level filtering)، ومعالِجات (processors)، وتوافق جاهز (drop-in) مع أي مُجمِّع سجلّات.

```python
import structlog
import logging

# Configure once at app startup
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger("llm")

def call_with_structlog(prompt: str, user_id: Optional[str] = None) -> str:
    """Same logging, but via structlog."""
    start = time.monotonic()
    prompt_hash = hash_prompt(prompt)
    _, pii_found = scrub_pii(prompt)

    bound = log.bind(prompt_hash=prompt_hash, user_id=user_id)

    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.monotonic() - start) * 1000
        text = response.content[0].text if response.content else ''

        bound.info(
            "llm_request",
            model="claude-3-5-haiku-20241022",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=round(latency_ms, 2),
            response_preview=text[:200],
            pii_detected=pii_found,
        )
        return text

    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        bound.error(
            "llm_request_failed",
            error=type(e).__name__,
            latency_ms=round(latency_ms, 2),
            pii_detected=pii_found,
        )
        raise
```

**ما يضيفه structlog على نهج JSONL اليدوي:**

| Feature | Manual JSONL | structlog |
|---|---|---|
| المُخرَج المُهيكل | Yes | Yes |
| ترشيح مستوى السجل | Manual | Built-in |
| ربط السياق (bind لكل طلب) | Manual | bind() |
| معالِجات قابلة للتوصيل | Manual | Built-in pipeline |
| دعم الاختبار | Manual | capture_logs() fixture |
| دعم async | Manual | Built-in |

> **نقلة في المنظور:** يراجع مهندس منصّة طلب الدمج (PR) لديك فيقول: "عندنا أصلًا سجلّات تطبيق تذهب إلى CloudWatch. لماذا نضيف مكتبة تسجيل أخرى؟ ألا يمكننا فقط استخدام print() مع json.dumps()؟" متى تصمد هذه الحجة، ومتى تنهار مع توسّع النظام؟

---

## التسليم

**المُخرَج (Artifact):** `outputs/skill-llm-request-logger.md`

يُنتج هذا الدرس صنف `LLMRequestLogger` ومُنظِّف PII يمكنك إدراجه في أي خدمة Python. يكتب الـ logger بصيغة JSONL تعمل مع أي مُجمِّع سجلّات. ونمط سجل الأخطاء (الـ prompt الكامل عند الفشل فقط) هو النهج الآمن إنتاجيًا للفرق ذات متطلبات الامتثال (compliance).

انسخ `code/main.py` إلى مشروعك. اضبط `log_path` على مسار يراقبه ناقل السجلّات (log shipper) لديك. واضبط `error_log_path` على مسار ذي وصول مقيّد وسياسة احتفاظ قصيرة (7-30 يومًا، لا نفس سجلّاتك الرئيسية).

---

## التقييم

**التحقق 1: الـ PII لا يظهر في السجل الرئيسي**

بعد تشغيل `call_with_logging` بـ prompt يحتوي عنوان بريد إلكتروني، تحقّق من أن السجل الرئيسي لا يحتوي على البريد:

```bash
grep -c '@' llm_requests.jsonl   # should be 0
grep 'EMAIL' llm_requests.jsonl  # should show [EMAIL] placeholder
```

**التحقق 2: الـ prompt الكامل يظهر في سجل الأخطاء عند الفشل**

افتعل فشلًا (مثلًا، مرّر اسم نموذج غير صالح). تحقّق من أن:
- `llm_requests.jsonl` يحتوي على `"level":"error"` و`"error":"..."` لكن ليس الـ prompt الكامل
- `llm_errors.jsonl` يحتوي على نص الـ prompt الكامل بجانب الخطأ

**التحقق 3: الـ prompt نفسه يُنتج الـ hash نفسه**

```python
h1 = hash_prompt("What is the capital of France?")
h2 = hash_prompt("What is the capital of France?")
assert h1 == h2, "Hash must be deterministic"
```

**التحقق 4: تكلفة الـ tokens مرئية**

حلّل سجل JSONL واجمع `input_tokens` و`output_tokens` عبر كل الإدخالات. هذا أساس درس محاسبة التكلفة (L06). إذا استطعت جمع الـ tokens من السجلّات، استطعت بناء لوحات التكلفة.

```bash
jq -s '[.[].input_tokens] | add' llm_requests.jsonl
jq -s '[.[].output_tokens] | add' llm_requests.jsonl
```
