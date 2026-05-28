# استراتيجيات التقطيع (Chunking Strategies)

> طريقة تقسيم المستندات تحدّد ما الذي يستطيع استرجاعك إيجاده. التقطيع السيّئ يجعل الـ embeddings الممتازة تسترجع الشيء الخاطئ.

**النوع:** بناء
**اللغات:** Python
**المتطلبات:** 02-01 الحدس وراء الـ Embeddings، 02-03 المخازن الشعاعية
**الوقت:** ~80 دقيقة
**المرحلة:** 02 · الاسترجاع و RAG

## أهداف التعلّم

- تنفيذ كل استراتيجيات التقطيع الست الرئيسية كدوال مستقلّة قابلة للاختبار
- شرح أوضاع الفشل لكل استراتيجية ومتى تفضّل واحدة على أخرى
- تحديد ما إذا كان فشل الاسترجاع سببه التقطيع لا جودة الـ embedding
- تطبيق التقطيع الدلالي (semantic chunking) لكشف حدود المواضيع في المحتوى الطويل
- شرح التقطيع المتأخّر (late chunking) ولماذا يحافظ على السياق بعيد المدى الذي تفقده الاستراتيجيات الأخرى

---

## المشكلة

بنت شركة تقنية قانونية نظام RAG على مجموعة عقودها. كانت جودة الـ embedding جيدة: فحوصات العقلانية نجحت. والمخزن الشعاعي مهيّأ بشكل صحيح. لكن حين استعلم المحامون عن "termination clauses"، كانت الـ chunks المُسترجَعة تُرجع باستمرار شظايا منتصف الجمل التي تحمل الكلمات المفتاحية الصحيحة لكن بلا معنى قانوني فعلي: مجرّد ظهور كلمة "terminate" في سياق مقطوع نحويًا عن الجملة العاملة. لم يستطع المحامون استخدام المخرجات. أسموها "سلطة كلمات".

السبب الجذري: التقطيع ثابت الحجم بنافذة 256 token ودون تداخل (overlap) كان يقطع الجمل في المنتصف. البند العامل: "Either party may terminate this agreement upon 30 days written notice": قُسّم عبر chunkين. لم تحتوِ أيّ chunk وحدها على بيان قانوني كامل قابل للاستخدام. النموذج رمّز بأمانة أنصاف جمل صادف أنها تحوي "terminate"، ونظام الاسترجاع أرجعها.

التقطيع هو الخطوة التي تتخطّاها أو تُعرّفها بشكل ناقص معظم دروس RAG. يحدث قبل الـ embedding، فتبدو إخفاقاته كإخفاقات embedding. ويحدث قبل الاسترجاع، فتبدو إخفاقاته كإخفاقات استرجاع. لكن نظام embedding واسترجاع مبني بشكل صحيح لا يستطيع إلا إرجاع ما في الفهرس، وإن احتوى الفهرس شظايا، حصلت على إجابات مبنية على الشظايا. هذا الدرس عن بناء حدود chunks تحافظ على المعنى.

---

## المفهوم

### ما الذي يفعله التقطيع فعلًا

نموذج الـ embedding يُحوّل نصًا ثابت الطول إلى شعاع. لكن المستندات ليست ثابتة الطول: قد يكون العقد 80 صفحة، ومقالة الدعم 200 كلمة. لا يمكنك تحويل مستند بـ 80 صفحة إلى شعاع واحد لأن:

1. معظم النماذج لها حدّ سياق 512 token: المستندات الطويلة تُقلَّم
2. حتى مع نماذج السياق الطويل، الشعاع الواحد يُمتوسط معنى 80 صفحة؛ فيصبح بند معيّن إشارة دقيقة في بحر من المحتوى الآخر
3. الوحدة المُسترجَعة يجب أن تكون صغيرة بما يكفي لتلائم نافذة سياق الـ LLM بجانب الاستعلام

التقطيع هو عملية تقسيم مستند إلى وحدات صغيرة بما يكفي لتحويلها إلى embedding بمعنى ولاسترجاعها بدقة.

التوتّر الجوهري:

```
Smaller chunks → more precise retrieval, but:
  - lose surrounding context
  - risk splitting across sentence/paragraph boundaries
  - need more index space

Larger chunks → more context per result, but:
  - embedding quality degrades (too many topics mixed)
  - harder for the LLM to identify the specific answer in the chunk
  - fewer results fit in the LLM's context window
```

تعتمد النقطة المثلى على نوع مستندك ونوع استعلامك. لذلك توجد ست استراتيجيات، لا واحدة.

### الاستراتيجيات الست بنظرة سريعة

```
Strategy              Best For              Key Property
──────────────────────────────────────────────────────────────────────
Fixed-size + overlap  Homogeneous docs      Simple, fast, controllable
Recursive splitter    General prose         Respects natural boundaries
Markdown-aware        Docs, wikis, READMEs  Preserves structure/headers
Sentence-window       Precision Q&A         Embeds context, returns sentence
Semantic              Varied long-form      Topic-boundary aware
Late chunking         Long docs needing     Full-doc context in chunk vectors
                      long-range context
```

### كيف يؤثّر التقطيع في جودة الـ Embedding

embedding الـ chunk هو تمثيله الشعاعي الواحد. إن احتوت الـ chunk فكرة كاملة: فقرة عن موضوع واحد، أو جملة كاملة: فالشعاع تمثيل نظيف لتلك الفكرة. وإن كانت الـ chunk شظية، فالشعاع مشوّش:

```
Good chunk (complete paragraph):
  "Payments are due on the first of each month. Late payments
   accrue interest at 1.5% per month."
  → Vector represents: {payment, due date, late fee, interest}

Bad chunk (fragment from fixed-size split):
  "...payments accrue interest at 1.5% per month. The indemnification
   provisions in Section 8 shall survive termin..."
  → Vector represents: {interest, indemnification, survival clause}: mixed signal
```

الـ chunk السيّئة لا تزال تُسترجَع للاستعلامات المتعلّقة بالدفع (لأنها تذكر الدفع) لكن السياق غير متماسك. يستقبلها الـ LLM فإمّا يهلوس إجابة أو يعترف بعدم اليقين.

### التقطيع المتأخّر: نموذج ذهني مختلف

الاستراتيجيات الخمس الأخرى تقطّع أولًا، ثم تُحوّل إلى embedding. التقطيع المتأخّر يعكس هذا: حوّل المستند الكامل إلى embedding أولًا (باستخدام نموذج سياق طويل)، ثم استخرج embeddings مستوى الـ chunk من تمثيلات tokens المستند الكامل.

```
Traditional:                    Late Chunking:

Doc → chunk1 → embed1           Doc → [full doc embedding]
Doc → chunk2 → embed2                    ↓
Doc → chunk3 → embed3           extract chunk1 vector from full-doc positions
                                extract chunk2 vector from full-doc positions
chunk1 loses context             chunk3 vector from full-doc positions
from chunks 2 and 3
                                each chunk vector "knows about" the full doc
```

هذا يهمّ حين تحتاج الـ chunks المبكّرة سياقًا من لاحق المستند. في دليل تقني، قد يشير الفصل 1 إلى مفاهيم مشروحة بالكامل في الفصل 5. التقطيع التقليدي يُحوّل الفصل 1 إلى embedding دون أي وعي بالفصل 5. أما embedding الفصل 1 في التقطيع المتأخّر فحُسب وكل الفصل 5 في نافذة السياق.

---

## البناء

ننفّذ كل الاستراتيجيات الست كدوال مستقلّة. كلٌّ تأخذ سلسلة نصية وتُرجع قائمة من سلاسل الـ chunk.

### الخطوة 1: تثبيت الاعتماديات وتحميل المستند العيّنة

```python
# pip install nltk tiktoken
import re
import textwrap
from typing import Callable

# Install NLTK sentence tokenizer data (one-time)
import nltk
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)

SAMPLE_DOCUMENT = """
# API Rate Limiting Guide

## Overview

Our API uses rate limiting to ensure fair usage and maintain service quality for all customers. Understanding these limits will help you design applications that stay within bounds and handle limit responses gracefully.

## Default Limits

Every API key is subject to default rate limits. The standard tier allows 60 requests per minute and 10,000 requests per day. Enterprise accounts receive higher limits by default and can request custom quotas.

Requests that exceed the rate limit receive a 429 Too Many Requests response. The response includes a Retry-After header indicating how many seconds to wait before retrying.

## Handling 429 Responses

When your application receives a 429 response, it should implement exponential backoff. Start with a 1-second delay, then double the delay on each subsequent retry up to a maximum of 32 seconds. After 5 failed retries, surface the error to the user or log it for investigation.

Do not retry immediately on receiving a 429: this will only worsen the situation. Burst behavior that triggers rate limits is usually caused by unbatched requests in tight loops. Review your request patterns before increasing retry counts.

## Monitoring Your Usage

You can monitor your API usage from the dashboard under Settings > API Usage. The usage page shows requests per minute, daily totals, and a breakdown by endpoint. An alert threshold can be set to notify you before you hit your limit.

If you consistently hit rate limits, consider batching requests, caching responses where possible, or upgrading your plan. The rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset) are included in every response.

## Enterprise Options

Enterprise customers can request custom rate limits through the sales team. Custom limits are applied per API key and can be set independently for different endpoints. Increased limits are subject to a capacity review and may require a dedicated infrastructure allocation.
""".strip()
```

### الخطوة 2: الاستراتيجية 1: ثابتة الحجم مع تداخل

أبسط استراتيجية. قطّع النص إلى نوافذ من N tokens، متقدّمًا بـ `N - overlap` token في كل خطوة. يضمن التداخل بقاء المعلومات قرب الحدّ محفوظةً في كلتا الـ chunkين المتجاورتين.

```python
import tiktoken

def fixed_size_chunks(
    text: str,
    chunk_size: int = 200,
    overlap: int = 40,
    encoding_name: str = "cl100k_base",
) -> list[str]:
    """
    Split text into fixed-size token windows with overlap.

    chunk_size: number of tokens per chunk
    overlap: number of tokens shared between consecutive chunks
    encoding_name: tiktoken encoding (cl100k_base matches OpenAI models)

    When to use:
    - Homogeneous content (all the same type/length)
    - Baseline for comparison: always run this first
    - When you need deterministic, reproducible chunks

    Failure mode:
    - Splits mid-sentence; embedding of partial sentences is noisy
    - Doesn't respect document structure (paragraphs, sections)
    """
    enc = tiktoken.get_encoding(encoding_name)
    tokens = enc.encode(text)
    chunks = []
    stride = chunk_size - overlap

    for start in range(0, len(tokens), stride):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)
        chunks.append(chunk_text.strip())
        if end == len(tokens):
            break

    return [c for c in chunks if c]
```

### الخطوة 3: الاستراتيجية 2: المُقسِّم المحرفي التعاودي (Recursive Character Splitter)

حاول التقسيم على أفضل فاصل متاح: فواصل الفقرات أولًا، ثم فواصل الجمل، ثم فواصل الكلمات، ثم الأحرف المفردة. استخدم التقسيمات الأدقّ فقط حين تكون الـ chunk ما تزال كبيرة جدًا بعد التقسيم الخشن.

```python
def recursive_char_split(
    text: str,
    max_chars: int = 800,
    overlap_chars: int = 100,
    separators: list[str] | None = None,
) -> list[str]:
    """
    Split on natural language boundaries, using progressively finer
    separators until chunks are small enough.

    When to use:
    - General prose (articles, documentation, emails)
    - Default choice when you don't know your document type in advance

    Failure mode:
    - Doesn't understand document structure (no awareness of headers)
    - Very long paragraphs still get split arbitrarily
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", "! ", "? ", " ", ""]

    def split_with_overlap(parts: list[str], target_size: int, overlap: int) -> list[str]:
        """Combine parts into chunks of at most target_size with overlap."""
        chunks = []
        current = ""
        for part in parts:
            if not part.strip():
                continue
            if len(current) + len(part) + 1 <= target_size:
                current = (current + " " + part).strip() if current else part
            else:
                if current:
                    chunks.append(current)
                    # Include overlap from the end of the previous chunk
                    overlap_text = current[-overlap:] if overlap else ""
                    current = (overlap_text + " " + part).strip() if overlap_text else part
                else:
                    current = part
        if current:
            chunks.append(current)
        return chunks

    def _split(text: str, sep_index: int) -> list[str]:
        if len(text) <= max_chars or sep_index >= len(separators):
            return [text]

        sep = separators[sep_index]
        parts = text.split(sep) if sep else list(text)

        result = []
        for part in parts:
            if len(part) > max_chars:
                # Part is still too large: recurse with next separator
                result.extend(_split(part, sep_index + 1))
            else:
                result.append(part)

        # Merge small parts back up to max_chars with overlap
        return split_with_overlap(result, max_chars, overlap_chars)

    return [c for c in _split(text, 0) if c.strip()]
```

### الخطوة 4: الاستراتيجية 3: المُقسِّم الواعي بـ Markdown

قسّم على عناوين Markdown. كل قسم H1/H2/H3 يصبح chunk واحدة أو أكثر، مع تضمين العنوان في كل chunk بحيث يحمل الـ embedding موضوع القسم.

```python
def markdown_split(
    text: str,
    max_chars: int = 1000,
) -> list[str]:
    """
    Split Markdown documents on headers (# ## ###).
    Preserves header context in each chunk.

    When to use:
    - Documentation sites, wikis, READMEs
    - Any content with a consistent header hierarchy
    - When section-level retrieval granularity is appropriate

    Failure mode:
    - Sections longer than max_chars are truncated (combine with recursive split)
    - Non-Markdown content produces a single chunk
    """
    header_pattern = re.compile(r'^(#{1,3})\s+(.+)$', re.MULTILINE)
    positions = [(m.start(), m.group()) for m in header_pattern.finditer(text)]

    if not positions:
        # No headers: return as single chunk (possibly oversized)
        return [text.strip()]

    chunks = []
    for i, (start, _) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        section = text[start:end].strip()

        if len(section) <= max_chars:
            chunks.append(section)
        else:
            # Section is too large: split it further while keeping the header
            header_match = header_pattern.match(section)
            header_line = header_match.group() + "\n\n" if header_match else ""
            body = section[len(header_line):]

            # Split body by paragraphs, prepend header to each chunk
            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
            current = header_line
            for para in paragraphs:
                if len(current) + len(para) + 2 <= max_chars:
                    current = current + para + "\n\n"
                else:
                    if current.strip():
                        chunks.append(current.strip())
                    current = header_line + para + "\n\n"
            if current.strip():
                chunks.append(current.strip())

    return [c for c in chunks if c]
```

### الخطوة 5: الاستراتيجية 4: نافذة الجملة (Sentence-Window)

خزّن جملة واحدة لكل chunk، لكن حوّل كل جملة إلى embedding مع نافذة من الجمل المحيطة كسياق. وقت الاسترجاع، أرجِع الجملة الأصلية (للدقة) لكن وفّر أيضًا النافذة المحيطة (لسياق الـ LLM).

```python
from nltk.tokenize import sent_tokenize

def sentence_window_chunks(
    text: str,
    window_size: int = 2,
) -> list[dict]:
    """
    One sentence per chunk, embedded with surrounding context window.

    Returns list of dicts:
      {
        "chunk_text": the sentence (used as embedding input),
        "context_text": sentence + window (returned to LLM),
        "sentence_index": position in document
      }

    When to use:
    - Precision Q&A where you need the exact sentence, not a paragraph
    - When your LLM needs surrounding context to interpret the answer

    Failure mode:
    - Very short sentences produce weak embeddings (too little signal)
    - Window doesn't span paragraph/section boundaries well
    """
    sentences = sent_tokenize(text)
    result = []

    for i, sentence in enumerate(sentences):
        window_start = max(0, i - window_size)
        window_end = min(len(sentences), i + window_size + 1)
        context = " ".join(sentences[window_start:window_end])
        result.append({
            "chunk_text": sentence,         # embed this
            "context_text": context,         # return this to the LLM
            "sentence_index": i,
        })

    return result
```

> **اختبار من الواقع:** مهندس بيانات في فريقك يقول: "احنا أصلًا نقسّم على أسطر جديدة (newlines) في خطّ ETL وهو يشتغل تمام للبيانات المُهيكلة. ليش نحتاج كل هذي الاستراتيجيات؟ مو هذا بس تعقيد زائد؟" كيف تشرح متى يكون التقسيم على الأسطر مناسبًا فعلًا ومتى يسبّب إخفاقات استرجاع تبدو كمشاكل نموذج؟

### الخطوة 6: الاستراتيجية 5: التقطيع الدلالي (Semantic Chunking)

حوّل كل جملة إلى embedding، ثم قِس تشابه جيب التمام بين الجمل المتجاورة. حيث ينخفض التشابه بشكل ملحوظ (حدّ موضوع)، ابدأ chunk جديدة.

```python
def semantic_chunks(
    text: str,
    threshold: float = 0.75,
    min_chunk_chars: int = 100,
) -> list[str]:
    """
    Split where semantic similarity between adjacent sentences drops below threshold.

    Requires: sentence-transformers (for sentence embeddings)

    When to use:
    - Long-form content covering multiple topics (blog posts, reports)
    - When fixed-size splits produce chunks that mix unrelated topics

    Failure mode:
    - Expensive: embeds every sentence individually
    - Threshold is sensitive to document domain; tune empirically
    - Very similar text throughout (technical manuals) produces few split points
    """
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        print("  [SKIP] semantic_chunks requires sentence-transformers")
        return [text]

    sentences = sent_tokenize(text)
    if len(sentences) <= 1:
        return sentences

    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(sentences, normalize_embeddings=True, convert_to_numpy=True)

    # Compute similarity between each pair of adjacent sentences
    similarities = [
        float(embeddings[i] @ embeddings[i + 1])
        for i in range(len(embeddings) - 1)
    ]

    # Split where similarity drops below threshold
    chunks = []
    current_sentences = [sentences[0]]

    for i, sim in enumerate(similarities):
        if sim < threshold and len(" ".join(current_sentences)) >= min_chunk_chars:
            chunks.append(" ".join(current_sentences))
            current_sentences = [sentences[i + 1]]
        else:
            current_sentences.append(sentences[i + 1])

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return [c for c in chunks if c.strip()]
```

### الخطوة 7: الاستراتيجية 6: التقطيع المتأخّر (Late Chunking)

يتطلّب التقطيع المتأخّر نموذجًا يوفّر embeddings مستوى الـ token لمستند كامل. نستخدم النهج الموصوف في ورقة JinaAI للتقطيع المتأخّر: رمّز المستند الكامل، ثم خذ متوسّط تجميع (mean-pool) embeddings الـ tokens ضمن نطاق كل chunk لإنتاج أشعّة مستوى الـ chunk.

```python
def late_chunking_embeddings(
    text: str,
    chunk_boundaries: list[str],
) -> list[dict]:
    """
    Late chunking: embed the full document first, then extract chunk vectors
    from the full-document token embeddings.

    Returns list of dicts:
      {"chunk_text": str, "embedding": np.ndarray}

    chunk_boundaries: list of chunk texts (define the boundaries first using
    any strategy: typically sentence or paragraph splits)

    When to use:
    - Long documents where early chunks reference concepts explained later
    - Technical manuals, academic papers, legal contracts
    - When you see that early chunks retrieve poorly despite good content

    Limitation:
    - Requires a model that exposes token-level embeddings (not all do)
    - In practice: use a BERT/transformer encoder, not a sentence-transformer
    - The JinaAI jina-embeddings-v2-base-en model supports this natively
    """
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
        import numpy as np
    except ImportError:
        print("  [SKIP] late_chunking requires transformers and torch")
        print("         pip install transformers torch")
        # Fallback: return fixed-size chunks with standard embeddings
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(chunk_boundaries, normalize_embeddings=True, convert_to_numpy=True)
        return [
            {"chunk_text": chunk, "embedding": emb, "method": "fallback_standard"}
            for chunk, emb in zip(chunk_boundaries, embeddings)
        ]

    # Load a model that provides per-token embeddings
    model_name = "jinaai/jina-embeddings-v2-base-en"
    print(f"  Loading {model_name} for late chunking (may download on first run)...")

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        model_hf = AutoModel.from_pretrained(model_name, trust_remote_code=True)
        model_hf.eval()
    except Exception as e:
        print(f"  [SKIP] Could not load {model_name}: {e}")
        print("  Falling back to standard chunking with sentence-transformers")
        from sentence_transformers import SentenceTransformer
        import numpy as np
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(chunk_boundaries, normalize_embeddings=True, convert_to_numpy=True)
        return [
            {"chunk_text": chunk, "embedding": emb, "method": "fallback_standard"}
            for chunk, emb in zip(chunk_boundaries, embeddings)
        ]

    # Encode the full document to get token-level embeddings
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=8192)
    with torch.no_grad():
        outputs = model_hf(**inputs)

    # token_embeddings: (1, seq_len, hidden_dim)
    token_embeddings = outputs.last_hidden_state[0]  # (seq_len, hidden_dim)
    tokens = tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])

    # For each chunk, find its token span in the full document and mean-pool
    results = []
    search_pos = 0  # track position in the token sequence

    for chunk_text in chunk_boundaries:
        chunk_tokens = tokenizer.tokenize(chunk_text)
        chunk_len = len(chunk_tokens)

        # Find this chunk's position in the full token sequence
        start = search_pos
        end = min(start + chunk_len + 2, len(token_embeddings))  # +2 for tokenization variance

        chunk_embedding = token_embeddings[start:end].mean(dim=0).numpy()
        norm = np.linalg.norm(chunk_embedding)
        if norm > 0:
            chunk_embedding = chunk_embedding / norm

        results.append({
            "chunk_text": chunk_text,
            "embedding": chunk_embedding,
            "method": "late_chunking",
        })
        search_pos = end

    return results
```

---

## الاستخدام

مُقسِّمات النصوص في LangChain تنفّذ الاستراتيجيات 1–3 بواجهة مصقولة. إن كنت تبني على LangChain، فاستخدم هذه بدلًا من تنفيذاتك الخاصة: فهي تتعامل مع الحالات الحدّية (Unicode، تطبيع المسافات البيضاء، الـ chunks الفارغة) التي يصعب ضبطها:

```python
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,   # Strategy 2
    MarkdownTextSplitter,              # Strategy 3
    CharacterTextSplitter,             # Strategy 1 (character-based)
)

# Recursive (most common)
splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    length_function=len,  # or: tiktoken-based length function
    separators=["\n\n", "\n", ". ", " ", ""],
)
chunks = splitter.split_text(document_text)

# Markdown-aware
md_splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=100)
chunks = md_splitter.split_text(markdown_text)
```

يوفّر LlamaIndex `SentenceSplitter` و`SemanticSplitterNodeParser` للاستراتيجيتين 4 و5:

```python
from llama_index.core.node_parser import SentenceSplitter, SemanticSplitterNodeParser
from llama_index.embeddings.openai import OpenAIEmbedding

# Sentence splitter with window
splitter = SentenceSplitter(chunk_size=128, chunk_overlap=20)

# Semantic splitter
embed_model = OpenAIEmbedding()
semantic_splitter = SemanticSplitterNodeParser(
    embed_model=embed_model,
    breakpoint_percentile_threshold=95,  # split at top 5% similarity drops
)
```

ما تضيفه الأطر (frameworks) على تنفيذاتك الخام: تعامل أفضل مع التقطيع إلى tokens، وأغلفة كائن `Document` تحمل البيانات الوصفية عبر خطّ الأنابيب، وتكامل مع سلاسل الاسترجاع. وما لا تضيفه: جودة تقطيع أفضل. الخوارزميات هي نفسها.

> **نقلة في المنظور:** زميل يقول: "كل مستنداتنا المصدرية PDFs، بعضها ممسوح ضوئيًا وبعضها رقمي. هل أي من هذا ينطبق علينا أصلًا، ولا نحلّ المشكلة الخطأ؟" ماذا تقول له عن موقع استراتيجية التقطيع في خطّ الأنابيب بالنسبة لمشكلة تحليل الـ PDF، وأي مشكلة ينبغي أن يُصلحها أولًا؟

---

## التسليم

ينتج هذا الدرس مستشار تقطيع يمكنك استخدامه لاختيار استراتيجية لأي نوع مستند.

**الأثر (Artifact):** `04-chunking-strategies/outputs/skill-chunking-strategy-picker.md`

يتضمّن ملف المهارة جدول قرار وأسئلة تشخيصية تربط خصائص مستندك بالاستراتيجية الصحيحة.

يشغّل `code/main.py` كل الاستراتيجيات الست على المستند العيّنة نفسه ويطبع أعداد الـ chunks، ومتوسّط الأطوال، ومخرجًا عيّنة لكلٍّ: مرجع سريع مفيد عند الاختيار بين الاستراتيجيات لنوع مستند جديد.

---

## التقييم

إخفاقات التقطيع غير مرئية وقت الإعداد ولا تظهر إلا أثناء الاسترجاع. إليك ثلاثة فحوصات تكشفها:

**الفحص 1: اختبار فحص حدّ الـ Chunk**

خذ 10 استعلامات من مجموعة اختبارك حيث تعرف الإجابة الصحيحة. استرجع أعلى 3 chunks. اقرأها. اسأل: هل تحتوي أيّ chunk منفردة إجابة كاملة قابلة للاستخدام للسؤال؟ إن لم تكن: إن امتدّت الإجابة عبر حدّ chunk: فاستراتيجية تقطيعك خاطئة لنوع المستند هذا.

يبدو هذا يدويًا، لكنه أعلى تشخيص إشارةً متاح. مهندس واحد يقضي 20 دقيقة في مراجعة الـ chunks السيّئة يوفّر أيامًا من مطاردة مشاكل embedding وهمية.

**الفحص 2: تغطية نطاق الإجابة**

لمجموعة مُصنّفة من أزواج (query, answer_text)، تحقّق ما إذا كانت أيّ chunk مُسترجَعة تحتوي نص الإجابة بالكامل:

```python
def answer_in_chunk(answer: str, chunks: list[str]) -> bool:
    """Check if any retrieved chunk contains the full answer text."""
    return any(answer.lower() in chunk.lower() for chunk in chunks)

coverage = sum(
    answer_in_chunk(answer, retrieved_chunks[query])
    for query, answer in labeled_pairs
) / len(labeled_pairs)

print(f"Answer coverage@top3: {coverage:.1%}")
# Below 70%: chunking is likely splitting answers across boundaries
```

**الفحص 3: توزيع متوسّط طول الـ Chunk**

شغّل استراتيجية تقطيعك على مجموعتك الكاملة وارسم توزيع أطوال الـ chunks (بالـ tokens). التوزيعات الصحّية تقريبًا جرسية الشكل حول حجمك المستهدف. الأعلام الحمراء:

- chunks كثيرة من 1–5 tokens: تقسيم عدواني، غالبًا علّة تقطيع إلى tokens
- chunks كثيرة عند حدّك الأقصى بالضبط بلا chunks أقصر: نقطة التقسيم لا تُفعَّل أبدًا (المستند بلا فواصل عند المستوى المتوقَّع)
- توزيع ثنائي النمط (كثير صغير + كثير كبير): تنسيق مستند غير متّسق تتعامل معه استراتيجيتك بشكل مختلف لمستندات مختلفة

```python
import tiktoken

enc = tiktoken.get_encoding("cl100k_base")

def chunk_length_stats(chunks: list[str]) -> dict:
    lengths = [len(enc.encode(c)) for c in chunks]
    return {
        "count": len(chunks),
        "mean_tokens": sum(lengths) / len(lengths),
        "min_tokens": min(lengths),
        "max_tokens": max(lengths),
        "p50": sorted(lengths)[len(lengths) // 2],
    }
```

---

## التمارين

1. **سهل:** شغّل كل الاستراتيجيات الست على المستند العيّنة في `code/main.py` وقارن أعداد الـ chunks ومتوسّط أطوال الـ tokens. لأي أنواع مستندات تُنتج كل استراتيجية أكثر التقسيمات "طبيعية"؟

2. **متوسط:** ابنِ مُقيِّم جودة تقطيع: خذ 10 جمل من مستندك العيّنة كـ "إجابات ذهبية". لكل استراتيجية، حوّل الـ chunks الناتجة إلى embedding، وشغّل بحثًا دلاليًا لكل إجابة ذهبية كاستعلام، وقِس ما النسبة التي تظهر فيها الـ chunk الصحيحة (التي تحتوي الإجابة) ضمن أعلى 3 نتائج. قارن الاستراتيجيات.

3. **صعب:** نفّذ استراتيجية هجينة: استخدم التقسيم الواعي بـ markdown للبنية، لكن داخل كل قسم طبّق التقطيع الدلالي لكشف تحوّلات المواضيع. تعامل مع حالة كون القسم أقصر من `min_chunk_chars` (لا تقسّمه أكثر). قِس هذا الهجين مقابل التقسيم المحرفي التعاودي على مستندك العيّنة باستخدام المُقيِّم من التمرين 2.

---

## المصطلحات الأساسية

| المصطلح | ما يقوله الناس | ما يعنيه فعلًا |
|------|----------------|----------------------|
| Chunk boundary | "حيث يُقسَّم المستند" | الموضع في النص حيث تنتهي chunk وتبدأ التالية؛ الحدود السيّئة تقطع وحدات ذات معنى (جمل، بنود) وتُدهور جودة الـ embedding |
| Chunk overlap | "محتوى متكرّر بين الـ chunks" | الـ N token في نهاية الـ chunk رقم K والموجودة أيضًا في بداية الـ chunk رقم K+1؛ يمنع فقدان المعلومات عند الحدود لكنه يزيد حجم الفهرس |
| Semantic chunking | "تقطيع مدعوم بالذكاء الاصطناعي" | التقسيم بناءً على انخفاضات تشابه جيب التمام بين الجمل المتجاورة: يكشف تغيّرات المواضيع بدلًا من العلامات البنيوية |
| Late chunking | "حوّل المستند إلى embedding أولًا، ثم قطّع" | حساب embeddings الـ chunks من تمثيلات tokens المستند الكامل، بحيث يحمل شعاع كل chunk وعيًا بسياق المستند المحيط |
| Sentence-window | "حوّل جملة إلى embedding، أرجِع السياق" | فهرسة الجمل المفردة لدقة الاسترجاع، لكن إرجاع نافذة من الجمل المحيطة للـ LLM لتوليد الإجابة |

---

## قراءات إضافية

- [Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models (JinaAI)](https://jina.ai/news/late-chunking-in-long-context-embedding-models/): التدوينة الأصلية للتقطيع المتأخّر بأمثلة كود ونتائج قياس تُظهر أين يتفوّق التقطيع المتأخّر على الأنهج التقليدية
- [LangChain Text Splitters Documentation](https://python.langchain.com/docs/how_to/split_by_header/): دليل عملي لـ MarkdownHeaderTextSplitter وRecursiveCharacterTextSplitter وSemanticChunker في LangChain؛ يشمل كودًا لكلٍّ
- [Evaluating Chunking Strategies for RAG (Pinecone)](https://www.pinecone.io/learn/chunking-strategies/): مقارنة تجريبية لاستراتيجيات التقطيع ثابتة الحجم والتعاودية والدلالية بقياسات جودة استرجاع؛ بيانات قياس مفيدة
- [LlamaIndex SemanticSplitterNodeParser](https://docs.llamaindex.ai/en/stable/examples/node_parsers/semantic_chunking/): تنفيذ LlamaIndex للتقطيع الدلالي بمئينية نقطة فاصلة قابلة للتهيئة
- [Tiktoken Library (OpenAI)](https://github.com/openai/tiktoken): مُقطِّع BPE سريع تستخدمه نماذج OpenAI؛ استخدمه حين تحتاج أعداد tokens دقيقة لقيود حجم الـ chunk المطابقة لسلوك الإنتاج
