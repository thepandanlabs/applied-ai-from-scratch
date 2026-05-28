# خطط الاحتياط (Fallbacks) وتجاوز فشل النموذج (Model Failover)

> المستخدمون يتحمّلون البطء، لكنهم لا يتحمّلون الانقطاع.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** دروس المرحلة 06 من 05 إلى 07 (Docker، الإعدادات، المرونة)
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- بناء `FallbackChain` يجرّب النماذج بالترتيب مع مهلة زمنية (timeout) لكل نموذج
- التمييز بين تجاوز الفشل المبني على المهلة (timeout) والمبني على الخطأ (error)
- إعداد سلسلة احتياطية (fallback chain) بحيث يكون Claude هو الأساسي وOpenAI هو الثانوي
- تنفيذ استجابة مخزّنة (cached response) كملاذ أخير قبل رسالة التدهور (degradation)
- توضيح المفاضلات بين التكلفة والجودة لكل طبقة احتياطية

---

## المشكلة

نموذج الذكاء الاصطناعي الأساسي لديك غير متاح. ربما يمرّ Anthropic API بحادثة تشغيلية. ربما بلغ حسابك حدّ المعدّل (rate limit) والفرصة التالية لإرسال طلب بعد 20 دقيقة. ربما يستجيب النموذج لكنه يستغرق 45 ثانية لكل طلب، وهو ما يعني عمليًا أنه غير متاح لمنتج موجّه للمستخدم.

الاستجابة الساذجة هي إرجاع HTTP 500 والأمل أن يحاول المستخدمون مرة أخرى. في منتج موجّه للمستخدم، هذا كارثي: المنافس الذي تعمل خدمته يكسب كل مستخدم اصطدم بخطأ 500 لديك. وفي أداة داخلية، يعني هذا أن المهندسين يفقدون ثقتهم في ميزات الذكاء الاصطناعي ويتجاوزونها. في كلتا الحالتين، تكون قد دربت مستخدميك على أن الذكاء الاصطناعي غير موثوق.

الاستجابة الإنتاجية هي سلسلة احتياطية (fallback chain): يفشل النموذج الأساسي، جرّب النموذج الثانوي. يفشل النموذج الثانوي، جرّب استجابة مخزّنة من طلب ناجح سابق على الاستعلام نفسه أو على استعلام مشابه. لا تتوفر استجابة مخزّنة، أرجع رسالة تدهور رشيقة (graceful degradation) تشرح الموقف وتخبر المستخدم بما يفعله. في كل طبقة يحصل المستخدم على استجابة. الجودة تتراجع، لكن الخدمة لا تصمت أبدًا.

---

## المفهوم

### السلسلة الاحتياطية (The Fallback Chain)

```
User Request
     |
     v
[1] Primary: Claude (claude-3-5-haiku-20241022)
     |  timeout=10s; errors: network, 5xx, 429
     v (on failure or timeout)
[2] Secondary: OpenAI (gpt-4o-mini)
     |  timeout=15s; errors: network, 5xx, 429
     v (on failure or timeout)
[3] Cache: Return a cached response if one exists for this query (or similar)
     |  cache hit: return immediately; cache miss: continue
     v (on cache miss)
[4] Degradation: Return a static message explaining the outage
     |  always succeeds; always returns something
     v
Response to User
```

لكل طبقة مهلة زمنية (timeout) خاصة بها. يحصل النموذج الأساسي على أقصر مهلة لأنه الأسرع. وقد يحصل الثانوي على مهلة أطول لأنه هو الاحتياط، وتوقعات زمن الاستجابة (latency) قد تأثرت بالفعل. أما طبقتا الذاكرة المؤقتة (cache) والتدهور فهما لحظيتان.

### نوعان من تجاوز الفشل (Failover)

ليست كل الإخفاقات يجب أن تطلق الانتقال إلى الاحتياط. فهم هذا التمييز هو ما يحدد متى نتخطى الطبقات.

```
TIMEOUT-BASED FAILOVER                ERROR-BASED FAILOVER
-----------------------------         -----------------------------
Primary takes > 10s                   Primary returns 500 / 503
  -> try secondary                      -> try secondary

Primary takes > 10s                   Primary returns 429 (rate limited)
  -> secondary also slow                 -> try secondary (different
  -> try cache                             provider, different limit)
  -> degrade

SKIP SECONDARY WHEN:                  NEVER SKIP TO DEGRADE FOR:
  - 401 (auth error; secondary        - Network timeout
    likely has same key issue)         - 503 (server unavailable)
  - 400 (bad request; same            - 429 (rate limited)
    request will fail everywhere)
```

### المفاضلات بين التكلفة والجودة

| الطبقة | زمن الاستجابة | الجودة | التكلفة |
|------|---------|---------|------|
| Claude (الأساسي) | ~2-5s | الأعلى لمعظم المهام | أقل لكل token |
| GPT-4o-mini (الثانوي) | ~3-8s | جيدة؛ بأسلوب مختلف قليلًا | مشابهة لكل token |
| الاستجابة المخزّنة (cached) | <10ms | مماثلة لوقت توليدها | مجانية |
| رسالة التدهور (degradation) | <1ms | لا شيء (نص ثابت) | مجانية |

عادةً يكون النموذج الثانوي أغلى أو أبطأ من الأساسي. اللجوء إليه أفضل دائمًا من إرجاع خطأ، لكن ينبغي أن تتعقّب معدّل اللجوء إلى الاحتياط (fallback rate) كمقياس. إن كنت تلجأ إلى الاحتياط في أكثر من 1-2% من الطلبات، فأصلِح الأساسي لا الاحتياطي.

---

## البناء

### الخطوة 1: صنف FallbackChain

```python
import time
import hashlib
from typing import Any
from dataclasses import dataclass, field


@dataclass
class ModelConfig:
    """Configuration for a single model in the fallback chain."""
    provider: str          # "anthropic" or "openai"
    model: str             # model ID
    timeout: float         # seconds before trying the next tier
    max_tokens: int = 1024


class FallbackChain:
    """
    Tries models in priority order until one succeeds or all fail.

    Tiers:
      1+ model configs (tried in order)
      Last-resort: simple in-memory response cache
      Final fallback: static degradation message
    """

    def __init__(
        self,
        models: list[ModelConfig],
        degradation_message: str = (
            "The AI service is temporarily unavailable. "
            "Please try again in a few minutes."
        ),
        cache_ttl: float = 300.0,  # seconds
    ):
        self.models = models
        self.degradation_message = degradation_message
        self.cache_ttl = cache_ttl
        self._cache: dict[str, dict] = {}  # {cache_key: {text, timestamp}}
        self._stats = {"primary": 0, "fallback": 0, "cache": 0, "degraded": 0}
```

### الخطوة 2: مفتاح الذاكرة المؤقتة والبحث فيها

```python
    def _cache_key(self, prompt: str) -> str:
        """SHA-256 hash of the prompt. Identical prompts share a cache entry."""
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def _get_from_cache(self, prompt: str) -> str | None:
        """Return cached response if it exists and has not expired."""
        key = self._cache_key(prompt)
        entry = self._cache.get(key)
        if entry and (time.time() - entry["timestamp"]) < self.cache_ttl:
            return entry["text"]
        return None

    def _put_in_cache(self, prompt: str, text: str) -> None:
        """Cache a successful response with the current timestamp."""
        key = self._cache_key(prompt)
        self._cache[key] = {"text": text, "timestamp": time.time()}
```

### الخطوة 3: استدعاء كل مزوّد مع مهلة زمنية

```python
import signal

class TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError("Model call timed out")


def call_with_timeout(fn, timeout: float) -> Any:
    """
    Call fn and raise TimeoutError if it takes longer than timeout seconds.
    Uses POSIX signals (Unix only). For cross-platform use, run in a thread.
    """
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(int(timeout))
    try:
        return fn()
    finally:
        signal.alarm(0)  # cancel the alarm
```

### الخطوة 4: دالة التوليد generate

```python
    def generate(self, prompt: str) -> dict:
        """
        Try each model tier in order. Fall back to cache, then to a
        degradation message. Always returns a dict with 'text' and 'tier'.
        """
        for i, model_config in enumerate(self.models):
            try:
                start = time.time()
                text = call_with_timeout(
                    lambda: self._call_model(model_config, prompt),
                    timeout=model_config.timeout,
                )
                elapsed = time.time() - start

                self._put_in_cache(prompt, text)
                tier = "primary" if i == 0 else "fallback"
                self._stats[tier] += 1

                return {
                    "text": text,
                    "tier": tier,
                    "model": model_config.model,
                    "latency_seconds": elapsed,
                }

            except Exception as e:
                print(f"[tier {i+1}: {model_config.model}] failed: {e}")
                continue  # try next tier

        # No model succeeded: try cache
        cached = self._get_from_cache(prompt)
        if cached:
            self._stats["cache"] += 1
            return {
                "text": cached,
                "tier": "cache",
                "model": "cache",
                "latency_seconds": 0.0,
            }

        # Final fallback: degradation message
        self._stats["degraded"] += 1
        return {
            "text": self.degradation_message,
            "tier": "degraded",
            "model": "none",
            "latency_seconds": 0.0,
        }
```

> **اختبار من الواقع:** ينظر مديرك التقني (CTO) إلى السلسلة الاحتياطية ويقول: "إذا لجأنا إلى GPT-4o-mini حين يتعطل Claude، فنحن ندفع لـOpenAI مقابل طلبات نرسلها عادةً إلى Anthropic. لماذا ندفع لمزوّدَين معًا فقط من أجل تجاوز فشل قد يحدث مرة واحدة في الشهر؟" ما الحجة التكلفية للحفاظ على علاقة مع النموذج الثانوي؟

### الخطوة 5: مُستدعي النموذج

```python
    def _call_model(self, config: ModelConfig, prompt: str) -> str:
        """Route the call to the appropriate provider SDK."""
        if config.provider == "anthropic":
            return self._call_anthropic(config, prompt)
        elif config.provider == "openai":
            return self._call_openai(config, prompt)
        else:
            raise ValueError(f"Unknown provider: {config.provider}")

    def _call_anthropic(self, config: ModelConfig, prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    def _call_openai(self, config: ModelConfig, prompt: str) -> str:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model=config.model,
            max_tokens=config.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
```

---

## الاستخدام

اربط `FallbackChain` بخدمة FastAPI واعرض معلومة الطبقة (tier) في الاستجابة كي يعرف المستدعون أي نموذج خدمهم:

```python
from fastapi import FastAPI
from settings import get_settings
from fallback_chain import FallbackChain, ModelConfig

app = FastAPI()
settings = get_settings()

chain = FallbackChain(
    models=[
        ModelConfig(
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            timeout=10.0,
        ),
        ModelConfig(
            provider="openai",
            model="gpt-4o-mini",
            timeout=15.0,
        ),
    ],
    degradation_message=(
        "Our AI assistant is temporarily unavailable. "
        "Please try again in a few minutes or contact support."
    ),
    cache_ttl=300.0,
)


@app.post("/generate")
def generate(prompt: str):
    result = chain.generate(prompt)
    return {
        "text": result["text"],
        "model": result["model"],
        "tier": result["tier"],       # primary / fallback / cache / degraded
        "latency": result["latency_seconds"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "chain_stats": chain.stats}
```

حقل `tier` في الاستجابة هو إشارة تشغيلية. إذا بدأ العملاء بتسجيله، فبإمكان فريق العمليات لديك أن يرى متى يرتفع معدّل اللجوء إلى الاحتياط (fallback rate) قبل أن يفتح مستخدمٌ تذكرة دعم.

> **نقلة في المنظور:** يحاجج زميل بأن عرض `tier` في استجابة الـAPI خطأ لأن "المستخدمين لا ينبغي أن يعرفوا أي نموذج أجاب على سؤالهم -- فقد يجعلهم ذلك يفقدون الثقة في الاحتياط." ما الحجة المضادة لصالح الشفافية، ومن الذي ينبغي أن يرى معلومة الطبقة حتى لو لم يرها المستخدمون النهائيون؟

---

## التسليم

المنتَج القابل لإعادة الاستخدام في هذا الدرس هو `outputs/skill-model-fallback-chain.md`: قالب `FallbackChain` بنمط الطبقات الأربع والمقاييس التشغيلية التي ينبغي تعقّبها. أسقطه في أي خدمة تستدعي نموذج ذكاء اصطناعي.

لاستخدامه:
1. انسخ `code/main.py` (أو استخرج صنف `FallbackChain`) إلى خدمتك.
2. اضبط قائمة `models` بمزوّديك الأساسي والثانوي.
3. عيّن `cache_ttl` بناءً على المدة التي تبقى فيها الاستجابات صالحة لحالة استخدامك (محتوى ثابت: ساعات؛ محتوى مخصّص: أقصر أو صفر).
4. في طبقة الـAPI، سجّل حقل `tier` في كل استجابة. أطلق تنبيهًا حين يكون `fallback_rate > 0.02` (لجوء 2% من الطلبات إلى الاحتياط يشير إلى مشكلة في النموذج الأساسي).

---

## التقييم

**الفحص 1: تجاوز الفشل يُطلَق عند انتهاء المهلة (timeout).**
اضبط مهلة النموذج الأساسي على 0.001 ثانية. ينبغي أن يسقط كل طلب إلى النموذج الثانوي. تحقّق من أن `result["tier"] == "fallback"`.

```python
chain = FallbackChain(
    models=[
        ModelConfig(provider="anthropic", model="claude-3-5-haiku-20241022", timeout=0.001),
        ModelConfig(provider="openai", model="gpt-4o-mini", timeout=15.0),
    ]
)
result = chain.generate("Hello")
assert result["tier"] == "fallback", f"Expected fallback, got {result['tier']}"
```

**الفحص 2: إصابة الذاكرة المؤقتة (cache hit) عند تكرار الموجّه.**
أرسل الموجّه (prompt) نفسه مرتين. ينبغي أن يُرجِع الاستدعاء الثاني `tier="cache"` بزمن استجابة شبه معدوم.

```python
result1 = chain.generate("What is 2+2?")
result2 = chain.generate("What is 2+2?")
assert result2["tier"] == "cache"
assert result2["latency_seconds"] < 0.01
```

**الفحص 3: رسالة التدهور كملاذ أخير.**
اضبط مهلات كل النماذج على 0.001 ثانية وامسح الذاكرة المؤقتة. تفشل كل الطبقات. ينبغي أن تكون النتيجة `tier="degraded"` مع رسالة التدهور الثابتة.

**الفحص 4: مقياس معدّل اللجوء إلى الاحتياط (fallback rate).**
شغّل 100 طلب عبر السلسلة بنموذج أساسي معطّل (timeout=0.001). افحص `chain.stats`. ينبغي أن يكون عدد `fallback` نحو 100، وعدد `primary` صفرًا.

```python
for _ in range(100):
    chain.generate("test prompt")
assert chain.stats["primary"] == 0
assert chain.stats["fallback"] + chain.stats["cache"] + chain.stats["degraded"] == 100
```
