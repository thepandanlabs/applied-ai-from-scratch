"""
Chunking Strategies - Phase 02 Lesson 04
appliedaifromscratch.com

Implements all 6 chunking strategies as standalone functions.
Runs each on a sample document and prints statistics + sample output.

pip install nltk tiktoken sentence-transformers

On first run, NLTK will download punkt tokenizer data automatically.
"""

from __future__ import annotations

import re
import textwrap
from typing import Any

# ---------------------------------------------------------------------------
# Sample document (multi-topic prose + Markdown structure)
# ---------------------------------------------------------------------------

SAMPLE_DOCUMENT = """\
# API Rate Limiting Guide

## Overview

Our API uses rate limiting to ensure fair usage and maintain service quality for all customers. Understanding these limits will help you design applications that stay within bounds and handle limit responses gracefully.

## Default Limits

Every API key is subject to default rate limits. The standard tier allows 60 requests per minute and 10,000 requests per day. Enterprise accounts receive higher limits by default and can request custom quotas.

Requests that exceed the rate limit receive a 429 Too Many Requests response. The response includes a Retry-After header indicating how many seconds to wait before retrying.

## Handling 429 Responses

When your application receives a 429 response, it should implement exponential backoff. Start with a 1-second delay, then double the delay on each subsequent retry up to a maximum of 32 seconds. After 5 failed retries, surface the error to the user or log it for investigation.

Do not retry immediately on receiving a 429 - this will only worsen the situation. Burst behavior that triggers rate limits is usually caused by unbatched requests in tight loops. Review your request patterns before increasing retry counts.

## Monitoring Your Usage

You can monitor your API usage from the dashboard under Settings > API Usage. The usage page shows requests per minute, daily totals, and a breakdown by endpoint. An alert threshold can be set to notify you before you hit your limit.

If you consistently hit rate limits, consider batching requests, caching responses where possible, or upgrading your plan. The rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset) are included in every response.

## Enterprise Options

Enterprise customers can request custom rate limits through the sales team. Custom limits are applied per API key and can be set independently for different endpoints. Increased limits are subject to a capacity review and may require a dedicated infrastructure allocation.
""".strip()

# A second sample document: flat prose without Markdown (no headers)
PROSE_DOCUMENT = """\
Distributed systems face a fundamental tradeoff known as the CAP theorem. It states that any distributed data store can provide only two of three guarantees: consistency, availability, and partition tolerance.

Consistency means every read receives the most recent write or an error. Availability means every request receives a response, though it may not be the most recent version. Partition tolerance means the system continues to operate despite network partitions that prevent some nodes from communicating.

In practice, network partitions do occur in any distributed system, so the real choice is between consistency and availability during a partition. Systems like HBase and Zookeeper choose consistency, returning errors when a partition occurs rather than potentially stale data. Systems like Cassandra and CouchDB choose availability, returning the best available data and resolving conflicts later.

The choice has major implications for application design. Consistency-first systems require clients to handle errors and retries explicitly. Availability-first systems require conflict resolution strategies-last-write-wins, vector clocks, or application-level merge functions.

Modern systems increasingly use tunable consistency models that let operators configure the tradeoff per query. Cassandra allows choosing from ONE, QUORUM, and ALL consistency levels at read time. This gives teams control over where on the spectrum each operation falls.

Understanding the CAP theorem helps engineers make intentional database selection decisions rather than discovering the tradeoffs under production load.
""".strip()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens using tiktoken (accurate for OpenAI models)."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding(encoding_name)
        return len(enc.encode(text))
    except ImportError:
        # Rough approximation: 1 token ≈ 4 characters
        return len(text) // 4


def chunk_stats(chunks: list[str | dict], label: str) -> None:
    """Print summary statistics for a list of chunks."""
    # Handle sentence-window dicts
    texts = [
        c["chunk_text"] if isinstance(c, dict) else c
        for c in chunks
    ]
    texts = [t for t in texts if t.strip()]

    if not texts:
        print(f"  {label}: 0 chunks")
        return

    token_counts = [count_tokens(t) for t in texts]
    mean_tok = sum(token_counts) / len(token_counts)
    min_tok = min(token_counts)
    max_tok = max(token_counts)
    p50 = sorted(token_counts)[len(token_counts) // 2]

    print(f"\n  {label}")
    print(f"    Chunks:       {len(texts)}")
    print(f"    Tokens mean:  {mean_tok:.0f}")
    print(f"    Tokens range: {min_tok} – {max_tok}")
    print(f"    Tokens p50:   {p50}")


def print_chunks(chunks: list[str | dict], label: str, max_show: int = 2) -> None:
    """Print the first max_show chunks with formatting."""
    print(f"\n  --- {label} (showing first {min(max_show, len(chunks))}) ---")
    for i, chunk in enumerate(chunks[:max_show]):
        if isinstance(chunk, dict):
            text = chunk.get("chunk_text", "")
            ctx = chunk.get("context_text", "")
            print(f"\n  Chunk {i+1} [embed]: {text[:120]!r}")
            print(f"  Chunk {i+1} [ctx]:   {ctx[:200]!r}")
        else:
            wrapped = textwrap.fill(chunk[:300], width=70, initial_indent="    ", subsequent_indent="    ")
            print(f"\n  Chunk {i+1}:\n{wrapped}")
            if len(chunk) > 300:
                print("    [...]")


# ---------------------------------------------------------------------------
# Strategy 1: Fixed-size with overlap
# ---------------------------------------------------------------------------

def fixed_size_chunks(
    text: str,
    chunk_size: int = 200,
    overlap: int = 40,
    encoding_name: str = "cl100k_base",
) -> list[str]:
    """
    Slice text into fixed token-count windows with overlap.

    chunk_size: number of tokens per chunk
    overlap: tokens shared between consecutive chunks

    When to use: homogeneous content, baseline comparison, deterministic output.
    Failure mode: splits mid-sentence; embedding of partial sentences is noisy.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding(encoding_name)
        tokens = enc.encode(text)
        decode = lambda t: enc.decode(t)
    except ImportError:
        # Fallback: character-level approximation
        tokens = list(text)
        decode = lambda t: "".join(t)

    chunks = []
    stride = max(1, chunk_size - overlap)

    for start in range(0, len(tokens), stride):
        end = min(start + chunk_size, len(tokens))
        chunk = decode(tokens[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(tokens):
            break

    return chunks


# ---------------------------------------------------------------------------
# Strategy 2: Recursive character splitter
# ---------------------------------------------------------------------------

def recursive_char_split(
    text: str,
    max_chars: int = 800,
    overlap_chars: int = 100,
    separators: list[str] | None = None,
) -> list[str]:
    """
    Split on progressively finer separators until chunks fit within max_chars.

    When to use: general prose, default when document type is unknown.
    Failure mode: doesn't understand document structure; very long paragraphs
    still get split arbitrarily.
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", "! ", "? ", " ", ""]

    def _merge_with_overlap(parts: list[str]) -> list[str]:
        chunks: list[str] = []
        current = ""
        for part in parts:
            if not part.strip():
                continue
            candidate = (current + " " + part).strip() if current else part
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                    overlap = current[-overlap_chars:] if overlap_chars else ""
                    current = (overlap + " " + part).strip() if overlap else part
                else:
                    current = part
        if current:
            chunks.append(current)
        return chunks

    def _split(text: str, sep_idx: int) -> list[str]:
        if len(text) <= max_chars or sep_idx >= len(separators):
            return [text] if text.strip() else []
        sep = separators[sep_idx]
        parts = text.split(sep) if sep else list(text)
        sub_parts: list[str] = []
        for part in parts:
            if len(part) > max_chars:
                sub_parts.extend(_split(part, sep_idx + 1))
            elif part.strip():
                sub_parts.append(part)
        return _merge_with_overlap(sub_parts)

    return [c for c in _split(text, 0) if c.strip()]


# ---------------------------------------------------------------------------
# Strategy 3: Markdown-aware splitter
# ---------------------------------------------------------------------------

def markdown_split(
    text: str,
    max_chars: int = 1000,
) -> list[str]:
    """
    Split Markdown on H1/H2/H3 headers. Include the header in each chunk.

    When to use: documentation, wikis, READMEs - any content with headers.
    Failure mode: sections longer than max_chars need further splitting;
    non-Markdown documents produce one large chunk.
    """
    header_pattern = re.compile(r'^(#{1,3})\s+(.+)$', re.MULTILINE)
    positions = [(m.start(), m.group()) for m in header_pattern.finditer(text)]

    if not positions:
        return [text.strip()]

    chunks: list[str] = []
    for i, (start, _) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        section = text[start:end].strip()

        if len(section) <= max_chars:
            chunks.append(section)
        else:
            # Section is too large - extract header and split body by paragraphs
            header_match = header_pattern.match(section)
            header_line = header_match.group() + "\n\n" if header_match else ""
            body = section[len(header_line):]
            paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

            current = header_line
            for para in paragraphs:
                candidate = current + para + "\n\n"
                if len(candidate) <= max_chars:
                    current = candidate
                else:
                    if current.strip():
                        chunks.append(current.strip())
                    current = header_line + para + "\n\n"
            if current.strip():
                chunks.append(current.strip())

    return [c for c in chunks if c]


# ---------------------------------------------------------------------------
# Strategy 4: Sentence-window
# ---------------------------------------------------------------------------

def sentence_window_chunks(
    text: str,
    window_size: int = 2,
) -> list[dict[str, Any]]:
    """
    One sentence per chunk, embedded with surrounding context window.

    Each chunk is a dict:
      chunk_text:     the sentence (embed this)
      context_text:   sentence + window (return to the LLM)
      sentence_index: position in document

    When to use: precision Q&A, when exact sentence retrieval is needed.
    Failure mode: very short sentences produce weak embeddings.
    """
    try:
        import nltk
        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)
        from nltk.tokenize import sent_tokenize
        sentences = sent_tokenize(text)
    except ImportError:
        # Fallback: split on ". " "? " "! "
        sentences = re.split(r'(?<=[.!?])\s+', text)

    sentences = [s.strip() for s in sentences if s.strip()]
    result = []

    for i, sentence in enumerate(sentences):
        window_start = max(0, i - window_size)
        window_end = min(len(sentences), i + window_size + 1)
        context = " ".join(sentences[window_start:window_end])
        result.append({
            "chunk_text": sentence,
            "context_text": context,
            "sentence_index": i,
        })

    return result


# ---------------------------------------------------------------------------
# Strategy 5: Semantic chunking
# ---------------------------------------------------------------------------

def semantic_chunks(
    text: str,
    threshold: float = 0.75,
    min_chunk_chars: int = 80,
) -> list[str]:
    """
    Split where cosine similarity between adjacent sentences drops below threshold.

    When to use: long documents with multiple topics (reports, articles).
    Failure mode: expensive (embeds every sentence); threshold needs tuning.
    """
    try:
        from nltk.tokenize import sent_tokenize
        import numpy as np
    except ImportError:
        print("  [SKIP] semantic_chunks requires nltk and numpy")
        return [text]

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("  [SKIP] semantic_chunks requires sentence-transformers")
        return [text]

    try:
        import nltk
        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)
        sentences = sent_tokenize(text)
    except Exception:
        sentences = re.split(r'(?<=[.!?])\s+', text)

    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 1:
        return sentences

    print("  [semantic_chunks] Embedding sentences for similarity analysis...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(sentences, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)

    # Pairwise adjacent similarity
    similarities = [
        float(embeddings[i] @ embeddings[i + 1])
        for i in range(len(embeddings) - 1)
    ]

    chunks: list[str] = []
    current: list[str] = [sentences[0]]

    for i, sim in enumerate(similarities):
        if sim < threshold and len(" ".join(current)) >= min_chunk_chars:
            chunks.append(" ".join(current))
            current = [sentences[i + 1]]
        else:
            current.append(sentences[i + 1])

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if c.strip()]


# ---------------------------------------------------------------------------
# Strategy 6: Late chunking
# ---------------------------------------------------------------------------

def late_chunking_demo(
    text: str,
    base_chunks: list[str],
) -> list[dict[str, Any]]:
    """
    Late chunking: embed the full document, then extract chunk embeddings
    from the token-level representations of the full document.

    This preserves long-range context that standard chunking loses:
    early chunks in the document are embedded with "knowledge of" later chunks.

    base_chunks: pre-defined chunk boundaries (any strategy can produce these)

    Returns: list of {chunk_text, embedding, method}

    When to use: long documents where early sections reference later content.
    Limitation: requires a model that exposes token-level embeddings.
    """
    import numpy as np

    print("  [late_chunking] Attempting to load jina-embeddings-v2-base-en...")

    try:
        import torch
        from transformers import AutoModel, AutoTokenizer

        model_name = "jinaai/jina-embeddings-v2-base-en"
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        model_hf = AutoModel.from_pretrained(model_name, trust_remote_code=True)
        model_hf.eval()

        # Encode the FULL document - get token-level embeddings
        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=8192,
            return_offsets_mapping=True,
        )
        offsets = inputs.pop("offset_mapping")[0]

        with torch.no_grad():
            outputs = model_hf(**inputs)

        token_embeddings = outputs.last_hidden_state[0]  # (seq_len, hidden_dim)

        # Map each chunk to a token range and mean-pool
        results = []
        text_lower = text.lower()
        search_start = 0

        for chunk_text in base_chunks:
            chunk_lower = chunk_text.lower()
            pos = text_lower.find(chunk_lower, search_start)
            if pos == -1:
                # Chunk not found at position - approximate
                pos = search_start

            chunk_end = pos + len(chunk_text)

            # Find token indices that overlap with this chunk's character span
            token_indices = [
                i for i, (tok_start, tok_end) in enumerate(offsets.tolist())
                if tok_start < chunk_end and tok_end > pos and tok_end > tok_start
            ]

            if token_indices:
                chunk_emb = token_embeddings[token_indices].mean(dim=0).numpy()
            else:
                # Fallback: use the full document embedding
                chunk_emb = token_embeddings.mean(dim=0).numpy()

            norm = np.linalg.norm(chunk_emb)
            chunk_emb = chunk_emb / norm if norm > 0 else chunk_emb

            results.append({
                "chunk_text": chunk_text,
                "embedding": chunk_emb,
                "method": "late_chunking",
            })
            search_start = max(search_start, pos)

        print(f"  [late_chunking] Produced {len(results)} chunks with full-doc context")
        return results

    except (ImportError, Exception) as e:
        print(f"  [late_chunking] {e}")
        print("  Falling back to standard sentence-transformer embeddings")
        print("  (For true late chunking: pip install transformers torch)")

        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embeddings = model.encode(
                base_chunks, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
            )
            return [
                {"chunk_text": chunk, "embedding": emb, "method": "standard_fallback"}
                for chunk, emb in zip(base_chunks, embeddings)
            ]
        except ImportError:
            print("  [SKIP] sentence-transformers also not available")
            return [{"chunk_text": c, "embedding": np.zeros(384), "method": "unavailable"}
                    for c in base_chunks]


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def answer_coverage(
    labeled_pairs: list[tuple[str, str]],
    all_chunks: list[str],
    top_k: int = 3,
    model_name: str = "all-MiniLM-L6-v2",
) -> float:
    """
    Measure fraction of labeled queries where the correct answer appears
    in the top-k retrieved chunks.

    labeled_pairs: [(query_text, answer_text), ...]
    all_chunks: the full set of chunks from one strategy
    """
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        print("  [SKIP] answer_coverage requires sentence-transformers and numpy")
        return 0.0

    if not all_chunks:
        return 0.0

    model = SentenceTransformer(model_name)
    chunk_vecs = model.encode(all_chunks, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)

    hits = 0
    for query_text, answer_text in labeled_pairs:
        q_vec = model.encode([query_text], normalize_embeddings=True, convert_to_numpy=True)[0]
        scores = chunk_vecs @ q_vec
        top_indices = scores.argsort()[::-1][:top_k]
        top_chunks = [all_chunks[i] for i in top_indices]
        if any(answer_text.lower() in c.lower() for c in top_chunks):
            hits += 1

    return hits / len(labeled_pairs)


def token_distribution(chunks: list[str]) -> dict:
    """Compute token count statistics for a list of chunks."""
    if not chunks:
        return {"count": 0}
    lengths = [count_tokens(c if isinstance(c, str) else c.get("chunk_text", ""))
               for c in chunks]
    lengths.sort()
    n = len(lengths)
    return {
        "count": n,
        "mean": round(sum(lengths) / n, 1),
        "min": lengths[0],
        "max": lengths[-1],
        "p25": lengths[n // 4],
        "p50": lengths[n // 2],
        "p75": lengths[3 * n // 4],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Phase 02 · Lesson 04 - Chunking Strategies")
    print("=" * 60)

    doc_tokens = count_tokens(SAMPLE_DOCUMENT)
    print(f"\nSample document: {len(SAMPLE_DOCUMENT)} chars, ~{doc_tokens} tokens")
    print(f"Prose document:  {len(PROSE_DOCUMENT)} chars, ~{count_tokens(PROSE_DOCUMENT)} tokens")

    # ------------------------------------------------------------------
    # Strategy 1: Fixed-size + overlap
    # ------------------------------------------------------------------
    print("\n" + "=" * 50)
    print("Strategy 1: Fixed-Size with Overlap")
    print("=" * 50)

    chunks_fixed = fixed_size_chunks(SAMPLE_DOCUMENT, chunk_size=200, overlap=40)
    stats = token_distribution(chunks_fixed)
    print(f"  Count: {stats['count']} | Mean tokens: {stats['mean']} | Range: {stats['min']}–{stats['max']}")
    print_chunks(chunks_fixed, "Fixed-size chunks (chunk_size=200, overlap=40)", max_show=2)

    # ------------------------------------------------------------------
    # Strategy 2: Recursive character splitter
    # ------------------------------------------------------------------
    print("\n" + "=" * 50)
    print("Strategy 2: Recursive Character Splitter")
    print("=" * 50)

    chunks_recursive = recursive_char_split(SAMPLE_DOCUMENT, max_chars=600, overlap_chars=80)
    stats = token_distribution(chunks_recursive)
    print(f"  Count: {stats['count']} | Mean tokens: {stats['mean']} | Range: {stats['min']}–{stats['max']}")
    print_chunks(chunks_recursive, "Recursive chunks (max_chars=600, overlap=80)", max_show=2)

    # Also test on flat prose (no markdown)
    chunks_prose = recursive_char_split(PROSE_DOCUMENT, max_chars=400, overlap_chars=60)
    print(f"\n  On prose document: {len(chunks_prose)} chunks")
    print_chunks(chunks_prose, "Recursive on prose", max_show=1)

    # ------------------------------------------------------------------
    # Strategy 3: Markdown-aware
    # ------------------------------------------------------------------
    print("\n" + "=" * 50)
    print("Strategy 3: Markdown-Aware Splitter")
    print("=" * 50)

    chunks_md = markdown_split(SAMPLE_DOCUMENT, max_chars=800)
    stats = token_distribution(chunks_md)
    print(f"  Count: {stats['count']} | Mean tokens: {stats['mean']} | Range: {stats['min']}–{stats['max']}")
    print_chunks(chunks_md, "Markdown chunks (max_chars=800)", max_show=2)

    # Non-markdown falls back to single chunk
    chunks_md_prose = markdown_split(PROSE_DOCUMENT, max_chars=800)
    print(f"\n  On prose (no headers): {len(chunks_md_prose)} chunks")
    print("  → Expected: 1 large chunk (no header split points found)")

    # ------------------------------------------------------------------
    # Strategy 4: Sentence-window
    # ------------------------------------------------------------------
    print("\n" + "=" * 50)
    print("Strategy 4: Sentence-Window")
    print("=" * 50)

    chunks_sw = sentence_window_chunks(SAMPLE_DOCUMENT, window_size=2)
    print(f"  Count: {len(chunks_sw)} (one per sentence)")
    print_chunks(chunks_sw, "Sentence-window (window=2)", max_show=2)

    # Illustrate: the embedded text is short, the context is wider
    if chunks_sw:
        sample = chunks_sw[min(5, len(chunks_sw) - 1)]
        print(f"\n  Embed:   {count_tokens(sample['chunk_text'])} tokens")
        print(f"  Context: {count_tokens(sample['context_text'])} tokens")
        print("  → The LLM receives the context; the vector index is built on the sentence")

    # ------------------------------------------------------------------
    # Strategy 5: Semantic chunking
    # ------------------------------------------------------------------
    print("\n" + "=" * 50)
    print("Strategy 5: Semantic Chunking")
    print("=" * 50)

    chunks_semantic = semantic_chunks(PROSE_DOCUMENT, threshold=0.75, min_chunk_chars=80)
    stats = token_distribution(chunks_semantic)
    print(f"  Count: {stats['count']} | Mean tokens: {stats['mean']} | Range: {stats['min']}–{stats['max']}")
    print_chunks(chunks_semantic, "Semantic chunks (threshold=0.75)", max_show=2)

    # Show where the splits happened (low similarity = topic boundary)
    print("\n  The similarity drops signal topic boundaries:")
    print("  (Each break = the model detected a topic change)")

    # ------------------------------------------------------------------
    # Strategy 6: Late chunking demo
    # ------------------------------------------------------------------
    print("\n" + "=" * 50)
    print("Strategy 6: Late Chunking")
    print("=" * 50)

    # First produce base chunks (using recursive split as boundaries)
    base = recursive_char_split(PROSE_DOCUMENT, max_chars=300, overlap_chars=0)
    late_results = late_chunking_demo(PROSE_DOCUMENT, base)

    print(f"\n  Produced {len(late_results)} chunks")
    print(f"  Method: {late_results[0]['method'] if late_results else 'none'}")
    if late_results and late_results[0]["embedding"] is not None:
        dim = late_results[0]["embedding"].shape[0] if hasattr(late_results[0]["embedding"], "shape") else 0
        print(f"  Embedding dim: {dim}")
    print_chunks(
        [r["chunk_text"] for r in late_results],
        "Late-chunked base splits",
        max_show=2,
    )

    # ------------------------------------------------------------------
    # Comparison summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("STRATEGY COMPARISON SUMMARY")
    print("=" * 60)

    strategies = [
        ("Fixed-size + overlap", chunks_fixed),
        ("Recursive char split", chunks_recursive),
        ("Markdown-aware", chunks_md),
        ("Sentence-window", [c["chunk_text"] for c in chunks_sw]),
        ("Semantic", chunks_semantic),
        ("Late chunking (base)", [r["chunk_text"] for r in late_results]),
    ]

    print(f"\n{'Strategy':<28} {'Chunks':>7} {'Mean tok':>9} {'Min':>5} {'Max':>5}")
    print("-" * 60)
    for name, chunks in strategies:
        texts = [c if isinstance(c, str) else c.get("chunk_text", "") for c in chunks]
        stats = token_distribution(texts)
        print(
            f"{name:<28} {stats['count']:>7} {stats['mean']:>9} "
            f"{stats['min']:>5} {stats['max']:>5}"
        )

    # ------------------------------------------------------------------
    # Evaluation: which strategy retrieves best on sample queries?
    # ------------------------------------------------------------------
    print("\n" + "=" * 50)
    print("Retrieval Quality Check (requires sentence-transformers)")
    print("=" * 50)

    labeled_pairs = [
        ("what happens when I exceed the rate limit", "receive a 429 Too Many Requests response"),
        ("how many requests per day does the standard tier allow", "10,000 requests per day"),
        ("how should I handle rate limit errors", "exponential backoff"),
        ("where do I view my API usage statistics", "dashboard under Settings"),
    ]

    for name, chunks in strategies[:4]:  # skip late chunking (embeddings not standard strings)
        texts = [c if isinstance(c, str) else c.get("chunk_text", "") for c in chunks]
        try:
            coverage = answer_coverage(labeled_pairs, texts, top_k=3)
            print(f"  {name:<28} answer coverage@3: {coverage:.1%}")
        except Exception as e:
            print(f"  {name:<28} [SKIP: {e}]")

    print("\n" + "=" * 60)
    print("Done. Next: Lesson 05 - Naive RAG (full pipeline)")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Decision guide
    # ------------------------------------------------------------------
    print("""
Decision Guide
──────────────
  Document type          → Recommended strategy
  ─────────────────────────────────────────────
  PDFs, contracts        → Fixed-size + overlap (start) or Recursive
  Blog posts, articles   → Recursive or Semantic
  Docs, wikis, READMEs   → Markdown-aware
  Q&A datasets           → Sentence-window
  Long reports, books    → Semantic or Late chunking
  Code (see Lesson 14)   → AST-aware (not covered here)
    """)


if __name__ == "__main__":
    main()
