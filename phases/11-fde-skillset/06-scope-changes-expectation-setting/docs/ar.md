# تغييرات النطاق في منتصف العمل وضبط التوقعات

> الإجابة الصحيحة على "هل يمكننا أيضًا إضافة X؟" ليست أبدًا نعم أو لا. بل هي "دعني أقيّم الأثر وأعود إليك خلال 24 ساعة."

**النوع:** تعلّم
**اللغات:** Python
**المتطلبات:** 11-02 (تحديد النطاق قبل الحل)، 11-03 (الاكتشاف: من الطلب الغامض إلى المواصفات)
**الوقت:** ~45 دقيقة
**المرحلة:** 11 · مهارات الـ FDE

---

## أهداف التعلّم

- تصنيف أيّ تغيير نطاق (scope change) وارد بوصفه توضيحًا (clarification) أو توسعة (expansion) أو تحوّلًا جذريًا (pivot)
- شرح أثر كل نوع تغيير على الجدول الزمني والتكلفة وخطر التسليم
- تطبيق قاعدة التوقّف 24 ساعة لحماية الطرفين من القرارات الانفعالية
- بناء أداة CLI تصنّف التغييرات، وتقدّر فارق الجهد (effort delta)، وتصيغ ردًا للعميل
- الحفاظ على وثيقة نطاق حيّة (living scope doc) بقسم "خارج النطاق" موقَّع عليه باعتباره خط دفاعك الأساسي

---

## المشكلة

أنت في أسبوعك الثالث من ارتباط مدته ستة أسابيع. يرسل العميل رسالة على Slack: "مرحبًا، بينما تبني مُصنِّف تذاكر الدعم، هل يمكنك أيضًا جعله يتعامل مع أسئلة الفوترة؟ هذا في الأساس الشيء نفسه، صحيح؟"

هذه واحدة من أخطر ثلاث لحظات في ارتباط الـ FDE. لا لأن الطلب غير معقول، بل لأن كيفية ردّك في الثواني الستين القادمة تحدّد ما إن كنت ستنتهي في الوقت وضمن الميزانية، أو ما إن كنت ستوافق بصمت على تضخّم النطاق (scope creep) الذي يمدّ أسبوعين من العمل إلى خمسة.

نمط الإخفاق ليس سوء نية. العملاء بصدق لا يعرفون أن "أسئلة الفوترة" تعني إعادة تدريب على توزيع بيانات مختلف، وإضافة فئة نيّة (intent) جديدة، وإعادة تقييم المُصنِّف، وتحديث منطق التوجيه، وإعادة كتابة العرض. هم يرون حقل إدخال واحدًا. وأنت ترى نظامًا مختلفًا.

نمط الإخفاق الثاني هو قول "نعم" بلا تفكير لأنك تريد أن تبدو متعاونًا. هذا هو الذي يسبّب هرولات النشر في الساعة الثانية صباحًا، والمواعيد النهائية الضائعة، والعلاقات المتآكلة. العميل ليس سعيدًا حين تسلّم متأخرًا. هو غير سعيد بالمهندس الذي "وافق" على فعل كل شيء.

تحتاج إلى عملية قابلة للتكرار لاستقبال تغييرات النطاق: صنّف النوع، وقيّم الأثر، وتوقّف قبل الرد، وتواصل بوضوح.

---

## المفهوم

### أنواع تغيير النطاق الثلاثة

كل طلب تغيير نطاق يندرج تحت إحدى ثلاث فئات. تصنيفه بشكل صحيح يحدّد الرد الصحيح.

```
CLARIFICATION
  Definition: Same goal, better definition.
  Example: "By 'support tickets' we mean only Tier 1, not billing or returns."
  Impact: Usually reduces scope. Sometimes changes priority.
  Response: Accept immediately, update scope doc, document what changed.

EXPANSION
  Definition: Same goal, more features or coverage.
  Example: "Can we also handle billing questions with the classifier?"
  Impact: Additional work. Days to weeks. May shift delivery date.
  Response: Assess impact, communicate the tradeoff, negotiate or decline.

PIVOT
  Definition: Different goal entirely.
  Example: "Actually, instead of classifying tickets, can we build a chatbot?"
  Impact: Restart. New scoping, new timeline, new budget conversation.
  Response: Stop, scope the new goal from scratch, present options.
```

### شجرة القرار

```
Receive scope change request
           |
           v
 Is the core goal the same?
      |            |
     YES           NO
      |            |
      v            v
 Does it         PIVOT
 add work?     (restart scoping)
  |       |
 YES      NO
  |       |
  v       v
EXPANSION  CLARIFICATION
(negotiate) (accept + update doc)
```

### عُدّة ضبط التوقعات

ثلاث أدوات تحميك من انجراف النطاق:

```
TOOL 1: THE LIVING SCOPE DOC
  - Created at project start
  - Updated after every change
  - Has an explicit "NOT IN SCOPE" section
  - Customer signed off on the original version
  - Change log at the bottom: date, request, decision, who approved

TOOL 2: THE WEEKLY WRITTEN STATUS
  - Sent every Monday morning, no exceptions
  - Format: what shipped last week, what ships next week, blockers, open questions
  - Written, not verbal - creates a paper trail of shared understanding
  - Includes any scope changes discussed that week

TOOL 3: THE 24-HOUR RULE
  - Never respond to a scope change request immediately
  - "Let me assess the impact and get back to you by tomorrow"
  - This pause protects you from reactive yes/no answers
  - And it signals that you take the request seriously
```

### صيغة تقييم الأثر

حين تستقبل طلب توسعة، قدّر الأثر عبر أربعة أبعاد:

```
EFFORT DELTA
  Additional engineering days to implement, test, evaluate, and deploy.
  Always round up. Hidden work is always present.

TIMELINE RISK
  Does this compress any other deliverable?
  What slips if this is added?

EVALUATION COST
  AI systems need evals. New features need new eval sets.
  Budget 20-30% of implementation time for eval work.

DEPENDENCY RISK
  Does the new scope depend on data, access, or decisions
  not yet available? New dependencies = new blockers.
```

---

## البناء

### الخطوة 1: الإعداد

```python
# pip install anthropic
# Set ANTHROPIC_API_KEY in environment

import argparse
import json
import os
import sys
from dataclasses import dataclass
from enum import Enum

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
```

### الخطوة 2: تعداد نوع التغيير ونموذج البيانات

```python
class ChangeType(str, Enum):
    CLARIFICATION = "clarification"
    EXPANSION = "expansion"
    PIVOT = "pivot"


@dataclass
class ScopeChangeAssessment:
    change_type: ChangeType
    effort_delta_days: int
    timeline_risk: str       # "low", "medium", "high"
    rationale: str
    customer_response: str
    scope_doc_update: str
```

### الخطوة 3: المُصنِّف

```python
CLASSIFY_PROMPT = """You are an experienced AI engineering consultant assessing a scope change request.

Project context:
{context}

Original scope:
{original_scope}

Scope change request:
{change_request}

Classify this change and provide your assessment in this exact JSON format:
{{
  "change_type": "clarification" | "expansion" | "pivot",
  "effort_delta_days": <integer, 0 for clarification>,
  "timeline_risk": "low" | "medium" | "high",
  "rationale": "<one paragraph explaining the classification and why>",
  "customer_response": "<draft message to send the customer, professional and direct>",
  "scope_doc_update": "<one sentence: what to add to the scope doc change log>"
}}

Classification rules:
- clarification: same goal, better definition, usually reduces or maintains scope
- expansion: same goal, additional features or coverage, adds work
- pivot: fundamentally different goal, requires restarting scoping

For customer_response:
- Do not commit to anything until impact is assessed (even if it is clarification, say you are updating the scope doc)
- For expansion and pivot: be honest about the tradeoff, do not hedge with "might" and "maybe"
- Keep it under 100 words, professional but direct
- Do not start with "I hope this message finds you well" or similar filler

Return only the JSON object, no other text."""


def classify_scope_change(
    context: str,
    original_scope: str,
    change_request: str,
) -> ScopeChangeAssessment:
    """Classify a scope change and generate a customer response."""
    prompt = CLASSIFY_PROMPT.format(
        context=context,
        original_scope=original_scope,
        change_request=change_request,
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    data = json.loads(raw)

    return ScopeChangeAssessment(
        change_type=ChangeType(data["change_type"]),
        effort_delta_days=int(data["effort_delta_days"]),
        timeline_risk=data["timeline_risk"],
        rationale=data["rationale"],
        customer_response=data["customer_response"],
        scope_doc_update=data["scope_doc_update"],
    )
```

### الخطوة 4: مُنسّق التقرير

```python
RISK_COLORS = {
    "low": "[LOW]",
    "medium": "[MEDIUM]",
    "high": "[HIGH]",
}

CHANGE_LABELS = {
    ChangeType.CLARIFICATION: "CLARIFICATION (accept + update doc)",
    ChangeType.EXPANSION: "EXPANSION (negotiate or decline)",
    ChangeType.PIVOT: "PIVOT (restart scoping)",
}


def print_assessment(assessment: ScopeChangeAssessment) -> None:
    """Print a formatted assessment report."""
    print("\n" + "=" * 60)
    print("SCOPE CHANGE ASSESSMENT")
    print("=" * 60)

    print(f"\nType:          {CHANGE_LABELS[assessment.change_type]}")
    print(f"Effort delta:  +{assessment.effort_delta_days} engineering days")
    print(f"Timeline risk: {RISK_COLORS[assessment.timeline_risk]}")

    print("\n--- RATIONALE ---")
    print(assessment.rationale)

    print("\n--- DRAFT CUSTOMER RESPONSE ---")
    print(assessment.customer_response)

    print("\n--- SCOPE DOC UPDATE ---")
    print(assessment.scope_doc_update)

    print("\n" + "=" * 60)
    if assessment.change_type == ChangeType.PIVOT:
        print("ACTION REQUIRED: Stop current work. Schedule a scoping call.")
    elif assessment.change_type == ChangeType.EXPANSION:
        print("ACTION REQUIRED: Send response. Wait for customer decision before proceeding.")
    else:
        print("ACTION REQUIRED: Update scope doc. Confirm with customer in writing.")
    print("=" * 60 + "\n")
```

### الخطوة 5: الـ CLI الرئيسي

```python
DEMO_SCENARIOS = [
    {
        "name": "Scenario 1: Expansion",
        "context": "6-week engagement to build a support ticket classifier for a SaaS company. Week 3 of 6. Classifier covers Tier 1 support (password resets, account access, basic how-to questions). Eval set built, first model in staging.",
        "original_scope": "Build and deploy a text classifier that routes Tier 1 support tickets to the correct support queue. Includes: data labeling guide, model training, eval set (200 labeled examples), API endpoint, basic admin dashboard. NOT IN SCOPE: billing questions, Tier 2/3 tickets, multi-language support.",
        "change_request": "Hey, while you are at it, could you also make it handle billing questions? Customers always get confused between account access and billing, so it would be great to have both. That is basically the same data, right?",
    },
    {
        "name": "Scenario 2: Clarification",
        "context": "4-week engagement to build a document summarization tool for a legal firm. Week 1. Discovery just completed.",
        "original_scope": "Build a tool that summarizes legal documents under 50 pages and returns key clauses, dates, and parties. Integrates with their Google Drive. NOT IN SCOPE: contracts over 50 pages, court filings, multi-language documents.",
        "change_request": "We realized we should clarify: when we said 'legal documents' we meant specifically contract amendments and NDAs. We do not need it to handle lease agreements or employment contracts. Those go to a different team.",
    },
    {
        "name": "Scenario 3: Pivot",
        "context": "5-week engagement to build an internal knowledge base search tool. Week 2. Architecture designed, data pipeline in progress.",
        "original_scope": "Build a semantic search system over the company's internal wiki (3,000 documents). Includes: ingestion pipeline, vector store, search API, basic UI. NOT IN SCOPE: real-time document sync, user access controls, analytics dashboard.",
        "change_request": "Our CEO just came back from a conference and wants us to pivot. Instead of the search tool, can you build a full customer-facing chatbot that answers questions about our product? He wants it launched in 3 weeks.",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ScopeChangeEvaluator: classify scope changes and draft customer responses"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run on 3 built-in demo scenarios",
    )
    parser.add_argument("--context", help="Project context (what is being built, what week)")
    parser.add_argument("--scope", help="Original scope statement including NOT IN SCOPE section")
    parser.add_argument("--change", help="The scope change request text")
    args = parser.parse_args()

    if args.demo:
        for scenario in DEMO_SCENARIOS:
            print(f"\n{'#' * 60}")
            print(f"  {scenario['name']}")
            print(f"{'#' * 60}")
            assessment = classify_scope_change(
                context=scenario["context"],
                original_scope=scenario["original_scope"],
                change_request=scenario["change_request"],
            )
            print_assessment(assessment)
    elif args.context and args.scope and args.change:
        assessment = classify_scope_change(
            context=args.context,
            original_scope=args.scope,
            change_request=args.change,
        )
        print_assessment(assessment)
    else:
        print("Usage:")
        print("  python main.py --demo")
        print("  python main.py --context '...' --scope '...' --change '...'")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

> **اختبار من الواقع:** مؤسّس شركة ناشئة تعمل معه يقول: "نحن فريق رشيق (agile)، لا نعمل بوثائق نطاق رسمية. نناقش الأمور فحسب." كيف تشرح قيمة وثيقة النطاق الحيّة وقسم "خارج النطاق" دون أن تبدو بيروقراطيًا أو كأنك لا تثق بهم؟

---

## الاستخدام

شغّل الأداة على سيناريوهات العرض الثلاثة كلها:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --demo
```

المخرج المتوقع للسيناريو 1 (توسعة):
- التصنيف: EXPANSION
- فارق الجهد: 3-5 أيام (بيانات الفوترة تتطلب وسومًا جديدة، وتقييمًا جديدًا، ومنطق توجيه جديدًا)
- خطر الجدول الزمني: MEDIUM أو HIGH
- رد العميل: شفّاف بشأن المفاضلة، ولا يلتزم بشيء

المخرج المتوقع للسيناريو 2 (توضيح):
- التصنيف: CLARIFICATION
- فارق الجهد: 0 أيام (النطاق يضيق، لا يتوسّع)
- خطر الجدول الزمني: LOW
- رد العميل: يؤكّد التحديث، ويشكرهم على الوضوح

المخرج المتوقع للسيناريو 3 (تحوّل جذري):
- التصنيف: PIVOT
- فارق الجهد: كبير (إعادة بدء كاملة)
- خطر الجدول الزمني: HIGH
- رد العميل: صادق بشأن الأثر، ويقترح مكالمة تحديد نطاق

يمكنك أيضًا تشغيلها على سيناريوك الخاص:

```bash
python main.py \
  --context "8-week RAG project, week 4, document pipeline complete" \
  --scope "Build RAG over internal HR docs. NOT IN SCOPE: real-time sync, user authentication." \
  --change "HR wants the system to also answer questions about employee performance reviews"
```

> **نقلة في المنظور:** يقول مديرك "وافق على كل شيء، سنحلّ الأمر لاحقًا، نحتاج إلى إبقاء العميل سعيدًا." أنت تعرف أن هذا النهج يقود إلى مواعيد نهائية ضائعة وثقة متآكلة. كيف تعترض على ذلك بشكل بنّاء، وأيّ دليل من هذا الدرس تستخدمه؟

---

## التسليم

مخرج هذا الدرس هو `outputs/prompt-scope-change-playbook.md`. وهو دليل عمل (playbook) منظّم يمكنك لصقه في القرص المشترك أو مساحة عمل Notion لأيّ مشروع عند الانطلاق. يعطي العميل صورة واضحة عن كيفية التعامل مع تغييرات النطاق قبل وصول أول طلب تغيير.

الأداة القابلة للتشغيل هي `code/main.py`:

```bash
python main.py --demo
```

---

## التقييم

**الفحص 1: هل يطابق التصنيف الواقع؟**
شغّل سيناريوهات العرض الثلاثة. لكل واحد، صنّف التغيير يدويًا قبل قراءة المخرج. إن اختلف تصنيفك عن تصنيف النموذج في أكثر من سيناريو، فراجع محفّز المُصنِّف وأضف أمثلة أوضح.

**الفحص 2: هل رد العميل مناسب لكل نوع؟**
رد توضيح جيد يشكر العميل ويؤكّد أن وثيقة النطاق ستُحدَّث. رد توسعة جيد يسمّي أثر الجهد والجدول الزمني صراحةً. رد تحوّل جذري جيد يتوقّف، ويقترح مكالمة تحديد نطاق، ولا يلتزم بالجدول الزمني الجديد. إن تهرّب أيّ رد بلغة غامضة، فأحكِم المحفّز.

**الفحص 3: هل تقلّل الأداة زمن الاستجابة؟**
وقّت نفسك: كم تستغرق لصياغة رد تغيير نطاق بدون الأداة؟ ومعها؟ يجب أن تقلّص الأداة زمن مسودّتك الأولى من 20 دقيقة إلى 3 دقائق. إن لم تفعل، فالمحفّز ينتج ردودًا تحتاج إلى تحرير كثير.

**الفحص 4: اختبار الإجهاد بطلب غامض.**
قدّم طلب تغيير يمكن أن يكون توسعة أو توضيحًا تبعًا للتفسير. ينبغي للنموذج أن يُشير إلى الغموض في التبرير (rationale) بدلًا من اختيار أحدهما بصمت. إن لم يفعل، فأضف ملاحظة إلى المحفّز تطلب منه إبراز الحالات الغامضة.
