# أساسيات الـ Prompt

> الـ prompts شيفرة. التعليمات الغامضة تنتج مخرجات غامضة لأن النموذج يملأ الفجوات بتصوراته المسبقة (priors).

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** الدرس 01 (تشريح الطلب)، `pip install anthropic`
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- تطبيق مبادئ الـ prompt الستة الأساسية: تعريف المهمة، الدور/الشخصية، صيغة المخرجات، الأمثلة، القيود، والنبرة
- تشخيص لماذا يُنتج prompt غامض مخرجات غير متسقة
- تحسين prompt بشكل تكراري بتطبيق كل مبدأ بالتسلسل
- بناء صنف PromptTemplate قابل لإعادة الاستخدام باستخدام f-strings
- تقييم جودة الـ prompt بقياس اتساق المخرجات عبر عدة تشغيلات

---

## THE PROBLEM

تكتب prompt، يعمل في الغالب، فتُطلقه. بعد ثلاثة أسابيع، يُبلّغ المستخدمون أن استجابة من كل 10 مُهيّأة بصيغة خاطئة، أو طويلة جدًا، أو بلغة خاطئة، أو ببساطة "ليست في محلها". تُعدّل الـ prompt، تعيد النشر، يتحسن لأسبوع، ثم ينكسر شيء آخر.

المشكلة الكامنة: كتبت prompt بالطريقة التي تكتب بها رسالة Slack. عفوية، ناقصة، تعتمد على المتلقي ليملأ الفجوات. مع زميل، ينجح ذلك لأنه يشاركك السياق. مع نموذج لغوي، تُملأ الفجوات بتصورات إحصائية مسبقة من بيانات التدريب، وقد تطابق أو لا تطابق ما قصدته.

الـ prompts شيفرة. لها مهمة تؤديها، ولها مدخلات ومخرجات، وتحتاج أن تكون صريحة بشأن شكل النجاح. الـ prompt الذي يعمل 80% من الوقت ليس prompt على وشك أن ينجح. بل هو prompt مكسور 20% من الوقت.

---

## THE CONCEPT

### مبادئ الـ Prompt الستة

ست خصائص تميّز بشكل موثوق الـ prompts التي تنتج مخرجات متسقة بجودة إنتاجية عن تلك التي تنتج نتائج متغيرة:

```
1. TASK DEFINITION   What exactly is the model supposed to do?
                     Be specific. "Summarize" is not a task definition.
                     "Summarize in 3 bullet points, one sentence each" is.

2. ROLE / PERSONA    Who is the model in this context?
                     Roles activate relevant training patterns and
                     set implicit quality bars.

3. OUTPUT FORMAT     What does the output look like structurally?
                     JSON, markdown, plain text, list? Specify it.
                     Include structure, length, and any required fields.

4. EXAMPLES          One or two examples of good outputs.
                     The most reliable way to communicate format and style.
                     Description alone is ambiguous. Examples are concrete.

5. CONSTRAINTS       What should the model NOT do?
                     Negative constraints often matter more than positive ones.
                     "Do not include disclaimers" eliminates a common failure mode.

6. TONE              Formal, casual, technical, plain language?
                     Tone affects vocabulary, sentence structure, and assumed
                     reader expertise. Specify it or get inconsistency.
```

### تشريح الـ Prompt: قبل وبعد

```
BEFORE (vague):
┌──────────────────────────────────────────────────────┐
│ "Summarize this article."                            │
│                                                      │
│ Problems:                                            │
│  - Length undefined (3 words? 3 paragraphs?)         │
│  - Format undefined (prose? bullets? headline?)      │
│  - Audience undefined (expert? general public?)      │
│  - Tone undefined (formal? casual?)                  │
│  - No constraints (include opinions? caveats?)       │
└──────────────────────────────────────────────────────┘

AFTER (explicit):
┌──────────────────────────────────────────────────────┐
│ ROLE:    "You are an editor writing for a general    │
│           tech audience."                            │
│                                                      │
│ TASK:    "Summarize the article below in exactly     │
│           3 bullet points."                          │
│                                                      │
│ FORMAT:  "Each bullet: 1 sentence, under 20 words.  │
│           Start with a strong verb."                 │
│                                                      │
│ EXAMPLE: "- Reveals that X causes Y in production." │
│                                                      │
│ CONSTRAINT: "No marketing language. No caveats."    │
│                                                      │
│ TONE:    "Direct and factual."                       │
└──────────────────────────────────────────────────────┘
```

الـ prompt في حالة "بعد" يستغرق 30 ثانية إضافية في الكتابة وينتج مخرجات متسقة لا تحتاج إلى أي تنظيف.

---

## BUILD IT

### التحسين التكراري للـ Prompt

أفضل طريقة لاستيعاب هذه المبادئ هي أن تبدأ بـ prompt مكسور وتصلحه خطوة بخطوة. يجب أن تكون كل خطوة قابلة للقياس.

**المهمة:** استخراج بنود العمل (action items) من نص اجتماع. بسيطة بما يكفي للتقييم السريع، ومعقّدة بما يكفي لإظهار التباين.

**Step 0: The bad prompt.**

```python
import anthropic

client = anthropic.Anthropic()

TRANSCRIPT = """
Alex: We need to fix the login bug before the demo on Friday.
Sam: I'll look into it today. Also the dashboard is slow, we should profile it.
Alex: Good idea. Can you also update the README with the new setup steps?
Sam: Sure. Who's handling the client call at 3pm tomorrow?
Alex: I'll take it. Jordan should send the invoice by end of week.
"""

def run_prompt(prompt: str, transcript: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": f"{prompt}\n\n{transcript}"}]
    )
    return response.content[0].text

bad_prompt = "Extract the action items from this meeting."
print("BAD PROMPT OUTPUT:")
print(run_prompt(bad_prompt, TRANSCRIPT))
```

شغّل هذا 3 مرات. ستحصل على صيغ مختلفة، ومستويات تفصيل مختلفة، أحيانًا فقرة، وأحيانًا قائمة، أحيانًا بأسماء المكلَّفين، وأحيانًا بدونها.

**Step 1: Add task definition.**

```python
prompt_v1 = """Extract all action items from the meeting transcript below.
An action item is a task that a specific person agreed to do."""
```

أفضل. الآن أضِف الصيغة.

**Step 2: Add output format.**

```python
prompt_v2 = """Extract all action items from the meeting transcript below.
An action item is a task that a specific person agreed to do.

Output as a numbered list. Each item: [PERSON]: [TASK] by [DEADLINE or 'no deadline']."""
```

**Step 3: Add role and constraint.**

```python
prompt_v3 = """You are a project manager's assistant. Your job is to extract
clear action items from meeting transcripts.

Extract all action items from the transcript below. An action item is a
task that a specific person explicitly agreed to do.

Output as a numbered list. Each item: [PERSON]: [TASK] by [DEADLINE or 'no deadline'].
Do not include items that were discussed but not assigned.
Do not add commentary or explanation."""
```

**Step 4: Add an example.**

```python
prompt_v4 = """You are a project manager's assistant. Your job is to extract
clear action items from meeting transcripts.

Extract all action items from the transcript below. An action item is a
task that a specific person explicitly agreed to do.

Output as a numbered list. Each item: [PERSON]: [TASK] by [DEADLINE or 'no deadline'].
Do not include items that were discussed but not assigned.
Do not add commentary or explanation.

Example output format:
1. Sam: Fix the login bug by Friday
2. Alex: Schedule client kickoff call by no deadline

Transcript:
"""
```

> **اختبار من الواقع:** تطبّق المبادئ الستة جميعها على prompt، لكن المخرجات ما زالت تتباين مرة من كل 10. تبدو الصيغة صحيحة 9/10 مرات لكن التشغيل العاشر يُسقِط حقل الموعد النهائي (deadline). ما الفجوة المتبقية الأرجح، وكيف ستسدّها؟

الفجوة الأرجح هي أن القيد مذكور كتعليمة إيجابية ("include deadline") لا سلبية ("never omit the deadline field"). يتعامل النموذج مع المعلومة المفقودة بطريقة تختلف عن المعلومة المحظورة. أضِف: "If no deadline is mentioned, always write 'no deadline'. Never leave the deadline field blank." المعالجة الصريحة للحالة الحدّية تزيل التباين الذي لا يظهر إلا تحت شروط مدخلات معيّنة.

---

## USE IT

### PromptTemplate: التعامل مع الـ Prompts كأنها شيفرة

بمجرد أن يكون لديك prompt يعمل، تحتاج إلى تحويله إلى قالب ذي معاملات (parameterize) ليُعاد استخدامه مع مدخلات مختلفة. أبسط نسخة هي f-string. النسخة الإنتاجية صنف يتحقق من المدخلات ويصيّر القالب.

```python
class PromptTemplate:
    """
    A simple prompt template that validates required variables before rendering.
    Treats prompts as parameterized code artifacts, not ad-hoc strings.
    """

    def __init__(self, template: str, required_vars: list[str]):
        self.template = template
        self.required_vars = required_vars

    def render(self, **kwargs) -> str:
        missing = [v for v in self.required_vars if v not in kwargs]
        if missing:
            raise ValueError(f"Missing required variables: {missing}")
        return self.template.format(**kwargs)


# Define the template once, reuse with different inputs
action_item_template = PromptTemplate(
    template="""You are a project manager's assistant. Extract action items from meeting transcripts.

An action item is a task that a specific person explicitly agreed to do.

Output as a numbered list. Format: [PERSON]: [TASK] by [DEADLINE or 'no deadline'].
Do not include discussed-but-unassigned items. Do not add commentary.

Example:
1. Sam: Fix the login bug by Friday
2. Alex: Schedule client call by no deadline

Transcript:
{transcript}

Tone: {tone}""",
    required_vars=["transcript", "tone"]
)

# Render and run
prompt = action_item_template.render(
    transcript=TRANSCRIPT,
    tone="direct and factual"
)

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=512,
    messages=[{"role": "user", "content": prompt}]
)
print(response.content[0].text)
```

يمنحك نهج القوالب التحكم بالإصدارات (القوالب سلاسل يمكنك تخزينها)، وقابلية الاختبار (render() دالة نقية)، والمعاملة بالمتغيرات (تبديل المدخلات دون المساس بالمنطق).

> **نقلة في المنظور:** يقول زميل "أنا فقط أضع الـ prompts بشكل ثابت (hardcode) في استدعاء الـ API. تبدو القوالب هندسة مفرطة." متى تبدأ هذه العقلية بالتسبب في مشكلات حقيقية في الإنتاج؟

تبدأ بالتسبب في المشكلات لحظة وجود أكثر من موضع يُستخدم فيه الـ prompt، أو أكثر من شخص قد يعدّله. الـ prompts الثابتة تُنسخ وتتشعّب بصمت. حين يحتاج prompt إلى تغيير (يتبدّل سلوك النموذج، أو تتغير المتطلبات، أو يُكتشف خطأ)، عليك أن تجد كل نسخة. تجعل القوالب الـ prompt مصدرًا واحدًا للحقيقة بواجهة مُعرَّفة. كلفة "الهندسة المفرطة" هي 10 أسطر شيفرة. كلفة عدم فعلها تُتعقّب عبر تذاكر الدعم بعد ستة أشهر.

---

## SHIP IT

الأثر (artifact) الذي ينتجه هذا الدرس هو قائمة تحقق لجودة الـ prompt. انظر `outputs/prompt-fundamentals-checklist.md`.

تمرّ قائمة التحقق على المبادئ الستة جميعها بأسئلة تشخيصية لكل منها. استخدمها أثناء تأليف الـ prompt ومراجعة الشيفرة لاكتشاف الفجوات قبل أن تصبح أخطاء إنتاجية.

---

## EVALUATE IT

جودة الـ prompt قابلة للقياس. المقياس هو اتساق المخرجات: بإعطاء المهمة نفسها مع بيانات مدخلات مختلفة، هل تتبع المخرجات البنية نفسها في كل مرة؟

**Consistency test.** شغّل prompt النهائي على 10 نصوص اجتماعات مختلفة (أو ولّد نصوصًا اصطناعية). قيّم كل مخرج: هل يطابق الصيغة المحددة؟ هل يتضمن كل الحقول المطلوبة؟ الـ prompt المكتوب جيدًا ينبغي أن يصيب الصيغة بشكل صحيح في 10/10 تشغيلات. إن كنت عند 8/10، فجِد العطلين وحدِّد أي مبدأ يخالفانه.

**Ablation test.** خذ أفضل prompt لديك وأزِل مبدأً واحدًا في كل مرة. شغّل كل نسخة مُجزّأة 5 مرات. قِس مقدار زيادة التباين. هذا يخبرك أي المبادئ يقوم بأكبر دور لمهمتك المحددة. استنتاج شائع: صيغة المخرجات والقيود تفسّران معظم الاستقرار.

**New input stress test.** أعطِ prompt مدخلات مختلفة اختلافًا كبيرًا عما صمّمته من أجله: نص قصير بشكل غير معتاد، نص بلا مكلَّفين واضحين، نص في مجال مختلف. أين ينكسر؟ تكشف الأعطال عن قيود مفقودة أو تعريف مهمة مُفرِط في التحديد.

**Template rendering coverage.** اختبر صنف PromptTemplate باختبارات وحدة: متغير مطلوب مفقود يرفع ValueError، وجود كل المتغيرات يُصيّر دون خطأ، المخرج المُصيّر يحتوي على قيم المتغيرات في المواضع الصحيحة. أخطاء القوالب أخطاء منطقية، لا أخطاء prompt.
