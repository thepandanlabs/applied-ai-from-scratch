# اختيار النمط الصحيح

> أبسط نمط يلبّي المتطلبات هو دائمًا نقطة البدء الصحيحة.

**النوع:** تعلّم
**اللغات:** Python
**المتطلبات:** 11-02 تحديد النطاق قبل الحل، المراحل 02-04 (RAG، الأدوات، الوكلاء)
**الوقت:** ~45 دقيقة
**المرحلة:** 11 - مهارات الـ FDE

## أهداف التعلّم

- تسمية أنماط الذكاء الاصطناعي الخمسة الرئيسية ووصف متى يكون كل منها مناسبًا
- تطبيق مصفوفة قرار (decision matrix) على متطلب محدّد النطاق واختيار نمط البدء الصحيح
- التعرّف على أكثر حالات عدم تطابق الأنماط شيوعًا (استخدام الوكلاء agents حين يكفي استدعاء واحد)
- بناء أداة CLI باسم PatternMatcher تمنح وصف المتطلب درجة مقابل كل نمط
- شرح لماذا يكون البدء بأبسط نمط حجّة صيانة (maintenance)، لا حجّة تعقيد فحسب

---

## المشكلة

تنهي مقابلة تحديد النطاق ولديك مواصفات ذكاء اصطناعي نظيفة. الآن تجلس لتصميم بنية النظام. بنيت خطوط أنابيب RAG، وتعرف كيف تركّب وكلاء يستدعون الأدوات (tool-calling agents)، وأجريت تنسيق وكلاء متعددين (multi-agent orchestration) في المرحلة 04. الغريزة أن تمدّ يدك إلى أقدر نمط: وكلاء مع استخدام أدوات، وربما مشرف متعدد الوكلاء (multi-agent supervisor).

ثم تطلق النظام. يستغرق 8 ثوانٍ ليستجيب. يستدعي 4 أدوات في كل طلب، 3 منها لا تُستخدم أبدًا لأنواع تذاكر هذا العميل الفعلية. تنقيح الأخطاء مؤلم. يسأل العميل لماذا يعطي أحيانًا إجابات مختلفة للتذكرة نفسها. وتجد نفسك تشرح اللاحتمية (non-determinism) لفريق التزام.

المشكلة ليست في نمط الوكيل: الوكلاء صحيحون لبعض المشكلات. المشكلة هي مدّ اليد إلى الوكلاء قبل التحقق ما إن كان استدعاء LLM واحد، مع محفّز (prompt) مُصاغ جيدًا، سيلبّي كل المتطلبات. في ارتباطات الـ FDE، النمط الخاطئ المختار في بداية البناء يكلّف 3-5 أيام من إعادة العمل. قرار النمط يستحق 20 دقيقة من التحليل المتعمّد.

---

## المفهوم

### الأنماط الخمسة ومجالاتها

```
PATTERN              WHAT IT IS              WHEN IT FITS
-------------------  ----------------------  ----------------------------------
Single LLM call      One prompt, one         Fixed I/O, no retrieval needed,
                     response               deterministic output preferred,
                                            latency < 2s required

RAG                  Retrieve + generate     Output depends on a knowledge base
                     from retrieved          that changes or is too large for
                     context                context, factual grounding required

Agent with tools     LLM decides which       Requires external data (live APIs,
                     tools to call and       databases), multi-step reasoning,
                     how to combine          output varies by inputs
                     results

Multi-agent          Multiple LLMs with      Complex workflow with parallel
                     different roles         tasks, different expertise
                     coordinate             domains, or verification step
                                            requiring independent judgment

Fine-tuning          Trained on task-        Pattern is highly repetitive,
                     specific examples       examples are abundant, base model
                                            behavior must be suppressed
```

### مصفوفة القرار

امنح كل محور درجة 0 (لا)، 1 (ربما)، 2 (نعم) لمتطلبك:

```
Decision Axis           Single  RAG  Agent  Multi  Fine-tune
                        Call         Tools  Agent
----------------------  ------  ---  -----  -----  ---------
Output depends on a       0      2     1      1       0
changing knowledge base

Multi-step reasoning      0      0     2      2       0
required

Latency < 2s required     2      1     0      0       1

Output must be            2      1     0      0       2
deterministic

Integration complexity    2      1     0      0       1
must stay low

Data volume too large     0      2     1      1       1
for context window

Task is extremely         0      0     0      0       2
repetitive with examples
```

النمط الأعلى تسجيلًا لمحاورك هو نقطة البدء.

### أكثر حالات عدم التطابق شيوعًا

```
"This ticket needs context from our KB"
                |
                v
Engineer reaches for agent with KB tool
                |
                v
RAG pipeline + single LLM call would do the same job
at 4x lower latency and 10x simpler debugging
```

الوكلاء يستحقون تعقيدهم حين:
- يجب على النظام أن يقرّر أيّ الأدوات يستدعي بناءً على المدخل
- يجب على النظام أن يتعامل مع تدفقات عمل (workflows) متعددة الخطوات بمنطق تفرّعي
- يجب على النظام أن يستجيب للإخفاقات (إعادة محاولة، تصعيد، استخدام بديل)

الوكلاء لا يستحقون تعقيدهم حين:
- توجد أداة واحدة ثابتة تُستدعى في كل طلب
- تدفّق العمل خطّي بلا تفرّع
- زمن الاستجابة مهم ولا يُبرَّر عبء الوكيل (agent overhead)

أبسط اختبار لعدم التطابق: لو كتبت النظام كمحفّز واحد + RAG + استدعاء مخرج منظّم واحد، هل سيلبّي المواصفات؟ إن كانت الإجابة نعم، فذلك ما تبنيه.

---

## البناء

ابنِ أداة CLI باسم `PatternMatcher` تأخذ وصف متطلب، وتمنحه درجة مقابل محاور القرار الخمسة، وتوصي بنمط بدء مع تحذير إن تعارضت التوصية مع الوصف.

```python
# Each requirement description is scored on the decision axes.
# The scoring uses Claude to parse the description into axis scores,
# then applies the decision matrix.

DECISION_AXES = [
    "output_depends_on_knowledge_base",
    "requires_multistep_reasoning",
    "latency_under_2s_required",
    "output_must_be_deterministic",
    "integration_complexity_must_stay_low",
    "data_too_large_for_context_window",
    "highly_repetitive_with_abundant_examples",
]

PATTERN_SCORES = {
    "single_llm_call": {
        "output_depends_on_knowledge_base": 0,
        "requires_multistep_reasoning": 0,
        "latency_under_2s_required": 2,
        "output_must_be_deterministic": 2,
        "integration_complexity_must_stay_low": 2,
        "data_too_large_for_context_window": 0,
        "highly_repetitive_with_abundant_examples": 0,
    },
    # ... 4 more patterns
}
```

شغّل المطابِق:

```bash
python main.py --requirement "Classify support tickets into 5 categories"
python main.py --interactive
python main.py --requirement req.txt --scenarios all
```

مثال على المخرج لثلاثة سيناريوهات مختلفة:

**السيناريو 1: مُصنِّف تذاكر**
```
Requirement: Classify support tickets into 5 categories with <1s response time.
Customer has labeled examples from 18 months of history.

Axis scores:
  output_depends_on_knowledge_base:       No  (0)
  requires_multistep_reasoning:           No  (0)
  latency_under_2s_required:              Yes (2)
  output_must_be_deterministic:           Yes (2)
  integration_complexity_must_stay_low:   Yes (2)
  data_too_large_for_context_window:      No  (0)
  highly_repetitive_with_abundant_examples: Yes (2)

Pattern scores:
  Single LLM call:  8   *** RECOMMENDED ***
  RAG:              4
  Agent with tools: 2
  Multi-agent:      2
  Fine-tuning:      7   (close second - worth exploring if labeled data is large)

Warning: None.
```

**السيناريو 2: مساعد بحث**
```
Requirement: Help analysts research any public company by pulling live data,
SEC filings, and news, then synthesizing a 1-page report.

Pattern scores:
  Single LLM call:  2
  RAG:              4
  Agent with tools: 9   *** RECOMMENDED ***
  Multi-agent:      7
  Fine-tuning:      1

Warning: Live data retrieval requires tool use. RAG alone won't work for
live sources. Multi-agent is worth exploring if the synthesis step
benefits from independent verification.
```

**السيناريو 3: مبالغة في استخدام الوكيل**
```
Requirement: Draft a response to a support ticket by looking it up in the
knowledge base and generating a reply.

Pattern scores:
  RAG:              8   *** RECOMMENDED ***
  Agent with tools: 7

Warning: This requirement scores close on RAG and Agent. RAG is recommended
because the knowledge base lookup is the only tool needed and the workflow
is linear. An agent adds overhead and non-determinism without adding capability
for this use case. Start with RAG.
```

> **اختبار من الواقع:** يطلب منك عميل بناء نظام "يبحث في منافسينا ويكتب ملخصًا أسبوعيًا." تشغّل مطابِق الأنماط فيوصي بوكيل مع أدوات. غريزتك أن تستخدم وكلاء متعددين لأن البحث يبدو معقّدًا. ماذا ينبغي أن تفعل؟ ابدأ بوكيل واحد، لا بوكلاء متعددين. مطابِق الأنماط يوصي بأبسط نمط يناسب. الوكلاء المتعددون يستحقون تعقيدهم حين توجد أدوار متمايزة تستفيد من سلاسل استدلال منفصلة (باحث، مدقّق حقائق، كاتب). أما للملخّص الأسبوعي، فوكيل واحد مزوّد ببحث الويب وأدوات المستندات أبسط وأسهل في تنقيح الأخطاء ويلبّي المتطلب. أضف الوكيل الثاني إن كانت جودة مخرج الوكيل الواحد غير كافية.

التنفيذ الكامل في `code/main.py`. وهو يستخدم Claude لمنح وصف المتطلب درجة مقابل المحاور ويطبّق مصفوفة القرار لإنتاج توصية مرتّبة مع تحذيرات.

---

## الاستخدام

شغّل PatternMatcher على 3 سيناريوهات مختلفة لترى كيف تغيّر مصفوفة القرار التوصية.

**السيناريو أ: أسئلة وأجوبة بسيطة**

"فريق المبيعات لدينا يحتاج إلى طرح أسئلة عن كتالوج منتجاتنا. يحوي الكتالوج 500 منتج، لكل منها ورقة مواصفات. يجب أن تكون الردود دقيقة وفي أقل من ثانيتين."

```bash
python main.py --requirement "Sales team Q&A on 500-product catalog, accuracy required, < 2s"
```

النتيجة: التوصية بـ RAG. الكتالوج أكبر من أن يدخل في السياق (context) (500 منتج)، والاسترجاع (retrieval) يؤسّس الإجابة على المواصفات الفعلية، وزمن الاستجابة قابل للإدارة بطبقة استرجاع جيدة.

**السيناريو ب: استخراج من المستندات**

"استخرج بيانات منظّمة (تواريخ، أطراف، مبالغ، شروط دفع) من ملفات عقود PDF. لدينا 200 عقد شهريًا. قالب الاستخراج نفسه في كل مرة."

النتيجة: التوصية باستدعاء LLM واحد. مدخلات/مخرجات ثابتة، القالب نفسه في كل مرة، لا حاجة إلى استرجاع. عبء الوكيل عالي زمن الاستجابة غير مبرَّر. إضافةً: إن كان لديك 10,000 مثال استخراج موسوم، فالضبط الدقيق (fine-tuning) خيار ثانٍ قوي.

**السيناريو ج: مهمة بحث ذاتية**

"راقب أفضل 10 منافسين لدينا. كل اثنين، افحص صفحات أسعارهم وإعلانات وظائفهم ومنشورات مدوّناتهم. ولّد تقرير استخبارات تنافسية مع إبراز التغييرات الأساسية."

النتيجة: التوصية بوكيل مع أدوات. تدفّق عمل متعدد الخطوات (10 منافسين، 3 مصادر بيانات لكل منهم)، يتطلب بيانات حيّة، بمنطق تفرّعي (إبلاغ عن التغييرات فقط مقابل عدمها)، والمخرج يتباين من أسبوع لآخر.

> **نقلة في المنظور:** مطوّر بخلفية في هندسة البرمجيات قد ينظر إلى توصية استدعاء LLM واحد للأسئلة والأجوبة البسيطة فيشعر أنها قليلة الهندسة (under-engineered). في البرمجيات، إضافة طبقات تجريد كثيرًا ما تُسمّى "تصميمًا جيدًا". أما في هندسة الذكاء الاصطناعي، فإضافة استدعاءات LLM وحلقات وكلاء لا تتطلبها المواصفات تُسمّى "التزام صيانة (maintenance liability)". كل خطوة وكيل إضافية هي سطح إخفاق (انتهاء مهلة timeout، خطأ أداة، صيغة مخرج غير متوقعة). أبسط بنية تعمل ليست اختصارًا؛ بل هي انضباط الإنتاج.

---

## التسليم

الأثر القابل لإعادة الاستخدام في هذا الدرس هو `outputs/prompt-pattern-decision-guide.md`: دليل قرار قابل للطباعة يضم الأنماط الخمسة، ومحاور القرار، وبطاقة تحذير عدم التطابق، وورقة تسجيل درجات فارغة. استخدمه في بداية كل بناء لتوثيق قرار النمط قبل كتابة الكود.

---

## التقييم

كيف تعرف أن عملية قرار النمط تعمل:

1. **توثيق قرار النمط قبل البناء** - أكثر الفحوص مباشرةً. هل توجد ورقة قرار نمط في المستودع (repo) قبل أول حفظ (commit) للتنفيذ؟ إن لم توجد، فالقرار كان ضمنيًا ولا يمكن مراجعته أو تعديله.

2. **تبديلات النمط أثناء البناء** - تابع كم مرة يتغيّر النمط بعد بدء البناء (مثلًا، بدأ بالوكلاء ثم بدّل إلى استدعاء واحد). تبديل النمط في منتصف البناء يشير إلى أن النمط الأولي اختير بلا تحليل. قرار نمط موثّق جيدًا يقلّل تبديلات منتصف البناء بالتقاط حالات عدم التطابق قبل بنائها.

3. **زمن الاستجابة مقابل التنبؤ** - بالنسبة للمتطلبات الحسّاسة لزمن الاستجابة، هل حقّق النمط المختار متطلب زمن الاستجابة في الإنتاج؟ إن قال متطلب "< 2s" واخترت الوكلاء، فغالبًا أخفقت في ذلك. تابِع تنبؤات زمن الاستجابة مقابل زمن الاستجابة الإنتاجي لكل نمط.

4. **مراجعة استرجاعية للنمط بعد البناء** - في نهاية كل ارتباط، اسأل: هل كان النمط الذي اخترناه صحيحًا؟ وإن لم يكن، أيّ المحاور أسأنا تقديرها؟ ابنِ سجلًا فريقيًا لقرارات الأنماط ونتائجها لمعايرة مصفوفة القرار مع الوقت.
