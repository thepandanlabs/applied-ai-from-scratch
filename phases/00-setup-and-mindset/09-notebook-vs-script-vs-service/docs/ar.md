# Notebook مقابل Script مقابل Service

> الصيغة التي تستخدمها لبناء ميزة AI تحدّد مدى صعوبة تسليمها للإنتاج.

**النوع:** Learn
**اللغات:** Python
**المتطلبات:** الدرس 03 (أول استدعاء API)، الدرس 08 (أساسيات Docker)
**الوقت:** ~30 دقيقة
**أهداف التعلّم:**
- تسمية صيغ التسليم الثلاث لعمل AI وحالة الاستخدام الأساسية لكل منها
- تحديد الشروط التي تستدعي الترقية من صيغة إلى التي تليها
- تنفيذ نفس مهمة AI في الصيغ الثلاث جميعها وملاحظة الفرق في البنية
- تجنّب فخّ الـ notebook: البقاء في وضع الاستكشاف بعد أن يتجاوز فائدته

---

## المشكلة

عالِم بيانات يقضي أسبوعين في بناء أداة تلخيص للمستندات داخل Jupyter notebook. الـ notebook يعمل. يستدعي الـ API، ويعالج ملفات PDF، وينتج ملخّصات نظيفة. يسأل نائب رئيس الهندسة: "هل يمكننا إضافة هذا إلى المنتج؟"

الإجابة تستغرق أربعة أسابيع إضافية. لا بد من إعادة كتابة الـ notebook على هيئة service. نصف المنطق موزّع في خلايا (cells) عشوائية شُغّلت بترتيب غير خطي. لا توجد اختبارات. لم تُضَف معالجة الأخطاء أصلاً لأن إعادة تشغيل خلية كان أسهل. مفتاح الـ API مكتوب مباشرة في الكود (hardcoded). ولا توجد طريقة لاستدعائه دون فتح Jupyter.

هذه هي الفجوة بين الـ notebook والإنتاج، وهي تقتل عروض AI التوضيحية باستمرار. المشكلة ليست أن الـ notebooks سيئة، بل أن الفريق استمر في استخدام الـ notebook بعد تاريخ انتهاء صلاحيته الطبيعي.

لكل صيغة من الصيغ الثلاث موضعها المناسب: الـ notebooks للاستكشاف، والـ scripts لقابلية التكرار، والـ services للإنتاج. ومعرفة متى تتخرّج من واحدة إلى التي تليها مهارة جوهرية في هندسة AI التطبيقية.

---

## المفهوم

### الصيغ الثلاث

```
FORMAT        PRIMARY USE             EXPIRES WHEN...
-----------   ---------------------   ----------------------------------
Notebook      Exploration, demos,     You need to run it on a schedule,
              stakeholder review      share it as an API, or run it
                                      more than once without opening
                                      Jupyter

Script        Repeatable pipeline,    More than one user needs to call
              scheduled jobs,         it simultaneously, or it needs to
              CLI tools               stay alive between requests

Service       Persistent endpoint,    Never expires (this is the final
              multi-user, production  form for production AI features)
```

### شجرة القرار

```
Start here: What are you actually building?
         │
         ▼
Is this for exploration, one-off analysis, or a stakeholder demo?
    │
    ├── YES → Notebook
    │         Trigger to upgrade: "I need to run this again"
    │         or "I need to share this as an API"
    │
    └── NO
         │
         ▼
    Does a single person need to run it on demand, on a schedule,
    or from the command line?
         │
         ├── YES → Script
         │         Trigger to upgrade: "Multiple users need to call this"
         │         or "It needs to be always available"
         │
         └── NO
              │
              ▼
         Multiple users, persistent availability, or
         integration into another system → Service
```

### ما الذي يتغيّر عند كل ترقية

```
Notebook → Script        Script → Service
------------------       ------------------
Remove notebook cells    Add HTTP interface
Add main() function      Add async handling
Add error handling        Add concurrency
Add CLI args or config   Add health check
Move hardcoded values    Add logging to stdout
  to env vars            Add Docker container
```

---

## البناء

### المهمة: تلخيص مستند بالصيغ الثلاث

استخدم نفس مهمة AI في التنفيذات الثلاثة: تلخيص مقطع نصّي قصير. المهمة متطابقة تمامًا. صيغة التسليم هي ما يغيّر كل شيء آخر.

**الصيغة 1: خلية notebook**

في Jupyter notebook، يكون هذا عادةً بضع خلايا:

```python
# Cell 1: Imports and client setup
import anthropic
import os

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
```

```python
# Cell 2: The text to summarize (often copy-pasted in directly)
text = """
The transformer architecture, introduced in 2017, replaced recurrence
with self-attention. This enabled parallel training across tokens,
which unlocked much larger models and datasets. By 2020, these models
generalized across tasks without task-specific fine-tuning.
"""
```

```python
# Cell 3: The API call
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=128,
    messages=[{"role": "user", "content": f"Summarize in one sentence:\n\n{text}"}]
)
print(response.content[0].text)
```

هذا يعمل. يمكنك عرضه في اجتماع. ويمكنك إعادة تشغيل Cell 3. لكن إذا أغلقت Jupyter وعدت غدًا، تحتاج أن تتذكّر أي الخلايا تُشغّلها وبأي ترتيب.

**الصيغة 2: Script (`main.py`)**

```python
import anthropic
import os
import sys

def summarize(text: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        messages=[{"role": "user", "content": f"Summarize in one sentence:\n\n{text}"}]
    )
    return response.content[0].text

def main() -> None:
    text = sys.stdin.read().strip()
    if not text:
        print("Usage: echo 'your text' | python main.py", file=sys.stderr)
        sys.exit(1)
    print(summarize(text))

if __name__ == "__main__":
    main()
```

شغّله:
```bash
echo "The transformer architecture..." | python main.py
```

الآن أصبح أداة. قابل للتكرار. يستطيع أي شخص في الفريق تشغيله. ويمكنك وضعه في cron job. ويمكنك تمرير نص له من script آخر. ولا يزال يبعد دالّة واحدة عن أن يصبح قابلاً للاختبار.

**الصيغة 3: Service (`main.py` مع FastAPI)**

```python
import anthropic
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

class SummarizeRequest(BaseModel):
    text: str

class SummarizeResponse(BaseModel):
    summary: str

@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(req: SummarizeRequest) -> SummarizeResponse:
    if not req.text.strip():
        raise HTTPException(status_code=422, detail="text cannot be empty")
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        messages=[{"role": "user", "content": f"Summarize in one sentence:\n\n{req.text}"}]
    )
    return SummarizeResponse(summary=response.content[0].text)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

شغّله:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

استدعِه:
```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"text": "The transformer architecture..."}'
```

الآن أصبح يعمل باستمرار (always-on). يستطيع أي نظام استدعاءه عبر HTTP. ويمكن لعدّة مستخدمين الاتصال به في آنٍ واحد. ويمكنك وضعه في حاوية (Lesson 08) ونشره على أي سحابة.

> **اختبار من الواقع:** يسأل مدير منتج: "ألا يمكننا فقط تشغيل الـ notebook حاليًا ونقله لاحقًا؟" أحيانًا نعم. لكن "ننقله لاحقًا" يستغرق عادةً 4 أضعاف الوقت مقارنة بـ"كتابته كـ script من البداية". صيغة الـ notebook تراكم ديونًا تقنية غير مرئية حتى تأتي اللحظة التي يحاول فيها أحدهم تشغيله بلا واجهة (headlessly). إذا كان هناك أي احتمال لتشغيله أكثر من مرتين، فاكتبه كـ script.

---

## الاستخدام

معايير التخرّج للإنتاج بسيطة. احفظ هذا الجدول في مرجعك.

| تحتاج هذا... | استخدم هذه الصيغة |
|-----------------|----------------|
| الاستكشاف، النمذجة الأوّلية، الشرح لأصحاب المصلحة | Notebook |
| تشغيله وفق جدول زمني، تمريره في bash script، مشاركته مع مهندس واحد | Script |
| HTTP API، عدّة مستخدمين متزامنين، تشغيل دائم، محوسب في حاوية | Service |

التدرّج في الواقع باتجاه واحد. لا تعود أبدًا من service إلى notebook لميزة إنتاجية. كود الدرس (`code/main.py`) يعرض الأنماط الثلاثة كلها في ملف واحد يمكنك تشغيله لمقارنتها مباشرة.

> **نقلة في المنظور:** يسأل مهندس backend: "لماذا نستخدم notebook أصلًا؟ سأكتب script من البداية." بالنسبة للمسائل المحدّدة جيدًا، هذا صحيح. الـ notebooks تستحق مكانها حين تكون فعلاً غير متأكد من المقاربة الصحيحة. تتيح لك تجربة خمسة نماذج embedding في خمس خلايا ومقارنة النتائج بصريًا، دون انضباط حدود الدالّة النظيفة. الثمن أن عقلية الاستكشاف تبقى أطول مما ينبغي. أفضل مهندسي AI التطبيقي يعرفون متى يغلقون الـ notebook ويفتحون `main.py`.

---

## التسليم

المُخرَج القابل لإعادة الاستخدام لهذا الدرس هو `outputs/prompt-delivery-format-decision.md`: دليل قرار يمكنك لصقه في أي مشروع لتحديد الصيغة الصحيحة لميزة AI.

راجع `outputs/prompt-delivery-format-decision.md`.

---

## التقييم

**هل يستطيع الـ script العمل دون Jupyter؟**

```bash
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY echo "Test text" | python code/main.py
```

إذا خرج بالرمز 0 وطبع ملخّصًا، فصيغة الـ script تعمل.

**هل يتعامل الـ service مع الطلبات المتزامنة؟**

```bash
# Start the service
uvicorn code.main:app --port 8000 &

# Fire 5 concurrent requests
for i in {1..5}; do
  curl -s -X POST http://localhost:8000/summarize \
    -H "Content-Type: application/json" \
    -d '{"text": "Short test text number '"$i"'."}' &
done
wait
```

ينبغي أن تُرجِع الخمسة جميعها بنجاح. إذا تعلّق أيٌّ منها أو أخطأ، فمعالجة التزامن (concurrency) تحتاج عملًا.

**هل صيغة الـ service أكثر جاهزية للتشغيل (ops-ready) فعلاً؟**

قِس الوقت اللازم للإجابة عن "هل الـ service سليم؟" لكل صيغة:

- Notebook: افتح Jupyter، شغّل الخلايا، راقب المخرجات - دقائق
- Script: `python main.py --health-check` - ثوانٍ
- Service: `curl http://localhost:8000/health` - أجزاء من الثانية، وقابل للأتمتة

صيغة الـ service تفوز في قابلية المراقبة (observability). نقطة الـ health endpoint إشارة من الدرجة الأولى يفهمها كلٌّ من موازنات الأحمال (load balancers) وأنابيب الـ CI وأدوات المناوبة (on-call).
