# النشر (Deploying): المسار المُدار والمسار الحاوي (Container)

> لخدمة ذكاء اصطناعي دون 10 آلاف طلب/يوم، تكلّف المنصّة المُدارة (managed platform) ساعاتِ هندسةٍ أقل ممّا توفّره من بنية تحتية عند تشغيل حاوياتك (containers) بنفسك.

**النوع:** تعلّم
**اللغات:** Python
**المتطلبات:** 05-docker-image-ai-app، 06-config-and-secrets
**الوقت:** ~60 دقيقة
**أهداف التعلّم:**
- التمييز بين المنصّات المُدارة (Railway، Render، Fly.io) ومنصّات الحاويات (AWS ECS، GCP Cloud Run)
- نشر خدمة FastAPI من المرحلة 06 على Railway أو Render عبر الـCLI
- إعداد فحوصات الصحة (health checks) ومتغيّرات البيئة (environment variables) والوصول إلى السجلات (logs)
- تطبيق إطار قرار لاختيار مسار النشر المناسب لخدمة معيّنة

---

## الشعار

**اوصل إلى رابط يعمل أولًا. حسّن البنية التحتية لاحقًا، إن احتجت أصلًا.**

---

## المشكلة

لديك خدمة FastAPI تعمل وتغلّف Claude. لها Dockerfile. تعمل محليًا. والآن تحتاج إلى نشرها كي يستخدمها آخرون.

تفتح وثائق AWS. وبعد ثلاث ساعات تكون قد قرأت عن VPCs، وأدوار IAM، وتعريفات مهام ECS، ومجموعات الهدف في ALB، ومجموعات الأمان. ولم تنشر أيّ شيء بعد. خدمتك ما زالت تعمل على حاسوبك المحمول فقط.

الخطأ الجوهري هو حلّ المشكلة الخطأ. المشكلة ليست "كيف أصبح مهندس بنية تحتية". المشكلة هي "كيف أحصل على رابط يقبل طلبات HTTP ويمرّرها إلى تطبيق FastAPI لديّ". تحلّ المنصّة المُدارة هذه المشكلة في أقل من 15 دقيقة.

ثمة فئتان للنشر لخدمات الذكاء الاصطناعي. المنصّات المُدارة (Railway، Render، Fly.io) تأخذ Dockerfile لديك، وتشغّله، وتعطيك رابطًا، وتتولى TLS، وتعيد تشغيل الحاويات المتعطّلة، وتكشف السجلات. تدفع لكل ثانية من المعالج (CPU) والذاكرة (RAM). لا تضبط الشبكات. ومنصّات الحاويات (AWS ECS/Fargate، GCP Cloud Run) تعطيك تحكّمًا أكبر: VPCs مخصّصة، وIAM دقيق، وسياسات توسّع تلقائي (autoscaling)، وتوجيه متعدد المناطق. تكون مناسبة حين تصطدم بحدود لا تستطيع المنصّات المُدارة حلّها.

معظم خدمات الذكاء الاصطناعي لا تصطدم بتلك الحدود أبدًا. شجرة القرار أبسط ممّا تجعله مدوّنات البنية التحتية يبدو عليه.

---

## المفهوم

### المُدار مقابل الحاوي: شجرة القرار

```
Your AI service needs to be deployed.
           |
           v
Is traffic > 10k requests/day OR do you have
a dedicated DevOps/platform team?
           |
          NO ----> Use a managed platform (Railway / Render / Fly.io)
           |         - Dockerfile in, URL out
           |         - No VPC, no IAM, no ALB config
           |         - ~$5-50/month for typical AI service
           |         - Time to working URL: 15-30 minutes
           |
          YES
           |
           v
Do you need custom networking (VPC, private
subnets), compliance controls, or multi-region?
           |
          NO ----> GCP Cloud Run or AWS App Runner
           |         - Serverless containers, scale to zero
           |         - More config than managed, less than ECS
           |         - Good for bursty traffic patterns
           |
          YES ----> AWS ECS/Fargate or GCP GKE
                     - Full control, full responsibility
                     - Team needs infra expertise
                     - 2-4 hours to first deploy
```

### مقارنة المنصّات

```
+------------------+----------+-----------+----------+----------+
|                  | Railway  | Render    | Fly.io   | Cloud Run|
+------------------+----------+-----------+----------+----------+
| Dockerfile       | YES      | YES       | YES      | YES      |
| Time to URL      | 10 min   | 15 min    | 20 min   | 30 min   |
| Scale to zero    | YES      | YES       | NO       | YES      |
| Persistent disk  | add-on   | YES       | YES      | NO       |
| Free tier        | trial    | YES       | trial    | YES      |
| CLI deploy       | railway  | render    | flyctl   | gcloud   |
| Custom domains   | YES      | YES       | YES      | YES      |
| Best for         | demos    | APIs      | latency  | GCP stack|
+------------------+----------+-----------+----------+----------+
```

### ما يحتاجه النشر فعليًا

كل نشر لخدمة FastAPI من المرحلة 06 يتطلب أربعة أشياء:

1. ملف Dockerfile يبني التطبيق ويشغّله (الدرس 05)
2. متغيّرات بيئة (ANTHROPIC_API_KEY كحدّ أدنى)
3. نقطة فحص صحة (`GET /health` تُرجِع 200)
4. منفذ توجّه إليه المنصّة الترافيك (الافتراضي: 8000)

```
Platform reads Dockerfile
         |
         v
Builds container image
         |
         v
Injects env vars from dashboard / CLI
         |
         v
Starts container, maps port 8000 to HTTPS URL
         |
         v
Health check: GET /health -> 200 OK
         |
         v
Traffic routed to your URL
```

---

## البناء

### الخطوة 1: أضف فحص صحة إلى تطبيق FastAPI لديك

كل منصّة ترسل نبضة (ping) إلى نقطة الصحة لتقرّر إن كانت حاويتك جاهزة للترافيك. بدونها تفشل عمليات النشر بصمت.

```python
# Add this to your main.py (from lesson 02)
@app.get("/health")
async def health() -> dict[str, str]:
    """Health check. Platforms call this to verify the container is running."""
    return {"status": "ok"}
```

### الخطوة 2: تحقّق من Dockerfile لديك

```dockerfile
# Dockerfile (from lesson 05, reproduced for reference)
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# PORT env var is set by most managed platforms (default 8000)
ENV PORT=8000
EXPOSE 8000

# Use sh -c so $PORT is expanded at runtime
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
```

```txt
# requirements.txt
fastapi
uvicorn[standard]
anthropic
pydantic
python-dotenv
```

### الخطوة 3: النشر على Railway

Railway هو أسرع مسار من Dockerfile إلى رابط.

```bash
# Install Railway CLI
curl -fsSL https://railway.app/install.sh | sh

# Log in
railway login

# Initialize a new project in your service directory
railway init

# Set your secret env vars (never in Dockerfile or code)
railway variables set ANTHROPIC_API_KEY=sk-ant-...

# Deploy
railway up
# Railway builds your Dockerfile, starts the container, prints the URL.
# Typical time: 2-4 minutes.
```

يكتشف Railway ملف Dockerfile لديك تلقائيًا. يضبط `PORT` تلقائيًا ويوجّه ترافيك HTTPS إليه.

### الخطوة 4: النشر على Render (بديل)

```bash
# Install Render CLI
npm install -g @render-com/cli
# or download from https://render.com/docs/cli

render login

# Create a render.yaml in your project root:
```

```yaml
# render.yaml
services:
  - type: web
    name: ai-service
    runtime: docker
    healthCheckPath: /health
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false   # Render will prompt you to set this securely
```

```bash
render deploy
# Render reads render.yaml, builds the Docker image, deploys it.
```

> **اختبار من الواقع:** يبني كلٌّ من Railway وRender صورة Docker لديك على خوادمهما. ويعني هذا أن `ANTHROPIC_API_KEY` لديك لا يكون أبدًا في طبقة الصورة (image layer). تحقنه المنصّة كمتغيّر بيئة وقت التشغيل. وإن رأيت يومًا مفتاح API مكتوبًا بشكل ثابت (hard-coded) في Dockerfile أو مُودَعًا في git، فهو مكشوف ويجب تدويره (rotate) فورًا. تفرض المنصّات المُدارة هذا النمط بحكم تصميمها.

### الخطوة 5: قراءة السجلات (Logs)

السجلات هي أداة تصحيح الأخطاء (debug) الأساسية للخدمات المنشورة. كل منصّة تكشفها عبر الـCLI ولوحة التحكم.

```bash
# Railway: stream logs from the running deployment
railway logs

# Render: stream logs
render logs --service ai-service

# GCP Cloud Run (for later)
gcloud run services logs read ai-service --region us-central1 --tail 50
```

ابحث عن:
- `Application startup complete` من uvicorn (الخدمة تعمل)
- أسطر `GET /health 200` (فحوصات صحة المنصّة ناجحة)
- أسطر `4xx` (أخطاء العميل: إدخال خاطئ، إخفاقات مصادقة)
- أسطر `5xx` (أخطاء الخادم: استثناءات غير معالَجة، أخطاء واجهة النموذج)

---

## الاستخدام

كلٌّ من `railway up` و`render deploy` يشغّل عملية متعددة الخطوات كان يمكنك تنفيذها يدويًا بـ`docker build` و`docker push` وأمر تشغيل حاوية. تختزل المنصّة المُدارة ذلك في أمر واحد وتتولى الباقي.

```bash
# What railway up does under the hood:
# 1. Sends your project files to Railway's build servers
# 2. Runs: docker build -t <your-project>:<hash> .
# 3. Pushes the image to Railway's internal registry
# 4. Creates a new deployment with the image
# 5. Injects env vars from the dashboard/CLI
# 6. Starts the container, waits for health check to pass
# 7. Routes traffic from your-project.railway.app to the container
# 8. Keeps the old container running until the new one is healthy (zero-downtime)

# You run one command. The platform runs those 8 steps.
```

التدفّق نفسه على AWS ECS يتطلب منك: إنشاء مستودع ECR، وإعداد دور IAM بصلاحيات الدفع (push)، وبناء الصورة ودفعها بنفسك، وإنشاء ملف JSON لتعريف المهمة، وإنشاء أو تحديث خدمة ECS، وانتظار استقرار الخدمة، وفحص صحة مجموعة الهدف في لوحة ALB.

> **نقلة في المنظور:** المنصّات المُدارة ليست اختصارًا لمن لا يعرف AWS. بل هي الأداة الصحيحة لخدمة لا تحتاج تحكّمًا بمستوى AWS. المهندسون الذين "يتخرّجون" من Railway إلى ECS كثيرًا ما يكتشفون أنهم ينفقون 30% من وقتهم على بنية تحتية كان Railway يتولاها تلقائيًا. السؤال ليس "هل Railway بنية تحتية حقيقية". السؤال هو "هل تحتاج خدمتي ما يوفّره ECS". لمعظم خدمات الذكاء الاصطناعي، الجواب لا.

---

## التسليم

المنتَج القابل لإعادة الاستخدام هو `outputs/skill-deployment-decision-guide.md`. يحتوي على:
- شجرة قرار المُدار مقابل الحاوي
- جدول مقارنة المنصّات
- قوائم تحقّق نشر Railway وRender
- قائمة تحقّق متغيّرات البيئة لخدمات الذكاء الاصطناعي
- أنماط السجلات التي ينبغي مراقبتها

---

## التقييم

**الاختبار 1: فحص الصحة.** بعد النشر، نفّذ `curl https://your-service.railway.app/health`. تحقّق من HTTP 200 ومن `{"status": "ok"}`. إن أظهرت المنصّة أن النشر فشل، فهذا أول ما تفحصه.

**الاختبار 2: نقطة التوليد.** نفّذ `curl -X POST https://your-service.railway.app/generate -H 'Content-Type: application/json' -d '{"prompt": "Say hello."}'`. تحقّق من استجابة JSON صالحة فيها حقل `text`.

**الاختبار 3: الأسرار ليست في الصورة.** شغّل `railway run printenv | grep ANTHROPIC`. تحقّق من ظهور المفتاح كمتغيّر بيئة، لا كوسيط بناء (build arg) أو ملف. لا تُودِع مفاتيح API في git أبدًا.

**الاختبار 4: بثّ السجلات.** أثناء تنفيذ curl على نقطة التوليد، شغّل `railway logs` في طرفية أخرى. تحقّق من رؤيتك سجلات وصول فيها مسار الطلب وطريقته (method) ورمز حالته.

**الاختبار 5: التعافي من الأعطال.** عيّن `ANTHROPIC_API_KEY` مؤقتًا إلى قيمة غير صالحة. أرسل طلبًا. تحقّق من أن الخدمة تُرجِع خطأ 500 وأن المنصّة تعيد تشغيل الحاوية (أو تُبقيها تعمل إن كان الخطأ معالَجًا). افحص السجلات لتفاصيل الخطأ.

**الاختبار 6: تقدير التكلفة.** بعد 24 ساعة من الاستخدام الخفيف (بضعة طلبات)، افحص لوحة استخدام Railway أو Render. احسب التكلفة الشهرية المتوقّعة. قارنها بتكلفة تشغيل ما يكافئها على EC2 t3.micro ($8.35/شهر). ضع في الحسبان الوقت الموفَّر في إدارة البنية التحتية.
