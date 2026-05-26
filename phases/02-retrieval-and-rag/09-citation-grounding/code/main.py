# pip install openai
"""
Lesson 09: Citation Grounding
=============================
End-to-end citation-grounded RAG pipeline:
1. Retrieve chunks with metadata (source filename, page, chunk_id)
2. Build a prompt that asks the LLM to answer using ONLY the provided sources,
   citing them inline as [1], [2], etc.
3. Parse the response to extract citation markers
4. Verify each cited source actually exists in the retrieved set (hallucination check)
5. Format a final response with a "Sources" section listing only cited docs

Run: python main.py
Requires OPENAI_API_KEY in environment.
"""

import os
import re
from dataclasses import dataclass
from typing import Optional
from collections import Counter
from openai import OpenAI

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """A single text chunk with full provenance metadata."""
    chunk_id: str
    source: str
    page: Optional[int]
    section: Optional[str]
    text: str


# ---------------------------------------------------------------------------
# Sample corpus
# Hardcoded for demonstration; replace with your document store / vector DB
# ---------------------------------------------------------------------------

SAMPLE_CHUNKS = [
    Chunk(
        chunk_id="rag-001",
        source="rag-survey-2024.pdf",
        page=3,
        section="Introduction",
        text=(
            "Retrieval-Augmented Generation (RAG) was introduced by Lewis et al. (2020) "
            "as a method for conditioning language model generation on retrieved documents. "
            "Unlike purely parametric models, RAG systems can be updated without retraining "
            "by modifying the document store."
        ),
    ),
    Chunk(
        chunk_id="rag-002",
        source="rag-survey-2024.pdf",
        page=7,
        section="Retrieval Methods",
        text=(
            "Dense retrieval methods encode both queries and documents into a shared embedding "
            "space. The most commonly used models include DPR (Karpukhin et al., 2020) and "
            "Contriever (Izacard et al., 2022). Dense retrieval typically outperforms BM25 "
            "on out-of-domain queries but underperforms on keyword-heavy technical documents."
        ),
    ),
    Chunk(
        chunk_id="rag-003",
        source="hallucination-mitigation.pdf",
        page=2,
        section="Problem Statement",
        text=(
            "Large language models exhibit a behavior known as hallucination: generating "
            "plausible-sounding but factually incorrect statements. In the context of "
            "retrieval-augmented systems, a specific form called citation hallucination "
            "occurs when a model attributes a claim to a source that does not support it."
        ),
    ),
    Chunk(
        chunk_id="rag-004",
        source="hallucination-mitigation.pdf",
        page=8,
        section="Mitigation Strategies",
        text=(
            "Effective mitigation strategies include: (1) constrained generation, where the "
            "model is explicitly instructed to use only provided sources; (2) post-generation "
            "verification, where each cited source is checked against the claim; and (3) "
            "abstention training, where models learn to decline when retrieved context is "
            "insufficient."
        ),
    ),
    Chunk(
        chunk_id="rag-005",
        source="eval-best-practices.pdf",
        page=4,
        section="RAG Evaluation",
        text=(
            "The RAG Triad - faithfulness, answer relevance, and context relevance - provides "
            "a structured framework for evaluating RAG system quality. Faithfulness measures "
            "whether the generated answer is entailed by the retrieved context. Answer "
            "relevance measures whether the answer addresses the user's question. Context "
            "relevance measures whether the retrieved chunks were relevant to the query."
        ),
    ),
    Chunk(
        chunk_id="rag-006",
        source="dense-retrieval-paper.pdf",
        page=1,
        section="Abstract",
        text=(
            "Hybrid search combines dense vector retrieval with sparse keyword retrieval "
            "(e.g. BM25). By fusing the two result sets with Reciprocal Rank Fusion (RRF), "
            "hybrid search consistently outperforms either approach alone across diverse "
            "domain benchmarks."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Retrieval (toy implementation - replace with your vector store)
# ---------------------------------------------------------------------------

def _keyword_overlap_score(query: str, chunk: Chunk) -> float:
    """
    Naive keyword overlap score for demonstration.
    In production, replace with cosine similarity over embeddings.
    """
    q_tokens = set(re.findall(r'\b[a-z]+\b', query.lower()))
    c_tokens = Counter(re.findall(r'\b[a-z]+\b', chunk.text.lower()))
    overlap = sum(c_tokens[t] for t in q_tokens if t in c_tokens)
    return overlap / (len(q_tokens) + 1)


def retrieve(
    query: str,
    chunks: list[Chunk],
    top_k: int = 3,
) -> list[Chunk]:
    """
    Return the top-k most relevant chunks for a query, preserving all metadata.

    Replace the body of this function with your vector store lookup.
    The only contract: return a list of Chunk objects in ranked order.
    """
    scored = [(_keyword_overlap_score(query, c), c) for c in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a research assistant. Answer the user's question using ONLY \
the numbered sources provided below.

Rules:
1. Cite every factual claim inline using [N] notation, e.g. "...is established [1]."
2. You may cite multiple sources for one claim: "...is known [1][3]."
3. If the provided sources do not contain sufficient information to answer the question,
   respond ONLY with the exact phrase:
   "The provided sources do not contain sufficient information to answer this question."
4. Do not use knowledge from outside the provided sources.
5. Do not invent source numbers that are not in the numbered list below."""


def build_citation_prompt(
    query: str,
    retrieved_chunks: list[Chunk],
) -> tuple[str, str]:
    """
    Build (system_prompt, user_message) for citation-grounded generation.

    The user message embeds numbered sources so the LLM can cite them as [1], [2], etc.
    Every number maps to a specific chunk - which is what makes hallucination detection
    possible.
    """
    source_blocks = []
    for i, chunk in enumerate(retrieved_chunks, start=1):
        location = f"page {chunk.page}" if chunk.page else (chunk.section or "unknown location")
        source_blocks.append(
            f"[{i}] {chunk.text}\n"
            f"    (Source: {chunk.source}, {location})"
        )

    sources_text = "\n\n".join(source_blocks)
    user_message = f"Question: {query}\n\nSources:\n{sources_text}"

    return SYSTEM_PROMPT, user_message


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def generate_cited_answer(
    query: str,
    retrieved_chunks: list[Chunk],
    model: str = "gpt-4o-mini",
    client: Optional[OpenAI] = None,
) -> str:
    """
    Call the LLM with citation-enforcing prompts.
    Returns the raw response text including [N] markers.
    """
    if client is None:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    system_prompt, user_message = build_citation_prompt(query, retrieved_chunks)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,  # Deterministic - important for citation accuracy
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Citation verification
# ---------------------------------------------------------------------------

ABSTENTION_PHRASE = "the provided sources do not contain sufficient information"


def parse_citations(response_text: str) -> set[int]:
    """Extract all integer citation indices from [N] markers in the response."""
    return {int(m) for m in re.findall(r'\[(\d+)\]', response_text)}


def verify_citations(
    response_text: str,
    retrieved_chunks: list[Chunk],
) -> dict:
    """
    Mechanically verify that every [N] in the response maps to a real retrieved chunk.

    Returns a verification report dict with:
    - cited_ids: all [N] indices found in the response
    - valid_ids: cited IDs that correspond to an actual retrieved chunk
    - hallucinated_ids: cited IDs with no matching chunk (HALLUCINATION)
    - is_clean: True if no hallucinated citations
    - is_abstention: True if the system correctly declined to answer
    """
    is_abstention = ABSTENTION_PHRASE in response_text.lower()
    cited_ids = parse_citations(response_text)
    valid_range = set(range(1, len(retrieved_chunks) + 1))

    valid_ids = cited_ids & valid_range
    hallucinated_ids = cited_ids - valid_range

    return {
        "cited_ids": cited_ids,
        "valid_ids": valid_ids,
        "hallucinated_ids": hallucinated_ids,
        "is_clean": len(hallucinated_ids) == 0,
        "is_abstention": is_abstention,
    }


# ---------------------------------------------------------------------------
# Response formatting
# ---------------------------------------------------------------------------

def format_final_response(
    response_text: str,
    retrieved_chunks: list[Chunk],
    verification: dict,
) -> str:
    """
    Assemble the user-facing response.

    - If abstention: return a clean abstention message
    - If hallucinated citations exist: strip them and warn
    - Always append a "Sources" section listing only the actually-cited chunks
    """
    if verification["is_abstention"]:
        return (
            "**Answer:** The provided sources do not contain sufficient information "
            "to answer this question.\n\n"
            "_No sources were cited because the query could not be answered "
            "from the retrieved documents._"
        )

    display_text = response_text

    if verification["hallucinated_ids"]:
        for bad_id in sorted(verification["hallucinated_ids"]):
            display_text = display_text.replace(f"[{bad_id}]", "[REMOVED]")
        warning = (
            f"\n\n> **Warning:** {len(verification['hallucinated_ids'])} "
            f"hallucinated citation(s) were removed from this response."
        )
        display_text += warning

    # Build sources section - only chunks that were actually cited
    cited_source_lines = []
    for idx in sorted(verification["valid_ids"]):
        chunk = retrieved_chunks[idx - 1]
        location = f"page {chunk.page}" if chunk.page else (chunk.section or "")
        loc_str = f", {location}" if location else ""
        snippet = chunk.text[:80] + ("..." if len(chunk.text) > 80 else "")
        cited_source_lines.append(f"[{idx}] **{chunk.source}**{loc_str} - \"{snippet}\"")

    if cited_source_lines:
        sources_section = "\n".join(cited_source_lines)
    else:
        sources_section = "_No sources cited._"

    return f"{display_text}\n\n**Sources:**\n{sources_section}"


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def citation_grounded_rag(
    query: str,
    chunks: Optional[list[Chunk]] = None,
    top_k: int = 3,
    verbose: bool = True,
) -> str:
    """
    End-to-end citation-grounded RAG:
    retrieve → prompt → generate → verify → format
    """
    if chunks is None:
        chunks = SAMPLE_CHUNKS

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # 1. Retrieve
    retrieved = retrieve(query, chunks, top_k=top_k)

    if verbose:
        print(f"\n{'='*64}")
        print(f"QUERY: {query}")
        print("RETRIEVED CHUNKS:")
        for i, c in enumerate(retrieved, 1):
            print(f"  [{i}] {c.chunk_id} ({c.source}, p.{c.page})")

    # 2-3. Build prompt + generate
    raw_response = generate_cited_answer(query, retrieved, client=client)

    if verbose:
        print(f"\nRAW LLM RESPONSE:\n{raw_response}")

    # 4. Verify citations
    verification = verify_citations(raw_response, retrieved)

    if verbose:
        print("\nCITATION VERIFICATION:")
        print(f"  Cited IDs:        {sorted(verification['cited_ids'])}")
        print(f"  Valid IDs:        {sorted(verification['valid_ids'])}")
        print(f"  Hallucinated IDs: {sorted(verification['hallucinated_ids'])}")
        print(f"  Clean:            {verification['is_clean']}")
        print(f"  Abstention:       {verification['is_abstention']}")

    # 5. Format response
    final = format_final_response(raw_response, retrieved, verification)

    return final


# ---------------------------------------------------------------------------
# Evaluation helper
# ---------------------------------------------------------------------------

def run_eval_suite(queries: list[dict], verbose: bool = False) -> dict:
    """
    Run a batch evaluation over a list of queries.

    Each query dict should have:
    - "query": str
    - "answerable": bool (is the answer in the corpus?)

    Returns aggregate metrics:
    - hallucination_rate: fraction of citations that were hallucinated
    - abstention_rate_on_unanswerable: fraction of unanswerable queries where
      the system correctly abstained
    - total_queries: int
    """
    total_cited = 0
    total_hallucinated = 0
    unanswerable_count = 0
    correct_abstentions = 0

    for item in queries:
        query = item["query"]
        answerable = item.get("answerable", True)

        retrieved = retrieve(query, SAMPLE_CHUNKS, top_k=3)
        raw_response = generate_cited_answer(query, retrieved)
        verification = verify_citations(raw_response, retrieved)

        total_cited += len(verification["cited_ids"])
        total_hallucinated += len(verification["hallucinated_ids"])

        if not answerable:
            unanswerable_count += 1
            if verification["is_abstention"]:
                correct_abstentions += 1

        if verbose:
            status = "CLEAN" if verification["is_clean"] else "HALLUCINATION"
            if verification["is_abstention"]:
                status = "ABSTAINED"
            print(f"[{status}] {query[:60]}")

    hallucination_rate = (
        total_hallucinated / total_cited if total_cited > 0 else 0.0
    )
    abstention_rate = (
        correct_abstentions / unanswerable_count if unanswerable_count > 0 else None
    )

    return {
        "total_queries": len(queries),
        "total_citations": total_cited,
        "total_hallucinated": total_hallucinated,
        "hallucination_rate": hallucination_rate,
        "unanswerable_queries": unanswerable_count,
        "correct_abstentions": correct_abstentions,
        "abstention_rate_on_unanswerable": abstention_rate,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Lesson 09: Citation Grounding")
    print("=" * 64)

    test_queries = [
        "What is RAG and why was it introduced?",
        "How do dense retrieval methods work and what models are commonly used?",
        "What is citation hallucination and how can it be mitigated?",
        "What does the RAG Triad measure?",
        "What is the capital of France?",  # Out-of-scope - should trigger abstention
    ]

    for query in test_queries:
        result = citation_grounded_rag(query, verbose=True)
        print(f"\n--- FINAL RESPONSE ---\n{result}\n")

    print("\n" + "=" * 64)
    print("EVALUATION SUITE")

    eval_queries = [
        {"query": "What is RAG?", "answerable": True},
        {"query": "How does dense retrieval compare to BM25?", "answerable": True},
        {"query": "What are hallucination mitigation strategies?", "answerable": True},
        {"query": "What is the capital of Japan?", "answerable": False},
        {"query": "Who won the 2024 World Cup?", "answerable": False},
    ]

    metrics = run_eval_suite(eval_queries, verbose=True)
    print(f"\nMetrics:")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.1%}")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
