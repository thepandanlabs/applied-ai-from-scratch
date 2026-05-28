# بيئة التطوير: uv و Node و TypeScript

> أداة واحدة تغني عن أربع. البيئات القابلة للتكرار ليست ميزة كمالية؛ بل هي طريقتك لإطفاء حريق "يشتغل عندي" قبل أن يبدأ أصلًا.

**النوع:** بناء
**اللغات:** كلاهما (Python + TypeScript)
**المتطلبات:** لا يوجد
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- تثبيت uv وفهم سبب استبداله لكل من pyenv و pip و venv و pip-tools
- تهيئة مشروع Python باستخدام `uv init`، وإضافة الاعتماديات (dependencies)، وتشغيل السكربتات
- إعداد Node.js مع TypeScript وتثبيت Anthropic SDK
- التحقق من صحة بيئتك قبل كتابة أي كود متعلق بالـ AI

---

## المشكلة

تنضم إلى فريق يبني ميزة AI. المستودع (repo) يحتوي على ملف `requirements.txt`، وملف `.python-version`، وملف `setup.cfg`. تستنسخه (clone)، وتشغّل `pip install -r requirements.txt`، وفورًا تصطدم بتعارض: المشروع يحتاج Python 3.11، بينما Python على نظامك هو 3.12، وأحد الاعتماديات المثبّتة على إصدار قديم من `pydantic` يكسر اعتمادية أخرى. تقضي 90 دقيقة في تتبّع المشكلة قبل أن تكتب سطرًا واحدًا من منطق العمل.

هذا ليس سيناريو مفتعلًا. إنها التجربة الافتراضية حين تستخدم مشاريع Python حزمة الأدوات الأربع القديمة: pyenv لإدارة إصدار Python، و pip للتثبيت، و venv للعزل، و pip-tools لملفات الـ lockfile. أربع أدوات، وأربعة ملفات إعداد، وأربعة أنماط فشل، وصفر تنسيق بينها.

حزمة الـ AI الإنتاجية تحتاج أساسًا أفضل. كل درس في هذه الدورة يعتمد على uv (لـ Python) و Node/TypeScript. هذا الدرس يجهّز كليهما في أقل من 45 دقيقة، مع lockfile واستدعاء API أول تم التحقق منه كشرط للخروج.

---

## المفهوم

### الحزمة القديمة مقابل الحزمة الجديدة

الإعداد التقليدي لـ Python يستخدم أربع أدوات منفصلة لا تملك أي وعي أصيل ببعضها:

```
OLD STACK (4 tools, no coordination)
+----------+    +----------+    +---------+    +----------+
| pyenv    |    | venv     |    | pip     |    | pip-tools|
| (Python  |    | (isolat- |    | (install|    | (lock-   |
|  version)|    |  ation)  |    |  pkgs)  |    |  files)  |
+----------+    +----------+    +---------+    +----------+
     |               |               |               |
     v               v               v               v
.python-version  venv/ dir     requirements.txt  requirements.lock
                              (no pins = drift)   (optional, manual)

NEW STACK (1 tool, full coordination)
+------------------------------------------------------+
|                        uv                            |
|  version mgmt + isolation + install + lockfile       |
+------------------------------------------------------+
     |               |               |               |
     v               v               v               v
.python-version  .venv/ dir      pyproject.toml    uv.lock
                              (deps + metadata)  (auto-generated)
```

uv مكتوب بلغة Rust. عمليات التثبيت أسرع من pip بمقدار 10-100 مرة لأنه يحلّ ويحمّل الحزم بالتوازي مع ذاكرة تخزين مؤقت (cache) عدوانية. ملف الـ lockfile (`uv.lock`) يُولَّد تلقائيًا عند كل `uv add` أو `uv sync`، وليس كأمر لاحق مؤجَّل.

### بنية المشروع بعد `uv init`

```
my-project/
├── .python-version    # e.g. "3.11"
├── .venv/             # isolated environment (auto-created)
├── pyproject.toml     # deps + project metadata (replaces setup.cfg + requirements.txt)
├── uv.lock            # exact pinned versions of all transitive deps
└── main.py            # or src/my_project/
```

### بنية Node + TypeScript

```
my-ts-project/
├── package.json       # deps + scripts
├── package-lock.json  # or pnpm-lock.yaml
├── tsconfig.json      # TypeScript compiler options
├── node_modules/      # installed packages
└── main.ts            # source
```

في دروس هذه الدورة، يعيش كود TypeScript في `code/main.ts` جنبًا إلى جنب مع `code/main.py`. وكلاهما يتشارك نفس مجلد `code/`.

---

## البناء

### الخطوة 1: تثبيت uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify
uv --version
# uv 0.5.x (or higher)
```

uv يثبّت نفسه في `~/.cargo/bin/uv` (أو `~/.local/bin/uv` على Linux). إذا لم يُعثر على `uv` بعد التثبيت، أضف ذلك المجلد إلى متغير الـ PATH.

### الخطوة 2: إنشاء مشروع Python

```bash
# Create a new project directory
mkdir ai-scratch && cd ai-scratch

# Initialize with uv (creates pyproject.toml, .python-version, main.py)
uv init

# Add the Anthropic SDK as a dependency
uv add anthropic

# uv automatically:
# 1. Creates .venv/ if it doesn't exist
# 2. Installs anthropic and its dependencies into .venv/
# 3. Writes the exact versions to uv.lock
# 4. Updates pyproject.toml with anthropic as a dependency
```

تفحّص ما الذي تم إنشاؤه:

```bash
cat pyproject.toml
# [project]
# name = "ai-scratch"
# version = "0.1.0"
# dependencies = ["anthropic>=0.40.0"]

cat .python-version
# 3.12  (or whatever uv detected)

ls -la uv.lock
# This file pins every transitive dependency exactly
```

### الخطوة 3: تشغيل سكربت Python باستخدام uv

```bash
# Run without activating the venv first
uv run python main.py

# Or run any Python command
uv run python -c "import anthropic; print(anthropic.__version__)"
```

`uv run` هو الفكرة المحورية: لن تحتاج أبدًا إلى `source .venv/bin/activate`. فـ uv يتولّى حقن البيئة تلقائيًا. كل سكربت في هذه الدورة يستخدم `uv run`.

> **اختبار من الواقع:** يسألك زميل في الفريق لماذا تستخدم `uv run python main.py` بدلًا من مجرد `python main.py`. يحتجّ بأن تفعيل الـ venv مرة واحدة لكل جلسة طرفية (terminal) أبسط. كيف ستشرح ما الذي يفعله `uv run` فعليًا بشكل مختلف، ولماذا يهمّ ذلك في فريق لديه مشاريع متعددة على نفس الجهاز؟

### الخطوة 4: إعداد Node و TypeScript

```bash
# Check if Node is installed (need v20+)
node --version

# If not installed, use nvm (recommended):
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
nvm install 20
nvm use 20

# Initialize a Node project in the same directory
npm init -y

# Install the Anthropic TypeScript SDK
npm install @anthropic-ai/sdk

# Install TypeScript and ts-node for running .ts files directly
npm install --save-dev typescript ts-node @types/node

# Initialize TypeScript config
npx tsc --init
```

تحقّق من إعداد TypeScript:

```bash
# Create a minimal test file
echo 'import Anthropic from "@anthropic-ai/sdk"; console.log("SDK loaded:", typeof Anthropic);' > test-ts.ts
npx ts-node test-ts.ts
# SDK loaded: function
rm test-ts.ts
```

---

## الاستخدام

`uv run` مقابل تفعيل الـ virtualenv هو التحوّل الجوهري في سير العمل. وإليك المقارنة:

```
ACTIVATE WORKFLOW (old)               UV RUN WORKFLOW (new)
--------------------                  -------------------
cd project-a                          cd project-a
source .venv/bin/activate             uv run python script.py
python script.py

cd ../project-b                       cd ../project-b
deactivate                            uv run python script.py
source .venv/bin/activate             # correct venv used automatically
python script.py
```

مع `uv run`، تُستخدم البيئة الصحيحة دائمًا، بغضّ النظر عن المشروع الذي أنت فيه. ولا يمكنك عن طريق الخطأ تشغيل الكود مقابل الـ venv الخطأ.

```bash
# Add a new dependency (installs + updates pyproject.toml + uv.lock atomically)
uv add httpx

# Remove a dependency
uv remove httpx

# Sync environment to match uv.lock exactly (what CI/CD does)
uv sync

# Run with a specific Python version (uv installs it if missing)
uv run --python 3.11 python main.py

# Show the dependency tree
uv tree
```

> **نقلة في المنظور:** ملف `requirements.txt` الخاص بـ pip يسرد الاعتماديات المباشرة لكن دون اعتمادياتها العابرة (transitive) بالضبط -- ما يعني أن نفس الملف قد يثبّت إصدارات مختلفة من الحزم على أجهزة مختلفة أو في نقاط زمنية مختلفة. أما `uv.lock` فيسجّل كل إصدار من كل حزمة في رسم الاعتماديات بأكمله، ما يجعل البيئات قابلة للتكرار بتطابق تام (bit-for-bit). هذا هو نفس الضمان الذي تمنحك إياه صور Docker، لكن لبيئات Python ودون تكلفة الحاوية (container).

---

## التسليم

المُخرَج (artifact) لهذا الدرس هو بطاقة مرجعية لأوامر uv وبنية المشروع.

انظر `outputs/skill-dev-environment.md`.

---

## التقييم

بيئتك صحيحة عندما تنجح كل هذه الفحوص:

```bash
# 1. uv version is current
uv --version
# Expected: uv 0.5.x or higher

# 2. Python version matches .python-version
uv run python --version
# Expected: Python 3.11.x or 3.12.x

# 3. Anthropic SDK imports cleanly
uv run python -c "import anthropic; print('anthropic', anthropic.__version__)"
# Expected: anthropic 0.40.x or higher (no ImportError)

# 4. uv.lock exists and is non-empty
wc -l uv.lock
# Expected: 100+ lines (transitive deps pinned)

# 5. Node SDK imports cleanly
node -e "const a = require('@anthropic-ai/sdk'); console.log('ts sdk loaded:', typeof a.default);"
# Expected: ts sdk loaded: function

# 6. TypeScript compiles
npx tsc --noEmit main.ts 2>&1 || echo "check tsconfig.json"
# Expected: no errors
```

إذا فشل أي فحص، فإليك أكثر الحلول شيوعًا:

- `uv: command not found` -- أضف `~/.cargo/bin` أو `~/.local/bin` إلى الـ PATH
- `ImportError: No module named anthropic` -- شغّل `uv sync` لاستعادة حالة الـ lockfile
- `node: command not found` -- أكمل تثبيت nvm وشغّل `nvm use 20`
- أخطاء ترجمة (compile) TypeScript -- تأكد من أن `tsconfig.json` يحتوي على `"moduleResolution": "node16"` أو `"bundler"`
