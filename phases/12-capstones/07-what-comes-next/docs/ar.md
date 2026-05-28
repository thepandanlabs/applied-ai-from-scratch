# ماذا بعد

> المجال يتحرّك بسرعة. مهمّتك ليست مواكبة كل شيء - بل امتلاك الأسس التي تتيح لك تقييم ما يهمّ.

**النوع:** تعلّم
**اللغات:** Python
**المتطلبات:** كل المراحل السابقة
**الوقت:** ~1.5 ساعة
**المرحلة:** 12 · الكابستونات (Capstones)

---

## أهداف التعلّم

- التمييز بين الأسس المستقرة لهندسة الذكاء الاصطناعي (التي تتغيّر ببطء) والمساحة سريعة الحركة (التي تتغيّر أسبوعيًا)
- تحديد مصادر المعلومات الأربعة الجديرة بالمتابعة وشرح أهمية كلٍّ منها
- تطبيق قائمة تحقق تقييم "الأداة الجديدة" على أي إطار أو إصدار نموذج
- توليد خطة تدريب لأربعة أسابيع لهدف تعلّم محدّد باستخدام الـ CLI
- إكمال حلقة المنهج: مواءمة قدراتك الحالية مع الدور الذي استهدفته في البداية

---

## المشكلة

أنهيت المنهج. النموذج الذي استخدمته في المرحلة 01 قد يكون له بالفعل خلَف. والإطار الذي تعلّمته في المرحلة 04 قد يكون أصدر تغييرًا كاسرًا (breaking change). وظهرت مكتبتا تنسيق وكلاء (orchestration) جديدتان بينما كنت تعمل على المرحلة 09.

مجال هندسة الذكاء الاصطناعي يتحرّك أسرع مما يستطيع أي منهج مواكبته. هذه ليست مشكلة في المنهج - إنها سمة من سمات المجال. السؤال ليس "كيف أواكب كل شيء؟" فهذا السؤال بلا إجابة جيدة. السؤال هو: "كيف أبقى فعّالًا في مجال يتغيّر أسرع مما أستطيع القراءة عنه؟"

الإجابة من شقّين. الأول: الأسس التي بنيتها في هذا المنهج لا تتغيّر بسرعة. هندسة السياق، والتطوير المُوجَّه بالتقييم، والفرق بين الموجّه (router) والوكيل (agent)، وكيفية تسليم نظام - هذه لن تختفي. الثاني: معظم ما يبدو "جديدًا" في هندسة الذكاء الاصطناعي هو مساحة جديدة فوق أسس مستقرة. النموذج الجديد ما زال يُقيَّم بمجموعة ذهبية (golden set). والإطار الجديد ما زال مسألة اختيار نمط. وأداة النشر الجديدة ما زالت شأنًا من شؤون التسليم.

مهمّتك ليست قراءة كل شيء. مهمّتك أن تعرف أي الأسس حاملة للأثقال، حتى تستطيع تقييم المساحة الجديدة بسرعة.

---

## المفهوم

### الأسس مقابل المساحة السطحية

```
STABLE FOUNDATIONS (change in years)
+------------------------------------------+
| Context engineering principles           |
| Evaluation-driven development            |
| Pattern selection (router/RAG/agent)     |
| Go/no-go decision with evidence          |
| Handoff package disciplines              |
| Prompt design fundamentals               |
| Golden set construction                  |
+------------------------------------------+
         |
         | (frameworks sit on top of these)
         v
FAST-MOVING SURFACE (change in months)
+------------------------------------------+
| Specific model versions                  |
| Framework APIs (LangChain, LlamaIndex)   |
| Orchestration libraries                  |
| Deployment tooling                       |
| Benchmark scores                         |
| New modalities                           |
+------------------------------------------+
         |
         | (noise sits on top of these)
         v
NOISE (changes daily, mostly irrelevant)
+------------------------------------------+
| Twitter/X AI hot takes                   |
| Most benchmark announcements             |
| "Best practices" blog posts without evals|
| New model releases without papers        |
| Framework release announcements          |
+------------------------------------------+
```

حين يظهر شيء جديد، السؤال الأول هو: في أي طبقة هو؟ إن كان ضجيجًا (noise)، فتخطّه. وإن كان مساحة سطحية، فطبّق قائمة تحقق الأداة الجديدة. وإن كان يتحدّى أساسًا، فادرسه بعناية.

### المصادر الأربعة التي تهمّ

ليست كل المعلومات جديرة باهتمامك. أربعة مصادر أنتجت باستمرار نسبة إشارة إلى ضجيج عالية لهندسة الذكاء الاصطناعي التطبيقية:

**1. ملاحظات إصدار Anthropic وOpenAI (release notes - لا منشورات المدوّنات)**
لماذا: تخبرك بما تغيّر في النماذج والـ APIs التي تستخدمها فعلًا. منشورات المدوّنات تخبرك بما يريدونك أن تظنّه. ملاحظات الإصدار تخبرك بما أُطلق فعلًا.

**2. بودكاست Latent Space ‏(latent.space)**
لماذا: يُجري المُضيفون مقابلات مع المهندسين الذين بنوا الأنظمة، لا مع فريق التسويق. العمق التقني حقيقي ومرشّح "ما الذي يعمل فعلًا في الإنتاج" ثابت.

**3. ‏applied-llms.org**
لماذا: محتوى هندسة تطبيقية مُنتقى. المرشّح هو: "هل اختُبر هذا في الإنتاج؟" نسبة الضجيج منخفضة.

**4. مدوّنة Hamel Husain‏ (hamel.dev)**
لماذا: يعمل Hamel على أنظمة إنتاج حقيقية ويكتب عمّا يجده. محتواه عن التقييمات والضبط الدقيق تحديدًا مؤسَّس على نتائج مقيسة.

كل ما عدا ذلك اختياري. وسائل التواصل الاجتماعي، ونشرات الذكاء الاصطناعي المدعومة من رأس المال المغامر، ومعظم توثيق الأطر يمكن قراءتها عند وجود حاجة محدّدة، لا كمُدخَل محيطي دائم.

### قائمة تحقق الأداة الجديدة

حين يظهر إطار أو نموذج أو مكتبة جديدة:

```
1. PROBLEM CHECK: Does it solve a problem I actually have right now?
   - Yes: continue evaluation
   - No: bookmark, do not read further yet

2. FOUNDATION CHECK: Does it replace something from the stable foundations,
   or is it new surface area on existing foundations?
   - Replaces foundation: study carefully, this is rare and important
   - New surface area: evaluate against your current toolchain

3. EVIDENCE CHECK: Is there a benchmark, eval, or production case study?
   - Yes, from a team that published methodology: worth reading
   - No, or benchmark-only without production evidence: wait for production reports

4. COST CHECK: What does adopting this cost? (migration effort, learning curve,
   lock-in risk, infrastructure change)
   - Low cost, high evidence: try it on a small project
   - High cost, low evidence: do not adopt yet

5. REPLACE CHECK: Does it replace something you already have that works?
   - If you have a working solution: require measured evidence it is better
     before switching. "Newer" is not a reason.
```

### نمط الـ 20% من الوقت

هندسة الذكاء الاصطناعي الإنتاجية ليست مجالًا تبقى فيه مواكبًا عبر القراءة. تبقى مواكبًا عبر البناء. النمط العملي:

- **80% من وقت الهندسة:** العمل الإنتاجي، الأنظمة القائمة، الأنماط المعروفة
- **20% من وقت الهندسة:** الاستكشاف. أداة جديدة واحدة كل ربع سنة، مُقيَّمة على مشكلة حقيقية.

عمل الاستكشاف ينتج أمرين: قدرة جديدة حين تكون الأداة أفضل فعلًا، وحُكمًا مستنيرًا حين لا تكون كذلك. كلاهما ذو قيمة. والـ "جرّبت X وإليك سبب عدم استخدامنا له" المستنير لا يقلّ قيمةً عن "تبنّينا X".

---

## البناء

### أداة CLI لمُوصِي مسار التعلّم

أداة الـ CLI في `code/main.py` تأخذ هدف تعلّم، وتربطه بمُخرَجات منهج محدّدة للمراجعة، وتقترح ثلاث خطوات تالية من قائمة قراءة منتقاة، وتولّد خطة تدريب لأربعة أسابيع. وضع العرض التوضيحي لا يتطلّب أي نداءات API.

```bash
# Demo mode: no API key required
python main.py --demo "get better at eval-driven development"
python main.py --demo "prepare for FDE interviews"
python main.py --demo "understand agent patterns better"

# With Claude for more specific plans
python main.py --goal "build production RAG systems" --weeks 4
python main.py --goal "improve my observability practices" --weeks 6
```

**مُخرَج وضع العرض التوضيحي لـ "get better at eval-driven development":**

```
Learning Goal: get better at eval-driven development

Review these curriculum artifacts first:
  - skill-golden-set-builder.md (P05-02): Golden set construction methodology
  - eval-llm-as-judge-template.md (P05-04): LLM-as-judge evaluation template
  - prompt-go-no-go-decision.md (P05-06): Go/no-go decision framework
  - skill-eval-driven-dev-guide.md (P05-09): Eval-driven development workflow

Three next steps:
  1. Read: "Your AI Product Needs Evals" - Hamel Husain (hamel.dev)
  2. Build: Add a golden set eval to a project you have deployed. Measure quality
     baseline before making any prompt change.
  3. Study: Anthropic's evals documentation for model-graded evals
     (docs.anthropic.com/en/docs/test-and-evaluate)

4-Week Practice Plan:
  Week 1: Rebuild the P05 eval harness from scratch on a new use case
  Week 2: Write an LLM-as-judge prompt, test its agreement rate with human labels
  Week 3: Make 3 prompt changes to an existing project, use eval to decide which to keep
  Week 4: Write a go/no-go report with supporting evidence for a real or synthetic deployment
```

> **اختبار من الواقع:** لماذا يعمل وضع العرض التوضيحي دون نداء API؟ التعيين من أهداف التعلّم إلى مُخرَجات المنهج حتمي (deterministic): "eval" يُعيَّن إلى مُخرَجات المرحلة 05، و"agents" إلى المرحلة 04، و"FDE" إلى المرحلة 11. استخدام نموذج لغوي لهذا البحث يضيف زمن استجابة وتكلفة بلا مكسب في الجودة. نداءات الـ API تستحقّ تكلفتها حين تتطلّب المهمّة استدلالًا على مُدخَل مفتوح - لا حين تكون بحثًا منظّمًا.

---

## الاستخدام

### Claude كمدرّب تعلّم

أعطِ Claude سياق المنهج واطلب منه توليد خطة 90 يومًا مخصّصة:

```
I have completed a 12-phase Applied AI engineering curriculum covering:
- Phase 01: Context engineering and prompt design
- Phase 02: RAG and retrieval pipelines
- Phase 03: Tools and MCP
- Phase 04: Agents and multi-agent patterns
- Phase 05: Evaluation and eval-driven development
- Phase 06: Shipping AI services
- Phase 07: Observability with Langfuse and OpenTelemetry
- Phase 08: Security and guardrails
- Phase 09: Fine-tuning
- Phase 10: Multimodal and voice
- Phase 11: FDE skills (scoping, handoff, stakeholder communication)
- Phase 12: Capstone projects

My target role is: [Applied AI Engineer / FDE / AI Solutions Engineer]
My strongest areas from the curriculum: [list 3]
My weakest areas: [list 2]
My current job context: [brief description, or "job searching"]

Generate a 90-day skill maintenance and growth plan that:
1. Maintains the foundations I built (15 min/day max)
2. Deepens the 2-3 areas most relevant to my target role
3. Includes 5 specific small projects to build over 90 days (buildable in a weekend each)
4. Names 3-5 specific information sources to track (not general "stay current" advice)
5. Ends with a self-assessment question for each of the 5 curriculum pillars
```

### دليل الـ Gate للتقييم الذاتي المستمرّ

استخدم دليل `/gate` من المنهج لفحوص الكفاءة المستمرّة. طبّقه فصليًا:

1. اختر 5 مهام تمثيلية (واحدة لكل ركيزة: السياق، الـ RAG، الوكلاء، التقييم، النشر)
2. حاول كل مهمّة دون النظر إلى ملاحظاتك
3. قارن بمُخرَجات منهجك من حين أكملت كل مرحلة لأول مرة
4. لاحظ أين احتجت إلى الرجوع إلى المواد مقابل أين كنت طليقًا
5. الفجوة هي أولويّتك التالية في التعلّم

> **نقلة في المنظور:** دليل `/gate` مصمّم لتقييم الفهم في نهاية مرحلة. وعند تطبيقه فصليًا على مهاراتك، يصبح أداة مختلفة: تشخيصًا للطلاقة. الهدف ليس النجاح - بل تحديد أي الأسس بقيت حادّة وأيّها انحرف. الانحراف طبيعي. التشخيص يجعله مرئيًا قبل أن يصبح مشكلة في الإنتاج.

---

## التسليم

مُخرَج هذا الدرس في `outputs/prompt-continued-learning-map.md`.

يحتوي على قالب موجّه قابل لإعادة الاستخدام يأخذ:
- دورك المستهدف
- مستوى خبرتك الحالي
- أفضل 3 مجالات لك من هذا المنهج

ويُخرِج:
- خطة صيانة مهارات لمدة 90 يومًا بالتزامات أسبوعية محدّدة
- 5 مشاريع محدّدة لبنائها تاليًا (كلٌّ منها محدّد النطاق لعطلة نهاية أسبوع)
- قائمة قراءة منتقاة من 3-5 مصادر مع سبب محدّد لكلٍّ منها

---

## التقييم

### إغلاق حلقة المنهج

التقييم النهائي هو تقييم ذاتي مقابل الدور الذي استهدفته في بداية المنهج. شغّل دليل `/gate` للمرحلة 12 عبر الركائز الخمس كلها.

**عبارة "أستطيع الآن..."**

أكمل هذا لكل ركيزة. كن محدّدًا - لا صفات بلا مُخرَجات:

```
CONTEXT ENGINEERING (Phase 01)
"I can now: design a system prompt for a multi-step task, set a token budget,
use few-shot examples to shift model behavior, and diagnose a prompt that is
failing its quality target. Evidence: P01 artifacts, P12 capstone prompts."

RETRIEVAL AND RAG (Phase 02)
"I can now: choose a chunking strategy for a given document type, build a
pgvector retrieval pipeline, run a RAGAS evaluation, and interpret the results
to decide whether retrieval quality is good enough to deploy. Evidence: P02 runbook,
P12-01 capstone."

AGENTS (Phase 04)
"I can now: select between a router, single agent, and multi-agent based on
requirements, implement a tool-using agent with safe boundaries, and measure
whether the agent is meeting its quality target. Evidence: P04 runbook,
P12-02 and P12-04 capstones."

AI EVALUATION (Phase 05)
"I can now: build a golden set for a new use case, design an LLM-as-judge
evaluation, make a go/no-go decision with documented evidence, and set up
monitoring to detect post-deployment drift. Evidence: P05 eval artifacts,
P12-05 golden set evaluation."

DEPLOYMENT AND FDE SKILLS (Phases 06, 11)
"I can now: scope an AI engagement from a vague ask to a measurable AI spec,
deploy a service with Docker and FastAPI, produce a four-part handoff package,
and measure business impact against defined success criteria. Evidence:
P11 artifacts, P12-05 FDE engagement runbook."
```

### قياس الفجوة

بعد إكمال عبارات "أستطيع الآن...":

1. اربطها بمتطلبات الوظيفة لدورك المستهدف
2. حدّد مجالًا أو اثنين تبدو فيهما العبارة هزيلة (تستطيع كتابتها لكن لا تستطيع تنفيذها بطلاقة)
3. تصبح تلك المجالات أول بندين في خطّتك لمدة 90 يومًا

المنهج مكتمل. والتعلّم مستمرّ.
