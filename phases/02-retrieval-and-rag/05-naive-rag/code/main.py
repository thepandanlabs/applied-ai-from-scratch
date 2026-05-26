# pip install openai numpy
# Usage:
#   export OPENAI_API_KEY=sk-...
#   python main.py document.txt                        # demo mode (3 generic questions)
#   python main.py document.txt "What is the main argument?"  # single query
#
# This is a complete, zero-framework RAG pipeline.
# Everything that matters fits in four functions:
#   ingest()   → load + chunk + embed + store
#   retrieve() → embed query + cosine search
#   build_prompt() → format context into prompt
#   generate() → LLM call → answer + sources

import os
import sys
import uuid
from typing import Any

import numpy as np
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"
DEFAULT_CHUNK_SIZE = 400   # words per chunk
DEFAULT_OVERLAP = 50       # words shared between adjacent chunks
DEFAULT_TOP_K = 5          # number of chunks to retrieve per query

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# ---------------------------------------------------------------------------
# Step 0: The "database"
# ---------------------------------------------------------------------------

def make_store() -> dict[str, dict[str, Any]]:
    """
    Return an empty in-memory document store.
    Schema: {chunk_id: {"text": str, "vector": np.ndarray, "metadata": dict}}
    This is the entire vector database. No dependencies required.
    """
    return {}


def add_to_store(
    store: dict,
    text: str,
    vector: list[float],
    metadata: dict | None = None,
) -> str:
    """Add a chunk and its embedding to the store. Returns the chunk ID."""
    chunk_id = str(uuid.uuid4())[:8]
    store[chunk_id] = {
        "text": text,
        "vector": np.array(vector, dtype=np.float32),
        "metadata": metadata or {},
    }
    return chunk_id

# ---------------------------------------------------------------------------
# Step 1: Ingest - load + chunk + embed + store
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> list[str]:
    """
    Split text into overlapping fixed-size word-count chunks.

    overlap: number of words repeated at the start of the next chunk.
    This ensures answers that span a chunk boundary are still retrievable.

    Tune chunk_size for your domain:
      - Prose:     300-500 words
      - Code:      use logical block splitting instead (lesson 14)
      - Markdown:  split at headers (lesson 04)
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start = end - overlap
    return chunks


def embed(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts in a single batched API call.
    Returns one vector per input text.

    Batching matters: 50 texts in one call costs ~1/50th the latency
    of 50 individual calls. Always embed in bulk during ingest.
    """
    if not texts:
        return []
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    # API returns items in the same order as input
    return [item.embedding for item in response.data]


def ingest(filepath: str, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> dict:
    """
    Full ingest pipeline: load file → chunk → batch-embed → store in memory.
    Returns the populated store.

    This is O(n) in document length and runs once. For large corpora (>10k chunks),
    you would add: progress bars, error recovery, parallel embedding, and
    a persistent store (pgvector, Qdrant) instead of this in-memory dict.
    """
    store = make_store()

    with open(filepath, "r", encoding="utf-8") as f:
        raw_text = f.read()

    print(f"Loaded {len(raw_text):,} characters from '{filepath}'")

    chunks = chunk_text(raw_text, chunk_size=chunk_size, overlap=overlap)
    print(f"Split into {len(chunks)} chunks "
          f"(size={chunk_size} words, overlap={overlap} words)")

    print(f"Embedding {len(chunks)} chunks via {EMBED_MODEL}...")
    vectors = embed(chunks)

    for chunk, vector in zip(chunks, vectors):
        add_to_store(store, chunk, vector, metadata={"source": filepath})

    print(f"Stored {len(store)} chunks. Ingest complete.\n")
    return store

# ---------------------------------------------------------------------------
# Step 2: Retrieve - embed query + cosine search
# ---------------------------------------------------------------------------

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two vectors. Returns value in [-1.0, 1.0].
    For normalized embedding vectors, range is effectively [0.0, 1.0].
    """
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def retrieve(query: str, store: dict, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """
    Embed the query and return the top_k most similar chunks.

    This is a linear scan: O(n) over every stored chunk.
    Fine for up to ~50k chunks. Beyond that, use approximate nearest neighbor
    indexing (HNSW via Qdrant, pgvector, or FAISS) - same cosine math,
    just with an index that avoids the full scan.

    Returns list of dicts sorted by score descending:
      [{"id": str, "text": str, "score": float, "metadata": dict}, ...]
    """
    if not store:
        print("Warning: store is empty. Did ingest() run successfully?")
        return []

    query_vector = np.array(embed([query])[0], dtype=np.float32)

    scored = []
    for chunk_id, entry in store.items():
        score = cosine_similarity(query_vector, entry["vector"])
        scored.append({
            "id": chunk_id,
            "text": entry["text"],
            "score": score,
            "metadata": entry["metadata"],
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]

# ---------------------------------------------------------------------------
# Step 3: Augment - format retrieved chunks into a prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a precise, helpful assistant. Answer the user's question using ONLY the context provided below.
If the context does not contain enough information to answer the question, say: "I don't have enough context to answer this."
Do not invent facts. Do not use prior knowledge not present in the context."""


def build_prompt(query: str, retrieved_chunks: list[dict]) -> str:
    """
    Format retrieved chunks and the user query into a prompt string.

    Design choices that affect answer quality:
    - Label each source so the model can cite it
    - Separate chunks with a visible delimiter so the model treats them as distinct
    - Put the question AFTER the context (reduces hallucination vs question-first)
    - System prompt tells model to refuse if context is insufficient
    """
    context_parts = []
    for i, chunk in enumerate(retrieved_chunks, 1):
        source = chunk["metadata"].get("source", "unknown")
        score = chunk["score"]
        context_parts.append(
            f"[Context {i} | source: {source} | relevance: {score:.3f}]\n{chunk['text']}"
        )

    context_block = "\n\n---\n\n".join(context_parts)

    return f"""Context:

{context_block}

---

Question: {query}

Answer (based strictly on the context above):"""

# ---------------------------------------------------------------------------
# Step 4: Generate - LLM call → answer + sources
# ---------------------------------------------------------------------------

def generate(query: str, retrieved_chunks: list[dict]) -> dict:
    """
    Build the augmented prompt and call the LLM.

    Returns:
      {
        "answer": str,
        "sources": list[str],
        "retrieved_chunks": list[dict],   # for debugging
        "usage": {"prompt_tokens": int, "completion_tokens": int}
      }

    temperature=0.0 makes output deterministic - essential for reproducible evals.
    If you run the same query twice and get different answers, you cannot tell
    whether a code change helped or hurt.
    """
    prompt = build_prompt(query, retrieved_chunks)

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )

    answer = response.choices[0].message.content.strip()
    sources = list({c["metadata"].get("source", "unknown") for c in retrieved_chunks})

    return {
        "answer": answer,
        "sources": sources,
        "retrieved_chunks": retrieved_chunks,
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        },
    }

# ---------------------------------------------------------------------------
# Full pipeline: retrieve + augment + generate
# ---------------------------------------------------------------------------

def ask(query: str, store: dict, top_k: int = DEFAULT_TOP_K, verbose: bool = True) -> dict:
    """
    One call through the full RAG pipeline.
    Returns the generate() result dict.

    Debugging workflow:
      1. Log retrieved_chunks - if the right passage isn't here, fix retrieval
      2. If the right passage IS here but the answer is wrong, fix the prompt/model
      Never confuse these two failure modes.
    """
    if verbose:
        print(f"\nQuery: {query}")

    chunks = retrieve(query, store, top_k=top_k)

    if verbose and chunks:
        print(f"Retrieved {len(chunks)} chunks | "
              f"top score: {chunks[0]['score']:.3f} | "
              f"bottom score: {chunks[-1]['score']:.3f}")

    result = generate(query, chunks)

    if verbose:
        print(f"Answer ({result['usage']['completion_tokens']} tokens): "
              f"{result['answer'][:120]}{'...' if len(result['answer']) > 120 else ''}")

    return result

# ---------------------------------------------------------------------------
# Minimal eval harness
# ---------------------------------------------------------------------------

def run_eval(store: dict, eval_pairs: list[dict], top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """
    Run a list of {"question": ..., "expected": ...} pairs through the pipeline.
    Print results for manual review. Returns results list.

    This is your baseline eval:
      1. Write these pairs BEFORE tuning anything
      2. Score each answer: correct / partial / wrong
      3. Record the score as your v0 baseline
      4. Every change you make must beat this baseline

    Ten pairs is enough to catch systematic failures.
    Twenty pairs gives you statistical confidence in comparisons.
    """
    print("\n" + "=" * 60)
    print(f"EVAL RUN  ({len(eval_pairs)} questions, top_k={top_k})")
    print("=" * 60)

    results = []
    for i, pair in enumerate(eval_pairs, 1):
        print(f"\n[Q{i}] {pair['question']}")
        result = ask(pair["question"], store, top_k=top_k, verbose=False)

        print(f"  Expected : {pair['expected'][:150]}")
        print(f"  Got      : {result['answer'][:150]}")
        print(f"  Tokens   : {result['usage']['prompt_tokens']} prompt / "
              f"{result['usage']['completion_tokens']} completion")
        print(f"  Top chunk: {result['retrieved_chunks'][0]['text'][:100]}..." if result['retrieved_chunks'] else "  No chunks retrieved")

        results.append({**pair, "result": result})

    print("\n" + "=" * 60)
    print("Score each answer manually: correct / partial / wrong")
    print("This is your v0 baseline. Record it before changing anything.")
    print("=" * 60)
    return results

# ---------------------------------------------------------------------------
# Diagnostic helpers
# ---------------------------------------------------------------------------

def debug_retrieval(query: str, store: dict, top_k: int = 10) -> None:
    """
    Show top-K retrieved chunks with scores. Use this to diagnose
    retrieval failures before touching the prompt or the LLM.

    If the relevant passage is not in this list: fix chunking or embedding.
    If it IS in this list but the answer is wrong: fix the prompt/model.
    """
    print(f"\n--- RETRIEVAL DEBUG: '{query}' ---")
    chunks = retrieve(query, store, top_k=top_k)
    for i, chunk in enumerate(chunks, 1):
        print(f"\n[{i}] score={chunk['score']:.4f} | id={chunk['id']}")
        print(f"     {chunk['text'][:200]}...")


def show_store_stats(store: dict) -> None:
    """Print basic statistics about the current store."""
    if not store:
        print("Store is empty.")
        return
    texts = [v["text"] for v in store.values()]
    word_counts = [len(t.split()) for t in texts]
    print(f"\n--- STORE STATS ---")
    print(f"  Chunks: {len(store)}")
    print(f"  Avg words/chunk: {sum(word_counts) / len(word_counts):.0f}")
    print(f"  Min words/chunk: {min(word_counts)}")
    print(f"  Max words/chunk: {max(word_counts)}")
    total_words = sum(word_counts)
    print(f"  Total words: {total_words:,}")
    # Rough token estimate (1 word ≈ 1.3 tokens)
    print(f"  Estimated tokens (ingest): ~{int(total_words * 1.3):,}")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python main.py <path-to-text-file>")
        print("  python main.py <path-to-text-file> 'Your question here'")
        print("  python main.py <path-to-text-file> --debug 'Your question here'")
        print("\nExample:")
        print("  python main.py my_document.txt 'What are the main conclusions?'")
        sys.exit(1)

    filepath = sys.argv[1]

    # Build the store from the provided file
    store = ingest(filepath)
    show_store_stats(store)

    if len(sys.argv) >= 3 and sys.argv[2] == "--debug":
        # Debug mode: show retrieval results without generating an answer
        query = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "What is this document about?"
        debug_retrieval(query, store, top_k=10)

    elif len(sys.argv) >= 3:
        # Single query mode
        query = " ".join(sys.argv[2:])
        result = ask(query, store)
        print("\n" + "=" * 60)
        print("ANSWER")
        print("=" * 60)
        print(result["answer"])
        print(f"\nSources: {result['sources']}")
        print(f"Token cost: {result['usage']['prompt_tokens']} prompt + "
              f"{result['usage']['completion_tokens']} completion")

    else:
        # Demo mode: 3 generic questions
        demo_questions = [
            {"question": "What is the main topic or purpose of this document?",
             "expected": "(review manually)"},
            {"question": "What are the key conclusions, findings, or recommendations?",
             "expected": "(review manually)"},
            {"question": "What specific evidence, examples, or data are provided?",
             "expected": "(review manually)"},
        ]
        results = run_eval(store, demo_questions)

        print("\nTo ask a specific question:")
        print(f"  python main.py {filepath} 'Your question here'")
        print("\nTo debug retrieval for a query:")
        print(f"  python main.py {filepath} --debug 'Your question here'")
