# المخازن الشعاعية (Vector Stores)

> المخزن الشعاعي هو تشابه جيب التمام مُفهرَس على نطاق واسع. ابنِ واحدًا في 50 سطرًا، ثم افهم ما الذي يضيفه Qdrant فعلًا.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 02-01 الحدس وراء الـ Embeddings، 02-02 نماذج الـ Embedding
**الوقت:** ~75 دقيقة
**المرحلة:** 02 · الاسترجاع و RAG

## أهداف التعلّم

- تنفيذ مخزن شعاعي مبسّط في الذاكرة من الصفر مع الإضافة والبحث والترشيح والحذف
- شرح الفرق بين الفهرس المسطّح (flat index) وHNSW ومتى يناسب كلٌّ منهما
- استخدام Qdrant في الوضع المحلّي (بلا Docker، بلا خادم) ومقارنة واجهته بنسختك المصنوعة يدويًا
- وصف المفاضلات بين pgvector وقواعد البيانات الشعاعية المخصّصة والمخازن في الذاكرة
- بناء مجموعة تحقّق تلتقط أكثر أخطاء المخزن الشعاعي شيوعًا قبل أن تصل إلى الإنتاج

---

## المشكلة

اصطدم فريق يبني نظام RAG لقاعدة معرفة بعلّة محيّرة بعد ستة أسابيع من الإطلاق: أبلغ المستخدمون أن المستندات المرفوعة حديثًا لا تظهر في نتائج البحث، لكن نقطة نهاية الرفع تُرجع 200 OK. بعد يومين من التنقيح، وجدوا السبب الجذري: كانوا يُدرجون مستندات بمعرّفات (IDs) مكرّرة. ألحق المخزن الشعاعي إدخالًا ثانيًا بصمت لكل معرّف مكرّر بدلًا من تحديث الموجود، فكانت النسخة القديمة (المتقادمة) هي التي تُرجَع. المستند الجديد كان موجودًا: لكنه رُتّب ثانيًا بفارق ضئيل، وفازت النسخة المتقادمة عند المعرّف نفسه بقواعد فضّ التعادل.

هذه علّة صحّة في المخزن الشعاعي، لا مشكلة تعلّم آلة. بنى الفريق حزمته على الـ embeddings ومنطق الاسترجاع دون فهم البدائيات تحتها. لم يعرفوا أن دلالات التحديث (update semantics)، وسلوك إزالة التكرار، والترشيح تعمل بشكل مختلف عبر تطبيقات المخازن الشعاعية: ولم يكتبوا أي اختبارات تحقّق لالتقاط هذه الفروق.

تبدو المخازن الشعاعية بسيطة من الخارج: ضع الأشياء، واسترجع الأشياء المتشابهة. لكن أنظمة الإنتاج تفشل بالضبط عند الحواف التي تبدو بسيطة: الإدخالات المتقادمة بعد التحديثات، وعلل الترشيح التي تُرجع صفر نتيجة بصمت، وانجراف الفهرس (index drift) حين تُغيّر نماذج الـ embedding، وعدم تطابق العدّ بين نظامك المصدري وما هو مُفهرَس فعلًا. فهم البنية الداخلية يستغرق 30 دقيقة ويمنع أيامًا من التنقيح.

---

## المفهوم

### ما هو الفهرس الشعاعي فعلًا

في جوهره، يحمل المخزن الشعاعي شيئين:
1. مصفوفة من أشعّة الـ embedding: بالشكل `(N, D)` حيث N عدد المستندات وD بُعد الـ embedding
2. بيانات وصفية (metadata) لكل شعاع: النص الأصلي، ومعرّف المستند، وأي حقول قابلة للترشيح

عملية البحث تحسب التشابه بين شعاع الاستعلام وكل شعاع مخزّن، ثم تُرجع أعلى K.

**الفهرس المسطّح (القوّة الغاشمة):** احسب التشابه مقابل كل شعاع. نتائج دقيقة. O(N) لكل استعلام.
- يعمل جيدًا حتى ~100K شعاع على آلة واحدة (أجزاء من الثانية لكل استعلام)
- فوق ذلك، يصبح زمن الاستجابة مشكلة

**HNSW (Hierarchical Navigable Small World):** خوارزمية جار أقرب تقريبية (approximate nearest neighbor). تبني رسمًا بيانيًا متعدّد الطبقات حيث يتّصل كل عقدة بأقرب جيرانها على مقاييس متعدّدة. البحث يتنقّل في الرسم بدلًا من فحص كل شيء.
- O(log N) لكل استعلام بدلًا من O(N)
- يُرجع نتائج تقريبية: قد لا يكون الجار الأقرب الحقيقي في مجموعة النتائج
- "الاسترجاع" (recall) بنسبة 95–99% أمر معتاد (95% من الاستعلامات تُرجع الجار الأقرب الحقيقي)
- يستخدمه Qdrant وWeaviate وPinecone وpgvector (اختياري)

```
Flat Index: check every point             HNSW: navigate the graph
                                                      
  Query ──► [doc1] sim=0.72               Query ──► Layer 2 (coarse)
            [doc2] sim=0.45                         │
            [doc3] sim=0.91  ← top      ──► Layer 1 (medium)
            [doc4] sim=0.38                         │
            ...every doc...             ──► Layer 0 (fine) ──► top-K
                                                      
  Exact. Slow at scale.                 Approximate. Fast at scale.
```

### عمليات CRUD

يحتاج المخزن الشعاعي الإنتاجي إلى أكثر من مجرّد البحث:

```
add(id, vector, metadata)     → insert a new document
search(query_vector, top_k, filter)  → retrieve similar documents
get(id)                       → retrieve a document by ID
delete(id)                    → remove a document
update(id, new_vector, new_metadata) → replace a document (delete + add)
count()                       → how many documents are indexed
```

التحديث يُنفّذ دائمًا تقريبًا كحذف + إضافة، لأن تعديل شعاع في فهرس بياني مكلِف. هذا يعني أن تطبيقك يجب أن يتعامل مع حالة كون المستند في طور التحديث (غائبًا عن الفهرس لوهلة).

### ترشيح البيانات الوصفية

يتيح لك ترشيح البيانات الوصفية تقييد البحث في مجموعة فرعية من المستندات قبل (أو بعد) مقارنة الأشعّة.

```
Pre-filter: reduce the candidate set first, then search within it
  → Example: filter to user_id = "alice", then search her documents only
  → Risk: if the filtered set is small, HNSW accuracy drops (fewer neighbors)

Post-filter: search broadly, then remove results that fail the filter
  → Example: search top-100, then drop any that aren't status="published"
  → Risk: you may not get K results if many are filtered out
```

معظم المخازن الشعاعية الإنتاجية (Qdrant، Weaviate، Pinecone) تستخدم نهجًا هجينًا: ترشيح مسبق (pre-filter) للمرشّحات الانتقائية (تُزيل > 90% من المستندات)، وترشيح لاحق (post-filter) للمرشّحات الفضفاضة. يُظهر Qdrant هذا صراحةً كـ `filter` في واجهة بحثه.

الحقول الشائعة القابلة للترشيح في أنظمة RAG الإنتاجية:
- `tenant_id` / `user_id`: عزل البيانات متعدّد المستأجرين
- `doc_type`: التقييد على المقالات مقابل مقتطفات الكود مقابل الأسئلة الشائعة
- `created_at`: ترشيح الحداثة
- `language`: استرجاع أحادي اللغة من مجموعة متعدّدة اللغات
- `status`: البحث فقط في المحتوى المنشور/المعتمَد

### طيف التخزين

```
           Speed       Cost      Persistence   Scale     Ops Complexity
In-memory   ████████    Free      None          Small     Zero
────────────────────────────────────────────────────────────────────────
pgvector    █████       Cheap     Postgres      Medium    Low (in existing DB)
────────────────────────────────────────────────────────────────────────
Qdrant      ████████    Medium    File/Cloud    Large     Medium
────────────────────────────────────────────────────────────────────────
Pinecone    ████████    $$$$      Cloud         Very large Zero (managed)
Weaviate    ███████     Medium    File/Cloud    Large     Medium
────────────────────────────────────────────────────────────────────────
```

**قاعدة القرار:**

- التطوير / النماذج الأوّلية → في الذاكرة (صنفك المخصّص أو وضع `qdrant-client` المحلّي)
- تستخدم Postgres أصلًا → pgvector أولًا. بجدّ.
- تحتاج ANN عند > 1M شعاع دون تشغيل بنيتك التحتية → Pinecone أو Qdrant Cloud
- تحتاج بحثًا هجينًا (dense + sparse في استعلام واحد) → Qdrant أو Weaviate (كلاهما يدعمه أصليًا)
- تحتاج نصًا كاملًا + شعاعًا في استعلام واحد → pgvector + pg_bm25 (ParadeDB)، أو Elasticsearch بحقول شعاعية

**متى يكفي pgvector:**

pgvector مُبخَس القدر. إن كانت مجموعتك أقل من 5M شعاع، وفريقك يشغّل Postgres أصلًا، وهدف زمن استجابة استعلامك < 100ms، فإن pgvector يغطّي حالة الاستخدام. نسخة Postgres واحدة مع pgvector وفهرس HNSW تتعامل مع 5M شعاع عند 30–50ms لكل استعلام. لا تُضِف تعقيدًا تشغيليًا لا تحتاجه.

---

## البناء

### الخطوة 1: تعريف الواجهة

ابدأ بالواجهة، لا بالتنفيذ. المخزن الشعاعي عقد:

```python
# pip install numpy qdrant-client sentence-transformers

import numpy as np
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SearchResult:
    id: str
    score: float
    text: str
    metadata: dict[str, Any]
```

### الخطوة 2: بناء المخزن الشعاعي في الذاكرة

```python
import math

class InMemoryVectorStore:
    """
    Minimal vector store backed by a Python dict and NumPy matrix operations.
    
    Designed to be fully transparent: you can read every line and understand
    exactly what a vector store does. Not for production at scale (no ANN index),
    but correct and useful up to ~100K vectors.
    """

    def __init__(self) -> None:
        # Store vectors and metadata separately for O(1) ID lookup
        self._vectors: dict[str, np.ndarray] = {}
        self._texts: dict[str, str] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(
        self,
        doc_id: str,
        text: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Add a document to the store.
        If doc_id already exists, this raises an error to prevent silent duplicates.
        Use upsert() if you want update semantics.
        """
        if doc_id in self._vectors:
            raise ValueError(
                f"Document '{doc_id}' already exists. Use upsert() to overwrite."
            )
        self._vectors[doc_id] = vector / (np.linalg.norm(vector) or 1.0)  # normalize on insert
        self._texts[doc_id] = text
        self._metadata[doc_id] = metadata or {}

    def upsert(
        self,
        doc_id: str,
        text: str,
        vector: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert or replace. Safe for update workflows."""
        self._vectors[doc_id] = vector / (np.linalg.norm(vector) or 1.0)
        self._texts[doc_id] = text
        self._metadata[doc_id] = metadata or {}

    def delete(self, doc_id: str) -> bool:
        """Remove a document. Returns True if it existed, False if not found."""
        if doc_id not in self._vectors:
            return False
        del self._vectors[doc_id]
        del self._texts[doc_id]
        del self._metadata[doc_id]
        return True

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, doc_id: str) -> SearchResult | None:
        """Retrieve a document by ID."""
        if doc_id not in self._vectors:
            return None
        return SearchResult(
            id=doc_id,
            score=1.0,
            text=self._texts[doc_id],
            metadata=self._metadata[doc_id],
        )

    def count(self) -> int:
        return len(self._vectors)

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Find the top_k most similar documents.
        
        filter_metadata: optional dict of {field: value}: only documents
        where ALL fields match are included in the search.
        
        Implementation: brute-force cosine similarity (exact results).
        For N > 100K, use an ANN index instead.
        """
        if not self._vectors:
            return []

        query_norm = query_vector / (np.linalg.norm(query_vector) or 1.0)

        # Determine candidate IDs (apply pre-filter)
        candidates = list(self._vectors.keys())
        if filter_metadata:
            candidates = [
                doc_id for doc_id in candidates
                if all(
                    self._metadata[doc_id].get(k) == v
                    for k, v in filter_metadata.items()
                )
            ]

        if not candidates:
            return []

        # Stack candidate vectors into a matrix for batch dot product
        ids = candidates
        matrix = np.stack([self._vectors[i] for i in ids])  # (N, D)
        scores = matrix @ query_norm  # (N,)

        # Top-K selection
        k = min(top_k, len(ids))
        top_indices = np.argpartition(scores, -k)[-k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        return [
            SearchResult(
                id=ids[i],
                score=float(scores[i]),
                text=self._texts[ids[i]],
                metadata=self._metadata[ids[i]],
            )
            for i in top_indices
        ]
```

### الخطوة 3: اختبر كل الحالات الحدّية

قبل الوثوق بمخزن شعاعي في الإنتاج، مارِس كل عملية:

```python
def test_vector_store(store: InMemoryVectorStore) -> None:
    """Verify all store operations work correctly."""
    
    # Setup: create some test vectors
    v1 = np.array([1.0, 0.0, 0.0])
    v2 = np.array([0.9, 0.1, 0.0])   # very similar to v1
    v3 = np.array([0.0, 0.0, 1.0])   # unrelated

    # Test 1: basic add and count
    store.add("doc_1", "first document", v1, {"type": "article", "user": "alice"})
    store.add("doc_2", "second document", v2, {"type": "article", "user": "bob"})
    store.add("doc_3", "third document", v3, {"type": "faq", "user": "alice"})
    assert store.count() == 3, "count should be 3 after 3 adds"

    # Test 2: search returns most similar first
    results = store.search(v1, top_k=2)
    assert results[0].id == "doc_1", f"expected doc_1 first, got {results[0].id}"
    assert results[1].id == "doc_2", f"expected doc_2 second, got {results[1].id}"
    assert results[0].score > results[1].score, "scores should be descending"

    # Test 3: metadata filter
    alice_results = store.search(v1, top_k=5, filter_metadata={"user": "alice"})
    assert all(r.metadata["user"] == "alice" for r in alice_results), \
        "filter should only return alice's documents"
    assert len(alice_results) == 2, f"alice has 2 docs, got {len(alice_results)}"

    # Test 4: delete
    deleted = store.delete("doc_2")
    assert deleted is True, "delete should return True for existing doc"
    assert store.count() == 2, "count should decrease after delete"
    assert store.get("doc_2") is None, "deleted doc should not be retrievable"

    # Test 5: delete nonexistent returns False
    deleted = store.delete("does_not_exist")
    assert deleted is False, "deleting a nonexistent doc should return False"

    # Test 6: upsert (update)
    store.upsert("doc_1", "updated text", v3, {"type": "article", "user": "alice"})
    updated = store.get("doc_1")
    assert updated.text == "updated text", "upsert should update text"
    # After update, doc_1 now has v3's direction: should be similar to doc_3
    results = store.search(v3, top_k=2)
    assert any(r.id == "doc_1" for r in results), \
        "after upsert, doc_1 should appear in search results for its new vector"

    # Test 7: duplicate add raises error
    try:
        store.add("doc_1", "duplicate", v1)
        assert False, "duplicate add should raise ValueError"
    except ValueError:
        pass  # expected

    # Test 8: empty filter returns zero results gracefully
    no_results = store.search(v1, top_k=5, filter_metadata={"user": "nobody"})
    assert no_results == [], "filter with no matches should return empty list"

    print("[PASS] All vector store tests passed")
```

> **اختبار من الواقع:** المدير التقني لشركتك الناشئة يرى هذا ويقول: "هذا 50 سطر بايثون. ليش ندفع 70 دولار شهريًا لـ Pinecone واحنا نقدر نستخدم هذا؟" ما الجواب الصادق: ما الذي يتعامل معه هذا التنفيذ جيدًا، وما الأشياء المحدّدة التي قد تنهار في الإنتاج ويتولّاها لك Pinecone؟

### الخطوة 4: استخدم Qdrant في الوضع المحلّي

يدعم Qdrant التشغيل بالكامل داخل العملية بلا خادم، بلا Docker، بلا استدعاءات شبكة. تُديم المكتبة البيانات إلى دليل محلّي (أو تُبقيها في الذاكرة).

```python
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
)

def build_qdrant_store(documents: list[dict]) -> QdrantClient:
    """
    Build a Qdrant collection in local mode.
    
    ':memory:' → in-process, no persistence (like our InMemoryVectorStore)
    path='/tmp/qdrant_db' → file-backed persistence (survives restarts)
    """
    client = QdrantClient(":memory:")

    dim = len(documents[0]["vector"])
    collection_name = "docs"

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

    # Batch upsert: Qdrant uses integer IDs or UUIDs by default
    # We pass our string IDs as payload metadata
    points = [
        PointStruct(
            id=idx,
            vector=doc["vector"].tolist(),
            payload={
                "doc_id": doc["id"],
                "text": doc["text"],
                **doc.get("metadata", {}),
            },
        )
        for idx, doc in enumerate(documents)
    ]

    client.upsert(collection_name=collection_name, points=points)
    return client, collection_name


def qdrant_search(
    client: QdrantClient,
    collection_name: str,
    query_vector: np.ndarray,
    top_k: int = 5,
    filter_field: str | None = None,
    filter_value: Any | None = None,
) -> list[SearchResult]:
    """Search a Qdrant collection with optional metadata filtering."""
    query_filter = None
    if filter_field and filter_value is not None:
        query_filter = Filter(
            must=[FieldCondition(key=filter_field, match=MatchValue(value=filter_value))]
        )

    hits = client.search(
        collection_name=collection_name,
        query_vector=query_vector.tolist(),
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    return [
        SearchResult(
            id=hit.payload.get("doc_id", str(hit.id)),
            score=hit.score,
            text=hit.payload.get("text", ""),
            metadata={k: v for k, v in hit.payload.items() if k not in ("doc_id", "text")},
        )
        for hit in hits
    ]
```

---

## الاستخدام

واجهة Qdrant أكثر تعبيرًا من مخزننا المصنوع يدويًا بأربع طرق رئيسية:

| الميزة | InMemoryVectorStore | Qdrant |
|---|---|---|
| نوع الفهرس | مسطّح (دقيق) | HNSW (تقريبي، قابل للضبط) |
| دعم الترشيح | مساواة أساسية | غني: مدى، جغرافي، متداخل |
| الإدامة | الذاكرة فقط | الذاكرة أو مدعوم بملف |
| الأشعّة المسمّاة | لا | نعم (أشعّة متعددة لكل مستند) |
| فهرسة الـ payload | لا | نعم (حقول الترشيح فقط مُفهرَسة للسرعة) |
| التمرير/التصفّح (pagination) | لا | نعم |
| المجموعات (Collections) | واحدة | كثيرة |

الأشعّة المسمّاة مفيدة بشكل خاص للبحث الهجين (الدرس 07): خزّن شعاعًا dense وشعاعًا sparse للمستند نفسه في نقطة Qdrant واحدة، ثم استعلم كليهما في عملية واحدة.

إعداد Qdrant المحلّي الكامل لنموذج إنتاجي أوّلي يبدو هكذا:

```python
# Persistent local storage: no Docker, no server
client = QdrantClient(path="./qdrant_data")

# With named vectors for future hybrid search
from qdrant_client.models import NamedVector

client.create_collection(
    "my_docs",
    vectors_config={
        "dense": VectorParams(size=1536, distance=Distance.COSINE),
    }
)

# When you're ready for a server, just change the client init:
# client = QdrantClient(url="http://localhost:6333")
# client = QdrantClient(url="https://xyz.cloud.qdrant.io", api_key="...")
# The rest of your code is unchanged.
```

هذا هو مسار الانتقال الإنتاجي: طوّر بـ `:memory:`، وانتقل إلى `path=` للتطوير المحلّي المُدام، ثم بدّل إلى عنوان URL المستضاف للإنتاج: تغيير سطر واحد.

> **نقلة في المنظور:** مهندس العمليات لديك يقول: "احنا أصلًا نشغّل Postgres لكل شيء آخر. ليش تشغّل خدمة ثانية بـ Qdrant بدلًا من مجرّد استخدام pgvector؟" ما المفاضلة الحقيقية هنا، وتحت أي شروط ستقول لهم إنهم محقّون؟

---

## التسليم

ينتج هذا الدرس مخزنًا شعاعيًا قائمًا بذاته يمكنك استخدامه لأي مشروع لا يحتاج بعد قاعدة بيانات شعاعية مخصّصة.

**الأثر (Artifact):** `03-vector-stores/outputs/skill-vector-store-setup.md`

ملف المهارة يرشد إلى اختيار وتهيئة مخزن شعاعي لحالة استخدام معيّنة، ويغطّي المسار الكامل من التطوير المحلّي مرورًا بـ Qdrant المستضاف وصولًا إلى pgvector.

يوفّر `code/main.py` كلا التنفيذين جنبًا إلى جنب مع اختبار مقارنة يشغّل كليهما على البيانات نفسها ويتحقّق من أنهما يُرجعان نتائج متكافئة.

---

## التقييم

علل المخزن الشعاعي خبيثة لأن النظام يبدو وكأنه يعمل: تُرجع لك نتائج، وتبدو معقولة، ولا يكشف إلا القياس الدقيق أنها خاطئة أو متقادمة.

**الفحص 1: تكافؤ العدّ**

عدّ المستندات في مخزنك الشعاعي يجب أن يطابق نظامك المصدري. إن فهرست 50,000 مستند، فيجب أن يحوي المخزن 50,000 شعاع. عدم التطابق = فشل فهرسة صامت.

```python
# Run this after every bulk indexing job
expected_count = len(source_documents)
actual_count = store.count()  # or: client.count(collection_name).count
if actual_count != expected_count:
    print(f"WARNING: count mismatch! expected {expected_count}, got {actual_count}")
    # Investigate: look for failed upserts, duplicate IDs, or skipped documents
```

**الفحص 2: كشف الإدخالات المتقادمة**

إن كانت مستنداتك تُحدَّث (صفحات ويكي، توثيق منتجات، مقالات قاعدة معرفة)، تحقّق من أن عمليات البحث تُرجع المحتوى الحالي، لا النسخ القديمة:

```python
def check_for_stale_entries(store, source_docs: dict[str, str]) -> list[str]:
    """
    For each document in source_docs, retrieve it from the store
    and check whether the stored text matches the current source.
    Returns a list of stale document IDs.
    """
    stale_ids = []
    for doc_id, current_text in source_docs.items():
        stored = store.get(doc_id)
        if stored is None:
            print(f"MISSING: {doc_id} not in store")
        elif stored.text != current_text:
            stale_ids.append(doc_id)
    return stale_ids
```

**الفحص 3: صحّة الترشيح**

مرشّحات البيانات الوصفية مصدر متكرّر للعلل الصامتة: خطأ مطبعي في اسم حقل يُرجع صفر نتيجة، ما يبدو وكأنه "لا مستندات مطابقة" بدلًا من "المرشّح معطوب".

```python
def verify_filter(store, filter_field: str, expected_value, expected_min_count: int) -> None:
    """
    Verify that a metadata filter returns at least expected_min_count results.
    If it returns zero, the filter is likely misconfigured.
    """
    # Use a random query vector (just checking filter, not relevance)
    dummy_query = np.random.randn(384)
    results = store.search(dummy_query, top_k=10, filter_metadata={filter_field: expected_value})
    if len(results) < expected_min_count:
        print(
            f"WARNING: filter {filter_field}={expected_value!r} "
            f"returned {len(results)} results, expected >= {expected_min_count}. "
            f"Check field name spelling and value type."
        )
    else:
        print(f"[OK] filter {filter_field}={expected_value!r} → {len(results)} results")
```

---

## التمارين

1. **سهل:** أضف دالة `list_all(limit=100)` إلى `InMemoryVectorStore` تُرجع المستندات المضافة حديثًا. اختبرها مع مجموعة من 20 مستندًا.

2. **متوسط:** نفّذ دالة `rebuild_index(documents)` تستبدل كل الأشعّة في المخزن ذرّيًا (atomically): مفيدة لإعادة الفهرسة بعد تغيير نماذج الـ embedding. ينبغي أن تكون آمنة: إن فشلت إعادة البناء في منتصف الطريق، يجب أن يبقى الفهرس القديم سليمًا. تلميح: ابنِ الفهرس الجديد في مخزن مؤقّت، ثم بدّل المراجع.

3. **صعب:** وسّع `InMemoryVectorStore` لدعم تعبيرات ترشيح AND/OR، لا المساواة المسطّحة فقط: `filter={"AND": [{"user": "alice"}, {"type": "article"}]}`. اكتب مُحلّل ترشيح يتعامل مع منطق AND وOR وNOT. قِس ما إذا كان تنفيذ الترشيح سريعًا بما يكفي لـ 50K مستند (الهدف: < 20ms لاستعلام نموذجي بمرشّح).

---

## المصطلحات الأساسية

| المصطلح | ما يقوله الناس | ما يعنيه فعلًا |
|------|----------------|----------------------|
| HNSW | "فهرس الرسم البياني الذي تستخدمه قواعد البيانات الشعاعية" | Hierarchical Navigable Small World: رسم جار أقرب تقريبي يتيح بحث O(log N)؛ يقايض جزءًا صغيرًا من الاسترجاع مقابل زمن استجابة أفضل بأضعاف على نطاق واسع |
| Flat index | "بحث القوّة الغاشمة" | تشابه جيب تمام دقيق مقابل كل شعاع؛ صحيح لكنه O(N)؛ مناسب لأقل من 100K شعاع |
| Metadata filter | "تقييد البحث في مجموعة فرعية" | شرط يُطبَّق قبل أو بعد البحث بالتشابه الشعاعي لتقييد النتائج على المستندات المطابقة لقيم حقول معيّنة |
| Collection | "مجال أسماء شعاعي" | مجموعة مسمّاة من الأشعّة ببُعد متّسق ومقياس مسافة؛ يكافئ جدولًا في قاعدة بيانات علائقية |
| Payload | "بيانات وصفية مخزّنة مع شعاع" | بمصطلحات Qdrant: كائن JSON المخزّن بجانب كل شعاع، يحوي النص الأصلي وأي حقول قابلة للترشيح |

---

## قراءات إضافية

- [Qdrant Documentation: Quick Start](https://qdrant.tech/documentation/quick-start/): الدليل الرسمي لـ Qdrant المحلّي والمبني على الخادم؛ يغطّي المجموعات والـ upsert والبحث والترشيح
- [pgvector GitHub](https://github.com/pgvector/pgvector): امتداد Postgres للتخزين الشعاعي؛ يشمل الإعداد وإنشاء فهرس HNSW وقياسات الأداء
- [Approximate Nearest Neighbor Search in High Dimensions (Andoni et al.)](https://arxiv.org/abs/1806.09823): مسح سهل القراءة لخوارزميات ANN؛ يشرح لماذا تتوقّف القوّة الغاشمة عن العمل وما الذي يفعله HNSW وLSH وIVF بشكل مختلف
- [When to NOT Use a Vector Database](https://qdrant.tech/blog/vector-search-production-spikes/): إرشاد عملي حول البقاء مع Postgres+pgvector مقابل الانتقال إلى مخزن مخصّص
- [Pinecone: Vector Databases Explained](https://www.pinecone.io/learn/vector-database/): شرح موجز للترشيح ودلالات CRUD وأنماط عزل مجال الأسماء في المخازن الشعاعية الإنتاجية
