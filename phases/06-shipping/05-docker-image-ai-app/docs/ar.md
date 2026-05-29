# صورة Docker لتطبيق AI

> ترتيب الطبقات (layers) ليس مسألة أناقة: إنه الفرق بين بناء يستغرق ثانيتين وبناء يستغرق ثلاث دقائق.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** دروس المرحلة 06 من 01 إلى 04 (خدمة FastAPI لـ AI)، إلمام أساسي بـ Docker
**الوقت:** ~60 دقيقة
**أهداف التعلّم:**
- كتابة Dockerfile متعدّد المراحل (multi-stage) يفصل تثبيت الاعتماديات عن كود التطبيق
- شرح لماذا يحدّد ترتيب الطبقات نسبة إصابة الكاش (cache hit rate) ولماذا يهمّ ذلك على نطاق الـ CI
- تشغيل خدمة FastAPI لـ AI مُحوسَبة بـ Docker مع تمرير الأسرار (secrets) كمتغيرات بيئة وقت التشغيل
- التحقّق من فحص الصحة (health check) باستخدام `docker inspect`
- كتابة ملف `.dockerignore` يمنع بيانات الاعتماد والملفات الكبيرة من دخول الصورة

---

## المشكلة

لديك خدمة FastAPI لـ AI عاملة على جهازك. يستنسخ زميل المستودع فيحصل على إصدار Python مختلف، ومكتبة نظام مفقودة، وخطأ استيراد لم ترَه قطّ. بيئة الـ staging لديك تعمل بسلاسة؛ والإنتاج يرمي segfault لأن الصورة الأساسية (base image) لديها glibc مختلف. ومهندس المناوبة (on-call) لا يستطيع إعادة إنتاج العلّة لأنه على macOS والخادم على Linux.

هذه ليست مشكلة Python. إنها مشكلة تحزيم (packaging). كل خدمة AI تصل إلى الإنتاج يجب أن تجيب على سؤال واحد بيقين: "بهذه الصورة بالضبط، على أي جهاز يستطيع تشغيل Docker، هل تبدأ الخدمة وتستجيب بشكل صحيح؟" إن كانت الإجابة أي شيء غير "نعم"، فأنت لم تسلّم بعد.

وضع الفشل الذي يوقع معظم الفرق: يعمل الـ Dockerfile، لكنه يعيد البناء من الصفر في كل مرة لأن `COPY . .` يظهر قبل `RUN pip install -r requirements.txt`. مع 30 اعتمادية وanthropic SDK، يستغرق هذا التثبيت 90 ثانية. على خطّ أنابيب CI بـ 20 commit في اليوم، هذا 30 دقيقة من وقت البناء المهدور يوميًا. والإصلاح إعادة ترتيب سطر واحد. ومعرفة سبب نجاح ذلك تتطلّب فهم طبقات Docker.

---

## المفهوم

### طبقات Docker وكاش البناء

صورة Docker كومة من طبقات للقراءة فقط (read-only). كل تعليمة في الـ Dockerfile (`FROM`, `RUN`, `COPY`, `ENV`) تنشئ طبقة واحدة. يخزّن Docker كل طبقة في الكاش بحسب تعليمتها ومدخلاتها. وحين تتغيّر مدخلات طبقة، يُبطل Docker تلك الطبقة وكل طبقة بعدها.

```
┌─────────────────────────────────────────────────────────────┐
│  FROM python:3.12-slim                  layer 1 (base OS)   │
├─────────────────────────────────────────────────────────────┤
│  RUN apt-get install ...                layer 2 (sys deps)  │
├─────────────────────────────────────────────────────────────┤
│  COPY requirements.txt .                layer 3 (req file)  │
├─────────────────────────────────────────────────────────────┤
│  RUN pip install -r requirements.txt    layer 4 (packages)  │  <-- cache hit unless requirements.txt changed
├─────────────────────────────────────────────────────────────┤
│  COPY . .                               layer 5 (app code)  │  <-- always changes on code edit
├─────────────────────────────────────────────────────────────┤
│  CMD ["uvicorn", "app:app", ...]        layer 6 (entrypoint)│
└─────────────────────────────────────────────────────────────┘
```

إذا وضعت `COPY . .` قبل `RUN pip install`، فإن تغيير سطر واحد في `main.py` يُبطل طبقة pip install. وتُعاد الـ 90 ثانية كلها. أما بالترتيب الصحيح، فتغيير الكود يعيد تشغيل الطبقتين 5 و6 فقط. أما الطبقات 1-4 فتُصيب الكاش.

### البناء متعدّد المراحل

البناء متعدّد المراحل يستخدم عبارتي `FROM`. المرحلة الأولى (build) تثبّت المترجمات (compilers) وأدوات التطوير اللازمة لبناء الحزم (wheels). والمرحلة الثانية (runtime) تنسخ الحزم المُجمّعة فقط إلى صورة بسيطة، تاركةً أدوات البناء وراءها.

```
┌─────────────────────────────┐    ┌─────────────────────────────┐
│  BUILD STAGE                │    │  RUNTIME STAGE              │
│  python:3.12                │    │  python:3.12-slim           │
│                             │    │                             │
│  apt-get install gcc        │    │  (no gcc, no build tools)   │
│  pip install -r reqs.txt    │ -> │  COPY --from=build ...      │
│  (builds C extensions)      │    │  non-root user              │
│                             │    │  HEALTHCHECK                │
│  ~600 MB                    │    │  ~150 MB                    │
└─────────────────────────────┘    └─────────────────────────────┘
```

صورة الـ runtime أصغر بأربعة أضعاف، وفيها حزم مثبّتة أقل (سطح هجوم أصغر)، وتبدأ أسرع لأن ما يُحمَّل أقل.

### ما الذي يذهب أين

| الجانب | النهج |
|---------|----------|
| إعدادات غير سرّية (المنفذ، العمّال، مستوى السجلّ) | `ENV` في الـ Dockerfile أو `--env` وقت التشغيل |
| أسرار (مفاتيح API، رموز) | `--env` أو `--env-file` عند `docker run`؛ لا تكون أبدًا في الصورة |
| الكود المصدري | `COPY . .` في مرحلة الـ runtime |
| الحزم المُجمّعة | `COPY --from=build /usr/local/lib/python3.12/site-packages` |
| المستخدم المشغِّل | غير الجذر (`RUN useradd -m appuser && USER appuser`) |
| إشارة الصحة | `HEALTHCHECK CMD curl -f http://localhost:8000/health` |

---

## البناء

### الخطوة 1: خدمة FastAPI

أنشئ تطبيق FastAPI البسيط الذي سيحزّمه الـ Dockerfile. يتوقّع `ANTHROPIC_API_KEY` من البيئة ويكشف نقطة نهاية `/generate` ونقطة نهاية `/health`.

```python
# code/main.py
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import anthropic

app = FastAPI(title="AI App", version="1.0")
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("MODEL", "claude-3-5-haiku-20241022")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))


class GenerateRequest(BaseModel):
    prompt: str


class GenerateResponse(BaseModel):
    text: str
    model: str
    input_tokens: int
    output_tokens: int


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be empty")
    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": req.prompt}],
    )
    return GenerateResponse(
        text=msg.content[0].text,
        model=msg.model,
        input_tokens=msg.usage.input_tokens,
        output_tokens=msg.usage.output_tokens,
    )
```

### الخطوة 2: requirements.txt

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
anthropic==0.40.0
pydantic==2.9.2
```

ثبّت الإصدارات بدقّة. المتطلبات غير المثبّتة (unpinned) تعني أن الصورة المبنية اليوم قد تختلف عن الصورة المبنية الشهر القادم بعد إطلاق اعتمادية لتغيير يكسر التوافق.

### الخطوة 3: .dockerignore

```
.env
.env.*
__pycache__/
*.pyc
*.pyo
.git/
.github/
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
outputs/
docs/
*.md
```

ملف `.dockerignore` يمنع الأسرار (`.env`)، والمجلّدات الكبيرة (`.git`)، والملفات غير ذات الصلة من الإرسال إلى سياق بناء Docker. بدونه، يرسل `docker build` كل ملف في المجلّد إلى الـ daemon. على مستودع فيه `.venv/`، هذا غيغابايتات من الملفات المنسوخة قبل تشغيل أول طبقة.

### الخطوة 4: الـ Dockerfile

```dockerfile
# code/Dockerfile

# ----- BUILD STAGE -----
FROM python:3.12-slim AS build

WORKDIR /app

# Install system dependencies needed to build wheels (e.g., gcc for some packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements FIRST so pip install layer is cached on code-only changes
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ----- RUNTIME STAGE -----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install only curl for the health check
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from build stage (leave build tools behind)
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# Create non-root user
RUN useradd -m -u 1000 appuser

# Copy application code
COPY main.py .

USER appuser

# Non-secret config only; secrets injected at runtime via --env
ENV PORT=8000 \
    WORKERS=1 \
    LOG_LEVEL=info \
    MODEL=claude-3-5-haiku-20241022 \
    MAX_TOKENS=1024

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --log-level ${LOG_LEVEL}
```

### الخطوة 5: البناء والتشغيل

```bash
# Build the image
docker build -t ai-app:latest -f code/Dockerfile code/

# Run passing the API key at runtime (not baked into the image)
docker run -p 8000:8000 \
  --env ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  ai-app:latest

# Test
curl http://localhost:8000/health
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain Docker layers in one sentence."}'
```

> **اختبار من الواقع:** يسألك مدقّق أمان: "كيف تضمن أن `ANTHROPIC_API_KEY` ليس مدمجًا في صورة Docker وبالتالي مرئيًا لأي شخص يشغّل `docker history ai-app:latest`؟" ما إجابتك، وأي أمر ستشغّله الآن لإثبات ذلك؟

### الخطوة 6: التحقّق من فحص الصحة

```bash
# Inspect health check status
docker inspect --format='{{.State.Health.Status}}' $(docker ps -q --filter ancestor=ai-app:latest)
# Expected: healthy  (after ~40 seconds from start)

# View health check logs
docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' \
  $(docker ps -q --filter ancestor=ai-app:latest)
```

تعليمة `HEALTHCHECK` تخبر بيئة تشغيل حاويات Docker بأن تنبض دوريًا على `/health`. ومنسّقات (orchestrators) مثل Kubernetes وECS تستخدم هذه الإشارة لتقرّر متى تكون الحاوية جاهزة لاستقبال الحركة ومتى تعيد تشغيلها. بدون فحص صحة، الحاوية التي تبدأ ثم تخطئ فورًا عند أول استيراد تبدو سليمة للمجدوِل (scheduler).

---

## الاستخدام

بعد بناء الصورة، تغطّي أوامر `docker` الثلاثة هذه دورة الحياة التشغيلية الكاملة:

```bash
# Build: creates image from Dockerfile
docker build -t ai-app:v1.0 -f code/Dockerfile code/

# Run: starts container from image
docker run -d -p 8000:8000 \
  --name ai-app \
  --env ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  --env MODEL=claude-3-5-haiku-20241022 \
  ai-app:v1.0

# Inspect: checks container state including health
docker inspect ai-app
```

في خطّ أنابيب نشر حقيقي، يندرج هذا الـ Dockerfile مباشرة في تدفّق عمل CI/CD. GitHub Actions، مثلًا:

```yaml
# .github/workflows/build.yml
- name: Build and push
  uses: docker/build-push-action@v5
  with:
    context: ./code
    file: ./code/Dockerfile
    push: true
    tags: ghcr.io/org/ai-app:${{ github.sha }}
```

الفرق الجوهري بين Docker المحلي والإنتاج: تأتي الأسرار من مخزن أسرار الـ CI (`secrets.ANTHROPIC_API_KEY`)، لا من الـ Dockerfile أبدًا. والصورة نفسها خالية من الأسرار ويمكن تخزينها في سجلّ (registry) عام دون انكشاف.

> **نقلة في المنظور:** يقترح فريقك استخدام `ENV ANTHROPIC_API_KEY=sk-...` في الـ Dockerfile لـ "تبسيط التطوير المحلي". ويقول مديرك: "إنها للتطوير فقط، وصورة الإنتاج مختلفة." ما الخطر الملموس لتلك السياسة، وما البديل الأكثر أمانًا الذي يحقّق الراحة نفسها؟

---

## التسليم

المخرَج القابل لإعادة الاستخدام لهذا الدرس هو `outputs/skill-ai-app-dockerfile.md`: قالب Dockerfile جاهز للإنتاج بتعليقات تشرح كل قرار. أدرِجه في أي خدمة AI جديدة بـ Python.

لاستخدامه:
1. انسخ `code/Dockerfile` و`code/requirements.txt` و`code/.dockerignore` إلى مجلّد خدمتك.
2. استبدل `main.py` بنقطة دخول تطبيقك.
3. اضبط مسار `HEALTHCHECK` ليطابق نقطة نهاية الصحة في خدمتك.
4. شغّل `docker build -t your-service:latest .` وتحقّق من أن `docker inspect` يُظهر `healthy`.

---

## التقييم

**التحقق 1: كفاءة كاش الطبقات.**
أجرِ تغييرًا بسيطًا على `main.py` (أضف تعليقًا) وأعِد البناء. ينبغي أن تُظهر المخرجات `CACHED` للطبقات 1-4 وتعيد بناء الطبقتين 5-6 فقط. إذا رأيت pip يعيد تثبيت الحزم بعد تغيير في الكود فقط، فترتيب الطبقات خاطئ.

```bash
docker build -t ai-app:test -f code/Dockerfile code/ 2>&1 | grep -E "CACHED|RUN pip"
```

**التحقق 2: لا أسرار في الصورة.**
شغّل `docker history ai-app:latest` و`docker inspect ai-app:latest`. لا ينبغي أن يحوي أيٌّ منهما أي نصّ يبدو كمفتاح API. تحقّق من أن كتلة `ENV` في إعداد الصورة تحوي قيمًا غير سرّية فقط.

```bash
docker history ai-app:latest
docker inspect ai-app:latest | grep -i "api_key\|secret\|token"
# Should return nothing
```

**التحقق 3: مستخدم غير الجذر.**
تحقّق من أن العملية المشغَّلة ليست الجذر (root).

```bash
docker exec ai-app whoami
# Expected: appuser
```

**التحقق 4: حجم الصورة.**
قارن البناء متعدّد المراحل ببناء أحادي المرحلة ساذج (دون `AS build`، كل شيء في مرحلة واحدة). ينبغي أن تكون الصورة متعدّدة المراحل أصغر بنسبة 30% على الأقل.

```bash
docker images ai-app
```
