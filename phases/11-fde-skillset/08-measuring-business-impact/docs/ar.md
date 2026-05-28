# قياس الأثر التجاري

> إذا لم تستطع ترجمة درجة التقييم (eval score) إلى مبلغ بالدولار أو توفير في الوقت، فلن يستطيع العميل تبرير التجديد.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 11-02 (تحديد النطاق قبل الحل)، 05-01 (أساسيات التطوير المُوجَّه بالتقييم)
**الوقت:** ~45 دقيقة
**المرحلة:** 11 · مهارات الـ FDE

---

## أهداف التعلّم

- وصف سلسلة ترجمة المقاييس ثلاثية الطبقات من درجة التقييم إلى مؤشر الأداء التجاري (business KPI)
- تجهيز تجربة استرشادية (pilot) لالتقاط المقاييس التجارية إلى جانب مقاييس النموذج منذ اليوم الأول
- حساب الارتباط (correlation) بين جودة النموذج والنتيجة التجارية في سيناريو تجربة استرشادية
- بناء ImpactTracker يسجّل طبقتي المقاييس معًا ويُظهر العلاقة بينهما
- صياغة النتائج التجارية باللغة التي يتصرّف بناءً عليها أصحاب المصلحة (stakeholders): الوقت، التكلفة، معدّل الأخطاء

---

## المشكلة

أجريت تجربة استرشادية ناجحة. ارتفعت درجة التقييم لديك من 0.74 إلى 0.84. تحسّنت دقة الاسترجاع (retrieval precision). أصبح النموذج يؤسّس إجاباته بشكل أفضل. أنت فخور بعملك.

تعرض هذا في المراجعة التجارية الفصلية. يحدّق فيك نائب الرئيس لنجاح العملاء ويقول: "رائع. ماذا يعني هذا لفريقي؟"

لا تملك إجابة. قست الشيء الذي تعرف كيف تقيسه، وهو النموذج. لم تجهّز قياس الشيء الذي يهتمّ به العميل، وهو أداء فريقه.

هذه واحدة من أكثر فجوات الـ FDE شيوعًا. المهندسون مدرّبون على قياس جودة النموذج، لا النتائج التجارية. لكن قرار التجديد لدى العميل يستند بالكامل إلى النتائج التجارية. "ارتفعت دقة التقييم لدينا من 0.74 إلى 0.84" لا يجدّد عقدًا. أما "أصبح وكلاء الدعم لديك يتعاملون مع 84% من تذاكر المستوى الأول دون تصعيد، صعودًا من 74%، مما يوفّر نحو 200 ساعة عمل للوكلاء شهريًا" فيفعل.

الحل ليس التوقّف عن قياس مقاييس النموذج. بل بناء التقاط المقاييس التجارية في التجربة الاسترشادية منذ اليوم الأول، حتى تكون الطبقتان متوفّرتين لديك دائمًا.

---

## المفهوم

### سلسلة المقاييس ثلاثية الطبقات

```
LAYER 1: TECHNICAL (eval metrics)
  What engineers measure
  Examples: accuracy, F1, BLEU, RAGAS faithfulness, answer relevance
  Audience: the FDE team
  Problem: meaningless to business stakeholders

         |
         | translation required
         v

LAYER 2: OPERATIONAL (task success metrics)
  What the system actually does in production
  Examples: ticket correctly routed (yes/no), time-to-resolution,
            escalation rate, first-contact resolution rate
  Audience: team leads, operations managers
  Problem: not yet connected to dollars or strategic KPIs

         |
         | translation required
         v

LAYER 3: BUSINESS (KPI metrics)
  What the business cares about
  Examples: cost per ticket, agent utilization, customer satisfaction score,
            revenue influenced, errors avoided, hours saved per week
  Audience: VPs, executives, budget owners
  The renewal decision is made here.
```

### جدول الترجمة

```
+------------------------+---------------------------+---------------------------+
| EVAL METRIC            | OPERATIONAL METRIC        | BUSINESS KPI              |
+------------------------+---------------------------+---------------------------+
| Classifier accuracy    | % tickets routed          | Agent hours saved / week  |
|   0.84                 |   correctly               |   ~200 hrs/month          |
+------------------------+---------------------------+---------------------------+
| Retrieval recall       | % queries answered        | Self-service deflection   |
|   0.91                 |   without escalation      |   rate: 40% -> 58%        |
+------------------------+---------------------------+---------------------------+
| Answer faithfulness    | Customer satisfaction     | NPS improvement           |
|   0.88                 |   proxy score             |   +12 points              |
+------------------------+---------------------------+---------------------------+
| Latency p95: 1.2s      | % queries completed       | Abandonment rate          |
|                        |   under SLA               |   12% -> 4%               |
+------------------------+---------------------------+---------------------------+
| Error rate: 3%         | % interactions needing    | Re-work cost avoided      |
|                        |   manual correction       |   $18k/quarter            |
+------------------------+---------------------------+---------------------------+
```

### تجهيز التجربة الاسترشادية

يجب بناء التقاط المقاييس التجارية قبل أن تنطلق التجربة الاسترشادية. لا يمكنك التجهيز بأثر رجعي بدقة كافية لإقناع تنفيذي متشكّك.

```
PILOT INSTRUMENTATION PLAN

For every interaction in the pilot, log:
  - interaction_id
  - timestamp
  - model_quality_score       (your eval metric, 0-1)
  - task_success              (did the system accomplish the goal? boolean)
  - time_to_resolution        (how long did this take vs. baseline?)
  - escalation_required       (did a human need to intervene?)
  - customer_satisfaction     (proxy: was the next action a repeat inquiry?)

At the end of the pilot period:
  - Aggregate all three layers
  - Compute correlation between model_quality_score and task_success
  - Translate task_success rate into business KPI using baseline numbers
  - Present: "Before: X. After: Y. Delta: Z units of business value."
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
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import correlation, mean, stdev
from typing import Optional

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
```

### الخطوة 2: نموذج بيانات التفاعل

```python
@dataclass
class Interaction:
    interaction_id: str
    timestamp: str
    query: str
    model_response: str
    model_quality_score: float    # eval layer: 0.0 - 1.0
    task_success: bool            # operational layer: did it accomplish the goal?
    time_to_resolution_seconds: float    # operational: time taken
    escalation_required: bool     # operational: human intervention needed?
    customer_satisfaction_proxy: float   # 0.0 - 1.0, e.g. no repeat inquiry = 1.0


@dataclass
class PilotMetrics:
    interactions: list[Interaction] = field(default_factory=list)

    @property
    def avg_model_quality(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(i.model_quality_score for i in self.interactions)

    @property
    def task_success_rate(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(1.0 if i.task_success else 0.0 for i in self.interactions)

    @property
    def escalation_rate(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(1.0 if i.escalation_required else 0.0 for i in self.interactions)

    @property
    def avg_resolution_seconds(self) -> float:
        if not self.interactions:
            return 0.0
        return mean(i.time_to_resolution_seconds for i in self.interactions)

    @property
    def quality_success_correlation(self) -> Optional[float]:
        if len(self.interactions) < 3:
            return None
        quality_scores = [i.model_quality_score for i in self.interactions]
        success_scores = [1.0 if i.task_success else 0.0 for i in self.interactions]
        try:
            return correlation(quality_scores, success_scores)
        except Exception:
            return None
```

### الخطوة 3: مُقيِّم جودة النموذج

```python
QUALITY_SCORE_PROMPT = """You are evaluating the quality of an AI system response in a support ticket context.

Customer query: {query}
AI response: {response}
Expected behavior: {expected}

Score the response on a scale from 0.0 to 1.0:
- 1.0: Fully correct, directly addresses the query, no hallucination, actionable
- 0.7-0.9: Mostly correct with minor gaps or unnecessary hedging
- 0.4-0.6: Partially correct, misses key information, or partially wrong
- 0.1-0.3: Mostly incorrect or misleading
- 0.0: Completely wrong, harmful, or no response

Return only a JSON object:
{{"score": <float 0.0-1.0>, "reason": "<one sentence>"}}"""


def score_model_quality(query: str, response: str, expected: str) -> tuple[float, str]:
    """Score a model response using Claude as judge. Returns (score, reason)."""
    prompt = QUALITY_SCORE_PROMPT.format(
        query=query,
        response=response,
        expected=expected,
    )

    result = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = result.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    data = json.loads(raw)
    return float(data["score"]), data["reason"]
```

### الخطوة 4: مترجم الأثر التجاري

```python
TRANSLATE_PROMPT = """You are translating pilot metrics into business impact language for an executive audience.

Pilot context: {context}
Baseline metrics (before AI): {baseline}
Pilot metrics (with AI): {pilot_metrics}

Translate these results into business impact. Return a JSON object:
{{
  "headline": "<one sentence: the most important result, in business terms>",
  "time_saved_per_month": "<estimated hours or minutes saved per month, with reasoning>",
  "cost_impact": "<estimated cost impact if applicable, or 'requires cost-per-hour data from customer'>",
  "error_reduction": "<reduction in errors or escalations, expressed as percentage and absolute number>",
  "renewal_argument": "<one to two sentences a VP would use to justify renewing the contract>"
}}

Use concrete numbers. Do not hedge with 'potentially' or 'might'. If a number requires customer data you do not have, say what data is needed."""


def translate_to_business_impact(
    context: str,
    baseline: dict,
    pilot: PilotMetrics,
) -> dict:
    """Translate pilot metrics into business impact language."""
    pilot_summary = {
        "avg_model_quality": round(pilot.avg_model_quality, 3),
        "task_success_rate": round(pilot.task_success_rate, 3),
        "escalation_rate": round(pilot.escalation_rate, 3),
        "avg_resolution_seconds": round(pilot.avg_resolution_seconds, 1),
        "quality_success_correlation": round(pilot.quality_success_correlation or 0.0, 3),
        "total_interactions": len(pilot.interactions),
    }

    prompt = TRANSLATE_PROMPT.format(
        context=context,
        baseline=json.dumps(baseline, indent=2),
        pilot_metrics=json.dumps(pilot_summary, indent=2),
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    return json.loads(raw)
```

### الخطوة 5: طابع التقرير

```python
def print_impact_report(
    pilot: PilotMetrics,
    business_impact: dict,
    baseline: dict,
) -> None:
    """Print the full three-layer impact report."""
    print("\n" + "=" * 60)
    print("PILOT IMPACT REPORT")
    print("=" * 60)

    print("\n--- LAYER 1: TECHNICAL (Model Quality) ---")
    print(f"Average model quality score: {pilot.avg_model_quality:.3f}")
    q_corr = pilot.quality_success_correlation
    if q_corr is not None:
        print(f"Quality-to-success correlation: {q_corr:.3f}")
    print(f"Total interactions evaluated: {len(pilot.interactions)}")

    print("\n--- LAYER 2: OPERATIONAL (Task Performance) ---")
    print(f"Task success rate: {pilot.task_success_rate:.1%}")
    baseline_success = baseline.get("task_success_rate", 0)
    if baseline_success:
        delta = pilot.task_success_rate - baseline_success
        print(f"  vs. baseline: {baseline_success:.1%}  (delta: {delta:+.1%})")
    print(f"Escalation rate: {pilot.escalation_rate:.1%}")
    baseline_esc = baseline.get("escalation_rate", 0)
    if baseline_esc:
        delta_esc = pilot.escalation_rate - baseline_esc
        print(f"  vs. baseline: {baseline_esc:.1%}  (delta: {delta_esc:+.1%})")
    print(f"Avg resolution time: {pilot.avg_resolution_seconds:.0f}s")
    baseline_time = baseline.get("avg_resolution_seconds", 0)
    if baseline_time:
        time_delta = pilot.avg_resolution_seconds - baseline_time
        print(f"  vs. baseline: {baseline_time:.0f}s  (delta: {time_delta:+.0f}s)")

    print("\n--- LAYER 3: BUSINESS (KPI Impact) ---")
    print(f"Headline: {business_impact.get('headline', 'N/A')}")
    print(f"Time saved per month: {business_impact.get('time_saved_per_month', 'N/A')}")
    print(f"Cost impact: {business_impact.get('cost_impact', 'N/A')}")
    print(f"Error reduction: {business_impact.get('error_reduction', 'N/A')}")
    print(f"\nRenewal argument:\n  {business_impact.get('renewal_argument', 'N/A')}")

    print("\n" + "=" * 60)
```

> **اختبار من الواقع:** يقول المدير المالي (CFO) لدى عميلك: "تُظهر التجربة الاسترشادية أرقام دقّة جيدة، لكننا نحتاج إلى رؤية العائد على الاستثمار (ROI) قبل الالتزام بنشر كامل. أنفقنا 40 ألف دولار على التجربة." كيف تستخدم مُخرَج الـ ImpactTracker لبناء حجّة العائد على الاستثمار، وما البيانات الإضافية التي تحتاجها من العميل؟

---

## الاستخدام

شغّل سيناريو العرض التوضيحي: تجربة استرشادية لتصنيف تذاكر الدعم لعميل SaaS.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --demo
```

يولّد العرض التوضيحي 50 تفاعلًا اصطناعيًا بدرجات جودة النموذج والمقاييس التشغيلية، ويشغّل ترجمة الأثر التجاري، ويطبع التقرير ثلاثي الطبقات.

مثال على بنية المُخرَج:
- الطبقة 1: متوسط جودة النموذج 0.83، ارتباط الجودة بالنجاح 0.71
- الطبقة 2: معدّل نجاح المهمة 84% (مقابل خط أساس 68%)، معدّل التصعيد 18% (مقابل خط أساس 34%)
- الطبقة 3: "أصبح وكلاء الدعم يتعاملون مع 84% من تذاكر المستوى الأول دون تصعيد، مما يوفّر نحو 180 ساعة عمل للوكلاء شهريًا"

لتشغيل المُتتبّع على بيانات تفاعلاتك الخاصة:

```bash
python main.py --from-json interactions.json --baseline baseline.json
```

تنسيق JSON للتفاعلات يتبع حقول صنف البيانات `Interaction`. ملف خط الأساس عبارة عن dict بسيط يحتوي على `task_success_rate` و `escalation_rate` و `avg_resolution_seconds`.

> **نقلة في المنظور:** يقول مهندس أقدم في فريقك: "ينبغي أن نركّز على تحسين النموذج، لا تتبّع المقاييس التجارية. تلك مهمّة مدير المنتج." كيف توضّح لماذا يُعدّ تجهيز قياس المقاييس التجارية جزءًا من مهمّة المهندس في ارتباط الـ FDE، لا مسؤولية منفصلة؟

---

## التسليم

مُخرَج هذا الدرس هو `outputs/prompt-impact-measurement-framework.md`. وهو إطار قابل لإعادة الاستخدام لتنظيم حوار الأثر التجاري مع العملاء قبل بدء التجربة الاسترشادية.

الأداة القابلة للتشغيل هي `code/main.py`:

```bash
python main.py --demo
```

---

## التقييم

**التحقق 1: هل مقياس الارتباط منطقي؟**
ارتباط الجودة بالنجاح فوق 0.6 يعني أن مقياس التقييم لديك مؤشّر مفيد للنجاح التشغيلي. وأقل من 0.4 يعني أن تقييمك يقيس شيئًا لا يتنبّأ بنجاح المهمة في الواقع. شغّل العرض التوضيحي وتحقّق من قيمة الارتباط. إذا كانت منخفضة جدًا في بيانات تجربتك الاسترشادية الحقيقية، فإن مقياس التقييم لديك يحتاج إلى تغيير.

**التحقق 2: هل تستخدم ترجمة الأثر التجاري أرقامًا ملموسة؟**
يجب أن يتضمّن مُخرَج `translate_to_business_impact` أرقامًا محدّدة، لا لغة مبهمة. "نحو 180 ساعة عمل للوكلاء شهريًا" مقبول. "توفير كبير محتمل في الوقت" لا. إذا كان المُخرَج مبهمًا، فإن الموجّه يحتاج إلى تعليمات أصرح لاستخدام الأرقام.

**التحقق 3: هل يروي التقرير ثلاثي الطبقات قصة متماسكة؟**
يجب أن يشكّل المقياس التقني والمقياس التشغيلي والمقياس التجاري سلسلة متّسقة. إذا كانت جودة النموذج عالية (0.85) لكن معدّل نجاح المهمة منخفض (55%)، فإن السلسلة مكسورة وعليك التحقيق في سبب عدم ترجمة درجات التقييم الجيدة إلى نجاح تشغيلي. هذه علامة على أن مقياس التقييم لديك لا يطابق الاستخدام الحقيقي.

**التحقق 4: هل يمكنك توليد حجّة التجديد من التقرير وحده؟**
خذ مُخرَج الطبقة 3 واقرأه على شخص غير تقني. هل يستطيع فهم الحجّة التجارية دون شرح؟ إذا احتاج منك أن تشرح السياق، فإن الصياغة تحتاج إلى عمل.
