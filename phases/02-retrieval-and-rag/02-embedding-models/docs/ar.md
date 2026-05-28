# نماذج الـ Embedding

> نموذج الـ embedding الذي تختاره يحدّد سقف الاسترجاع لديك. وكل تحسين آخر محدود به.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 02-01 الحدس وراء الـ Embeddings
**الوقت:** ~75 دقيقة
**المرحلة:** 02 · الاسترجاع و RAG

## أهداف التعلّم

- مقارنة مشهد نماذج الـ embedding لعام 2026 من حيث التكلفة والجودة وزمن الاستجابة (latency) والملاءمة للمجال
- تنفيذ قياس مرجعي (benchmark) قابل للتكرار مبني على MRR لقياس جودة نموذج الـ embedding على بياناتك أنت
- شرح embeddings الماتريوشكا (Matryoshka) ومتى يكون التقليم (truncation) تحسينًا صحيحًا للتكلفة
- استدعاء OpenAI وVoyage ونموذج sentence-transformer محلّي بالواجهة نفسها ومقارنة النتائج
- بناء تقييم استرجاع خاص بالمجال يكشف فجوة جودة النموذج قبل الإنتاج

---

## المشكلة

أمضى فريق هندسي في شركة تقنية مالية (fintech) ثلاثة أسابيع في ضبط خطّ أنابيب RAG لديهم: هندسة الـ prompt، وتجارب حجم الـ chunk، وإعادة الترتيب (reranking): ولم يتمكّنوا من تجاوز دقة إجابة 60%. وحين أجروا أخيرًا تقييم استرجاع سليمًا، اكتشفوا أن دقة الاسترجاع للمرتبة الأولى لديهم كانت 47%. كانوا يستخدمون `all-MiniLM-L6-v2`: نموذجًا مبنيًا للبحث الدلالي العام: لاسترجاع مستندات تنظيمية مالية مليئة بالاختصارات والمصطلحات القانونية والمراجع العددية التي لم يُدرَّب النموذج قطّ على فهمها.

لا يستطيع الـ LLM توليد إجابة صحيحة من سياق غير ذي صلة. ولا قدر من ضبط الـ prompt يُصلح مشكلة استرجاع. ضاعت ثلاثة أسابيع من العمل لأن نموذج الـ embedding الخاطئ اختير من البداية.

هذا هو القرار الأهمّ في تصميم نظام RAG، وهو الذي غالبًا ما يتّخذه المهندسون باستهتار: اختيار أي نموذج ورد في أول درس قرأوه، أو اللجوء افتراضيًا إلى أكبر خيار متاح دون تقييم ما إذا كان الملائم. تتفاوت نماذج الـ embedding بعامل 10 أضعاف في التكلفة، و5 أضعاف في زمن الاستجابة، وبأكثر من 30 نقطة مئوية في جودة الاسترجاع للمجالات المتخصّصة. اتخاذ هذا القرار بشكل صحيح قبل كتابة بقية خطّ الأنابيب يوفّر أسابيع.

---

## المفهوم

### المشهد في عام 2026

نضج سوق نماذج الـ embedding ليصبح ثلاث طبقات:

**مستضافة عبر API، للأغراض العامة**: أفضل توازن بين الجودة والملاءمة:

| النموذج | المزوّد | الأبعاد | السياق | ملاحظات |
|---|---|---|---|---|
| text-embedding-3-small | OpenAI | 1536 | 8,192 tok | أفضل نسبة تكلفة/جودة للإنجليزية |
| text-embedding-3-large | OpenAI | 3072 | 8,192 tok | أعلى جودة للإنجليزية؛ 5 أضعاف تكلفة small |
| embed-v4 | Cohere | 1024 | 128K tok | قوي متعدّد اللغات؛ سياق طويل |
| voyage-4 | Voyage AI | 1024 | 32K tok | محسّن لـ RAG، قوي في مهام الاسترجاع |
| Gemini Embedding 2 | Google | 3072 | 32K tok | قوي عبر اللغات؛ بنية تحتية أصلية من Google |

**مفتوحة الأوزان، مستضافة ذاتيًا**: تحكّم كامل، بلا تكلفة لكل token:

| النموذج | الأبعاد | ملاحظات |
|---|---|---|
| BGE-M3 | 1024 | dense + sparse + ColBERT في نموذج واحد؛ متعدّد اللغات |
| Qwen3-Embedding | 1536 | خيار قوي مفتوح الأوزان؛ متعدّد اللغات |
| all-MiniLM-L6-v2 | 384 | خطّ أساس للنماذج الأوّلية: سريع، صغير، ليس بجودة إنتاجية |
| all-mpnet-base-v2 | 768 | خطّ أساس أفضل جودة؛ لا يزال للأغراض العامة |

**متخصّصة بالمجال**: مضبوطة بدقة لأنواع محتوى معيّنة:

| المجال | النموذج |
|---|---|
| Code | voyage-code-3, CodeBERT |
| Legal | legal-bert-base-uncased (أقدم لكنه لا يزال خطّ أساس مفيد) |
| Biomedical | BioBERT, PubMedBERT |
| Multilingual | BGE-M3, paraphrase-multilingual-MiniLM-L12-v2 |

### embeddings الماتريوشكا (Matryoshka)

يدعم نموذجا OpenAI `text-embedding-3-small` و`text-embedding-3-large` تعلّم التمثيل الماتريوشكي (Matryoshka Representation Learning - MRL). هذا يعني أن النموذج مُدرّب بحيث تحتوي أول N بُعدًا من شعاع بـ 1536 بُعدًا أهمّ المعلومات، ويمكنك التقليم إلى حجم أصغر دون خسارة كارثية في الجودة.

```
Full 1536-dim:   [d1, d2, d3, ..., d768, ..., d1536]   ← max quality
Truncate to 768: [d1, d2, d3, ..., d768]                ← ~95% quality at half the storage
Truncate to 256: [d1, d2, d3, ..., d256]                ← ~88% quality at 1/6 the storage
```

هذا مهمّ لأن تخزين الأشعّة وحساب التشابه يتناسبان مع البُعد. فهرس بـ 50 مليون مستند عند 1536 بُعدًا يستهلك 300GB. وعند 256 بُعدًا، يصبح 50GB. إن كانت جودة 88% مقبولة، فتقليم الماتريوشكا مكسب مجاني.

النماذج التقليدية لا تدعم هذا: تقليم `all-MiniLM-L6-v2` اعتباطيًا سيدمّر الجودة لأن الأبعاد المتأخّرة تحمل إشارة ذات معنى لا تلتقطها أول N.

### الأبعاد مقابل الجودة

على عكس الحدس، عدد أبعاد أكبر لا يعني دائمًا جودة أفضل:

```
Model quality is determined by:
  1. Training data quality and quantity
  2. Training objective (contrastive learning setup)
  3. Model architecture (BERT vs. transformer encoder variants)
  4. Fine-tuning on domain-specific tasks

Dimension count is a capacity choice: more capacity helps only if
the training data can fill it with meaningful signal.
```

نموذج بـ 768 بُعدًا مُدرّب على مليار زوج جمل كثيرًا ما يتفوّق على نموذج بـ 3072 بُعدًا مُدرّب على 100 مليون زوج في مهام الاسترجاع العامة. قيّم دائمًا؛ ولا تفترض أبدًا.

### حلقة التقييم: MTEB مقابل مجالك

MTEB (Massive Text Embedding Benchmark) هي لوحة الصدارة العامة المعتمَدة لمقارنة النماذج عبر 56 مهمة تشمل الاسترجاع والتصنيف والتجميع. نقطة انطلاق جيدة لكن لها قيد جوهري: تقيّم على مجموعات بيانات عامة. وبياناتك الإنتاجية مختلفة.

```
Decision flow:

1. Start with MTEB retrieval leaderboard to identify top-5 candidates
2. Collect 50-100 (query, relevant_document) pairs from YOUR data
3. Run your benchmark: measure MRR@5 and Hit Rate@5
4. Pick the model that wins on YOUR data, not MTEB
5. Re-run when your data distribution shifts (new product lines, new languages)
```

متوسّط الرتبة المعكوسة (Mean Reciprocal Rank - MRR) هو المقياس الصحيح لهذا التقييم:

```
For each query:
  find the rank of the first correct document in the results
  MRR contribution = 1 / rank

MRR = mean over all queries

MRR = 1.0   → first result is always correct
MRR = 0.5   → correct answer is at rank 1 or 2 on average
MRR = 0.2   → correct answer is buried; retrieval is failing
```

### متى تستخدم المحلّي مقابل الـ API

```
                   LOCAL (sentence-transformers / self-hosted)
                   ┌────────────────────────────────────────┐
                   │ Privacy: documents can't leave network  │
                   │ Cost: free at runtime, pay for compute  │
                   │ Latency: depends on hardware            │
                   │ Control: can fine-tune on your data     │
                   │ Ops: you manage model updates           │
                   └────────────────────────────────────────┘

                   API (OpenAI / Voyage / Cohere)
                   ┌────────────────────────────────────────┐
                   │ Privacy: data leaves your network       │
                   │ Cost: pay per token (scales with volume)│
                   │ Latency: 50-200ms per batch API call    │
                   │ Control: no fine-tuning (usually)       │
                   │ Ops: zero; provider handles updates     │
                   └────────────────────────────────────────┘

Decision rule of thumb:
  < 10M docs AND non-sensitive: start with API (text-embedding-3-small)
  > 10M docs: self-hosted to control costs
  Sensitive data (healthcare, finance, legal): self-hosted
  Need fine-tuning: self-hosted
```

---

## البناء

سنبني منصّة قياس (benchmark harness) تقيّم عدة نماذج embedding على مجموعة الاختبار نفسها وتحسب MRR@5. هذه هي الأداة التي تشغّلها قبل الالتزام بنموذج embedding للإنتاج.

### الخطوة 1: تعريف مجموعة الاختبار

مجموعة الاختبار الجيدة لها أزواج استعلام/مستند مُصنّفة بشريًا. للتوضيح، سنبني مجموعة اختبار صغيرة داخل الكود. عمليًا، ستُحمّلها من ملف CSV أو JSONL يحوي أزواجًا مُصنّفة من مجالك.

```python
# pip install numpy sentence-transformers openai httpx

# Structure: a list of (query, list_of_relevant_doc_ids, all_documents)
# We represent documents as (doc_id, text) tuples

DOCUMENTS = [
    ("doc_0", "How to configure multi-factor authentication for your account"),
    ("doc_1", "Understanding your monthly invoice and billing cycle"),
    ("doc_2", "Troubleshooting application startup failures and crash reports"),
    ("doc_3", "API rate limits: requests per second and daily quota"),
    ("doc_4", "Data retention policies and automated backup schedules"),
    ("doc_5", "Setting up SSO with SAML 2.0 and identity providers"),
    ("doc_6", "Network timeout errors and connection refused troubleshooting"),
    ("doc_7", "Exporting account data for GDPR compliance requests"),
    ("doc_8", "Password reset flow and recovery email configuration"),
    ("doc_9", "Webhook event types and payload schema reference"),
]

# Each entry: (query_text, [list of relevant doc_ids])
LABELED_QUERIES = [
    ("my login isn't working with the authenticator app", ["doc_0"]),
    ("I can't see my latest charge on the bill", ["doc_1"]),
    ("the app crashes immediately when I try to open it", ["doc_2"]),
    ("how do I avoid hitting API limits in production", ["doc_3"]),
    ("where are my files backed up", ["doc_4"]),
    ("set up enterprise single sign-on", ["doc_5"]),
    ("connection keeps timing out", ["doc_6"]),
    ("I need to download all my data for legal reasons", ["doc_7"]),
    ("forgot password and can't get into my account", ["doc_8"]),
    ("what data format do webhooks send", ["doc_9"]),
]
```

### الخطوة 2: تنفيذ MRR@K

```python
import numpy as np

def cosine_similarity_matrix(query_vecs: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """
    Compute pairwise cosine similarity between query and doc vectors.
    Assumes vectors are already normalized (unit length).
    Returns shape (num_queries, num_docs).
    """
    return query_vecs @ doc_vecs.T


def compute_mrr(
    query_vecs: np.ndarray,
    doc_vecs: np.ndarray,
    labeled_queries: list[tuple[str, list[str]]],
    doc_ids: list[str],
    k: int = 5,
) -> dict:
    """
    Compute MRR@K and Hit Rate@K for a set of labeled queries.

    labeled_queries: list of (query_text, [relevant_doc_ids])
    doc_ids: ordered list of document IDs matching doc_vecs rows
    """
    id_to_idx = {doc_id: i for i, doc_id in enumerate(doc_ids)}
    sim_matrix = cosine_similarity_matrix(query_vecs, doc_vecs)

    reciprocal_ranks = []
    hits = []

    for q_idx, (query_text, relevant_ids) in enumerate(labeled_queries):
        scores = sim_matrix[q_idx]
        # argsort descending: highest score first
        ranked_indices = np.argsort(scores)[::-1][:k]
        ranked_doc_ids = [doc_ids[i] for i in ranked_indices]

        # MRR: find rank of first relevant document
        rr = 0.0
        hit = False
        for rank, doc_id in enumerate(ranked_doc_ids, start=1):
            if doc_id in relevant_ids:
                rr = 1.0 / rank
                hit = True
                break

        reciprocal_ranks.append(rr)
        hits.append(1 if hit else 0)

    mrr = float(np.mean(reciprocal_ranks))
    hit_rate = float(np.mean(hits))
    return {"mrr": mrr, "hit_rate": hit_rate, "k": k}
```

### الخطوة 3: بناء منصّة التقييم

```python
import time
from dataclasses import dataclass

@dataclass
class ModelResult:
    model_name: str
    mrr: float
    hit_rate: float
    latency_ms: float  # time to encode all queries, in ms
    dim: int


def evaluate_sentence_transformer(
    model_name: str,
    documents: list[tuple[str, str]],
    labeled_queries: list[tuple[str, list[str]]],
    k: int = 5,
) -> ModelResult:
    """Evaluate a sentence-transformer model."""
    from sentence_transformers import SentenceTransformer

    doc_ids = [d[0] for d in documents]
    doc_texts = [d[1] for d in documents]
    query_texts = [q[0] for q in labeled_queries]

    model = SentenceTransformer(model_name)

    # Encode documents (index time: we don't time this)
    doc_vecs = model.encode(
        doc_texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    )

    # Encode queries and time it (query time: this is what matters for latency)
    t0 = time.perf_counter()
    query_vecs = model.encode(
        query_texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    metrics = compute_mrr(query_vecs, doc_vecs, labeled_queries, doc_ids, k=k)

    return ModelResult(
        model_name=model_name,
        mrr=metrics["mrr"],
        hit_rate=metrics["hit_rate"],
        latency_ms=latency_ms,
        dim=doc_vecs.shape[1],
    )
```

### الخطوة 4: إضافة استدعاء embedding من OpenAI

```python
def evaluate_openai(
    model_name: str,
    documents: list[tuple[str, str]],
    labeled_queries: list[tuple[str, list[str]]],
    dimensions: int | None = None,
    k: int = 5,
) -> ModelResult:
    """
    Evaluate an OpenAI embedding model.
    Set OPENAI_API_KEY in your environment.

    `dimensions` enables Matryoshka truncation for text-embedding-3-* models.
    Pass dimensions=256 to test a truncated version.
    """
    import openai

    client = openai.OpenAI()
    doc_ids = [d[0] for d in documents]
    doc_texts = [d[1] for d in documents]
    query_texts = [q[0] for q in labeled_queries]

    def embed_batch(texts: list[str]) -> np.ndarray:
        kwargs = {"model": model_name, "input": texts}
        if dimensions:
            kwargs["dimensions"] = dimensions
        response = client.embeddings.create(**kwargs)
        vecs = np.array([item.embedding for item in response.data])
        # Normalize
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / norms

    doc_vecs = embed_batch(doc_texts)

    t0 = time.perf_counter()
    query_vecs = embed_batch(query_texts)
    latency_ms = (time.perf_counter() - t0) * 1000

    metrics = compute_mrr(query_vecs, doc_vecs, labeled_queries, doc_ids, k=k)
    actual_dim = dimensions if dimensions else doc_vecs.shape[1]

    return ModelResult(
        model_name=f"{model_name}@{actual_dim}d" if dimensions else model_name,
        mrr=metrics["mrr"],
        hit_rate=metrics["hit_rate"],
        latency_ms=latency_ms,
        dim=actual_dim,
    )
```

### الخطوة 5: طباعة جدول النتائج

```python
def print_benchmark_table(results: list[ModelResult]) -> None:
    print(f"\n{'Model':<45} {'Dims':>5} {'MRR@5':>7} {'Hit@5':>7} {'Q-Lat ms':>10}")
    print("-" * 80)
    for r in sorted(results, key=lambda x: x.mrr, reverse=True):
        print(
            f"{r.model_name:<45} {r.dim:>5} {r.mrr:>7.3f} "
            f"{r.hit_rate:>7.1%} {r.latency_ms:>10.1f}"
        )
    print()
    best = max(results, key=lambda x: x.mrr)
    print(f"Best model: {best.model_name}  (MRR@5={best.mrr:.3f})")
```

> **اختبار من الواقع:** مدير المنتج لديك ينظر إلى هذا القياس ويقول: "ما نقدر بس نختار أرخص نموذج ونمشي؟ يبدو أن المستخدمين راضين عن البحث الحالي." كيف تشرح لماذا يهمّ اختيار النموذج بدلالة النتائج التي يهتمّ بها فعلًا، دون الخوض في درجات MRR؟

---

## الاستخدام

في الإنتاج، تستدعي embedding APIs عبر عملائها الرسميين. إليك الواجهة المبسّطة لكل مزوّد رئيسي: لاحظ أن النمط متطابق عبرها جميعًا، يتغيّر العميل واسم النموذج فقط:

```python
# OpenAI
import openai
client = openai.OpenAI()
response = client.embeddings.create(
    model="text-embedding-3-small",
    input=["text one", "text two"],
    dimensions=1536,  # optional: Matryoshka truncation
)
vectors = [item.embedding for item in response.data]

# Voyage AI
import voyageai
client = voyageai.Client()
result = client.embed(
    ["text one", "text two"],
    model="voyage-4",
    input_type="document",  # or "query" for query embedding
)
vectors = result.embeddings

# Cohere
import cohere
co = cohere.Client()
response = co.embed(
    texts=["text one", "text two"],
    model="embed-english-v3.0",
    input_type="search_document",  # or "search_query"
)
vectors = response.embeddings
```

**لماذا تستخدم API بدلًا من نموذج محلّي؟**

- صفر بنية تحتية: لا تخصيص GPU، ولا عبء تحميل النموذج
- تحديثات النموذج شفّافة (المزوّد يتولّى تحسينات الجودة)
- جودة أفضل على النصّ الإنجليزي لمعظم حالات الاستخدام (text-embedding-3-small يتفوّق على all-MiniLM بـ 15-20 نقطة على قياسات الاسترجاع)
- يوفّر Cohere وVoyage معامل `input_type` الذي يضبط الـ embedding لعدم تماثل الاستعلام مقابل المستند: تحسين جودة ذو معنى لـ RAG

**حيلة الـ embedding غير المتماثل:**

حين يكون استعلامك قصيرًا ("what is a refund policy?") ومستنداتك طويلة (صفحات سياسة كاملة)، تساعد الـ embeddings غير المتماثلة: الاستعلام والمستند يُرمّزان بدالّتين مختلفتين قليلًا، كلتاهما مُدرّبتان معًا لتعظيم الاسترجاع. معامل Voyage `input_type="query"` / `"document"` ينفّذ هذا. واستخدام الدالة نفسها للاستعلام والمستند (كما تفعل sentence-transformers افتراضيًا) يُسمّى embedding متماثل.

> **نقلة في المنظور:** مهندس أول متشكّك يقول: "احنا أصلًا ندفع لـ OpenAI. ليش نقيّم Voyage وCohere؟ مو هذا بس إضافة تعقيد بمزوّدين مقابل مكاسب هامشية؟" ماذا تقول لتأخذ هذا القلق على محمل الجدّ، وما الشروط الملموسة التي تبرّر فعلًا البقاء مع مزوّد واحد؟

---

## التسليم

ينتج هذا الدرس سكربت قياس قابلًا لإعادة الاستخدام يمكنك تشغيله على بياناتك أنت.

**الأثر (Artifact):** `02-embedding-models/outputs/prompt-embedding-model-selector.md`

ملف الـ prompt هذا مستشار على هيئة شجرة قرار يمكنك استخدامه مع أي LLM للحصول على توصية مُهيكلة لقيودك المحدّدة. زوّده بتفاصيل حالة استخدامك واحصل على قائمة مختصرة مُرتّبة من النماذج للاختبار.

يوفّر `code/main.py` منصّة قياس جاهزة للتشغيل. استبدل بمستنداتك واستعلاماتك المُصنّفة (حتى 20 زوجًا كافية لإشارة ذات معنى) وشغّلها قبل الالتزام بنموذج.

---

## التقييم

**الفحص 1: MRR@5 على بيانات مجالك**

شغّل منصّة القياس في `code/main.py` مع 30–50 زوجًا مُصنّفًا من مجموعتك الفعلية. فسّر:
- MRR@5 > 0.85: استرجاع قوي: النموذج يلائم مجالك
- MRR@5 0.65–0.85: مقبول لمعظم حالات الاستخدام، لكن اختبر البدائل
- MRR@5 < 0.65: عدم تطابق بين النموذج والمجال؛ قيّم خيارات متخصّصة

**الفحص 2: اختبار تقليم المستند الطويل**

إن تجاوزت مستنداتك نافذة سياق النموذج (معظم النماذج: 512 token)، يُتجاهَل ذيل المستند بصمت. اختبر هذا:

```python
long_doc = "short intro... " + ("filler content " * 200) + "the answer is here at the end"
short_query = "what is the answer"
# If the model can't find it, your long docs need chunking (Lesson 04)
```

**الفحص 3: التوافق بين النماذج**

لا تخلط أبدًا embeddings من نماذج مختلفة (أو إصدارات نماذج مختلفة) في الفهرس نفسه. هذا يُنتج درجات تشابه بلا معنى:

```python
import numpy as np
from sentence_transformers import SentenceTransformer

m1 = SentenceTransformer("all-MiniLM-L6-v2")
m2 = SentenceTransformer("all-mpnet-base-v2")

v1 = m1.encode(["test query"], normalize_embeddings=True)
v2 = m2.encode(["test query"], normalize_embeddings=True)

# These vectors have different dimensions (384 vs 768): you can't compare them.
# Even if dimensions matched, different training = different coordinate systems.
print(f"m1 dim: {v1.shape[1]}, m2 dim: {v2.shape[1]}")
# Store model name and version alongside every indexed document.
```

---

## التمارين

1. **سهل:** وسّع منصّة القياس لتُبلّغ أيضًا عن *أسوأ استعلام أداءً* لكل نموذج: الاستعلام صاحب أدنى مساهمة في MRR. هذا يحدّد وضع الفشل المعيّن لكل نموذج.

2. **متوسط:** نفّذ تقييم تقليم الماتريوشكا لـ `text-embedding-3-small`. قِس MRR@5 عند الأبعاد 256 و512 و768 و1536. ارسم منحنى مفاضلة الجودة/التكلفة وأوجد نقطة الركبة (knee point): أصغر بُعد يحافظ على 95% من جودة البُعد الكامل.

3. **صعب:** اضبط بدقة (fine-tune) نموذج sentence-transformer على بيانات مجالك أنت باستخدام واجهة تدريب `sentence-transformers`. ولّد أزواجًا موجبة (query, relevant_doc) من مجموعتك المُصنّفة، وسلبيات صعبة (query, مستند يسجّل عاليًا لكنه خاطئ). قارن MRR@5 للنموذج المضبوط مقابل الأساس. هذا هو سير العمل الذي تشغّله لسدّ فجوة المجال حين لا يلائمك أي نموذج جاهز.

---

## المصطلحات الأساسية

| المصطلح | ما يقوله الناس | ما يعنيه فعلًا |
|------|----------------|----------------------|
| Matryoshka embeddings | "embeddings قابلة للتقليم" | أشعّة مُدرّبة بحيث تحوي أول N بُعدًا أعلى تمثيل جودةً: يمكنك إسقاط الأبعاد المتأخّرة دون خسارة جودة كثيرة بشكل متناسب |
| MRR | "متوسّط الرتبة المعكوسة: يقيس جودة الاسترجاع" | متوسّط 1/rank عبر الاستعلامات، حيث rank هو موضع أول نتيجة ذات صلة. MRR=1.0 يعني الترتيب أولًا دائمًا. |
| MTEB | "لوحة صدارة نماذج الـ embedding" | قياس متعدّد المهام يغطّي الاسترجاع والتصنيف والتجميع: مفيد للفرز الأوّلي لكنه ليس بديلًا عن تقييم خاص بالمجال |
| Asymmetric embedding | "دالّتان مختلفتان للاستعلامات مقابل المستندات" | نماذج embedding مُدرّبة للتعامل مع عدم تماثل الاستعلام/المستند: استعلامات قصيرة تُحوّل إلى فضاء محسّن لاسترجاع مستندات أطول |
| Context window | "كم طول النص الذي يتعامل معه النموذج" | أقصى طول إدخال (بالـ tokens) يعالجه النموذج؛ النص بعده يُقلَّم بصمت: مصدر متكرّر لأخطاء الاسترجاع في المستندات الطويلة |

---

## قراءات إضافية

- [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard): رشّح حسب نوع مهمة "Retrieval"؛ رتّب حسب لغتك وحالة استخدامك ذات الصلة قبل اختيار نموذج
- [OpenAI Embeddings Documentation](https://platform.openai.com/docs/guides/embeddings): يغطّي تقليم الماتريوشكا، ومعامل dimensions، وحدود الدُفعات لنماذج text-embedding-3-*
- [Voyage AI Model Cards](https://docs.voyageai.com/docs/embeddings): يشرح أنواع إدخال الاستعلام مقابل المستند ومتى يُحسّن الـ embedding غير المتماثل الاسترجاع
- [BGE-M3: Multi-Functionality, Multi-Linguality, Multi-Granularity](https://arxiv.org/abs/2402.03216): الورقة وراء BGE-M3؛ تشرح كيف يمكن جمع embeddings dense + sparse + بأسلوب ColBERT من نموذج واحد
- [Matryoshka Representation Learning](https://arxiv.org/abs/2205.13147): الورقة الأصلية؛ تشرح إجراء التدريب الذي يجعل تقليم الماتريوشكا يعمل دون انهيار الجودة
