# Few-Shot و Chain-of-Thought

> الـ chain-of-thought ينجح لأنه يجبر النموذج على إنفاق tokens على الاستدلال قبل الالتزام بإجابة.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** الدرس 01 (تشريح الطلب)، الدرس 02 (أساسيات الـ Prompt)، `pip install anthropic`
**الوقت:** ~60 دقيقة
**أهداف التعلّم:**
- تنفيذ الـ prompting بأساليب zero-shot و few-shot و chain-of-thought وملاحظة الفرق في جودة المخرجات
- شرح لماذا يحسّن CoT الاستدلال في المهام متعددة الخطوات
- بناء أمثلة few-shot باستخدام دور assistant في مصفوفة messages
- الجمع بين few-shot و CoT للمهام التي تتطلب اتساق الصيغة والاستدلال الدقيق معًا
- تحديد متى تساعد كل تقنية ومتى تفشل كل منها

---

## THE PROBLEM

تبني نظام فرز (triage) يصنّف تذاكر دعم العملاء حسب الخطورة: Critical، High، Medium، Low. يُصيب prompt من نوع zero-shot في 70% من الوقت. أنت بحاجة إلى 95%+. تضيف أمثلة إلى الـ prompt فتصل إلى 85%. لا تزال بعيدًا. تجرّب أن تطلب من النموذج أن "يفكر بعناية" فلا يتغير شيء.

المشكلة أنك تطبّق تقنيات دون فهم الآلية. ليست few-shot و chain-of-thought تعاويذ سحرية. هما تعملان بتغيير ما يفعله النموذج بقدرته الحاسوبية (compute) قبل توليد الإجابة. معرفة سبب نجاحهما تخبرك متى تستخدمهما، وكيف تجمع بينهما، ولماذا يفشلان أحيانًا.

---

## THE CONCEPT

### ثلاثة أشكال للـ Prompt

الفرق البنيوي بين zero-shot و few-shot و CoT:

```
ZERO-SHOT
┌──────────────────────────────────────────────────────┐
│ [Task instruction]                                   │
│ [Input]                                              │
│ -> Model generates answer directly                   │
└──────────────────────────────────────────────────────┘

FEW-SHOT
┌──────────────────────────────────────────────────────┐
│ [Task instruction]                                   │
│ [Example input 1] -> [Example output 1]              │
│ [Example input 2] -> [Example output 2]              │
│ [Example input 3] -> [Example output 3]              │
│ [Real input]                                         │
│ -> Model infers pattern and applies it               │
└──────────────────────────────────────────────────────┘

CHAIN-OF-THOUGHT
┌──────────────────────────────────────────────────────┐
│ [Task instruction + "reason step by step"]           │
│ [Input]                                              │
│ -> Model generates: reasoning... -> answer           │
└──────────────────────────────────────────────────────┘

FEW-SHOT + COT (combined)
┌──────────────────────────────────────────────────────┐
│ [Task instruction]                                   │
│ [Example input 1] -> [Reasoning 1] -> [Answer 1]     │
│ [Example input 2] -> [Reasoning 2] -> [Answer 2]     │
│ [Real input]                                         │
│ -> Model generates: reasoning... -> answer           │
└──────────────────────────────────────────────────────┘
```

### لماذا ينجح Few-Shot

تتنبأ النماذج اللغوية بالـ token التالي اعتمادًا على الأنماط في الـ context. حين تُضمّن أمثلة في الـ prompt، يرى النموذج نمط مدخل-مخرج ويستخدمه كقالب. تنقل الأمثلة الصيغة والمفردات وأسلوب الاستدلال بدقة أكبر من الوصف وحده.

يكون few-shot أكثر فائدة حين: تكون صيغة المخرجات غير قياسية، أو تتطلب المهمة أسلوبًا أو مفردات محددة، أو يُنتج zero-shot بنية غير متسقة.

يفشل few-shot حين: لا تغطي أمثلتك توزيع المدخلات الحقيقية، أو تكون الأمثلة متشابهة جدًا فيما بينها، أو تتطلب المهمة استدلالًا لا يمكن عرضه بالأمثلة وحدها.

### لماذا ينجح Chain-of-Thought

هذه هي الآلية، لا السحر: ينجح CoT لأن الـ tokens هي قدرة النموذج الحاسوبية. يولّد النموذج token واحدًا في كل مرة. كل token يولّده يصبح جزءًا من "ورقة المسوّدة" (scratchpad) لديه. بتوليد خطوات الاستدلال قبل token الإجابة، يصبح لدى النموذج مزيد من المعلومات الوسيطة المتاحة حين يلتزم بالإجابة النهائية.

فكّر فيه على أنه إجبار للنموذج على إظهار خطوات حلّه. الطالب الذي يكتب خطوات مسألة الرياضيات أقل عرضة لخطأ حسابي من الذي يحاول الاحتفاظ بكل شيء في ذهنه وكتابة الإجابة النهائية فقط. الآلية نفسها.

يكون CoT أكثر فائدة حين: تتطلب المهمة استدلالًا متعدد الخطوات، أو حسابات، أو موازنة بين عوامل متعددة. يفشل CoT حين: تكون المهمة استرجاعًا (zero-shot أو few-shot أسرع وأرخص)، أو حين تصبح سلسلة الاستدلال نفسها مشوّشة فتقود النموذج بعيدًا عن الإجابة الصحيحة.

---

## BUILD IT

### ثلاث تجارب

شغّلها بالترتيب. كل تجربة تستخدم المهمة نفسها لكن تغيّر أسلوب الـ prompting.

**المهمة:** تصنيف خطورة تذاكر دعم العملاء.

```python
import anthropic
import json

client = anthropic.Anthropic()

# Test tickets covering the full severity range
TEST_TICKETS = [
    "My account was charged twice for the same order. I need a refund.",
    "The entire payment service is down. No transactions are going through.",
    "How do I change my billing address?",
    "Users in the EU region cannot log in. This has been broken for 30 minutes.",
    "The font in the mobile app looks slightly different than the web version.",
]

SEVERITY_LEVELS = ["Critical", "High", "Medium", "Low"]
```

**Experiment 1: Zero-shot baseline.**

```python
ZERO_SHOT_PROMPT = """Classify the severity of this customer support ticket.
Severity levels: Critical, High, Medium, Low.

Output only the severity level. No explanation.

Ticket: {ticket}"""

def classify_zero_shot(ticket: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        messages=[{
            "role": "user",
            "content": ZERO_SHOT_PROMPT.format(ticket=ticket)
        }]
    )
    return response.content[0].text.strip()
```

**Experiment 2: Few-shot with examples in the prompt.**

```python
FEW_SHOT_PROMPT = """Classify the severity of this customer support ticket.
Severity levels: Critical, High, Medium, Low.

Examples:
Ticket: Our API is returning 500 errors for all requests. Production is down.
Severity: Critical

Ticket: The export to CSV function is producing incorrect totals.
Severity: High

Ticket: Can you add a dark mode option to the app?
Severity: Low

Ticket: The search results sometimes show duplicates.
Severity: Medium

Output only the severity level. No explanation.

Ticket: {ticket}"""

def classify_few_shot(ticket: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        messages=[{
            "role": "user",
            "content": FEW_SHOT_PROMPT.format(ticket=ticket)
        }]
    )
    return response.content[0].text.strip()
```

**Experiment 3: Chain-of-thought - reasoning before label.**

```python
COT_SYSTEM = """You are a support ticket triage specialist. When classifying tickets:
1. Assess: who is affected (one user vs. many vs. all)?
2. Assess: is revenue or core functionality impacted?
3. Assess: is this time-sensitive?
Then assign: Critical (total outage/data loss), High (major feature broken),
Medium (partial impact/workaround exists), Low (minor/cosmetic/question)."""

COT_USER_TEMPLATE = """Classify this ticket. Reason through the 3 questions,
then output your final answer as: SEVERITY: [level]

Ticket: {ticket}"""

def classify_cot(ticket: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        system=COT_SYSTEM,
        messages=[{
            "role": "user",
            "content": COT_USER_TEMPLATE.format(ticket=ticket)
        }]
    )
    return response.content[0].text.strip()
```

> **اختبار من الواقع:** تشغّل التجارب الثلاث جميعها. كل من zero-shot و few-shot يصنّف "The entire payment service is down" على أنه Critical. CoT أيضًا يصيبها لكنه يستخدم 8 أضعاف tokens المخرجات. يحصل منتجك على 10,000 تذكرة يوميًا. متى يستحق نهج CoT كلفته، ومتى ستعود إلى few-shot؟

استخدم CoT للشريحة الوسطى الغامضة: التذاكر التي قد تكون High أو Critical، أو Medium مقابل High. للحالات القاطعة عند الطرفين ("الخدمة بأكملها معطّلة" أو "كيف أغيّر كلمة المرور")، يكون prompt من نوع few-shot مبني جيدًا دقيقًا وأرخص. في الإنتاج: وجّه التذاكر إلى CoT فقط حين يُرجع few-shot قيمة Medium أو High (النطاق الغامض)، واستخدم التصنيف السريع/الرخيص للطرفين. طبقة توجيه (routing) تطبّق التقنية الصحيحة لكل حالة أفضل من تطبيق التقنية الأغلى على كل شيء.

---

## USE IT

### Few-Shot بنمط دور Assistant في الـ SDK

تدعم مصفوفة messages في الـ SDK طريقة أنظف للتعبير عن أمثلة few-shot: تناوب أدوار user/assistant. هذا يفصل الأمثلة عن التعليمات، ما يسهّل إضافة أو إزالة أو تعديل كل مثال (shot) دون المساس بمنطق الـ prompt.

```python
def classify_few_shot_sdk(ticket: str) -> str:
    """
    Few-shot using the messages array: examples as user/assistant pairs.
    Same examples as the inline prompt but structured as conversation turns.
    """
    messages = [
        # Example 1
        {"role": "user",      "content": "Ticket: Our API is returning 500 errors for all requests. Production is down."},
        {"role": "assistant", "content": "Critical"},

        # Example 2
        {"role": "user",      "content": "Ticket: The export to CSV function is producing incorrect totals."},
        {"role": "assistant", "content": "High"},

        # Example 3
        {"role": "user",      "content": "Ticket: Can you add a dark mode option to the app?"},
        {"role": "assistant", "content": "Low"},

        # Example 4
        {"role": "user",      "content": "Ticket: The search results sometimes show duplicates."},
        {"role": "assistant", "content": "Medium"},

        # The real ticket
        {"role": "user",      "content": f"Ticket: {ticket}"},
    ]

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        system="You are a support ticket triage specialist. Classify severity: Critical, High, Medium, Low. Output only the label.",
        messages=messages
    )
    return response.content[0].text.strip()
```

هذه هي المعلومات نفسها التي في الـ prompt المضمّن (inline) من نوع few-shot، منظّمة بشكل مختلف. لنهج مصفوفة messages ميزة عملية واحدة: يمكنك تحميل الأمثلة من قاعدة بيانات أو ملف إعدادات وبناء المصفوفة ديناميكيًا. أما نهج الـ prompt المضمّن فيتطلب معالجة سلاسل لإضافة الأمثلة أو إزالتها.

> **نقلة في المنظور:** يجادل زميل بأن CoT مهدِر لمهمة تصنيف لأن "النموذج يعرف أصلًا ما معنى Critical". متى ستعترض على هذا؟

اعترض حين تحتوي المهمة على حالات حدّية تتطلب موازنة عوامل متعددة قبل اتخاذ القرار. عبارة "النموذج يعرف ما معنى Critical" صحيحة للحالات النمطية. الحالات الصعبة هي الوسطى: خطأ دفع يؤثر في 2% من المستخدمين (High أم Critical؟)، API بطيء تنتهي مهلته للاستعلامات الكبيرة (Medium أم High؟). هذه تتطلب استدلالًا حول النطاق والأثر على الأعمال. يستحق CoT كلفته حين تتركّز معدلات الخطأ في zero-shot و few-shot في الحالات الوسطى الغامضة، لا في الطرفين القاطعين. شغّل اختبار الـ ablation: إن كان إزالة CoT يخطئ فقط في الحالات الحدّية، فهذا بالضبط حين يهمّ.

---

## SHIP IT

الأثر (artifact) الذي ينتجه هذا الدرس هو مرجع لأنماط few-shot و CoT. انظر `outputs/skill-few-shot-cot.md`.

يلتقط المرجع أشكال الـ prompt الثلاثة، ومتى تُستخدم كل منها، ونمط مصفوفة messages في الـ SDK لأمثلة few-shot المنظّمة، وعبارات إطلاق CoT التي تُفعّل بشكل موثوق الاستدلال خطوة بخطوة.

---

## EVALUATE IT

لا تستحق هذه التقنيات الاستخدام إلا إذا حسّنت الدقة في مهمتك المحددة. يتطلب قياس التحسّن مجموعة اختبار موسومة (labeled test set).

**Build a test set.** اجمع أو ولّد 20-30 مثالًا موسومًا: مدخلات حقيقية أو واقعية بإجابات صحيحة. لتصنيف الخطورة: 5 أمثلة لكل شريحة تكفي للتقييم الأساسي. وسِمها بنفسك أو بمساعدة خبير مجال. هذا هو الحد الأدنى لمجموعة تقييم صالحة.

**Baseline measurement.** شغّل zero-shot على كل الأمثلة. سجّل الدقة لكل شريحة (Critical، High، Medium، Low) لا الدقة الإجمالية فقط. الدقة الإجمالية تخفي الأعطال الخاصة بكل شريحة.

**Few-shot measurement.** شغّل نسخة few-shot. قارن الدقة لكل شريحة. استنتاج شائع: يحسّن few-shot الاتساق أكثر من الدقة. كان النموذج يصنّف بشكل صحيح لكن يهيّئ المخرج بشكل غير متسق. few-shot يصلح ذلك.

**CoT measurement.** شغّل نسخة CoT. قارن على الحالات التي فشل فيها zero-shot و few-shot. ينبغي أن يقلّل CoT الأخطاء في الحالات متعددة العوامل (مثل النطاق الغامض). إن لم يقلّل CoT الأخطاء في حالات الفشل المحددة لديك، فهو ليس الأداة المناسبة لمهمتك.

**Cost/accuracy trade-off.** لكل تقنية: سجّل متوسط tokens المخرجات ومتوسط الدقة. ارسم الدقة مقابل كلفة الـ tokens. الهدف هو التقنية التي تحقق هدف دقتك بأقل كلفة tokens. لمعظم مهام التصنيف الإنتاجية، يصيب few-shot بـ 4-6 أمثلة مختارة جيدًا الهدف دون عبء tokens الخاص بـ CoT.
