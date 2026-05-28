# الـ SLOs والـ SLIs والتنبيه (Alerting) لميزات الذكاء الاصطناعي

> عرّف معنى "الجيد" قبل أن تطلق. "المستخدمون يشتكون" ليس مقياسًا.

**النوع:** تعلّم
**اللغات:** Python
**المتطلبات:** المرحلة 07 الدروس 01-10 (الـ observability، والتكلفة، وزمن الاستجابة)، المرحلة 06 (الإطلاق)
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- تعريف الـ SLIs والـ SLOs لمقاييس ميزة الذكاء الاصطناعي الستة الأساسية
- كتابة ميزانيات أخطاء (error budgets) تترجم أهداف الـ SLO إلى عتبات قابلة للتنفيذ
- تنفيذ صنف `SLOMonitor` يتتبّع جميع الـ SLIs الستة ويُصدر تنبيهات بنيوية عند التجاوز
- ربط مقاييس الـ SLO بصيغة Prometheus للتكامل مع Grafana
- التمييز بين التنبيهات القابلة للتنفيذ والتنبيهات المزعجة (noise)

---

## المشكلة

تُطلق ميزة ذكاء اصطناعي بهدف توافر (availability SLO) قدره 99.5% لأن هذا ما تملكه كل الخدمات الأخرى. بعد ثلاثة أشهر، يصلك تصعيد: "إجابات الذكاء الاصطناعي تزداد سوءًا." تتحقّق من لوحاتك. التوافر 99.7%. زمن الاستجابة عند p95 ضمن الحدود. معدّل الخطأ 0.3%. كل شيء أخضر.

لكن إجابات الذكاء الاصطناعي كانت تزداد سوءًا منذ أسبوعين لأن SLI درجة الـ eval لم يُعرَّف قط. لم يختر أحد عتبة. كان المقياس يُجمَع لكنه لا يُراقَب.

هذه هي الفجوة بين observability الخدمات التقليدية وobservability ميزات الذكاء الاصطناعي. تغطي الـ SLIs التقليدية التوافر، وزمن الاستجابة، ومعدّل الخطأ. هذه ضرورية لكنها غير كافية. لميزات الذكاء الاصطناعي ثلاثة SLIs إضافية لا تعرفها أنظمة المراقبة التقليدية: درجة الـ eval (الجودة)، ومعدّل إصابة الكاش (cache hit rate) (كفاءة التكلفة)، والتكلفة لكل طلب (صحّة الميزانية). إذا راقبت الثلاثة التقليدية فقط، فقد تكون لوحاتك خضراء بينما ميزة الذكاء الاصطناعي لديك تتدهور بصمت.

الحل هو تعريف جميع الـ SLIs الستة قبل الإطلاق وضبط عتبات التنبيه في الوقت نفسه. هذا الدرس يبني صنف المراقبة ومنطق التنبيه.

---

## المفهوم

### الـ SLIs الستة للذكاء الاصطناعي مع أمثلة أهداف

```
+---------------------+------------------+------------------+------------------+
| SLI                 | What it measures | Target           | Alert threshold  |
+---------------------+------------------+------------------+------------------+
| Availability        | % requests that  | >= 99.5%         | < 99.0%          |
|                     | get a response   | (30-day window)  | for 5 min        |
+---------------------+------------------+------------------+------------------+
| Latency (TTFT)      | Time to first    | p95 < 2000ms     | p95 > 3000ms     |
|                     | token            | (1-hour window)  | for 10 min       |
+---------------------+------------------+------------------+------------------+
| Error rate          | % requests with  | < 1.0%           | > 2.0%           |
|                     | non-retried err  | (15-min window)  | for 5 min        |
+---------------------+------------------+------------------+------------------+
| Eval score          | Quality score    | >= 0.80 mean     | < 0.75 mean      |
|                     | from eval suite  | (24-hour window) | for 1 hour       |
+---------------------+------------------+------------------+------------------+
| Cache hit rate      | Prompt cache     | >= 40%           | < 20%            |
|                     | hits / total     | (1-hour window)  | for 30 min       |
+---------------------+------------------+------------------+------------------+
| Cost per request    | USD per LLM call | <= $0.005 mean   | > $0.008 mean    |
|                     | (incl. retries)  | (1-hour window)  | for 15 min       |
+---------------------+------------------+------------------+------------------+
```

### ميزانيات الأخطاء (Error Budgets)

تحوّل ميزانية الأخطاء نسبة الـ SLO المئوية إلى مخصّص يمكنك إنفاقه:

```
99.5% availability SLO over 30 days
= 0.5% allowed downtime
= 0.005 x 30 days x 24 hours x 60 min = 216 minutes of allowed downtime

Error budget burn rate:
  Normal: consuming ~7 min/day of budget -> fine
  Alert:  consuming > 30 min/day (3x normal) -> investigate
  Page:   consuming > 100 min/day (14x normal) -> incident
```

يلتقط التنبيه بمعدّل الاستهلاك (burn rate) استنزاف الميزانية قبل وقوعه. إذا كنت تستهلك بمعدّل 14 ضعفًا للمعدّل الطبيعي، فستستنزف ميزانية الـ 30 يومًا خلال يومين.

---

## البناء

ثبّت المتطلبات:

```bash
pip install pydantic
```

يتتبّع `SLOMonitor` نوافذ متدرّجة (rolling windows) لكل SLI ويُصدر تنبيهات عند تجاوز العتبات:

```python
from slo_monitor import SLOMonitor, RequestEvent, AlertLevel

monitor = SLOMonitor()

# Record each LLM call
monitor.record(RequestEvent(
    ttft_ms=450,
    total_latency_ms=2100,
    error=False,
    cache_hit=True,
    cost_usd=0.0035,
    eval_score=0.87,
))

# Check for SLO breaches
alerts = monitor.check_slos()
for alert in alerts:
    print(f"[{alert.level}] {alert.sli_name}: {alert.message}")

# Get current status
status = monitor.status()
print(status.to_dict())
```

المخرجات المتوقعة (نظام سليم):

```
SLO Status Report
-----------------
availability:    99.8% [OK]   (target: >= 99.5%)
ttft_p95:        980ms [OK]   (target: <= 2000ms)
error_rate:      0.2%  [OK]   (target: <= 1.0%)
eval_score_mean: 0.86  [OK]   (target: >= 0.80)
cache_hit_rate:  47%   [OK]   (target: >= 40%)
cost_p95:        $0.004 [OK]  (target: <= $0.005)
```

المخرجات المتوقعة (تجاوز SLO):

```
[WARNING] eval_score: Mean eval score 0.74 is below SLO target 0.80. 24-hour window. Breach duration: 72 min.
[WARNING] cache_hit_rate: Cache hit rate 18% is below SLO target 40%. 1-hour window. Breach duration: 35 min.
```

> **اختبار من الواقع:** لماذا نافذة SLI درجة الـ eval (eval_score) مدتها 24 ساعة بينما نافذة معدّل الخطأ (error_rate) مدتها 15 دقيقة؟ لأن درجات الـ eval تتطلب تشغيل مجموعة التقييم لديك، التي تعالج عادةً عيّنة من ترافيك الإنتاج بشكل غير متزامن. لا يمكنك حساب درجات الـ eval في الوقت الحقيقي. نافذة الـ 24 ساعة هي الحد الأدنى للنافذة ذات المعنى إذا كان خط أنابيب الـ eval لديك يعمل مرة كل ساعة على عيّنة مدتها 24 ساعة. إذا أطلقت تنبيهًا على نافذة eval مدتها ساعة واحدة، فأنت تُطلق تنبيهًا على عدد عيّنات أقل من أن يكون ذا دلالة إحصائية.

شغّل التنفيذ:

```bash
python code/main.py
```

---

## الاستخدام

اكشف مقاييس الـ SLO بصيغة Prometheus لأجل Grafana:

```python
from prometheus_client import Gauge, start_http_server

# Define Prometheus gauges
slo_gauges = {
    "availability": Gauge("ai_slo_availability_ratio", "Availability SLI ratio"),
    "ttft_p95_ms": Gauge("ai_slo_ttft_p95_ms", "TTFT p95 in milliseconds"),
    "error_rate": Gauge("ai_slo_error_rate_ratio", "Error rate ratio"),
    "eval_score": Gauge("ai_slo_eval_score_mean", "Mean eval score"),
    "cache_hit_rate": Gauge("ai_slo_cache_hit_rate_ratio", "Cache hit rate ratio"),
    "cost_p95_usd": Gauge("ai_slo_cost_p95_usd", "Cost p95 in USD"),
}

def push_slo_metrics(monitor: SLOMonitor):
    status = monitor.status()
    slo_gauges["availability"].set(status.availability)
    slo_gauges["ttft_p95_ms"].set(status.ttft_p95_ms)
    slo_gauges["error_rate"].set(status.error_rate)
    slo_gauges["eval_score"].set(status.eval_score_mean)
    slo_gauges["cache_hit_rate"].set(status.cache_hit_rate)
    slo_gauges["cost_p95_usd"].set(status.cost_p95_usd)

# In your FastAPI app
start_http_server(9090)  # Prometheus scrapes :9090/metrics
```

> **نقلة في المنظور:** تبدو مقاييس Prometheus من نوع gauge كهندسة مفرطة حين تُعدّها لأول مرة، لكنها تطلق قوة خارقة: لوحات يستطيع أصحاب المصلحة من غير المهندسين قراءتها. مدير منتج ينظر إلى لوحة Grafana بها لوحات حالة SLO خضراء/حمراء يستطيع أن يجيب بنفسه عن سؤال "هل ميزة الذكاء الاصطناعي سليمة؟" دون فتح تذكرة. تكلفة الهندسة هي بعد ظهر واحد من الإعداد. والفائدة التنظيمية هي القضاء على فئة كاملة من أسئلة الحالة.

---

## التسليم

مخرَج هذا الدرس هو `outputs/skill-ai-slo-template.md`: قالب يعرّف جميع الـ SLIs الستة للذكاء الاصطناعي مع أمثلة أهداف وعتبات تنبيه، جاهز للتخصيص لخدمتك.

انسخ القالب إلى دليل التشغيل (ops runbook) لخدمتك. املأ أهدافك المحددة بناءً على خطوط أساس اختبار الحمل لديك من الدرس 10. عرّف توجيه التنبيهات (من يُستدعى لأي مستوى) قبل أن تطلق.

---

## التقييم

**مراجعة SLO قبل الإطلاق:** قبل إطلاق أي ميزة ذكاء اصطناعي، يوقّع قائد الفريق على أن جميع الـ SLIs الستة لها هدف معرّف، وعتبة تنبيه معرّفة، ومالك تنبيه معرّف. لا ينبغي لأي SLI أن يحمل "TBD" بجانبه حين تضغط زر النشر (deploy).

**تدقيق ضوضاء التنبيهات:** بعد أسبوع واحد من التنبيهات في الإنتاج، احسب معدّل الإيجابيات الكاذبة (false-positive): التنبيهات التي أُطلقت ثم انحلّت دون أي إجراء هندسي. إذا كان أكثر من 20% من التنبيهات إيجابيات كاذبة، فالعتبة شديدة الحساسية. وسّعها. وإذا كان أكثر من 10% من الحوادث لم يسبقها تنبيه، فالعتبة متساهلة جدًا. شدّدها.

**مراجعة ميزانية الأخطاء:** مراجعة أسبوعية لاستهلاك ميزانية الأخطاء عبر جميع الـ SLIs الستة. إذا كان أي SLI يستهلك الميزانية بأسرع من ضعف المعدّل المتوقع، فهذا مؤشر مبكّر على فوات SLO مستقبلي. تصرّف قبل أن يُظهر التقرير الشهري تجاوزًا.
