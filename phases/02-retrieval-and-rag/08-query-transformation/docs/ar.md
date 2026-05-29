# تحويل الاستعلام (Query Transformation)

> الاستعلام الذي يكتبه المستخدم نادرًا ما يكون أفضل استعلام للاسترجاع (retrieval). حوّله قبل أن تبحث.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** الدرس 05 (naive RAG)، الدرس 06 (مقاييس الاسترجاع)
**الوقت:** ~50 دقيقة
**المرحلة:** 02 · الاسترجاع و RAG

---

## أهداف التعلّم

- شرح لماذا يكون استعلام المستخدم الخام استعلام استرجاع ضعيفًا في معظم أنظمة الإنتاج
- تطبيق أربع تقنيات لتحويل الاستعلام: إعادة الصياغة (rewriting)، و HyDE، و step-back prompting، و multi-query
- معرفة متى تطبّق كل تقنية ومتى يضيف التحويل تكلفة دون فائدة
- قياس التحسّن في الـ recall الناتج عن التحويل على مجموعة اختبار

---

## المشكلة

تخيّل نظام توثيق طبي. يسأل طبيب: "is aspirin safe after a bleed?" المستند الذي يجيب عن هذا السؤال يحتوي على عبارة "salicylates are contraindicated following hemorrhagic events." التشابه في الـ embedding بين استعلام الطبيب والمقطع ذي الصلة منخفض: المفردات مختلفة، والصياغة سريرية مقابل عامية، والمقطع يعالج مفهومًا أعمّ مما يطرحه السؤال المحدد.

نظام naive RAG من الدرس 05 يحوّل الاستعلام الخام إلى embedding ويبحث عن أقرب chunk. يسترجع chunks عن تأثير الأسبرين المضاد للصفائح الدموية، وإرشادات الجرعات، والتفاعلات الدوائية: كلها ذات صلة تقنيًا، وكلها تفتقد الحقيقة المحددة التي يحتاجها الطبيب. الإجابة التي ينتجها النظام مراوغة وناقصة. لا يعرف الطبيب هل فشل النظام أم أن الإجابة فعلًا غير موجودة في المتن (corpus).

هذه مشكلة مفردات في الاسترجاع، وهي متفشّية في الأنظمة الحقيقية. يكتب المستخدمون استعلاماتهم بكلماتهم الخاصة. وتُكتب المستندات من قِبل أشخاص آخرين في سياق مختلف. تلتقط نماذج الـ embedding جزءًا من هذه الفجوة، لكنها لا تستطيع سدّها بالكامل: خصوصًا للاستعلامات القصيرة أو العامية أو شديدة التحديد. الحل ليس نموذج embedding أفضل. الحل هو تحويل الاستعلام إلى شيء يسترجع بشكل أفضل قبل أن يصل أصلًا إلى الـ vector store.

---

## المفهوم

### لماذا الاستعلامات الخام استعلامات استرجاع ضعيفة

| المشكلة | المثال | الأثر |
|---------|---------|--------|
| قصير جدًا، سياق قليل جدًا | "authentication timeout" | الـ embedding غير محدد بدقة؛ يسترجع تطابقات غامضة كثيرة |
| مفردات مختلفة عن المستند | "is it safe" vs "contraindicated" | تشابه cosine منخفض رغم التكافؤ الدلالي |
| ضمائر شخصية وسياق ضمني | "how do I fix the error I got?" | الـ embedding يرمّز الضمائر بدلًا من السؤال الفعلي |
| مفرط في التحديد، يفوّت السياق الأوسع | "CVE-2024-41110 in libssl 3.2.1" | استعلام شديد التحديد يفوّت القسم الأعمّ ذا الصلة |
| غامض | "Python environment setup" | قد يعني virtualenv أو conda أو إعداد الـ IDE |

### أربع تقنيات

**إعادة صياغة الاستعلام (Query Rewriting)** هي أبسط تقنية. تطلب من LLM أن يعيد صياغة سؤال المستخدم كاستعلام استرجاع أفضل: أكثر تحديدًا، مفردات موسّعة، دون ضمائر أو إشارات غامضة. تنفع في معظم الحالات.

**HyDE (Hypothetical Document Embeddings)** مبنيّة على رؤية مخالفة للبديهة: عندما تحوّل السؤال "what is the capital of France?" إلى embedding، يحتل المتجه الناتج جزءًا مختلفًا من فضاء الـ embedding عن نص المستند "Paris is the capital of France." للأسئلة والإجابات أنماط لغوية مختلفة. بدلًا من تحويل السؤال إلى embedding، تطلب HyDE من LLM توليد إجابة افتراضية: مستند معقول من شأنه أن يجيب عن السؤال: وتحوّل تلك الإجابة إلى embedding عوضًا عنه. تعيش الإجابة الافتراضية في الجزء نفسه من فضاء الـ embedding الذي تعيش فيه الإجابات الحقيقية.

**Step-Back Prompting** تعالج مشكلة الإفراط في التحديد. عندما يسأل المستخدم عن تفاعل دواء-جرعة محدد، فإن السياق ذا الصلة غالبًا ما يكون عند مستوى تجريد أعلى: آلية عمل فئة الدواء، أو قواعد موانع الاستخدام العامة. step-back تولّد نسخة أعمّ من الاستعلام تسترجع السياق الخلفي اللازم للإجابة عن السؤال المحدد.

**Multi-Query** تولّد N صياغة مختلفة للسؤال نفسه، وتسترجع لكل منها، وتزيل التكرار، ثم تدمج. تقايض زمن الاستجابة (latency) وحوسبة الـ LLM مقابل recall أعلى. مفيدة للاستعلامات الغامضة أو المبهمة حين تكون الصياغة الصحيحة مجهولة.

### دليل اختيار التقنية

```
Is the query clear and specific enough?
  ├─ NO (vague, short, pronoun-heavy) ──► Query Rewriting (always try first)
  └─ YES
       │
       Is the document vocabulary very different from query vocabulary?
       ├─ YES (academic→informal, clinical→colloquial) ──► HyDE
       └─ NO
            │
            Is the question very specific but the relevant context is broader?
            ├─ YES (specific drug → drug class context) ──► Step-Back
            └─ NO
                 │
                 Is the query ambiguous or could be interpreted multiple ways?
                 ├─ YES ──► Multi-Query
                 └─ NO ──► No transformation needed
```

### متى لا تحوّل

| السيناريو | لماذا تتخطى التحويل |
|----------|--------------------------|
| الاستعلام دقيق جدًا أصلًا | إضافة كلمات قد تُدخل مصطلحات مهلوسة تضرّ بالاسترجاع |
| مطلوب زمن استجابة منخفض جدًا (< 50ms) | كل استدعاء LLM يضيف 200-500ms |
| مفردات المتن والاستعلام متطابقة جيدًا | التحويل يضيف تكلفة دون تحسّن في الـ recall |
| HyDE تولّد محتوى خاطئًا بثقة | الإجابة الافتراضية تتحول إلى embedding نحو مستندات خاطئة |
| multi-query على متن صغير جدًا | إزالة التكرار تُرجع النتائج نفسها على أي حال |

---

## البناء

### الخطوة 1: الإعداد

```python
# pip install openai numpy
# Set environment variable: OPENAI_API_KEY=sk-...

import os
import hashlib
from typing import Any

import numpy as np
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"
```

### الخطوة 2: أدوات مشتركة

```python
def embed(texts: list[str]) -> list[list[float]]:
    """Batch embed a list of texts."""
    if not texts:
        return []
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in response.data]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def llm_call(system: str, user: str, temperature: float = 0.3) -> str:
    """Single LLM call. Returns the text content."""
    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()
```

### الخطوة 3: التقنية 1: إعادة صياغة الاستعلام

```python
REWRITE_SYSTEM = """You are a retrieval query optimizer. Your job is to rewrite a user's question
into a more effective retrieval query. Rules:
- Expand abbreviations and acronyms
- Replace pronouns with explicit nouns
- Add synonyms or related terms that might appear in relevant documents
- Remove filler words and conversational phrasing
- Make the query specific and concrete
- Return ONLY the rewritten query, nothing else."""


def rewrite_query(query: str) -> str:
    """
    Rewrite a user query to be more effective for retrieval.

    This is the simplest transformation and should be your default starting point.
    It costs one LLM call (~200ms) and typically improves recall by 5-15%
    on conversational or informal queries.

    Example:
      Input:  "how do I fix the auth error I kept getting yesterday?"
      Output: "authentication error troubleshooting OAuth JWT token validation failure"
    """
    rewritten = llm_call(
        system=REWRITE_SYSTEM,
        user=f"Original query: {query}\n\nRewritten query:",
        temperature=0.1,  # low temperature for consistent rewriting
    )
    return rewritten
```

### الخطوة 4: التقنية 2: HyDE (Hypothetical Document Embeddings)

```python
HYDE_SYSTEM = """You are a knowledgeable assistant. Your task is to write a hypothetical document
passage that would directly answer the given question.

Write as if you are the author of the relevant documentation or knowledge base.
Be specific, use the technical vocabulary that would appear in relevant source documents.
Write 2-3 sentences. Do not acknowledge uncertainty: write as a confident excerpt.
Do not say "In this passage" or "This document explains": just write the content directly."""


def hyde_query(query: str) -> tuple[str, list[float]]:
    """
    HyDE: Generate a hypothetical answer, embed it instead of the question.

    The insight: "what does the answer look like?" embeds closer to actual answers
    than the question itself does.

    Questions and answers occupy different regions of embedding space:
      Query:    "is aspirin safe after a bleed?"
      HyDE doc: "Aspirin (salicylate) is contraindicated following hemorrhagic events
                 due to its antiplatelet activity. Patients who have experienced
                 intracranial hemorrhage should avoid NSAIDs including aspirin."

    The HyDE document embeds very close to the real document.
    The original query embeds further away.

    Works best when:
    - Document vocabulary is very different from query vocabulary
    - Queries are informal/colloquial, documents are technical/formal
    - Questions are about concepts that have a canonical "textbook" answer

    Risks:
    - The LLM may generate a confidently wrong hypothetical answer
    - The wrong hypothetical embeds toward wrong documents
    - Mitigated by using temperature=0.2 and a strong system prompt
    """
    hypothetical_doc = llm_call(
        system=HYDE_SYSTEM,
        user=f"Question: {query}",
        temperature=0.2,
    )
    # Embed the hypothetical document (not the original query)
    hyde_vector = embed([hypothetical_doc])[0]
    return hypothetical_doc, hyde_vector
```

### الخطوة 5: التقنية 3: Step-Back Prompting

```python
STEPBACK_SYSTEM = """You are a retrieval strategist. Your task is to generate a more general,
"step back" version of a specific question.

The step-back question should:
- Ask about the broader concept, principle, or category
- Be general enough to retrieve the background context needed to answer the specific question
- NOT include the specific details from the original question (those come after retrieving context)

Examples:
  Specific: "What is the contraindication of beta blockers for a patient with COPD?"
  Step-back: "What are the general contraindications and precautions for beta blocker use?"

  Specific: "How do I fix a segmentation fault in my recursive Fibonacci implementation?"
  Step-back: "What are common causes of segmentation faults in recursive C programs?"

Return ONLY the step-back question, nothing else."""


def stepback_query(query: str) -> str:
    """
    Step-back prompting: generate a more general version of the query
    to retrieve background context.

    Use this when the user's question is very specific but the relevant context
    is documented at a higher level of abstraction.

    Pattern in RAG: retrieve the step-back query first to get background context,
    then retrieve the original query for specific details, combine both result sets.

    Example workflow:
      query = "dosage adjustment for metformin in CKD stage 3a"
      step_back = "metformin pharmacokinetics and renal dosing guidelines"
      → retrieve both → merge → LLM sees both background and specific context
    """
    return llm_call(
        system=STEPBACK_SYSTEM,
        user=f"Specific question: {query}\n\nStep-back question:",
        temperature=0.2,
    )
```

### الخطوة 6: التقنية 4: Multi-Query

```python
MULTIQUERY_SYSTEM = """You are a query generation assistant. Generate {n} different phrasings
of the given question that might retrieve different relevant documents.

Each phrasing should:
- Preserve the core information need
- Use different vocabulary, phrasing, or emphasis
- Approach the question from a different angle

Return exactly {n} queries, one per line, numbered 1. 2. 3. etc.
Do not include explanations or preamble: only the queries."""


def multi_query(query: str, n: int = 3) -> list[str]:
    """
    Generate N different phrasings of the same query.
    Use all N phrasings for retrieval, then deduplicate results.

    Why this works: vague or ambiguous queries may have multiple valid
    interpretations. Generating several phrasings covers more of the
    relevant search space, improving recall.

    Cost: N extra LLM calls (or 1 call that generates N queries),
    plus N extra embedding calls. Latency roughly doubles.

    When to use:
    - Ambiguous queries with multiple valid interpretations
    - Vague queries where the "right" vocabulary is unknown
    - When recall is more important than latency

    When NOT to use:
    - Latency-sensitive applications
    - Precise queries where additional phrasings add noise
    - Very small corpora where deduplication returns the same K results anyway
    """
    prompt = MULTIQUERY_SYSTEM.format(n=n)
    raw_output = llm_call(system=prompt, user=f"Original query: {query}", temperature=0.5)

    queries = []
    for line in raw_output.strip().split("\n"):
        line = line.strip()
        # Remove numbering if present
        if line and line[0].isdigit():
            # "1. query text" → "query text"
            parts = line.split(".", 1)
            if len(parts) == 2:
                line = parts[1].strip()
        if line:
            queries.append(line)

    # Always include the original query
    if query not in queries:
        queries.insert(0, query)

    return queries[:n + 1]  # original + n generated


def deduplicate_chunks(all_chunks: list[dict]) -> list[dict]:
    """
    Deduplicate retrieved chunks by text content hash.
    Multi-query retrieval often returns the same chunk for different query phrasings.
    """
    seen: set[str] = set()
    unique = []
    for chunk in all_chunks:
        chunk_hash = hashlib.md5(chunk["text"].encode()).hexdigest()
        if chunk_hash not in seen:
            seen.add(chunk_hash)
            unique.append(chunk)
    return unique
```

### الخطوة 7: دمج التحويلات في خط معالجة (Pipeline)

```python
def retrieve_with_transformation(
    query: str,
    retrieval_fn: Any,  # fn(query_text: str, top_k: int) -> list[dict]
    technique: str = "rewrite",
    top_k: int = 5,
    verbose: bool = True,
) -> dict:
    """
    Apply a query transformation technique and retrieve.

    Args:
        query: original user query
        retrieval_fn: your existing retrieve() function from Lesson 05
        technique: "rewrite" | "hyde" | "stepback" | "multi_query" | "none"
        top_k: number of chunks to retrieve

    Returns:
        {
            "original_query": str,
            "transformed_query": str or list[str],
            "retrieved_chunks": list[dict],
            "technique": str,
        }
    """
    if verbose:
        print(f"\nOriginal query: '{query}'")
        print(f"Technique: {technique}")

    if technique == "none":
        chunks = retrieval_fn(query, top_k)
        return {
            "original_query": query,
            "transformed_query": query,
            "retrieved_chunks": chunks,
            "technique": "none",
        }

    elif technique == "rewrite":
        transformed = rewrite_query(query)
        if verbose:
            print(f"Rewritten: '{transformed}'")
        chunks = retrieval_fn(transformed, top_k)

    elif technique == "hyde":
        hypothetical_doc, hyde_vec = hyde_query(query)
        if verbose:
            print(f"HyDE doc: '{hypothetical_doc[:100]}...'")
        # Pass the hypothetical doc text for retrieval (embed internally)
        chunks = retrieval_fn(hypothetical_doc, top_k)
        transformed = hypothetical_doc

    elif technique == "stepback":
        step_back = stepback_query(query)
        if verbose:
            print(f"Step-back: '{step_back}'")
        # Retrieve both the step-back and the original, merge
        stepback_chunks = retrieval_fn(step_back, top_k)
        original_chunks = retrieval_fn(query, top_k)
        chunks = deduplicate_chunks(stepback_chunks + original_chunks)[:top_k]
        transformed = step_back

    elif technique == "multi_query":
        queries = multi_query(query, n=3)
        if verbose:
            print(f"Generated queries: {queries}")
        all_chunks = []
        for q in queries:
            all_chunks.extend(retrieval_fn(q, top_k))
        chunks = deduplicate_chunks(all_chunks)[:top_k * 2]  # more chunks, deduped
        transformed = queries

    else:
        raise ValueError(f"Unknown technique: {technique}")

    return {
        "original_query": query,
        "transformed_query": transformed,
        "retrieved_chunks": chunks,
        "technique": technique,
    }
```

> **اختبار من الواقع:** مهندس backend يراجع الـ PR الخاص بك يقول: "صرنا نقوم باستدعاء LLM إضافي فقط لإعادة صياغة السؤال قبل أن نبدأ الاسترجاع أصلًا. هذا يضاعف تكلفتنا لكل استعلام تقريبًا. متى يستحق ذلك فعلًا، وكيف سنعرف ما إذا كان استعلام معيّن يحتاجه من الأساس؟" ما إجابتك، وهل هناك طريقة لتطبيق التحويل بشكل انتقائي بدلًا من تطبيقه على كل استعلام؟

### الخطوة 8: قياس الأثر

```python
def compare_techniques(
    query: str,
    retrieval_fn: Any,
    relevant_texts: list[str],  # ground truth: text snippets that should be retrieved
    top_k: int = 5,
) -> dict:
    """
    Compare all four techniques for a single query.
    Measure: how many relevant texts appear in the retrieved chunks?

    relevant_texts: list of text fragments that a correct answer requires.
    We check if any retrieved chunk contains each fragment (substring match).
    This is a simple recall proxy without requiring exact doc IDs.
    """

    def recall_score(chunks: list[dict], relevant: list[str]) -> float:
        """What fraction of relevant texts are covered by retrieved chunks?"""
        if not relevant:
            return 1.0
        covered = 0
        for text_fragment in relevant:
            if any(text_fragment.lower() in chunk["text"].lower() for chunk in chunks):
                covered += 1
        return covered / len(relevant)

    results = {}
    for technique in ["none", "rewrite", "hyde", "stepback", "multi_query"]:
        result = retrieve_with_transformation(
            query, retrieval_fn, technique=technique, top_k=top_k, verbose=False
        )
        recall = recall_score(result["retrieved_chunks"], relevant_texts)
        results[technique] = {
            "recall": recall,
            "chunks_retrieved": len(result["retrieved_chunks"]),
            "transformed_query": result["transformed_query"],
        }

    return results


def print_comparison(query: str, comparison: dict) -> None:
    print(f"\nQuery: '{query}'")
    print(f"{'Technique':<15}  {'Recall':>8}  {'Chunks':>8}  Transformed query")
    print("-" * 70)
    for technique, metrics in comparison.items():
        tq = metrics["transformed_query"]
        tq_str = str(tq)[:40] + "..." if len(str(tq)) > 40 else str(tq)
        print(
            f"  {technique:<13}  {metrics['recall']:>8.2f}  "
            f"{metrics['chunks_retrieved']:>8}  {tq_str}"
        )
```

### الخطوة 9: نقطة الدخول الرئيسية

```python
if __name__ == "__main__":
    # Demo: show each technique's output for example queries.
    # To test with your actual RAG pipeline, replace this stub
    # with your retrieve() function from Lesson 05.

    def stub_retriever(query: str, top_k: int) -> list[dict]:
        """
        Stub retriever for demonstration.
        Replace with your actual retrieve() from Lesson 05:
            from lesson05 import ingest, retrieve
            store = ingest("my_document.txt")
            def my_retriever(query, top_k):
                return retrieve(query, store, top_k=top_k)
        """
        print(f"  [stub] retrieve('{query[:60]}...', top_k={top_k})")
        return [
            {"text": f"Stub result {i} for: {query[:40]}", "score": 0.9 - i * 0.1}
            for i in range(top_k)
        ]

    demo_queries = [
        "is aspirin safe after a bleed?",
        "how do I fix the auth error I keep getting",
        "metformin dose for CKD patient stage 3a",
    ]

    print("=" * 70)
    print("QUERY TRANSFORMATION DEMO")
    print("=" * 70)

    for query in demo_queries:
        print(f"\n{'─'*70}")
        print(f"Original: '{query}'")

        print(f"\n[1] Rewrite:")
        rewritten = rewrite_query(query)
        print(f"    → '{rewritten}'")

        print(f"\n[2] HyDE:")
        hyde_doc, _ = hyde_query(query)
        print(f"    → '{hyde_doc[:120]}...'")

        print(f"\n[3] Step-back:")
        stepback = stepback_query(query)
        print(f"    → '{stepback}'")

        print(f"\n[4] Multi-query:")
        mq = multi_query(query, n=3)
        for i, q in enumerate(mq, 1):
            print(f"    {i}. {q}")

    print("\n\n" + "=" * 70)
    print("USAGE WITH YOUR RAG PIPELINE")
    print("=" * 70)
    print("""
To use with your pipeline from Lesson 05:

    from main import ingest, retrieve

    store = ingest("my_document.txt")

    def my_retriever(query: str, top_k: int) -> list[dict]:
        return retrieve(query, store, top_k=top_k)

    # Use rewrite for most queries:
    result = retrieve_with_transformation(
        "how do I set up authentication?",
        retrieval_fn=my_retriever,
        technique="rewrite",
    )

    # Use HyDE for vocabulary-mismatch domains:
    result = retrieve_with_transformation(
        "is this drug safe for liver patients?",
        retrieval_fn=my_retriever,
        technique="hyde",
    )

    # Use multi-query for vague queries:
    result = retrieve_with_transformation(
        "connection issues",
        retrieval_fn=my_retriever,
        technique="multi_query",
    )

    print(result["retrieved_chunks"])
""")
```

---

## الاستخدام

يوفّر LangChain التحويلات الأربعة جميعها كسلاسل (chains) جاهزة مدمجة:

```python
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_openai import ChatOpenAI

# Multi-query retriever: generates N queries automatically
retriever = MultiQueryRetriever.from_llm(
    retriever=vectorstore.as_retriever(),
    llm=ChatOpenAI(temperature=0),
)
docs = retriever.get_relevant_documents("how does auth work")
```

ولـ HyDE تحديدًا:

```python
from langchain.chains import HypotheticalDocumentEmbedder
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

embeddings = HypotheticalDocumentEmbedder.from_llm(
    llm=ChatOpenAI(),
    embeddings=OpenAIEmbeddings(),
    chain_type="stuff",
)
result = embeddings.embed_query("what is the capital of France?")
# result is the embedding of a hypothetical answer
```

ولدى LlamaIndex هذه التقنيات على هيئة كائنات `QueryTransformComponent` في خط معالجة الاستعلام الخاص به. المنطق الأساسي مطابق لما بنيناه؛ ويضيف إطار العمل معالجة الأخطاء، ودعم async، والتكامل مع تجريداته للـ retriever.

> **نقلة في المنظور:** يقول مدير المنتج (product manager) لديك: "بحثنا يعمل جيدًا لمعظم الاستعلامات بالفعل. صار عندنا الآن أربع تقنيات تحويل مختلفة للاختيار منها. كيف نقرر أيها ننشره فعلًا وأيها نتخطاه؟ ما الدليل الذي يجعلك واثقًا بما يكفي لإطلاق إحداها إلى الإنتاج؟" ما إطار اتخاذ القرار لديك، وكيف يبدو "الدليل الكافي"؟

---

## التسليم

مخرج هذا الدرس هو الـ prompt في `outputs/prompt-query-transformer.md`. ينصح بأي تحويل يُطبَّق بحسب الاستعلام ونوع نظام الاسترجاع، ويوفّر الـ prompts الفعلية للاستخدام.

والقطعة القابلة للتشغيل هي `code/main.py`:

```bash
export OPENAI_API_KEY=sk-...
python main.py
```

ستعرض التقنيات الأربعة كلها على استعلامات أمثلة باستخدام retriever بديل (stub). استبدل الـ stub بدالة `retrieve()` من الدرس 05 لتختبر على متنك الفعلي.

---

## التقييم

**التحقق 1: قِس الـ recall قبل وبعد.**
اختر 10 استعلامات من مجموعة التقييم لديك تعاني حاليًا من recall@5 ضعيف. طبّق إعادة صياغة الاستعلام على كل منها. احسب recall@5 من جديد. إذا تحسّن الـ recall بنسبة 10%+ على هذه الاستعلامات، فإن إعادة الصياغة تستحق تكلفة الـ latency. وإذا لم يتحسّن، فالمشكلة ليست في مفردات الاستعلام: بل في الـ chunking، أو نموذج الـ embedding، أو حجم K.

**التحقق 2: اختبر HyDE على نطاقات عدم تطابق المفردات.**
تعمل HyDE على أفضل وجه عندما تكون مفردات المستند مختلفة جدًا عن مفردات الاستعلام. حدّد 3-5 استعلامات يستخدم فيها المستند ذو الصلة مفردات تقنية غير موجودة في الاستعلام. شغّل كلًّا من الـ embedding العادي و HyDE، وقارن أعلى 3 chunks مسترجعة لكل منهما. إذا استرجعت HyDE المقطع الصحيح ولم يفعل الـ embedding العادي، فالفرضية مؤكدة لنطاقك.

**التحقق 3: تتبّع تكلفة الـ latency لكل تقنية.**
كل تحويل يتطلب استدعاء LLM واحدًا أو أكثر. قِس زمن استجابة الاستعلام الكلي:
- الأساس (بلا تحويل): embed + بحث cosine ≈ 50–100ms
- إعادة الصياغة: +1 استدعاء LLM ≈ +200–400ms
- HyDE: +1 استدعاء LLM ≈ +200–400ms
- Step-back: +1 استدعاء LLM + استدعاءا استرجاع ≈ +300–500ms
- Multi-query (3 صياغات): +1 استدعاء LLM + 3 استدعاءات استرجاع ≈ +400–600ms

هل المكسب في الـ recall يستحق الـ latency؟ بالنسبة لنظام أسئلة وأجوبة آني (real-time)، قد تكون multi-query بطيئة جدًا. وبالنسبة لنظام بحث في المستندات يعمل بشكل async، فإن الـ 500ms الإضافية غير ذات أهمية.

---

## تمارين

1. **[سهل]** سجّل الاستعلام الأصلي والاستعلام المعاد صياغته لـ 10 استعلامات حقيقية من متنك. قارن تشابه الـ cosine بين الاستعلام والمقطع ذي الصلة، قبل إعادة الصياغة وبعدها. هل يتحسّن مقياس التشابه باطّراد؟

2. **[متوسط]** نفّذ طبقة caching لتحويلات الاستعلام: إذا سبق تحويل الاستعلام نفسه (تطابق نصّي دقيق)، أرجِع النتيجة المخزّنة بدلًا من استدعاء الـ LLM مجددًا. استخدم dict بسيطًا في Python. قِس مقدار ما يخفّضه ذلك من الـ latency في جلسة استعلام واقعية.

3. **[صعب]** نفّذ "محدِّد تحويل" (transformer selector) يختار تلقائيًا أفضل تقنية تحويل بناءً على خصائص الاستعلام. القواعد المطلوب تنفيذها: (أ) إذا كان طول الاستعلام < 5 كلمات → rewrite، (ب) إذا كان الاستعلام يحتوي معرّفات شديدة التحديد (regex للأكواد والإصدارات وأرقام النماذج) → بلا تحويل، (ج) إذا كان الاستعلام سؤالًا دون مصطلحات تقنية → HyDE، (د) وإلا → rewrite. اختبره على 20 استعلامًا من مجموعة التقييم لديك. هل يطابق الاختيار التلقائي ما كنت ستختاره يدويًا؟

---

## مصطلحات أساسية

| المصطلح | ما يقوله الناس | ما يعنيه فعلًا |
|------|----------------|----------------------|
| Query transformation | "query expansion," "query augmentation" | تعديل استعلام المستخدم قبل الاسترجاع لتحسين جودة النتائج المسترجعة |
| Query rewriting | "query reformulation" | استخدام LLM لإعادة صياغة الاستعلام بمفردات استرجاع أفضل |
| HyDE | "Hypothetical Document Embeddings" | توليد إجابة افتراضية وتحويلها إلى embedding بدلًا من السؤال؛ يستغل حقيقة أن الإجابات والمستندات تتشارك المفردات |
| Step-back prompting | "query abstraction," "level-up prompting" | توليد نسخة أعمّ من استعلام محدد لاسترجاع السياق الخلفي |
| Multi-query retrieval | "query expansion," "query diversification" | توليد عدة صياغات للاستعلام نفسه والاسترجاع لها جميعًا لتحسين الـ recall |
| Vocabulary mismatch | "lexical gap," "query-document gap" | حين يستخدم استعلام المستخدم باللغة الطبيعية كلمات مختلفة عن المستندات التي تحتوي الإجابة |
| OOV | "Out-of-vocabulary" | مصطلح لم يُرَ أثناء تدريب نموذج الـ embedding؛ سيكون تمثيله في الـ embedding ضعيفًا |

---

## قراءات إضافية

- [HyDE Paper: Precise Zero-Shot Dense Retrieval](https://arxiv.org/abs/2212.10496): Gao et al., 2022؛ ورقة HyDE الأصلية؛ تُظهر النتائج التجريبية متى تساعد أكثر
- [Step-Back Prompting Paper](https://arxiv.org/abs/2310.06117): Zheng et al., Google DeepMind؛ تقدّم step-back كتقنية RAG؛ تتضمن تقييمًا عبر عدة معايير قياس (benchmarks)
- [Query Expansion in Modern IR](https://dl.acm.org/doi/10.1145/3404835.3463017): درس تعليمي في SIGIR 2021 حول توسيع الاستعلام؛ يربط مقاربات الاسترجاع المعلوماتي الكلاسيكية بالطرق القائمة على LLM
- [RAG Survey](https://arxiv.org/abs/2312.10997): مسح شامل يغطي تحويل الاستعلام في سياق مشهد RAG الكامل
- [MultiQueryRetriever in LangChain](https://python.langchain.com/docs/how_to/MultiQueryRetriever/): تنفيذ إنتاجي مع تسجيل (logging)؛ يبيّن كيفية دمج multi-query مع الـ retrievers الموجودة
- [FLARE: Forward-Looking Active REtrieval](https://arxiv.org/abs/2305.06983): تقنية متقدمة تولّد استعلامات الاسترجاع أثناء التوليد في الوقت الفعلي؛ الخطوة التالية بعد هذه التقنيات الأربع
