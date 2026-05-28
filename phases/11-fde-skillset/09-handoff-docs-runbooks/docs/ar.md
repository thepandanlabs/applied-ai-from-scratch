# التسليم: الوثائق، الـ runbooks، تدريب الفريق

> التسليم الذي تجيب فيه عن أسئلة بعده هو تسليم فاشل.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 11-07 (بيئة العميل الفوضوية)، 06-01 (أساسيات التسليم)
**الوقت:** ~60 دقيقة
**المرحلة:** 11 · مهارات الـ FDE

---

## أهداف التعلّم

- سرد الوثائق الأربع في حزمة تسليم (handoff package) كاملة وشرح ما يغطّيه كل منها
- التعرّف على الإخفاقات الثلاثة الأكثر شيوعًا التي سيواجهها فريق العميل دون runbook
- بناء HandoffPackageGenerator يصوغ الوثائق الأربع كلها من قالب مشروع
- إجراء فحص اكتمال (completeness check) على حزمة تسليم مُولَّدة
- قياس ما إذا كان التسليم قد نجح: هل يستطيع الفريق تشخيص الإخفاقات الثلاثة الأكثر شيوعًا دون الاتصال بك؟

---

## المشكلة

بنيت نظام ذكاء اصطناعي متينًا. تم نشره، وقبله العميل، والارتباط يقترب من النهاية. تقضي اليومين الأخيرين في كتابة وثيقة تسليم: ملف Word فيه نظرة عامة على النظام، وبعض لقطات الشاشة، وقسم اسمه "FAQ".

بعد ثلاثة أسابيع، يتصل العميل. توقّفت مهمّتهم المجدولة لإعادة استيعاب الوثائق عن العمل. لا أحد في فريقهم يعرف كيف يعيد تشغيلها. الشخص الذي يعرف النظام هو أنت، وأنت الآن في ارتباط مختلف.

هذه ليست مشكلة دعم عملاء. إنها إخفاق تسليم. لم يغطِّ الـ runbook المشكلة التشغيلية الأكثر شيوعًا. لم يُدرَّب الفريق على تشخيصها. ومسار التصعيد كان يشير إلى قناة Slack لم تعد تراقبها.

التسليم ليس وثيقة. إنه نقل للملكية التشغيلية. مقياس النجاح ثنائي: هل يستطيع فريق العميل تشغيل النظام وتشخيصه وإصلاحه دونك؟ إن لم يكن كذلك، فالتسليم غير مكتمل بغضّ النظر عن عدد صفحات الوثيقة.

حزمة التسليم رباعية الأجزاء موجودة لسدّ هذه الفجوة بشكل منهجي.

---

## المفهوم

### حزمة التسليم رباعية الأجزاء

```
DOCUMENT 1: SYSTEM OVERVIEW
  What it does, what it does not do, what it needs to run.
  Audience: anyone who needs to understand the system at a high level.
  Key sections:
    - Purpose and scope (one paragraph)
    - What the system does NOT do (explicit)
    - Dependencies: external APIs, internal systems, data sources
    - Infrastructure: where it runs, what it costs per month
    - Owner after handoff: name, role, contact

DOCUMENT 2: OPERATIONAL RUNBOOK
  How to run it day-to-day.
  Audience: the person who will operate the system.
  Key sections:
    - How to start, stop, and restart the system
    - Configuration: all environment variables, where they are set
    - Scheduled jobs: what they do, when they run, how to check if they ran
    - The 5 most common failures and how to fix each one
    - How to check system health without reading code

DOCUMENT 3: PROMPT AND MODEL CHANGE GUIDE
  How to update the AI components safely.
  Audience: the engineer who will maintain the system.
  Key sections:
    - How to update a prompt (the safe way)
    - How to run the eval set before deploying a change
    - How to interpret eval results and decide whether to deploy
    - How to roll back if a prompt change degrades quality
    - When to contact the original team vs. handle it yourself

DOCUMENT 4: ESCALATION PATH
  What to try first, when to escalate, who to contact.
  Audience: everyone on the customer team.
  Key sections:
    - Level 1: things to try before escalating (restart, check logs, check config)
    - Level 2: when to involve the internal tech lead
    - Level 3: when to contact the original FDE team
    - Contact information: email, Slack, response time expectations
    - What to include in an escalation message (symptoms, logs, what you tried)
```

### الوثائق الأربع وجمهور كل منها

```
+--------------------------+---------------------------+---------------------------+
| DOCUMENT                 | PRIMARY AUDIENCE          | ANSWERS THE QUESTION      |
+--------------------------+---------------------------+---------------------------+
| 1. System Overview       | Anyone new to the system  | What does this do?        |
+--------------------------+---------------------------+---------------------------+
| 2. Operational Runbook   | The system operator       | How do I run and fix it?  |
+--------------------------+---------------------------+---------------------------+
| 3. Prompt Change Guide   | The maintaining engineer  | How do I update the AI?   |
+--------------------------+---------------------------+---------------------------+
| 4. Escalation Path       | Everyone                  | Who do I call and when?   |
+--------------------------+---------------------------+---------------------------+
```

### اختبار اكتمال التسليم

```
A handoff is complete if and only if:

  The customer team can diagnose and fix the 3 most common failures
  without calling you.

Determine the 3 most common failures from your own knowledge of the system.
For each one, verify:
  [x] The runbook has a section for this failure
  [x] The section names the symptom, the cause, and the fix
  [x] A team member who did not build the system can follow the fix

If any of the three fails this test, the runbook is incomplete.
```

### جلسة التسليم المباشرة

وثيقة تسليم تُرسَل بالبريد الإلكتروني تساوي 20% من جلسة تسليم مباشرة.

```
LIVE HANDOFF SESSION FORMAT (~2 hours)

1. Walk through each document (30 min)
   - You present, they ask questions
   - Do not read the doc out loud: explain the reasoning behind each section

2. They run it themselves, you watch (45 min)
   - They restart the system using only the runbook
   - They simulate the most common failure and fix it using only the runbook
   - You do not help unless they are completely stuck

3. Q&A and gap closing (30 min)
   - For every question that needed your help in step 2, update the runbook
   - That question is a runbook gap

4. Confirm escalation path (15 min)
   - Who do they call first? Second? When?
   - Confirm your availability and response time after handoff
```

---

## البناء

### الخطوة 1: الإعداد

```python
# pip install anthropic
# Set ANTHROPIC_API_KEY in environment

import argparse
import json
import os
import sys
from dataclasses import dataclass

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
```

### الخطوة 2: قالب المشروع

```python
@dataclass
class ProjectTemplate:
    project_name: str
    system_description: str          # what it does
    what_it_does_not_do: str         # explicit non-scope
    external_dependencies: str       # APIs, services
    infrastructure: str              # where it runs, estimated cost
    scheduled_jobs: str              # cron jobs, pipelines
    common_failures: str             # top 3-5 known failure modes
    prompt_files: str                # where prompts live
    eval_command: str                # how to run evals
    fde_contact: str                 # name and contact for escalation
    customer_tech_lead: str          # internal owner after handoff
```

### الخطوة 3: مولّدات الوثائق

```python
OVERVIEW_PROMPT = """You are writing the System Overview document for a customer handoff package.

Project: {project_name}
System description: {system_description}
What it does NOT do: {what_it_does_not_do}
External dependencies: {external_dependencies}
Infrastructure: {infrastructure}
Customer tech lead (owner after handoff): {customer_tech_lead}

Write a concise System Overview document. Use markdown. Include:
1. A one-paragraph purpose statement (what it does, for whom, why it matters)
2. A "What this system does NOT do" section with a bullet list
3. A "Dependencies" section listing all external systems and APIs
4. An "Infrastructure" section: where it runs, estimated monthly cost, scaling limits
5. An "Ownership" section: the customer tech lead's name, role, and what they own

Keep the whole document under 500 words. Use plain language. Avoid technical jargon where possible."""


RUNBOOK_PROMPT = """You are writing the Operational Runbook for a customer handoff package.

Project: {project_name}
Infrastructure: {infrastructure}
Scheduled jobs: {scheduled_jobs}
Common failures: {common_failures}
External dependencies: {external_dependencies}

Write a complete operational runbook. Use markdown. Include:
1. "Starting the system" - step-by-step instructions
2. "Stopping and restarting" - when and how
3. "Configuration" - what can be configured, where environment variables are set
4. "Scheduled jobs" - what each job does, when it runs, how to verify it ran
5. "Common failures" - for each failure mode listed, write: Symptom, Cause, Fix (step-by-step)
6. "Health checks" - how to verify the system is working without reading code

For the Common Failures section: make each fix self-contained. Assume the reader has not seen the codebase."""


PROMPT_CHANGE_GUIDE_PROMPT = """You are writing the Prompt and Model Change Guide for a customer handoff package.

Project: {project_name}
Prompt files location: {prompt_files}
Eval command: {eval_command}
Common failures: {common_failures}

Write a guide for safely updating AI components. Use markdown. Include:
1. "When to update prompts" - what symptoms indicate a prompt needs changing
2. "How to update a prompt safely" - step by step: edit, run eval, review results, deploy
3. "Running the eval set" - exact commands to run, what the output means
4. "Interpreting eval results" - what scores are acceptable vs. require investigation
5. "Rolling back a prompt change" - how to revert if quality drops
6. "When to contact the original team" - specific conditions that require expert help

Assume the reader is a competent engineer who did not build the original system."""


ESCALATION_PROMPT = """You are writing the Escalation Path document for a customer handoff package.

Project: {project_name}
Customer tech lead: {customer_tech_lead}
FDE contact: {fde_contact}
Common failures: {common_failures}

Write a clear escalation path document. Use markdown. Include:
1. "Level 1: Self-service" - things to try before involving anyone (restart, logs, config check)
2. "Level 2: Internal tech lead" - when to involve {customer_tech_lead} and what to bring to them
3. "Level 3: Original FDE team" - when to escalate externally, contact info for {fde_contact}, expected response time
4. "What to include in an escalation message" - a template with: system name, symptom, when it started, what you tried, relevant logs
5. "Contacts" - a table: person, role, contact method, response time expectation

Be concrete about when to escalate vs. when to keep troubleshooting independently."""


def generate_document(prompt_template: str, template: ProjectTemplate) -> str:
    """Generate a single handoff document using the given prompt template."""
    filled_prompt = prompt_template.format(
        project_name=template.project_name,
        system_description=template.system_description,
        what_it_does_not_do=template.what_it_does_not_do,
        external_dependencies=template.external_dependencies,
        infrastructure=template.infrastructure,
        scheduled_jobs=template.scheduled_jobs,
        common_failures=template.common_failures,
        prompt_files=template.prompt_files,
        eval_command=template.eval_command,
        fde_contact=template.fde_contact,
        customer_tech_lead=template.customer_tech_lead,
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": filled_prompt}],
    )

    return response.content[0].text.strip()
```

### الخطوة 4: فاحص الاكتمال

```python
COMPLETENESS_CHECK_PROMPT = """You are reviewing a handoff package for completeness.

Project: {project_name}
Known common failures: {common_failures}

Handoff package content:
{package_content}

Check the package against these requirements and return a JSON object:
{{
  "completeness_score": <integer 0-100>,
  "has_system_overview": true/false,
  "has_runbook": true/false,
  "has_prompt_change_guide": true/false,
  "has_escalation_path": true/false,
  "common_failures_covered": <integer: how many of the listed failures have runbook sections>,
  "missing_items": ["<item 1>", "<item 2>"],
  "gaps": ["<gap 1>", "<gap 2>"],
  "recommendation": "<one sentence: is this handoff package complete enough to transfer operational ownership?>"
}}"""


def check_completeness(template: ProjectTemplate, package: dict[str, str]) -> dict:
    """Run a completeness check on the handoff package."""
    package_content = "\n\n".join(
        f"=== {name.upper()} ===\n{content[:800]}..."
        for name, content in package.items()
    )

    prompt = COMPLETENESS_CHECK_PROMPT.format(
        project_name=template.project_name,
        common_failures=template.common_failures,
        package_content=package_content,
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    return json.loads(raw)
```

### الخطوة 5: المولّد الرئيسي للحزمة

```python
def generate_handoff_package(
    template: ProjectTemplate,
    output_dir: str,
) -> dict[str, str]:
    """Generate all four handoff documents and save them to output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    package = {}

    docs = [
        ("01-system-overview.md", OVERVIEW_PROMPT, "System Overview"),
        ("02-runbook.md", RUNBOOK_PROMPT, "Operational Runbook"),
        ("03-prompt-change-guide.md", PROMPT_CHANGE_GUIDE_PROMPT, "Prompt Change Guide"),
        ("04-escalation-path.md", ESCALATION_PROMPT, "Escalation Path"),
    ]

    for filename, prompt, name in docs:
        print(f"Generating: {name}...")
        content = generate_document(prompt, template)
        package[name] = content
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w") as f:
            f.write(f"# {name}\n\n")
            f.write(content)
        print(f"  Saved: {filepath}")

    return package
```

> **اختبار من الواقع:** يقول المدير التقني (CTO) لدى العميل: "لا نحتاج إلى كل هذا التوثيق. مهندسونا أذكياء، سيكتشفون الأمر بأنفسهم." كيف توضّح أن توثيق التسليم لا يتعلّق بذكاء المهندس، بل بتقليص زمن التشخيص من ساعات إلى دقائق حين يتعطّل شيء في الثانية صباحًا والفريق الأصلي غير متاح؟

---

## الاستخدام

شغّل المولّد على مشروع خدمة RAG نموذجي:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --demo --output ./handoff-package
```

يولّد هذا أربعة ملفات markdown في `./handoff-package/`. راجع كلًّا منها وتحقّق:
- هل تذكر النظرة العامة على النظام بوضوح ما لا يفعله النظام؟
- هل يغطّي الـ runbook الإخفاقات الثلاثة الشائعة المذكورة كلها؟
- هل يتضمّن دليل تغيير الموجّهات أوامر التقييم بدقّة؟
- هل يتضمّن مسار التصعيد توقّعات محدّدة لزمن الاستجابة؟

ثم شغّل فحص الاكتمال:

```bash
python main.py --demo --check
```

لاستخدامه مع مشروعك الخاص، أنشئ ملف `project.json` يطابق حقول قالب المشروع وشغّل:

```bash
python main.py --from-json project.json --output ./handoff-package
```

> **نقلة في المنظور:** يقول مهندس مبتدئ: "وثّقت كل شيء في تعليقات الشيفرة. الـ runbook زائد عن الحاجة." كيف توضّح الفرق بين توثيق الشيفرة (لمهندسين يعدّلون النظام) والتوثيق التشغيلي (لمهندسين يشغّلون النظام)، ولماذا يختلف الجمهور تمامًا؟

---

## التسليم

مُخرَج هذا الدرس هو `outputs/skill-handoff-package-template.md`. وهو قالب جاهز للتعبئة لكل الوثائق الأربع للتسليم يمكنك استخدامه في نهاية أي ارتباط.

الأداة القابلة للتشغيل هي `code/main.py`:

```bash
python main.py --demo --output ./handoff-package
python main.py --demo --check
```

---

## التقييم

**التحقق 1: اختبار الإخفاقات الثلاثة.**
بعد توليد الـ runbook، حدّد الإخفاقات الثلاثة الأكثر شيوعًا لمشروع العرض التوضيحي (فشل مهمّة الاستيعاب، انتهاء صلاحية مفتاح الـ API، تدهور جودة الموجّه). تحقّق من أن الـ runbook فيه قسم مخصّص لكلٍّ منها ببنية واضحة عرَض-سبب-إصلاح. إذا غاب أي إخفاق، فالتسليم غير مكتمل.

**التحقق 2: درجة الاكتمال.**
شغّل فاحص الاكتمال. درجة دون 75 تعني فجوات كبيرة. درجة فوق 90 تعني أن الحزمة جاهزة لجلسة تسليم مباشرة. إذا كانت درجتك دون 75، فراجع قائمة العناصر الناقصة وعالجها.

**التحقق 3: اختبار غير الباني.**
أعطِ الـ runbook المُولَّد لزميل لم يبنِ النظام. اطلب منه اتّباع تعليمات "إعادة تشغيل النظام" وإصلاح إخفاق محاكى واحد. إذا احتاج منك أكثر من 3 دقائق مساعدة، فهناك فجوة في الـ runbook.

**التحقق 4: هل يتضمّن مسار التصعيد معلومات اتصال ملموسة؟**
مسار تصعيد فيه "اتصل بفريق الـ FDE" بلا بريد إلكتروني، ولا زمن استجابة، ولا توجيه حول ما يجب تضمينه في الرسالة، ليس مسار تصعيد قابلًا للاستخدام. تحقّق من أن الوثيقة المُولَّدة فيها العناصر الأربعة كلها: مَن، وكيف، ومتى، وماذا تتضمّن.
