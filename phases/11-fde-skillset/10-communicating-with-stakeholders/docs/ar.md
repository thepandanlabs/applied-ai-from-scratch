# التواصل مع أصحاب المصلحة غير التقنيين

> "تحسّنت دقّة النموذج من 0.79 إلى 0.84" و"أصبح وكلاء الدعم يتعاملون بشكل صحيح مع 84% من تذاكر المستوى الأول دون تصعيد، صعودًا من 79%" يصفان النتيجة نفسها. أحدهما يحصل على تجديد الميزانية؛ والآخر يحصل على سؤال متابعة حائر.

**النوع:** تعلّم
**اللغات:** Python
**المتطلبات:** 11-08 (قياس الأثر التجاري)، 11-05 (عروض توضيحية تصمد أمام البيانات الحقيقية)
**الوقت:** ~45 دقيقة
**المرحلة:** 11 · مهارات الـ FDE

---

## أهداف التعلّم

- التعرّف على مشكلات الترجمة الثلاث التي تجعل التحديثات التقنية غامضة لأصحاب المصلحة التجاريين
- تطبيق خمسة قوالب تواصل لتحديثات الحالة، وتصعيد المخاطر، وملخّصات النتائج
- بناء StakeholderTranslator (أداة CLI) يعيد كتابة التحديثات التقنية بلغة جاهزة لأصحاب المصلحة
- تقييم المُخرَج المُترجَم على الوضوح، والملاءمة التجارية، وكثافة المصطلحات (jargon)
- إيصال رسالة عدم يقين بشأن الذكاء الاصطناعي دون إثارة الذعر

---

## المشكلة

أنت على بُعد أسبوعين من الإطلاق. يقول تحديث حالتك الأسبوعي: "أكملنا اندماج وحدة الاسترجاع الهجين مع إعادة الترتيب بـ cross-encoder. تحسّنت درجات RAGAS: faithfulness 0.82 -> 0.89، answer relevance 0.77 -> 0.85. الـ Latency p95 هو 1.4 ثانية. ما زلنا نحقّق في هلوسات (hallucinations) عرضية في الحالات الطرفية."

صاحب المصلحة الرئيسي لديك، نائب رئيس العمليات، يعيد توجيه هذا إلى المدير المالي مع الرسالة: "فريق الذكاء الاصطناعي يقول إن النظام أحيانًا يهلوس. هل ينبغي أن نقلق؟"

يرسل المدير المالي بريدًا للرئيس التنفيذي. يطلب الرئيس التنفيذي اجتماعًا.

تسبّبت في أزمة بإرسال تحديث تقني دقيق. المشكلة لم تكن في المحتوى؛ بل في الجمهور. قرأ نائب الرئيس "هلوسات في الحالات الطرفية" على أنها "النظام يكذب أحيانًا ولا نعرف متى." كنت تعني "نمط إخفاق نادر ومحدود نتتبّعه وسنعالجه قبل الإطلاق."

هذا واحد من أكثر إخفاقات التواصل شيوعًا وكلفةً في هندسة الذكاء الاصطناعي. الحل ليس التوقّف عن الدقّة. بل وجود طبقة ترجمة لكل تحديث يذهب إلى أصحاب المصلحة غير التقنيين.

---

## المفهوم

### مشكلات الترجمة الثلاث

```
TRANSLATION PROBLEM 1: METRIC TRANSLATION
  Technical: "RAGAS faithfulness improved from 0.82 to 0.89"
  Stakeholder hears: "They changed a number. I do not know if that is good."
  Translation: "The system now gives accurate, well-sourced answers 89% of the time,
                up from 82%. The improvement means fewer corrections needed by your team."

TRANSLATION PROBLEM 2: UNCERTAINTY TRANSLATION
  Technical: "Occasional hallucinations on edge cases under investigation"
  Stakeholder hears: "The system makes things up and they do not know when or why"
  Translation: "We have identified a narrow category of unusual questions where the
                system occasionally gives incomplete answers. We have a fix scheduled
                for next week. This affects less than 3% of expected query volume."

TRANSLATION PROBLEM 3: PROGRESS TRANSLATION
  Technical: "Completed hybrid retrieval integration. Working on prompt optimization."
  Stakeholder hears: "I have no idea what this means."
  Translation: "We finished the search component that lets the system find relevant
                documents. We are now tuning the instructions that tell the AI how
                to answer questions from those documents. On track for the scheduled
                launch date."
```

### قوالب التواصل الخمسة

```
TEMPLATE 1: WEEKLY STATUS UPDATE (one page, every Monday)
  Section 1: One-sentence summary (what is the headline this week?)
  Section 2: What shipped (in plain language, user-facing impact)
  Section 3: What ships next (concrete deliverables with dates)
  Section 4: Risks on the radar (framed as "we are watching X and will have Y by Z")
  Section 5: What we need from you (specific asks, not vague "input")
  Length: 200-300 words maximum

TEMPLATE 2: RISK ESCALATION
  Risk name (plain language, not "p95 latency spike")
  Impact if unresolved (who it affects, when it becomes a problem)
  Probability (is this likely or a tail risk?)
  Current status (what are we doing about it right now?)
  What we need (specific decision or resource)
  Deadline for the decision

TEMPLATE 3: RESULTS SUMMARY (for QBRs and pilots)
  Before: [metric in business terms] - not "baseline accuracy was 0.72"
  After:  [metric in business terms] - not "accuracy is now 0.85"
  Delta:  [what changed for users or the business]
  Projection: [what this means at full scale]
  Next step: [clear ask or decision]

TEMPLATE 4: AI UNCERTAINTY FRAMING
  Never say "hallucination" to a non-technical stakeholder without context.
  Instead: "The system handles [X]% of questions with high confidence.
            For the remaining [Y]%, it flags the answer as needing review,
            or routes to a human. This is by design."

TEMPLATE 5: LAUNCH READINESS UPDATE
  Green: On track for [date]. [N] items remaining, all on schedule.
  Yellow: [specific risk] may affect [date]. Mitigation: [action] by [date].
  Red: [specific blocker]. Options: [A], [B], [C]. Recommendation: [X].
```

### جدول استبدال المصطلحات

```
+----------------------------+------------------------------------------+
| TECHNICAL PHRASE           | STAKEHOLDER-FRIENDLY EQUIVALENT          |
+----------------------------+------------------------------------------+
| Model accuracy: 0.84       | The system gives the right answer 84%    |
|                            | of the time                              |
+----------------------------+------------------------------------------+
| Hallucination              | The system generates an incorrect or     |
|                            | unsupported answer                       |
+----------------------------+------------------------------------------+
| Latency p95: 1.4s          | 95% of responses arrive within 1.4      |
|                            | seconds                                  |
+----------------------------+------------------------------------------+
| RAG pipeline               | The system that finds relevant documents |
|                            | before answering a question              |
+----------------------------+------------------------------------------+
| Embedding model            | The component that understands the       |
|                            | meaning of text                          |
+----------------------------+------------------------------------------+
| Context window exceeded    | The question or document was too long    |
|                            | for the AI to process in one step        |
+----------------------------+------------------------------------------+
| RAGAS faithfulness: 0.89   | 89% of answers are directly supported   |
|                            | by the source documents                  |
+----------------------------+------------------------------------------+
| Fine-tuning                | Training the AI on your specific data   |
|                            | and use case                             |
+----------------------------+------------------------------------------+
| Eval set / eval score      | Our quality test: [N] sample questions  |
|                            | with known correct answers               |
+----------------------------+------------------------------------------+
| Token limit                | The maximum length the AI can process   |
|                            | at once                                  |
+----------------------------+------------------------------------------+
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

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
```

### الخطوة 2: موجّه الترجمة

```python
@dataclass
class TranslationResult:
    original: str
    translated: str
    clarity_score: float          # 0-1: how clear is it to a non-technical reader?
    business_relevance_score: float  # 0-1: does it speak to business outcomes?
    jargon_score: float           # 0-1: 0 = no jargon, 1 = full jargon
    improvements: list[str]


TRANSLATE_PROMPT = """You are an expert at translating technical AI project updates into clear, business-focused language for non-technical stakeholders.

The audience is a VP or C-level executive who:
- Has no background in machine learning or software engineering
- Cares about business outcomes: time saved, cost reduced, risk managed, users helped
- Makes decisions based on confidence and clarity, not technical details
- Will escalate or block a project if they feel uncertain or out of the loop

Technical update to translate:
{update}

Translate this into a stakeholder-ready update. Then score the original and your translation.

Return a JSON object:
{{
  "translation": "<your stakeholder-friendly rewrite of the update>",
  "clarity_score": <float 0.0-1.0: how clear is the translated version to a non-technical reader>,
  "business_relevance_score": <float 0.0-1.0: does it speak to business outcomes and impact?>,
  "jargon_score": <float 0.0-1.0: how much technical jargon remains? 0=none, 1=all jargon>,
  "improvements": ["<specific change 1>", "<specific change 2>", "<specific change 3>"]
}}

Translation rules:
- Replace every metric with its business meaning (e.g., "accuracy 0.84" becomes "correctly handles 84% of requests")
- Replace "hallucination" with a concrete description of what happens and how often
- Replace infrastructure terms (RAG, embedding, p95, tokens) with plain-language equivalents
- Keep the update under 150 words
- End with either a concrete status (on track / at risk) or a specific ask
- Do not introduce uncertainty you did not have - be honest about risks using plain language
- Never start with "I hope this email finds you well" or similar filler"""
```

### الخطوة 3: دالة الترجمة

```python
def translate_update(technical_update: str) -> TranslationResult:
    """Translate a technical update into stakeholder-ready language and score it."""
    prompt = TRANSLATE_PROMPT.format(update=technical_update)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    data = json.loads(raw)

    return TranslationResult(
        original=technical_update,
        translated=data["translation"],
        clarity_score=float(data["clarity_score"]),
        business_relevance_score=float(data["business_relevance_score"]),
        jargon_score=float(data["jargon_score"]),
        improvements=data.get("improvements", []),
    )
```

### الخطوة 4: مُنسّق التقرير

```python
def print_translation(result: TranslationResult) -> None:
    """Print the original, translation, and scores."""
    print("\n" + "=" * 60)
    print("STAKEHOLDER TRANSLATOR")
    print("=" * 60)

    print("\n--- ORIGINAL (TECHNICAL) ---")
    print(result.original)

    print("\n--- TRANSLATED (STAKEHOLDER-READY) ---")
    print(result.translated)

    print("\n--- SCORES ---")
    print(f"Clarity:           {result.clarity_score:.2f} / 1.0")
    print(f"Business relevance:{result.business_relevance_score:.2f} / 1.0")
    print(f"Jargon remaining:  {result.jargon_score:.2f} / 1.0  (lower is better)")

    if result.improvements:
        print("\n--- KEY CHANGES MADE ---")
        for improvement in result.improvements:
            print(f"  - {improvement}")

    # Overall assessment
    avg_score = (result.clarity_score + result.business_relevance_score + (1.0 - result.jargon_score)) / 3
    print(f"\nOverall translation quality: {avg_score:.2f} / 1.0")
    if avg_score >= 0.80:
        print("STATUS: Ready to send to stakeholders.")
    elif avg_score >= 0.65:
        print("STATUS: Review and refine before sending.")
    else:
        print("STATUS: Needs significant rework.")
    print("=" * 60 + "\n")
```

### الخطوة 5: الترجمة بالدفعة وتحديثات العرض التوضيحي

```python
DEMO_UPDATES = [
    {
        "name": "Status Update 1: Technical Progress",
        "text": (
            "Completed integration of the hybrid retrieval module with cross-encoder reranking. "
            "RAGAS scores improved: faithfulness 0.82 -> 0.89, answer relevance 0.77 -> 0.85. "
            "Latency p95 is 1.4s, within SLA. Still investigating occasional hallucinations "
            "on edge cases involving multi-hop reasoning over documents > 50 pages."
        ),
    },
    {
        "name": "Status Update 2: Risk Escalation",
        "text": (
            "We identified a risk: the customer's Oracle CRM database does not have an API. "
            "We need to build an ETL pipeline to export data nightly to S3 as a workaround. "
            "This adds approximately 8 engineering days and introduces a data freshness "
            "constraint: the system will only have access to data as of the previous day's "
            "export. This may impact the real-time classification use case."
        ),
    },
    {
        "name": "Status Update 3: Pilot Results",
        "text": (
            "Pilot results for the 4-week support ticket classification evaluation: "
            "precision 0.87, recall 0.83, F1 0.85. Escalation rate dropped from 34% to 18%. "
            "Average time-to-resolution improved from 185s to 62s. "
            "Correlation between model confidence score and task success: 0.71. "
            "Token usage averaging 2,800 tokens per query, within budget."
        ),
    },
]


def run_demo() -> None:
    """Run the translator on three demo updates."""
    for item in DEMO_UPDATES:
        print(f"\n{'#' * 60}")
        print(f"  {item['name']}")
        print(f"{'#' * 60}")
        result = translate_update(item["text"])
        print_translation(result)
```

> **اختبار من الواقع:** يقول مدير برنامج غير تقني: "قال فريق الذكاء الاصطناعي إن هناك 'قيد طزاجة بيانات' (data freshness constraint) بسبب خط أنابيب الـ ETL. ماذا يعني هذا، وهل ينبغي أن أقلق؟" كيف تشرح هذا بلغة بسيطة، وهل يحتاج إلى تصعيد؟

---

## الاستخدام

شغّل المترجم على تحديثات العرض التوضيحي الثلاثة كلها:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --demo
```

بالنسبة للتحديث الأول (التقدّم التقني)، توقّع:
- "الهلوسات في الحالات الطرفية" مُترجَمة إلى شيء مثل: "يعطي النظام أحيانًا إجابات ناقصة في فئة ضيّقة من الوثائق الطويلة والمعقّدة. هذا يؤثّر على أقل من 5% من الاستعلامات المتوقّعة ولدينا إصلاح مجدول قبل الإطلاق."
- درجات RAGAS مُترجَمة إلى لغة نتائج المستخدم
- درجة المصطلحات قرب 0.0 (لا مصطلحات تقنية متبقّية)
- درجة الوضوح فوق 0.80

اختبر بتحديثك الخاص:

```bash
python main.py --update "We hit a context window limit when processing documents over 100k tokens. We are implementing a sliding window with overlap to handle this edge case."
```

> **نقلة في المنظور:** يقول مديرك الهندسي: "كتابة نسختين من كل تحديث (تقنية وأخرى لأصحاب المصلحة) يضاعف عبء التواصل. درّب أصحاب المصلحة على فهم المصطلحات التقنية بدلًا من ذلك." كيف تردّ، وما تكلفة البديل؟

---

## التسليم

مُخرَج هذا الدرس هو `outputs/prompt-stakeholder-communication-guide.md`. وهو مرجع قابل لإعادة الاستخدام لأي مهندس يحتاج إلى إيصال حالة مشروع ذكاء اصطناعي لجمهور غير تقني.

الأداة القابلة للتشغيل هي `code/main.py`:

```bash
python main.py --demo
python main.py --update "your technical update here"
```

---

## التقييم

**التحقق 1: هل اختفت كلمة "hallucination" من كل المُخرَجات المُترجَمة؟**
شغّل تحديثات العرض التوضيحي الثلاثة كلها عبر المترجم. ابحث في الترجمات عن "hallucination" و"embedding" و"RAG" و"RAGAS" و"p95" و"precision" و"recall" و"F1" و"tokens". أيٌّ منها في المُخرَج المُترجَم يُعدّ إخفاقًا في معالجة المصطلحات. إذا ظهرت، فإن موجّه الترجمة يحتاج إلى أن يكون أصرح.

**التحقق 2: هل يتضمّن تحديث نتائج التجربة الاسترشادية المُترجَم أرقامًا تجارية؟**
يجب أن تذكر ترجمة التحديث 3: انخفاض معدّل التصعيد (من 34% إلى 18%)، وتحسّن زمن الحل (من 185 ثانية إلى 62 ثانية)، وما يعنيه هذا للأعمال. إذا بقيت الترجمة عند مستوى F1/precision/recall، فإنها لم تعبر إلى الطبقة 3 (لغة مؤشّر الأداء التجاري).

**التحقق 3: هل تتضمّن ترجمة تصعيد المخاطرة طلبًا واضحًا؟**
ترجمة تصعيد المخاطرة الجيدة تنتهي بطلب قرار محدّد وموعد نهائي. "نحتاج قرارًا حول المضيّ في نهج الدفعة الليلية بحلول الأربعاء" طلب واضح. "أخبرونا إن كانت لديكم مخاوف" ليس كذلك.

**التحقق 4: هل سيعيد نائب الرئيس توجيه هذا إلى الرئيس التنفيذي؟**
اقرأ نتائج التجربة الاسترشادية المُترجَمة كما يقرؤها نائب الرئيس. هل ستعيد توجيهها إلى الرئيس التنفيذي؟ إذا كانت ما زالت تحتوي على محتوى تقني يتطلّب شرحًا، فإن الترجمة غير مكتملة.
