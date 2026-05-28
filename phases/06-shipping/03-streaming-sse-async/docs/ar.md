# الاستجابات المتدفّقة (Streaming): SSE والـ Async والتزامن

> يشعر المستخدمون بالسرعة عند الرمز (token) الأول، لا الأخير.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** الدرس 06-02 (خدمة FastAPI)، إلمام بـ async/await في Python
**الوقت:** ~60 دقيقة
**أهداف التعلّم:**
- شرح لماذا يحسّن streaming الأداء المُدرَك (perceived performance) لاستجابات LLM
- تنفيذ نقطة نهاية `/stream` باستخدام StreamingResponse في FastAPI ومولّدات async (async generators)
- تنسيق أحداث Server-Sent Events (SSE) بشكل صحيح كي تستهلكها المتصفّحات وcurl
- فهم كيف تعالج FastAPI طلبات streaming المتزامنة المتعدّدة بـ asyncio
- اختبار نقطة نهاية streaming بـ curl وصفحة HTML بسيطة

---

## المشكلة

نقطة نهاية `/generate` لديك تعمل لكن المستخدمين غير راضين. استجابة Claude نموذجية تستغرق 8-12 ثانية لتكتمل. ينقر المستخدم الزر، فلا يرى شيئًا لعشر ثوانٍ، ثم تظهر الاستجابة بكاملها دفعةً واحدة. يظنّ أن الصفحة معطّلة. والكثير يغادر قبل وصول الاستجابة.

النموذج ليس بطيئًا، فهو ينتج الرموز باستمرار من المليّ ثانية الأولى. المشكلة أنك تخزّنها كلها في مخزن مؤقّت (buffer) قبل إرسال أي شيء. الحل هو streaming: أرسِل كل رمز إلى العميل بمجرّد أن ينتجه النموذج. يرى المستخدم الكلمة الأولى في أقل من ثانية ويشاهد الاستجابة تُبنى في الوقت الفعلي.

كما يحلّ streaming مشكلة المهلة (timeout). طلب HTTP يستغرق 10 ثوانٍ يقترب من كثير من القيم الافتراضية لمهلة موازنات الأحمال والعملاء. الاستجابة المتدفّقة تُبقي الاتصال حيًّا بإرسال البيانات باستمرار.

---

## المفهوم

### الاستجابة المخزّنة مقابل المتدفّقة

```
BUFFERED (current behavior):
User clicks        API call starts        Model finishes      User sees output
    |                    |                     |                    |
    |<---- 10 seconds ----------------------------------->|
    |                                          buffer fills -> response sent


STREAMING (what we want):
User clicks   API call starts   Token 1   Token 2   ...   Done
    |               |              |         |              |
    |               |<-- ~0.3s -->|<~0.05s>|<~0.05s>...   |
    |                             user sees first word      |
    |<--- 0.3s to first content --------- 10s total ------>|
```

الزمن الإجمالي هو نفسه. أما الزمن المُدرَك حتى أول محتوى فيهبط من 10 ثوانٍ إلى أقل من ثانية.

### صيغة Server-Sent Events

SSE بروتوكول HTTP أحادي الاتجاه يدفع فيه الخادم البيانات إلى العميل. كل حدث نصّ يفصله `\n\n`:

```
data: {"token": "Hello"}\n\n
data: {"token": " world"}\n\n
data: {"token": "!"}\n\n
data: [DONE]\n\n
```

القواعد:
- يبدأ كل حدث بـ `data: `
- ينتهي كل حدث بـ `\n\n` بالضبط (سطران جديدان، لا واحد)
- `[DONE]` هي القيمة الحارسة (sentinel) المتعارَف عليها للإشارة إلى نهاية التدفّق
- يجب أن تكون ترويسة `Content-Type` هي `text/event-stream`
- يجب أن تكون ترويسة `Cache-Control` هي `no-cache`

### SSE مقابل WebSocket

```
+--------------------+------------------+-------------------------+
| Feature            | SSE              | WebSocket               |
+--------------------+------------------+-------------------------+
| Direction          | Server to client | Bidirectional           |
| Protocol           | Plain HTTP       | WebSocket upgrade       |
| Reconnect          | Built-in         | Manual                  |
| Browser support    | All modern       | All modern              |
| Load balancer      | Works natively   | Requires upgrade config |
| Right choice for   | Model streaming  | Live chat, games        |
+--------------------+------------------+-------------------------+
```

تدفّق مخرجات النموذج أحادي الاتجاه. وSSE هو الخيار الصحيح. أما WebSockets فتضيف تعقيد ثنائية الاتجاه التي لا تحتاجها.

### التزامن مع asyncio في streaming

```
Event Loop (single thread)

Request A: stream start
    |-- await client.messages.stream()  <-- suspends, loop runs other tasks
    |
Request B arrives during A's await:
    |-- Request B handler starts immediately
    |-- await client.messages.stream()  <-- suspends
    |
Event Loop schedules both:
    A: receives token, sends SSE event, suspends again
    B: receives token, sends SSE event, suspends again
    A: next token...
    B: next token...
```

`async def` و`await` يسمحان لحلقة الأحداث (event loop) بخدمة عدة استجابات streaming متزامنة من خيط واحد. لا خيوط، لا أقفال (locks)، ولا مشكلات حالة مشتركة.

---

## البناء

### الخطوة 1: عميل Anthropic غير المتزامن (Async)

يتطلّب streaming عميل Anthropic غير المتزامن. فالعميل المتزامن (sync) من الدرس 02 يحجب حلقة الأحداث.

```python
from anthropic import AsyncAnthropic
import os

# In the lifespan event:
app.state.client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
```

### الخطوة 2: مولّد async

المولّد هو قلب SSE. يولّد حدث SSE منسّقًا واحدًا لكل رمز.

```python
import json
from anthropic import AsyncAnthropic

async def stream_tokens(
    client: AsyncAnthropic,
    model: str,
    prompt: str,
    system: str | None = None,
    max_tokens: int = 1024,
):
    """
    Async generator that yields SSE-formatted events for each token.

    Each yield produces a string like:
        data: {"token": "Hello"}\n\n

    A final [DONE] event signals end of stream.
    """
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    try:
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                # Format as SSE event: "data: {json}\n\n"
                event_data = json.dumps({"token": text})
                yield f"data: {event_data}\n\n"

            # Send final event with usage stats
            final = await stream.get_final_message()
            done_data = json.dumps({
                "done": True,
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
            })
            yield f"data: {done_data}\n\n"

    except Exception as e:
        # Yield an error event so the client knows something went wrong
        error_data = json.dumps({"error": str(e)})
        yield f"data: {error_data}\n\n"
```

مدير السياق `async with client.messages.stream()` يتولّى دورة حياة الاتصال. و`stream.text_stream` مكرِّر async يولّد كل رمز نصّي حين يصل.

### الخطوة 3: نقطة نهاية StreamingResponse

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

class StreamRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    max_tokens: int = Field(default=1024, ge=1, le=4096)
    system: str | None = None

@app.post("/stream")
async def stream_endpoint(req: Request, body: StreamRequest):
    """
    Stream model output as Server-Sent Events.
    The response body is a continuous stream of text/event-stream data.
    """
    client = req.app.state.client
    model = req.app.state.model

    return StreamingResponse(
        stream_tokens(
            client=client,
            model=model,
            prompt=body.prompt,
            system=body.system,
            max_tokens=body.max_tokens,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables nginx buffering if deployed behind nginx
        },
    )
```

يقبل `StreamingResponse` مولّد async ويدفق مخرجاته إلى العميل مع تنفيذ كل `yield`.

> **اختبار من الواقع:** يسألك مهندس الواجهة الأمامية: "لماذا نحتاج الحارس `[DONE]` في النهاية؟ ألا تستطيع الواجهة الأمامية ببساطة أن تعرف أن التدفّق انتهى حين يُغلق الاتصال؟" كيف تشرح وضع الفشل الذي يسقط فيه الاتصال في منتصف التدفّق مقابل تدفّق يكتمل بنظافة؟

---

## الاستخدام

### تشغيل الخدمة

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --reload --port 8000
```

### الاختبار بـ curl

```bash
# Stream a response -- the --no-buffer flag shows each event as it arrives
curl -X POST http://localhost:8000/stream \
  --no-buffer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Count from 1 to 10, one number per line."}'
```

المخرجات المتوقعة (تصل الرموز واحدًا تلو الآخر):
```
data: {"token": "1"}

data: {"token": "\n2"}

data: {"token": "\n3"}

...

data: {"done": true, "input_tokens": 15, "output_tokens": 24}
```

### الاختبار عبر متصفّح (HTML بسيط)

```html
<!DOCTYPE html>
<html>
<body>
<button onclick="startStream()">Generate</button>
<div id="output"></div>
<script>
async function startStream() {
    const output = document.getElementById('output');
    output.textContent = '';

    const response = await fetch('/stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt: 'Tell me a short story about a robot.'})
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const {done, value} = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n\n').filter(l => l.startsWith('data: '));

        for (const line of lines) {
            const data = JSON.parse(line.slice(6));  // remove "data: "
            if (data.token) output.textContent += data.token;
            if (data.done) console.log('Stream complete:', data);
        }
    }
}
</script>
</body>
</html>
```

### الـ streaming المتزامن

شغّل الخادم وافتح نافذتي طرفية:

```bash
# Terminal 1
curl -X POST http://localhost:8000/stream --no-buffer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a 200-word essay on astronomy."}'

# Terminal 2 (at the same time)
curl -X POST http://localhost:8000/stream --no-buffer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Write a 200-word essay on biology."}'
```

يعمل التدفّقان معًا بشكل متزامن من عامل uvicorn واحد. تشابك حلقة الأحداث بينهما دون خيوط أو حجب.

> **نقلة في المنظور:** يقترح زميل استخدام WebSockets بدل SSE لأن "WebSockets أحدث وأقوى." وبما أنك تعلم أن حالتك الحالية هي تدفّق أحادي الاتجاه لمخرجات النموذج، كيف تقيّم هذا الاقتراح؟ ما الذي يجب أن يكون صحيحًا بشأن متطلباتك كي تصبح WebSockets الخيار الأفضل؟

---

## التسليم

المخرَج القابل لإعادة الاستخدام لهذا الدرس هو `outputs/skill-streaming-sse.md`. يحوي نمط streaming بـ SSE كمقطع كود قائم بذاته فيه مولّد async، ومسار FastAPI، وعميل HTML، جاهز للإدراج في أي خدمة FastAPI.

---

## التقييم

**التحقق 1: الزمن حتى أول رمز.**
استخدم curl مع `--no-buffer` وقِس بصريًا. ينبغي أن ترى أول رمز في الطرفية في أقل من ثانية واحدة. إذا لم ترَ شيئًا لعدّة ثوانٍ ثم ظهرت الاستجابة كلها دفعةً واحدة، فالاستجابة تُخزّن في مكان ما (nginx، أو وسيط (proxy)، أو أن المولّد لا يولّد تدريجيًا).

**التحقق 2: التدفّقات المتزامنة لا يحجب بعضها بعضًا.**
افتح طرفيتين. ابدأ تدفّقًا طويلًا في الطرفية 1 (اطلب مقالًا من 500 كلمة). ابدأ فورًا تدفّقًا في الطرفية 2. ينبغي أن تُظهر كلتا الطرفيتين رموزًا تصل بشكل متشابك. إذا انتظرت الطرفية 2 حتى تنتهي الطرفية 1، فالمعالجات تحجب (دالة متزامنة بدل async، أو عميل sync بدل AsyncAnthropic).

**التحقق 3: صيغة SSE صحيحة.**
وجّه مخرجات التدفّق إلى ملف وافحصها. يجب أن يبدأ كل سطر حدث بـ `data: ` وينتهي بـ `\n\n`. أي انحراف سيكسر EventSource في المتصفّح. تحقّق بـ: `curl ... | cat -A | grep -v "^data:" `، ينبغي ألّا توجد أسطر غير فارغة.

**التحقق 4: أحداث الخطأ منسّقة بشكل صحيح.**
أطلِق خطأً بتمرير مفتاح API غير صالح. تأكّد من أن تدفّق الاستجابة يحوي حدث `data: {"error": "..."}` يتبعه إغلاق التدفّق بنظافة. لا ينبغي أن يتعلّق الاتصال.

**التحقق 5: وصول حدث Done.**
بعد تدفّق كامل، تأكّد من أن السطر الأخير في المخرجات هو `data: {"done": true, ...}`. إذا لم يستطع العميل اكتشاف اكتمال التدفّق بنظافة، فلن يستطيع التمييز بين "انتهى التدفّق" و"سقط الاتصال في منتصف التدفّق".
