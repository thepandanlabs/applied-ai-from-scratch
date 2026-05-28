**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 06-llm-as-judge, 08-eval-harnesses, 09-ci-for-prompts
**الوقت:** ~60 دقيقة
**أهداف التعلّم:**
- بناء خط أنابيب تقييم آني (online eval) غير متزامن (async) يقيّم حركة مرور الإنتاج دون إضافة زمن تأخير يواجه المستخدم
- التقاط إشارات تغذية راجعة ضمنية (إعجاب/عدم إعجاب) وربطها بدرجات مقيّم الـ LLM
- تنفيذ عرض ملخّص (summary view) يُبرز اتجاهات الجودة، ومعدّلات الفشل، والحالات المُعلَّمة

---

## MOTTO

**التقييمات الآنية (online evals) هي كاشف الحريق في إنتاجك: لا تمنع الحرائق، لكنها تخبرك أن المبنى يحترق قبل أن يبدأ المستخدمون بالاتصال.**

---

## المشكلة

بنيت golden set، وربطت تقييم CI، وأنت واثق أن مساعدك ينجح قبل كل عملية نشر (deploy). ثم يحدّث مزوّد نموذج نموذجَه بصمت الساعة الثانية صباحاً يوم ثلاثاء. أو تنتقل قاعدة مستخدميك من أسئلة تقنية إلى أسئلة خدمة عملاء. أو يبدأ نوع جديد من المدخلات بتوليد هلوسات (hallucinations) لم تتوقّعها أبداً.

تفوّت تقييماتك دون اتصال (offline evals) كل هذا. لا تعرف إلا ما وضعته في golden set. الإنتاج مختلف: فوضوي، غير متوقّع، وحيّ. تحتاج إشارة مستمرّة على حركة المرور الحقيقية، لا مجرّد فحص بوّابة (gating check) على حالات معروفة.

الفخّ الذي يقع فيه المهندسون: يعاملون التقييم كبوّابة نشر بدل كونه أداة قياس مستمرّة. التقييم على البوّابة فقط يعني أن جودتك تتدهور بصمت لأيام أو أسابيع قبل أن يلاحظ أحد. وعندما تتراكم تذاكر الدعم، يكون الضرر قد وقع.

تعمل التقييمات الآنية باستمرار على عيّنة من حركة مرور الإنتاج، وتقيّمها بشكل غير متزامن (صفر زمن تأخير مضاف للمستخدمين)، وتغذّي تلك الإشارة عائدةً إلى عملية تحسينك. هكذا تبقى أنظمة الـ AI الإنتاجية بصحة جيدة.

---

## المفهوم

### التقييمات دون اتصال مقابل الآنية

```
OFFLINE EVAL                          ONLINE EVAL
--------------------                  --------------------
Runs on golden set                    Runs on real traffic
Runs before deploy (CI)               Runs continuously in prod
Synchronous (blocks deploy)           Asynchronous (no user latency)
Catches known failure modes           Catches unknown failure modes
You control the inputs                Users control the inputs
```

### خط أنابيب التقييم غير المتزامن

```mermaid
flowchart LR
    U[User Request] --> API[FastAPI Handler]
    API --> R[Response to User]
    API --> Q[Eval Queue]
    Q --> W[Eval Worker]
    W --> J[LLM Judge]
    J --> L[Score Log]
    U2[User Feedback] --> F[/feedback endpoint]
    F --> L
    L --> S[Summary View]
```

القرار المعماري الأساسي: طابور التقييم (eval queue) من نوع "أطلق وانسَ" (fire-and-forget). يضع معالج الـ API التفاعل في الطابور ويعيد الرد إلى المستخدم فوراً. يلتقطه عامل التقييم (worker) في الخلفية. لا ينتظر المستخدمون التقييم أبداً.

### استراتيجية أخذ العيّنات

لا تقيّم كل شيء. نظام إنتاجي يعالج 10,000 طلب يومياً بسعر 0.02$ للتقييم = 200$ يومياً لمجرّد التقييم. بدلاً من ذلك:

```
SAMPLING STRATEGY
-----------------
Random sample:      5-10% of all traffic (baseline signal)
Edge case triggers: 100% of inputs matching risky patterns
                    (long inputs, unusual topics, low-confidence outputs)
Feedback-triggered: 100% of interactions with explicit thumbs-down
```

الهدف: 100+ تقييم مُسجّل يومياً كحدّ أدنى لاكتشاف هبوط جودة بنسبة 10% خلال 24 ساعة.

### حلقة التغذية الراجعة

التقييمات الآنية مفيدة فقط إن أغلقت الحلقة:

```
score drops below threshold
        |
        v
    alert fires
        |
        v
  error analysis on flagged cases
        |
        v
  identify failure category
        |
        v
  add cases to golden set
        |
        v
  fix prompt or model config
        |
        v
  offline eval verifies fix
        |
        v
  deploy
        |
        v
  online eval confirms production improvement
```

### الإشارات الضمنية

حتى بدون مقيّم LLM، يمنحك المستخدمون إشارات:
- إعجاب/عدم إعجاب (صريح)
- معدّل النسخ واللصق (ضمني: إن نسخوا الإجابة، فقد كانت مفيدة)
- سؤال متابعة مباشرة بعد الإجابة (ضمني: الإجابة الأولى لم تنفع)
- معدّل هجر الجلسة (ضمني: غادروا بعد إجابة سيئة)

هذه رخيصة الالتقاط وترتبط جيداً بدرجات مقيّم الـ LLM عند تجميعها.

---

## البناء

### الإعداد

```bash
uv init online-evals
cd online-evals
uv add fastapi uvicorn anthropic python-dotenv
```

أنشئ `main.py`:

```python
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, date
from typing import Optional
from collections import defaultdict

import anthropic
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

app = FastAPI()
client = anthropic.Anthropic()

# In-memory queue (replace with Redis or SQS in production)
eval_queue: asyncio.Queue = asyncio.Queue()
score_log: list[dict] = []
```

### الخطوة 1: معالج الطلب

يعيد المعالج الرد أولاً، ثم يضعه في الطابور للتقييم. لا ينتظر المستخدم التقييم أبداً.

```python
class QuestionRequest(BaseModel):
    question: str
    user_id: Optional[str] = None

class QuestionResponse(BaseModel):
    trace_id: str
    answer: str

async def call_model(question: str) -> str:
    """Call the model and return the answer."""
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": f"Answer this question concisely and accurately: {question}"
            }
        ]
    )
    return response.content[0].text

@app.post("/ask", response_model=QuestionResponse)
async def ask(request: QuestionRequest, background_tasks: BackgroundTasks):
    trace_id = str(uuid.uuid4())[:8]
    
    # Get the model response
    answer = await call_model(request.question)
    
    # Fire-and-forget: enqueue for background eval
    background_tasks.add_task(
        enqueue_for_eval,
        trace_id=trace_id,
        question=request.question,
        answer=answer,
    )
    
    # Return immediately -- user never waits for eval
    return QuestionResponse(trace_id=trace_id, answer=answer)
```

### الخطوة 2: عامل التقييم

يلتقط عامل التقييم التفاعلات من الطابور ويقيّمها بمقيّم LLM.

```python
JUDGE_PROMPT = """You are an eval judge. Score this AI response on a scale of 0.0 to 1.0.

Question: {question}
Answer: {answer}

Score on:
- Accuracy: is the answer factually correct?
- Completeness: does it address the full question?
- Conciseness: is it appropriately brief without losing content?

Return ONLY a JSON object: {{"score": 0.85, "rationale": "one sentence"}}"""

async def enqueue_for_eval(trace_id: str, question: str, answer: str):
    """Put an interaction on the eval queue."""
    await eval_queue.put({
        "trace_id": trace_id,
        "question": question,
        "answer": answer,
        "timestamp": datetime.utcnow().isoformat(),
    })

async def eval_worker():
    """Background worker: scores queued interactions."""
    print("Eval worker started")
    while True:
        try:
            interaction = await asyncio.wait_for(eval_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        
        # Score with LLM judge
        try:
            judge_response = client.messages.create(
                model="claude-haiku-4-5",  # cheaper model for judging
                max_tokens=128,
                messages=[
                    {
                        "role": "user",
                        "content": JUDGE_PROMPT.format(
                            question=interaction["question"],
                            answer=interaction["answer"],
                        )
                    }
                ]
            )
            result = json.loads(judge_response.content[0].text)
            score = float(result.get("score", 0.5))
            rationale = result.get("rationale", "")
        except Exception as e:
            print(f"Judge error for {interaction['trace_id']}: {e}")
            score = -1.0  # sentinel: eval failed
            rationale = str(e)
        
        # Write to score log
        log_entry = {
            "trace_id": interaction["trace_id"],
            "score": score,
            "rationale": rationale,
            "timestamp": interaction["timestamp"],
            "input": interaction["question"],
            "output": interaction["answer"],
            "source": "judge",
        }
        score_log.append(log_entry)
        
        # Also persist to file
        with open("score_log.jsonl", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        eval_queue.task_done()
        print(f"Scored {interaction['trace_id']}: {score:.2f}")

@app.on_event("startup")
async def startup_event():
    """Start the eval worker on app startup."""
    asyncio.create_task(eval_worker())
```

### الخطوة 3: نقطة نهاية إشارة التغذية الراجعة

```python
class FeedbackRequest(BaseModel):
    trace_id: str
    thumbs_up: bool

@app.post("/feedback")
async def feedback(request: FeedbackRequest):
    """Capture explicit user feedback and append to the score log."""
    log_entry = {
        "trace_id": request.trace_id,
        "score": 1.0 if request.thumbs_up else 0.0,
        "rationale": "user feedback",
        "timestamp": datetime.utcnow().isoformat(),
        "input": None,
        "output": None,
        "source": "user_feedback",
    }
    score_log.append(log_entry)
    
    with open("score_log.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    
    return {"status": "recorded", "trace_id": request.trace_id}
```

### الخطوة 4: عرض الملخّص

```python
@app.get("/summary")
async def summary():
    """Read the score log and return today's quality summary."""
    today = date.today().isoformat()
    
    # Separate judge scores from user feedback
    judge_scores = [
        e["score"] for e in score_log
        if e["source"] == "judge" and e["score"] >= 0 and e["timestamp"].startswith(today)
    ]
    feedback_entries = [
        e for e in score_log
        if e["source"] == "user_feedback" and e["timestamp"].startswith(today)
    ]
    
    # Flag low-scoring cases for review
    flagged = [
        {"trace_id": e["trace_id"], "score": e["score"], "input": e["input"]}
        for e in score_log
        if e["source"] == "judge" and e["score"] < 0.5 and e["timestamp"].startswith(today)
    ]
    
    avg_score = sum(judge_scores) / len(judge_scores) if judge_scores else None
    thumbs_up_count = sum(1 for e in feedback_entries if e["score"] == 1.0)
    thumbs_up_rate = thumbs_up_count / len(feedback_entries) if feedback_entries else None
    
    return {
        "date": today,
        "judge_evals_today": len(judge_scores),
        "average_score": round(avg_score, 3) if avg_score else None,
        "thumbs_up_rate": round(thumbs_up_rate, 3) if thumbs_up_rate is not None else None,
        "flagged_cases": flagged,
        "alert": avg_score is not None and avg_score < 0.7,
    }
```

### تشغيلها

```bash
uvicorn main:app --reload
```

أرسل طلباً:
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of France?"}'
# Returns immediately with trace_id and answer
# Background: eval worker scores it in ~2 seconds

# Give feedback
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{"trace_id": "abc12345", "thumbs_up": true}'

# Check summary
curl http://localhost:8000/summary
```

> **اختبار من الواقع:** يُظهر تقييمك الآني أن مقيّم الـ LLM لديك يقيّم 200 تفاعل إنتاج يومياً بسعر 0.02$ لكل واحد. هذا 4$ يومياً أو 1,460$ سنوياً لمجرّد التقييم. ما استراتيجيتك للحصول على الإشارة نفسها بتكلفة أقل بعشرة أضعاف؟

للجواب ثلاثة أجزاء: (1) خذ عيّنات بشكل أكثر صرامة: عيّنة عشوائية بنسبة 10% بدل 100% = 20 تقييماً يومياً للمراقبة الروتينية. (2) استخدم نموذج مقيّم أرخص (Claude Haiku بدل Opus) للتقييم الروتيني، مع حجز النموذج القوي للحالات المُعلَّمة. (3) استفد من الإشارات الضمنية أولاً: التقط الإعجاب/عدم الإعجاب وأطلق تقييمات مقيّم الـ LLM فقط عند عدم الإعجاب أو على حركة مرور مأخوذة كعيّنة إحصائياً. يمكنك الحصول على 80% من الإشارة بـ 5% من التكلفة.

---

## الاستخدام

يعمل خط الأنابيب محلي الصنع لكن فيه احتكاك: لا لوحة تحكم، لا تنبيهات، لا تجميع عبر عمليات النشر. يحلّ Langfuse كل هذا.

### الإعداد

```bash
uv add langfuse
```

```python
import os
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context

langfuse = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)
```

### التتبّع (Tracing) مع Langfuse

```python
@observe()  # automatically creates a trace
async def ask_with_langfuse(question: str) -> dict:
    trace_id = langfuse_context.get_current_trace_id()
    
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=512,
        messages=[{"role": "user", "content": question}]
    )
    answer = response.content[0].text
    
    return {"trace_id": trace_id, "answer": answer}
```

### التسجيل في الخلفية مع Langfuse

```python
async def score_with_langfuse(trace_id: str, question: str, answer: str):
    """Background task: run LLM judge and post score to Langfuse."""
    # Run your judge (same as before)
    judge_response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=128,
        messages=[{
            "role": "user",
            "content": JUDGE_PROMPT.format(question=question, answer=answer)
        }]
    )
    result = json.loads(judge_response.content[0].text)
    
    # Post score to Langfuse -- appears in dashboard immediately
    langfuse.score(
        trace_id=trace_id,
        name="llm-judge-quality",
        value=float(result["score"]),
        comment=result.get("rationale", ""),
    )
```

### التقاط التغذية الراجعة مع Langfuse

```python
@app.post("/feedback")
async def feedback_langfuse(request: FeedbackRequest):
    """User feedback goes directly to Langfuse as a score."""
    langfuse.score(
        trace_id=request.trace_id,
        name="user-thumbs",
        value=1.0 if request.thumbs_up else 0.0,
        comment="explicit user feedback",
    )
    return {"status": "recorded"}
```

### ما الذي تضيفه لوحة تحكم Langfuse

تمنحك واجهة Langfuse ما لا يستطيعه سجلّ الـ JSONL محلي الصنع:
- مخطّط سلاسل زمنية لمتوسط الدرجة باليوم، مع نطاقات مئوية (percentile bands)
- تفصيل الدرجة حسب النموذج، أو إصدار الـ prompt، أو شريحة المستخدمين
- التنقيب من هبوط في اتجاه (trend) إلى المسارات الفردية التي سبّبته
- قواعد تنبيه (الدرجة < 0.7 لمدة 3 ساعات = إرسال إشعار Slack)
- مقارنة مسارات جنباً إلى جنب: ما الذي تشترك فيه المسارات الفاشلة؟

### محلي الصنع مقابل Langfuse

```
HOMEGROWN PIPELINE          LANGFUSE
--------------------------  --------------------------
asyncio Queue               Managed queue, no infra
JSONL file                  Postgres-backed, queryable
Manual summary endpoint     Built-in dashboard + alerts
No drill-down               Trace viewer with full context
Works offline/air-gap       Requires network (or self-host)
Zero vendor dependency      Vendor dependency (open-source)
```

متى تستخدم محلي الصنع: النماذج الأولية المبكّرة، البيئات المعزولة (air-gapped)، عندما تريد تحكّماً كاملاً في منطق التقييم.

متى يستحقّ Langfuse تعقيده: عندما يكون لديك عدّة مهندسين، عدّة نماذج، عدّة إصدارات prompt، وتحتاج رؤية مشتركة لجودة الإنتاج دون بناء منصّة مراقبة.

> **نقلة في المنظور:** تعرض لوحة تحكم تقييمك الآني على مدير منتج. يسأل "لماذا الدرجة 0.87 اليوم لكنها 0.79 في عطلات نهاية الأسبوع؟" ما الذي يسبّب هذا النمط، وماذا يخبرك عن أين تركّز تحسيناتك؟

مستخدمو عطلة نهاية الأسبوع جمهور مختلف. قد يكونون أقلّ تقنية، أو أكثر استكشافاً، أو يسألون أسئلة خارج حالة الاستخدام الأساسية التي صُمّم النظام لها. يخبرك النمط: golden set لديك على الأرجح مثقل باستعلامات على نمط أيام الأسبوع. الإصلاح ليس جعل النموذج أذكى بشكل عام: بل تحليل مسارات فشل عطلة نهاية الأسبوع، وتحديد فئة الفشل (أسئلة خارج النطاق؟ لغة غير رسمية؟ توزيع موضوعات مختلف؟)، وإضافة حالات تمثيلية من عطلة نهاية الأسبوع إلى golden set.

---

## التسليم

ناتج هذا الدرس هو `outputs/skill-online-eval-pipeline.md`. راجع مجلّد المخرجات.

**ما الذي بنيته:**
- خدمة FastAPI بتقييم خلفي من نوع "أطلق وانسَ" (صفر زمن تأخير يواجه المستخدم)
- عامل مقيّم LLM يقيّم التفاعلات بشكل غير متزامن
- نقطة نهاية إشارة تغذية راجعة تلتقط إعجاب/عدم إعجاب المستخدم الصريح
- عرض ملخّص يُبرز متوسط الدرجة، ومعدّل الإعجاب، والحالات المُعلَّمة
- خط الأنابيب نفسه باستخدام Langfuse للمراقبة بمستوى إنتاجي

---

## التقييم

### التغطية

هل معدّل أخذ العيّنات لديك مرتفع بما يكفي لاكتشاف هبوط جودة بنسبة 10% خلال 24 ساعة؟

قاعدة عملية: 100 تقييم مأخوذ كعيّنة يومياً هو الحدّ الأدنى لاكتشاف الانزياح (drift) بشكل موثوق. إن كانت حركة مرورك 1,000 طلب/يوم، فمعدّل عيّنة 10% يبلغ تلك العتبة. إن كانت الحركة أقلّ، فزِد معدّل العيّنة أو استخدم كل الحركة.

تحقّق: احقن هبوط جودة اصطناعياً (اجعل نموذجك الوهمي يعيد إجابات منخفضة الجودة لـ 10% من الطلبات)، وأكّد أن عرض الملخّص يُظهر هبوط الدرجة خلال 24 ساعة.

### أثر زمن التأخير

عرض القيمة الكامل للتقييم غير المتزامن هو صفر زمن تأخير للمستخدم. تحقّق منه:

```python
import time
import httpx

start = time.time()
response = httpx.post("http://localhost:8000/ask", json={"question": "test"})
latency = time.time() - start

# The eval should NOT add latency -- this should match your model call time only
print(f"User-facing latency: {latency:.3f}s")
```

عامل التقييم العامل في الخلفية يجب ألّا يظهر في هذا القياس.

### اتّساق المقيّم

شغّل الـ 20 حالة نفسها عبر كل من مقيّمك الآني ومقيّم CI دون اتصال. توافق الدرجات ضمن 10% هو الهدف.

```python
def check_judge_consistency(cases: list[dict]) -> float:
    online_scores = [online_judge(c) for c in cases]
    offline_scores = [offline_judge(c) for c in cases]
    
    deltas = [abs(o - f) for o, f in zip(online_scores, offline_scores)]
    avg_delta = sum(deltas) / len(deltas)
    
    print(f"Average score delta: {avg_delta:.3f}")
    print(f"Max delta: {max(deltas):.3f}")
    return avg_delta

# Target: avg_delta < 0.10
```

إن كان الاتّساق ضعيفاً، فإن prompt مقيّمك غير محدّد بما يكفي. أضف مقياساً (rubric) بمعايير صريحة ومراسي درجات (score anchors) (كيف تبدو 0.5؟ كيف تبدو 0.9؟).
