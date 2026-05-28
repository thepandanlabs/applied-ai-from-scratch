# مقاييس الاسترجاع (Retrieval Metrics)

> "النتائج تبدو ذات صلة" ليس تقييمًا. المقاييس هي التقييم.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** الدرس 05 (RAG البسيط)
**الوقت:** ~45 دقيقة
**المرحلة:** 02 · الاسترجاع و RAG

---

## أهداف التعلّم

- تنفيذ precision@K وrecall@K وMRR وnDCG@K ومعدّل الإصابة (hit rate) من الصفر بـ Python خالص
- شرح ما يقيسه كل مقياس ومتى يهمّ كلٌّ منها لنظام RAG إنتاجي
- تنفيذ المقياسين الخاصّين بـ RAG: دقة السياق (context precision) واسترجاع السياق (context recall)
- بناء مجموعة بيانات ذهبية مبسّطة (5 استعلامات) وتشغيل كل المقاييس عليها
- تفسير مخرجات المقاييس لتشخيص أي جزء من الاسترجاع ينبغي تحسينه

---

## المشكلة

نظام RAG لديك يسترجع خمس chunks. تبدو مرتبطة بالاستعلام. والإجابة تبدو صحيحة. تُطلقه. بعد ثلاثة أسابيع يُبلّغ عميل أنه يستشهد باستمرار بالأقسام الخاطئة وأحيانًا يُغفل الحقيقة الأساسية كليًا. ليس لديك أرقام. وليست لديك طريقة لمعرفة ما إذا كان التغيير الذي أجريته الثلاثاء الماضي أفاد أم أضرّ. وليس لديك خطّ أساس للمقارنة.

"يبدو ذا صلة" شعور. وليس مقياسًا. الأشاعر لا تنجو من تغيير في الـ codebase، أو تسليم بين الفِرق، أو مجموعة مستندات جديدة، أو ترقية نموذج. كل نظام إنتاجي يحتاج في النهاية رقمًا يستطيع تتبّعه عبر الزمن.

السبب الذي يجعل معظم الفِرق تتخطّى هذه الخطوة هو أن بناء مجموعة تقييم سليمة يبدو مكلفًا. وهو ليس كذلك. عشرون زوج استعلام/مستند ذي صلة يكتبها إنسان يعرف المجموعة تستغرق ساعتين. وتلك الساعتان تشتريان لك قياسًا قابلًا للتكرار يمكنك تشغيله في أقل من ثانية. بدونه، كل قرار ضبط: حجم الـ chunk، قيمة K، نموذج الـ embedding، البحث الهجين، إعادة الترتيب: تخمين. ومعه، تصبح قرارات الضبط تجارب لها نتائج.

---

## المفهوم

### ما الذي تقيسه هذه المقاييس فعلًا

يفترض تقييم الاسترجاع أن لديك مجموعة بيانات ذهبية: لكل استعلام، صنّف إنسان أي معرّفات مستندات ذات صلة. ثم تُشغّل نظام استرجاعك وتقارن ما أرجعه مقابل الحقيقة الأرضية.

```
Golden dataset:
  query_1 → relevant_docs = {doc_A, doc_B, doc_C}

Your retrieval at K=5:
  query_1 → retrieved_docs = [doc_A, doc_X, doc_B, doc_Y, doc_Z]
                               ✓       ✗       ✓      ✗      ✗
```

| المقياس | السؤال الذي يجيب عنه | الأفضل لـ |
|--------|-------------------|---------|
| **Precision@K** | من الـ K chunks التي استرجعتها، كم منها ذو صلة؟ | تقليل الضوضاء في السياق |
| **Recall@K** | من كل الـ chunks ذات الصلة، كم استرجعت ضمن أعلى K؟ | تعظيم التغطية (لا تُغفل الإجابة) |
| **Hit Rate** | هل كانت chunk واحدة ذات صلة على الأقل ضمن أعلى K؟ | الحدّ الأدنى للجدوى: هل النظام قابل للاستخدام أصلًا؟ |
| **MRR** | ما مدى ارتفاع أول نتيجة ذات صلة؟ | أنظمة الأسئلة والأجوبة حيث تقود النتيجة الأولى الإجابة |
| **nDCG@K** | ما جودة الترتيب الكامل، مرجّحًا نحو المواضع العليا؟ | جودة إعادة الترتيب، الاستعلامات متعددة الإجابات |
| **Context Precision** | من الـ chunks المُسترجَعة، أي جزء مفيد فعلًا؟ | التحكّم في انتفاخ نافذة السياق |
| **Context Recall** | هل يستطيع السياق المُسترجَع ترسيخ الإجابة المتوقَّعة كاملة؟ | كشف الإجابات الجزئية/الناقصة |

### مفاضلة الدقة مقابل الاسترجاع

رفع K يزيد الاسترجاع دائمًا (chunks أكثر = فرص أكثر لإصابة ذات الصلة) لكنه عادة يُنقص الدقة (chunks أكثر غير ذات صلة تُخفّف السياق). إيجاد نقطة عملك هو مشكلة ضبط الاسترجاع الجوهرية.

```
K=1:  High precision (1 chunk, probably relevant), Low recall (might miss most relevant docs)
K=20: Low precision (lots of noise), High recall (probably found them all)
K=5:  Typical operating point: balance noise vs coverage
```

### nDCG: لماذا يهمّ الموضع

كلتا نتيجتي الاسترجاع هاتين لهما precision@3 = 0.67 (2 من 3 ذات صلة)، لكنهما ليستا متساويتين في الجودة:

```
Result A: [relevant, relevant, irrelevant]   nDCG is higher
Result B: [irrelevant, relevant, relevant]   nDCG is lower
```

nDCG يعاقب وضع المستندات ذات الصلة أسفل القائمة المرتّبة. لنظام RAG، يهمّ هذا لأن الـ LLMs تولي انتباهًا أكبر للمحتوى قرب أعلى نافذة السياق. المحتوى ذو الصلة في الموضع 1 يساهم أكثر من المحتوى ذي الصلة في الموضع 5.

### دقة السياق واسترجاع السياق (خاصّان بـ RAG)

مقاييس استرجاع المعلومات (IR) القياسية تقيس ما إذا كانت المستندات المُسترجَعة تطابق وسم صلة. RAG يحتاج مقياسين إضافيين يربطان الاسترجاع بجودة الإجابة:

**دقة السياق (Context Precision)**: بمعلومية الـ chunks المُسترجَعة، أي جزء لازم فعلًا للإجابة عن السؤال؟ دقة سياق عالية تعني أن نافذة سياقك فعّالة: بلا حشو. ودقة سياق منخفضة تعني أنك تدفع مقابل tokens تُربك النموذج.

**استرجاع السياق (Context Recall)**: هل تستطيع الـ chunks المُسترجَعة دعم الإجابة المتوقَّعة كاملة؟ استرجاع سياق منخفض يعني أن النموذج سيضطرّ للهلوسة أو إعطاء إجابة جزئية، لا لأنه نموذج سيّئ، بل لأنك لم تعطه مادة كافية.

```
Expected answer: "The product was launched in March 2024 in the US market"
                  ─────────────────────────┬────────────────────────────
                                           │
Retrieved chunk A: "The product launched in March 2024"     → covers part 1
Retrieved chunk B: "The US rollout began first"             → covers part 2
Retrieved chunk C: "Revenue doubled year-over-year"         → irrelevant

Context Precision = 2/3 (2 of 3 retrieved chunks are useful)
Context Recall    = 1.0 (both required facts are present)
```

---

## البناء

### الخطوة 1: مجموعة البيانات الذهبية

```python
# No dependencies needed: pure Python.
# Usage: python main.py

# A minimal golden dataset.
# In production, this is written by a domain expert who reads the corpus
# and writes query/relevant_doc_id pairs. Start with 20 pairs minimum.
#
# Format: each query has a set of relevant doc IDs (ground truth)
# and a ranked list of retrieved doc IDs (system output to evaluate).

GOLDEN_DATASET = [
    {
        "query": "What is the recommended dosage for adults?",
        "relevant_ids": {"doc_3", "doc_7"},         # ground truth
        "retrieved_ids": ["doc_3", "doc_1", "doc_7", "doc_9", "doc_2"],  # system output
    },
    {
        "query": "How do I configure the authentication timeout?",
        "relevant_ids": {"doc_12"},
        "retrieved_ids": ["doc_5", "doc_12", "doc_8", "doc_3", "doc_14"],
    },
    {
        "query": "What are the contraindications for patients with liver disease?",
        "relevant_ids": {"doc_3", "doc_5", "doc_9"},
        "retrieved_ids": ["doc_3", "doc_9", "doc_2", "doc_5", "doc_11"],
    },
    {
        "query": "What version introduced the rate limiting feature?",
        "relevant_ids": {"doc_22"},
        "retrieved_ids": ["doc_1", "doc_4", "doc_6", "doc_22", "doc_9"],
    },
    {
        "query": "Explain the refund policy for digital products",
        "relevant_ids": {"doc_8", "doc_15"},
        "retrieved_ids": ["doc_15", "doc_8", "doc_3", "doc_1", "doc_7"],
    },
]
```

### الخطوة 2: Precision@K وRecall@K

```python
def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Of the top K retrieved documents, what fraction is relevant?
    Measures noise: a low value means you're filling the context window
    with irrelevant chunks.

    Range: 0.0 to 1.0
    """
    if k == 0:
        return 0.0
    top_k = retrieved_ids[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return hits / k


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Of all relevant documents, what fraction was retrieved in the top K?
    Measures coverage: a low value means the model won't have the answer
    because retrieval missed it.

    Range: 0.0 to 1.0
    If there are no relevant documents, recall is defined as 1.0 (vacuously true).
    """
    if not relevant_ids:
        return 1.0
    top_k = set(retrieved_ids[:k])
    hits = len(top_k & relevant_ids)
    return hits / len(relevant_ids)
```

### الخطوة 3: معدّل الإصابة (Hit Rate)

```python
def hit_rate_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Was at least one relevant document in the top K? Returns 1.0 or 0.0.

    This is the minimum useful metric for a RAG system.
    If hit_rate@5 is below 0.7, your system is broken for 30% of queries -
    the model literally cannot answer because retrieval returned nothing relevant.
    """
    top_k = set(retrieved_ids[:k])
    return 1.0 if top_k & relevant_ids else 0.0
```

### الخطوة 4: MRR: متوسّط الرتبة المعكوسة

```python
def reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    Reciprocal rank for a single query: 1/rank of the first relevant result.
    rank is 1-based.

    If the first result is relevant: RR = 1/1 = 1.0
    If the second result is first relevant: RR = 1/2 = 0.5
    If no relevant result in list: RR = 0.0

    Heavily penalizes putting the key document anywhere but position 1.
    Use MRR when you want the model to have the best single answer at the top.
    """
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(dataset: list[dict]) -> float:
    """
    MRR: average reciprocal rank across all queries.
    Interpretation:
      MRR = 1.0 → every query's first result is relevant
      MRR = 0.5 → on average, the first relevant result is at position 2
      MRR < 0.3 → retrieval is unreliable for production Q&A
    """
    if not dataset:
        return 0.0
    rr_scores = [
        reciprocal_rank(q["retrieved_ids"], q["relevant_ids"])
        for q in dataset
    ]
    return sum(rr_scores) / len(rr_scores)
```

### الخطوة 5: nDCG@K: المكسب التراكمي المخصوم المُطبَّع

```python
import math


def dcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Discounted Cumulative Gain at K.

    DCG rewards:
      - Finding relevant documents (adds to the gain)
      - Finding them early (divides by log2(rank + 1), so earlier = higher weight)

    For binary relevance (relevant=1, irrelevant=0):
      DCG@K = sum_{i=1}^{K} rel_i / log2(i + 1)
    """
    dcg = 0.0
    for rank, doc_id in enumerate(retrieved_ids[:k], start=1):
        if doc_id in relevant_ids:
            dcg += 1.0 / math.log2(rank + 1)
    return dcg


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """
    Normalized DCG@K: DCG divided by the ideal DCG.

    Ideal DCG assumes all relevant documents are ranked first.
    Normalizing to [0, 1] makes scores comparable across queries
    with different numbers of relevant documents.

    nDCG@K = 1.0 → perfect ranking (all relevant docs at the top)
    nDCG@K = 0.0 → no relevant documents retrieved
    """
    actual_dcg = dcg_at_k(retrieved_ids, relevant_ids, k)
    # Ideal: rank all relevant docs first, up to K
    n_relevant = min(len(relevant_ids), k)
    ideal_retrieved = list(relevant_ids)[:n_relevant]
    ideal_dcg = dcg_at_k(ideal_retrieved, relevant_ids, n_relevant)
    if ideal_dcg == 0.0:
        return 0.0
    return actual_dcg / ideal_dcg
```

### الخطوة 6: دقة السياق واسترجاع السياق (خاصّان بـ RAG)

```python
def context_precision(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    RAG-specific: of all retrieved chunks, what fraction is relevant?

    This is precision over the full retrieved list (not just top K).
    Low context precision means your prompt is bloated with noise.
    The LLM has to "find" the answer in a haystack of irrelevant chunks.

    Rule of thumb: context_precision below 0.5 → reduce K or add a
    minimum similarity score threshold to filter low-quality retrievals.
    """
    if not retrieved_ids:
        return 0.0
    hits = sum(1 for doc_id in retrieved_ids if doc_id in relevant_ids)
    return hits / len(retrieved_ids)


def context_recall(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    """
    RAG-specific: what fraction of relevant documents was retrieved?

    This is recall over the full retrieved list.
    Low context recall means the model cannot fully answer the question -
    not because it's hallucinating, but because you didn't give it enough.

    Rule of thumb: context_recall below 0.8 → increase K, re-chunk,
    or add hybrid search to catch what dense retrieval misses.
    """
    if not relevant_ids:
        return 1.0
    hits = sum(1 for doc_id in relevant_ids if doc_id in retrieved_ids)
    return hits / len(relevant_ids)
```

### الخطوة 7: تشغيل كل المقاييس معًا

```python
def evaluate_retrieval(dataset: list[dict], k: int = 5) -> dict:
    """
    Compute all retrieval metrics for a dataset of (query, relevant_ids, retrieved_ids) triples.
    Returns aggregate scores (averages across all queries) and per-query breakdowns.
    """
    per_query = []

    for item in dataset:
        retrieved = item["retrieved_ids"]
        relevant = item["relevant_ids"]

        scores = {
            "query": item["query"],
            f"precision@{k}": precision_at_k(retrieved, relevant, k),
            f"recall@{k}": recall_at_k(retrieved, relevant, k),
            f"hit_rate@{k}": hit_rate_at_k(retrieved, relevant, k),
            "reciprocal_rank": reciprocal_rank(retrieved, relevant),
            f"ndcg@{k}": ndcg_at_k(retrieved, relevant, k),
            "context_precision": context_precision(retrieved, relevant),
            "context_recall": context_recall(retrieved, relevant),
        }
        per_query.append(scores)

    # Aggregate metrics (mean across queries)
    metric_keys = [key for key in per_query[0] if key != "query"]
    aggregates = {}
    for key in metric_keys:
        aggregates[key] = sum(q[key] for q in per_query) / len(per_query)

    return {
        "aggregate": aggregates,
        "per_query": per_query,
        "k": k,
        "n_queries": len(dataset),
    }


def print_report(results: dict) -> None:
    """
    Print a readable metrics report with interpretation guidance.
    """
    k = results["k"]
    agg = results["aggregate"]

    print("\n" + "=" * 60)
    print(f"RETRIEVAL METRICS REPORT  (K={k}, N={results['n_queries']} queries)")
    print("=" * 60)

    print(f"\n  Precision@{k}      : {agg[f'precision@{k}']:.3f}   (of retrieved, fraction relevant)")
    print(f"  Recall@{k}         : {agg[f'recall@{k}']:.3f}   (of relevant, fraction retrieved)")
    print(f"  Hit Rate@{k}       : {agg[f'hit_rate@{k}']:.3f}   (queries with ≥1 relevant result)")
    print(f"  MRR              : {agg['reciprocal_rank']:.3f}   (how high up is first relevant result)")
    print(f"  nDCG@{k}          : {agg[f'ndcg@{k}']:.3f}   (ranking quality, position-weighted)")
    print(f"  Context Precision: {agg['context_precision']:.3f}   (retrieved chunks that are useful)")
    print(f"  Context Recall   : {agg['context_recall']:.3f}   (answer supportable by retrieved chunks)")

    print("\n--- Per-Query Breakdown ---")
    for q in results["per_query"]:
        print(f"\n  Query: {q['query'][:60]}...")
        print(f"    P@{k}={q[f'precision@{k}']:.2f}  R@{k}={q[f'recall@{k}']:.2f}  "
              f"HR={q[f'hit_rate@{k}']:.0f}  RR={q['reciprocal_rank']:.2f}  "
              f"nDCG={q[f'ndcg@{k}']:.2f}  CP={q['context_precision']:.2f}  CR={q['context_recall']:.2f}")

    print("\n--- Interpretation Guide ---")
    _interpret(agg, k)


def _interpret(agg: dict, k: int) -> None:
    """Print actionable interpretation based on metric values."""
    issues = []

    hit_rate = agg[f"hit_rate@{k}"]
    recall = agg[f"recall@{k}"]
    precision = agg[f"precision@{k}"]
    mrr = agg["reciprocal_rank"]
    cp = agg["context_precision"]
    cr = agg["context_recall"]
    ndcg = agg[f"ndcg@{k}"]

    if hit_rate < 0.7:
        issues.append(f"  [CRITICAL] Hit Rate@{k}={hit_rate:.2f}: retrieval is missing relevant docs "
                      f"for {(1-hit_rate)*100:.0f}% of queries. Fix: increase K, re-chunk, "
                      f"or switch embedding model.")

    if recall < 0.6:
        issues.append(f"  [HIGH] Recall@{k}={recall:.2f}: missing relevant docs too often. "
                      f"Fix: increase K, or add hybrid search (Lesson 07).")

    if precision < 0.4:
        issues.append(f"  [MEDIUM] Precision@{k}={precision:.2f}: too much noise in context. "
                      f"Fix: reduce K, add min_score threshold, or add reranker (Lesson 07).")

    if mrr < 0.4:
        issues.append(f"  [MEDIUM] MRR={mrr:.2f}: first relevant result is not near position 1. "
                      f"Fix: reranking or query transformation (Lesson 08).")

    if cp < 0.5:
        issues.append(f"  [MEDIUM] Context Precision={cp:.2f}: LLM context is more than half noise. "
                      f"Fix: add similarity threshold, reduce K, or add cross-encoder reranker.")

    if cr < 0.8:
        issues.append(f"  [HIGH] Context Recall={cr:.2f}: retrieved context cannot support full answers. "
                      f"Fix: increase K, fix chunking (splits key facts), or add multi-query (Lesson 08).")

    if ndcg < 0.5:
        issues.append(f"  [MEDIUM] nDCG@{k}={ndcg:.2f}: ranking quality is weak. "
                      f"Fix: add cross-encoder reranker or tune retrieval scoring.")

    if not issues:
        print("  All metrics look healthy. Consider tightening thresholds or expanding your eval set.")
    else:
        for issue in issues:
            print(issue)
```

### الخطوة 8: نقطة الدخول الرئيسية

```python
if __name__ == "__main__":
    print("Running retrieval metrics on sample golden dataset...")
    print(f"Dataset size: {len(GOLDEN_DATASET)} queries")

    results = evaluate_retrieval(GOLDEN_DATASET, k=5)
    print_report(results)

    # Show how metrics change with different K values
    print("\n\n--- Metrics at Different K Values ---")
    print(f"{'K':>4}  {'P@K':>8}  {'R@K':>8}  {'HR@K':>8}  {'MRR':>8}  {'nDCG@K':>8}")
    for k in [1, 3, 5, 10]:
        r = evaluate_retrieval(GOLDEN_DATASET, k=k)["aggregate"]
        print(f"{k:>4}  "
              f"{r[f'precision@{k}']:>8.3f}  "
              f"{r[f'recall@{k}']:>8.3f}  "
              f"{r[f'hit_rate@{k}']:>8.3f}  "
              f"{r['reciprocal_rank']:>8.3f}  "
              f"{r[f'ndcg@{k}']:>8.3f}")

    print("\nNote: Precision typically decreases as K increases.")
    print("      Recall typically increases as K increases.")
    print("      MRR is K-independent (based on full ranked list).")
```

> **اختبار من الواقع:** يراجع مدير المنتج لديك المخرجات ويقول: "النتائج تبدو لي ذات صلة عندما أتصفّحها، فلماذا نحتاج إلى كل هذه الأرقام؟ ماذا يقول لنا المقياس ولا يقوله فحص بشري عشوائي؟" كيف تشرح ما الذي تلتقطه المقاييس وتُفوّته معاينة بضع نتائج بالعين، خصوصًا حين يتغيّر النظام أو المجموعة عبر الزمن؟

---

## الاستخدام

في الإنتاج، لن تكتب هذه الدوال يدويًا. المكتبة القياسية هي `ranx`:

```python
from ranx import Qrels, Run, evaluate

# qrels: ground truth relevance judgments
qrels = Qrels({"q1": {"doc_3": 1, "doc_7": 1}, "q2": {"doc_12": 1}})

# run: your system's ranked retrieval results
run = Run({"q1": {"doc_3": 0.95, "doc_1": 0.82, "doc_7": 0.78}, "q2": {"doc_5": 0.91, "doc_12": 0.85}})

results = evaluate(qrels, run, ["precision@5", "recall@5", "mrr", "ndcg@5"])
```

RAGAS (الدرس 10) يضيف المقاييس الخاصّة بـ RAG مع تقييم بأسلوب LLM-as-judge لدقة السياق واسترجاع السياق: مفيد حين لا تستطيع وسم الصلة يدويًا لكل chunk.

مكتبة pytrec_eval تُغلّف عُدّة تقييم TREC المكتوبة بـ C وهي المعيار في أبحاث استرجاع المعلومات. استخدمها إن احتجت قابلية تكرار دقيقة مع القياسات المنشورة.

> **نقلة في المنظور:** مؤسّسك يقول: "المستخدمون يبدون راضين عن الإجابات اللي نطلقها. بناء مجموعة بيانات ذهبية وتشغيل بنية تقييم يأخذ وقتًا حقيقيًا. كيف نقرّر ما إذا كان هذا الاستثمار يستحقّ الآن، مقابل مجرّد إطلاق الميزات؟" ما الحجّة لفعل هذا قبل أن تكون لديك مشكلة ظاهرة، وما الذي يكلّفك إن تخطّيته وأضفته لاحقًا؟

---

## التسليم

مخرَج هذا الدرس هو المهارة في `outputs/skill-retrieval-evaluator.md`. ترشد عملية حساب وتفسير المقاييس لأي نظام RAG: ما تقيسه، وكيف تقرأ المخرجات، وما تُصلحه.

الأثر القابل للتشغيل هو `code/main.py`. شغّله بلا اعتماديات:

```bash
python main.py
```

سيطبع تقرير المقاييس الكامل على مجموعة البيانات العيّنة ويُظهر كيف تتغيّر المقاييس عبر قيم K.

---

## التقييم

**الفحص 1: ابدأ بمعدّل الإصابة.**
إن كان معدّل الإصابة عند الـ K الذي اخترته أقل من 0.7، فلا شيء آخر يهمّ: نظامك يفشل في استرجاع أي شيء ذي صلة لـ 30% من الاستعلامات. نقّح الاسترجاع (جودة نموذج الـ embedding، حجم K، حدود الـ chunk) قبل قياس أي شيء آخر.

**الفحص 2: ابنِ مجموعتك الذهبية على مجموعتك الفعلية، لا على نموذج تجريبي.**
المقاييس من مجموعة البيانات العيّنة في `main.py` توضيحية. المقاييس التي تهمّ هي على مجالك. مجموعة مستندات مالية ستكون لها خصائص تشغيل مختلفة عن قاعدة معرفة دعم العملاء. اكتب 20 زوج استعلام/مستند ذي صلة لبياناتك المحدّدة. حتى 20 كافية لكشف الانحدارات الكبرى.

**الفحص 3: شغّل المقاييس قبل وبعد كل تغيير في الاسترجاع.**
تغيير K، تبديل نموذج الـ embedding، ضبط حجم الـ chunk، إضافة البحث الهجين: كل تغيير يجب التحقّق منه بالمقاييس، لا بـ "جرّبت بضع استعلامات وبدت أفضل". سجّل الأرقام. ابنِ جدول مقارنة بسيطًا: التغيير → دلتا precision@5 → دلتا recall@5 → دلتا context_recall. التغييرات التي تُحسّن recall@5 بنسبة 10% مقابل تكلفة 5% في precision@5 غالبًا تستحقّ. والتغييرات التي تُحسّن الدقة بينما تُسقط الاسترجاع غالبًا لا تستحقّ.

---

## التمارين

1. **[سهل]** أضف `average_precision` (المساحة تحت منحنى الدقة-الاسترجاع لاستعلام واحد) إلى المقاييس لكل استعلام. ارسم الدقة مقابل الاسترجاع لاستعلام واحد وأنت تنوّع K من 1 إلى 10.

2. **[متوسط]** مجموعة البيانات الذهبية في `main.py` لها الصلة ثنائية (0 أو 1). وسّع nDCG لدعم الصلة المُدرّجة (0=غير ذي صلة، 1=ذو صلة إلى حدّ ما، 2=ذو صلة عالية). كيف تتغيّر صيغة nDCG؟ استخدم `2^rel - 1` كمكسب بدلًا من الثنائي 0/1.

3. **[صعب]** ابنِ سكربتًا يقرأ مخرجات RAG البسيط من الدرس 05 (حقل `retrieved_chunks` في dict النتيجة) ويقيّمها مقابل مجموعة بيانات ذهبية. ستحتاج إلى: (أ) إسناد معرّفات ثابتة للـ chunks أثناء الاستيعاب، (ب) كتابة 10 أزواج استعلام/معرّف-chunk-ذي-صلة يدويًا، (ج) تشغيل خطّ الأنابيب وجمع المعرّفات المُسترجَعة، (د) حساب كل المقاييس الستة. هذه هي حلقة التقييم الحقيقية.

---

## المصطلحات الأساسية

| المصطلح | ما يقوله الناس | ما يعنيه فعلًا |
|------|----------------|----------------------|
| Golden dataset | "مجموعة تقييم"، "وسوم الحقيقة الأرضية"، "مجموعة اختبار" | مجموعة منسّقة بشريًا من أزواج (query, relevant_doc_ids) تُستخدم لقياس جودة الاسترجاع موضوعيًا |
| Precision@K | "P@5" | نسبة المستندات الـ K العليا المُسترجَعة التي هي ذات صلة فعلًا |
| Recall@K | "R@5" | نسبة كل المستندات ذات الصلة التي تظهر ضمن الـ K العليا المُسترجَعة |
| Hit Rate | "HR@K"، "معدّل النجاح" | ما إذا كان مستند واحد ذو صلة على الأقل استُرجِع ضمن أعلى K؛ المقياس الأدنى للجدوى |
| MRR | "متوسّط الرتبة المعكوسة" | متوسّط 1/رتبة-أول-نتيجة-ذات-صلة عبر الاستعلامات؛ يعاقب المستندات ذات الصلة المدفونة في القائمة |
| nDCG | "المكسب التراكمي المخصوم المُطبَّع" | جودة ترتيب مرجّحة بالموضع؛ درجة 1.0 تعني أن كل مستند ذي صلة وُجد ورُتّب أولًا |
| Context Precision | "الدقة في RAG"، "دقة الـ chunk" | نسبة الـ chunks المُسترجَعة التي تساهم فعلًا في الإجابة عن الاستعلام |
| Context Recall | "تغطية الترسيخ" | ما إذا كان السياق المُسترجَع يحوي كل المعلومات اللازمة للإجابة عن السؤال |

---

## قراءات إضافية

- [BEIR Benchmark](https://arxiv.org/abs/2104.08663): قياس مرجعي قياسي لمقارنة أنظمة الاسترجاع عبر 18 مجموعة بيانات غير متجانسة؛ نقطة المرجع لتقييم نموذج الـ embedding
- [ranx Documentation](https://amenra.github.io/ranx/): أسرع مكتبة Python لمقاييس تقييم IR؛ بديل مباشر للكود في هذا الدرس
- [RAGAS Paper](https://arxiv.org/abs/2309.15217): الورقة المعتمَدة لمقاييس دقة/استرجاع السياق بأسلوب LLM-as-judge؛ اقرأها قبل بناء تقييم RAG آلي
- [Evaluating RAG Pipelines](https://www.pinecone.io/learn/series/rag/rag-evaluation/): شرح Pinecone للممارسين يربط مقاييس IR بجودة نظام RAG
- [MS MARCO Dataset](https://microsoft.github.io/msmarco/): القياس المرجعي القياسي لاسترجاع المقاطع؛ مصدر بيانات التدريب لمعظم نماذج الـ embedding التجارية
