"""
Capstone 12-01: Production RAG Assistant Over a Real Corpus
Phase 12: Capstones

A FastAPI service that indexes the curriculum's own documentation and answers
questions with hybrid BM25 + dense retrieval, streaming SSE responses,
citation grounding, and an off-topic guardrail.

Usage:
    # Install dependencies
    uv pip install -r requirements.txt

    # Set API key
    export ANTHROPIC_API_KEY=sk-...

    # Run the service (indexes corpus at startup)
    uvicorn main:app --reload

    # Query the service
    curl -X POST http://localhost:8000/query \
         -H "Content-Type: application/json" \
         -d '{"question": "What phases cover evaluation?"}' \
         --no-buffer
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Iterator

import anthropic
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rank_bm25 import BM25Okapi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHUNK_SIZE = 512         # characters per chunk
CHUNK_OVERLAP = 64       # character overlap between chunks
TOP_K_DEFAULT = 5
RRF_K = 60               # RRF smoothing constant
MODEL = "claude-3-5-haiku-20241022"
MAX_TOKENS = 1024

# Resolve corpus root relative to this file or via env var
CORPUS_ROOT = os.environ.get(
    "CORPUS_ROOT",
    str(Path(__file__).resolve().parents[4])  # repo root
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rag-assistant")

# ---------------------------------------------------------------------------
# Corpus ingestion
# ---------------------------------------------------------------------------

def iter_corpus_files(root: str) -> Iterator[tuple[str, str]]:
    """Yield (filepath, content) for every .md file under root."""
    for path in Path(root).rglob("*.md"):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            if content.strip():
                yield str(path), content
        except Exception as exc:
            log.warning("Skipping %s: %s", path, exc)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping character chunks."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start += size - overlap
    return chunks


def build_corpus(root: str) -> list[dict]:
    """Return list of {id, text, source} dicts."""
    docs: list[dict] = []
    file_count = 0
    for filepath, content in iter_corpus_files(root):
        file_count += 1
        for i, chunk in enumerate(chunk_text(content)):
            docs.append({
                "id": f"{filepath}::{i}",
                "text": chunk,
                "source": os.path.relpath(filepath, root),
            })
    log.info("Ingested %d files -> %d chunks", file_count, len(docs))
    return docs


# ---------------------------------------------------------------------------
# BM25 + demo dense indexing
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def build_bm25_index(docs: list[dict]) -> BM25Okapi:
    corpus = [tokenize(d["text"]) for d in docs]
    return BM25Okapi(corpus)


def embed_text(text: str, vocab_size: int = 512) -> np.ndarray:
    """
    Demo embedding: bag-of-chars frequency vector, L2-normalized.
    Replace with a real embedding API (Voyage, OpenAI, etc.) for production.
    """
    vec = np.zeros(vocab_size, dtype=np.float32)
    for ch in text:
        vec[ord(ch) % vocab_size] += 1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def build_dense_matrix(docs: list[dict]) -> np.ndarray:
    """Return embedding matrix of shape (n_docs, vocab_size)."""
    return np.stack([embed_text(d["text"]) for d in docs])


# ---------------------------------------------------------------------------
# Hybrid retrieval with RRF
# ---------------------------------------------------------------------------

def hybrid_search(
    query: str,
    docs: list[dict],
    bm25: BM25Okapi,
    dense_matrix: np.ndarray,
    top_k: int = TOP_K_DEFAULT,
    rrf_k: int = RRF_K,
) -> list[dict]:
    """Retrieve top_k docs using BM25 + dense cosine + Reciprocal Rank Fusion."""
    tokens = tokenize(query)
    bm25_scores = bm25.get_scores(tokens)
    bm25_ranks = np.argsort(-bm25_scores)

    q_vec = embed_text(query)
    cosine_scores = dense_matrix @ q_vec
    dense_ranks = np.argsort(-cosine_scores)

    rrf_scores: dict[int, float] = {}
    for rank, idx in enumerate(bm25_ranks):
        rrf_scores[int(idx)] = rrf_scores.get(int(idx), 0.0) + 1.0 / (rrf_k + rank + 1)
    for rank, idx in enumerate(dense_ranks):
        rrf_scores[int(idx)] = rrf_scores.get(int(idx), 0.0) + 1.0 / (rrf_k + rank + 1)

    top_indices = sorted(rrf_scores, key=rrf_scores.__getitem__, reverse=True)[:top_k]
    return [docs[i] for i in top_indices]


# ---------------------------------------------------------------------------
# Off-topic guardrail
# ---------------------------------------------------------------------------

CURRICULUM_KEYWORDS = {
    "rag", "agent", "llm", "prompt", "embedding", "vector", "retrieval",
    "evaluation", "fine-tuning", "observability", "tool", "mcp", "guardrail",
    "fastapi", "anthropic", "claude", "lesson", "phase", "capstone",
    "python", "typescript", "shipping", "multimodal", "security", "fde",
    "chunk", "index", "stream", "inference", "model", "context", "token",
}

CURRICULUM_VEC = embed_text("applied AI engineering curriculum lessons phases Python")


def is_on_topic(query: str) -> bool:
    """Return True if the query is within curriculum scope."""
    words = set(tokenize(query))
    if words & CURRICULUM_KEYWORDS:
        return True
    q_vec = embed_text(query)
    similarity = float(np.dot(q_vec, CURRICULUM_VEC))
    return similarity > 0.85


# ---------------------------------------------------------------------------
# System prompt with citation instructions
# ---------------------------------------------------------------------------

def build_system_prompt(contexts: list[dict]) -> str:
    ctx_parts = []
    for i, c in enumerate(contexts):
        ctx_parts.append(f"[SOURCE {i + 1}] {c['source']}\n{c['text']}")
    ctx_text = "\n\n---\n\n".join(ctx_parts)
    return (
        "You are a teaching assistant for the appliedaifromscratch.com curriculum. "
        "Answer questions using only the provided sources. "
        "After each factual claim, cite the source number in square brackets, e.g. [1]. "
        "Only cite a source if that source directly contains evidence for the specific claim. "
        "If the sources do not contain enough information to answer, say: "
        "'I do not have enough information in the provided sources to answer this.' "
        "Do not answer questions unrelated to AI engineering or this curriculum.\n\n"
        f"SOURCES:\n\n{ctx_text}"
    )


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="RAG Assistant", version="1.0")
anthropic_client = anthropic.Anthropic()

# Module-level index (populated at startup)
DOCS: list[dict] = []
BM25_INDEX: BM25Okapi | None = None
DENSE_MATRIX: np.ndarray | None = None


@app.on_event("startup")
def startup_index():
    global DOCS, BM25_INDEX, DENSE_MATRIX
    log.info("Building corpus index from: %s", CORPUS_ROOT)
    t0 = time.time()
    DOCS = build_corpus(CORPUS_ROOT)
    if not DOCS:
        log.warning("No documents found under %s", CORPUS_ROOT)
        return
    BM25_INDEX = build_bm25_index(DOCS)
    DENSE_MATRIX = build_dense_matrix(DOCS)
    log.info("Index ready: %d chunks in %.1fs", len(DOCS), time.time() - t0)


class QueryRequest(BaseModel):
    question: str
    top_k: int = TOP_K_DEFAULT


@app.post("/query")
async def query_endpoint(req: QueryRequest):
    """Stream a RAG response with citation grounding."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    if not is_on_topic(req.question):
        raise HTTPException(
            status_code=400,
            detail="Query is outside curriculum scope. Ask about AI engineering topics.",
        )

    if BM25_INDEX is None or DENSE_MATRIX is None:
        raise HTTPException(status_code=503, detail="Index not ready.")

    contexts = hybrid_search(req.question, DOCS, BM25_INDEX, DENSE_MATRIX, top_k=req.top_k)
    system = build_system_prompt(contexts)

    def event_stream():
        # First event: citations metadata
        citations = [{"index": i + 1, "source": c["source"]} for i, c in enumerate(contexts)]
        yield f"data: {json.dumps({'type': 'citations', 'data': citations})}\n\n"

        # Stream the model response
        t_start = time.time()
        input_tokens = 0
        output_tokens = 0

        with anthropic_client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": req.question}],
        ) as stream:
            for text_chunk in stream.text_stream:
                yield f"data: {json.dumps({'type': 'chunk', 'text': text_chunk})}\n\n"
            final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens

        latency_ms = int((time.time() - t_start) * 1000)
        log.info(
            "query=%r latency_ms=%d input_tokens=%d output_tokens=%d",
            req.question[:60], latency_ms, input_tokens, output_tokens,
        )
        yield f"data: {json.dumps({'type': 'done', 'latency_ms': latency_ms, 'input_tokens': input_tokens, 'output_tokens': output_tokens})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "docs_indexed": len(DOCS),
        "index_ready": BM25_INDEX is not None,
    }


@app.post("/reindex")
def reindex():
    """Re-ingest corpus. Call after updating documentation."""
    startup_index()
    return {"docs_indexed": len(DOCS)}


# ---------------------------------------------------------------------------
# CLI demo (without FastAPI)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("Building corpus index...")
    docs = build_corpus(CORPUS_ROOT)
    if not docs:
        print(f"ERROR: No .md files found under {CORPUS_ROOT}")
        sys.exit(1)

    bm25 = build_bm25_index(docs)
    dense = build_dense_matrix(docs)
    print(f"Indexed {len(docs)} chunks from {CORPUS_ROOT}\n")

    demo_queries = [
        "What phases cover evaluation and how do they differ?",
        "Which lesson teaches BM25 retrieval?",
        "What tools does Phase 03 cover?",
        # Off-topic query (should be rejected)
        "How do I bake a sourdough loaf?",
    ]

    for q in demo_queries:
        print(f"Query: {q}")
        if not is_on_topic(q):
            print("REJECTED: off-topic query\n")
            continue

        contexts = hybrid_search(q, docs, bm25, dense, top_k=3)
        system = build_system_prompt(contexts)

        print(f"Retrieved {len(contexts)} chunks:")
        for i, c in enumerate(contexts):
            print(f"  [{i+1}] {c['source']}")

        response = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": q}],
        )
        answer = next(
            (b.text for b in response.content if hasattr(b, "text")), "(no answer)"
        )
        print(f"Answer: {answer[:300]}")
        print(f"Tokens: in={response.usage.input_tokens} out={response.usage.output_tokens}\n")
