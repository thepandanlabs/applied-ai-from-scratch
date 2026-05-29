# هندسة الـ Context

> الـ context هو المنتَج. ما تضعه في النافذة، وأين تضعه، يحدّد ما يخرج منها.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** الدرس 01 (تشريح الطلب)، الدرس 02 (أساسيات الـ Prompt)، `pip install anthropic`
**الوقت:** ~60 دقيقة
**أهداف التعلّم:**
- وصف التسلسل الهرمي للمعلومات في نافذة الـ context وكيف يؤثر الموضع في البروز (salience)
- بناء دالة تجميع context تحزم استعلام المستخدم والمستندات المُسترجَعة وسجل المحادثة والتعليمات بالترتيب الأمثل
- شرح انحياز الأسبقية (primacy) والحداثة (recency) وأثرهما على انتباه النموذج
- مقارنة التجميع الساذج (naive) مقابل المُهندَس للـ context في مهمة استرجاع
- تطبيق ميزانية الـ context: تخصيص ميزانية tokens عبر طبقات الـ context بناءً على أولويتها

---

## THE PROBLEM

تبني نظام RAG. تسترجع المستندات الصحيحة. تُضمّن سؤال المستخدم. لكن إجابات النموذج غامضة، أو تفوّت تفاصيل أساسية من المستندات، أو تنحرف عائدةً إلى المعرفة العامة بدلًا من الإجابة من المحتوى المُسترجَع.

الاسترجاع صحيح. التعليمات واضحة. المشكلة في تجميع الـ context: أين تجلس المعلومة في النافذة نسبةً إلى كل شيء آخر.

هذه هي هندسة الـ context: ليس ما تُضمّنه، بل كيف ترتّبه. انتباه النموذج ليس موحّدًا عبر نافذة الـ context. الموضع يهمّ. الحجم يهمّ. نسبة الإشارة إلى الضوضاء (signal-to-noise) تهمّ. الخطأ في هذا يُنتج نماذج لديها كل المعلومات الصحيحة لكنها ما زالت تعطي إجابات خاطئة.

---

## THE CONCEPT

### نافذة الـ Context كطبقات

كل شيء في استدعاء API واحد يتنافس على انتباه النموذج ضمن ميزانية tokens ثابتة. يمكن تنظيم المعلومات في طبقات حسب الأولوية:

```
HIGH PRIORITY (processed with most weight)
    ┌─────────────────────────────────────────┐
    │  LAYER 1: Task instructions             │ <-- TOP: primacy bias
    │  What to do, how to respond, what       │
    │  format to use, what to prioritize.     │
    ├─────────────────────────────────────────┤
    │  LAYER 2: Relevant retrieved content    │
    │  Documents, facts, data directly        │
    │  relevant to the user's query.          │
    ├─────────────────────────────────────────┤
    │  LAYER 3: Conversation history          │
    │  Prior turns that establish context.    │
    │  Most recent turns matter most.         │
    ├─────────────────────────────────────────┤
    │  LAYER 4: The user's current query      │ <-- BOTTOM: recency bias
    │  What they actually asked right now.    │
    └─────────────────────────────────────────┘
LOW PRIORITY (at risk of being underweighted)
    - Anything in the middle of a long context
    - Redundant or contradictory content
    - Content not relevant to the current query
```

### انحياز الأسبقية والحداثة

تُظهر الأبحاث على أنماط انتباه الـ transformer تأثيرين متّسقين:

**انحياز الأسبقية (Primacy bias):** المحتوى في بداية الـ context تمامًا (الـ system prompt) يحظى بانتباه قوي. يستخدمه النموذج كإطار مرجعي موثوق لتفسير كل ما يليه.

**انحياز الحداثة (Recency bias):** المحتوى قرب نهاية الـ context (رسالة user الأخيرة) يحظى بانتباه قوي لأنه أحدث إشارة يعالجها النموذج قبل توليد استجابته.

**منطقة الخطر:** المحتوى المحشور في منتصف context طويل هو الأكثر عرضة لأن يُقلَّل وزنه. مستند مُسترجَع وثيق الصلة لكنه مدفون بين 10 مستندات أخرى وسجل محادثة طويل معرّض لأن يُتجاهَل.

```
Token position in context:
0        25%      50%      75%      100%
|--------|--------|--------|--------|
^                                   ^
High attention                 High attention
(primacy)                      (recency)

                    ^
               Lower attention
               (lost in middle)
```

هذا ليس خللًا في النموذج. بل خاصية لكيفية عمل آليات الانتباه. الاستجابة الهندسية هي ترتيب المعلومات بحيث يستفيد المحتوى الأهم من الأسبقية أو الحداثة.

### ميزانية الـ Context

ميزانيات الـ tokens قيود حقيقية. عند context بحجم 128k، يمكنك تضمين الكثير، لكن لا تزال تحتاج إلى تحديد ما يستحق مساحته. إطار تخصيص تقريبي:

```
TYPICAL CONTEXT BUDGET ALLOCATION

  System instructions:     5-10%  (dense, high-priority)
  Retrieved documents:    40-60%  (the core content)
  Conversation history:   20-30%  (recent turns, trimmed)
  Current user query:      5-10%  (short, always included)
  Output headroom:        10-20%  (reserved for response)
```

يتبدّل التخصيص بناءً على نوع المهمة: مهمة التلخيص تحتاج مساحة مستندات أكبر؛ مهمة الدردشة تحتاج سجلًا أكبر.

---

## BUILD IT

### دالة تجميع الـ Context

تأخذ دالة تجميع الـ context كل الأجزاء وتحزمها بالترتيب الصحيح بقيود الميزانية الصحيحة.

**Step 1: Naive assembly (what most people do first).**

```python
import anthropic

client = anthropic.Anthropic()

def assemble_naive(
    query: str,
    documents: list[str],
    history: list[dict],
    instructions: str
) -> list[dict]:
    """Naive: stuff everything into one user message in arbitrary order."""
    content_parts = []
    content_parts.append(f"Instructions: {instructions}")
    content_parts.append(f"Documents:\n" + "\n\n".join(documents))
    # Flatten history into a string (loses structure)
    for turn in history:
        content_parts.append(f"{turn['role']}: {turn['content']}")
    content_parts.append(f"Question: {query}")

    full_content = "\n\n".join(content_parts)
    return [{"role": "user", "content": full_content}]
```

مشكلات التجميع الساذج: التعليمات مدفونة قبل المستندات، السجل مسطّح (يفقد بنية الأدوار)، استعلام المستخدم في النهاية لكنه مختلط بالضوضاء، لا تحكم بالميزانية.

**Step 2: Engineered assembly.**

```python
def count_tokens_estimate(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


def truncate_history(
    history: list[dict],
    max_tokens: int
) -> list[dict]:
    """Keep the most recent turns that fit within max_tokens."""
    result = []
    token_count = 0
    for turn in reversed(history):
        turn_tokens = count_tokens_estimate(turn["content"])
        if token_count + turn_tokens > max_tokens:
            break
        result.insert(0, turn)
        token_count += turn_tokens
    return result


def truncate_documents(
    documents: list[str],
    max_tokens: int
) -> list[str]:
    """Keep the most relevant documents (assumes ordered by relevance) that fit."""
    result = []
    token_count = 0
    for doc in documents:
        doc_tokens = count_tokens_estimate(doc)
        if token_count + doc_tokens > max_tokens:
            break
        result.append(doc)
        token_count += doc_tokens
    return result


def assemble_engineered(
    query: str,
    documents: list[str],
    history: list[dict],
    instructions: str,
    total_budget: int = 4000,
) -> tuple[str, list[dict]]:
    """
    Engineered context assembly with explicit layer ordering and token budgeting.

    Layer order (by priority):
    1. System prompt: instructions (primacy bias)
    2. Retrieved documents: most relevant content
    3. Conversation history: recent turns only
    4. User's current query: last message (recency bias)

    Returns: (system_prompt, messages_array)
    """
    # Budget allocation
    instruction_budget = int(total_budget * 0.10)
    document_budget   = int(total_budget * 0.50)
    history_budget    = int(total_budget * 0.25)
    # query gets the remainder; output is on top of total_budget

    # Layer 1: Instructions in system prompt (primacy)
    system = instructions[:instruction_budget * 4]  # rough char limit

    # Layer 2: Retrieved documents (most relevant first, truncated to budget)
    docs_included = truncate_documents(documents, document_budget)
    docs_block = ""
    if docs_included:
        docs_block = "RELEVANT DOCUMENTS:\n" + "\n\n---\n\n".join(
            f"[Doc {i+1}]\n{doc}" for i, doc in enumerate(docs_included)
        )

    # Layer 3: Conversation history (recent turns only, within budget)
    trimmed_history = truncate_history(history, history_budget)

    # Layer 4: Current query (recency)
    # Combine docs + query into the final user message
    if docs_block:
        final_user_content = f"{docs_block}\n\nQUESTION: {query}"
    else:
        final_user_content = f"QUESTION: {query}"

    # Build messages array: history turns + final user message
    messages = list(trimmed_history) + [{"role": "user", "content": final_user_content}]

    return system, messages
```

> **اختبار من الواقع:** تجميع الـ context المُهندَس لديك يعمل جيدًا، لكنك تلاحظ أنه في المحادثات الأطول من 20 دورًا، يبدأ النموذج بمناقضة معلومات كان "يعرفها" في الدور 5. المستندات المُسترجَعة سليمة. ما السبب الأرجح، وأي معامل ميزانية ستعدّل؟

السبب الأرجح هو أن ميزانية السجل (history budget) أصغر من أن تُضمّن الدور 5، فتُقتطع الأدوار الحديثة عودةً إلى الدور 15 تقريبًا. النموذج لا يرى السياق الأقدم. اضبط نسبة `history_budget` للأعلى (من 25% إلى 35-40%)، أو أضِف منطقًا للحفاظ دائمًا على أول N أدوار من السجل ("أدوار المرساة") قبل الاقتطاع من المنتصف نحو الخارج. المقايضة هي tokens أقل للمستندات، لذا تحقّق أيضًا مما إذا كانت كل المستندات المُسترجَعة ما زالت ضرورية.

---

## USE IT

### مقارنة التجميع الساذج مقابل المُهندَس

يظهر الفرق القابل للقياس حين يحتاج النموذج إلى الإجابة من تفاصيل محددة في المستندات المُسترجَعة مع الحفاظ على ترابط المحادثة.

```python
def run_comparison(
    query: str,
    documents: list[str],
    history: list[dict],
    instructions: str
) -> None:
    """Run both assembly strategies and compare outputs."""

    # Naive assembly
    naive_messages = assemble_naive(query, documents, history, instructions)
    naive_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=naive_messages
    )

    # Engineered assembly
    system, eng_messages = assemble_engineered(
        query, documents, history, instructions
    )
    eng_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system=system,
        messages=eng_messages
    )

    print("NAIVE ASSEMBLY:")
    print(naive_response.content[0].text)
    print(f"\nInput tokens: {naive_response.usage.input_tokens}")

    print("\nENGINEERED ASSEMBLY:")
    print(eng_response.content[0].text)
    print(f"\nInput tokens: {eng_response.usage.input_tokens}")
```

ما الذي تبحث عنه في المقارنة:

1. هل تستشهد النسخة المُهندَسة بتفاصيل محددة من المستندات بينما تتحدث النسخة الساذجة بعموميات؟
2. هل تحافظ النسخة المُهندَسة على ترابط المحادثة (إشارات إلى أدوار سابقة) بينما تفوّت النسخة الساذجة السياق؟
3. هل أعداد tokens المدخلات متقاربة؟ إن كان للنسخة الساذجة عدد tokens أكبر بكثير، فهي تحشو الـ context بمحتوى غير لازم.

> **نقلة في المنظور:** يقول زميل "هندسة الـ context تحسين سابق لأوانه. فقط ضع كل شيء ودع النموذج يكتشفه." متى تبدأ هذه العقلية بتكلفة المال والدقة؟

تكلّف المال حين يُضمّن النهج الساذج المستندات والسجل والصياغة الجاهزة بثلاثة أضعاف tokens اللازمة، فتتضاعف كلفة مدخلاتك ثلاث مرات على نطاق واسع. وتكلّف الدقة حين يصبح الـ context طويلًا جدًا فتسقط المعلومات الحرجة في المنتصف (مشكلة الضياع في المنتصف). عند 10,000 استدعاء API يوميًا، فإن عدم كفاءة بمقدار 3 أضعاف في الـ tokens يتراكم إلى أثر حقيقي على الميزانية. وعند 50+ مستندًا في الـ context، يصبح أثر الضياع في المنتصف قابلًا للقياس. ليست هندسة الـ context تحسينًا سابقًا لأوانه حين يكون لديك ميزانية tokens ملموسة أو مهمة استرجاع تهمّ فيها الدقة.

---

## SHIP IT

الأثر (artifact) الذي ينتجه هذا الدرس هو دليل هندسة الـ context. انظر `outputs/skill-context-engineering.md`.

يلتقط الدليل نموذج ترتيب الطبقات، وإطار وضع الميزانية، وتحذير الضياع في المنتصف، ونمط دالة التجميع لإعادة الاستخدام عبر المشاريع.

---

## EVALUATE IT

تظهر جودة هندسة الـ context في دقة الاسترجاع: هل يجيب النموذج من المستندات المقدّمة أم يعود إلى المعرفة العامة؟

**Attribution test.** أعطِ النموذج 3 مستندات بحقائق متمايزة وفريدة. اطرح سؤالًا إجابته موجودة فقط في المستند 2. قيّم: هل يجيب النموذج من المستند 2 أم يهلوس من المعرفة العامة؟ شغّل هذا بالتجميع الساذج مقابل المُهندَس. ينبغي أن تُظهر النسخة المُهندَسة دقة إسناد (attribution) أعلى.

**Lost-in-middle test.** أنشئ context بـ 10 مستندات. ضع المستند ذا الصلة في الموضع 1، ثم 5، ثم 10 عبر تشغيلات منفصلة. قِس جودة الإجابة. إن كانت الجودة أدنى ملحوظًا حين يكون المستند ذو الصلة في الموضع 5، فلديك مشكلة ضياع في المنتصف. الحل: ضع المستند الأكثر صلة أخيرًا (الأقرب إلى الاستعلام) أو أولًا (يستفيد من الأسبقية).

**Budget utilization.** بعد كل استدعاء، تحقّق من `response.usage.input_tokens`. هل هو قريب من ميزانيتك، أم أقل بكثير منها (اقتطاع مفرط)، أم أعلى منها (اقتطاع غير كافٍ)؟ سجّل هذا عبر استدعاءات الإنتاج لمعايرة نسب ميزانيتك.

**History truncation correctness.** ابنِ محادثة اختبار تُذكر فيها حقيقة حرجة في الدور 1. اسأل عنها في الدور 15. تحقّق من أن النموذج ما زال يجيب بشكل صحيح حين تتضمّن ميزانية السجل لديك الدور 1. ثم قلّل ميزانية السجل حتى يُسقَط الدور 1 وتحقّق من أن النموذج يفشل. هذا يعطيك الحد الأدنى لميزانية السجل لتطبيقك المحدد.
