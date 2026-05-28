# مفاتيح الـ API ومزوّدو الخدمة ومشهد النماذج في 2026

> النموذج الذي تختاره هو مقايضة بين التكلفة والكُمون (latency) والقدرة، وليس قرارًا يتعلّق بالصحّة. معظم المهام تعمل بشكل جيد مع Haiku بتكلفة أقل بمقدار 20 مرة من Opus.

**النوع:** تعلّم
**اللغات:** Python
**المتطلبات:** 00-01 (بيئة التطوير)
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- تحميل مفاتيح الـ API بأمان باستخدام متغيرات البيئة (environment variables) و python-dotenv
- فهم مصفوفة طبقات النماذج لعام 2026 لكل من Claude و OpenAI و Gemini
- بناء فئة ModelConfig تلتقط بيانات المزوّد/النموذج/التكلفة الوصفية (metadata)
- اتخاذ قرارات اختيار نماذج واعية بالتكلفة لأنواع مهام مختلفة

---

## المشكلة

أنت تبني ميزة لتلخيص المستندات لشركة تقنية قانونية (legal tech). توصّلها بـ GPT-4o لأنه النموذج الذي تعرف أنه يعمل. تُطلَق الميزة، ويرتفع الاستخدام، وبعد ثلاثة أسابيع يسألك المدير التقني (CTO) عن سبب قفزة ميزانية الـ AI من 200$/شهريًا إلى 3,400$/شهريًا.

المشكلة ليست أن GPT-4o سيئ. المشكلة أن معظم مهام التلخيص لديك روتينية: استخراج التواريخ والأطراف والبنود الأساسية من قوالب العقود القياسية. نموذج يكلّف أقل بمقدار 20 مرة ويستجيب أسرع بثلاث مرات يتولّى 80% من تلك المهام دون أي فرق في الجودة. لقد اخترت الخيار باهظ الثمن افتراضيًا، لا عن تصميم.

هذا الدرس يغطّي أمرين يسهل الخطأ فيهما مبكرًا: إبقاء مفاتيح الـ API خارج كودك، وفهم مصفوفة طبقات النماذج بما يكفي لاتخاذ قرارات تكلفة/قدرة مدروسة منذ اليوم الأول.

---

## المفهوم

### إبقاء المفاتيح خارج الكود

مفتاح الـ API داخل الكود المصدري هو تسريب اعتماد (credential) ينتظر وقوعه. عندما ترفع (push) الكود إلى GitHub، تعثر عليه الماسحات الضوئية للمفاتيح خلال دقائق. النمط الصحيح يستخدم ثلاث طبقات:

```
WRONG:
  client = Anthropic(api_key="sk-ant-api03-abc123...")
  # ^ This is now in git history forever, even if you delete it later.

CORRECT (3-layer pattern):
  .env file          -->  ANTHROPIC_API_KEY=sk-ant-...  (in .gitignore)
     |
  os.environ         -->  loaded by python-dotenv at startup
     |
  client             -->  Anthropic()  (SDK reads from env automatically)
```

ملف `.env` يعيش فقط على جهازك وفي مدير الأسرار (secrets manager) الخاص بـ CI/CD لديك. ولا يدخل git أبدًا.

### مصفوفة طبقات النماذج لعام 2026

كل مزوّد رئيسي ينشر الآن عائلة نماذج من ثلاث طبقات: سريع/رخيص، ومتوازن، وقوي/باهظ. الأبعاد التي تهمّ عند الاختيار هي التكلفة (لكل مليون token)، والكُمون (latency، أي الزمن حتى أول token)، ونافذة السياق (context window)، وسقف القدرة.

```
FAST / CHEAP              BALANCED                  POWERFUL / EXPENSIVE
(routine tasks,           (most production          (complex reasoning,
 high volume)             workloads)                 long context, research)

Claude Haiku 3.5          Claude Sonnet 4           Claude Opus 4
~$0.80/1M in              ~$3/1M in                 ~$15/1M in
~$4/1M out                ~$15/1M out               ~$75/1M out
200K context              200K context              200K context

GPT-4o mini               GPT-4o                    o3
~$0.15/1M in              ~$2.50/1M in              ~$10/1M in
~$0.60/1M out             ~$10/1M out               ~$40/1M out
128K context              128K context              200K context

Gemini 2.0 Flash          Gemini 2.0 Pro            Gemini 2.0 Ultra
~$0.10/1M in              ~$1.25/1M in              ~$5/1M in
~$0.40/1M out             ~$5/1M out                ~$15/1M out
1M context                2M context                1M context

Open-weight (self-hosted via vLLM):
Llama 3.3 70B             Llama 3.1 405B            ---
$0 API cost               $0 API cost
(infra cost only)         (infra cost only)
```

ملاحظة: الأسعار تتغير كثيرًا. تعامل معها كمراجع تقريبية بالترتيب من حيث الحجم (order-of-magnitude)، لا كضمانات للفوترة. راجع صفحات تسعير المزوّدين للأسعار الحالية.

### قاعدة القرار التجريبية (Heuristic)

```
Is the task well-defined with a clear correct answer?
  YES --> Start with Fast/Cheap. Test it. Only upgrade if quality fails.
  NO  --> Is it a one-shot user interaction where quality matters?
            YES --> Balanced tier.
            NO  --> Is it complex multi-step reasoning or long document analysis?
                      YES --> Powerful tier or balanced with extended thinking.
                      NO  --> Re-examine whether you need AI at all.
```

معظم ميزات الـ AI الإنتاجية -- التصنيف، والاستخراج، والتلخيص، والتوجيه (routing) -- تعمل جيدًا على الطبقة السريعة/الرخيصة. أما الطبقة القوية فتستحق تكلفتها في: تركيب (synthesis) معلومات من مستندات متعددة، وتوليد كود لأنظمة معقدة، والكتابة الطويلة الدقيقة، والمهام التي تتطلب سياقًا بحجم 100K+ token.

---

## البناء

### الخطوة 1: إعداد تحميل المفاتيح

```bash
# Install python-dotenv
uv add python-dotenv

# Create .env (one time, never commit this)
touch .env
echo "ANTHROPIC_API_KEY=your-key-here" >> .env

# Add to .gitignore
echo ".env" >> .gitignore
```

```python
# key_loader.py
import os
from dotenv import load_dotenv

def load_api_keys() -> dict[str, str | None]:
    """
    Load API keys from environment variables.
    .env file is loaded first, then actual environment variables override.
    Returns a dict of provider -> key (None if not set).
    """
    load_dotenv()  # reads .env into os.environ (does not overwrite existing vars)

    keys = {
        "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
        "openai": os.environ.get("OPENAI_API_KEY"),
        "gemini": os.environ.get("GEMINI_API_KEY"),
    }

    for provider, key in keys.items():
        if key:
            masked = key[:8] + "..." + key[-4:]
            print(f"  {provider}: {masked}")
        else:
            print(f"  {provider}: NOT SET")

    return keys
```

### الخطوة 2: بناء فئة ModelConfig

```python
# model_config.py
from dataclasses import dataclass

@dataclass
class ModelConfig:
    provider: str           # "anthropic", "openai", "gemini", "vllm"
    model_id: str           # exact model string for the API call
    tier: str               # "fast", "balanced", "powerful"
    input_cost_per_1m: float    # USD per 1M input tokens
    output_cost_per_1m: float   # USD per 1M output tokens
    context_window: int     # max tokens (input + output)
    notes: str = ""

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Return estimated USD cost for a single call."""
        input_cost = (input_tokens / 1_000_000) * self.input_cost_per_1m
        output_cost = (output_tokens / 1_000_000) * self.output_cost_per_1m
        return input_cost + output_cost

# The 2026 catalog (approximate -- verify current pricing before committing to a budget)
MODEL_CATALOG: dict[str, ModelConfig] = {
    "claude-haiku": ModelConfig(
        provider="anthropic",
        model_id="claude-3-5-haiku-20241022",
        tier="fast",
        input_cost_per_1m=0.80,
        output_cost_per_1m=4.00,
        context_window=200_000,
        notes="Best for classification, extraction, high-volume tasks",
    ),
    "claude-sonnet": ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-5",
        tier="balanced",
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
        context_window=200_000,
        notes="Production workhorse for most AI features",
    ),
    "claude-opus": ModelConfig(
        provider="anthropic",
        model_id="claude-opus-4-5",
        tier="powerful",
        input_cost_per_1m=15.00,
        output_cost_per_1m=75.00,
        context_window=200_000,
        notes="Complex reasoning, long-form synthesis, research tasks",
    ),
    "gpt-4o-mini": ModelConfig(
        provider="openai",
        model_id="gpt-4o-mini",
        tier="fast",
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
        context_window=128_000,
        notes="OpenAI fast tier; very low cost",
    ),
    "gpt-4o": ModelConfig(
        provider="openai",
        model_id="gpt-4o",
        tier="balanced",
        input_cost_per_1m=2.50,
        output_cost_per_1m=10.00,
        context_window=128_000,
        notes="OpenAI production standard",
    ),
    "gemini-flash": ModelConfig(
        provider="gemini",
        model_id="gemini-2.0-flash",
        tier="fast",
        input_cost_per_1m=0.10,
        output_cost_per_1m=0.40,
        context_window=1_000_000,
        notes="Extremely fast and cheap; best for very long context at low cost",
    ),
}
```

### الخطوة 3: توضيح سلوك المفتاح المفقود

```python
# show what happens without a key set
import anthropic
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # simulate missing key

try:
    client = anthropic.Anthropic()  # SDK reads from env
    client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        messages=[{"role": "user", "content": "ping"}],
    )
except anthropic.AuthenticationError as e:
    print(f"AuthenticationError (expected): {e}")
except Exception as e:
    print(f"Error type: {type(e).__name__}: {e}")
```

> **اختبار من الواقع:** ميزة الـ AI الخاصة بفريقك يستخدمها 500 مستخدم مؤسسي يوميًا. كل طلب يرسل نحو 1,000 token مُدخَل ويستقبل نحو 300 token مُخرَج. يسألك مديرك: "هل يمكننا تقدير التكلفة الشهرية للـ AI؟" استعرض الحساب باستخدام الدالة ModelConfig.estimate_cost() لكل من claude-haiku و claude-sonnet. ما هو فرق التكلفة الشهرية، وهل يبرّر الطبقة التي تختارها؟

### الخطوة 4: بناء مُحدِّد واعٍ بالتكلفة

```python
def select_model(task_type: str, token_volume: str = "low") -> ModelConfig:
    """
    Simple rule-based model selector.
    In production, this logic lives in a config file, not hardcoded here.
    """
    ROUTING_TABLE = {
        # (task_type, token_volume) -> model key
        ("classification", "high"): "claude-haiku",
        ("classification", "low"): "claude-haiku",
        ("extraction", "high"): "claude-haiku",
        ("extraction", "low"): "claude-haiku",
        ("summarization", "high"): "claude-haiku",
        ("summarization", "low"): "claude-sonnet",
        ("generation", "high"): "claude-sonnet",
        ("generation", "low"): "claude-sonnet",
        ("reasoning", "high"): "claude-sonnet",
        ("reasoning", "low"): "claude-opus",
    }
    key = ROUTING_TABLE.get((task_type, token_volume), "claude-sonnet")
    return MODEL_CATALOG[key]

# Example usage
for task in ["classification", "summarization", "reasoning"]:
    config = select_model(task, "high")
    monthly_cost = config.estimate_cost(1000, 300) * 500 * 30
    print(f"{task:20} -> {config.model_id:35} ${monthly_cost:,.2f}/month")
```

---

## الاستخدام

يقرأ Anthropic SDK المتغيّر `ANTHROPIC_API_KEY` من البيئة تلقائيًا عندما تستدعي `Anthropic()` دون وسائط (arguments):

```python
import anthropic
from dotenv import load_dotenv

load_dotenv()  # load .env into os.environ

# No api_key= argument needed -- SDK reads from ANTHROPIC_API_KEY
client = anthropic.Anthropic()

# Create a message using the haiku model (fast tier)
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    messages=[{"role": "user", "content": "Classify this as POSITIVE, NEGATIVE, or NEUTRAL: 'The product works as described.'"}],
)

print(response.content[0].text)
print(f"Tokens used: {response.usage.input_tokens} in / {response.usage.output_tokens} out")
```

يرفع الـ SDK الاستثناء `anthropic.AuthenticationError` إذا كان المفتاح مفقودًا أو غير صالح، و `anthropic.RateLimitError` إذا تجاوزت حصة طبقتك (quota)، و `anthropic.APIConnectionError` لمشاكل الشبكة. التقط هذه تحديدًا بدلًا من استخدام `except Exception` مجرّد.

> **نقلة في المنظور:** الدالة `load_dotenv()` في python-dotenv تقرأ ملف `.env` فقط إذا لم يكن المتغيّر موجودًا بالفعل في `os.environ`. هذا يعني أن نفس الكود يعمل في ثلاث بيئات دون تعديل: التطوير المحلي (يقرأ من `.env`)، و CI/CD (يقرأ من أسرار خط الأنابيب (pipeline) المحقونة في متغيرات البيئة)، والإنتاج (يقرأ من أسرار المنصة مثل AWS Secrets Manager أو أسرار Kubernetes، والتي تُحقَن أيضًا كمتغيرات بيئة). الكود لا يتغير أبدًا -- بل يتغير مصدر متغيّر البيئة فقط.

---

## التسليم

المُخرَج (artifact) لهذا الدرس هو دليل قرار لاختيار النموذج.

انظر `outputs/prompt-model-selection-guide.md`.

---

## التقييم

إعداد إدارة المفاتيح واختيار النموذج لديك يكون جاهزًا للإنتاج عندما:

```bash
# 1. No keys in any Python file
grep -r "sk-ant\|sk-proj\|AIza" code/ outputs/ docs/
# Expected: no matches

# 2. .env is gitignored
grep -c "\.env" .gitignore
# Expected: 1 or more

# 3. Key loads correctly via dotenv
uv run python -c "
from dotenv import load_dotenv
import os
load_dotenv()
key = os.environ.get('ANTHROPIC_API_KEY', '')
print('Key present:', bool(key))
print('Key format OK:', key.startswith('sk-ant-') if key else False)
"

# 4. ModelConfig cost math is correct
uv run python -c "
from model_config import MODEL_CATALOG
haiku = MODEL_CATALOG['claude-haiku']
cost = haiku.estimate_cost(1000, 300)
print(f'1K in + 300 out with haiku: \${cost:.6f}')
assert cost < 0.01, 'Haiku cost estimate seems too high'
print('Cost estimate: OK')
"

# 5. Authentication error is raised cleanly when key is missing
uv run python -c "
import anthropic, os
os.environ.pop('ANTHROPIC_API_KEY', None)
try:
    anthropic.Anthropic().messages.create(model='claude-3-5-haiku-20241022', max_tokens=8, messages=[{'role':'user','content':'x'}])
    print('ERROR: should have raised')
except anthropic.AuthenticationError:
    print('OK: AuthenticationError raised as expected')
"
```
