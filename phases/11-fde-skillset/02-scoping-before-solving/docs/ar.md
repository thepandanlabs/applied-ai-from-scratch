# تحديد النطاق قبل الحل

> "نريد ذكاءً اصطناعيًا" ليس متطلبًا. وظيفتك أن تستخرج متطلبًا منه.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 11-01 ما الذي يفعله الـ FDE فعليًا
**الوقت:** ~60 دقيقة
**المرحلة:** 11 - مهارات الـ FDE

## أهداف التعلّم

- التعرّف على أسئلة تحديد النطاق (scoping) الخمسة التي تحوّل الطلب الغامض إلى متطلب قابل للبناء
- إدراك أكثر ثلاثة أنماط مضادة (anti-patterns) شيوعًا في تحديد النطاق وعواقبها
- بناء أداة CLI باسم ScopingInterview تُجري مقابلة عميل منظّمة وتنتج وثيقة نطاق (scope document)
- تطبيق الأداة على سيناريو عميل واقعي وإنتاج وثيقة نطاق في أقل من 30 دقيقة
- شرح سبب كون سؤال نقطة التكامل (integration point) هو الأكثر تخطّيًا

---

## المشكلة

يقول العميل: "نريد ذكاءً اصطناعيًا لمساعدة فريق الدعم لدينا." توافق بإيماءة، وتفتح حاسوبك، وتبدأ بتركيب هيكل لروبوت دعم. بعد ثلاثة أسابيع، تعرض مُصنِّفًا للتذاكر يعمل مع ردود مُصاغة تلقائيًا. يقول العميل إنه يبدو رائعًا. ثم يسأل: "كيف يتصل بـ Zendesk؟"

ليس لديك إجابة. لدى Zendesk واجهة API، لكن خطة العميل لا تتضمّن الوصول إلى الـ API. تذاكرهم مخزّنة في صندوق وارد مشترك على Gmail. البيانات التي تحتاجها محجوزة خلف تدفّق OAuth يتطلب موافقة فريق تقنية المعلومات (IT) لديهم، وهي تستغرق أسبوعين. عرضك يعمل. أما تكاملك فلا. وتُعلَّق التجربة الأولية.

هذا إخفاق في تحديد النطاق. سؤال Zendesk ليس مفاجأة تقنية: بل سؤال كان ينبغي طرحه في اليوم الأول. مقابلة تحديد النطاق موجودة لإبراز هذه العوائق قبل أن تكتب سطرًا واحدًا من الكود. المطوّرون الذين يتخطّونها يبنون النظام الصحيح للبيئة الخطأ.

---

## المفهوم

### من الطلب الغامض إلى المتطلب المُحدَّد النطاق

الضغط (compression) الذي يحدث عند كل سؤال:

```
Customer input           Question asked               Output

"We want AI to           "What is the current    --> "Support agents spend
help our support         process step that            4 hours/day manually
team"                    takes the most time?"        triaging Tier 1 tickets"

"Reduce how long         "What does success      --> "Reduce Tier 1 first
it takes"                look like in a               response time from
                         number?"                     4 hours to 30 minutes"

"We have all our         "Who owns the data,     --> "Gmail shared inbox,
ticket history"          and what format              IT approval needed
                         is it in?"                   for OAuth access"

"It should connect       "Where exactly does     --> "Agent drafts response
to our workflow"         the output go and            in Gmail, human
                         who acts on it?"             reviews before send"

"We don't want it        "What is explicitly     --> "No auto-send.
to do everything"        out of scope?"               No Tier 2 routing.
                                                       No Spanish language."
```

كل سؤال يضغط حالة عدم اليقين. وبحلول السؤال الخامس، يكون لديك متطلب قابل للبناء، قابل للقياس، ومؤكَّد التكامل.

### أسئلة تحديد النطاق الخمسة

```
Q1: CURRENT PROCESS
    "Walk me through the current manual process, step by step."
    Goal: Understand what you are replacing or augmenting.
    Anti-pattern: Skipping this and assuming you understand the domain.

Q2: FAILURE POINT
    "Where does this process break down or take too long?"
    Goal: Find the pain point worth solving.
    Anti-pattern: Accepting "everything takes too long" as an answer.

Q3: SUCCESS METRIC
    "What does success look like as a specific number in 90 days?"
    Goal: Establish the eval criterion before the build starts.
    Anti-pattern: Accepting "faster" or "better" without a number.

Q4: DATA OWNERSHIP
    "Who owns the data the system needs, in what format, and can we
     get access this week?"
    Goal: Surface data blockers before they become timeline killers.
    Anti-pattern: Assuming access because the customer offered to "share."

Q5: INTEGRATION POINT
    "Where exactly does the AI output go, and who acts on it next?"
    Goal: Confirm the output lands somewhere usable.
    Anti-pattern: Skipping this because "we'll figure out integration later."
```

### الأنماط المضادة الثلاثة في تحديد النطاق

```
Anti-pattern            Symptom                     Consequence
---------------------   -------------------------   -----------------------
Jumping to solution     You sketch an architecture  You build the wrong
                        before Q1 is answered       thing. Correctly.

Accepting vague         Success = "make it          You have no eval
success criteria        smarter / faster"           criterion. The demo
                                                    "looks good" and no
                                                    one can prove it works.

Assuming data access    "We have all the data"       Week 2 blocker: IT
                        without confirming           approval, format mismatch,
                        format and access path       or GDPR restriction
```

---

## البناء

ابنِ أداة CLI باسم `ScopingInterview` تمرّ عبر مجالات الأسئلة الخمسة، وتلتقط الإجابات، وتنتج وثيقة نطاق منظّمة بصيغتي JSON والصيغة القابلة للقراءة البشرية معًا.

تسأل الأداة عن كل مجال سؤال مع متابعات (follow-up) إن كانت الإجابة غامضة جدًا. وتكتشف الإجابات النمطية المضادة الشائعة (إجابات بلا رقم للسؤال Q3، إجابات بلا اسم مالك بيانات للسؤال Q4) وتُشير إليها.

```python
# Key structure: each question area has a primary prompt,
# a vagueness detector, and a follow-up

QUESTION_AREAS = [
    {
        "id": "current_process",
        "label": "Current Process",
        "prompt": "Walk me through the current manual process, step by step.",
        "follow_up": "Roughly how many people do this, and how many times per day?",
        "vague_signals": ["it depends", "varies", "sometimes"],
        "vague_follow_up": "Can you give me the most common case, even if it's not universal?",
    },
    # ... 4 more
]
```

شغّل المقابلة:

```bash
python main.py
python main.py --output scope-document.json
```

مثال على المخرج:

```
=== SCOPING INTERVIEW ===
This interview takes 15-20 minutes. Answer as specifically as possible.
Vague answers will be flagged for follow-up.

--- CURRENT PROCESS ---
Walk me through the current manual process, step by step.
> Agents read incoming tickets, categorize them, and write a response.

Roughly how many people do this, and how many times per day?
> 8 agents, about 200 tickets per day total.

--- FAILURE POINT ---
Where does this process break down or take the most time?
> Categorization takes too long, especially for new agents.

[FLAG] Your answer does not include a time estimate.
How long does categorization take on average, per ticket?
> About 8 minutes per ticket for new agents, 2 minutes for experienced ones.

...

=== SCOPE DOCUMENT ===

Problem:
  Ticket categorization takes 8 min/ticket for new agents (vs. 2 min for
  experienced agents). With 200 tickets/day, new agents account for 30%
  of volume = 480 agent-minutes/day on categorization alone.

Success metric:
  Reduce average categorization time for new agents to under 3 minutes
  within 60 days of deployment.

Data: Zendesk tickets, owned by Support Ops (Maria Chen).
  Access path: Zendesk API, IT approval required (2-3 days).
  Format: JSON via REST API, 18 months of history available.

Integration point:
  AI suggests category in Zendesk sidebar. Agent confirms or overrides.
  No auto-assignment without human review.

Out of scope:
  Response drafting, Tier 2 routing, Spanish language support.
```

> **اختبار من الواقع:** تُجري مقابلة تحديد النطاق فيعطيك العميل إجابة غامضة للسؤال Q3: "نريده فقط أن يكون أسرع." تُشير الأداة إليها. تطلب رقمًا. فيقول العميل: "لا أعرف أيّ رقم أعطيك إيّاه." ماذا يخبرك هذا؟ يخبرك أن العميل لا يملك قياسًا أساسيًا (baseline). لا يوجد مؤقّت على العملية الحالية. هذا عائق في تحديد النطاق، لا خطأ تقريب. إجراؤك التالي أن تراقب العملية لمدة 30 دقيقة وتقيسها بنفسك، أو تطلب من العميل إجراء تمرين قياس لمدة أسبوع قبل أن تحدّد نطاق البناء. البناء بلا قياس أساسي يعني أنك لا تستطيع إثبات أن النظام نجح.

التنفيذ الكامل في `code/main.py`. وهو يتعامل مع المدخلات متعددة الأسطر، واكتشاف الغموض، ومنطق المتابعة، وينتج وثيقة نطاق منظّمة بصيغة JSON إضافةً إلى ملخّص بصيغة markdown.

---

## الاستخدام

طبّق ScopingInterview على السيناريو: "نريد ذكاءً اصطناعيًا لمساعدة فريق الدعم لدينا على الرد بشكل أسرع."

شغّل:
```bash
python main.py --output support-scope.json
```

امضِ عبر كل مجال سؤال بإجابات واقعية:

- **العملية الحالية:** يقرأ الموظفون تذاكر Zendesk يدويًا ويصنّفونها ويردّون عليها. 10 موظفين، 300 تذكرة/يوم.
- **نقطة الإخفاق:** متوسط زمن أول استجابة 4 ساعات للمستوى الأول (Tier 1). اتفاقية مستوى الخدمة (SLA) ساعتان. يُخفَق في الالتزام بالـ SLA في 40% من الحالات.
- **مقياس النجاح:** تقليص زمن أول استجابة للمستوى الأول من 4 ساعات إلى أقل من ساعتين. الالتزام بالـ SLA في 90% من الحالات.
- **البيانات:** Zendesk، يملكها رئيس الدعم (James Li). الوصول إلى الـ API متاح بمفتاح المدير (admin key). سجلّ تذاكر لمدة سنتين.
- **نقطة التكامل:** يُصيغ الذكاء الاصطناعي ردًا في صندوق الرد في Zendesk. يحرّره الموظف ويرسله. لا إرسال تلقائي (auto-send).
- **خارج النطاق:** تذاكر المستوى الثاني (Tier 2)، استفسارات الفوترة، التذاكر بغير الإنجليزية.

تنتج الأداة:

```json
{
  "problem": "Tier 1 first-response time averages 4 hours against a 2-hour SLA. Missing SLA 40% of the time across 300 tickets/day.",
  "success_metric": "Reduce Tier 1 first-response time to under 2 hours. Achieve SLA compliance rate of 90% within 60 days.",
  "data": {
    "source": "Zendesk",
    "owner": "James Li, Head of Support",
    "access": "Admin API key available",
    "volume": "2 years of ticket history"
  },
  "integration_point": "AI draft in Zendesk reply box. Agent reviews and sends. No auto-send.",
  "out_of_scope": ["Tier 2 tickets", "billing inquiries", "non-English tickets"],
  "flags": []
}
```

لا إشارات (flags). هذا نطاق نظيف. الآن يمكنك البناء.

> **نقلة في المنظور:** مدير منتج (product manager) يقرأ وثيقة النطاق هذه قد يقول إنها تبدو كوثيقة متطلبات معتادة. هي كذلك، لكن بفارق واحد: مقياس النجاح هو معيار التقييم (eval criterion). حين تبني إطار التقييم في المرحلة 05، لا يكون السؤال "هل يبدو المخرج معقولًا؟" بل "هل ينخفض متوسط زمن أول استجابة دون ساعتين على مجموعة احتجاز (holdout set) من 100 تذكرة؟" مقابلة تحديد النطاق تزرع بذرة التقييم قبل كتابة أول سطر كود. وثائق المتطلبات التي لا تفعل ذلك تنتج أنظمة لا يمكن قياسها، ومن ثَمّ لا يمكن تحسينها.

---

## التسليم

الأثر القابل لإعادة الاستخدام في هذا الدرس هو `outputs/prompt-scoping-interview-guide.md`: دليل منظّم لإجراء مقابلة تحديد النطاق يدويًا (بدون الـ CLI)، مع الأسئلة الخمسة، ومحفّزات المتابعة، وإشارات الغموض، وتحذيرات الأنماط المضادة. استخدمه في مكالمات العملاء حين لا تستطيع تشغيل الـ CLI تفاعليًا.

---

## التقييم

كيف تعرف أن مقابلة تحديد النطاق تعمل:

1. **إنتاج وثيقة النطاق قبل بدء البناء** - أبسط فحص. إذا بدأ المهندسون البناء قبل وجود وثيقة نطاق مكتوبة بمقياس نجاح، فالمقابلة لم تحدث. قِس الفجوة بين بداية الارتباط وأول حفظ (commit) لوثيقة النطاق.

2. **درجة دقّة مقياس النجاح** - راجع وثائق النطاق من حيث جودة المقياس: هل يحتوي على رقم وقياس أساسي وأفق زمني ومصدر بيانات؟ مقياس مثل "تقليص زمن الاستجابة بنسبة 50% خلال 60 يومًا مقاسًا عبر متوسط Zendesk" يسجّل 4/4. أما "اجعله أسرع" فيسجّل 0/4.

3. **تأكيد الوصول إلى البيانات قبل نهاية الأسبوع الأول** - تتبّع ما إذا كان الوصول إلى البيانات قد تأكّد (اختُبِر فعليًا، لا مجرد وعد) قبل بدء أول دورة بناء. عدم تأكيد الوصول إلى البيانات في نهاية الأسبوع الأول يتنبأ بعائق في الأسبوع الثاني بموثوقية تفوق 80%.

4. **تأكيد نقطة التكامل قبل النموذج الأولي** - افحص ما إذا كانت وجهة المخرج قد تأكّدت قبل بناء النموذج الأولي. المهندسون الذين يكتشفون قيد التكامل بعد البناء يهدرون في المتوسط 3-5 أيام في إعادة بناء صيغة المخرج.
