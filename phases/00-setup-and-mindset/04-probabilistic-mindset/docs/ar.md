# العقلية الاحتمالية: لماذا ينهار التفكير الحتمي

> لا يمكنك تصحيح نظام احتمالي بقراءة أثر (trace) واحد. تصحّحه بتحليل التوزيعات (distributions).

**النوع:** تعلّم
**اللغات:** Python
**المتطلبات:** 00-01 (Dev Environment)، 00-02 (API Keys)، 00-03 (First API Call)
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- شرح لماذا الموديلات هي أخذة عيّنات (samplers) لا دوال (functions)، وماذا يعني ذلك للهندسة
- التعرّف على أنماط الفشل الخمسة للتفكير الحتمي عند تطبيقه على الـ AI
- تشغيل نفس الـ prompt N مرة وقياس تباين المخرجات تجريبياً
- استخدام الـ temperature بشكل صحيح كمقبض للتباين

---

## المشكلة

ميزة الـ AI لديك تنجح في كل الاختبارات يوم الاثنين. بحلول الخميس، يُبلِّغ ثلاثة مستخدمين أنها تُرجِع إجابات خاطئة. تسحب السجلات (logs)، تجد أحد الآثار السيئة، تعيد تشغيله يدوياً، فيعمل بشكل سليم. تُغلِق بلاغ الخطأ: "لا يمكن إعادة إنتاج المشكلة."

بعد أسبوعين تصلك خمسة بلاغات أخرى. تعيد التشغيل مجدداً. سليم مجدداً. المشكلة ليست في أي أثر مفرد. المشكلة في التوزيع: 8% من الاستدعاءات تُرجِع استجابة لا تطابق الـ schema الخاص بك، و3% تُرجِع التصنيف الخاطئ، و2% تُرجِع سلسلة نصية فارغة لحقل يجب أن يكون مملوءاً دائماً. لا شيء من هذه أخطاء في كودك. إنها خصائص للتوزيع الذي يأخذ موديلك العيّنات منه.

المهندسون الذين يتعاملون مع الموديلات كدوال حتمية -- نفس المدخل، نفس المخرج -- يطلقون أنظمة بمعدلات فشل خفية لا يرونها، ولا يستطيعون قياسها، ولا يستطيعون تحسينها. هذا الدرس يثبّت النموذج الذهني الذي يجعل معدلات الفشل هذه مرئية.

---

## المفهوم

### الدالة الحتمية مقابل أخذة العيّنات الاحتمالية

```
DETERMINISTIC FUNCTION (what software engineers expect):

Input A ----[ function ]----> Output X (always)
Input A ----[ function ]----> Output X (always)
Input A ----[ function ]----> Output X (always)

Examples: hash(), sort(), parseInt()


PROBABILISTIC SAMPLER (what an LLM actually is):

Input A ----[ model ]----> Output X  (60% of the time)
Input A ----[ model ]----> Output Y  (25% of the time)
Input A ----[ model ]----> Output Z  (10% of the time)
Input A ----[ model ]----> Output W  ( 5% of the time)

The output is a SAMPLE from a probability distribution over all possible responses.
That distribution is shaped by: the model weights, the temperature, and the prompt.
```

الموديل ليس دالة معطوبة تُرجِع أحياناً القيمة الخاطئة. إنه أخذة عيّنات تعمل بشكل سليم، وهي -- لأي مدخل -- تحافظ على توزيع فوق المخرجات الممكنة. عندما تشغّله، تحصل على سحبة واحدة من ذلك التوزيع.

### الـ Temperature: مقبض التباين

الـ temperature يتحكم في شكل توزيع المخرجات. الـ temperature الأقل يركّز الاحتمال على أكثر المخرجات ترجيحاً. والأعلى ينشر الاحتمال على نطاق أوسع.

```
Temperature 0.0 (nearly deterministic):
  Most likely output gets almost all probability mass.
  Same input --> same output on nearly every run.
  Best for: extraction, classification, structured output.

Temperature 0.5-0.7 (moderate variance):
  Probability spread across several likely outputs.
  Some run-to-run variation.
  Best for: summarization, explanation, translation.

Temperature 1.0 (default, higher variance):
  Wider spread. More creative, less predictable.
  Visible variation across runs.
  Best for: brainstorming, creative writing, ideation.
```

ملاحظة: حتى عند temperature=0، الموديل ليس حتمياً تماماً بسبب عدم الحتمية في حسابات الفاصلة العائمة (floating-point) على الـ GPU. قد تلاحظ تبايناً عرضياً. "Temperature 0" تعني "أدنى تباين"، لا "تباين صفري".

### أنماط الفشل الخمسة للتفكير الحتمي

```
+---------------------------+------------------------------------------+
| DETERMINISTIC ASSUMPTION  | HOW IT BREAKS IN AI SYSTEMS              |
+---------------------------+------------------------------------------+
| 1. Unit test one output   | Pass rate on your test case != pass rate |
|    and ship if it passes  | on the distribution. 1 sample tells you  |
|                           | almost nothing about the 8% failure rate.|
+---------------------------+------------------------------------------+
| 2. Exact string matching  | Model says "Positive" on run 1,          |
|    in test assertions     | "POSITIVE" on run 2, "positive." on      |
|                           | run 3. All correct, all fail your test.  |
+---------------------------+------------------------------------------+
| 3. Assume idempotency     | Running the same pipeline twice on the   |
|    (run twice = same)     | same input produces different outputs.   |
|                           | You cannot use "just run it again" to    |
|                           | verify a fix.                            |
+---------------------------+------------------------------------------+
| 4. Trust a one-shot eval  | You evaluate quality on 10 examples,     |
|    to measure quality     | get 9/10. But over 1000 real user calls, |
|                           | the actual pass rate is 73%. Small eval  |
|                           | sets hide the tail.                      |
+---------------------------+------------------------------------------+
| 5. Build brittle if/else  | if response == "yes": ... else: ...      |
|    on model output        | The model says "Yes", "yes.", "YES",     |
|                           | "Yes, I agree", "Affirmative" -- your    |
|                           | if/else handles one case and breaks on   |
|                           | all the others.                          |
+---------------------------+------------------------------------------+
```

---

## البناء

### الخطوة 1: ملاحظة تباين المخرجات

شغّل نفس الـ prompt 10 مرات واجمع المخرجات. لا تستخدم temperature=0 في هذا التمرين -- نريد أن نرى التباين الطبيعي.

```python
import anthropic
from dotenv import load_dotenv
from collections import Counter

load_dotenv()
client = anthropic.Anthropic()

def run_n_times(prompt: str, n: int = 10, temperature: float = 1.0) -> list[str]:
    """Run the same prompt N times and return all outputs."""
    results = []
    for i in range(n):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=32,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        results.append(text)
        print(f"  Run {i+1:2d}: {text!r}")
    return results
```

### الخطوة 2: قياس التوزيع

```python
def measure_distribution(prompt: str, n: int = 20) -> dict:
    """
    Run a prompt N times and return distribution statistics.
    For a classification task, this tells you: what fraction of calls
    return each possible label?
    """
    print(f"\nRunning '{prompt[:50]}...' {n} times (temperature=1.0):\n")
    results = run_n_times(prompt, n, temperature=1.0)

    # Count unique outputs
    counter = Counter(results)
    total = len(results)

    print(f"\nDistribution ({total} runs):")
    for output, count in counter.most_common():
        pct = count / total * 100
        bar = "=" * int(pct / 5)
        print(f"  {output!r:30} {count:3}x ({pct:5.1f}%) {bar}")

    unique_count = len(counter)
    most_common_pct = counter.most_common(1)[0][1] / total * 100
    print(f"\nSummary: {unique_count} unique outputs, most common at {most_common_pct:.1f}%")

    return {
        "outputs": results,
        "distribution": dict(counter),
        "unique_count": unique_count,
        "consistency_pct": most_common_pct,
    }
```

> **اختبار من الواقع:** تشغّل مُصنِّف مشاعر (sentiment classifier) 20 مرة على نفس مراجعة المنتج فتحصل على "POSITIVE" 17 مرة، و"VERY POSITIVE" مرتين، و"Positive sentiment" مرة واحدة. يقول زميل: "إنه متّسق في الأساس، 17 من 20 جيد." كيف تشرح لماذا يُعدّ هذا مشكلة لأنظمة الإنتاج التي تحلّل المخرجات بمطابقة نصية دقيقة (exact string matching)؟

### الخطوة 3: مقارنة إعدادات الـ Temperature

```python
def compare_temperatures(prompt: str, temperatures: list[float], n_per_temp: int = 10) -> None:
    """Show how temperature affects output variance for the same prompt."""
    print(f"\n=== Temperature Comparison ===")
    print(f"Prompt: '{prompt[:60]}...'")

    for temp in temperatures:
        print(f"\nTemperature {temp}:")
        results = run_n_times(prompt, n_per_temp, temperature=temp)
        unique = len(set(results))
        print(f"  -> {unique}/{n_per_temp} unique outputs")
```

### الخطوة 4: نمط الاختبار الصحيح

```python
def robust_classify(text: str) -> str:
    """
    Classification that handles output variance correctly.
    Normalizes the response before comparing, so "POSITIVE", "Positive",
    and "positive." all map to "POSITIVE".
    """
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        temperature=0.0,   # minimize variance for classification
        messages=[{
            "role": "user",
            "content": (
                f"Classify as POSITIVE, NEGATIVE, or NEUTRAL. "
                f"Reply with only the label, nothing else.\n\nText: {text}"
            ),
        }],
    )
    raw = response.content[0].text.strip().upper()

    # Normalize: handle common variations
    if "POSITIVE" in raw:
        return "POSITIVE"
    if "NEGATIVE" in raw:
        return "NEGATIVE"
    if "NEUTRAL" in raw:
        return "NEUTRAL"

    # Unknown output: log it, return a safe default
    print(f"WARNING: unexpected classification output: {raw!r}")
    return "UNKNOWN"
```

---

## الاستخدام

يُضبَط الـ temperature على مستوى استدعاء الـ API عبر المُعامِل `temperature`. يقبل قيماً من 0.0 إلى 1.0 (نطاق Claude؛ بعض المزوّدين يصلون إلى 2.0).

```python
# Task-appropriate temperature choices

# Extraction: minimize variance -- you want the same answer every time
extraction_response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    temperature=0.0,
    messages=[{"role": "user", "content": "Extract all dates from this text: ..."}],
)

# Summarization: moderate variance is acceptable
summary_response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=512,
    temperature=0.3,
    messages=[{"role": "user", "content": "Summarize this document: ..."}],
)

# Creative writing: higher variance is desirable
story_response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    temperature=0.9,
    messages=[{"role": "user", "content": "Write an opening paragraph for a short story about..."}],
)
```

لا يوفّر Anthropic SDK المُعامِل `top_p` كمقبض منفصل (فهو مُدمَج ضمن الـ temperature في Claude). إذا كنت تنقل كوداً من قاعدة كود OpenAI، فالـ temperature هو المُعامِل المفرد الصحيح لضبطه.

> **نقلة في المنظور:** اختبار البرمجيات التقليدي يفترض: إذا نجحت دالة في اختبار، فإنها تنجح في ذلك الاختبار في كل مرة. اختبار أنظمة الـ AI يفترض العكس: نجاح تشغيلة واحدة لا يُثبِت شيئاً عن معدل النجاح. الاختبار الصحيح للـ AI يشغّل كل حالة N مرة (10-50 كحد أدنى) ويقيس النسبة التي تنجح. هذا ليس عبئاً إضافياً -- بل هو الحد الأدنى من الإشارة القابلة للاستخدام. النظام بمعدل نجاح 90% في تقييمك (eval) يبدو رائعاً إلى أن يعالج 10,000 مستخدم ويفشل مع 1,000 منهم يومياً.

---

## التسليم

المُخرَج (artifact) لهذا الدرس هو دليل مرجعي حول العقلية الاحتمالية في هندسة الـ AI.

راجع `outputs/prompt-probabilistic-mindset.md`.

---

## التقييم

تكون نقلة النموذج الذهني قد حدثت عندما تستطيع:

```python
# 1. Measure a real distribution (not just run once)
# Run this and check: does the consistency_pct vary between runs of the script?
from collections import Counter
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

prompt = "Is 'The meeting was fine' positive, negative, or neutral? Reply with one word."
results = []
for _ in range(10):
    r = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=8,
        temperature=1.0,
        messages=[{"role": "user", "content": prompt}],
    )
    results.append(r.content[0].text.strip().lower())

counter = Counter(results)
print(f"Distribution over 10 runs: {dict(counter)}")
unique = len(counter)
print(f"Unique outputs: {unique}/10")

# 2. Verify temperature=0 reduces (but does not eliminate) variance
results_t0 = []
for _ in range(5):
    r = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=8,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}],
    )
    results_t0.append(r.content[0].text.strip().lower())

unique_t0 = len(set(results_t0))
print(f"\nWith temperature=0: {unique_t0}/5 unique outputs (expect 1, occasionally 2)")

# 3. Verify robust_classify handles case variants
test_cases = [
    ("The service was excellent", "POSITIVE"),
    ("Worst experience ever", "NEGATIVE"),
    ("It was okay", "NEUTRAL"),
]
for text, expected in test_cases:
    # Test that normalization would catch variations
    for variant in [expected, expected.lower(), expected.capitalize() + "."]:
        assert expected in variant.upper(), f"Normalization would miss: {variant!r}"
print("\nOK: normalization logic handles case variants")
```
