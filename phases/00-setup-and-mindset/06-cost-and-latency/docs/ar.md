# التكلفة وزمن الاستجابة منذ السطر الأول

> إذا لم تستطع قياسه، فلا يمكنك تحمّل تكلفة إطلاقه.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** الدرس 03 (أول طلب API)، الدرس 05 (قراءة وثائق النماذج)
**الوقت:** ~45 دقيقة
**المرحلة:** 00 - الإعداد والعقلية

---

## أهداف التعلّم

- حساب التكلفة الدقيقة لأي طلب API انطلاقًا من كائن usage في الردّ
- التمييز بين زمن الاستجابة الكلي (wall-clock latency) وزمن أول token‏ (TTFT)، ومعرفة أيّهما يهم لأي نمط من تجربة المستخدم (UX)
- بناء صنف (class) باسم `CostTracker` يسجّل زمن الاستجابة، وأعداد tokens، وإجماليات التكلفة التراكمية
- تحديد مكوّنات زمن الاستجابة التي تتحكم بها وتلك التي لا تتحكم بها
- شرح لماذا تكلّف tokens الإخراج أكثر من tokens الإدخال، وماذا يعني ذلك لتصميم الـ prompt

---

## المشكلة

تُطلق أول ميزة ذكاء اصطناعي لك. تعمل. تبدو التكاليف معقولة أثناء الاختبار - كل طلب يكلّف بضعة سنتات. بعد ثلاثة أسابيع، صار الفريق يستخدمها بكثافة، وفاتورة API لديك صارت 800 دولار للشهر بدلًا من الـ 80 دولارًا التي خطّطت لها. تحقّق فتكتشف أن قالب prompt كتبته يبدأ كل ردّ بـ "Of course! I'd be happy to help you with that. Here's what I found:". تلك المقدّمة هي 20 token إخراج لكل طلب. عند 50,000 طلب في الشهر، يصبح ذلك مليون token إخراج - أي 4 دولارات تكلفة إضافية كل شهر مقابل التحية فقط. وبضربها عبر 10 قوالب prompt، تكون قد اشتريت بلا قصد ما قيمته 40 دولارًا شهريًا من النصوص الحشوية.

في الوقت نفسه، ميزة موجَّهة للمستخدم بدت "سريعة بما يكفي" أثناء الاختبار تتلقّى الآن شكاوى في الإنتاج. تقيسها: زمن الاستجابة الوسيط 4.2 ثانية. المستخدمون يتخلّون عن روبوتات المحادثة بعد نحو 3 ثوانٍ. لكن لا توجد لديك سجلّات تبيّن ما إذا كانت الـ 4.2 ثانية ناتجة عن عبء الشبكة، أو TTFT، أو زمن التوليد. بدون هذا التفصيل، لا يمكنك إصلاحه.

كلا المشكلتين لهما السبب الجذري نفسه: لم تُجهّز قياس التكلفة وزمن الاستجابة منذ السطر الأول. هذه ليست شؤونًا خاصة بالعمليات (ops) تضيفها لاحقًا. إنها قيود هندسية تقيسها منذ أول طلب.

---

## المفهوم

### من أين يأتي زمن الاستجابة

```
Your Code                  Anthropic API
    |                           |
    |---[1. Network: ~30ms]---->|
    |                           |--[2. Queue: 0ms-2000ms]
    |                           |--[3. TTFT: 200ms-800ms]
    |<--[first token]-----------|
    |                           |--[4. Generation: 50ms per 100 tokens]
    |<--[last token]------------|
    |---[5. Your processing]--->
    |
    v
 Wall-clock latency = 1 + 2 + 3 + 4 + 5
```

**ما الذي تتحكم به:**
- حجم الطلب (عدد أقل من tokens الإدخال = معالجة أقل)
- طول الإخراج (عدد أقل من tokens المطلوبة = توليد أقل)
- اختيار النموذج (النماذج الأصغر لها TTFT أدنى وتوليد أسرع)
- البث المباشر (streaming) (يعرض أول token للمستخدم أبكر، حتى لو كان الزمن الإجمالي نفسه)
- كود المعالجة لديك (الخطوة 5)

**ما الذي لا تتحكم به:**
- زمن استجابة الشبكة (الموقع الجغرافي، بنية المزوّد التحتية)
- زمن الانتظار في الطابور (عندما يكون API الخاص بـ Anthropic تحت ضغط)
- TTFT (أمر جوهري في طريقة عمل استدلال الـ transformer)

```mermaid
flowchart LR
    A[Your App] -->|request| B[Network]
    B -->|50-100ms| C[API Queue]
    C -->|0-2000ms| D[Model Load\nTTFT]
    D -->|200-800ms| E[Token Generation\n~50ms per 100 tokens]
    E -->|stream or batch| F[Your App]
    
    style C fill:#f5a623,color:#000
    style D fill:#f5a623,color:#000
```

### عدم تماثل tokens الإخراج

```
                  INPUT TOKENS          OUTPUT TOKENS
Cost:             $0.80 / 1M            $4.00 / 1M
Speed:            parallel              sequential (one at a time)
Control:          you write the prompt  you can cap with max_tokens
Ratio:            5x cheaper            5x more expensive

Example prompt:
  Input:  "Summarize this 500-word article in 3 bullet points"
          = ~20 tokens
  Output: "Sure! Here are 3 bullet points:\n• ..." + actual bullets
          = ~150 tokens

  The preamble ("Sure! Here are 3 bullet points:") = ~10 tokens
  Cost of that preamble = 10 * ($4.00 / 1,000,000) = $0.00004 per call
  At 100,000 calls/month = $4.00/month wasted on filler text

  Fix: instruct the model to skip the preamble. "Respond with the 3
  bullet points only. No introduction." Saves output tokens,
  reduces latency, improves UX.
```

---

## البناء

### الخطوة 1: صنف CostTracker

```python
# code/main.py
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic

MODEL = "claude-3-5-haiku-20241022"
PRICING = {
    "input_per_million": 0.80,
    "output_per_million": 4.00,
    "cache_read_per_million": 0.08,
}


@dataclass
class RequestRecord:
    """A single recorded API request with timing and cost data."""
    prompt_preview: str           # first 80 chars of the prompt
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    cache_cost_usd: float
    total_cost_usd: float
    wall_clock_seconds: float     # total request duration
    ttft_seconds: float | None    # time to first token (streaming only)


@dataclass
class CostTracker:
    """
    Wraps the Anthropic client to record cost and latency for every call.

    Usage:
        tracker = CostTracker()
        response, record = tracker.call(messages=[...])
        print(tracker.summary())
    """
    records: list[RequestRecord] = field(default_factory=list)
    _client: anthropic.Anthropic = field(default_factory=anthropic.Anthropic)

    def _compute_cost(self, usage: Any) -> tuple[float, float, float]:
        """Return (input_cost, output_cost, cache_cost) in USD."""
        input_tokens = getattr(usage, "input_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0)
        cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0

        # Fresh input = total input minus what came from cache
        fresh_input = max(0, input_tokens - cache_read_tokens)

        input_cost = (fresh_input / 1_000_000) * PRICING["input_per_million"]
        output_cost = (output_tokens / 1_000_000) * PRICING["output_per_million"]
        cache_cost = (cache_read_tokens / 1_000_000) * PRICING["cache_read_per_million"]

        return input_cost, output_cost, cache_cost
```

### الخطوة 2: مكالمة API المُتتبَّعة

```python
    def call(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
        model: str = MODEL,
    ) -> tuple[anthropic.types.Message, RequestRecord]:
        """
        Make an API call and record cost + latency.
        Returns (response, record) so you can use the response normally.
        """
        prompt_preview = str(messages[0].get("content", ""))[:80]

        start = time.perf_counter()

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)

        elapsed = time.perf_counter() - start

        usage = response.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        input_cost, output_cost, cache_cost = self._compute_cost(usage)
        total_cost = input_cost + output_cost + cache_cost

        record = RequestRecord(
            prompt_preview=prompt_preview,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            cache_cost_usd=cache_cost,
            total_cost_usd=total_cost,
            wall_clock_seconds=elapsed,
            ttft_seconds=None,  # not available in non-streaming mode
        )
        self.records.append(record)

        return response, record
```

### الخطوة 3: البث المباشر مع قياس TTFT

```python
    def call_streaming(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 1024,
        model: str = MODEL,
    ) -> tuple[str, RequestRecord]:
        """
        Streaming call that measures time-to-first-token (TTFT).
        Returns (full_text, record).
        """
        prompt_preview = str(messages[0].get("content", ""))[:80]

        start = time.perf_counter()
        ttft = None
        text_parts = []
        final_usage = None

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                if ttft is None:
                    ttft = time.perf_counter() - start
                text_parts.append(text)
            final_message = stream.get_final_message()
            final_usage = final_message.usage

        elapsed = time.perf_counter() - start
        full_text = "".join(text_parts)

        input_tokens = final_usage.input_tokens
        output_tokens = final_usage.output_tokens
        cache_read = getattr(final_usage, "cache_read_input_tokens", 0) or 0

        input_cost, output_cost, cache_cost = self._compute_cost(final_usage)
        total_cost = input_cost + output_cost + cache_cost

        record = RequestRecord(
            prompt_preview=prompt_preview,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            input_cost_usd=input_cost,
            output_cost_usd=output_cost,
            cache_cost_usd=cache_cost,
            total_cost_usd=total_cost,
            wall_clock_seconds=elapsed,
            ttft_seconds=ttft,
        )
        self.records.append(record)

        return full_text, record
```

### الخطوة 4: تقرير الملخّص

```python
    def summary(self) -> str:
        """Return a formatted cost and latency summary."""
        if not self.records:
            return "No requests recorded."

        total_cost = sum(r.total_cost_usd for r in self.records)
        total_input = sum(r.input_tokens for r in self.records)
        total_output = sum(r.output_tokens for r in self.records)
        avg_latency = sum(r.wall_clock_seconds for r in self.records) / len(self.records)

        ttft_records = [r for r in self.records if r.ttft_seconds is not None]
        avg_ttft = (
            sum(r.ttft_seconds for r in ttft_records) / len(ttft_records)
            if ttft_records else None
        )

        lines = [
            f"{'='*55}",
            f"  Cost and Latency Summary ({len(self.records)} requests)",
            f"{'='*55}",
            f"  Total cost       : ${total_cost:.6f}",
            f"  Total input tok  : {total_input:,}",
            f"  Total output tok : {total_output:,}",
            f"  Output/input ratio: {total_output/max(total_input,1):.2f}",
            f"  Avg wall-clock   : {avg_latency:.2f}s",
        ]
        if avg_ttft is not None:
            lines.append(f"  Avg TTFT         : {avg_ttft:.2f}s")

        # Per-request breakdown
        lines.append(f"\n  Per-request breakdown:")
        for i, r in enumerate(self.records, 1):
            ttft_str = f"  ttft={r.ttft_seconds:.2f}s" if r.ttft_seconds else ""
            lines.append(
                f"  [{i}] ${r.total_cost_usd:.6f}  "
                f"in={r.input_tokens} out={r.output_tokens}  "
                f"wall={r.wall_clock_seconds:.2f}s{ttft_str}"
            )
            lines.append(f"      \"{r.prompt_preview}...\"")

        # Monthly projection
        if len(self.records) > 0:
            avg_cost = total_cost / len(self.records)
            lines.append(f"\n  Monthly projections (avg ${avg_cost:.6f}/req):")
            for volume in [1_000, 10_000, 100_000]:
                projected = avg_cost * volume
                lines.append(f"    {volume:>8,} req/month = ${projected:.2f}/month")

        return "\n".join(lines)
```

> **اختبار من الواقع:** يراجع قائد فريقك التقني صنف CostTracker لديك ويقول: "هذه أدوات قياس جميلة، لكن أنظمة الإنتاج ينبغي أن تستخدم منصة رصد (observability) مخصّصة مثل Langfuse أو Datadog، لا صنفًا مصنوعًا منزليًا." إنه محقّ - لكن ما الذي يعلّمك إياه بناء هذا الصنف أولًا ولن تحصل عليه من إدراج SDK طرف ثالث منذ اليوم الأول؟

---

## الاستخدام

كائن `response.usage` هو مصدر الحقيقة بجودة إنتاجية لأعداد tokens. وanthropic SDK يكشفه مباشرة:

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Summarize AI in one sentence."}],
)

# These are your ground truth numbers - always log them.
print(f"Input tokens  : {response.usage.input_tokens}")
print(f"Output tokens : {response.usage.output_tokens}")

# Compute cost inline - no class needed for simple scripts
input_cost = response.usage.input_tokens * 0.80 / 1_000_000
output_cost = response.usage.output_tokens * 4.00 / 1_000_000
print(f"Request cost  : ${input_cost + output_cost:.6f}")

# For streaming, get usage from the final message
with client.messages.stream(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Count to 5."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
    final = stream.get_final_message()
    print(f"\nUsage: {final.usage}")
```

بيانات usage في الـ SDK تتكامل مع Langfuse وBraintrust ومنصات رصد أخرى عبر callbacks أو التسجيل اليدوي. نموذج البيانات هو نفسه دائمًا: tokens الإدخال، tokens الإخراج، وtokens الـ cache الاختيارية.

> **نقلة في المنظور:** يخبرك مؤسّس شركة ناشئة أنه لا يقلق بشأن تكاليف tokens الآن لأن فاتورة API الشهرية لديه ليست سوى 50 دولارًا و"التوسّع مشكلة جيدة أن تواجهها". عند أي نقطة يصبح هذا التأطير خطيرًا، وما النمط المحدّد للتكلفة في تطبيقات الذكاء الاصطناعي الذي يجعل هذا مختلفًا عن توسيع نطاق web API اعتيادي؟

---

## التسليم

المُخرَج في هذا الدرس هو `outputs/skill-cost-latency-tracker.md`: دليل تنفيذ قابل لإعادة الاستخدام لتجهيز قياس التكلفة وزمن الاستجابة في أي تطبيق ذكاء اصطناعي.

شغّل عرض متتبّع التكلفة:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
cd phases/00-setup-and-mindset/06-cost-and-latency
python code/main.py
```

يشغّل السكربت ثلاثة طلبات (قصير، طويل، بث مباشر) ويطبع تفصيلًا كاملًا للتكلفة وزمن الاستجابة مع توقّعات شهرية.

---

## التقييم

**التحقق 1: شغّل المتتبّع على prompts الخاصة بك.**

شغّل `CostTracker` على خمسة prompts تستخدمها فعليًا في عملك. انظر إلى نسبة tokens الإخراج إلى الإدخال. إذا كان لأي prompt نسبة إخراج/إدخال أكبر من 1.0 وكانت المقدّمة المطوّلة ("Sure! Here's what I found:") تساهم في ذلك، فأعد كتابة الـ prompt بتعليمات صريحة لتخطّي المقدّمة. قِس أعداد tokens قبل وبعد.

**التحقق 2: قِس TTFT على طلب بث مباشر.**

استخدم الدالة `call_streaming` وقِس قيمة TTFT. لطلب قصير وبسيط (أقل من 100 token إدخال)، يجب أن يكون TTFT أقل من ثانية واحدة. إذا كان باستمرار أعلى من ثانيتين، فتحقّق مما إذا كنت على نقطة وصول (endpoint) لمنطقة مزدحمة.

**التحقق 3: ابنِ تقدير تكلفتك الشهرية.**

للميزة التي تبنيها، قدّر: متوسط tokens الإدخال لكل طلب، ومتوسط tokens الإخراج لكل طلب، وعدد الطلبات المتوقّع شهريًا. أدخلها في حسابات التوقّع داخل المتتبّع. إذا تجاوزت التكلفة الشهرية ميزانيتك، فحدّد أي مكوّن (الإدخال، أو الإخراج، أو الحجم) هو المحرّك وما هي خياراتك.
