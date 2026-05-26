# pip install openai llama-index llama-index-llms-openai llama-index-embeddings-openai
#             langchain langchain-openai langchain-community faiss-cpu
# Set environment variable: OPENAI_API_KEY=sk-...

import os
import sys
import time

import numpy as np
from openai import OpenAI

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

CORPUS = [
    "Retrieval Augmented Generation (RAG) combines a retrieval system with an LLM to ground answers in a document corpus.",
    "Chunking strategy is the most impactful decision in a RAG pipeline. Chunk too small: context is lost. Chunk too large: retrieval is diluted.",
    "Cosine similarity measures the angle between two vectors, regardless of magnitude. It is the standard similarity metric for embedding-based retrieval.",
    "Hybrid search combines dense (embedding) retrieval with sparse (BM25/keyword) retrieval. It consistently outperforms either alone on recall.",
    "Re-ranking uses a cross-encoder to re-score retrieved chunks after initial retrieval. It adds latency but improves precision significantly.",
    "The RAG Triad evaluates three dimensions: faithfulness (answer grounded in context?), answer relevance (answers the question?), and context relevance (retrieved the right chunks?).",
    "LlamaIndex specializes in document ingestion pipelines and multi-index retrieval. It manages document nodes, metadata, and relationships automatically.",
    "LangChain's LCEL (LangChain Expression Language) allows composing chains declaratively. The pipe operator chains runnables sequentially.",
    "A naive RAG pipeline: chunk text, embed chunks, store vectors, embed query, cosine search, format prompt, call LLM.",
    "Evaluation without ground truth is dangerous. Build your eval set before you build your pipeline. Otherwise you tune to pass the test you already know.",
]

TEST_QUERIES = [
    "What is RAG?",
    "How does hybrid search work?",
    "What is the RAG Triad?",
    "When should I use LlamaIndex?",
    "How do I evaluate a RAG pipeline?",
]

EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"


# ===========================================================================
# IMPLEMENTATION 1: RAW (no framework)
# ===========================================================================

raw_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


def raw_embed(texts: list[str]) -> np.ndarray:
    """Batch embed using OpenAI API. Returns (n, dim) numpy array."""
    resp = raw_client.embeddings.create(model=EMBED_MODEL, input=texts)
    return np.array([item.embedding for item in resp.data], dtype=np.float32)


def raw_build_index(corpus: list[str]) -> dict:
    """
    Build in-memory index: embed all corpus texts.
    Returns {texts, vectors}.
    """
    vectors = raw_embed(corpus)
    return {"texts": corpus, "vectors": vectors}


def raw_retrieve(query: str, index: dict, top_k: int = 3) -> list[dict]:
    """Cosine similarity search. Returns list of {text, score}."""
    query_vec = raw_embed([query])[0]
    vectors = index["vectors"]
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vec)
    norms = np.where(norms == 0, 1e-10, norms)
    scores = vectors @ query_vec / norms
    top = np.argsort(scores)[::-1][:top_k]
    return [{"text": index["texts"][i], "score": float(scores[i])} for i in top]


def raw_ask(query: str, index: dict, top_k: int = 3, verbose: bool = False) -> dict:
    """
    Full RAG pipeline: retrieve + augment + generate.
    Returns {answer, retrieved, latency_ms}.
    """
    t0 = time.time()
    retrieved = raw_retrieve(query, index, top_k=top_k)

    if verbose:
        print(f"  [Raw] Retrieved {len(retrieved)} chunks:")
        for r in retrieved:
            print(f"    ({r['score']:.3f}) {r['text'][:80]}")

    context = "\n\n".join(f"[{i+1}] {c['text']}" for i, c in enumerate(retrieved))
    prompt = (
        f"Answer the question using ONLY the context below.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {query}\n"
        f"Answer:"
    )
    resp = raw_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": "Answer only from the provided context. Be concise."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )
    answer = resp.choices[0].message.content.strip()
    return {
        "answer": answer,
        "retrieved": retrieved,
        "latency_ms": int((time.time() - t0) * 1000),
        "impl": "raw",
    }


# ===========================================================================
# IMPLEMENTATION 2: LlamaIndex
# ===========================================================================

def build_llamaindex(corpus: list[str]):
    """
    Build a LlamaIndex VectorStoreIndex from the corpus.
    LlamaIndex handles: Document wrapping, node parsing, embedding, storage.
    Returns the index object.
    """
    try:
        from llama_index.core import VectorStoreIndex, Document, Settings
        from llama_index.core.node_parser import SentenceSplitter
        from llama_index.llms.openai import OpenAI as LlamaOpenAI
        from llama_index.embeddings.openai import OpenAIEmbedding
    except ImportError as e:
        print(f"LlamaIndex not installed: {e}")
        print("Install with: pip install llama-index llama-index-llms-openai llama-index-embeddings-openai")
        return None

    # Configure global settings (LlamaIndex uses a global Settings object)
    Settings.llm = LlamaOpenAI(model=CHAT_MODEL, temperature=0.0)
    Settings.embed_model = OpenAIEmbedding(model=EMBED_MODEL)
    Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)

    documents = [Document(text=text) for text in corpus]
    index = VectorStoreIndex.from_documents(documents, show_progress=False)
    return index


def llamaindex_ask(query: str, index, top_k: int = 3, verbose: bool = False) -> dict:
    """
    Query via LlamaIndex QueryEngine.
    The QueryEngine wraps: retriever + prompt template + LLM call.
    """
    if index is None:
        return {"answer": "[LlamaIndex not available]", "retrieved": [], "latency_ms": 0, "impl": "llamaindex"}

    t0 = time.time()
    query_engine = index.as_query_engine(similarity_top_k=top_k)
    response = query_engine.query(query)

    if verbose:
        print(f"  [LlamaIndex] Source nodes:")
        for node in response.source_nodes:
            print(f"    ({node.score:.3f}) {node.text[:80]}")

    retrieved = []
    if hasattr(response, "source_nodes"):
        retrieved = [
            {"text": n.text, "score": float(n.score) if n.score else 0.0}
            for n in response.source_nodes
        ]

    return {
        "answer": str(response),
        "retrieved": retrieved,
        "latency_ms": int((time.time() - t0) * 1000),
        "impl": "llamaindex",
    }


def llamaindex_retrieve_raw(query: str, index, top_k: int = 3) -> list:
    """
    Escape hatch: get raw Node objects for custom processing.
    Bypasses the QueryEngine - use for custom re-ranking or prompt formatting.
    """
    if index is None:
        return []
    retriever = index.as_retriever(similarity_top_k=top_k)
    return retriever.retrieve(query)  # list of NodeWithScore


# ===========================================================================
# IMPLEMENTATION 3: LangChain / LCEL
# ===========================================================================

def build_langchain(corpus: list[str]):
    """
    Build a LangChain FAISS vectorstore from the corpus.
    Returns the vectorstore object.
    """
    try:
        from langchain_openai import OpenAIEmbeddings
        from langchain_core.documents import Document as LCDocument
        from langchain_community.vectorstores import FAISS
    except ImportError as e:
        print(f"LangChain not installed: {e}")
        print("Install with: pip install langchain langchain-openai langchain-community faiss-cpu")
        return None

    embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
    documents = [LCDocument(page_content=text) for text in corpus]
    vectorstore = FAISS.from_documents(documents, embeddings)
    return vectorstore


def langchain_ask(query: str, vectorstore, top_k: int = 3, verbose: bool = False) -> dict:
    """
    LCEL chain: retriever | format_docs | prompt | llm | output_parser.
    The pipe operator (|) composes Runnables sequentially.
    """
    if vectorstore is None:
        return {"answer": "[LangChain not available]", "retrieved": [], "latency_ms": 0, "impl": "langchain"}

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.runnables import RunnablePassthrough
    except ImportError as e:
        return {"answer": f"[Import error: {e}]", "retrieved": [], "latency_ms": 0, "impl": "langchain"}

    t0 = time.time()

    retriever = vectorstore.as_retriever(search_kwargs={"k": top_k})
    llm = ChatOpenAI(model=CHAT_MODEL, temperature=0.0)

    prompt = ChatPromptTemplate.from_template(
        "Answer the question using ONLY the context below. Be concise.\n\n"
        "Context:\n{context}\n\n"
        "Question: {question}\n"
        "Answer:"
    )

    def format_docs(docs) -> str:
        texts = [doc.page_content for doc in docs]
        if verbose:
            print(f"  [LangChain] Retrieved {len(texts)} chunks:")
            for t in texts:
                print(f"    {t[:80]}")
        return "\n\n".join(texts)

    # LCEL chain using the | operator
    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    answer = chain.invoke(query)

    # Also retrieve for logging
    retrieved_docs = retriever.invoke(query)
    retrieved = [{"text": d.page_content, "score": 0.0} for d in retrieved_docs]

    return {
        "answer": answer,
        "retrieved": retrieved,
        "latency_ms": int((time.time() - t0) * 1000),
        "impl": "langchain",
    }


def langchain_retrieve_raw(query: str, vectorstore, top_k: int = 3) -> list:
    """
    Escape hatch: retrieve raw Document objects for custom processing.
    Use for custom re-ranking, metadata filtering, or prompt formatting.
    """
    if vectorstore is None:
        return []
    retriever = vectorstore.as_retriever(search_kwargs={"k": top_k})
    return retriever.invoke(query)  # list of Document objects


# ===========================================================================
# Comparison runner
# ===========================================================================

def print_separator(title: str = "", width: int = 65) -> None:
    if title:
        print(f"\n{'=' * width}")
        print(f"  {title}")
        print(f"{'=' * width}")
    else:
        print(f"\n{'─' * width}")


def run_comparison(verbose: bool = False) -> None:
    print_separator("STEP 1: BUILD INDEXES")

    # Raw
    print("\nBuilding Raw index...", end=" ", flush=True)
    t0 = time.time()
    raw_index = raw_build_index(CORPUS)
    raw_build_time = time.time() - t0
    print(f"done ({raw_build_time:.2f}s)")

    # LlamaIndex
    print("Building LlamaIndex index...", end=" ", flush=True)
    t0 = time.time()
    llama_index = build_llamaindex(CORPUS)
    llama_build_time = time.time() - t0
    print(f"done ({llama_build_time:.2f}s)" if llama_index else "SKIPPED (not installed)")

    # LangChain
    print("Building LangChain index...", end=" ", flush=True)
    t0 = time.time()
    lc_vectorstore = build_langchain(CORPUS)
    lc_build_time = time.time() - t0
    print(f"done ({lc_build_time:.2f}s)" if lc_vectorstore else "SKIPPED (not installed)")

    print_separator("STEP 2: QUERY COMPARISON")

    results_by_impl: dict[str, list[dict]] = {"raw": [], "llamaindex": [], "langchain": []}

    for query in TEST_QUERIES:
        print(f"\nQuery: \"{query}\"")
        print("─" * 55)

        r = raw_ask(query, raw_index, verbose=verbose)
        print(f"  [Raw        {r['latency_ms']:4d}ms]  {r['answer'][:100]}")
        results_by_impl["raw"].append(r)

        if llama_index:
            r = llamaindex_ask(query, llama_index, verbose=verbose)
            print(f"  [LlamaIndex {r['latency_ms']:4d}ms]  {r['answer'][:100]}")
            results_by_impl["llamaindex"].append(r)

        if lc_vectorstore:
            r = langchain_ask(query, lc_vectorstore, verbose=verbose)
            print(f"  [LangChain  {r['latency_ms']:4d}ms]  {r['answer'][:100]}")
            results_by_impl["langchain"].append(r)

    print_separator("STEP 3: ESCAPE HATCH DEMO")
    print("\nDemonstrating that each framework exposes raw retrieval...")

    demo_query = "What is the RAG Triad?"

    raw_chunks = raw_retrieve(demo_query, raw_index, top_k=2)
    print(f"\n[Raw] Retrieved {len(raw_chunks)} chunks for: \"{demo_query}\"")
    for c in raw_chunks:
        print(f"  ({c['score']:.3f}) {c['text'][:80]}")

    if llama_index:
        nodes = llamaindex_retrieve_raw(demo_query, llama_index, top_k=2)
        print(f"\n[LlamaIndex] Retrieved {len(nodes)} nodes:")
        for n in nodes:
            score = f"{n.score:.3f}" if n.score else "n/a"
            print(f"  ({score}) {n.text[:80]}")

    if lc_vectorstore:
        docs = langchain_retrieve_raw(demo_query, lc_vectorstore, top_k=2)
        print(f"\n[LangChain] Retrieved {len(docs)} documents:")
        for d in docs:
            print(f"  {d.page_content[:80]}")

    print_separator("STEP 4: DECISION MATRIX")
    print("""
  ┌─────────────────────────────────────┬────────────────────────────┐
  │ Situation                           │ Recommendation             │
  ├─────────────────────────────────────┼────────────────────────────┤
  │ < 10k docs, simple Q&A              │ Raw                        │
  │ Prototype / exploration             │ Raw                        │
  │ Complex ingestion (PDFs, HTML, etc) │ LlamaIndex                 │
  │ Hierarchical index needed           │ LlamaIndex                 │
  │ Knowledge graph required            │ LlamaIndex                 │
  │ Conditional routing between pipelines│ LangChain/LCEL            │
  │ Conversational RAG with history     │ LangChain/LCEL             │
  │ RAG inside an agent                 │ LangChain/LangGraph        │
  │ Need streaming responses            │ LangChain/LCEL             │
  └─────────────────────────────────────┴────────────────────────────┘

  The escape hatch principle: any framework you use MUST let you access
  raw retrieved chunks and implement custom logic. If it doesn't, it
  will eventually trap you.
""")


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    if verbose:
        print("Verbose mode: showing retrieved chunks for each query.")

    run_comparison(verbose=verbose)


if __name__ == "__main__":
    main()
