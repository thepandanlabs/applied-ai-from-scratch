# واجهة أمامية بسيطة بـTypeScript

> البثّ (streaming) من الخادم إلى المتصفّح يتطلب EventSource لا fetch. فـfetch ينتظر الاستجابة كاملة، بينما يعالج EventSource المقاطع (chunks) فور وصولها.

**النوع:** بناء
**اللغات:** كلاهما
**المتطلبات:** 02-wrapping-model-in-fastapi، 03-streaming-sse-async
**الوقت:** ~60 دقيقة
**أهداف التعلّم:**
- بناء واجهة أمامية بـTypeScript + HTML خالصة دون أي إطار عمل (framework)
- استدعاء نقطة `/generate` في FastAPI باستخدام Fetch API
- استهلاك نقطة `/stream` SSE في FastAPI باستخدام EventSource
- عرض الـtokens المبثوثة في الـDOM فور وصولها
- تقديم الواجهة الأمامية من `http.server` في Python أو من ملفات FastAPI الثابتة

---

## الشعار

**المتصفّح يعرف كيف يبثّ مسبقًا. كل ما عليك أن تعطيه الواجهة الصحيحة: EventSource لا fetch.**

---

## المشكلة

بنيت خدمة FastAPI تغلّف Claude. تعمل بشكل مثالي في `curl`. والآن تريد واجهة مستخدم. تتجه إلى React وVite ومكتبة مكوّنات وراوتر ومدير حالة. وبعد أربع ساعات تجد نفسك تعدّ المُجمِّع (bundler) دون أن تكتب سطرًا واحدًا من شيفرة المنتج.

المتطلب الحقيقي أبسط: مربّع نص، وزرّ إرسال، ومنطقة تمتلئ بالنص. لأداة داخلية أو عرض توضيحي (demo)، تكفي TypeScript خالصة مُجمَّعة بـ`tsc`. لا إطار عمل، ولا خطّ بناء (build pipeline) أبعد من `tsc`، ولا مجلد `node_modules` فيه 400 حزمة.

ثمة مشكلة واحدة غير بديهية: البثّ (streaming). حين تستخدم `fetch()` لطلب POST، ينتظر المتصفّح الاستجابة كاملة قبل أن يسلّمها إلى JavaScript. وهذا جيد لنقطة `/generate` المتزامنة. لكن لنقطة `/stream` المبثوثة، تريد أن تظهر الـtokens في الواجهة فور وصولها، كما يعرض ChatGPT المخرجات. ولذلك تحتاج `EventSource`، وهي واجهة المتصفّح المدمجة لأحداث الخادم المرسَلة (Server-Sent Events).

يتعلّم معظم المطوّرين هذا بالطريقة الصعبة: يربطون `fetch` بنقطة البثّ، ثم يحتارون لماذا لا يظهر شيء حتى تكتمل الاستجابة. الحلّ هو استبدال واجهة واحدة.

---

## المفهوم

### سلسلة الاستدعاء بين المتصفّح وFastAPI وAnthropic

```
SYNC PATH (fetch -> /generate)
                                                         
  Browser          FastAPI             Anthropic API     
    |                  |                    |            
    |--fetch POST------>|                    |            
    |                  |--messages.create-->|            
    |                  |   (waits)          |            
    |                  |<--full response----|            
    |<--JSON response---|                    |            
    |  (entire text     |                    |            
    |   in one chunk)   |                    |            
                                                         
  DOM: set innerHTML once when fetch resolves            


STREAMING PATH (EventSource -> /stream)
                                                         
  Browser          FastAPI             Anthropic API     
    |                  |                    |            
    |--EventSource----->|                    |            
    |  (GET /stream?q=.)|                    |            
    |                  |--stream.create---->|            
    |<--data: token1----|<--chunk1---------- |            
    |  append to DOM    |                    |            
    |<--data: token2----|<--chunk2---------- |            
    |  append to DOM    |                    |            
    |<--data: [DONE]----|<--stream end------ |            
    |  stop listening   |                    |            
                                                         
  DOM: append each token as it arrives                   
```

### لماذا EventSource لا fetch؟

`fetch` هو طلب-استجابة: يجمع جسم الاستجابة كاملًا قبل أن يحلّ الوعد (Promise). لا يمكنك الحصول على بيانات جزئية من استدعاء `fetch` حتى يغلق الخادم الاتصال.

`EventSource` اتصال دائم يعالج أسطر `data:` فور وصولها. صُمِّم تحديدًا لأحداث الخادم المرسَلة (Server-Sent Events). ويتولى المتصفّح إعادة الاتصال وتحليل الأحداث والتخزين المؤقت (buffering) تلقائيًا.

| | `fetch` | `EventSource` |
|---|---|---|
| البروتوكول | HTTP طلب-استجابة | HTTP اتصال دائم |
| البيانات الجزئية | لا (ينتظر الإغلاق) | نعم (كل سطر `data:` يطلق حدثًا) |
| إعادة الاتصال | يدوية | تلقائية |
| الطريقة (Method) | POST أو GET | GET فقط |
| الأنسب لـ | `/generate` (استجابة JSON كاملة) | `/stream` (SSE توكنًا بتوكن) |

ملاحظة: `EventSource` يدعم طلبات GET فقط. إن كانت نقطة البثّ لديك تتطلب POST (مثلًا لجسم طلب طويل)، فاستخدم بدلًا منها واجهة `fetch` Streams (`response.body.getReader()`).

---

## البناء

### الخطوة 1: بنية المشروع

```
phases/06-shipping/10-minimal-typescript-frontend/code/
├── index.html      # HTML shell, imports compiled client.js
├── client.ts       # TypeScript source
├── client.js       # compiled output (tsc produces this)
└── tsconfig.json   # minimal TS config
```

لا `package.json`. لا `node_modules`. مجرد `tsc` للتجميع.

### الخطوة 2: هيكل HTML

```html
<!-- code/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Frontend</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
    textarea { width: 100%; height: 80px; font-size: 1rem; padding: 0.5rem; box-sizing: border-box; }
    .btn-row { display: flex; gap: 0.5rem; margin: 0.5rem 0; }
    button { padding: 0.5rem 1rem; font-size: 1rem; cursor: pointer; }
    #output {
      white-space: pre-wrap;
      background: #f5f5f5;
      border-radius: 4px;
      padding: 1rem;
      min-height: 120px;
      margin-top: 1rem;
    }
    #error { color: #c00; margin-top: 0.5rem; font-size: 0.9rem; }
    .loading { opacity: 0.5; }
  </style>
</head>
<body>
  <h1>AI Frontend</h1>
  <textarea id="prompt" placeholder="Enter your prompt here..."></textarea>
  <div class="btn-row">
    <button id="btn-generate">Generate (sync)</button>
    <button id="btn-stream">Stream (SSE)</button>
    <button id="btn-clear">Clear</button>
  </div>
  <div id="error"></div>
  <div id="output">Output will appear here.</div>

  <!-- Import compiled TypeScript -->
  <script src="client.js"></script>
</body>
</html>
```

### الخطوة 3: عميل TypeScript

```typescript
// code/client.ts

const API_BASE = "http://localhost:8000";

// DOM references
const promptEl = document.getElementById("prompt") as HTMLTextAreaElement;
const outputEl = document.getElementById("output") as HTMLDivElement;
const errorEl = document.getElementById("error") as HTMLDivElement;
const btnGenerate = document.getElementById("btn-generate") as HTMLButtonElement;
const btnStream = document.getElementById("btn-stream") as HTMLButtonElement;
const btnClear = document.getElementById("btn-clear") as HTMLButtonElement;

// --- Utilities ---

function setError(msg: string): void {
  errorEl.textContent = msg;
}

function clearError(): void {
  errorEl.textContent = "";
}

function setOutput(text: string): void {
  outputEl.textContent = text;
}

function appendOutput(text: string): void {
  outputEl.textContent += text;
}

function setLoading(loading: boolean): void {
  outputEl.classList.toggle("loading", loading);
  btnGenerate.disabled = loading;
  btnStream.disabled = loading;
}

// --- Sync Generate (fetch) ---

async function handleGenerate(): Promise<void> {
  const prompt = promptEl.value.trim();
  if (!prompt) {
    setError("Enter a prompt first.");
    return;
  }
  clearError();
  setOutput("");
  setLoading(true);

  try {
    const response = await fetch(`${API_BASE}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`HTTP ${response.status}: ${detail}`);
    }

    const data = await response.json() as { text: string };
    setOutput(data.text);
  } catch (err: unknown) {
    setError(err instanceof Error ? err.message : String(err));
  } finally {
    setLoading(false);
  }
}

// --- Streaming Generate (EventSource) ---

function handleStream(): void {
  const prompt = promptEl.value.trim();
  if (!prompt) {
    setError("Enter a prompt first.");
    return;
  }
  clearError();
  setOutput("");
  setLoading(true);

  // EventSource only supports GET. Pass prompt as query parameter.
  const url = `${API_BASE}/stream?prompt=${encodeURIComponent(prompt)}`;
  const source = new EventSource(url);

  source.onmessage = (event: MessageEvent) => {
    const data = event.data as string;
    if (data === "[DONE]") {
      source.close();
      setLoading(false);
      return;
    }
    appendOutput(data);
  };

  source.onerror = (_event: Event) => {
    source.close();
    setLoading(false);
    setError("Stream error. Check server is running at " + API_BASE);
  };
}

// --- Event listeners ---

btnGenerate.addEventListener("click", () => { void handleGenerate(); });
btnStream.addEventListener("click", handleStream);
btnClear.addEventListener("click", () => {
  setOutput("");
  clearError();
  promptEl.value = "";
});
```

> **اختبار من الواقع:** لماذا يتطلب `EventSource` طلب GET؟ تستخدم مواصفة SSE في المتصفّح اتصال GET دائمًا. يستجيب الخادم بـ`Content-Type: text/event-stream` ويبقي الاتصال مفتوحًا، مرسلًا أسطر `data:`. لا تدعم واجهة `EventSource` الأصلية طلب POST. لنقاط البثّ التي تحتاج POST (موجّهات طويلة، جسم منظّم)، استخدم `fetch` مع `response.body.getReader()` واقرأ الجسم كبثّ يدويًا.

### الخطوة 4: tsconfig والتجميع

```json
// code/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM"],
    "strict": true,
    "outDir": ".",
    "rootDir": ".",
    "module": "None",
    "noEmit": false
  },
  "include": ["client.ts"]
}
```

جمّع بـ:
```bash
tsc --project code/tsconfig.json
# Produces code/client.js
```

---

## الاستخدام

### الخيار أ: Python http.server (دون أي تغيير في FastAPI)

```bash
# From the code/ directory
python -m http.server 3000
# Open http://localhost:3000/index.html
```

هذا يقدّم الملفات الثابتة. يستدعي عميل TypeScript خدمة FastAPI على `http://localhost:8000`. تحتاج إلى تفعيل CORS في تطبيق FastAPI لديك (راجع الدرس 02 من المرحلة 06).

### الخيار ب: تركيب ملفات FastAPI الثابتة

```python
# Add to your FastAPI app (main.py)
from fastapi.staticfiles import StaticFiles

# Mount after all API routes to avoid shadowing them
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="ui")
# Access at http://localhost:8000/ui/
```

انسخ `index.html` و`client.js` إلى مجلد `frontend/` بجوار `main.py`.

```python
# FastAPI /generate endpoint expected by the client
from pydantic import BaseModel

class GenerateRequest(BaseModel):
    prompt: str

@app.post("/generate")
async def generate(request: GenerateRequest) -> dict[str, str]:
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": request.prompt}],
    )
    return {"text": message.content[0].text}

# FastAPI /stream endpoint expected by the client
from fastapi.responses import StreamingResponse
import anthropic

@app.get("/stream")
async def stream(prompt: str) -> StreamingResponse:
    def generate_stream():
        with client.messages.stream(
            model="claude-3-5-haiku-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {text}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
```

> **نقلة في المنظور:** هذه الواجهة الأمامية بأكملها 60 سطرًا من TypeScript و40 سطرًا من HTML. لنموذج أولي أو أداة داخلية أو عرض توضيحي، هذا كل ما تحتاجه. قيمة TypeScript الخالصة أن كل سطر مرئي وقابل لتصحيح الأخطاء (debug) في تبويب Network ضمن أدوات المطوّر بالمتصفّح. حين يتعطل البثّ، تفتح فاحص Network، وتنقر على طلب `/stream`، وتشاهد أسطر `data:` تظهر آنيًا. ومع إطار عمل يغلّف fetch وEventSource، تتطلب خطوة التصحيح ذاتها معرفة أيّ تجريد (abstraction) ابتلع الخطأ.

---

## التسليم

المنتَج القابل لإعادة الاستخدام هو `outputs/skill-ai-frontend-template.md`. يحتوي على:
- `index.html` و`client.ts` كاملين كقوالب جاهزة للنسخ واللصق
- نقطتا `/generate` و`/stream` في FastAPI اللتان يتوقعهما
- ملاحظات حول CORS وخيارات التقديم

---

## التقييم

**الاختبار 1: التجميع نظيف.** شغّل `tsc --project code/tsconfig.json --noEmit`. تحقّق من عدم وجود أي أخطاء.

**الاختبار 2: التوليد المتزامن.** شغّل خلفية FastAPI. افتح `index.html` في متصفّح، اكتب موجّهًا (prompt)، وانقر "Generate (sync)". تحقّق من امتلاء عنصر المخرجات بالاستجابة كاملة بعد تأخير قصير.

**الاختبار 3: البثّ.** انقر "Stream (SSE)". افتح تبويب Network في أدوات المطوّر، انقر على طلب `/stream`، وراقب لوحة EventStream. تحقّق من ظهور الـtokens واحدًا تلو الآخر. تحقّق من تحديث الـDOM آنيًا.

**الاختبار 4: عرض الخطأ.** أوقف خادم FastAPI. انقر "Generate". تحقّق من أن عنصر `#error` يعرض رسالة خطأ ذات معنى، لا شاشة فارغة ولا استثناءً غير ملتقَط.

**الاختبار 5: علامة [DONE].** تحقّق من أنه بعد انتهاء البثّ، تُمسح حالة التحميل (إعادة تفعيل الأزرار، إزالة صنف loading) ولا يظهر أي محتوى إضافي بعد الـtoken الأخير.

**الاختبار 6: CORS.** إن كنت تقدّم HTML من المنفذ 3000 والـAPI على المنفذ 8000، تحقّق من أن المتصفّح لا يُظهر أخطاء CORS في الـconsole. إن أظهرها، أضف `CORSMiddleware` إلى FastAPI مع `allow_origins=["http://localhost:3000"]`.
