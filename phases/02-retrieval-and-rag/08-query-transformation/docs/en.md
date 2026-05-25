# Query Transformation

> The query your user types is rarely the best query for retrieval. Transform it before you search.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lesson 05 (naive RAG), Lesson 06 (retrieval metrics)
**Time:** ~50 minutes
**Phase:** 02 · Retrieval & RAG

---

## Learning Objectives

- Explain why the raw user query is a poor retrieval query in most production systems
- Implement four query transformation techniques: rewriting, HyDE, step-back prompting, and multi-query
- Know when to apply each technique and when transformation adds cost without benefit
- Measure the recall improvement from transformation on a test set

---

## The Problem

Consider a medical documentation system. A doctor asks: "is aspirin safe after a bleed?" The document that answers this question contains the phrase "salicylates are contraindicated following hemorrhagic events." The embedding similarity between the doctor's query and the relevant passage is low: the vocabularies are different, the phrasing is clinical vs. colloquial, and the passage addresses a more general concept than the specific question asks.

The naive RAG system from Lesson 05 embeds the raw query and searches for the closest chunk. It retrieves chunks about aspirin's anti-platelet effects, dosage guidelines, and drug interactions: all technically related, all missing the specific fact the doctor needs. The answer the system produces is evasive and incomplete. The doctor does not know if the system failed or if the answer genuinely is not in the corpus.

This is a retrieval vocabulary problem, and it is endemic to real systems. Users write queries in their own words. Documents are written by different people in a different context. Embedding models capture some of this gap, but they cannot bridge all of it: especially for short, colloquial, or highly specific queries. The fix is not a better embedding model. The fix is to transform the query into something that retrieves better before it ever hits the vector store.

---

## The Concept

### Why Raw Queries Are Poor Retrieval Queries

| Problem | Example | Effect |
|---------|---------|--------|
| Too short, too little context | "authentication timeout" | Embedding is underspecified; retrieves many vague matches |
| Different vocabulary than the document | "is it safe" vs "contraindicated" | Low cosine similarity despite semantic equivalence |
| Personal pronouns and implicit context | "how do I fix the error I got?" | Embedding encodes pronouns rather than the actual question |
| Over-specified, misses broader context | "CVE-2024-41110 in libssl 3.2.1" | Very specific query misses the more general relevant section |
| Ambiguous | "Python environment setup" | Could mean virtualenv, conda, or IDE configuration |

### Four Techniques

**Query Rewriting** is the simplest technique. You ask an LLM to rephrase the user's question as a better retrieval query: more specific, expanded vocabulary, without pronouns or ambiguous references. It works for most cases.

**HyDE (Hypothetical Document Embeddings)** is based on a counterintuitive insight: when you embed the question "what is the capital of France?", the resulting vector occupies a different part of embedding space than the document text "Paris is the capital of France." Questions and answers have different linguistic patterns. Instead of embedding the question, HyDE asks the LLM to generate a hypothetical answer: a plausible document that would answer the question: and embeds that instead. The hypothetical answer lives in the same part of embedding space as real answers.

**Step-Back Prompting** addresses the over-specification problem. When a user asks about a specific drug-dose interaction, the relevant context is often at a higher level of abstraction: the drug class's mechanism of action, or general contraindication rules. Step-back generates a more general version of the query that retrieves the background context needed to answer the specific question.

**Multi-Query** generates N different phrasings of the same question, retrieves for each, deduplicates, and merges. It trades latency and LLM compute for higher recall. Useful for vague or ambiguous queries where the correct phrasing is unknown.

### Technique Selection Guide

```
Is the query clear and specific enough?
  ├─ NO (vague, short, pronoun-heavy) ──► Query Rewriting (always try first)
  └─ YES
       │
       Is the document vocabulary very different from query vocabulary?
       ├─ YES (academic→informal, clinical→colloquial) ──► HyDE
       └─ NO
            │
            Is the question very specific but the relevant context is broader?
            ├─ YES (specific drug → drug class context) ──► Step-Back
            └─ NO
                 │
                 Is the query ambiguous or could be interpreted multiple ways?
                 ├─ YES ──► Multi-Query
                 └─ NO ──► No transformation needed
```

### When NOT to Transform

| Scenario | Why to skip transformation |
|----------|--------------------------|
| Query is already very precise | Adding words can introduce hallucinated terms that hurt retrieval |
| Very low latency required (< 50ms) | Each LLM call adds 200-500ms |
| Corpus and query vocabulary match well | Transformation adds cost with no recall improvement |
| HyDE generates confidently wrong content | The hypothetical answer embeds toward wrong documents |
| Multi-query on a tiny corpus | Deduplication returns same results anyway |

---

## Build It

### Step 1: Setup

```python
# pip install openai numpy
# Set environment variable: OPENAI_API_KEY=sk-...

import os
import hashlib
from typing import Any

import numpy as np
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"
```

### Step 2: Shared Utilities

```python
def embed(texts: list[str]) -> list[list[float]]:
    """Batch embed a list of texts."""
    if not texts:
        return []
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in response.data]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def llm_call(system: str, user: str, temperature: float = 0.3) -> str:
    """Single LLM call. Returns the text content."""
    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()
```

### Step 3: Technique 1: Query Rewriting

```python
REWRITE_SYSTEM = """You are a retrieval query optimizer. Your job is to rewrite a user's question
into a more effective retrieval query. Rules:
- Expand abbreviations and acronyms
- Replace pronouns with explicit nouns
- Add synonyms or related terms that might appear in relevant documents
- Remove filler words and conversational phrasing
- Make the query specific and concrete
- Return ONLY the rewritten query, nothing else."""


def rewrite_query(query: str) -> str:
    """
    Rewrite a user query to be more effective for retrieval.

    This is the simplest transformation and should be your default starting point.
    It costs one LLM call (~200ms) and typically improves recall by 5-15%
    on conversational or informal queries.

    Example:
      Input:  "how do I fix the auth error I kept getting yesterday?"
      Output: "authentication error troubleshooting OAuth JWT token validation failure"
    """
    rewritten = llm_call(
        system=REWRITE_SYSTEM,
        user=f"Original query: {query}\n\nRewritten query:",
        temperature=0.1,  # low temperature for consistent rewriting
    )
    return rewritten
```

### Step 4: Technique 2: HyDE (Hypothetical Document Embeddings)

```python
HYDE_SYSTEM = """You are a knowledgeable assistant. Your task is to write a hypothetical document
passage that would directly answer the given question.

Write as if you are the author of the relevant documentation or knowledge base.
Be specific, use the technical vocabulary that would appear in relevant source documents.
Write 2-3 sentences. Do not acknowledge uncertainty: write as a confident excerpt.
Do not say "In this passage" or "This document explains": just write the content directly."""


def hyde_query(query: str) -> tuple[str, list[float]]:
    """
    HyDE: Generate a hypothetical answer, embed it instead of the question.

    The insight: "what does the answer look like?" embeds closer to actual answers
    than the question itself does.

    Questions and answers occupy different regions of embedding space:
      Query:    "is aspirin safe after a bleed?"
      HyDE doc: "Aspirin (salicylate) is contraindicated following hemorrhagic events
                 due to its antiplatelet activity. Patients who have experienced
                 intracranial hemorrhage should avoid NSAIDs including aspirin."

    The HyDE document embeds very close to the real document.
    The original query embeds further away.

    Works best when:
    - Document vocabulary is very different from query vocabulary
    - Queries are informal/colloquial, documents are technical/formal
    - Questions are about concepts that have a canonical "textbook" answer

    Risks:
    - The LLM may generate a confidently wrong hypothetical answer
    - The wrong hypothetical embeds toward wrong documents
    - Mitigated by using temperature=0.2 and a strong system prompt
    """
    hypothetical_doc = llm_call(
        system=HYDE_SYSTEM,
        user=f"Question: {query}",
        temperature=0.2,
    )
    # Embed the hypothetical document (not the original query)
    hyde_vector = embed([hypothetical_doc])[0]
    return hypothetical_doc, hyde_vector
```

### Step 5: Technique 3: Step-Back Prompting

```python
STEPBACK_SYSTEM = """You are a retrieval strategist. Your task is to generate a more general,
"step back" version of a specific question.

The step-back question should:
- Ask about the broader concept, principle, or category
- Be general enough to retrieve the background context needed to answer the specific question
- NOT include the specific details from the original question (those come after retrieving context)

Examples:
  Specific: "What is the contraindication of beta blockers for a patient with COPD?"
  Step-back: "What are the general contraindications and precautions for beta blocker use?"

  Specific: "How do I fix a segmentation fault in my recursive Fibonacci implementation?"
  Step-back: "What are common causes of segmentation faults in recursive C programs?"

Return ONLY the step-back question, nothing else."""


def stepback_query(query: str) -> str:
    """
    Step-back prompting: generate a more general version of the query
    to retrieve background context.

    Use this when the user's question is very specific but the relevant context
    is documented at a higher level of abstraction.

    Pattern in RAG: retrieve the step-back query first to get background context,
    then retrieve the original query for specific details, combine both result sets.

    Example workflow:
      query = "dosage adjustment for metformin in CKD stage 3a"
      step_back = "metformin pharmacokinetics and renal dosing guidelines"
      → retrieve both → merge → LLM sees both background and specific context
    """
    return llm_call(
        system=STEPBACK_SYSTEM,
        user=f"Specific question: {query}\n\nStep-back question:",
        temperature=0.2,
    )
```

### Step 6: Technique 4: Multi-Query

```python
MULTIQUERY_SYSTEM = """You are a query generation assistant. Generate {n} different phrasings
of the given question that might retrieve different relevant documents.

Each phrasing should:
- Preserve the core information need
- Use different vocabulary, phrasing, or emphasis
- Approach the question from a different angle

Return exactly {n} queries, one per line, numbered 1. 2. 3. etc.
Do not include explanations or preamble: only the queries."""


def multi_query(query: str, n: int = 3) -> list[str]:
    """
    Generate N different phrasings of the same query.
    Use all N phrasings for retrieval, then deduplicate results.

    Why this works: vague or ambiguous queries may have multiple valid
    interpretations. Generating several phrasings covers more of the
    relevant search space, improving recall.

    Cost: N extra LLM calls (or 1 call that generates N queries),
    plus N extra embedding calls. Latency roughly doubles.

    When to use:
    - Ambiguous queries with multiple valid interpretations
    - Vague queries where the "right" vocabulary is unknown
    - When recall is more important than latency

    When NOT to use:
    - Latency-sensitive applications
    - Precise queries where additional phrasings add noise
    - Very small corpora where deduplication returns the same K results anyway
    """
    prompt = MULTIQUERY_SYSTEM.format(n=n)
    raw_output = llm_call(system=prompt, user=f"Original query: {query}", temperature=0.5)

    queries = []
    for line in raw_output.strip().split("\n"):
        line = line.strip()
        # Remove numbering if present
        if line and line[0].isdigit():
            # "1. query text" → "query text"
            parts = line.split(".", 1)
            if len(parts) == 2:
                line = parts[1].strip()
        if line:
            queries.append(line)

    # Always include the original query
    if query not in queries:
        queries.insert(0, query)

    return queries[:n + 1]  # original + n generated


def deduplicate_chunks(all_chunks: list[dict]) -> list[dict]:
    """
    Deduplicate retrieved chunks by text content hash.
    Multi-query retrieval often returns the same chunk for different query phrasings.
    """
    seen: set[str] = set()
    unique = []
    for chunk in all_chunks:
        chunk_hash = hashlib.md5(chunk["text"].encode()).hexdigest()
        if chunk_hash not in seen:
            seen.add(chunk_hash)
            unique.append(chunk)
    return unique
```

### Step 7: Combining Transformations in a Pipeline

```python
def retrieve_with_transformation(
    query: str,
    retrieval_fn: Any,  # fn(query_text: str, top_k: int) -> list[dict]
    technique: str = "rewrite",
    top_k: int = 5,
    verbose: bool = True,
) -> dict:
    """
    Apply a query transformation technique and retrieve.

    Args:
        query: original user query
        retrieval_fn: your existing retrieve() function from Lesson 05
        technique: "rewrite" | "hyde" | "stepback" | "multi_query" | "none"
        top_k: number of chunks to retrieve

    Returns:
        {
            "original_query": str,
            "transformed_query": str or list[str],
            "retrieved_chunks": list[dict],
            "technique": str,
        }
    """
    if verbose:
        print(f"\nOriginal query: '{query}'")
        print(f"Technique: {technique}")

    if technique == "none":
        chunks = retrieval_fn(query, top_k)
        return {
            "original_query": query,
            "transformed_query": query,
            "retrieved_chunks": chunks,
            "technique": "none",
        }

    elif technique == "rewrite":
        transformed = rewrite_query(query)
        if verbose:
            print(f"Rewritten: '{transformed}'")
        chunks = retrieval_fn(transformed, top_k)

    elif technique == "hyde":
        hypothetical_doc, hyde_vec = hyde_query(query)
        if verbose:
            print(f"HyDE doc: '{hypothetical_doc[:100]}...'")
        # Pass the hypothetical doc text for retrieval (embed internally)
        chunks = retrieval_fn(hypothetical_doc, top_k)
        transformed = hypothetical_doc

    elif technique == "stepback":
        step_back = stepback_query(query)
        if verbose:
            print(f"Step-back: '{step_back}'")
        # Retrieve both the step-back and the original, merge
        stepback_chunks = retrieval_fn(step_back, top_k)
        original_chunks = retrieval_fn(query, top_k)
        chunks = deduplicate_chunks(stepback_chunks + original_chunks)[:top_k]
        transformed = step_back

    elif technique == "multi_query":
        queries = multi_query(query, n=3)
        if verbose:
            print(f"Generated queries: {queries}")
        all_chunks = []
        for q in queries:
            all_chunks.extend(retrieval_fn(q, top_k))
        chunks = deduplicate_chunks(all_chunks)[:top_k * 2]  # more chunks, deduped
        transformed = queries

    else:
        raise ValueError(f"Unknown technique: {technique}")

    return {
        "original_query": query,
        "transformed_query": transformed,
        "retrieved_chunks": chunks,
        "technique": technique,
    }
```

> **Real-world check:** A backend engineer reviewing your PR says: "we're now making an extra LLM call just to rephrase the question before we even start retrieval. That roughly doubles our cost per query. When is that actually worth it, and how would we know if a given query needed it at all?" What is your answer, and is there a way to apply transformation selectively rather than to every query?

### Step 8: Measuring the Impact

```python
def compare_techniques(
    query: str,
    retrieval_fn: Any,
    relevant_texts: list[str],  # ground truth: text snippets that should be retrieved
    top_k: int = 5,
) -> dict:
    """
    Compare all four techniques for a single query.
    Measure: how many relevant texts appear in the retrieved chunks?

    relevant_texts: list of text fragments that a correct answer requires.
    We check if any retrieved chunk contains each fragment (substring match).
    This is a simple recall proxy without requiring exact doc IDs.
    """

    def recall_score(chunks: list[dict], relevant: list[str]) -> float:
        """What fraction of relevant texts are covered by retrieved chunks?"""
        if not relevant:
            return 1.0
        covered = 0
        for text_fragment in relevant:
            if any(text_fragment.lower() in chunk["text"].lower() for chunk in chunks):
                covered += 1
        return covered / len(relevant)

    results = {}
    for technique in ["none", "rewrite", "hyde", "stepback", "multi_query"]:
        result = retrieve_with_transformation(
            query, retrieval_fn, technique=technique, top_k=top_k, verbose=False
        )
        recall = recall_score(result["retrieved_chunks"], relevant_texts)
        results[technique] = {
            "recall": recall,
            "chunks_retrieved": len(result["retrieved_chunks"]),
            "transformed_query": result["transformed_query"],
        }

    return results


def print_comparison(query: str, comparison: dict) -> None:
    print(f"\nQuery: '{query}'")
    print(f"{'Technique':<15}  {'Recall':>8}  {'Chunks':>8}  Transformed query")
    print("-" * 70)
    for technique, metrics in comparison.items():
        tq = metrics["transformed_query"]
        tq_str = str(tq)[:40] + "..." if len(str(tq)) > 40 else str(tq)
        print(
            f"  {technique:<13}  {metrics['recall']:>8.2f}  "
            f"{metrics['chunks_retrieved']:>8}  {tq_str}"
        )
```

### Step 9: Main Entry Point

```python
if __name__ == "__main__":
    # Demo: show each technique's output for example queries.
    # To test with your actual RAG pipeline, replace this stub
    # with your retrieve() function from Lesson 05.

    def stub_retriever(query: str, top_k: int) -> list[dict]:
        """
        Stub retriever for demonstration.
        Replace with your actual retrieve() from Lesson 05:
            from lesson05 import ingest, retrieve
            store = ingest("my_document.txt")
            def my_retriever(query, top_k):
                return retrieve(query, store, top_k=top_k)
        """
        print(f"  [stub] retrieve('{query[:60]}...', top_k={top_k})")
        return [
            {"text": f"Stub result {i} for: {query[:40]}", "score": 0.9 - i * 0.1}
            for i in range(top_k)
        ]

    demo_queries = [
        "is aspirin safe after a bleed?",
        "how do I fix the auth error I keep getting",
        "metformin dose for CKD patient stage 3a",
    ]

    print("=" * 70)
    print("QUERY TRANSFORMATION DEMO")
    print("=" * 70)

    for query in demo_queries:
        print(f"\n{'─'*70}")
        print(f"Original: '{query}'")

        print(f"\n[1] Rewrite:")
        rewritten = rewrite_query(query)
        print(f"    → '{rewritten}'")

        print(f"\n[2] HyDE:")
        hyde_doc, _ = hyde_query(query)
        print(f"    → '{hyde_doc[:120]}...'")

        print(f"\n[3] Step-back:")
        stepback = stepback_query(query)
        print(f"    → '{stepback}'")

        print(f"\n[4] Multi-query:")
        mq = multi_query(query, n=3)
        for i, q in enumerate(mq, 1):
            print(f"    {i}. {q}")

    print("\n\n" + "=" * 70)
    print("USAGE WITH YOUR RAG PIPELINE")
    print("=" * 70)
    print("""
To use with your pipeline from Lesson 05:

    from main import ingest, retrieve

    store = ingest("my_document.txt")

    def my_retriever(query: str, top_k: int) -> list[dict]:
        return retrieve(query, store, top_k=top_k)

    # Use rewrite for most queries:
    result = retrieve_with_transformation(
        "how do I set up authentication?",
        retrieval_fn=my_retriever,
        technique="rewrite",
    )

    # Use HyDE for vocabulary-mismatch domains:
    result = retrieve_with_transformation(
        "is this drug safe for liver patients?",
        retrieval_fn=my_retriever,
        technique="hyde",
    )

    # Use multi-query for vague queries:
    result = retrieve_with_transformation(
        "connection issues",
        retrieval_fn=my_retriever,
        technique="multi_query",
    )

    print(result["retrieved_chunks"])
""")
```

---

## Use It

LangChain provides all four transformations as built-in chains:

```python
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_openai import ChatOpenAI

# Multi-query retriever: generates N queries automatically
retriever = MultiQueryRetriever.from_llm(
    retriever=vectorstore.as_retriever(),
    llm=ChatOpenAI(temperature=0),
)
docs = retriever.get_relevant_documents("how does auth work")
```

For HyDE specifically:

```python
from langchain.chains import HypotheticalDocumentEmbedder
from langchain_openai import OpenAIEmbeddings, ChatOpenAI

embeddings = HypotheticalDocumentEmbedder.from_llm(
    llm=ChatOpenAI(),
    embeddings=OpenAIEmbeddings(),
    chain_type="stuff",
)
result = embeddings.embed_query("what is the capital of France?")
# result is the embedding of a hypothetical answer
```

LlamaIndex has these as `QueryTransformComponent` objects in its query pipeline. The underlying logic is identical to what we built; the framework adds error handling, async support, and integration with its retriever abstractions.

> **Perspective shift:** Your product manager says: "our search works fine for most queries already. We now have four different transformation techniques to choose from. How do we decide which ones to actually deploy versus which ones to skip? What evidence would make you confident enough to ship one of these to production?" What is your decision framework, and what does "good enough evidence" look like?

---

## Ship It

The output for this lesson is the prompt in `outputs/prompt-query-transformer.md`. It advises which transformation to apply given a query and retrieval system type, and provides the actual prompts to use.

The runnable artifact is `code/main.py`:

```bash
export OPENAI_API_KEY=sk-...
python main.py
```

It will demonstrate all four techniques on example queries using a stub retriever. Replace the stub with your `retrieve()` function from Lesson 05 to test on your actual corpus.

---

## Evaluate It

**Check 1: Measure recall before and after.**
Pick 10 queries from your eval set that currently have poor recall@5. Apply query rewriting to each. Compute recall@5 again. If recall improved by 10%+ on these queries, query rewriting is earning its latency cost. If it did not improve, the problem is not query vocabulary: it is chunking, embedding model, or K size.

**Check 2: Test HyDE on vocabulary-mismatch domains.**
HyDE works best when document vocabulary is very different from query vocabulary. Identify 3-5 queries where the relevant document uses technical vocabulary not in the query. Run both plain embedding and HyDE, compare the top-3 retrieved chunks for each. If HyDE retrieves the right passage and plain embedding does not, the hypothesis is confirmed for your domain.

**Check 3: Track latency cost per technique.**
Each transformation requires one or more LLM calls. Measure total query latency:
- Baseline (no transformation): embed + cosine search ≈ 50–100ms
- Query rewrite: +1 LLM call ≈ +200–400ms
- HyDE: +1 LLM call ≈ +200–400ms
- Step-back: +1 LLM call + 2 retrieval calls ≈ +300–500ms
- Multi-query (3 phrasings): +1 LLM call + 3 retrieval calls ≈ +400–600ms

Is the recall gain worth the latency? For a real-time Q&A system, multi-query may be too slow. For an async document research system, the extra 500ms is irrelevant.

---

## Exercises

1. **[Easy]** Log the original query and the rewritten query for 10 real queries from your corpus. Compare the cosine similarity between the query and the relevant passage, before and after rewriting. Does the similarity score improve consistently?

2. **[Medium]** Implement a caching layer for query transformations: if the same query (exact string match) has been transformed before, return the cached result instead of calling the LLM again. Use a simple Python dict. Measure how much this reduces latency in a realistic query session.

3. **[Hard]** Implement a "transformer selector" that automatically chooses the best transformation technique based on query characteristics. Rules to implement: (a) if query length < 5 words → rewrite, (b) if query contains very specific identifiers (regex for codes, versions, model numbers) → no transformation, (c) if query is a question without technical terms → HyDE, (d) otherwise → rewrite. Test it on 20 queries from your eval set. Does automatic selection match what you would choose by hand?

---

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Query transformation | "query expansion," "query augmentation" | Modifying the user's query before retrieval to improve the quality of retrieved results |
| Query rewriting | "query reformulation" | Using an LLM to rephrase a query into better retrieval vocabulary |
| HyDE | "Hypothetical Document Embeddings" | Generating a hypothetical answer and embedding that instead of the question; exploits the fact that answers and documents share vocabulary |
| Step-back prompting | "query abstraction," "level-up prompting" | Generating a more general version of a specific query to retrieve background context |
| Multi-query retrieval | "query expansion," "query diversification" | Generating multiple phrasings of the same query and retrieving for all of them to improve recall |
| Vocabulary mismatch | "lexical gap," "query-document gap" | When the user's natural language query uses different words than the documents that contain the answer |
| OOV | "Out-of-vocabulary" | A term that was not seen during embedding model training; will have a poor embedding representation |

---

## Further Reading

- [HyDE Paper: Precise Zero-Shot Dense Retrieval](https://arxiv.org/abs/2212.10496): Gao et al., 2022; the original HyDE paper; the experimental results show when it helps most
- [Step-Back Prompting Paper](https://arxiv.org/abs/2310.06117): Zheng et al., Google DeepMind; introduces step-back as a RAG technique; includes evaluation across multiple benchmarks
- [Query Expansion in Modern IR](https://dl.acm.org/doi/10.1145/3404835.3463017): SIGIR 2021 tutorial on query expansion; connects classical IR approaches to LLM-based methods
- [RAG Survey](https://arxiv.org/abs/2312.10997): comprehensive survey covering query transformation in context of the full RAG landscape
- [MultiQueryRetriever in LangChain](https://python.langchain.com/docs/how_to/MultiQueryRetriever/): production implementation with logging; shows how multi-query is integrated with existing retrievers
- [FLARE: Forward-Looking Active REtrieval](https://arxiv.org/abs/2305.06983): an advanced technique that generates retrieval queries on-the-fly during generation; the next step beyond these four techniques
