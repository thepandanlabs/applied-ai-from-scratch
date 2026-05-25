# pip install openai numpy sentence-transformers
"""
Lesson 11: Advanced RAG
=======================
Three advanced RAG patterns:
1. Parent-Document Retrieval: index small child chunks, return large parent chunks
2. Multi-Vector Indexing: generate summaries, index both, retrieve by either
3. Contextual Retrieval (Anthropic): prepend context sentence to each chunk before indexing

Run: python main.py
Requires OPENAI_API_KEY in environment.
"""

import os
import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from openai import OpenAI
from sentence_transformers import SentenceTransformer


# ---------------------------------------------------------------------------
# Sample documents
# ---------------------------------------------------------------------------

SAMPLE_DOCUMENTS = [
    {
        "source": "board-risk-report-2024.pdf",
        "section": "Q3 Risk Assessment",
        "text": (
            "The board's Q3 risk assessment evaluated 12 distinct risk categories "
            "including market risk, operational risk, regulatory compliance risk, "
            "and reputational risk. A cross-functional risk committee reviewed each "
            "category using a two-dimensional materiality matrix: likelihood of "
            "occurrence and potential financial impact. After thorough review, the "
            "committee determined that none of the assessed risks exceeded the "
            "materiality threshold of $50 million in potential impact within a "
            "12-month horizon. The board concluded that the current risk posture "
            "is acceptable and no immediate mitigation actions are required."
        ),
    },
    {
        "source": "ml-systems-architecture.pdf",
        "section": "Embedding Models",
        "text": (
            "Modern embedding models are built on transformer architectures fine-tuned "
            "for semantic similarity tasks. The training procedure uses contrastive loss: "
            "similar pairs are pulled together in embedding space while dissimilar pairs "
            "are pushed apart. Popular choices include sentence-transformers models "
            "(all-MiniLM-L6-v2, all-mpnet-base-v2) for local deployment and OpenAI's "
            "text-embedding-3 family for API-based workflows. Model selection depends "
            "on the trade-off between embedding quality and inference cost."
        ),
    },
    {
        "source": "rag-design-patterns.pdf",
        "section": "Retrieval Strategies",
        "text": (
            "Hybrid retrieval combines dense vector search with sparse keyword search "
            "using Reciprocal Rank Fusion to merge result sets. As described in the "
            "previous chapter on index architecture, dense retrieval captures semantic "
            "similarity while sparse retrieval captures exact keyword matches. The "
            "hybrid approach consistently outperforms either method alone, particularly "
            "on technical domain queries where terminology precision matters. The "
            "optimal fusion weight (alpha) between dense and sparse components typically "
            "falls between 0.6 and 0.8 in favor of dense retrieval for natural language "
            "queries, but may shift toward sparse for code and identifier-heavy queries."
        ),
    },
]

# Chunks with problematic references — ideal test for contextual retrieval
ORPHANED_CHUNKS = [
    {
        "source": "methodology-report.pdf",
        "full_document": (
            "Section 2: Legacy Methodology\n"
            "The previous methodology relied on manual annotation and had a error rate of 15%.\n\n"
            "Section 3: Updated Methodology\n"
            "As noted in section 2, the previous approach had significant limitations. "
            "The updated methodology introduced in Q3 2024 addresses these by automating "
            "the annotation step, reducing error rates to 2.3%.\n\n"
            "Section 4: Results\n"
            "Using the methodology described above, we processed 10,000 records."
        ),
        "chunk_text": (
            "As noted above, the previous approach had significant limitations. "
            "The updated methodology introduced in Q3 2024 addresses these by automating "
            "the annotation step, reducing error rates to 2.3%."
        ),
    },
]


# ---------------------------------------------------------------------------
# Pattern 1: Parent-Document Retrieval
# ---------------------------------------------------------------------------

@dataclass
class ParentChunk:
    parent_id: str
    source: str
    text: str
    section: Optional[str] = None


@dataclass
class ChildChunk:
    child_id: str
    parent_id: str
    text: str
    embedding: Optional[np.ndarray] = field(default=None, repr=False)


class ParentDocRetriever:
    """
    Index small child chunks for precise retrieval.
    Return parent (larger) chunks to the LLM.

    The key insight: retrieval precision comes from small chunks;
    generation quality comes from large context. Separate the two.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.parents: dict[str, ParentChunk] = {}
        self.children: list[ChildChunk] = []

    def _split_into_children(
        self, text: str, child_size: int = 100, overlap: int = 15
    ) -> list[str]:
        """Split text into overlapping word-based windows."""
        words = text.split()
        children = []
        start = 0
        while start < len(words):
            children.append(" ".join(words[start: start + child_size]))
            start += child_size - overlap
        return [c for c in children if c.strip()]

    def add_document(
        self,
        parent_text: str,
        source: str,
        section: Optional[str] = None,
        child_size: int = 100,
    ) -> str:
        """
        Register a parent chunk, split into children, embed children.
        Returns parent_id.
        """
        parent_id = str(uuid.uuid4())[:8]
        self.parents[parent_id] = ParentChunk(
            parent_id=parent_id,
            source=source,
            text=parent_text,
            section=section,
        )

        child_texts = self._split_into_children(parent_text, child_size)
        if not child_texts:
            return parent_id

        embeddings = self.model.encode(child_texts, normalize_embeddings=True)
        for i, (text, emb) in enumerate(zip(child_texts, embeddings)):
            self.children.append(ChildChunk(
                child_id=f"{parent_id}-c{i}",
                parent_id=parent_id,
                text=text,
                embedding=emb,
            ))

        return parent_id

    def retrieve(self, query: str, top_k: int = 3) -> list[ParentChunk]:
        """
        Score all child chunks by cosine similarity to the query.
        Deduplicate by parent_id and return parent chunks.
        """
        if not self.children:
            return []

        query_emb = self.model.encode([query], normalize_embeddings=True)[0]
        child_embs = np.stack([c.embedding for c in self.children])
        scores = child_embs @ query_emb

        ranked = sorted(
            zip(scores.tolist(), self.children),
            key=lambda x: x[0],
            reverse=True,
        )

        seen_parents: set[str] = set()
        results: list[ParentChunk] = []
        for score, child in ranked:
            if child.parent_id not in seen_parents:
                seen_parents.add(child.parent_id)
                results.append(self.parents[child.parent_id])
            if len(results) >= top_k:
                break

        return results

    def stats(self) -> dict:
        return {
            "num_parents": len(self.parents),
            "num_children": len(self.children),
            "avg_children_per_parent": (
                len(self.children) / len(self.parents) if self.parents else 0
            ),
        }


# ---------------------------------------------------------------------------
# Pattern 2: Multi-Vector Indexing
# ---------------------------------------------------------------------------

@dataclass
class MultiVectorDoc:
    doc_id: str
    source: str
    full_text: str
    summary: str = ""
    embeddings: dict = field(default_factory=dict, repr=False)


class MultiVectorRetriever:
    """
    Index multiple representations per document: full text + LLM-generated summary.
    Retrieve by any representation, return the full document.

    Why: a conceptual query ("what does this paper claim about attention?") may
    match the summary better than the raw dense chunk.
    """

    def __init__(
        self,
        embed_model: str = "all-MiniLM-L6-v2",
        llm_model: str = "gpt-4o-mini",
    ):
        self.embed_model = SentenceTransformer(embed_model)
        self.llm_model = llm_model
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.docs: dict[str, MultiVectorDoc] = {}
        # Each entry: (doc_id, representation_type, embedding)
        self._index: list[tuple[str, str, np.ndarray]] = []

    def _generate_summary(self, text: str) -> str:
        """LLM-generated 2-3 sentence summary for indexing as a second representation."""
        resp = self.client.chat.completions.create(
            model=self.llm_model,
            messages=[{"role": "user", "content": (
                "Summarize the following in 2-3 sentences, focusing on the main claim.\n\n"
                f"{text}"
            )}],
            temperature=0.0,
            max_tokens=100,
        )
        return resp.choices[0].message.content.strip()

    def add_document(self, text: str, source: str) -> str:
        """
        Add document. Generate summary. Embed both full text and summary.
        Both go into the search index; both point back to this document.
        """
        doc_id = str(uuid.uuid4())[:8]
        summary = self._generate_summary(text)

        doc = MultiVectorDoc(doc_id=doc_id, source=source, full_text=text, summary=summary)
        full_emb = self.embed_model.encode([text], normalize_embeddings=True)[0]
        summary_emb = self.embed_model.encode([summary], normalize_embeddings=True)[0]
        doc.embeddings = {"full_text": full_emb, "summary": summary_emb}

        self.docs[doc_id] = doc
        self._index.append((doc_id, "full_text", full_emb))
        self._index.append((doc_id, "summary", summary_emb))

        print(f"  Added doc {doc_id} from {source}")
        print(f"  Summary: {summary[:100]}...")

        return doc_id

    def retrieve(self, query: str, top_k: int = 3) -> list[MultiVectorDoc]:
        """Score all indexed representations. Deduplicate. Return full documents."""
        if not self._index:
            return []

        query_emb = self.embed_model.encode([query], normalize_embeddings=True)[0]
        all_embs = np.stack([emb for _, _, emb in self._index])
        scores = all_embs @ query_emb

        ranked = sorted(
            zip(scores.tolist(), self._index),
            key=lambda x: x[0],
            reverse=True,
        )

        seen: set[str] = set()
        results: list[MultiVectorDoc] = []
        for score, (doc_id, rep_type, _) in ranked:
            if doc_id not in seen:
                seen.add(doc_id)
                doc = self.docs[doc_id]
                results.append(doc)
                print(f"  Match via '{rep_type}' (score={score:.3f}): {doc.source}")
            if len(results) >= top_k:
                break

        return results


# ---------------------------------------------------------------------------
# Pattern 3: Contextual Retrieval
# ---------------------------------------------------------------------------

CONTEXT_PROMPT = (
    "Here is a document:\n"
    "<document>\n"
    "{full_document}\n"
    "</document>\n\n"
    "Here is a chunk from this document:\n"
    "<chunk>\n"
    "{chunk_text}\n"
    "</chunk>\n\n"
    "Write 1-2 sentences that:\n"
    "1. Describe where this chunk appears in the document (section, position, topic)\n"
    "2. State what broader concept or argument it belongs to\n\n"
    "Write only the context sentences. Do not repeat chunk text. Do not add headers."
)


def contextualize_chunk(
    chunk_text: str,
    full_document: str,
    client: OpenAI,
    model: str = "gpt-4o-mini",
) -> str:
    """
    Prepend a LLM-generated context sentence to the chunk.
    This is Anthropic's Contextual Retrieval (Sept 2024).
    Run once per chunk at index time — zero added retrieval latency.
    """
    prompt = CONTEXT_PROMPT.format(
        full_document=full_document[:3000],  # Trim for token budget
        chunk_text=chunk_text,
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=80,
    )
    context_sentence = resp.choices[0].message.content.strip()
    return f"{context_sentence}\n\n{chunk_text}"


class ContextualRetriever:
    """
    Retriever that enriches each chunk with a context sentence before indexing.
    Reduces retrieval failure on orphaned chunks, pronoun references, and section-relative text.
    """

    def __init__(
        self,
        embed_model: str = "all-MiniLM-L6-v2",
        llm_model: str = "gpt-4o-mini",
    ):
        self.embed_model = SentenceTransformer(embed_model)
        self.llm_model = llm_model
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.chunks: list[dict] = []

    def add_document(
        self,
        full_document: str,
        chunks: list[str],
        source: str,
        use_context: bool = True,
    ) -> None:
        """
        Add chunks with optional contextual enrichment.
        Set use_context=False to compare naive vs contextual retrieval.
        """
        for i, raw_chunk in enumerate(chunks):
            if use_context:
                enriched = contextualize_chunk(
                    raw_chunk, full_document, self.client, self.llm_model
                )
            else:
                enriched = raw_chunk

            emb = self.embed_model.encode([enriched], normalize_embeddings=True)[0]
            self.chunks.append({
                "chunk_id": f"{source}-{i}",
                "source": source,
                "raw_text": raw_chunk,
                "enriched_text": enriched,
                "embedding": emb,
                "contextualized": use_context,
            })

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        """Standard cosine similarity retrieval over contextualized chunk embeddings."""
        if not self.chunks:
            return []

        query_emb = self.embed_model.encode([query], normalize_embeddings=True)[0]
        all_embs = np.stack([c["embedding"] for c in self.chunks])
        scores = all_embs @ query_emb

        ranked = sorted(
            zip(scores.tolist(), self.chunks),
            key=lambda x: x[0],
            reverse=True,
        )[:top_k]

        return [c for _, c in ranked]


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def demo_parent_doc():
    print("\n" + "=" * 64)
    print("PATTERN 1: Parent-Document Retrieval")
    print("=" * 64)

    retriever = ParentDocRetriever()
    for doc in SAMPLE_DOCUMENTS:
        retriever.add_document(
            parent_text=doc["text"],
            source=doc["source"],
            section=doc["section"],
        )

    print(f"Index stats: {retriever.stats()}")

    queries = [
        "What was the conclusion of the board's risk assessment?",
        "How are embedding models trained?",
        "What is the optimal alpha weight for hybrid retrieval?",
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        results = retriever.retrieve(query, top_k=2)
        for r in results:
            word_count = len(r.text.split())
            print(f"  Source: {r.source} | Section: {r.section} | Words: {word_count}")
            print(f"  Text: {r.text[:150]}...")


def demo_multi_vector():
    print("\n" + "=" * 64)
    print("PATTERN 2: Multi-Vector Indexing")
    print("=" * 64)

    retriever = MultiVectorRetriever()

    print("\nIndexing documents (generating summaries)...")
    for doc in SAMPLE_DOCUMENTS:
        retriever.add_document(text=doc["text"], source=doc["source"])

    print("\n--- Retrieval ---")
    # Conceptual query likely to match summary better than raw text
    conceptual_queries = [
        "What does the research say about combining retrieval methods?",
        "How do language models learn to represent meaning?",
    ]

    for query in conceptual_queries:
        print(f"\nQuery: {query}")
        results = retriever.retrieve(query, top_k=2)
        for r in results:
            print(f"  Source: {r.source}")
            print(f"  Summary: {r.summary}")


def demo_contextual_retrieval():
    print("\n" + "=" * 64)
    print("PATTERN 3: Contextual Retrieval")
    print("=" * 64)

    example = ORPHANED_CHUNKS[0]

    # Naive retrieval — chunk without context
    naive_retriever = ContextualRetriever()
    naive_retriever.add_document(
        full_document=example["full_document"],
        chunks=[example["chunk_text"]],
        source=example["source"],
        use_context=False,
    )

    # Contextual retrieval — chunk with prepended context
    contextual_retriever = ContextualRetriever()
    contextual_retriever.add_document(
        full_document=example["full_document"],
        chunks=[example["chunk_text"]],
        source=example["source"],
        use_context=True,
    )

    # Show the difference
    print("\nOriginal chunk (orphaned reference):")
    print(f"  {example['chunk_text'][:200]}")

    if contextual_retriever.chunks:
        enriched = contextual_retriever.chunks[0]["enriched_text"]
        print(f"\nContextualized chunk:")
        print(f"  {enriched[:400]}")

    # Test retrieval
    queries = [
        "What limitations did the previous methodology have?",
        "What changed in Q3 2024 regarding the annotation process?",
    ]

    for query in queries:
        print(f"\nQuery: {query}")

        naive_result = naive_retriever.retrieve(query, top_k=1)
        ctx_result = contextual_retriever.retrieve(query, top_k=1)

        print(f"  Naive chunk (first 150 chars):  {naive_result[0]['raw_text'][:150] if naive_result else 'N/A'}")
        print(f"  Context chunk (first 150 chars): {ctx_result[0]['enriched_text'][:150] if ctx_result else 'N/A'}")


def compare_patterns():
    """Show which pattern to use for which symptom."""
    print("\n" + "=" * 64)
    print("PATTERN SELECTION GUIDE")
    print("=" * 64)

    comparison_table = [
        ("Answers are truncated or miss surrounding context", "Parent-Document Retrieval"),
        ("Poor recall on paraphrase or conceptual queries", "Multi-Vector Indexing"),
        ("Chunks contain pronouns/references (as described above)", "Contextual Retrieval"),
        ("Long structured documents (reports, papers)", "Contextual Retrieval + Parent-Doc"),
        ("Short precise queries over technical documents", "Parent-Document Retrieval"),
        ("Multi-domain corpus with varied terminology", "Multi-Vector (with summaries)"),
    ]

    print(f"\n{'Symptom':<52} {'Recommended Pattern'}")
    print("-" * 80)
    for symptom, pattern in comparison_table:
        print(f"  {symptom:<50} {pattern}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Lesson 11: Advanced RAG")
    print("=" * 64)
    print("Three patterns for when naive RAG breaks:\n")
    print("  1. Parent-Document Retrieval")
    print("  2. Multi-Vector Indexing")
    print("  3. Contextual Retrieval (Anthropic)")

    demo_parent_doc()
    demo_multi_vector()
    demo_contextual_retrieval()
    compare_patterns()

    print("\n" + "=" * 64)
    print("Done. Use the RAG Triad from Lesson 10 to measure improvement.")


if __name__ == "__main__":
    main()
