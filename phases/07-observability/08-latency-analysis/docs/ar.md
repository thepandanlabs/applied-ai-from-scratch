# زمن الاستجابة (Latency): p50/p95/p99 وTTFT وأين يضيع الوقت

> الـ p50 يخبرك بما يختبره أغلب المستخدمين. أما p99 فيخبرك بمن سيغادر.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** المرحلة 07 الدرسان 01 و05 (أساسيات الـ Observability، تسجيل طلبات الـ LLM)
**الوقت:** ~60 دقيقة
**أهداف التعلّم:**
- تفكيك زمن استجابة طلب الـ LLM إلى مكوّناته: الشبكة، وTTFT، والتوليد، والمعالجة اللاحقة
- قياس زمن الوصول إلى أول توكن (time-to-first-token أو TTFT) بشكل منفصل عن إجمالي زمن الاستجابة في النقاط المتدفقة (streaming endpoints)
- حساب النسب المئوية p50 وp95 وp99، وشرح لماذا يهم p99 في الاحتفاظ بالمستخدمين
- تحديد أي مكوّن من مكوّنات زمن الاستجابة هو عنق الزجاجة انطلاقًا من توزيع النسب المئوية
- ربط `LatencyProfiler` بنقطة طرفية متدفقة (streaming endpoint)

---

## المشكلة

ميزة الذكاء الاصطناعي لديك تبلغ زمن استجابتها عند p50 نحو 1.2 ثانية. تبدو ممتازة أثناء الاختبار، فتطلقها.

بعد شهرين، يُظهر تحليل المغادرة (churn) أن المستخدمين الذين يختبرون استجابات تتجاوز 4 ثوانٍ أكثر عرضةً بثلاثة أضعاف لعدم العودة. تنظر إلى بيانات زمن الاستجابة لأول مرة. لا تملك نسبًا مئوية. لا تملك TTFT. تملك متوسط زمن استجابة: 1.4 ثانية. يبدو جيدًا.

ما فاتك: زمن الاستجابة عند p99 يبلغ 8.7 ثانية. واحد من كل 100 طلب يستغرق قرابة 9 ثوانٍ. عند 10,000 مستخدم يوميًا، هذا يعني 100 شخص يوميًا يختبرون انتظارًا مدته 8.7 ثانية. كل يوم. لمدة شهرين. أي 6,000 شخص حصلوا على تجربة سيئة بما يكفي لرفع معدّل المغادرة لديك.

المتوسط (mean) كذب عليك. النسب المئوية ما كانت لتكذب.

---

## المفهوم

### أين يضيع الوقت في طلب LLM متدفق

```
Request timeline (wall clock):

[Client sends request]
     |
     |---- Network: client to API edge -----------| ~50-150ms (varies by region)
                                                  |
     |---- API queuing + scheduling -------| ~10-100ms (varies by load)
                                           |
     |---- Prompt processing (prefill) ---| ~50-500ms (scales with prompt length)
                                          |
                                          | FIRST TOKEN ARRIVES HERE  <-- TTFT
                                          |
     |--- Generation (decode) -------------------------| ms/token * output_tokens
                                                       |
     |--- Network: API to client (streaming chunks) --| per-chunk latency
                                                      |
     [Last token received]                            |
     |--- Post-processing (parse, validate, format) --| ~1-50ms
     [Response delivered to user]
```

**فكرة جوهرية للـ streaming:** يرى المستخدمون أول توكن قبل اكتمال التوليد. الـ TTFT هو ما يحدد إن كانت الواجهة "تبدو" سريعة الاستجابة. وإجمالي زمن الاستجابة هو ما يحدد متى يستطيع المستخدم التصرّف بناءً على الاستجابة الكاملة. كلاهما مهم؛ لكنهما مهمان بطرق مختلفة.

### النسب المئوية ولماذا يضلّلك المتوسط

```
Example latency distribution (1000 requests):
  800 requests: 0.8 - 1.5 seconds   (fast, warm paths)
  150 requests: 2.0 - 3.5 seconds   (cold starts, longer prompts)
   40 requests: 4.0 - 6.0 seconds   (retry paths, peak load)
   10 requests: 7.0 - 12.0 seconds  (timeout edge cases, network issues)

Statistics:
  mean:   1.8 seconds   (pulled up by the tail - looks acceptable)
  median: 1.2 seconds   (p50 - what most users experience)
  p95:    4.2 seconds   (1 in 20 users waits this long)
  p99:    8.7 seconds   (1 in 100 users waits this long)
  p999:  11.5 seconds   (1 in 1000 users - may trigger client timeouts)

Mean: 1.8s looks fine. p99: 8.7s does not.
```

**عتبات تجربة المستخدم (لميزات الذكاء الاصطناعي):**
```
Under 1s   : Feels instant, no perceived latency
1s - 3s    : Acceptable for complex AI tasks
3s - 5s    : Users notice the wait; some abandon
Over 5s    : Significant abandonment; clear UX damage
Over 10s   : Timeout territory; users assume it is broken
```

### معادلة تجربة المستخدم في الـ Streaming

في الاستجابات غير المتدفقة (non-streaming)، إجمالي زمن الاستجابة هو ما ينتظره المستخدم.
أما في الاستجابات المتدفقة، فتتغيّر معادلة تجربة المستخدم:

```
Perceived wait  =  TTFT   (until UI shows "thinking is done, here it comes")
Content quality  =  total response / generation time
User patience   =  f(TTFT)  -- users tolerate long generation if TTFT is low
```

لهذا السبب يهم الـ streaming. توليد إجماليّ مدته 5 ثوانٍ بـ TTFT يبلغ 300ms يبدو مقبولًا. أما توليد إجمالي مدته 5 ثوانٍ بـ TTFT يبلغ 4 ثوانٍ فيبدو معطّلًا.

---

## البناء

### الخطوة 1: قياس TTFT مع الـ Streaming

```python
import time
import anthropic
from typing import Optional, Iterator

client = anthropic.Anthropic()


def stream_with_ttft(
    prompt: str,
    model: str = "claude-3-5-haiku-20241022",
) -> tuple[str, float, float]:
    """
    Stream a response and measure TTFT and total latency separately.

    Returns:
        (full_response_text, ttft_ms, total_latency_ms)
    """
    start = time.monotonic()
    ttft_ms: Optional[float] = None
    chunks: list[str] = []

    with client.messages.stream(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text_chunk in stream.text_stream:
            if ttft_ms is None:
                ttft_ms = (time.monotonic() - start) * 1000
            chunks.append(text_chunk)

    total_ms = (time.monotonic() - start) * 1000
    return "".join(chunks), ttft_ms or total_ms, total_ms
```

### الخطوة 2: حاسبة النسب المئوية

```python
import statistics
from dataclasses import dataclass


@dataclass
class PercentileReport:
    count: int
    p50_ms: float
    p75_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    mean_ms: float


def compute_percentiles(latencies_ms: list[float]) -> PercentileReport:
    """
    Compute latency percentiles from a list of measurements.
    Uses linear interpolation (the standard definition).
    """
    if not latencies_ms:
        raise ValueError("Cannot compute percentiles of empty list")

    sorted_vals = sorted(latencies_ms)
    n = len(sorted_vals)

    def percentile(p: float) -> float:
        """Linear interpolation percentile."""
        idx = (p / 100) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return round(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac, 2)

    return PercentileReport(
        count=n,
        p50_ms=percentile(50),
        p75_ms=percentile(75),
        p90_ms=percentile(90),
        p95_ms=percentile(95),
        p99_ms=percentile(99),
        min_ms=round(min(sorted_vals), 2),
        max_ms=round(max(sorted_vals), 2),
        mean_ms=round(statistics.mean(sorted_vals), 2),
    )
```

### الخطوة 3: LatencyProfiler

```python
import json
from collections import defaultdict
from datetime import datetime, timezone


class LatencyProfiler:
    """
    Tracks TTFT and total latency across multiple calls.
    Computes percentiles and identifies the latency bottleneck.

    Usage:
        profiler = LatencyProfiler()

        response, ttft, total = stream_with_ttft(prompt)
        profiler.record(ttft_ms=ttft, total_ms=total, feature="search")

        report = profiler.report()
        print(report)
    """

    def __init__(self):
        self._ttft_records: list[float] = []
        self._total_records: list[float] = []
        self._by_feature: dict[str, list[tuple[float, float]]] = defaultdict(list)

    def record(
        self,
        ttft_ms: float,
        total_ms: float,
        feature: str = "default",
    ) -> None:
        """Record one latency measurement."""
        self._ttft_records.append(ttft_ms)
        self._total_records.append(total_ms)
        self._by_feature[feature].append((ttft_ms, total_ms))

    def report(self) -> str:
        """Render an ASCII latency report."""
        if not self._ttft_records:
            return "No data recorded."

        ttft_stats = compute_percentiles(self._ttft_records)
        total_stats = compute_percentiles(self._total_records)

        # Estimate generation time = total - TTFT (approximate)
        gen_times = [
            t - f for f, t in zip(self._ttft_records, self._total_records)
        ]
        gen_stats = compute_percentiles(gen_times)

        lines = []
        lines.append("=" * 60)
        lines.append("LATENCY REPORT")
        lines.append("=" * 60)
        lines.append(f"Total measurements : {ttft_stats.count}")

        lines.append("\n--- Time-to-First-Token (TTFT) ---")
        lines.append(_stats_table(ttft_stats))

        lines.append("\n--- Total Latency ---")
        lines.append(_stats_table(total_stats))

        lines.append("\n--- Generation Time (Total - TTFT) ---")
        lines.append(_stats_table(gen_stats))

        # Bottleneck analysis
        lines.append("\n--- Bottleneck Analysis ---")
        ttft_share = ttft_stats.p99_ms / total_stats.p99_ms * 100 if total_stats.p99_ms else 0
        gen_share = 100 - ttft_share
        lines.append(f"At p99: TTFT = {ttft_share:.0f}% of total, generation = {gen_share:.0f}%")
        if ttft_share > 60:
            lines.append("  -> Bottleneck: network + prefill (TTFT dominates)")
            lines.append("     Fix: prompt compression, CDN edge, or async prefill")
        else:
            lines.append("  -> Bottleneck: generation (output tokens dominate)")
            lines.append("     Fix: max_tokens limit, output length instructions, or streaming")

        # Per-feature breakdown
        if len(self._by_feature) > 1:
            lines.append("\n--- By Feature (p99 Total) ---")
            for feat, records in sorted(self._by_feature.items()):
                totals = [r[1] for r in records]
                stats = compute_percentiles(totals)
                lines.append(
                    f"  {feat:<25} n={stats.count:>4}  "
                    f"p50={stats.p50_ms:>7.0f}ms  p99={stats.p99_ms:>7.0f}ms"
                )

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    def alert_threshold_violations(
        self, p99_threshold_ms: float = 5000.0
    ) -> list[dict]:
        """
        Return records where total latency exceeded the threshold.
        Useful for feeding into alerting or SLO dashboards.
        """
        violations = []
        for i, (ttft, total) in enumerate(
            zip(self._ttft_records, self._total_records)
        ):
            if total > p99_threshold_ms:
                violations.append({"index": i, "ttft_ms": ttft, "total_ms": total})
        return violations


def _stats_table(s: PercentileReport) -> str:
    return (
        f"  min={s.min_ms:>7.0f}ms  "
        f"p50={s.p50_ms:>7.0f}ms  "
        f"p95={s.p95_ms:>7.0f}ms  "
        f"p99={s.p99_ms:>7.0f}ms  "
        f"max={s.max_ms:>7.0f}ms  "
        f"mean={s.mean_ms:>7.0f}ms"
    )
```

> **اختبار من الواقع:** يقول مدير المنتج لديك: "متوسط زمن الاستجابة لدينا 1.4 ثانية، وهو ضمن الهدف البالغ 3 ثوانٍ بأريحية. لا نحتاج إلى تتبّع النسب المئوية." أنت تعرف من البيانات أن p99 يبلغ 8.7 ثانية. كيف تشرح، بلغة سيتصرّف بناءً عليها مدير المنتج، لماذا المتوسط هو المقياس الخاطئ في نقاش حول الاحتفاظ بالمستخدمين؟

---

## الاستخدام

يندمج `LatencyProfiler` في أي مسار كود يستدعي النموذج. ولخدمة FastAPI، أضِفه على هيئة middleware:

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()
profiler = LatencyProfiler()


@app.post("/chat")
async def chat(request: Request):
    body = await request.json()
    prompt = body["message"]

    async def stream_response():
        import asyncio
        start = asyncio.get_event_loop().time()
        ttft = None
        full_text = []

        # Use the async streaming client in production
        for chunk in stream_with_ttft_sync(prompt):
            if ttft is None:
                ttft = (asyncio.get_event_loop().time() - start) * 1000
            full_text.append(chunk)
            yield chunk

        total = (asyncio.get_event_loop().time() - start) * 1000
        profiler.record(ttft_ms=ttft or total, total_ms=total, feature="chat")

    return StreamingResponse(stream_response(), media_type="text/plain")
```

**ما الذي يضيفه الـ profiler مقارنةً بالتوقيت الخام:**

| النهج | ما تراه | ما يفوتك |
|---|---|---|
| `time.time()` قبل/بعد | إجمالي زمن الاستجابة، كمتوسط | ذيل p95/p99، وTTFT، والتفصيل حسب الميزة |
| `LatencyProfiler` | كل النسب المئوية، وفصل TTFT عن التوليد، وp99 لكل ميزة، وتحليل عنق الزجاجة | (لا شيء، هذه هي الصورة الكاملة) |

> **نقلة في المنظور:** يقول مهندس backend: "لدينا أصلًا زمن الاستجابة في الـ distributed tracing لدينا (Datadog APM). لماذا نبني profiler منفصلًا؟" متى يستحق الـ profiler المخصّص العناء بالتوازي مع أدوات الـ APM العامة، وما الذي يمنحك إياه ولا يمنحه الـ APM؟

---

## التسليم

**المخرَج:** `outputs/skill-latency-profiler.md`

ينتج هذا الدرس صنف `LatencyProfiler` يقيس TTFT وإجمالي زمن الاستجابة بشكل منفصل، ويحسب النسب المئوية، ويحدد عنق الزجاجة في زمن الاستجابة. الـ profiler ذو حالة (يراكم القياسات عبر الاستدعاءات) ومصمّم للعمل داخل العملية (in-process). أما في الأنظمة الموزّعة، فصدّر ملخّصات النسب المئوية إلى منصة الـ observability لديك (Langfuse، أو Datadog، أو OpenTelemetry) على فترات منتظمة.

---

## التقييم

**التحقق 1: الـ TTFT دائمًا أقل من أو يساوي إجمالي زمن الاستجابة**

```python
_, ttft, total = stream_with_ttft("What is 2+2?")
assert ttft <= total, f"TTFT ({ttft}ms) cannot exceed total ({total}ms)"
```

**التحقق 2: النسب المئوية تتزايد بشكل مطّرد**

```python
stats = compute_percentiles([random.uniform(100, 5000) for _ in range(100)])
assert stats.p50_ms <= stats.p95_ms <= stats.p99_ms <= stats.max_ms
```

**التحقق 3: الـ p99 أعلى بشكل ملموس من المتوسط في أحمال العمل الواقعية**

بعد تشغيل أكثر من 50 استدعاءً حقيقيًا، احسب نسبة p99/mean. بالنسبة لنقاط الـ LLM الطرفية، تتراوح هذه النسبة عادةً بين 3 و7 أضعاف. إذا كان p99 لديك يساوي المتوسط، فالأرجح أن بياناتك غير كافية أو أن حمل العمل لديك منتظم على نحو غير معتاد.

**التحقق 4: عزو عنق الزجاجة قابل للتنفيذ**

من أكثر من 50 استدعاءً مُحلَّلًا، ينبغي أن يخبرك تحليل عنق الزجاجة بأحد الأمرين:
- "TTFT dominates"، افحص طول الـ prompt، وزمن الـ prefill، وتوجيه الشبكة
- "Generation dominates"، افحص أعداد توكنات الإخراج، وإعداد `max_tokens`، وفئة النموذج

إذا كانا متساويين، فلديك متّسع متوازن للتحسين على الجانبين. وهذا وضع غير معتاد ويُحسد عليه.
