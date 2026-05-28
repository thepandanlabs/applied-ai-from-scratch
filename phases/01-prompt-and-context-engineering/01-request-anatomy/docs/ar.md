# تشريح الطلب: System و User و Assistant

> النموذج لا يتذكر شيئًا. هو يعيد قراءة المحادثة بالكامل في كل مرة.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** أساسيات Python، `pip install anthropic`
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- وصف الغرض من أدوار system و user و assistant وما الذي يتحكم فيه كل دور
- بناء مصفوفة messages صحيحة يدويًا دون تجريدات الـ SDK
- شرح لماذا لا يُعد system prompt ذاكرة خاصة بل مجرد أول context يقرأه النموذج
- استخدام Anthropic SDK لإرسال طلب مبني بشكل صحيح
- تحديد ما الذي ينكسر عند إساءة استخدام الأدوار أو تشويه أدوار المحادثة (turns)

---

## THE PROBLEM

تبدأ باستخدام API الخاص بـ Claude ويعمل. تلصق أمثلة، وتعدّل الـ prompts، وتحصل على نتائج لا بأس بها. ثم ينكسر الإنتاج بطرق غير منطقية: يتجاهل النموذج تعليماتك في منتصف المحادثة، أو يبدأ بالرد بصيغة خاطئة، أو "ينسى" ما أخبرته به قبل ثلاثة أدوار.

السبب الجذري دائمًا تقريبًا هو نفسه: ليس لديك نموذج ذهني لما يستقبله النموذج فعليًا في كل استدعاء API. تظن أن system prompt إعداد دائم. تظن أن النموذج "يتذكر" الأدوار السابقة. وكلا الأمرين غير صحيح.

كل استدعاء API يرسل حِملًا (payload) كاملًا وجديدًا. يقرأه النموذج من أعلاه إلى أسفله، في كل مرة. إذا كان context الخاص بك خاطئًا، فإن مخرجاتك خاطئة. فهم تشريح الطلب ليس معرفة خلفية اختيارية. بل هو متطلب مسبق لتصحيح كل مشكلة أخرى في هندسة الـ prompt.

---

## THE CONCEPT

### الأدوار الثلاثة

كل طلب إلى Anthropic Messages API هو قائمة من الرسائل، لكل منها دور. توجد ثلاثة أدوار، ويخدم كل منها غرضًا مميزًا:

```
SYSTEM        Sets the model's behavior, persona, and constraints.
              Not part of the messages array. Sent as a top-level parameter.
              The model treats it as authoritative context.

USER          The human turn. Your input, the user's input,
              or any content from outside the model.
              Alternates with assistant.

ASSISTANT     The model's output. In a multi-turn conversation,
              previous model responses are included here so the
              model can maintain coherence.
```

القاعدة البنيوية الأساسية: يجب أن يتناوب دورا `user` و `assistant`. لا يمكن أن يكون لديك رسالتا user متتاليتان. كل دور assistant يأتي بعد دور user.

### كيف يرى النموذج المحادثة

هذا ما يُرسل في الدور الثالث من محادثة:

```
┌────────────────────────────────────────────────────────┐
│  SYSTEM (top-level parameter)                          │
│  "You are a code review assistant. Be concise."        │
├────────────────────────────────────────────────────────┤
│  USER  (turn 1)                                        │
│  "Review this function: def add(a, b): return a + b"   │
├────────────────────────────────────────────────────────┤
│  ASSISTANT  (turn 1)                                   │
│  "The function is correct. Consider adding type hints."│
├────────────────────────────────────────────────────────┤
│  USER  (turn 2)                                        │
│  "How would I add type hints?"                         │
├────────────────────────────────────────────────────────┤
│  ASSISTANT  (turn 2)   <-- model generates this now    │
└────────────────────────────────────────────────────────┘
```

لا توجد ذاكرة. لا توجد حالة جلسة (session state). يقرأ النموذج هذه الكتلة بالكامل ويولّد دور assistant التالي. إذا أزلت الدور الأول من مصفوفة messages، فلن يكون لدى النموذج أي فكرة عن الدالة التي راجعها.

### وهم النسيان

"لكن ChatGPT يتذكر رسائلي السابقة!" نعم: التطبيق هو من يخزّنها ويعيد إرسالها في كل استدعاء. النموذج نفسه لا ذاكرة له بين الاستدعاءات. المحادثة موجودة فقط لأن شيفرتك (أو واجهة الدردشة) تُلحق كل دور وتعيد إرسال السجل الكامل.

هذا يعني: حجم نافذة الـ context هو ما يحدّ من طول محادثتك الفعّال، وليس أي حد لذاكرة النموذج. حين تطول المحادثة أكثر من اللازم، فإما أن تقتطع الأدوار القديمة أو يتوقف النموذج عن رؤيتها.

---

## BUILD IT

### بناء الطلبات يدويًا

قبل استخدام الـ SDK، ابنِ الطلب على شكل قواميس (dicts) Python خام. هذا يجعل البنية ملموسة ويزيل أي وهم بأن الـ SDK يقوم بشيء سحري.

**Step 1: A single-turn request, no history.**

```python
import anthropic
import json

client = anthropic.Anthropic()

# The messages array: one user turn, no history
messages = [
    {"role": "user", "content": "What is the capital of France?"}
]

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    system="You are a geography assistant. Answer in one sentence.",
    messages=messages
)

print(response.content[0].text)
```

المعامل `system` منفصل عن `messages`. هو يضبط السلوك، لا المحادثة.

**Step 2: A multi-turn request, manually constructed.**

لاحظ أنك لا تستدعي كائن جلسة دردشة. أنت تبني قائمة عادية وتمررها:

```python
messages = [
    {"role": "user",      "content": "My name is Alex. Remember it."},
    {"role": "assistant", "content": "Got it, Alex. How can I help you?"},
    {"role": "user",      "content": "What is my name?"},
]

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=128,
    system="You are a helpful assistant.",
    messages=messages
)

print(response.content[0].text)
# Output: "Your name is Alex."
```

الآن جرّب إزالة الرسالتين الأوليين من تلك القائمة. سيقول النموذج إنه لا يعرف اسمك. لا توجد جلسة. الـ context الذي ترسله هو الـ context الوحيد لدى النموذج.

**Step 3: Break it intentionally.**

جرّب إرسال رسالتي user متتاليتين:

```python
# This will raise an API error
messages = [
    {"role": "user", "content": "First message"},
    {"role": "user", "content": "Second message"},  # invalid: two user turns in a row
]
```

يرفض الـ API هذا. البنية المتناوبة متطلب صارم، لا مجرد اصطلاح.

> **اختبار من الواقع:** روبوت الدردشة متعدد الأدوار لديك "ينسى" اسم المستخدم بعد 10 أدوار. لم تغيّر الشيفرة. ما السبب الأرجح، وأين ستبحث أولًا؟

السبب الأرجح هو شيفرة إدارة نافذة الـ context التي تقتطع الأدوار القديمة لتوفير الـ tokens، وهي تقتطع الأدوار التي تحتوي على الاسم. انظر إلى كيف يبني تطبيقك مصفوفة `messages` قبل كل استدعاء API. تحقّق مما إذا كنت تُمرّر نافذة منزلقة فوق السجل، وإن كان كذلك، فهل حافظت على context حرج (مثل تعريف المستخدم بنفسه في البداية) قبل الاقتطاع.

---

## USE IT

### دالة `messages.create` في Anthropic SDK

يغلّف الـ SDK البنية نفسها تمامًا. لا يتغير شيء بشأن الأدوار، أو قاعدة التناوب، أو معامل system. يضيف الـ SDK التحقق من الأنواع (type checking)، ومنطق إعادة المحاولة (retry logic)، وتحليل الاستجابة.

```python
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    system="You are a precise technical writer. Use plain language.",
    messages=[
        {"role": "user", "content": "Explain what an API is in two sentences."}
    ]
)

# response.content is a list of content blocks
# For text responses, block.text contains the output
print(response.content[0].text)
print(f"\nTokens used: {response.usage.input_tokens} in / {response.usage.output_tokens} out")
```

يكشف كائن الاستجابة عن `stop_reason` (`end_turn`، `max_tokens`، `stop_sequence`)، و `usage` لأعداد الـ tokens، و `content` كقائمة من الكتل المُحدَّدة الأنواع (typed blocks). ستستخدم الثلاثة جميعًا في الإنتاج.

**Appending turns for a real conversation loop:**

```python
def chat(system_prompt: str) -> None:
    """Simple REPL demonstrating manual turn management."""
    client = anthropic.Anthropic()
    messages = []

    print("Type 'quit' to exit.\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() == "quit":
            break

        messages.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system=system_prompt,
            messages=messages
        )

        assistant_text = response.content[0].text
        # Append the assistant turn so the next call has full history
        messages.append({"role": "assistant", "content": assistant_text})

        print(f"Claude: {assistant_text}\n")
        print(f"[Context: {len(messages)} turns, "
              f"{response.usage.input_tokens} input tokens]\n")
```

لاحظ النمط: ألحِق دور user، استدعِ الـ API، ألحِق استجابة assistant، كرّر. قائمة `messages` هي حالة محادثتك. أنت تملكها.

> **نقلة في المنظور:** إطار عمل مثل LangChain "يدير سجل المحادثة" نيابةً عنك تلقائيًا. ماذا تتنازل عنه حين تترك الإطار يتولى مصفوفة messages؟

تتنازل عن الوضوح (visibility). حين يُنتج النموذج استجابة غير متوقعة، يكون السؤال الأول دائمًا "ما الذي استقبله النموذج فعلًا؟" مع الإدارة اليدوية، يمكنك طباعة `messages` في أي لحظة ورؤية الحِمل (payload) بالضبط. مع إطار يدير السجل، تحتاج إلى معرفة كيفية استخراج التمثيل الداخلي للإطار، ما يضيف طبقة تصحيح بينك وبين النموذج. النموذج يستقبل مصفوفة JSON. كلما بقيتَ أقرب إلى هذه الحقيقة، أسرع تُصحّح.

---

## SHIP IT

الأثر (artifact) الذي ينتجه هذا الدرس هو بطاقة مرجعية لتشريح الطلب. انظر `outputs/skill-request-anatomy.md`.

يلتقط المرجع تعريفات الأدوار، وقاعدة البنية المتناوبة، ودلالات معامل system، وأنماط الأعطال الشائعة. استخدمه كقائمة تحقق عند تصحيح أخطاء المحادثة متعددة الأدوار.

---

## EVALUATE IT

يظهر الفهم الراسخ لتشريح الطلب في القدرة على تصحيح أعطال المحادثة دون تخمين. وإليك كيف تتحقق من رسوخ المفاهيم:

**Role structure.** اكتب دالة `validate_messages(messages: list) -> list[str]` تُعيد قائمة بسلاسل الأخطاء لأي مخالفات: رسائل متتالية لنفس الدور، غياب دور user في البداية، دور assistant في النهاية (ما يُنتج استكمالًا فارغًا). اختبرها على 5 مصفوفات رسائل صحيحة و5 غير صحيحة.

**Context persistence.** ابنِ محادثة من 5 أدوار يذكر فيها المستخدم اسمه في الدور 1 ويسأل عنه في الدور 5. شغّلها مرتين: مرة بالسجل الكامل، ومرة مع إزالة الدورين 2-3. تحقّق من أن النموذج يجيب بشكل صحيح في الحالة الأولى ويقول إنه لا يعرف في الثانية. هذا هو اختبار "النسيان فقدان للبيانات".

**Token growth.** أضِف قياسات إلى دالة `chat` لطباعة `usage.input_tokens` بعد كل دور. بعد 10 أدوار، ارسم النمو. ينبغي أن يكون خطيًا تقريبًا مع طول المحادثة. تحقّق من أن معدل النمو يطابق مجموع كل الرسائل في المصفوفة، لا دور user الأخير فقط.

**System prompt isolation.** شغّل رسالة user نفسها مع 3 system prompts مختلفة: واحدة تطلب لغة رسمية، وواحدة تطلب إجابات من كلمة واحدة، وواحدة تطلب مخرجات JSON. تحقّق من أن المخرجات تختلف اختلافًا جذريًا. هذا يؤكد أن معامل system يضبط سلوك النموذج فعلًا، ولا يُتجاهَل ببساطة.
