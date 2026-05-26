# pip install openai numpy
# Usage:
#   export OPENAI_API_KEY=sk-...
#   python main.py
#
# Implements 4 query transformation techniques:
#   (1) Query Rewriting - rephrase for better retrieval vocabulary
#   (2) HyDE - generate hypothetical answer, embed that instead of the question
#   (3) Step-Back Prompting - generate more general query for background context
#   (4) Multi-Query - generate N phrasings, retrieve all, deduplicate
#
# To use with your RAG pipeline from Lesson 05:
#   from lesson05_main import ingest, retrieve
#   store = ingest("my_document.txt")
#   retrieval_fn = lambda q, k: retrieve(q, store, top_k=k)

import os
import hashlib
from typing import Any, Callable

import numpy as np
from openai import OpenAI

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"

# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def embed(texts: list[str]) -> list[list[float]]:
    """Batch embed a list of texts. Returns one vector per input."""
    if not texts:
        return []
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in response.data]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    va, vb = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def llm_call(system: str, user: str, temperature: float = 0.3) -> str:
    """Single LLM call. Returns the string content of the response."""
    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def deduplicate_chunks(chunks: list[dict]) -> list[dict]:
    """
    Remove duplicate chunks by content hash.
    Multi-query retrieval will often return the same chunk for different phrasings.
    Keeps the first occurrence (highest score if sorted before calling).
    """
    seen: set[str] = set()
    unique = []
    for chunk in chunks:
        h = hashlib.md5(chunk.get("text", "").encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(chunk)
    return unique

# ---------------------------------------------------------------------------
# Technique 1: Query Rewriting
# ---------------------------------------------------------------------------

REWRITE_SYSTEM = """You are a retrieval query optimizer. Rewrite the user's question
into a more effective retrieval query that will better match relevant documents.

Rules:
- Expand abbreviations, acronyms, and pronouns
- Replace informal language with technical vocabulary likely to appear in documents
- Add synonyms or related terms that might appear in relevant passages
- Remove filler words and conversational phrasing
- Return ONLY the rewritten query - no explanation, no preamble, no punctuation at the end."""


def rewrite_query(query: str) -> str:
    """
    Rewrite a user query to be more effective for retrieval.

    This is the lowest-risk, highest-value transformation.
    Apply it first. It helps when:
      - The user wrote informally ("how do I fix that error from last week")
      - The query contains pronouns ("it", "this", "my")
      - The user uses different vocabulary than the documents

    One LLM call. ~200-400ms latency.

    Example:
      Input:  "how do I set the timeout for auth?"
      Output: "authentication session timeout configuration maximum duration setting"
    """
    return llm_call(
        system=REWRITE_SYSTEM,
        user=f"Original query: {query}",
        temperature=0.1,  # low temperature for consistent, deterministic output
    )

# ---------------------------------------------------------------------------
# Technique 2: HyDE (Hypothetical Document Embeddings)
# ---------------------------------------------------------------------------

HYDE_SYSTEM = """You are a technical writer. Write a short hypothetical passage that would
directly answer the given question, as if it came from the relevant documentation.

Requirements:
- Write 2-4 sentences
- Use the technical vocabulary that would appear in source documents
- Be specific and concrete - write as a confident factual excerpt
- Do NOT say "In this document" or "This passage explains" - start with the content directly
- Do NOT express uncertainty or use hedging language"""


def hyde_query(query: str) -> tuple[str, list[float]]:
    """
    HyDE: Generate a hypothetical answer to the query, embed that instead.

    Key insight: questions and answers occupy different regions of embedding space.
    A question like "what causes segfaults in C?" embeds differently from
    "A segmentation fault occurs when a program accesses memory it does not own,
    typically through a null pointer dereference or buffer overflow."

    The hypothetical answer embeds in the same neighborhood as real document
    passages - because it uses the same vocabulary and sentence patterns.

    Returns: (hypothetical_document_text, embedding_vector_of_that_text)

    When to use:
      - Documents are formal/technical, queries are informal/colloquial
      - Academic papers queried with casual questions
      - Medical/legal documents queried by non-experts

    Risk: if the LLM generates factually wrong content, the embedding
    points toward wrong documents. Mitigate by using a strong model
    and keeping temperature low.
    """
    hypothetical_doc = llm_call(
        system=HYDE_SYSTEM,
        user=f"Question: {query}",
        temperature=0.2,
    )
    # Embed the hypothetical document, NOT the original query
    vector = embed([hypothetical_doc])[0]
    return hypothetical_doc, vector

# ---------------------------------------------------------------------------
# Technique 3: Step-Back Prompting
# ---------------------------------------------------------------------------

STEPBACK_SYSTEM = """You are a retrieval strategist. Given a specific question,
generate a more general "step-back" question that asks about the underlying
principle, category, or background concept.

The step-back question should:
- Ask about the broader concept rather than the specific detail
- Be general enough to retrieve foundational context
- NOT include the specific identifiers or values from the original question

Return ONLY the step-back question - no explanation, no preamble.

Examples:
  Specific: "What is the max dose of ibuprofen for a 70kg adult with mild pain?"
  Step-back: "What are the dosing guidelines and safety considerations for ibuprofen?"

  Specific: "How do I fix TypeError: unsupported operand type(s) for +: int and str in Python?"
  Step-back: "What are common Python type error causes and how are they debugged?"

  Specific: "What does section 14(b)(ii) of the Master Service Agreement say about liability?"
  Step-back: "What are standard liability limitation clauses in service agreements?" """


def stepback_query(query: str) -> str:
    """
    Step-back prompting: generate a more general version of the query.

    Use this when the user's question is very specific but the relevant
    context lives at a higher level of abstraction.

    Pattern: retrieve the step-back query first (background context),
    then retrieve the original query (specific details), merge both.
    The LLM gets both the background and the specific answer.

    Example:
      query = "metformin dose adjustment for eGFR < 45"
      step_back = "metformin pharmacokinetics and renal impairment guidelines"
      → Both retrieve different useful chunks
      → LLM can answer the specific question with proper context
    """
    return llm_call(
        system=STEPBACK_SYSTEM,
        user=f"Specific question: {query}",
        temperature=0.2,
    )

# ---------------------------------------------------------------------------
# Technique 4: Multi-Query
# ---------------------------------------------------------------------------

MULTIQUERY_SYSTEM = """Generate {n} different phrasings of the following question.
Each phrasing should:
- Preserve the same core information need
- Use different vocabulary or framing
- Approach the question from a different angle

Return exactly {n} numbered queries (1. 2. 3. etc.), one per line.
No explanations. No preamble. Just the queries."""


def multi_query(query: str, n: int = 3) -> list[str]:
    """
    Generate n alternative phrasings of the query.
    Retrieve with all phrasings, deduplicate results.

    This trades latency and LLM cost for higher recall.
    Each phrasing may retrieve different relevant chunks.
    After deduplication, the combined result set has better coverage.

    Cost: 1 extra LLM call + n extra embedding calls.
    Latency budget: roughly 2-3x the baseline retrieval latency.

    Always includes the original query in the returned list.
    Returns: [original_query, generated_query_1, ..., generated_query_n]
    """
    prompt = MULTIQUERY_SYSTEM.format(n=n)
    raw = llm_call(system=prompt, user=f"Question: {query}", temperature=0.6)

    # Parse numbered lines: "1. query text" → "query text"
    queries = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Remove "1." or "1)" prefix
        if line[0].isdigit():
            parts = line.split(".", 1)
            if len(parts) == 2:
                line = parts[1].strip()
            parts = line.split(")", 1)
            if len(parts) == 2 and parts[0].isdigit():
                line = parts[1].strip()
        if line:
            queries.append(line)

    # Original query goes first (highest confidence phrasing)
    result = [query]
    for q in queries:
        if q.lower().strip() != query.lower().strip():
            result.append(q)

    return result[:n + 1]

# ---------------------------------------------------------------------------
# Unified transformation interface
# ---------------------------------------------------------------------------

RetrievalFn = Callable[[str, int], list[dict]]


def retrieve_with_transformation(
    query: str,
    retrieval_fn: RetrievalFn,
    technique: str = "rewrite",
    top_k: int = 5,
    verbose: bool = True,
) -> dict:
    """
    Apply a query transformation and retrieve.

    Args:
        query: original user query string
        retrieval_fn: function(query_text: str, top_k: int) -> list[dict]
                      Use your retrieve() from Lesson 05 here
        technique: one of "none" | "rewrite" | "hyde" | "stepback" | "multi_query"
        top_k: number of chunks to retrieve per query
        verbose: print transformation output

    Returns:
        {
          "original_query": str,
          "transformed_query": str | list[str],
          "retrieved_chunks": list[dict],
          "technique": str,
          "n_chunks_after_dedup": int,
        }
    """
    if verbose:
        print(f"  technique={technique} | query='{query[:60]}'")

    if technique == "none":
        chunks = retrieval_fn(query, top_k)
        return {
            "original_query": query,
            "transformed_query": query,
            "retrieved_chunks": chunks,
            "technique": "none",
            "n_chunks_after_dedup": len(chunks),
        }

    elif technique == "rewrite":
        transformed = rewrite_query(query)
        if verbose:
            print(f"  rewritten → '{transformed[:80]}'")
        chunks = retrieval_fn(transformed, top_k)

    elif technique == "hyde":
        hypothetical_doc, _ = hyde_query(query)
        if verbose:
            print(f"  HyDE doc → '{hypothetical_doc[:80]}...'")
        # Pass hypothetical doc text to retriever (it will embed it internally)
        chunks = retrieval_fn(hypothetical_doc, top_k)
        transformed = hypothetical_doc

    elif technique == "stepback":
        step_back = stepback_query(query)
        if verbose:
            print(f"  step-back → '{step_back[:80]}'")
        # Retrieve both step-back and original, merge
        sb_chunks = retrieval_fn(step_back, top_k)
        orig_chunks = retrieval_fn(query, top_k)
        chunks = deduplicate_chunks(sb_chunks + orig_chunks)[:top_k]
        transformed = step_back

    elif technique == "multi_query":
        queries = multi_query(query, n=3)
        if verbose:
            for i, q in enumerate(queries, 1):
                print(f"  query {i} → '{q[:70]}'")
        all_chunks = []
        for q in queries:
            all_chunks.extend(retrieval_fn(q, top_k))
        # Sort by score if available, then deduplicate
        all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
        chunks = deduplicate_chunks(all_chunks)[:top_k * 2]
        transformed = queries

    else:
        raise ValueError(f"Unknown technique: '{technique}'. "
                         f"Choose from: none, rewrite, hyde, stepback, multi_query")

    return {
        "original_query": query,
        "transformed_query": transformed,
        "retrieved_chunks": chunks,
        "technique": technique,
        "n_chunks_after_dedup": len(chunks),
    }

# ---------------------------------------------------------------------------
# Evaluation helper
# ---------------------------------------------------------------------------

def measure_recall_improvement(
    query: str,
    retrieval_fn: RetrievalFn,
    ground_truth_fragments: list[str],
    top_k: int = 5,
) -> dict:
    """
    Compare all techniques on a single query.
    ground_truth_fragments: list of text substrings that should appear in retrieved chunks.
    Returns per-technique recall scores.

    Use this with a real retrieval_fn to measure whether transformation helps your corpus:
        recall_before = measure_recall_improvement(query, retrieval_fn, relevant_texts)
        # Look at "none" vs other techniques
    """

    def recall(chunks: list[dict], fragments: list[str]) -> float:
        if not fragments:
            return 1.0
        found = sum(
            1 for frag in fragments
            if any(frag.lower() in c.get("text", "").lower() for c in chunks)
        )
        return found / len(fragments)

    results = {}
    for technique in ["none", "rewrite", "hyde", "stepback", "multi_query"]:
        try:
            result = retrieve_with_transformation(
                query, retrieval_fn, technique=technique, top_k=top_k, verbose=False
            )
            r = recall(result["retrieved_chunks"], ground_truth_fragments)
            results[technique] = {"recall": r, "chunks": len(result["retrieved_chunks"])}
        except Exception as e:
            results[technique] = {"recall": None, "error": str(e)}

    return results


def print_recall_table(query: str, results: dict) -> None:
    """Print recall comparison table for a single query."""
    print(f"\nQuery: '{query[:70]}'")
    print(f"  {'Technique':<15}  {'Recall':>8}  Notes")
    print("  " + "─" * 50)
    baseline = results.get("none", {}).get("recall", 0) or 0
    for technique, metrics in results.items():
        if metrics.get("recall") is None:
            print(f"  {technique:<15}  {'ERROR':>8}  {metrics.get('error', '')}")
            continue
        r = metrics["recall"]
        delta = r - baseline
        note = f"  +{delta:.2f} vs baseline" if delta > 0.01 else ("  (baseline)" if technique == "none" else "")
        print(f"  {technique:<15}  {r:>8.2f}{note}")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Stub retriever: replace with your retrieve() from Lesson 05
    def stub_retriever(query: str, top_k: int) -> list[dict]:
        """
        Stub for demonstration. Replace with real retriever:

            from lesson05_main import ingest, retrieve
            store = ingest("your_document.txt")
            def real_retriever(q, k): return retrieve(q, store, top_k=k)
        """
        # Simulate returning chunks with some relation to the query
        return [
            {"text": f"Document passage {i}: content related to '{query[:30]}...'",
             "score": round(0.9 - i * 0.08, 2),
             "id": f"doc_{i}"}
            for i in range(top_k)
        ]

    demo_queries = [
        ("is aspirin safe after a bleed?",
         ["aspirin", "hemorrhage", "contraindicated", "antiplatelet"]),
        ("how do I configure the auth timeout setting?",
         ["authentication", "timeout", "session", "configuration"]),
        ("metformin for kidney disease patient",
         ["metformin", "renal impairment", "eGFR", "contraindicated"]),
    ]

    print("=" * 70)
    print("QUERY TRANSFORMATION DEMO")
    print("(Using stub retriever - replace with your real retrieve() function)")
    print("=" * 70)

    for query, _ in demo_queries[:1]:
        print(f"\nQuery: '{query}'")
        print("\n[1] Query Rewriting:")
        rw = rewrite_query(query)
        print(f"    → {rw}")

        print("\n[2] HyDE:")
        hyde_doc, _ = hyde_query(query)
        print(f"    → {hyde_doc[:150]}...")

        print("\n[3] Step-Back:")
        sb = stepback_query(query)
        print(f"    → {sb}")

        print("\n[4] Multi-Query (3 phrasings):")
        mqs = multi_query(query, n=3)
        for i, q in enumerate(mqs, 1):
            print(f"    {i}. {q}")

    print("\n" + "=" * 70)
    print("INTEGRATION GUIDE")
    print("=" * 70)
    print("""
Replace stub_retriever with your real pipeline:

    # From Lesson 05:
    from lesson05_main import ingest, retrieve

    store = ingest("my_document.txt")

    def my_retriever(query: str, top_k: int) -> list[dict]:
        return retrieve(query, store, top_k=top_k)

    # Apply a transformation:
    result = retrieve_with_transformation(
        query="how does authentication work",
        retrieval_fn=my_retriever,
        technique="rewrite",    # or: hyde, stepback, multi_query
        top_k=5,
    )
    print(result["retrieved_chunks"])

    # Measure which technique helps most on your corpus:
    from main import measure_recall_improvement, print_recall_table

    recall_results = measure_recall_improvement(
        query="is aspirin safe after a bleed?",
        retrieval_fn=my_retriever,
        ground_truth_fragments=["contraindicated", "hemorrhage"],
    )
    print_recall_table("is aspirin safe after a bleed?", recall_results)
""")
