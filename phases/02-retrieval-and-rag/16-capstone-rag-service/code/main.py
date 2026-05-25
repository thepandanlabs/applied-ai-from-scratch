# pip install fastapi uvicorn openai sentence-transformers pydantic numpy
# Optional: pip install qdrant-client  (for production vector store)
# Set environment variable: OPENAI_API_KEY=sk-...
#
# Run with:
#   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
#
# Or standalone (runs demo mode, no server):
#   python main.py

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

import numpy as np
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Config from environment variables
# ---------------------------------------------------------------------------

class Config:
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    EMBED_MODEL: str = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
    CHAT_MODEL: str = os.environ.get("CHAT_MODEL", "gpt-4o-mini")
    LOCAL_EMBED_MODEL: str = os.environ.get("LOCAL_EMBED_MODEL", "all-MiniLM-L6-v2")
    TOP_K: int = int(os.environ.get("TOP_K", "5"))
    CHUNK_SIZE: int = int(os.environ.get("CHUNK_SIZE", "400"))
    CHUNK_OVERLAP: int = int(os.environ.get("CHUNK_OVERLAP", "50"))
    MAX_RETRIES: int = int(os.environ.get("MAX_RETRIES", "3"))
    # Set USE_LOCAL_EMBEDDINGS=true to use sentence-transformers instead of OpenAI
    USE_LOCAL_EMBEDDINGS: bool = os.environ.get("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    PORT: int = int(os.environ.get("PORT", "8000"))


cfg = Config()


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
    format="%(message)s",
)
logger = logging.getLogger("rag_service")


def log_event(event: str, data: dict[str, Any]) -> None:
    """Emit a structured JSON log line to stdout."""
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        **data,
    }
    logger.info(json.dumps(entry, default=str))


# ---------------------------------------------------------------------------
# In-memory vector store
# ---------------------------------------------------------------------------

class InMemoryVectorStore:
    """
    Numpy-backed in-memory vector store.

    For production:
    - Replace with Qdrant (pip install qdrant-client)
    - Or pgvector (pip install psycopg2 pgvector)
    The interface (add, search, count) stays the same.
    """

    def __init__(self) -> None:
        self.chunks: list[dict] = []
        self.vectors: Optional[np.ndarray] = None
        self.doc_hashes: set[str] = set()

    def add(
        self,
        text: str,
        vector: np.ndarray,
        metadata: dict,
    ) -> str:
        chunk_id = str(uuid.uuid4())[:12]
        self.chunks.append({"id": chunk_id, "text": text, "metadata": metadata})
        vec = vector.reshape(1, -1).astype(np.float32)
        self.vectors = vec if self.vectors is None else np.vstack([self.vectors, vec])
        return chunk_id

    def search(self, query_vec: np.ndarray, top_k: int) -> list[dict]:
        if self.vectors is None or len(self.chunks) == 0:
            return []
        q = query_vec.astype(np.float32)
        norms = np.linalg.norm(self.vectors, axis=1) * np.linalg.norm(q)
        norms = np.where(norms == 0, 1e-10, norms)
        scores = self.vectors @ q / norms
        k = min(top_k, len(self.chunks))
        top_idx = np.argsort(scores)[::-1][:k]
        return [{**self.chunks[i], "score": float(scores[i])} for i in top_idx]

    def count(self) -> int:
        return len(self.chunks)

    def is_doc_known(self, doc_hash: str) -> bool:
        return doc_hash in self.doc_hashes

    def register_doc(self, doc_hash: str) -> None:
        self.doc_hashes.add(doc_hash)

    def remove_doc(self, doc_id: str) -> int:
        """Remove all chunks for a given doc_id. Returns chunks removed."""
        keep_mask = [c["metadata"].get("doc_id") != doc_id for c in self.chunks]
        removed = len(self.chunks) - sum(keep_mask)
        if removed == 0:
            return 0
        keep_idx = [i for i, keep in enumerate(keep_mask) if keep]
        self.chunks = [self.chunks[i] for i in keep_idx]
        self.vectors = self.vectors[keep_idx] if keep_idx else None
        return removed


# Singleton store — shared by all endpoints
vector_store = InMemoryVectorStore()

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

_oai_client = None
_local_embed_model = None


def get_oai_client():
    global _oai_client
    if _oai_client is None and cfg.OPENAI_API_KEY:
        from openai import OpenAI
        _oai_client = OpenAI(api_key=cfg.OPENAI_API_KEY)
    return _oai_client


def get_local_model():
    global _local_embed_model
    if _local_embed_model is None:
        from sentence_transformers import SentenceTransformer
        _local_embed_model = SentenceTransformer(cfg.LOCAL_EMBED_MODEL)
    return _local_embed_model


def with_retry(fn, max_retries: int = 3, request_id: str = ""):
    """
    Retry fn() with exponential backoff + jitter on rate limit errors.
    Raises after max_retries failed attempts.
    """
    from openai import RateLimitError, APIError

    for attempt in range(max_retries + 1):
        try:
            return fn()
        except RateLimitError as e:
            if attempt == max_retries:
                raise
            wait = (2 ** attempt) + random.uniform(0, 0.5)
            log_event("rate_limit_backoff", {
                "request_id": request_id,
                "attempt": attempt + 1,
                "wait_s": round(wait, 2),
            })
            time.sleep(wait)
        except APIError as e:
            if attempt == max_retries or getattr(e, "status_code", 0) not in (429, 500, 503):
                raise
            wait = (2 ** attempt) + random.uniform(0, 0.5)
            time.sleep(wait)


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Embed texts using OpenAI (default) or sentence-transformers (local).
    Set USE_LOCAL_EMBEDDINGS=true to run without an API key.
    """
    if cfg.USE_LOCAL_EMBEDDINGS or not cfg.OPENAI_API_KEY:
        model = get_local_model()
        return model.encode(texts, show_progress_bar=False).astype(np.float32)

    client = get_oai_client()

    def call():
        resp = client.embeddings.create(model=cfg.EMBED_MODEL, input=texts)
        return np.array([item.embedding for item in resp.data], dtype=np.float32)

    return with_retry(call, max_retries=cfg.MAX_RETRIES)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Word-based sliding window chunking."""
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap
    return chunks


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_document(
    content: str,
    doc_id: str,
    metadata: dict,
    chunk_size: int,
    overlap: int,
) -> dict:
    """
    Idempotent ingestion: hash document content before processing.
    Identical documents are skipped on subsequent calls.
    Returns: {doc_id, chunks_added, was_duplicate, doc_hash}
    """
    doc_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    if vector_store.is_doc_known(doc_hash):
        return {
            "doc_id": doc_id,
            "chunks_added": 0,
            "was_duplicate": True,
            "doc_hash": doc_hash,
        }

    chunks = chunk_text(content, chunk_size, overlap)
    vectors = embed_texts(chunks)

    chunk_meta = {**metadata, "doc_id": doc_id, "doc_hash": doc_hash}
    for chunk, vec in zip(chunks, vectors):
        vector_store.add(chunk, vec, chunk_meta)

    vector_store.register_doc(doc_hash)

    return {
        "doc_id": doc_id,
        "chunks_added": len(chunks),
        "was_duplicate": False,
        "doc_hash": doc_hash,
    }


# ---------------------------------------------------------------------------
# Query pipeline
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer the user's question using ONLY "
    "the provided context. If the context does not contain enough information, "
    "say so explicitly. Cite sources using [Source N] notation."
)

RAG_TRIAD_PROMPT = """You are evaluating a RAG system's answer quality. Score the following
on three dimensions, each from 0.0 to 1.0:

FAITHFULNESS: Is every claim in the answer supported by the context? (1.0 = fully supported)
ANSWER_RELEVANCE: Does the answer directly address the question? (1.0 = fully answers it)
CONTEXT_RELEVANCE: How relevant is the retrieved context to the question? (1.0 = directly contains the answer)

Return ONLY valid JSON with keys: faithfulness, answer_relevance, context_relevance.

Question: {question}

Retrieved context:
{context}

Answer:
{answer}

JSON:"""


def run_query(query: str, top_k: int, request_id: str = "") -> dict:
    """
    Full RAG pipeline with latency instrumentation.
    Returns: {answer, sources, retrieved_chunks, latency_breakdown, tokens}
    """
    timings: dict[str, int] = {}

    # Step 1: Embed query
    t0 = time.time()
    query_vec = embed_texts([query])[0]
    timings["embed_ms"] = int((time.time() - t0) * 1000)

    # Step 2: Retrieve
    t0 = time.time()
    results = vector_store.search(query_vec, top_k=top_k)
    timings["retrieve_ms"] = int((time.time() - t0) * 1000)

    if not results:
        timings["generate_ms"] = 0
        timings["total_ms"] = sum(timings.values())
        return {
            "answer": "No relevant documents found in the index.",
            "sources": [],
            "retrieved_chunks": [],
            "latency_breakdown": timings,
            "tokens": {},
        }

    # Step 3: Format context
    context_parts = []
    for i, r in enumerate(results, 1):
        src = r["metadata"].get("doc_id", "unknown")
        context_parts.append(f"[Source {i}: {src}]\n{r['text']}")
    context = "\n\n---\n\n".join(context_parts)

    # Step 4: Generate
    t0 = time.time()
    client = get_oai_client()
    answer = "[LLM not configured — set OPENAI_API_KEY or USE_LOCAL_EMBEDDINGS=true]"
    token_info: dict = {}

    if client:
        prompt = f"Context:\n{context}\n\n---\n\nQuestion: {query}\n\nAnswer:"

        def call_llm():
            return client.chat.completions.create(
                model=cfg.CHAT_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )

        resp = with_retry(call_llm, max_retries=cfg.MAX_RETRIES, request_id=request_id)
        answer = resp.choices[0].message.content.strip()
        token_info = {
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
        }

    timings["generate_ms"] = int((time.time() - t0) * 1000)
    timings["total_ms"] = sum(timings.values())

    sources = list({r["metadata"].get("doc_id", "unknown") for r in results})

    return {
        "answer": answer,
        "sources": sources,
        "retrieved_chunks": [
            {
                "text": r["text"][:200],
                "score": round(r["score"], 4),
                "source": r["metadata"].get("doc_id"),
            }
            for r in results
        ],
        "latency_breakdown": timings,
        "tokens": token_info,
    }


def run_rag_triad(question: str, context: str, answer: str) -> dict:
    """
    Score answer quality using the RAG Triad:
    faithfulness, answer_relevance, context_relevance.
    Each score is 0.0–1.0.
    """
    client = get_oai_client()
    if not client:
        return {
            "faithfulness": 0.0,
            "answer_relevance": 0.0,
            "context_relevance": 0.0,
            "error": "LLM not configured",
        }

    prompt = RAG_TRIAD_PROMPT.format(
        question=question,
        context=context[:2000],
        answer=answer,
    )

    def call():
        return client.chat.completions.create(
            model=cfg.CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )

    resp = with_retry(call, max_retries=2)
    raw = resp.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if "```" in raw:
        raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        scores = json.loads(raw)
        return {
            "faithfulness": float(scores.get("faithfulness", 0.0)),
            "answer_relevance": float(scores.get("answer_relevance", 0.0)),
            "context_relevance": float(scores.get("context_relevance", 0.0)),
        }
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        return {
            "faithfulness": 0.0,
            "answer_relevance": 0.0,
            "context_relevance": 0.0,
            "parse_error": str(e),
            "raw_response": raw[:200],
        }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


# Pydantic models

class IngestRequest(BaseModel):
    content: str = Field(..., description="Document text to ingest")
    doc_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="Unique document identifier",
    )
    metadata: dict = Field(default_factory=dict)
    chunk_size: Optional[int] = Field(default=None)
    chunk_overlap: Optional[int] = Field(default=None)


class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    top_k: Optional[int] = Field(default=None)


class EvalRequest(BaseModel):
    question: str = Field(..., description="Question to evaluate the RAG system on")
    expected_answer: Optional[str] = Field(default=None)
    context: Optional[str] = Field(default=None, description="Override retrieved context")


if FASTAPI_AVAILABLE:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log_event("service_start", {
            "chat_model": cfg.CHAT_MODEL,
            "embed_model": cfg.EMBED_MODEL if not cfg.USE_LOCAL_EMBEDDINGS else cfg.LOCAL_EMBED_MODEL,
            "use_local_embeddings": cfg.USE_LOCAL_EMBEDDINGS,
            "top_k": cfg.TOP_K,
        })
        yield
        log_event("service_stop", {"total_chunks": vector_store.count()})

    app = FastAPI(
        title="RAG Service",
        description="Production RAG API — Applied AI From Scratch, Phase 02 Capstone",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Request ID middleware
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = str(uuid.uuid4())[:12]
        request.state.request_id = request_id
        t0 = time.time()
        response = await call_next(request)
        total_ms = int((time.time() - t0) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(total_ms)
        return response

    # ----------------------------------------------------------------
    # GET /health
    # ----------------------------------------------------------------

    @app.get("/health")
    async def health(request: Request) -> JSONResponse:
        """
        Deep health check — not just 'process alive' but 'system functional'.
        Returns 200 if healthy, 207 if degraded, 503 if unhealthy.
        """
        checks: dict[str, Any] = {}
        status = "healthy"

        # Vector store
        try:
            count = vector_store.count()
            checks["vector_store"] = {"status": "ok", "chunk_count": count}
            if count == 0:
                checks["vector_store"]["warning"] = "Index is empty — ingest documents first"
                status = "degraded"
        except Exception as e:
            checks["vector_store"] = {"status": "error", "detail": str(e)}
            status = "unhealthy"

        # LLM
        if cfg.OPENAI_API_KEY:
            checks["llm"] = {"status": "configured", "model": cfg.CHAT_MODEL}
        else:
            checks["llm"] = {"status": "not_configured", "note": "Set OPENAI_API_KEY or USE_LOCAL_EMBEDDINGS=true"}
            if status == "healthy":
                status = "degraded"

        # Embeddings
        checks["embeddings"] = {
            "status": "ok",
            "mode": "local" if cfg.USE_LOCAL_EMBEDDINGS else "openai",
            "model": cfg.LOCAL_EMBED_MODEL if cfg.USE_LOCAL_EMBEDDINGS else cfg.EMBED_MODEL,
        }

        http_status = {"healthy": 200, "degraded": 207, "unhealthy": 503}.get(status, 200)

        return JSONResponse(
            status_code=http_status,
            content={
                "status": status,
                "request_id": request.state.request_id,
                "checks": checks,
            },
        )

    # ----------------------------------------------------------------
    # POST /ingest
    # ----------------------------------------------------------------

    @app.post("/ingest")
    async def ingest(req: IngestRequest, request: Request) -> dict:
        """
        Ingest a document. Idempotent: duplicate content hashes are skipped.
        """
        request_id = request.state.request_id

        try:
            t0 = time.time()
            result = ingest_document(
                content=req.content,
                doc_id=req.doc_id,
                metadata=req.metadata,
                chunk_size=req.chunk_size or cfg.CHUNK_SIZE,
                overlap=req.chunk_overlap or cfg.CHUNK_OVERLAP,
            )
            elapsed = int((time.time() - t0) * 1000)

            log_event("ingest", {
                "request_id": request_id,
                "doc_id": req.doc_id,
                "chunks_added": result["chunks_added"],
                "was_duplicate": result["was_duplicate"],
                "latency_ms": elapsed,
                "total_chunks_in_index": vector_store.count(),
            })

            return {**result, "request_id": request_id}

        except Exception as e:
            log_event("ingest_error", {"request_id": request_id, "error": str(e)})
            raise HTTPException(
                status_code=500,
                detail={"error": str(e), "request_id": request_id},
            )

    # ----------------------------------------------------------------
    # POST /query
    # ----------------------------------------------------------------

    @app.post("/query")
    async def query(req: QueryRequest, request: Request) -> dict:
        """
        Query the RAG index. Returns answer, sources, retrieved chunks, latency breakdown.
        """
        request_id = request.state.request_id

        if not req.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        if vector_store.count() == 0:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Index is empty. POST to /ingest first.",
                    "request_id": request_id,
                },
            )

        try:
            result = run_query(
                query=req.query,
                top_k=req.top_k or cfg.TOP_K,
                request_id=request_id,
            )

            log_event("query", {
                "request_id": request_id,
                "query": req.query[:100],
                "retrieved_chunks": len(result["retrieved_chunks"]),
                "top_chunk_score": (
                    result["retrieved_chunks"][0]["score"]
                    if result["retrieved_chunks"] else 0
                ),
                "latency_breakdown": result["latency_breakdown"],
                "tokens": result["tokens"],
                "answer_length": len(result["answer"]),
                "model": cfg.CHAT_MODEL,
            })

            return {**result, "request_id": request_id}

        except Exception as e:
            # Import here to handle case where openai is not installed
            try:
                from openai import RateLimitError
                if isinstance(e, RateLimitError):
                    log_event("rate_limit_final", {"request_id": request_id})
                    raise HTTPException(
                        status_code=429,
                        detail={"error": "Rate limit exceeded after retries", "request_id": request_id},
                    )
            except ImportError:
                pass

            log_event("query_error", {"request_id": request_id, "error": str(e)})
            raise HTTPException(
                status_code=500,
                detail={"error": str(e), "request_id": request_id},
            )

    # ----------------------------------------------------------------
    # POST /eval
    # ----------------------------------------------------------------

    @app.post("/eval")
    async def eval_endpoint(req: EvalRequest, request: Request) -> dict:
        """
        Run RAG Triad evaluation: query → answer → score faithfulness/relevance.
        Returns scores plus the answer generated.
        """
        request_id = request.state.request_id

        if vector_store.count() == 0:
            raise HTTPException(
                status_code=503,
                detail={"error": "Index is empty. Ingest documents first.", "request_id": request_id},
            )

        try:
            # Get answer from the pipeline
            result = run_query(req.question, top_k=cfg.TOP_K, request_id=request_id)
            answer = result["answer"]

            # Build context for scoring
            context = req.context if req.context else "\n\n".join(
                c["text"] for c in result["retrieved_chunks"]
            )

            # Score
            scores = run_rag_triad(req.question, context, answer)

            log_event("eval", {
                "request_id": request_id,
                "question": req.question[:100],
                "scores": scores,
                "latency_ms": result["latency_breakdown"]["total_ms"],
            })

            output = {
                "question": req.question,
                "answer": answer,
                "scores": scores,
                "retrieved_chunks": result["retrieved_chunks"],
                "request_id": request_id,
            }

            if req.expected_answer:
                output["expected_answer"] = req.expected_answer

            return output

        except Exception as e:
            log_event("eval_error", {"request_id": request_id, "error": str(e)})
            raise HTTPException(
                status_code=500,
                detail={"error": str(e), "request_id": request_id},
            )


# ---------------------------------------------------------------------------
# Standalone demo (no web server)
# ---------------------------------------------------------------------------

DEMO_CORPUS = [
    "RAG (Retrieval Augmented Generation) is a technique that combines vector search with LLM generation to ground answers in a document corpus.",
    "Chunking strategy is the most impactful decision in a RAG pipeline. Too small: context is lost. Too large: retrieval is diluted.",
    "Hybrid search combines dense (embedding) retrieval with sparse (BM25/keyword) retrieval. It consistently outperforms either approach alone.",
    "The RAG Triad evaluates three dimensions: faithfulness (answer grounded in context?), answer relevance (answers the question?), and context relevance (right chunks retrieved?).",
    "Idempotent ingestion uses content hashing to detect duplicate documents. Re-ingesting the same document produces no change — no error, no duplicate chunks.",
    "Exponential backoff with jitter handles rate limiting: wait 1s, 2s, 4s with small random offsets to desynchronize retries from concurrent clients.",
    "Health checks should verify all dependencies: vector store reachable, LLM API configured, index non-empty. A process that is alive but has an empty index is not healthy.",
    "Structured JSON logging captures: request_id, query, latency_breakdown (embed_ms + retrieve_ms + generate_ms), tokens, and top chunk score.",
    "Text-to-SQL is the right tool when data lives in structured tables and queries need aggregation, filtering, or joins. RAG is for unstructured documents.",
    "AST-based chunking extracts semantic units (functions, classes) from code. Line-based chunking destroys code semantics by splitting functions arbitrarily.",
]

DEMO_QUERIES = [
    "What is RAG and how does it work?",
    "How should I handle rate limiting in an LLM application?",
    "What does idempotent ingestion mean?",
    "How do I evaluate a RAG system?",
]


def run_demo() -> None:
    """
    Standalone demo: ingest corpus, run queries, show results.
    Does not require a running server.
    """
    print("=" * 65)
    print("RAG Service — Standalone Demo")
    print("=" * 65)

    # Ingest
    print("\n1. Ingesting demo corpus...")
    for i, doc in enumerate(DEMO_CORPUS):
        result = ingest_document(
            content=doc,
            doc_id=f"doc-{i+1:02d}",
            metadata={"source": "demo"},
            chunk_size=cfg.CHUNK_SIZE,
            overlap=cfg.CHUNK_OVERLAP,
        )
        status = "duplicate" if result["was_duplicate"] else f"+{result['chunks_added']} chunks"
        print(f"  doc-{i+1:02d}: {status}")

    print(f"\nIndex size: {vector_store.count()} chunks")

    # Query
    print("\n2. Running queries...")
    for query_text in DEMO_QUERIES:
        print(f"\nQuery: \"{query_text}\"")
        result = run_query(query_text, top_k=cfg.TOP_K)
        print(f"  Answer: {result['answer'][:200]}")
        print(f"  Sources: {result['sources']}")
        print(f"  Latency: {result['latency_breakdown']['total_ms']}ms "
              f"(embed: {result['latency_breakdown']['embed_ms']}ms, "
              f"retrieve: {result['latency_breakdown']['retrieve_ms']}ms, "
              f"generate: {result['latency_breakdown']['generate_ms']}ms)")

    # Eval
    if cfg.OPENAI_API_KEY:
        print("\n3. Running eval on first query...")
        q = DEMO_QUERIES[0]
        result = run_query(q, top_k=cfg.TOP_K)
        context = "\n\n".join(c["text"] for c in result["retrieved_chunks"])
        scores = run_rag_triad(q, context, result["answer"])
        print(f"  Faithfulness:       {scores.get('faithfulness', 'n/a'):.2f}")
        print(f"  Answer relevance:   {scores.get('answer_relevance', 'n/a'):.2f}")
        print(f"  Context relevance:  {scores.get('context_relevance', 'n/a'):.2f}")
    else:
        print("\n3. Skipping eval (no OPENAI_API_KEY configured)")
        print("   Set USE_LOCAL_EMBEDDINGS=true to test without an API key.")

    # Idempotency demo
    print("\n4. Idempotency test — re-ingest the same doc...")
    result = ingest_document(
        content=DEMO_CORPUS[0],
        doc_id="doc-01",
        metadata={"source": "demo"},
        chunk_size=cfg.CHUNK_SIZE,
        overlap=cfg.CHUNK_OVERLAP,
    )
    print(f"  was_duplicate: {result['was_duplicate']}  (chunks_added: {result['chunks_added']})")
    print(f"  Index size unchanged: {vector_store.count()} chunks")

    print("\nDemo complete. Start the API server with:")
    print("  uvicorn main:app --host 0.0.0.0 --port 8000 --reload")


if __name__ == "__main__":
    import sys

    if "--server" in sys.argv:
        if not FASTAPI_AVAILABLE:
            print("FastAPI not installed. Install with: pip install fastapi uvicorn")
            sys.exit(1)
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=cfg.PORT, reload=False)
    else:
        run_demo()
