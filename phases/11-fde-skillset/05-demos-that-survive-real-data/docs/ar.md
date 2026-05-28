# عروض تصمد أمام البيانات الحقيقية

> عرض (demo) يعمل على 3 أمثلة منتقاة يدويًا ويفشل على أول ملف حقيقي للعميل أسوأ من غياب العرض كليًا.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 11-02 تحديد النطاق قبل الحل، المرحلة 05 (أساسيات التقييم)
**الوقت:** ~60 دقيقة
**المرحلة:** 11 - مهارات الـ FDE

## أهداف التعلّم

- تسمية أنماط إخفاق العرض الأربعة وشرح كيف يتجلّى كل منها
- بناء فئة (class) باسم DemoTester تشغّل دالة عرض على مجموعة بيانات عيّنة وتُبلّغ عن معدّل الإخفاق وزمن الاستجابة واتساق صيغة المخرج
- تطبيق DemoTester على عرض استخراج وهمي قبل عرض تقديمي أمام عميل
- إنشاء بروتوكول اختبار ما قبل العرض باستخدام أثر قائمة التحقّق
- شرح لماذا يكون الاختبار على 20 عيّنة حقيقية أو أكثر من العميل غير قابل للتفاوض قبل العرض

---

## المشكلة

إنه يوم العرض. بنيت نظام استخراج مستندات يستخرج الحقول الأساسية من عقود PDF. في بيئة اختبارك، يعمل بشكل مثالي على العقود الثلاثة العيّنة التي استخدمتها أثناء التطوير. يبدأ العرض. على أول عقد يرفعه العميل من نظامه، يُخرِج النموذج كائن JSON فارغًا. والعقد الثاني يسبّب KeyError. والثالث يستغرق 45 ثانية لأنه من 60 صفحة ولم تختبر قطّ على مستندات طويلة.

انتهى العرض. العميل مهذّب لكن الطاقة تبدّلت. يقول إنه يودّ "أن يراه مجددًا حين يصبح أكثر استقرارًا." لا تحصل على انطباع أول ثانٍ.

هذا السيناريو هو أكثر إخفاقات العروض قابلية للمنع في هندسة الذكاء الاصطناعي. الإصلاح ليس كتابة كود أفضل. الإصلاح هو الاختبار على بيانات حقيقية من العميل، بأحجام مدخلات واقعية، قبل أن تدخل غرفة العرض. DemoTester موجود كي لا يحدث هذا لك أبدًا.

---

## المفهوم

### أنماط إخفاق العرض الأربعة

```
FAILURE MODE        WHAT IT LOOKS LIKE              DETECTION METHOD
------------------  ------------------------------  -----------------------
Hardcoded samples   Works on your 3 test files,     Run on 20+ real customer
                    fails on customer's first file  samples before demo

No error handling   Crashes on malformed input,     Test with malformed,
                    empty files, or unexpected      empty, and edge-case
                    formats                         inputs explicitly

Latency cliff       Fast on your short examples,    Measure latency on the
                    stalls or times out on long     full distribution of
                    customer documents              realistic input sizes

Output format       Model produces valid output     Ask customer to confirm
mismatch            but not in the format the       expected format before
                    customer expected               demo, test against it
```

لكل نمط إخفاق اختبار محدّد يلتقطه قبل العرض. وDemoTester يشغّل الأربعة جميعًا.

### بروتوكول اختبار ما قبل العرض

```
Step 1: GET REAL DATA (at least 20 samples)
  - Ask customer: "Can you share 20-30 real examples from your system?"
  - If they can't: ask for anonymized or redacted versions
  - If they won't: be explicit that the demo will be on synthetic data

Step 2: RUN FAILURE RATE TEST
  - Run your demo function on all 20+ samples
  - Target: failure rate below 5% before demo
  - If above 5%: fix the failures or delay the demo

Step 3: MEASURE LATENCY DISTRIBUTION
  - Run on samples at the realistic size range (not just short ones)
  - Target: p95 latency below your requirement (typically 2-10s)
  - If above: test caching, chunking, or async approaches

Step 4: VERIFY OUTPUT FORMAT
  - Confirm with customer: "Here is the output format the system produces.
    Is this what you expected?"
  - Check field names, data types, nesting
  - Test that your parsing code handles empty fields, null values

Step 5: TEST EDGE CASES EXPLICITLY
  - Empty input
  - Minimum length input
  - Maximum length input (your latency cliff)
  - Input with unexpected characters or encoding

Step 6: REHEARSE
  - Do one full demo run with the customer's actual data before demo day
  - Use the same laptop and network you will use in the demo
```

---

## البناء

ابنِ فئة (class) باسم `DemoTester` تشغّل دالة عرض على مجموعة بيانات عيّنة وتنتج تقرير اختبار يغطّي معدّل الإخفاق وتوزيع زمن الاستجابة واتساق صيغة المخرج.

يقبل المُختبِر أيّ قابل للاستدعاء (callable) كدالة عرض، ويشغّله على قائمة من المدخلات الاختبارية، ويقيس:
- معدّل النجاح (الدالة تعود بلا استثناء)
- زمن الاستجابة لكل استدعاء (p50، p95، p99)
- اتساق صيغة المخرج (وجود الحقول المتوقعة)

```python
from demo_tester import DemoTester

# Define what your demo function does
def my_extraction_demo(document_text: str) -> dict:
    # your LLM call here
    ...

# Define what a valid output looks like
expected_fields = ["contract_date", "party_a", "party_b", "total_value", "duration"]

# Run the tester
tester = DemoTester(
    demo_fn=my_extraction_demo,
    expected_fields=expected_fields,
    latency_threshold_p95=5.0,  # seconds
)
report = tester.run(samples=my_20_real_samples)
tester.print_report(report)
```

مثال على المخرج:

```
=== DEMO TEST REPORT ===

Samples tested: 24
Success rate:   87.5% (21/24 passed)
  Failed samples: #8, #15, #22

Latency:
  p50:  1.2s
  p95:  4.8s
  p99:  12.3s  [!] WARNING: p95 is near threshold (5.0s)
  Max:  18.7s  [!] LATENCY CLIFF: 3 samples over 10s (samples #14, #19, #23)

Output format:
  All required fields present: 83.3% (20/24 samples)
  Missing fields by frequency:
    contract_date: missing in 4 samples
    total_value:   missing in 1 sample

DEMO READINESS:
  [FAIL] Failure rate 12.5% exceeds 5% threshold.
  [WARN] p95 latency (4.8s) near threshold (5.0s).
  [WARN] 3 samples cause latency cliff (over 10s). Check if demo inputs include long documents.
  [FAIL] Output format incomplete in 4 samples (contract_date missing).

ACTION ITEMS (before demo):
  1. Investigate failures in samples #8, #15, #22.
  2. Fix or handle missing contract_date extraction.
  3. Test longest customer documents to understand latency cliff.
  4. Do not demo until failure rate is below 5%.
```

قسم `DEMO READINESS` يعطي إشارة المضي/التوقف (go/no-go). العرض غير جاهز إن تجاوز معدّل الإخفاق 5% أو إن غابت الحقول المطلوبة في أكثر من 10% من العيّنات.

> **اختبار من الواقع:** تشغّل DemoTester فتحصل على معدّل إخفاق 12.5%، قبل العرض بثلاثة أيام. تحقّق فتجد أن الإخفاقات الثلاثة جميعها على عقود بعناوين (headers) غير قياسية. لديك خياران: إصلاح المحلّل (parser) ليتعامل مع العناوين غير القياسية، أو ترشيح هذه العيّنات من العرض وعرض العقود التي تعمل فقط. أيهما الصحيح؟ أصلِح المحلّل إن كان بإمكانك ذلك خلال يومين. وإن لم تستطع، فأجرِ محادثة صريحة مع العميل: "حدّدنا فئة من المستندات يتعامل معها الإصدار الحالي بموثوقية أقل. سنُريك الحالات التي يعمل فيها بشكل جيد اليوم ونعالج الحالات الطرفية في التكرار التالي." إخفاء الإخفاقات بانتقاء مدخلات العرض هو الخطوة الخطأ. سيكتشفها العميل بعد العرض.

التنفيذ الكامل في `code/main.py`. وهو يتضمّن فئة `DemoTester`، ودالة عرض استخراج وهمية للاختبار، وواجهة سطر أوامر لتشغيل المُختبِر على مجموعة بيانات JSON.

---

## الاستخدام

طبّق DemoTester على عرض استخراج عقود وهمي.

عرّف دالة عرض وهمية تستخرج الحقول من نص العقد باستخدام Claude:

```python
import anthropic

client = anthropic.Anthropic()

def extract_contract_fields(document_text: str) -> dict:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""Extract these fields from the contract as JSON:
contract_date, party_a, party_b, total_value, duration

Contract:
{document_text}

Return only valid JSON."""
        }]
    )
    import json
    return json.loads(response.content[0].text)
```

ابنِ مجموعة بيانات اختبار صغيرة بـ 20 عيّنة واقعية أو أكثر تتضمّن حالات طرفية:

```python
SAMPLES = [
    # Normal contracts
    "This Agreement is entered into on January 15, 2024...",
    # Short contracts (edge case)
    "Service agreement. Party A: Acme Corp. Party B: Globex. Amount: $5,000.",
    # Long contracts (latency cliff test)
    "MASTER SERVICE AGREEMENT\n" + "..." * 2000,
    # Malformed input
    "",
    # Non-standard format
    "CONTRATO DE SERVICIOS\nFecha: 15 enero 2024...",
]

tester = DemoTester(
    demo_fn=extract_contract_fields,
    expected_fields=["contract_date", "party_a", "party_b", "total_value", "duration"],
    latency_threshold_p95=5.0,
    failure_rate_threshold=0.05,
)
report = tester.run(SAMPLES)
tester.print_report(report)
```

شغّله:
```bash
python main.py --samples contracts.json --fields contract_date,party_a,party_b,total_value
```

يكشف المُختبِر أيّ المدخلات تفشل، وأين يقع منحدر زمن الاستجابة (latency cliff)، وأيّ الحقول يُستخرَج بشكل غير متّسق. أصلِح الإخفاقات، ثم شغّل مجددًا. كرّر حتى يجتاز فحص جاهزية العرض.

> **نقلة في المنظور:** مهندس ضمان جودة (QA) يقرأ هذا قد يتعرّف عليه كمجموعة اختبارات (test suite). أما الـ FDE فيضيف شيئًا قد لا يضيفه مهندس الـ QA: مفهوم "جاهزية العرض" كبوابة ثنائية (binary gate). اختبارات الوحدة تفحص الصحة بمعزل. أما DemoTester فيفحص سلوكًا قريبًا من الإنتاج: معدّل الإخفاق على مدخلات واقعية، وزمن الاستجابة عند أحجام واقعية، واتساق الصيغة مقابل توقعات العميل. اجتياز مجموعة اختبارات الوحدة لا يضمن اجتياز العرض. DemoTester هو الفحص المحدّد بين "الكود يعمل في بيئتي" و"العرض يعمل أمام عميل".

---

## التسليم

الأثر القابل لإعادة الاستخدام في هذا الدرس هو `outputs/skill-demo-prep-checklist.md`: قائمة تحقّق لتجهيز ما قبل العرض تضم أنماط الإخفاق الأربعة، وبروتوكول الاختبار ذا الخطوات الست، ومصفوفة قرار المضي/التوقف. امضِ خلالها قبل كل عرض موجّه للعميل.

---

## التقييم

كيف تعرف أن عملية تجهيز العرض تعمل:

1. **معدّل نجاح العرض** - أوضح إشارة. تابع نسبة العروض التي تُشغَّل بلا إخفاق للنظام أمام العميل. الهدف: 100%. أيّ إخفاق أثناء العرض حدث قابل للمنع لو اتُّبِع بروتوكول اختبار ما قبل العرض.

2. **معدّل إخفاق DemoTester وقت العرض** - سجّل معدّل الإخفاق الذي يُبلّغ عنه DemoTester في اليوم السابق للعرض. إن كانت العروض تُشغَّل باستمرار بمعدّلات إخفاق تفوق 5%، فالبروتوكول يُتخطّى. الهدف: كل العروض تُشغَّل بمعدّل إخفاق دون 5%.

3. **مفاجآت زمن الاستجابة في العرض** - تابع الحالات التي شهد فيها العرض زمن استجابة لاحظه العميل (توقفات، انتهاء مهلات). كل حالة تمثّل منحدر زمن استجابة كان ينبغي لبروتوكول ما قبل العرض التقاطه. السبب الجذري: إما أن DemoTester لم يُشغَّل، أو أن أحجام المدخلات الواقعية لم تُختبَر.

4. **ملاحظات صيغة المخرج بعد العرض** - "هذه ليست الصيغة التي توقعناها" تعليق قابل للمنع. تابع تكراره. كل ظهور يعني أن خطوة تأكيد صيغة المخرج (الخطوة 4 في البروتوكول) تُخطّيت. الهدف: صفر مفاجآت صيغة بعد العرض.
