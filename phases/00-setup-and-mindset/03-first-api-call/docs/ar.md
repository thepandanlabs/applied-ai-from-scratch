# أول استدعاء للـ API: الـ Streaming والـ Tokens وكائن الاستجابة

> الاستدعاء بدون streaming يُجمِّد كل شيء. مع الـ streaming تتدفق المخرجات. وفهم ما يخبرك به كائن الاستجابة هو الطريقة التي ستصحّح بها أي ميزة AI ستبنيها في حياتك.

**النوع:** بناء
**اللغات:** كلاهما (Python + TypeScript)
**المتطلبات:** 00-01 (Dev Environment)، 00-02 (API Keys)
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- إجراء استدعاء API بدون streaming وفحص كل حقل في كائن الاستجابة
- إجراء استدعاء API مع streaming وتجميع التدفق بشكل صحيح
- قراءة عدد tokens المدخلات والمخرجات من الاستجابة
- فهم متى تستخدم streaming مقابل عدم استخدامه في بيئة الإنتاج

---

## المشكلة

تربط أول ميزة AI لديك. تعمل بشكل ممتاز في دفتر الاختبار: تستدعي الـ API، تحصل على استجابة، تعرضها. تطلقها للمستخدمين. يشتكي المستخدمون أن الصفحة تتجمد لمدة 4 ثوانٍ، ثم يظهر النص دفعة واحدة. يقترح أحد أعضاء فريقك "فقط أضف مؤشر تحميل (loading spinner)". تضيف المؤشر. لا يزال المستخدمون يشتكون: يرون الاستجابة تبدأ بالتكوّن في أماكن أخرى ويريدون قراءتها أثناء توليدها.

الحل هو الـ streaming. لكن الـ streaming ليس مجرد استبدال جاهز -- عليك تجميع الأجزاء (chunks)، والتعامل مع حدث التوقف، وعدّ الـ tokens بطريقة مختلفة. المشكلة الثانية أنه حتى في الاستدعاءات بدون streaming، ينظر معظم المهندسين إلى النص فقط ويتجاهلون البيانات الوصفية (metadata): عدد الـ tokens، وأسباب التوقف، وإصدار الموديل. هذه الحقول هي حيث تجد شذوذات التكلفة، والاستجابات المبتورة، ومخالفات نافذة السياق (context window) قبل أن تتحول إلى أخطاء في الإنتاج.

يمر هذا الدرس عبر النمطين بالكامل، باستخدام نفس الـ prompt.

---

## المفهوم

### دورة الطلب والاستجابة

```
NON-STREAMING (blocks until complete):

Client                          Anthropic API
  |                                   |
  |--- POST /v1/messages ------------>|
  |                                   | (model generates entire response)
  |                                   | (might take 3-8 seconds for long outputs)
  |<-- 200 OK + full response --------|
  |                                   |
  Display text                        |

STREAMING (tokens arrive as generated):

Client                          Anthropic API
  |                                   |
  |--- POST /v1/messages ------------>|
  |<-- event: message_start ----------|
  |<-- event: content_block_start ----|
  |<-- event: content_block_delta ----|  (token by token)
  |<-- event: content_block_delta ----|  (token by token)
  |<-- event: content_block_delta ----|  (continues...)
  |<-- event: message_delta ----------|  (stop_reason + usage)
  |<-- event: message_stop -----------|
  |                                   |
  Display tokens as they arrive       |
```

### حقول كائن الاستجابة

كل استجابة بدون streaming من Anthropic API تحتوي على هذه الحقول على المستوى الأعلى:

```
Message
  .id             str    "msg_01XYZ..."  (unique per call)
  .type           str    "message"
  .role           str    "assistant"
  .model          str    "claude-3-5-haiku-20241022" (actual model used)
  .content        list   [ContentBlock, ...]
  .stop_reason    str    "end_turn" | "max_tokens" | "stop_sequence" | "tool_use"
  .stop_sequence  str?   None unless a stop_sequence was triggered
  .usage          Usage
      .input_tokens   int  (tokens in the prompt + system prompt)
      .output_tokens  int  (tokens the model generated)
```

حقل `stop_reason` بالغ الأهمية. القيمة `"max_tokens"` تعني أن الموديل وصل إلى الحد الذي وضعته وأن الاستجابة مبتورة -- ارفع `max_tokens` أو قلّص الـ prompt. والقيمة `"end_turn"` هي الاكتمال الطبيعي. تحقّق دائماً من هذا الحقل في كود الإنتاج.

### أحداث الـ Streaming

أثناء الـ streaming، تستقبل سلسلة من الأحداث المُرسَلة من الخادم (server-sent events). يجرّد الـ SDK هذه الأحداث إلى كائن قابل للتكرار (iterable). نوع الـ delta الأساسي هو `text_delta`، الذي يحتوي على حقل `text` يحمل الجزء الجديد:

```
message_start         -> gives you message id and input_tokens
content_block_start   -> marks start of a content block (type="text")
content_block_delta   -> type="text_delta", delta.text = new chunk
message_delta         -> gives you stop_reason and output_tokens
message_stop          -> stream is done
```

---

## البناء

### الخطوة 1: استدعاء بدون streaming

```python
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    messages=[
        {"role": "user", "content": "Explain what a context window is in one sentence."}
    ],
)

# The response object -- inspect every field
print("=== Response Object ===")
print(f"id:           {response.id}")
print(f"model:        {response.model}")
print(f"stop_reason:  {response.stop_reason}")
print(f"stop_sequence:{response.stop_sequence}")
print(f"input_tokens: {response.usage.input_tokens}")
print(f"output_tokens:{response.usage.output_tokens}")
print(f"content type: {response.content[0].type}")
print(f"\nText:\n{response.content[0].text}")
```

حقل `response.model` يخبرك بإصدار الموديل الفعلي المستخدَم -- مفيد عندما يكون لديك عدة موديلات مُهيّأة وتريد التأكد أيّها عالج طلباً معيّناً.

### الخطوة 2: التحقق من سبب التوقف

```python
def safe_text(response: anthropic.types.Message) -> str:
    """
    Extract text from a response, raising if it was truncated.
    In production, you handle max_tokens by increasing the limit
    or splitting the task -- never silently return partial output.
    """
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Response truncated: {response.usage.output_tokens} tokens generated "
            f"but max_tokens was hit. Increase max_tokens or shorten the prompt."
        )
    return response.content[0].text
```

> **اختبار من الواقع:** تستدعي الـ API بقيمة `max_tokens=50` وتحصل على stop_reason قيمته `"max_tokens"`. يرى المستخدم جملة تنتهي في منتصف كلمة. كيف تشرح لمدير منتج غير تقني ماذا حدث، وما هما الخياران المتاحان لإصلاح المشكلة؟

### الخطوة 3: استدعاء مع streaming

```python
print("\n=== Streaming Call ===")

accumulated_text = ""

with client.messages.stream(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    messages=[
        {"role": "user", "content": "Explain what a context window is in one sentence."}
    ],
) as stream:
    for text_chunk in stream.text_stream:
        print(text_chunk, end="", flush=True)
        accumulated_text += text_chunk

print()  # newline after streaming

# After the stream closes, get the final message for metadata
final_message = stream.get_final_message()
print(f"\nStop reason:  {final_message.stop_reason}")
print(f"Input tokens: {final_message.usage.input_tokens}")
print(f"Output tokens:{final_message.usage.output_tokens}")
print(f"Accumulated text length: {len(accumulated_text)} chars")
```

خاصية `stream.text_stream` تُنتِج فقط الـ text deltas، متجاوزةً كل البنية التحتية للأحداث. وهي التجريد الصحيح لمعظم حالات الاستخدام. استخدم `stream.get_final_message()` بعد خروج كتلة `with` للحصول على بيانات الاستخدام وسبب التوقف.

### الخطوة 4: عدّ الـ Tokens بدون استدعاء API

```python
# Count tokens before sending (to avoid context window violations)
token_count = client.messages.count_tokens(
    model="claude-3-5-haiku-20241022",
    messages=[
        {"role": "user", "content": "Explain what a context window is in one sentence."}
    ],
)
print(f"\nToken count (pre-flight): {token_count.input_tokens} tokens")
```

استخدم هذا قبل إرسال prompts كبيرة للتأكد من أنك ضمن حدّ نافذة السياق (context window).

---

## الاستخدام

مدير السياق `client.messages.stream()` هو نمط الإنتاج للـ streaming. هذا هو المكافئ الكامل بلغة TypeScript جنباً إلى جنب مع Python، يوضّح كيف يبدو النمطان في كل لغة:

```python
# Python -- production streaming pattern
import anthropic
from dotenv import load_dotenv

load_dotenv()

def stream_response(prompt: str, system: str = "") -> tuple[str, anthropic.types.Usage]:
    """
    Stream a response, returning (full_text, usage).
    Suitable for web server endpoints that stream to the client.
    """
    client = anthropic.Anthropic()
    accumulated = []

    messages_kwargs = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        messages_kwargs["system"] = system

    with client.messages.stream(**messages_kwargs) as stream:
        for chunk in stream.text_stream:
            accumulated.append(chunk)
            # In a web server: yield chunk to the HTTP response here

    final = stream.get_final_message()
    return "".join(accumulated), final.usage


text, usage = stream_response("What is the capital of France? One word.")
print(f"Response: {text}")
print(f"Usage: {usage.input_tokens} in / {usage.output_tokens} out")
```

نسخة TypeScript (`code/main.ts`) تستخدم النمط نفسه مع `async/await` و `for await` فوق التدفق.

> **نقلة في المنظور:** عدم استخدام الـ streaming ليس أبطأ فقط -- بل يُشغِل عملية الخادم (server process) بينما تنتظر الاستجابة الكاملة. في خادم ويب يعالج طلبات متزامنة، استدعاء بدون streaming يستغرق 5 ثوانٍ سيحجز ذلك الـ thread لمدة 5 ثوانٍ. أما الـ streaming فيتيح لك البدء بإرسال البايتات إلى المستخدم فوراً بينما يواصل الموديل التوليد، وهذا تحسين لتجربة المستخدم وتحسين لكفاءة الخادم في آنٍ واحد. المقايضة: الـ streaming يتطلب منك التعامل مع حالة جزئية، ما يضيف تعقيداً لمعالجة الأخطاء والتسجيل (logging).

---

## التسليم

المُخرَج (artifact) لهذا الدرس هو بطاقة مهارة لأنماط أول استدعاء للـ API.

راجع `outputs/skill-first-api-call.md`.

---

## التقييم

تكون إعدادات أول استدعاء للـ API لديك صحيحة عندما تنجح كل هذه الفحوصات:

```python
# Run with: uv run python -c "exec(open('checks.py').read())"
# Or step through manually:

import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

# 1. Non-streaming response has expected fields
r = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=32,
    messages=[{"role": "user", "content": "Reply with exactly: CHECK OK"}],
)
assert r.stop_reason in ("end_turn", "max_tokens", "stop_sequence"), f"Unexpected: {r.stop_reason}"
assert r.usage.input_tokens > 0, "Input tokens should be > 0"
assert r.usage.output_tokens > 0, "Output tokens should be > 0"
assert len(r.content) > 0, "Content should not be empty"
print(f"OK: non-streaming response valid. stop_reason={r.stop_reason}")

# 2. Stop reason "max_tokens" is detectable
r2 = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=5,  # intentionally tiny
    messages=[{"role": "user", "content": "Write a 500-word essay about the ocean."}],
)
assert r2.stop_reason == "max_tokens", f"Expected max_tokens, got {r2.stop_reason}"
print(f"OK: max_tokens stop reason detected correctly")

# 3. Streaming accumulates correctly
with client.messages.stream(
    model="claude-3-5-haiku-20241022",
    max_tokens=32,
    messages=[{"role": "user", "content": "Reply with exactly: STREAM OK"}],
) as stream:
    chunks = list(stream.text_stream)
full_text = "".join(chunks)
final = stream.get_final_message()
assert len(full_text) > 0, "Accumulated stream text should not be empty"
assert final.usage.output_tokens > 0, "Output tokens should be > 0 after streaming"
print(f"OK: streaming accumulated {len(chunks)} chunks, {final.usage.output_tokens} tokens")

print("\nAll API call checks passed.")
```
