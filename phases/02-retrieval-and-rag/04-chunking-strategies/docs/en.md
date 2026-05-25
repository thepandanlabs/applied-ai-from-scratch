# Chunking Strategies

> How you split documents determines what your retrieval can find. Bad chunking makes great embeddings retrieve the wrong thing.

**Type:** Build
**Languages:** Python
**Prerequisites:** 02-01 Embeddings Intuition, 02-03 Vector Stores
**Time:** ~80 minutes
**Phase:** 02 · Retrieval & RAG

## Learning Objectives

- Implement all six major chunking strategies as standalone, testable functions
- Explain the failure modes of each strategy and when to prefer one over another
- Identify whether a retrieval failure is caused by chunking rather than embedding quality
- Apply semantic chunking to detect topic boundaries in long-form content
- Explain late chunking and why it preserves long-range context that other strategies lose

---

## The Problem

A legal tech company built a RAG system over their contract corpus. Embedding quality was good: sanity checks passed. Vector store was correctly configured. But when lawyers queried for "termination clauses," the retrieved chunks consistently returned mid-sentence fragments that had the right keywords but no actual legal meaning: just the word "terminate" appearing in a context that was grammatically cut off from the operative sentence. The lawyers couldn't use the output. They called it "word salad."

The root cause: fixed-size chunking with a 256-token window and no overlap was splitting sentences in the middle. The operative clause: "Either party may terminate this agreement upon 30 days written notice": was split across two chunks. Neither chunk alone contained a complete, usable legal statement. The embedding model faithfully embedded half-sentences that happened to contain "terminate," and the retrieval system returned them.

Chunking is the step that most RAG tutorials skip or under-specify. It happens before embedding, so its failures look like embedding failures. It happens before retrieval, so its failures look like retrieval failures. But a correctly built embedding and retrieval system can only return what's in the index, and if the index contains fragments, you get fragment-based answers. This lesson is about building chunk boundaries that preserve meaning.

---

## The Concept

### What Chunking Actually Does

An embedding model maps a fixed-length text to a vector. But documents are not fixed-length: a contract might be 80 pages, a support article might be 200 words. You can't embed an 80-page document as a single vector because:

1. Most models have a 512-token context limit: long documents are truncated
2. Even with long-context models, a single vector averages the meaning of 80 pages; a specific clause becomes a tiny signal in a sea of other content
3. The retrieved unit must be small enough to fit in the LLM's context window alongside the query

Chunking is the process of splitting a document into units small enough to embed meaningfully and retrieve specifically.

The key tension:

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

The sweet spot depends on your document type and query type. That's why there are six strategies, not one.

### The Six Strategies at a Glance

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

### How Chunking Affects Embedding Quality

The embedding of a chunk is its single vector representation. If the chunk contains a complete thought: a paragraph about one topic, or a full sentence: the vector is a clean representation of that idea. If the chunk is a fragment, the vector is noisy:

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

The bad chunk still gets retrieved for payment-related queries (it mentions payments) but the context is incoherent. The LLM receives it and either hallucinates an answer or confesses uncertainty.

### Late Chunking: A Different Mental Model

The other five strategies chunk first, then embed. Late chunking inverts this: embed the full document first (using a long-context model), then extract chunk-level embeddings from the full-document token representations.

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

This matters when early chunks need context from later in the document. In a technical manual, chapter 1 might reference concepts fully explained in chapter 5. Traditional chunking embeds chapter 1 without any awareness of chapter 5. Late chunking's embedding of chapter 1 was computed with all of chapter 5 in the context window.

---

## Build It

We implement all six strategies as standalone functions. Each takes a text string and returns a list of chunk strings.

### Step 1: Install Dependencies and Load Sample Document

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

### Step 2: Strategy 1: Fixed-Size with Overlap

The simplest strategy. Slice the text into windows of N tokens, advancing by `N - overlap` tokens each step. The overlap ensures that information near a boundary is preserved in both adjacent chunks.

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

### Step 3: Strategy 2: Recursive Character Splitter

Try to split on the best separator available: paragraph breaks first, then sentence breaks, then word breaks, then individual characters. Only use finer-grained splits when a chunk is still too large after the coarse split.

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

### Step 4: Strategy 3: Markdown-Aware Splitter

Split on Markdown headers. Each H1/H2/H3 section becomes one or more chunks, with the header included in each chunk so the embedding carries the section's topic.

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

### Step 5: Strategy 4: Sentence-Window

Store one sentence per chunk, but embed each sentence with a window of surrounding sentences as context. At retrieval time, return the original sentence (for precision) but also provide the surrounding window (for LLM context).

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

> **Real-world check:** A data engineer on your team says: "We already split on newlines in our ETL pipeline and it works fine for structured data. Why do we need all these strategies? Isn't this just overcomplicating things?" How do you explain when newline-splitting is actually fine and when it causes retrieval failures that look like model problems?

### Step 6: Strategy 5: Semantic Chunking

Embed each sentence, then measure cosine similarity between adjacent sentences. Where similarity drops significantly (a topic boundary), start a new chunk.

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

### Step 7: Strategy 6: Late Chunking

Late chunking requires a model that provides token-level embeddings for a full document. We use the approach described in the JinaAI late chunking paper: encode the full document, then mean-pool the token embeddings within each chunk's span to produce chunk-level vectors.

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

## Use It

LangChain's text splitters implement strategies 1–3 with a polished API. If you're building on LangChain, use these rather than your own implementations: they handle edge cases (Unicode, whitespace normalization, empty chunks) that are tedious to get right:

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

LlamaIndex provides `SentenceSplitter` and `SemanticSplitterNodeParser` for strategies 4 and 5:

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

What the frameworks add over your raw implementations: better tokenization handling, `Document` object wrappers that carry metadata through the pipeline, and integration with retrieval chains. What they don't add: better chunking quality. The algorithms are the same.

> **Perspective shift:** A teammate says: "All our source documents are PDFs, some scanned, some digital. Does any of this even apply to us, or are we solving the wrong problem?" What would you tell them about where chunking strategy sits in the pipeline relative to the PDF parsing problem, and which issue they should fix first?

---

## Ship It

This lesson produces a chunking advisor you can use to pick a strategy for any document type.

**Artifact:** `04-chunking-strategies/outputs/skill-chunking-strategy-picker.md`

The skill file includes a decision table and diagnostic questions that map your document characteristics to the right strategy.

The `code/main.py` runs all six strategies on the same sample document and prints chunk counts, average lengths, and a sample output for each: a useful quick-reference when choosing between strategies for a new document type.

---

## Evaluate It

Chunking failures are invisible at setup time and only surface during retrieval. Three checks that reveal them:

**Check 1: The Chunk Boundary Inspection Test**

Take 10 queries from your test set where you know the correct answer. Retrieve the top-3 chunks. Read them. Ask: does any single chunk contain a complete, usable answer to the question? If not: if the answer spans a chunk boundary: your chunking strategy is wrong for this document type.

This sounds manual, but it's the highest-signal diagnostic available. One engineer spending 20 minutes reviewing bad chunks saves days of chasing phantom embedding problems.

**Check 2: Answer Span Coverage**

For a labeled set of (query, answer_text) pairs, check whether any retrieved chunk fully contains the answer text:

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

**Check 3: Average Chunk Length Distribution**

Run your chunking strategy on your full corpus and plot the distribution of chunk lengths (in tokens). Healthy distributions are roughly bell-shaped around your target size. Red flags:

- Many chunks of 1–5 tokens: aggressive splitting, probably tokenization bug
- Many chunks at exactly your max size with no shorter chunks: the split point is never being triggered (document has no separators at the expected level)
- Bimodal distribution (many tiny + many large): inconsistent document formatting that your strategy handles differently for different docs

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

## Exercises

1. **Easy:** Run all six chunking strategies on the sample document in `code/main.py` and compare their chunk counts and average token lengths. For which document types does each strategy produce the most "natural" splits?

2. **Medium:** Build a chunking quality evaluator: take 10 sentences from your sample document as "golden answers." For each strategy, embed the resulting chunks, run semantic search for each golden answer as a query, and measure what fraction of the time the correct chunk (the one containing the answer) appears in the top-3 results. Compare strategies.

3. **Hard:** Implement a hybrid strategy: use markdown-aware splitting for structure, but within each section apply semantic chunking to detect topic shifts. Handle the case where a section is shorter than `min_chunk_chars` (don't split it further). Benchmark this hybrid against recursive-character splitting on your sample document using the evaluator from Exercise 2.

---

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Chunk boundary | "Where the document gets split" | The position in text where one chunk ends and the next begins; bad boundaries split meaningful units (sentences, clauses) and degrade embedding quality |
| Chunk overlap | "Repeated content between chunks" | The N tokens at the end of chunk K that are also at the start of chunk K+1; prevents information loss at boundaries but increases index size |
| Semantic chunking | "AI-powered chunking" | Splitting based on cosine similarity drops between adjacent sentences: detects topic changes rather than structural markers |
| Late chunking | "Embed the doc first, chunk later" | Computing chunk embeddings from full-document token representations, so each chunk's vector carries awareness of the surrounding document context |
| Sentence-window | "Embed one sentence, return context" | Indexing individual sentences for retrieval precision, but returning a window of surrounding sentences to the LLM for answer generation |

---

## Further Reading

- [Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models (JinaAI)](https://jina.ai/news/late-chunking-in-long-context-embedding-models/): The original late chunking blog post with code examples and benchmark results showing where late chunking beats traditional approaches
- [LangChain Text Splitters Documentation](https://python.langchain.com/docs/how_to/split_by_header/): Practical guide to LangChain's MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter, and SemanticChunker; includes code for each
- [Evaluating Chunking Strategies for RAG (Pinecone)](https://www.pinecone.io/learn/chunking-strategies/): Empirical comparison of fixed-size, recursive, and semantic chunking strategies with retrieval quality measurements; useful benchmark data
- [LlamaIndex SemanticSplitterNodeParser](https://docs.llamaindex.ai/en/stable/examples/node_parsers/semantic_chunking/): LlamaIndex's implementation of semantic chunking with configurable breakpoint percentile
- [Tiktoken Library (OpenAI)](https://github.com/openai/tiktoken): Fast BPE tokenizer used by OpenAI models; use this when you need accurate token counts for chunk size constraints that match production behavior
