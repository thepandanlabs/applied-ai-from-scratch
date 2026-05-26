# pip install sentence-transformers rank-bm25
# Usage: python main.py
#
# Implements from scratch:
#   (1) BM25 - inverted index, TF-IDF weighting, BM25 formula
#   (2) Dense retrieval - sentence-transformers bi-encoder (local, no API key needed)
#   (3) Reciprocal Rank Fusion - merge ranked lists without score normalization
#   (4) Cross-encoder reranking - precision scoring of top candidates
#
# All components are runnable on CPU. First run downloads models (~100MB total).

import math
import re
from collections import defaultdict
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer, CrossEncoder

# ---------------------------------------------------------------------------
# Sample corpus
# ---------------------------------------------------------------------------
CORPUS = [
    {"id": "doc_1",  "text": "BM25 is a probabilistic ranking function used in information retrieval systems."},
    {"id": "doc_2",  "text": "Dense retrieval uses neural embeddings to find semantically similar documents."},
    {"id": "doc_3",  "text": "Reciprocal rank fusion combines multiple ranked lists without score normalization."},
    {"id": "doc_4",  "text": "The transformer architecture introduced attention mechanisms for sequence modeling."},
    {"id": "doc_5",  "text": "Vector databases store high-dimensional embeddings for approximate nearest neighbor search."},
    {"id": "doc_6",  "text": "TF-IDF weights terms by frequency in the document and rarity across the corpus."},
    {"id": "doc_7",  "text": "Cross-encoders compute relevance scores for query-document pairs jointly."},
    {"id": "doc_8",  "text": "BM25 parameters k1 and b control term frequency saturation and length normalization."},
    {"id": "doc_9",  "text": "Semantic search understands meaning and paraphrase beyond exact keyword matching."},
    {"id": "doc_10", "text": "Hybrid search combines sparse and dense retrieval to improve recall and precision."},
    {"id": "doc_11", "text": "Inverted indexes map terms to the documents that contain them for fast lookup."},
    {"id": "doc_12", "text": "Sentence transformers fine-tune BERT-like models for semantic similarity tasks."},
    {"id": "doc_13", "text": "The k1 parameter in BM25 defaults to 1.5; increasing it rewards higher term frequency."},
    {"id": "doc_14", "text": "pgvector extends PostgreSQL with a vector similarity search column type."},
    {"id": "doc_15", "text": "Reranking improves precision by scoring the top-M candidates with a cross-encoder."},
]

# ---------------------------------------------------------------------------
# Text preprocessing
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    """
    Lowercase + remove punctuation + whitespace split.
    For production, replace with a domain-specific tokenizer:
      - Medical: preserve hyphens in drug names
      - Code: preserve underscores, camelCase split
      - Legal: preserve citation formats
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return [t for t in text.split() if t]

# ---------------------------------------------------------------------------
# Component 1: BM25 from scratch
# ---------------------------------------------------------------------------

class BM25Index:
    """
    BM25 (Okapi BM25) sparse retrieval index.

    Builds an inverted index from a corpus and scores queries using:
        score(q, d) = Σ_t IDF(t) × tf_norm(t, d)

    IDF(t) = log((N - df(t) + 0.5) / (df(t) + 0.5) + 1)
        N      = total documents
        df(t)  = number of documents containing term t
        IDF is high for rare terms (informative), low for common terms (noise)

    tf_norm(t, d) = tf(t,d) × (k1 + 1) / (tf(t,d) + k1 × (1 - b + b × dl/avgdl))
        tf(t,d) = raw term frequency of t in document d
        dl      = document length
        avgdl   = average document length across corpus
        k1      = TF saturation [1.2, 2.0], default 1.5
        b       = length normalization [0, 1], default 0.75

    Parameters:
        k1=1.5: standard default. Increase (→2.0) if TF should matter more.
                Decrease (→1.2) for shorter docs where raw counts are more reliable.
        b=0.75:  standard default. b=0 disables length normalization.
                 b=1.0 fully normalizes. For short fixed-length chunks, try b=0.5.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_ids: list[str] = []
        self.doc_lengths: list[int] = []
        self.avgdl: float = 1.0
        self.N: int = 0
        # inverted_index[term][doc_index] = term_frequency
        self.inverted_index: dict[str, dict[int, int]] = defaultdict(dict)
        self.df: dict[str, int] = {}  # document frequency

    def build(self, documents: list[dict]) -> None:
        """
        Build index from list of {"id": str, "text": str} documents.
        Time complexity: O(total_tokens)
        Space complexity: O(vocabulary_size × avg_docs_per_term)
        """
        self.doc_ids = [doc["id"] for doc in documents]
        tokenized_docs = [tokenize(doc["text"]) for doc in documents]

        self.doc_lengths = [len(tokens) for tokens in tokenized_docs]
        self.N = len(documents)
        self.avgdl = sum(self.doc_lengths) / self.N if self.N > 0 else 1.0

        # Build inverted index: term → {doc_index: count}
        for doc_idx, tokens in enumerate(tokenized_docs):
            term_counts: dict[str, int] = defaultdict(int)
            for token in tokens:
                term_counts[token] += 1
            for term, count in term_counts.items():
                self.inverted_index[term][doc_idx] = count

        self.df = {
            term: len(postings)
            for term, postings in self.inverted_index.items()
        }

        vocab_size = len(self.inverted_index)
        print(f"  BM25 index: {self.N} docs | {vocab_size:,} unique terms | "
              f"avgdl={self.avgdl:.1f} words")

    def _idf(self, term: str) -> float:
        """
        Robertson-Sparck Jones IDF.
        Clipped to 0 for terms that appear in all documents.
        """
        df_t = self.df.get(term, 0)
        return math.log((self.N - df_t + 0.5) / (df_t + 0.5) + 1)

    def _score_doc(self, query_terms: list[str], doc_idx: int) -> float:
        """BM25 score for a single document."""
        dl = self.doc_lengths[doc_idx]
        total = 0.0
        for term in set(query_terms):  # deduplicate
            tf = self.inverted_index.get(term, {}).get(doc_idx, 0)
            if tf == 0:
                continue
            idf = self._idf(term)
            # BM25 TF normalization: saturates at high TF, penalizes long docs
            tf_norm = (tf * (self.k1 + 1)) / (
                tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            )
            total += idf * tf_norm
        return total

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """
        Retrieve top_k documents by BM25 score.
        Only scores candidate documents that contain at least one query term
        (exact matches only - this is the fundamental difference from dense).
        Returns: [{"id": str, "score": float, "rank": int}, ...]
        """
        query_terms = tokenize(query)
        if not query_terms:
            return []

        # Candidate pool: docs containing any query term (union of postings)
        candidates: set[int] = set()
        for term in query_terms:
            candidates.update(self.inverted_index.get(term, {}).keys())

        if not candidates:
            return []  # no exact term overlap - BM25 returns nothing

        scored = [
            {"doc_idx": idx, "score": self._score_doc(query_terms, idx)}
            for idx in candidates
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)

        return [
            {
                "id": self.doc_ids[item["doc_idx"]],
                "score": item["score"],
                "rank": rank + 1,
            }
            for rank, item in enumerate(scored[:top_k])
        ]

# ---------------------------------------------------------------------------
# Component 2: Dense retrieval (sentence-transformers bi-encoder)
# ---------------------------------------------------------------------------

class DenseIndex:
    """
    Dense retrieval using a local sentence-transformer model.

    Uses all-MiniLM-L6-v2: 80MB, fast on CPU, strong semantic understanding.
    Alternative models (slower but better):
      - all-mpnet-base-v2: 420MB, significantly better quality
      - BAAI/bge-base-en-v1.5: 430MB, best open-source bi-encoder as of 2024
    """

    EMBED_MODEL = "all-MiniLM-L6-v2"

    def __init__(self):
        print(f"  Loading dense model: {self.EMBED_MODEL}")
        self.model = SentenceTransformer(self.EMBED_MODEL)
        self.doc_ids: list[str] = []
        self.embeddings: np.ndarray | None = None

    def build(self, documents: list[dict]) -> None:
        """Embed all documents. normalize_embeddings=True → dot product = cosine sim."""
        self.doc_ids = [doc["id"] for doc in documents]
        texts = [doc["text"] for doc in documents]

        self.embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        )
        dim = self.embeddings.shape[1]
        print(f"  Dense index: {len(self.doc_ids)} docs | dim={dim}")

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """Embed query and return top_k by cosine similarity."""
        if self.embeddings is None:
            raise RuntimeError("Call build() before search()")

        q_vec = self.model.encode(
            query, convert_to_numpy=True, normalize_embeddings=True
        )
        # Cosine similarity via dot product (vectors are L2-normalized)
        scores = np.dot(self.embeddings, q_vec)

        k = min(top_k, len(scores))
        top_idxs = np.argpartition(scores, -k)[-k:]
        top_idxs = top_idxs[np.argsort(scores[top_idxs])[::-1]]

        return [
            {
                "id": self.doc_ids[int(idx)],
                "score": float(scores[idx]),
                "rank": rank + 1,
            }
            for rank, idx in enumerate(top_idxs)
        ]

# ---------------------------------------------------------------------------
# Component 3: Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]],
    k: int = 60,
) -> list[dict]:
    """
    Merge N ranked lists using Reciprocal Rank Fusion (RRF).

    For each document, sum 1/(k + rank) across all lists it appears in.
    Documents appearing in multiple lists get additive credit.

    RRF score(doc) = Σ_i 1/(k + rank_i(doc))

    Why k=60?
    The original paper found k=60 works well across a wide range of tasks.
    Smaller k: higher variance, top-ranked docs dominate more.
    Larger k: more uniform fusion, position matters less.

    Why RRF instead of score normalization?
    - BM25 scores are unbounded integers; cosine scores are [0, 1].
    - Min-max normalization is query-dependent and unstable with outliers.
    - RRF is scale-free, stable, and empirically competitive with score fusion.

    Args:
        ranked_lists: each list is [{"id": str, "rank": int, ...}, ...]
        k: RRF constant (default: 60)

    Returns:
        Merged list sorted by RRF score descending, with rank assigned.
    """
    rrf_scores: dict[str, float] = defaultdict(float)

    for ranked_list in ranked_lists:
        for item in ranked_list:
            doc_id = item["id"]
            rank = item["rank"]  # 1-based
            rrf_scores[doc_id] += 1.0 / (k + rank)

    merged = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {"id": doc_id, "rrf_score": score, "rank": rank + 1}
        for rank, (doc_id, score) in enumerate(merged)
    ]

# ---------------------------------------------------------------------------
# Component 4: Cross-encoder reranker
# ---------------------------------------------------------------------------

class CrossEncoderReranker:
    """
    Cross-encoder reranker using ms-marco-MiniLM-L-6-v2.

    Unlike a bi-encoder (which embeds query and doc separately), a cross-encoder
    takes the concatenated (query, doc) pair as input. This lets it model
    the interaction between query terms and document terms - much more
    expressive but O(n) inference cost per query.

    Model output: logit score, higher = more relevant.
    Typical range: -10 to +10.

    Usage pattern:
        1. Retrieve top-50 candidates cheaply (BM25 + dense)
        2. Rerank top-20 candidates with cross-encoder
        3. Return top-5 to the LLM

    This two-stage design keeps latency manageable while getting
    near-oracle ranking quality on the top candidates.
    """

    RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self):
        print(f"  Loading cross-encoder: {self.RERANK_MODEL}")
        self.model = CrossEncoder(self.RERANK_MODEL, max_length=512)

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        corpus: dict[str, str],
        top_k: int = 5,
    ) -> list[dict]:
        """
        Score each (query, doc_text) pair and re-sort by cross-encoder score.
        corpus: {doc_id: doc_text}
        Returns top_k results with cross_encoder_score attached.
        """
        valid = [c for c in candidates if c["id"] in corpus]
        if not valid:
            return candidates[:top_k]

        pairs = [(query, corpus[c["id"]]) for c in valid]
        scores = self.model.predict(pairs)

        reranked = sorted(
            [
                {**cand, "cross_encoder_score": float(score)}
                for cand, score in zip(valid, scores)
            ],
            key=lambda x: x["cross_encoder_score"],
            reverse=True,
        )
        return reranked[:top_k]

# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

class HybridSearchPipeline:
    """
    Two-stage hybrid search:
      Stage 1: BM25 + dense → RRF merge (high recall, lower precision)
      Stage 2: Cross-encoder rerank top candidates (high precision)

    retrieve_k: how many results to get from BM25 and dense individually
    rerank_k: how many merged results to pass to the cross-encoder
    final_k: how many results to return (feeds into LLM context)

    Latency budget (CPU, 15-doc corpus):
      BM25 search: <1ms
      Dense search: ~10ms
      RRF merge: <1ms
      Cross-encoder (10 candidates): ~100-300ms
      Total: ~200-400ms
    """

    def __init__(
        self,
        documents: list[dict],
        retrieve_k: int = 20,
        rerank_k: int = 10,
        final_k: int = 5,
    ):
        self.corpus = {doc["id"]: doc["text"] for doc in documents}
        self.retrieve_k = retrieve_k
        self.rerank_k = rerank_k
        self.final_k = final_k

        print("Building hybrid search pipeline...")
        self.bm25 = BM25Index(k1=1.5, b=0.75)
        self.bm25.build(documents)

        self.dense = DenseIndex()
        self.dense.build(documents)

        self.reranker = CrossEncoderReranker()
        print("Pipeline ready.\n")

    def search_bm25_only(self, query: str, top_k: int | None = None) -> list[dict]:
        k = top_k or self.final_k
        results = self.bm25.search(query, top_k=k)
        for r in results:
            r["text"] = self.corpus.get(r["id"], "")
        return results

    def search_dense_only(self, query: str, top_k: int | None = None) -> list[dict]:
        k = top_k or self.final_k
        results = self.dense.search(query, top_k=k)
        for r in results:
            r["text"] = self.corpus.get(r["id"], "")
        return results

    def search_hybrid(
        self,
        query: str,
        use_reranker: bool = True,
        verbose: bool = False,
    ) -> list[dict]:
        """
        Full hybrid pipeline: BM25 + dense → RRF → (optional) cross-encoder.
        Returns final_k results with text and scores attached.
        """
        # Stage 1: Retrieve from both
        bm25_results = self.bm25.search(query, top_k=self.retrieve_k)
        dense_results = self.dense.search(query, top_k=self.retrieve_k)

        if verbose:
            print(f"  BM25:  {[r['id'] for r in bm25_results[:5]]}")
            print(f"  Dense: {[r['id'] for r in dense_results[:5]]}")

        # Stage 1c: Merge with RRF
        merged = reciprocal_rank_fusion([bm25_results, dense_results])

        if verbose:
            print(f"  RRF:   {[r['id'] for r in merged[:5]]}")

        # Stage 2: Rerank if requested
        if use_reranker:
            candidates = merged[:self.rerank_k]
            final = self.reranker.rerank(query, candidates, self.corpus, top_k=self.final_k)
        else:
            final = merged[:self.final_k]

        # Attach text to all results
        for r in final:
            r["text"] = self.corpus.get(r["id"], "")

        return final

# ---------------------------------------------------------------------------
# Comparison and analysis utilities
# ---------------------------------------------------------------------------

def print_result_row(label: str, results: list[dict]) -> None:
    """Print a single row of the comparison table."""
    ids = [r["id"] for r in results[:3]]
    print(f"  {label:<20} {ids}")


def compare_methods(pipeline: HybridSearchPipeline, queries: list[str]) -> None:
    """
    Side-by-side comparison: BM25-only vs dense-only vs hybrid vs hybrid+rerank.
    This shows you empirically where each method wins.
    """
    print("=" * 70)
    print("METHOD COMPARISON (top-3 results per method)")
    print("=" * 70)

    for query in queries:
        print(f"\nQuery: '{query}'")
        print_result_row("BM25 only:", pipeline.search_bm25_only(query, top_k=3))
        print_result_row("Dense only:", pipeline.search_dense_only(query, top_k=3))

        # Hybrid without reranker
        merged = reciprocal_rank_fusion([
            pipeline.bm25.search(query, top_k=pipeline.retrieve_k),
            pipeline.dense.search(query, top_k=pipeline.retrieve_k),
        ])
        for r in merged:
            r["text"] = pipeline.corpus.get(r["id"], "")
        print_result_row("Hybrid (RRF):", merged[:3])

        # Full pipeline
        full = pipeline.search_hybrid(query, use_reranker=True, verbose=False)
        print_result_row("Hybrid + CE:", full[:3])


def show_bm25_tf_saturation() -> None:
    """
    Visualize how the k1 parameter controls TF saturation.
    Higher k1 = TF contributes more before diminishing returns.
    """
    print("\n" + "=" * 50)
    print("BM25 TF Saturation (b=0.75, dl=avgdl)")
    print("=" * 50)
    print(f"{'TF':>5}  {'k1=1.2':>10}  {'k1=1.5':>10}  {'k1=2.0':>10}")
    print(f"{'─'*5}  {'─'*10}  {'─'*10}  {'─'*10}")

    for tf in [1, 2, 3, 5, 10, 20]:
        row = [f"{tf:>5}"]
        for k1 in [1.2, 1.5, 2.0]:
            # Simplified: dl=avgdl so length term cancels
            tf_norm = (tf * (k1 + 1)) / (tf + k1)
            row.append(f"{tf_norm:>10.3f}")
        print("  ".join(row))

    print("\nObservation: k1=1.2 saturates quickly; k1=2.0 lets TF grow longer.")
    print("For very short fixed-length chunks, k1 matters less than b.")


def demonstrate_rrf() -> None:
    """Walk through RRF calculation by hand for one example."""
    print("\n" + "=" * 50)
    print("RRF Calculation Example (k=60)")
    print("=" * 50)

    # Scenario: doc_3 is rank 3 in BM25 and rank 5 in dense
    # doc_10 is rank 1 in both
    print("\nDocument ranking from each method:")
    print("  BM25 ranking:  [doc_10, doc_8, doc_3, doc_1, doc_6]")
    print("  Dense ranking: [doc_10, doc_2, doc_9, doc_7, doc_3]")

    scenarios = [
        ("doc_10", 1, 1),   # rank 1 in both
        ("doc_3",  3, 5),   # rank 3 in BM25, rank 5 in dense
        ("doc_8",  2, None), # rank 2 in BM25 only
    ]

    k = 60
    print(f"\n{'Doc':<10}  {'BM25 rank':>10}  {'Dense rank':>10}  {'RRF score':>12}")
    print(f"{'─'*10}  {'─'*10}  {'─'*10}  {'─'*12}")

    for doc_id, bm25_rank, dense_rank in scenarios:
        rrf = 1.0 / (k + bm25_rank)
        formula = f"1/(60+{bm25_rank})"
        if dense_rank is not None:
            rrf += 1.0 / (k + dense_rank)
            formula += f" + 1/(60+{dense_rank})"
        print(f"{doc_id:<10}  {bm25_rank:>10}  "
              f"{'N/A' if dense_rank is None else dense_rank:>10}  "
              f"{rrf:>12.5f}  [{formula}]")

    print("\nNote: doc_10 (rank 1 in both) scores ~2x a doc ranked only in one list.")
    print("      This naturally rewards consensus between methods.")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pipeline = HybridSearchPipeline(
        CORPUS,
        retrieve_k=20,
        rerank_k=10,
        final_k=3,
    )

    # Queries designed to test different retrieval method strengths
    test_queries = [
        "How do neural networks understand text meaning?",   # semantic → dense wins
        "BM25 k1 parameter TF saturation",                  # exact terms → BM25 wins
        "combining sparse and dense retrieval methods",      # hybrid should win
        "RRF formula rank fusion",                           # exact terms, BM25 advantage
    ]

    compare_methods(pipeline, test_queries)
    show_bm25_tf_saturation()
    demonstrate_rrf()

    # Full pipeline demo
    print("\n\n" + "=" * 70)
    print("FULL PIPELINE DEMO")
    print("=" * 70)
    demo_query = "combining sparse and dense retrieval methods"
    print(f"\nQuery: '{demo_query}'")
    results = pipeline.search_hybrid(demo_query, use_reranker=True, verbose=True)
    print(f"\nFinal top-{len(results)} results:")
    for i, r in enumerate(results, 1):
        ce_score = r.get("cross_encoder_score", r.get("rrf_score", 0))
        print(f"  [{i}] {r['id']} | score={ce_score:.3f}")
        print(f"       {r['text']}")
