# إدارة الإعدادات والأسرار (Config and Secrets)

> الخدمة التي تقرأ إعدادًا سيئًا عند بدء التشغيل تخبرك به فورًا. أما الخدمة التي تقرأ إعدادًا سيئًا وقت الطلب فتجعلك تكتشفه الساعة الثانية فجرًا.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** درس المرحلة 06 رقم 05 (صورة Docker)، أساسيات Pydantic
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- تنفيذ صنف `Settings` مُنمَّط (typed) باستخدام pydantic-settings يحمّل من متغيرات البيئة بقيم افتراضية
- شرح ترتيب حلّ الإعدادات ثلاثي الطبقات ولماذا يوجد
- التمييز بين الإعدادات (غير سرّية، تحت إدارة الإصدار) والأسرار (مفاتيح API، رموز، لا تُلتزَم أبدًا)
- دمج صنف `Settings` في خدمة FastAPI مع تحقّق فوري عند بدء التشغيل (fail-fast)
- تسمية ثلاثة خيارات لمخازن الأسرار ووصف متى تلجأ لكل منها

---

## المشكلة

خدمة AI إنتاجية لديها على الأقل دزينة من قيم الإعداد: اسم النموذج، والحدّ الأقصى للرموز، والحرارة (temperature)، والمهلة (timeout)، وعدد المحاولات، وحدّ المعدّل (rate limit)، ومنفذ الخدمة، ومستوى السجلّ، ومفتاح الـ API. أين تعيش هذه القيم؟

تنتهي معظم الفرق بمزيج من الثوابت المثبّتة في الكود (hardcoded)، وقراءات متغيرات بيئة متناثرة عبر ستة ملفات، وإعداد YAML يعمل في الـ staging فقط، وملف `.env` لا أحد يتذكّر صيغته الصحيحة تمامًا. حين تستخدم خدمة الإنتاج نموذجًا افتراضيًا بصمت لأن متغير بيئة staging لم يُضبط في الإنتاج، يظل التدهور غير مرئي حتى يشتكي مستخدم من أن الاستجابات خاطئة. وحين تسبّب مهلة مضبوطة خطأً تعليق كل طلب لمدة 30 ثانية، لا يشتبه أحد فورًا في طبقة الإعداد.

المشكلة الأعمق أن الإعداد يُتحقَّق منه في الوقت الخاطئ. في معظم قواعد الكود، القيمة المطلوبة المفقودة لا تخطئ إلا حين يُنفَّذ مسار الكود الذي يقرأها. قد لا يظهر `ANTHROPIC_API_KEY` المفقود إلا عند أول طلب مستخدم حقيقي الساعة الثانية ظهرًا يوم الثلاثاء. وقد لا تفشل قيمة `MAX_TOKENS` المضبوطة على نصّ بدل عدد صحيح إلا في الطلبات التي تتجاوز الحدّ الافتراضي للنموذج. التحقّق الفوري عند بدء التشغيل (fail-fast) يقضي على هذه الفئة كاملةً من مفاجآت الإنتاج: إما أن تبدأ الخدمة مضبوطة بشكل صحيح، أو ترفض البدء كليًا.

---

## المفهوم

### ترتيب حلّ الإعدادات ثلاثي الطبقات

كل خدمة جيّدة البنية لديها إعداد يتدفّق من ثلاثة مصادر، كل طبقة قادرة على تجاوز الطبقة التي تحتها.

```
Tier 3 (highest priority): Environment Variables
    ANTHROPIC_API_KEY=sk-ant-...
    LOG_LEVEL=debug

          overrides
              |
              v

Tier 2 (medium priority): Config File (YAML or TOML)
    model: claude-3-5-haiku-20241022
    max_tokens: 1024
    timeout_seconds: 30

          overrides
              |
              v

Tier 1 (lowest priority): Defaults in Code
    model = "claude-3-5-haiku-20241022"
    max_tokens = 1024
    timeout_seconds = 30
    log_level = "info"
```

يوجد هذا الترتيب لأن:
- القيم الافتراضية في الكود تضمن أن الخدمة تعمل دون أي إعداد خارجي (مفيد للاختبار والتطوير المحلي).
- ملف الإعداد يتيح لك إدارة إصدار الإعدادات غير السرّية لكل بيئة (متغيّرات النموذج في staging مقابل الإنتاج، ومهلات مختلفة).
- متغيرات البيئة تتيح للمنسّقات (Kubernetes، ECS، Docker) تجاوز قيم محدّدة دون لمس الملفات، وتوفّر الآلية الآمنة الوحيدة للأسرار.

### الإعدادات مقابل الأسرار

ليس كل إعداد متساويًا. التمييز يحدّد أين تُخزَّن القيم ومن يستطيع رؤيتها.

```
CONFIG (non-secret)                    SECRETS
- Safe to commit to version control    - Never commit to version control
- Safe to bake into Docker image ENV   - Injected at runtime only
- Readable by anyone on the team       - Access-controlled; audited
                                       
Examples:                              Examples:
  model name                             ANTHROPIC_API_KEY
  max_tokens                             OPENAI_API_KEY
  log level                              DATABASE_URL (contains password)
  port                                   JWT_SECRET
  timeout                                STRIPE_SECRET_KEY
  retry count
```

### مخازن الأسرار: متى تلجأ لكل منها

| المخزن | متى تستخدمه |
|-------|----------------|
| متغيرات البيئة + أسرار CI | الافتراضي لمعظم الفرق. بسيط، ومدعوم في كل مكان. |
| أسرار Docker | نشر Docker Swarm متعدّد الخدمات. تُركَّب الأسرار كملفات، لا كمتغيرات بيئة. |
| AWS Secrets Manager | خدمات أصيلة في AWS تحتاج تدويرًا (rotation)، أو سجلّ تدقيق (audit trail)، أو بيانات اعتماد ديناميكية. |
| HashiCorp Vault | متعدّد السحابات أو محلي (on-prem)؛ سياسات دقيقة الحبيبات؛ بيانات اعتماد قاعدة بيانات ديناميكية. |

ابدأ بمتغيرات البيئة. واِلجأ لمخزن أسرار مخصّص حين تحتاج تدويرًا، أو سجلات تدقيق، أو سياسات وصول لا تستطيع متغيرات البيئة توفيرها.

---

## البناء

### الخطوة 1: تثبيت pydantic-settings

```bash
uv add pydantic-settings
# or: pip install pydantic-settings
```

تُوسِّع `pydantic-settings` Pydantic لقراءة قيم الحقول من متغيرات البيئة تلقائيًا. اسم كل حقل يُطابَق بمتغير بيئة كبير الحروف بالاسم نفسه.

### الخطوة 2: صنف Settings

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Typed configuration for the AI service.

    Resolution order (highest to lowest priority):
      1. Environment variables (e.g., ANTHROPIC_API_KEY=sk-...)
      2. .env file (if env_file is set and the file exists)
      3. Default values defined below

    Validation runs at instantiation time (startup), not at request time.
    A missing required field or a wrong type raises ValidationError immediately.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- SECRETS (required, no defaults, must be injected via environment) ---
    anthropic_api_key: str = Field(..., description="Anthropic API key")

    # --- MODEL CONFIG ---
    model: str = Field(
        default="claude-3-5-haiku-20241022",
        description="Claude model ID to use for generation",
    )
    max_tokens: int = Field(
        default=1024,
        ge=1,
        le=8192,
        description="Maximum tokens in the model response",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Sampling temperature (0.0 = deterministic)",
    )

    # --- SERVICE CONFIG ---
    port: int = Field(default=8000, ge=1024, le=65535)
    log_level: str = Field(default="info")
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
```

ثلاثة أمور تستحقّ الملاحظة:
1. `anthropic_api_key` ليس له قيمة افتراضية (`...` هي علامة Pydantic لـ "مطلوب"). ترفض الخدمة البدء إذا غاب هذا.
2. الحقول العددية لها قيود `ge` (أكبر من أو يساوي) و`le` (أصغر من أو يساوي). نصّ مثل `"fast"` لـ `max_tokens` يثير `ValidationError` عند بدء التشغيل، لا وقت التشغيل.
3. `SettingsConfigDict(env_file=".env")` يتيح التطوير المحلي بملف `.env` دون لمس متغيرات البيئة. في الـ CI والإنتاج، لا يوجد ملف `.env` وتتولّى متغيرات البيئة الأمر.

### الخطوة 3: تحميل Settings مرة واحدة

```python
# settings.py
from functools import lru_cache

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Load settings once and cache the result.
    Calling get_settings() multiple times returns the same object.
    Use lru_cache so the settings are only parsed once per process.
    """
    return Settings()
```

`lru_cache` يضمن قراءة البيئة والتحقّق منها مرة واحدة بالضبط. بدونه، كل نداء لـ `get_settings()` يعيد قراءة البيئة والتحقّق منها، ما يهدر الوقت، والأهمّ أنه قد يسبّب عللًا خفيّة إذا تغيّرت متغيرات البيئة في منتصف العملية (وهو ما لا ينبغي حدوثه، لكنه يحدث أحيانًا في الاختبارات).

### الخطوة 4: التحقّق عند بدء التشغيل

```python
# main.py
import sys
from pydantic import ValidationError
from settings import get_settings

try:
    settings = get_settings()
except ValidationError as e:
    print(f"Configuration error - service will not start:\n{e}", file=sys.stderr)
    sys.exit(1)
```

هذا هو الـ fail-fast. تخرج العملية بالرمز 1 برسالة خطأ واضحة قبل ربط منفذ، وقبل تحميل أوزان النموذج، وقبل قبول أي اتصالات. وسيسجّل Kubernetes وDocker الخطأ ويبلّغان عن فشل الحاوية بدل "تعمل لكنها معطّلة".

> **اختبار من الواقع:** يسألك فريق العمليات: "إذا التقط التحقّق من الإعدادات مفتاح API مفقودًا عند بدء التشغيل، فكيف يفيدنا ذلك مقارنةً ببدء الخدمة ثم فشلها عند أول طلب حقيقي؟" ما الفرق التشغيلي الملموس، ولماذا يهمّ أكثر أثناء طرح نشر (deployment rollout)؟

---

## الاستخدام

بوجود صنف `Settings`، يربط حقن الاعتماديات (dependency injection) في FastAPI الإعداد بمعالجات مساراتك بنظافة:

```python
from fastapi import FastAPI, Depends
import anthropic
from settings import Settings, get_settings

app = FastAPI()


def get_client(settings: Settings = Depends(get_settings)) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


@app.post("/generate")
def generate(
    prompt: str,
    settings: Settings = Depends(get_settings),
    client: anthropic.Anthropic = Depends(get_client),
):
    msg = client.messages.create(
        model=settings.model,
        max_tokens=settings.max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return {"text": msg.content[0].text}
```

يتلقّى كل معالج مسار كائن `Settings` المُتحقَّق منه نفسه. لا نداءات `os.environ.get()` متناثرة. ولا تحويل أنواع في منطق العمل. عقد الإعداد معرَّف مرة واحدة في `Settings` ومفروض قبل بدء الخدمة.

ما يقابله باستخدام `os.environ.get()` الخام (ما تبدو عليه معظم قواعد الكود فعلًا):

```python
# What NOT to do: scattered, untyped, unvalidated
model = os.environ.get("MODEL", "claude-3-5-haiku-20241022")
max_tokens = int(os.environ.get("MAX_TOKENS", "1024"))  # crashes if set to "fast"
api_key = os.environ.get("ANTHROPIC_API_KEY")  # None if missing, crashes at API call
timeout = os.environ.get("TIMEOUT_SECONDS", "30")  # string, not int; used wrong later
```

> **نقلة في المنظور:** يشير زميل إلى أن استخدام `Depends(get_settings)` في كل مسار متكرّر ويقترح تخزين `settings` كمتغير عام على مستوى الوحدة (module-level global) بدلًا من ذلك. ما المفاضلات، وفي أي موقف يسبّب نهج المتغير العام على مستوى الوحدة علّةً فعلًا؟

---

## التسليم

المخرَج القابل لإعادة الاستخدام لهذا الدرس هو `outputs/skill-config-secrets-pattern.md`: قالب صنف `Settings` ونمط الحلّ ثلاثي الطبقات الذي يمكنك إدراجه في أي خدمة AI جديدة بـ Python.

لاستخدامه:
1. انسخ `code/settings.py` إلى خدمتك.
2. أضف حقولك الخاصة بالخدمة متّبعًا نمط الإعدادات مقابل الأسرار.
3. أنشئ ملف `.env.example` (مُلتزَم) بقيم عنصر نائب (placeholder). أنشئ `.env` (لا يُلتزَم أبدًا، في `.gitignore`) للتطوير المحلي.
4. في `main.py`، نادِ `get_settings()` عند بدء التشغيل داخل كتلة `try/except ValidationError`.

---

## التقييم

**التحقق 1: التحقّق الفوري (fail-fast).**
ابدأ الخدمة بحقل مطلوب مفقود. ينبغي أن تخرج العملية فورًا برمز خروج غير صفري ورسالة خطأ واضحة تحدّد الحقل المفقود. ولا ينبغي أن تبدأ خادم ويب أو تقبل اتصالات.

```bash
unset ANTHROPIC_API_KEY
python main.py
# Expected: ValidationError on ANTHROPIC_API_KEY, exit code 1
```

**التحقق 2: التحقّق من النوع.**
اضبط حقلًا عدديًا على قيمة غير صالحة وتحقّق من أن بدء التشغيل يفشل بخطأ نوع، لا بانهيار وقت تشغيل لاحقًا.

```bash
MAX_TOKENS=not-a-number python main.py
# Expected: ValidationError on max_tokens, exit code 1
```

**التحقق 3: أسبقية التجاوز.**
اضبط قيمة في `.env` وتجاوزها بمتغير بيئة. ينبغي أن يفوز متغير البيئة.

```bash
echo "MODEL=claude-opus-4-5" > .env
MODEL=claude-3-5-haiku-20241022 python -c "from settings import get_settings; s = get_settings(); print(s.model)"
# Expected: claude-3-5-haiku-20241022  (env var wins over .env file)
```

**التحقق 4: لا أسرار تحت إدارة الإصدار.**
تحقّق من أن `.env` في `.gitignore` وأن `.env.example` بقيم عنصر نائب مُلتزَم بدلًا منه.

```bash
git status .env
# Expected: .env should not appear (it is gitignored)
cat .env.example
# Expected: ANTHROPIC_API_KEY=your-key-here (placeholder, not a real key)
```
