# تجهيز الـ portfolio والتحضير للمقابلات

> الـ portfolio (ملفّ أعمالك) ليس الشيفرة. إنه الحجّة على أنك قادر على أداء العمل.

**النوع:** تعلّم
**اللغات:** Python
**المتطلبات:** كل المراحل السابقة
**الوقت:** ~2 ساعة
**المرحلة:** 12 · الكابستونات (Capstones)

---

## أهداف التعلّم

- صياغة الأسئلة الثلاثة التي يطرحها كل مُحاوِر لوظيفة Applied AI Engineer وFDE، وربط مُخرَجات منهجك بكلٍّ منها
- توليد ملف PORTFOLIO.md منسّق يجمّع المُخرَجات حسب المرحلة ويُبرز أقوى مشاريع الكابستون
- كتابة وصف مشروع (writeup) لأي كابستون يجيب عن الأسئلة الثلاثة للمُحاوِر في أقل من 300 كلمة
- استخدام قالب موجّه عرض الـ portfolio لتوليد خطاب تغطية ووصف مشروع مُصمَّم لأي إعلان وظيفي
- تحديد أي المُخرَجات تُبرزها لأدوار Applied AI Engineer مقابل FDE مقابل AI Solutions Engineer

---

## المشكلة

أنهيت 12 مرحلة من عمل هندسة الذكاء الاصطناعي. لديك نحو 150 مُخرَجًا قابلًا لإعادة الاستخدام، و8 مشاريع كابستون أو أكثر، وخبرة عملية في هندسة السياق (context engineering)، والـ RAG، والوكلاء، والتقييم، والتسليم، والملاحظة (observability)، والأمن، والضبط الدقيق (fine-tuning)، والوسائط المتعدّدة، ومهارات الـ FDE.

لكن مدير التوظيف الذي يفتح مستودع GitHub الخاص بك يرى 150 ملفًا منظّمة برقم المرحلة وبلا سرد. لديه 30 ثانية قبل أن يقرّر ما إذا كان سيستمرّ في القراءة.

المشكلة ليست في العمل. المشكلة في العرض. مهندسون أقوياء يخسرون فرصًا لصالح مرشّحين أضعف يجهّزون أعمالهم بشكل أفضل. يحتاج الـ portfolio لديك إلى الإجابة عن ثلاثة أسئلة في 30 ثانية، وإلا فإن بقيّة العمل غير مرئية.

هذا الدرس عن بناء طبقة التجهيز: الفهرس المُولَّد، وأوصاف المشاريع، وقالب الموجّه الذي يخصّص العرض لأي دور محدّد.

---

## المفهوم

### اختبار الأسئلة الثلاثة

كل مُحاوِر لأدوار Applied AI Engineer وFDE وAI Solutions Engineer يطرح في الحقيقة ثلاثة أسئلة. قد لا يقولها بصوت عالٍ، لكن كل سؤال يطرحه هو وكيل لأحدها:

```
QUESTION 1: Can you build it?
  Evidence: capstone projects with working code and measurable results
  What they fear: engineers who know the theory but cannot ship

QUESTION 2: Do you know when NOT to build it?
  Evidence: pattern decision artifacts, AI specs with explicit out-of-scope sections,
            scoping writeups that rejected complexity
  What they fear: engineers who reach for agents when a prompt would do

QUESTION 3: Can you deliver it to a customer?
  Evidence: FDE engagement, handoff packages, eval reports with go/no-go decisions,
            runbooks written for non-engineers
  What they fear: engineers who build but cannot communicate, scope, or hand off
```

منهجك فيه دليل على الثلاثة كلها. مهمّة التجهيز هي إبراز ذلك الدليل بالترتيب الصحيح للجمهور الصحيح.

### خريطة المُخرَجات: من الكابستونات إلى متطلبات الوظيفة

```
ROLE: Applied AI Engineer
Key requirements: build and evaluate LLM systems, prompt engineering,
                  RAG, agents, production deployment, observability
Top artifacts to surface:
  - P12-01 through P12-04: capstone projects (build evidence)
  - P05 eval artifacts: RAGAS eval harness, LLM-as-judge framework
  - P06 shipping: FastAPI service template, Docker deployment pattern
  - P07 observability: Langfuse integration, GenAI tracing guide
  - P02 RAG artifacts: retrieval pipeline, chunking strategy guide

ROLE: Forward-Deployed Engineer (FDE)
Key requirements: customer discovery, scoping, demos that work on real data,
                  handoff packages, business impact measurement
Top artifacts to surface:
  - P12-05: FDE mock engagement (this capstone - the whole thing)
  - P11 artifacts: scoping interview guide, AI spec template, handoff template
  - P12-02 customer support agent: agent with production constraints
  - P05 evals: go/no-go decision framework
  - P08 security: guardrails and input validation (customers ask about safety)

ROLE: AI Solutions Engineer
Key requirements: technical sales support, POCs, integration patterns,
                  explaining tradeoffs to non-technical stakeholders
Top artifacts to surface:
  - P11 communication artifact: stakeholder presentation template
  - P12-01 through P12-05: all capstones (breadth evidence)
  - P04 agents: pattern selection guide
  - P03 tools/MCP: integration patterns
  - P05 evals: evidence that you measure before you claim
```

### بنية سرد الـ portfolio

```
HERO SECTION (30 seconds)
  Name, role target, one-line summary
  3-5 featured projects with outcome statements

PROJECT WRITEUPS (3 minutes each)
  The problem (1 sentence): what real pain did this solve?
  The build (2-3 sentences): what did you build and how?
  The result (1-2 sentences): what did you measure, what worked?
  The artifact (link): what can they reuse or review?

ARTIFACT INDEX (searchable reference)
  All artifacts grouped by phase and type
  Skill, prompt, runbook, eval, service-template labels
  Quick-filter by role relevance
```

---

## البناء

### أداة CLI لمولّد الـ portfolio

أداة الـ CLI في `code/main.py` تقرأ `outputs/index.json` (فهرس مُخرَجات المنهج)، وتجمّع المُخرَجات حسب المرحلة والنوع، وتولّد ملف `PORTFOLIO.md` مع:
- جدول ملخّص للمشاريع (مشاريع الكابستون فقط)
- عدد المُخرَجات حسب المرحلة والنوع
- قائمة "المشاريع المُميَّزة" المُوصى بها: المُخرَجات الخمسة الأكثر ملاءمة لطلب وظيفة
- سرد مقابلة نموذجي من قالب مدمج

```bash
# Generate PORTFOLIO.md from the artifact index
python main.py --generate

# Generate with a role filter (emphasizes relevant artifacts)
python main.py --generate --role fde
python main.py --generate --role applied-ai-engineer
python main.py --generate --role solutions-engineer

# Count artifacts by type across all phases
python main.py --count

# Generate a sample interview narrative for a specific capstone
python main.py --narrative --project email-triage
```

وضع العرض التوضيحي (لا يتطلّب index.json) يستخدم قائمة مُخرَجات مكتوبة في الشيفرة تعكس المنهج الكامل:

```bash
python main.py --demo --generate
```

> **اختبار من الواقع:** لماذا تولّد PORTFOLIO.md من سكربت بدلًا من كتابته يدويًا؟ المنهج فيه نحو 150 مُخرَجًا عبر 12 مرحلة. أي فهرس مكتوب يدويًا يتقادم لحظة إضافتك مُخرَجًا جديدًا. المولّد يعمل على الحالة الراهنة للمستودع. والأهم، السكربت الذي يولّد portfolio من بيانات منظّمة هو بحدّ ذاته دليل portfolio - فهو يُظهر أنك تفكّر في قابلية الصيانة.

### خوارزمية اختيار المشاريع المُميَّزة

يستخدم السكربت أسلوبًا حسابيًا (heuristic) بسيطًا للتقييم:

```python
FEATURE_PROJECT_SCORES = {
    "capstone": 10,   # Any phase 12 lesson
    "runbook": 7,     # Operational artifact
    "eval": 6,        # Evaluation artifact
    "service": 5,     # Deployable service
    "prompt": 4,      # Reusable prompt
    "skill": 3,       # Process skill
}
```

تحصل الكابستونات دائمًا على أعلى الدرجات. وضمن الكابستونات، تلك التي فيها مُخرَج تقييم go/no-go تتفوّق على التي بدونه. تصبح الخمسة الأعلى قائمة المشاريع المُميَّزة في `PORTFOLIO.md`.

---

## الاستخدام

### ملف README على GitHub مع شارات (Badges)

المُخرَج نفسه منسّقًا كملف README على GitHub:

```markdown
# Applied AI From Scratch

![Lessons complete](https://img.shields.io/badge/lessons-157-green)
![Phases done](https://img.shields.io/badge/phases-12-blue)
![Artifacts built](https://img.shields.io/badge/artifacts-~150-orange)

## Featured Projects

| Project | What it demonstrates | Artifact |
|---------|---------------------|---------|
| Email Triage MVP | FDE engagement, go/no-go eval, handoff | runbook-fde-engagement-playbook.md |
| RAG Production Pipeline | Retrieval, chunking, RAGAS evaluation | rag-pipeline-template.md |
| Customer Support Agent | Agent patterns, tool use, safety | skill-agent-implementation-guide.md |
| Text-to-SQL Analytics | Tool calling, structured output | skill-sql-agent-safety-guide.md |
| Coding Automation Agent | Agents, code execution, safety | skill-coding-agent-patterns.md |
```

### قسم Featured على LinkedIn

المشاريع المُميَّزة الخمسة تُربَط مباشرةً بمدخلات Featured على LinkedIn. لكلٍّ منها:
1. خذ وصف المشروع المُولَّد بواسطة `python main.py --narrative`
2. أضف رابطًا إلى مجلد GitHub (لا ملف المُخرَج - بل المجلد مع سياق README)
3. اضبط الصورة المصغّرة على لقطة شاشة لمُخرَج التقييم أو مخطّط المعمارية
4. استخدم عبارة النتيجة كوصف LinkedIn (أقل من 200 حرف)

> **نقلة في المنظور:** المُجنِّدون ومديرو التوظيف في الشركات المتقدّمة في الذكاء الاصطناعي لا يقرؤون مستودعات GitHub سطرًا سطرًا. إنهم يبحثون عن إشارة بمطابقة الأنماط: "هل أطلق هذا الشخص شيئًا من البداية إلى النهاية؟ هل يعرف كيف يقيّمه؟ هل وثّقه؟" مولّد الـ portfolio لا يتعلّق بإبهار المهندسين - بل بأن تكون قابلًا للقراءة من قِبل الأشخاص الذين يقرّرون ما إذا كانوا سيمرّرونك إلى المقابلة الهندسية.

---

## التسليم

مُخرَج هذا الدرس في `outputs/prompt-portfolio-presentation-guide.md`.

يحتوي على قالب موجّه قابل لإعادة الاستخدام يأخذ:
- إعلانًا وظيفيًا (رابط أو نصًّا ملصوقًا)
- أفضل 3 مشاريع كابستون لك من هذا المنهج
- دورك المستهدف (Applied AI Engineer / FDE / Solutions Engineer)

ويُخرِج:
- وصف مشروع مُصمَّم يربط عمل منهجك بمتطلبات الوظيفة
- المُخرَجات الثلاثة الأكثر ملاءمة لإبرازها لذلك الدور المحدّد
- 5 أسئلة مقابلة محتملة مع أطر إجابات مبنية على مُخرَجاتك

القالب مصمّم للاستخدام مع Claude أو GPT-4 أو أي نموذج رائد (frontier model). إنه موجّه، لا سكربت.

---

## التقييم

### هل يعمل المولّد؟

شغّل على حالة المنهج:

```bash
python main.py --demo --generate
```

تحقّق:
1. كل مشروع كابستون (P12-01 حتى P12-07) يظهر في جدول المشاريع المُميَّزة
2. أعداد المُخرَجات حسب المرحلة غير صفرية للمراحل 00-12
3. مُخرَجات الـ runbook تتفوّق على مُخرَجات الموجّه البسيطة في اختيار المشاريع المُميَّزة
4. ملف PORTFOLIO.md المُولَّد بلا نص نائب (لا أقسام `[fill in]`)

### هل يجيب السرد عن الأسئلة الثلاثة؟

لكل وصف مشروع مُميَّز، تحقّق يدويًا:
- س1 (هل يمكنك بناؤه؟): هل هناك وصف تقني محدّد بمُخرَج قابل للقياس؟
- س2 (هل تعرف متى لا تفعل؟): هل ذُكر قرار تحديد نطاق أو اختيار نمط؟
- س3 (هل يمكنك تسليمه؟): هل أُشير إلى مُخرَج تسليم أو نتيجة تقييم؟

إذا أغفل أي وصف أحد الأسئلة الثلاثة، فراجع قالب السرد.

### فحص المواءمة مع الدور

شغّل مرشّحات الأدوار الثلاثة وتحقّق من أن ترتيب المُخرَجات يتغيّر بشكل مناسب:

```bash
python main.py --demo --generate --role fde         # P12-05 and P11 artifacts ranked highest
python main.py --demo --generate --role applied-ai-engineer  # P05 and P12 capstones ranked highest
python main.py --demo --generate --role solutions-engineer   # P11 comms + all capstones ranked
```

يجب أن تختلف قائمة المشاريع المُميَّزة اختلافًا ملموسًا بين الأدوار. إذا ظهرت المُخرَجات الخمسة نفسها للأدوار الثلاثة كلها، فإن أوزان التقييم تحتاج إلى تعديل.
