# إدارة إصدارات الموجّهات والنماذج والإعدادات في الإنتاج

> ما الذي يعمل في الإنتاج الآن؟ إن لم تستطع الإجابة عن ذلك في عشر ثوانٍ، فلديك مشكلة في إدارة الإصدارات (versioning).

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** الدرس 06 (الإعدادات والأسرار)، الدرس 02 (تغليف النموذج في FastAPI)
**الوقت:** ~45 دقيقة
**أهداف التعلّم:**
- تحديد الأجزاء المتحرّكة الثلاثة في خدمة ذكاء اصطناعي إنتاجية وشرح سبب احتياج كلٍّ منها إلى إصدار خاص
- بناء صنف بيانات `VersionManifest` يربط إصدار الموجّه ومعرّف النموذج وبصمة الإعدادات (config hash) معًا
- تنفيذ سجلّ بيانات (registry) مبني على YAML مع دالة تراجع (rollback)
- دمج تسجيل البيان (manifest) في بدء تشغيل FastAPI كي يصف كل نشر نفسه
- شرح لماذا يمنع تثبيت معرّفات النماذج (لا الأسماء المستعارة aliases) التغييرات الصامتة في السلوك

---

## المشكلة

كانت خدمة الذكاء الاصطناعي لديك تعمل بشكل جيد الثلاثاء الماضي. واليوم تنتج مخرجات مختلفة بشكل دقيق. لم يتغيّر شيء في تاريخ git لديك. ولم تحدث أي عمليات نشر. فما الذي تعطّل؟

حدّث مزوّد النموذج بهدوء النقطة خلف `claude-haiku-latest`. أو حصل ملف إعداداتك على تعديل من سطر واحد غيّر حرارة (temperature) موجّه النظام (system prompt). أو حدّث زميل قالب الموجّه بينما كنت نائمًا، ودخل التغيير حيز الإنتاج دون أيّ سجلّ عن متى أو من قبل من.

في خدمات الذكاء الاصطناعي ثلاثة أجزاء متحرّكة لا تلتقطها إدارة إصدارات الشيفرة:

1. قالب الموجّه (يتغيّر كثيرًا، وغالبًا على يد غير مهندسين)
2. معرّف النموذج (قد يتغيّر من تحتك حين تستخدم الأسماء المستعارة aliases)
3. إعدادات الخدمة (الحرارة temperature، أقصى عدد tokens، حدود إعادة المحاولة، المهلات الزمنية)

تغيّر أيٍّ من هذه بصمت قد يغيّر سلوك المخرجات بطرق تبدو كإخفاقات للنموذج، أو شكاوى مستخدمين، أو تراجعات في التقييم (eval regressions)، بينما الجاني الحقيقي هو انجراف في الإعدادات (config drift) لا تستطيع تتبّعه.

الحلّ بيان إصدار (version manifest): ملف واحد يسجّل التركيبة الدقيقة للأجزاء الثلاثة التي نُشِرت معًا. حين يتعطل شيء، تنظر إلى البيان، تجد آخر تركيبة معروفة بأنها جيدة، وتتراجع إليها. وبدون بيان، يكون التراجع تخمينًا.

---

## المفهوم

### ثلاثة مكوّنات، بيان واحد

```
+-------------------+    +-------------------+    +-------------------+
|  PROMPT TEMPLATE  |    |    MODEL ID        |    |  SERVICE CONFIG   |
|                   |    |                    |    |                   |
|  version: v1.2    |    |  claude-3-5-haiku  |    |  hash: a4f9c2b1   |
|  commit: abc123   |    |  -20241022         |    |  temp: 0.3        |
|  author: alice    |    |  (pinned, not      |    |  max_tokens: 512  |
|                   |    |   an alias)        |    |  retries: 3       |
+-------------------+    +-------------------+    +-------------------+
          |                       |                         |
          +-------------------------------------------+-----+
                                  |
                    +-------------v-----------+
                    |    VERSION MANIFEST      |
                    |                          |
                    |  manifest_id: v1.2.0     |
                    |  prompt_version: v1.2    |
                    |  model_id: claude-3-5-   |
                    |    haiku-20241022        |
                    |  config_hash: a4f9c2b1   |
                    |  deployed_at: 2025-01-15 |
                    |  deployed_by: ci-bot     |
                    +--------------------------+
                                  |
                    +-------------v-----------+
                    |  MANIFEST REGISTRY       |
                    |  (YAML file, git-tracked)|
                    |                          |
                    |  current: v1.2.0         |
                    |  history: [v1.1.0, ...]  |
                    +--------------------------+
```

### لماذا نثبّت معرّفات النماذج لا الأسماء المستعارة (Aliases)

تُحدّث الأسماء المستعارة للنماذج (`claude-haiku-latest`، `gpt-4-turbo`) من قِبل المزوّدين دون إعلان. في يومٍ يوجّه `claude-haiku-latest` إلى إصدار النموذج X. وفي اليوم التالي يوجّه إلى إصدار النموذج Y. كان موجّهك مضبوطًا على X. وإصدار Y له سلوك مختلف في اتّباع التعليمات. تبدأ تقييماتك (evals) بالفشل ولا تعرف لماذا.

تحلّ المعرّفات المثبّتة (pinned IDs) هذا:

```
WRONG:  model: "claude-haiku-latest"       # silently changes
RIGHT:  model: "claude-3-5-haiku-20241022" # immutable
```

يفرض البيان التثبيت وقت التسجيل: إن احتوى معرّف النموذج على `-latest` أو انتهى دون لاحقة تاريخ، يرفضه السجلّ.

### بصمة الإعدادات مقابل قيم الإعدادات

تخزين الإعدادات كاملةً في البيان ينتج ملفًا طويلًا يصعب مقارنته (diff). تخزين البصمة (hash) فقط يتيح لك الإجابة عن "هل تغيّرت الإعدادات؟" بكلفة زهيدة. وحين تحتاج إلى فحص ما الذي تغيّر، تبحث عن ملف الإعدادات ببصمته. البيان هو الفهرس؛ وملف الإعدادات هو مصدر الحقيقة.

---

## البناء

### الخطوة 1: صنف بيانات VersionManifest

```python
# code/main.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class VersionManifest:
    """Records the exact combination of prompt, model, and config deployed together."""
    manifest_id: str           # e.g. "v1.2.0"
    prompt_version: str        # e.g. "v1.2" (matches git tag or semver)
    model_id: str              # e.g. "claude-3-5-haiku-20241022" (pinned, never alias)
    config_hash: str           # first 8 chars of SHA-256 of the config dict
    deployed_at: str           # ISO-8601 UTC timestamp
    deployed_by: str = "local" # person or CI system that deployed
    notes: str = ""            # optional release note


def hash_config(config: dict) -> str:
    """
    Compute a short, stable SHA-256 hash of a config dict.
    Keys are sorted so insertion order does not affect the hash.
    Returns first 8 hex characters.
    """
    serialized = json.dumps(config, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]
```

صنف البيانات (dataclass) كائن قيمة بسيط. لا ORM، ولا قاعدة بيانات. هو مجرد بيانات يمكنك إجراؤها (serialize) إلى YAML وقراءتها ثانيةً.

### الخطوة 2: سجلّ البيانات (Manifest Registry)

```python
MANIFEST_FILE = Path("manifests.yaml")


class ManifestRegistry:
    """
    Loads, saves, and queries VersionManifest records from a YAML file.
    The YAML file is meant to be git-tracked alongside your code.
    """

    def __init__(self, path: Path = MANIFEST_FILE):
        self.path = path
        self._manifests: list[VersionManifest] = []
        self._current_id: Optional[str] = None
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        data = yaml.safe_load(self.path.read_text())
        if not data:
            return
        self._current_id = data.get("current")
        for entry in data.get("history", []):
            self._manifests.append(VersionManifest(**entry))

    def _save(self) -> None:
        data = {
            "current": self._current_id,
            "history": [asdict(m) for m in self._manifests],
        }
        self.path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=True))

    def register(self, manifest: VersionManifest) -> None:
        """Add a new manifest and mark it as current."""
        if "latest" in manifest.model_id.lower():
            raise ValueError(
                f"Model alias '{manifest.model_id}' is not allowed. "
                "Use a pinned model ID like 'claude-3-5-haiku-20241022'."
            )
        self._manifests.append(manifest)
        self._current_id = manifest.manifest_id
        self._save()

    def current(self) -> Optional[VersionManifest]:
        """Return the currently active manifest."""
        if not self._current_id:
            return None
        for m in self._manifests:
            if m.manifest_id == self._current_id:
                return m
        return None

    def get(self, manifest_id: str) -> Optional[VersionManifest]:
        """Retrieve a specific manifest by ID."""
        for m in self._manifests:
            if m.manifest_id == manifest_id:
                return m
        return None

    def history(self) -> list[VersionManifest]:
        """Return all manifests in registration order."""
        return list(self._manifests)
```

### الخطوة 3: دالة التراجع (Rollback)

```python
def rollback(registry: ManifestRegistry, manifest_id: str) -> VersionManifest:
    """
    Roll back to a previous manifest by ID.
    This does NOT revert config files - it only changes which manifest
    is marked as current. The caller is responsible for loading the
    config that corresponds to the rolled-back manifest.

    Returns the manifest that is now active.
    """
    target = registry.get(manifest_id)
    if target is None:
        raise ValueError(
            f"Manifest '{manifest_id}' not found in registry. "
            f"Available: {[m.manifest_id for m in registry.history()]}"
        )
    registry._current_id = manifest_id
    registry._save()
    print(f"Rolled back to manifest {manifest_id}")
    print(f"  prompt_version: {target.prompt_version}")
    print(f"  model_id:       {target.model_id}")
    print(f"  config_hash:    {target.config_hash}")
    print(f"  deployed_at:    {target.deployed_at}")
    return target
```

> **اختبار من الواقع:** يُستدعى مهندس المناوبة (on-call) لديك الساعة الثانية صباحًا لأن استجابات الذكاء الاصطناعي صارت فجأةً أطول بكثير وتربك المستخدمين. يفحص سجلّ git: لا تغييرات في الشيفرة خلال 48 ساعة. يفحص صفحة حالة مزوّد النموذج: لا حوادث. كيف يغيّر وجود بيان إصدار ما يفعله في الدقائق الخمس التالية مقارنةً بعدم وجوده؟

### الخطوة 4: إنشاء بيان وقت النشر

```python
def make_manifest(
    manifest_id: str,
    prompt_version: str,
    model_id: str,
    config: dict,
    deployed_by: str = "local",
    notes: str = "",
) -> VersionManifest:
    """
    Factory: builds a VersionManifest from raw inputs.
    Computes the config hash automatically.
    """
    return VersionManifest(
        manifest_id=manifest_id,
        prompt_version=prompt_version,
        model_id=model_id,
        config_hash=hash_config(config),
        deployed_at=datetime.now(timezone.utc).isoformat(),
        deployed_by=deployed_by,
        notes=notes,
    )


# Demo: register two versions and roll back
if __name__ == "__main__":
    registry = ManifestRegistry(Path("demo_manifests.yaml"))

    config_v1 = {"temperature": 0.3, "max_tokens": 512, "retries": 3}
    config_v2 = {"temperature": 0.7, "max_tokens": 1024, "retries": 3}

    m1 = make_manifest(
        manifest_id="v1.0.0",
        prompt_version="v1.0",
        model_id="claude-3-5-haiku-20241022",
        config=config_v1,
        deployed_by="alice",
        notes="Initial production deploy",
    )
    registry.register(m1)
    print(f"Registered: {m1.manifest_id} (config_hash={m1.config_hash})")

    m2 = make_manifest(
        manifest_id="v1.1.0",
        prompt_version="v1.1",
        model_id="claude-3-5-haiku-20241022",
        config=config_v2,
        deployed_by="bob",
        notes="Increased temperature for more creative responses",
    )
    registry.register(m2)
    print(f"Registered: {m2.manifest_id} (config_hash={m2.config_hash})")

    print(f"\nCurrent manifest: {registry.current().manifest_id}")

    print("\n--- Rolling back to v1.0.0 ---")
    active = rollback(registry, "v1.0.0")
    print(f"\nActive after rollback: {registry.current().manifest_id}")

    # Show the full history
    print("\n--- Full History ---")
    for m in registry.history():
        marker = " <-- current" if m.manifest_id == registry.current().manifest_id else ""
        print(f"  {m.manifest_id}  prompt={m.prompt_version}  model={m.model_id}  config={m.config_hash}{marker}")
```

---

## الاستخدام

ادمج سجلّ البيانات في خدمة FastAPI باستخدام نمط lifespan كي يُسجَّل البيان الفعّال عند كل بدء تشغيل. ويعني هذا أن كل نشر يصف نفسه: يستطيع أي مهندس فحص السجلات ليعرف بالضبط ما الذي يعمل.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import anthropic
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log the active manifest at startup. Fail fast if none is registered."""
    registry = ManifestRegistry(Path("manifests.yaml"))
    manifest = registry.current()

    if manifest is None:
        raise RuntimeError(
            "No active manifest found. Register a manifest before starting the service."
        )

    logger.info("=== SERVICE STARTUP ===")
    logger.info(f"manifest_id:     {manifest.manifest_id}")
    logger.info(f"prompt_version:  {manifest.prompt_version}")
    logger.info(f"model_id:        {manifest.model_id}")
    logger.info(f"config_hash:     {manifest.config_hash}")
    logger.info(f"deployed_at:     {manifest.deployed_at}")
    logger.info(f"deployed_by:     {manifest.deployed_by}")
    if manifest.notes:
        logger.info(f"notes:           {manifest.notes}")
    logger.info("=== STARTUP COMPLETE ===")

    # Store manifest on app state so endpoints can access it
    app.state.manifest = manifest
    app.state.registry = registry

    yield

    logger.info("Service shutting down.")


app = FastAPI(title="AI Service", lifespan=lifespan)
client = anthropic.Anthropic()


@app.get("/health")
async def health():
    """Returns the active manifest with every health check response."""
    manifest = app.state.manifest
    return {
        "status": "ok",
        "manifest_id": manifest.manifest_id,
        "prompt_version": manifest.prompt_version,
        "model_id": manifest.model_id,
        "config_hash": manifest.config_hash,
    }


@app.post("/chat")
async def chat(request: dict):
    """
    Chat endpoint that logs which manifest served each request.
    In production you would also log this to your observability platform.
    """
    manifest = app.state.manifest
    user_message = request.get("message", "")

    response = client.messages.create(
        model=manifest.model_id,
        max_tokens=512,
        messages=[{"role": "user", "content": user_message}],
    )

    return {
        "response": response.content[0].text,
        "manifest_id": manifest.manifest_id,
        "model_id": manifest.model_id,
    }
```

> **نقلة في المنظور:** يحاجج زميل: "نحن نستخدم git لإدارة الإصدارات. كل تغيير في الإعدادات هو commit. فلماذا نحتاج إلى ملف بيان منفصل فوق تاريخ git؟" ما الذي يمنحك إياه البيان ولا يمنحك إياه git، خصوصًا حين تأتي الإعدادات من متغيّرات البيئة، أو مديري الأسرار (secrets managers)، أو تُغيَّر من قِبل المشغّلين (operators) وقت التشغيل لا عبر الشيفرة؟

---

## التسليم

المنتَج لهذا الدرس هو `outputs/skill-version-manifest.md`: قالب بيان إصدار قابل لإعادة الاستخدام وقائمة تحقّق للنشر يمكنك تكييفها لأي خدمة ذكاء اصطناعي.

لاستخدام شيفرة هذا الدرس:

```bash
# Install deps
pip install pyyaml fastapi anthropic uvicorn

# Register your first manifest
python main.py

# Start the service (requires manifests.yaml to exist)
uvicorn main:app --reload

# Check what is running
curl http://localhost:8000/health
```

---

## التقييم

**الفحص 1: سجلات بدء التشغيل قابلة للتدقيق.**
لأيّ نشر في الـ30 يومًا الماضية، ينبغي أن تستطيع الإجابة من السجلات وحدها: أي معرّف نموذج كان يعمل، وأي إصدار موجّه كان فعّالًا، وأي بصمة إعدادات كانت مستخدمة. إن لم تستطع، فالبيان لا يُسجَّل عند بدء التشغيل.

**الفحص 2: التراجع يعمل تحت الضغط.**
قِس كم يستغرق مهندس لم يرَ هذه الشيفرة من قبل ليتراجع إلى بيان سابق. الهدف: أقل من دقيقتين. إن استغرق أطول، فواجهة السجلّ غامضة أكثر من اللازم، أو معرّفات البيان غير وصفية بما يكفي.

**الفحص 3: رفض الأسماء المستعارة (Alias) يعمل.**
حاول تسجيل بيان بـ`model_id="claude-haiku-latest"`. ينبغي أن يرفع السجلّ خطأ `ValueError`. هذا حارس صارم: يجب ألّا تصل الأسماء المستعارة إلى الإنتاج أبدًا.

**الفحص 4: بصمة الإعدادات تلتقط الانجراف.**
غيّر قيمة واحدة في إعداداتك (مثلًا الحرارة من 0.3 إلى 0.31). تحقّق من تغيّر بصمة الإعدادات. هذا يؤكّد أن دالة البصمة حسّاسة للقيم التي تؤثر فعلًا في سلوك النموذج.

**الفحص 5: نقطة الصحة موثوقة.**
في تدريب على حادثة إنتاجية، ينبغي أن يكون السؤال الأول: "ما معرّف البيان الآن؟" إن أجابت نقطة `/health` عن ذلك، فسيفحصها فريقك أولًا بدل التخمين. قِس ما إذا كان فريقك يستخدمها.
