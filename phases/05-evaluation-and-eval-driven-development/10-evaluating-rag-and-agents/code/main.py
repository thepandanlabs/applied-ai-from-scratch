"""
Lesson 10: Evaluating RAG, Agents, and Multi-Step Systems
Phase 05: Evaluation & Eval-Driven Development

Demonstrates:
- eval_retrieval: precision@k and recall@k for retrieved chunks
- eval_faithfulness: sentence-level grounding check (overlap-based)
- eval_answer_relevance: LLM judge for question-answer relevance
- eval_trajectory: exact match, tool coverage, order score, extra calls
- eval_termination: did the agent stop at the right step?
- demo: run all evals on example RAG trace and agent trace

Run:
    uv run main.py

Requires: ANTHROPIC_API_KEY
"""

import json
import re
from anthropic import Anthropic

client = Anthropic()


# ---------------------------------------------------------------------------
# RAG Component Eval 1: Context Relevance (Retrieval Quality)
# ---------------------------------------------------------------------------

def eval_retrieval(
    question: str,
    retrieved_chunks: list[str],
    relevant_chunks: list[str],
    overlap_threshold: float = 0.5,
) -> dict:
    """
    Precision@k: what fraction of retrieved chunks are relevant?
    Recall@k: what fraction of relevant chunks were retrieved?

    Relevance is determined by word overlap with ground-truth relevant chunks.
    In production, replace with embedding cosine similarity.

    Args:
        question: the user query (used for context; not scored here)
        retrieved_chunks: chunks your retriever returned
        relevant_chunks: ground-truth chunks that should have been returned
        overlap_threshold: minimum word overlap fraction to count as relevant

    Returns:
        {"precision_at_k": float, "recall_at_k": float, "k": int, ...}
    """
    def is_relevant(chunk: str, ground_truth: list[str]) -> bool:
        for ref in ground_truth:
            words_chunk = set(chunk.lower().split())
            words_ref = set(ref.lower().split())
            if not words_ref:
                continue
            overlap = len(words_chunk & words_ref) / len(words_ref)
            if overlap >= overlap_threshold:
                return True
        return False

    k = len(retrieved_chunks)
    relevant_retrieved = sum(1 for c in retrieved_chunks if is_relevant(c, relevant_chunks))

    precision_at_k = relevant_retrieved / k if k > 0 else 0.0
    recall_at_k = relevant_retrieved / len(relevant_chunks) if relevant_chunks else 0.0

    return {
        "precision_at_k": round(precision_at_k, 3),
        "recall_at_k": round(recall_at_k, 3),
        "k": k,
        "relevant_retrieved": relevant_retrieved,
        "total_relevant": len(relevant_chunks),
    }


# ---------------------------------------------------------------------------
# RAG Component Eval 2: Faithfulness (Generation Grounded in Chunks?)
# ---------------------------------------------------------------------------

def eval_faithfulness(answer: str, retrieved_chunks: list[str]) -> dict:
    """
    Approximate faithfulness: what fraction of answer sentences have
    substantial word overlap with the retrieved context?

    This is a fast, model-free approximation. For production accuracy,
    use RAGAS's faithfulness metric, which uses an LLM to extract claims
    and verify each against the context.

    Returns:
        {"faithfulness": float, "grounded_sentences": int, "total_sentences": int}
    """
    combined_context = " ".join(retrieved_chunks).lower()
    context_words = set(combined_context.split())

    sentences = [s.strip() for s in re.split(r"[.!?]", answer) if s.strip()]
    if not sentences:
        return {"faithfulness": 0.0, "grounded_sentences": 0, "total_sentences": 0}

    grounded = 0
    for sentence in sentences:
        words = set(sentence.lower().split())
        # Focus on content words (length > 4 as a stopword proxy)
        content_words = {w for w in words if len(w) > 4}
        if not content_words:
            # Treat pure stopword sentences as neutral (do not penalize)
            grounded += 1
            continue
        overlap = len(content_words & context_words) / len(content_words)
        if overlap >= 0.4:
            grounded += 1

    faithfulness = grounded / len(sentences)
    return {
        "faithfulness": round(faithfulness, 3),
        "grounded_sentences": grounded,
        "total_sentences": len(sentences),
    }


# ---------------------------------------------------------------------------
# RAG Component Eval 3: Answer Relevance (Addresses the Question?)
# ---------------------------------------------------------------------------

def eval_answer_relevance(question: str, answer: str) -> dict:
    """
    LLM judge: does this answer address the original question?
    Scale: 0.0 (off-topic) to 1.0 (fully addresses).

    Returns:
        {"answer_relevance": float, "reasoning": str}
    """
    prompt = f"""Does the following answer address the question asked?

Question: {question}

Answer: {answer}

Rate on a scale of 0 to 1:
- 1.0: Fully addresses the question
- 0.7: Partially addresses it, missing key aspects
- 0.3: Tangentially related but does not answer the question
- 0.0: Completely off-topic or refuses to answer

Respond with JSON only:
{{"score": <float between 0.0 and 1.0>, "reasoning": "<one sentence>"}}"""

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]

    result = json.loads(text.strip())
    return {
        "answer_relevance": round(float(result["score"]), 3),
        "reasoning": result["reasoning"],
    }


# ---------------------------------------------------------------------------
# Agent Eval 4: Trajectory Eval
# ---------------------------------------------------------------------------

def _lcs_length(a: list, b: list) -> int:
    """Longest common subsequence length."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def eval_trajectory(
    expected_tools: list[str],
    actual_tools: list[str],
) -> dict:
    """
    Compare expected vs actual agent tool call sequences.

    Metrics:
    - exact_match: 1.0 if sequences are identical
    - tool_coverage: fraction of expected tools that appear anywhere in actual
    - order_score: LCS / len(expected) -- right tools in right order
    - extra_calls: number of calls beyond the expected sequence length

    Returns:
        {"exact_match": float, "tool_coverage": float, "order_score": float, "extra_calls": int}
    """
    exact = 1.0 if expected_tools == actual_tools else 0.0

    # Coverage: which expected tools appeared at all?
    actual_set = set(actual_tools)
    coverage = (
        sum(1 for t in expected_tools if t in actual_set) / len(expected_tools)
        if expected_tools
        else 0.0
    )

    # Order score: LCS / expected length
    lcs = _lcs_length(expected_tools, actual_tools)
    order_score = lcs / len(expected_tools) if expected_tools else 0.0

    extra_calls = max(0, len(actual_tools) - len(expected_tools))

    return {
        "exact_match": exact,
        "tool_coverage": round(coverage, 3),
        "order_score": round(order_score, 3),
        "extra_calls": extra_calls,
    }


# ---------------------------------------------------------------------------
# Agent Eval 5: Termination Eval
# ---------------------------------------------------------------------------

def eval_termination(
    trace: list[dict],
    should_have_stopped_at: int,
) -> dict:
    """
    Did the agent stop at the right step?

    trace: list of {"type": "tool_call"|"final_answer", "tool": str, ...}
    should_have_stopped_at: 1-indexed expected step for final_answer

    Termination outcomes:
    - correct: stopped at the expected step (score 1.0)
    - too_early: stopped before the expected step (score 0.5)
    - looped: ran past the expected step (score 0.3)
    - never_stopped: no final_answer in trace (score 0.0)

    Returns:
        {"termination": str, "score": float, ...}
    """
    final_answer_at = None
    for i, step in enumerate(trace):
        if step.get("type") == "final_answer":
            final_answer_at = i + 1  # 1-indexed
            break

    if final_answer_at is None:
        return {"termination": "never_stopped", "score": 0.0, "steps": len(trace)}
    elif final_answer_at < should_have_stopped_at:
        return {
            "termination": "too_early",
            "score": 0.5,
            "actual_step": final_answer_at,
            "expected_step": should_have_stopped_at,
        }
    elif final_answer_at == should_have_stopped_at:
        return {"termination": "correct", "score": 1.0, "actual_step": final_answer_at}
    else:
        return {
            "termination": "looped",
            "score": 0.3,
            "actual_step": final_answer_at,
            "expected_step": should_have_stopped_at,
        }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo():
    print("=" * 60)
    print("MULTI-STEP EVAL DEMO")
    print("=" * 60)

    # --- RAG Trace ---
    question = "What is the capital of the Roman Empire?"
    retrieved_chunks = [
        "Rome was the capital of the Roman Empire from its founding until 286 AD.",
        "The Roman Empire covered much of Europe, North Africa, and the Middle East.",
        "Constantinople became the eastern capital in 330 AD under Constantine.",
    ]
    relevant_chunks = [
        "Rome was the capital of the Roman Empire from its founding until 286 AD.",
        "Constantinople became the eastern capital in 330 AD under Constantine.",
    ]
    good_answer = (
        "The capital of the Roman Empire was Rome. "
        "Later, Constantinople became the eastern capital in 330 AD under Emperor Constantine."
    )
    hallucinated_answer = (
        "The capital was Alexandria, which served as the administrative center. "
        "Athens was also important as a cultural hub during this period."
    )

    print("\n--- RAG Component Evals ---")
    print(f"Question: {question}")

    retrieval_result = eval_retrieval(question, retrieved_chunks, relevant_chunks)
    print(f"\nRetrieval (context relevance):")
    print(f"  precision@{retrieval_result['k']}: {retrieval_result['precision_at_k']:.2f}")
    print(f"  recall@{retrieval_result['k']}:    {retrieval_result['recall_at_k']:.2f}")
    print(f"  {retrieval_result['relevant_retrieved']}/{retrieval_result['k']} retrieved chunks were relevant")

    faith_good = eval_faithfulness(good_answer, retrieved_chunks)
    faith_bad = eval_faithfulness(hallucinated_answer, retrieved_chunks)
    print(f"\nFaithfulness (grounded in context):")
    print(f"  Good answer:         {faith_good['faithfulness']:.2f}  ({faith_good['grounded_sentences']}/{faith_good['total_sentences']} sentences)")
    print(f"  Hallucinated answer: {faith_bad['faithfulness']:.2f}  ({faith_bad['grounded_sentences']}/{faith_bad['total_sentences']} sentences)")

    print("\nAnswer Relevance (addresses the question):")
    rel_good = eval_answer_relevance(question, good_answer)
    rel_bad = eval_answer_relevance(question, hallucinated_answer)
    print(f"  Good answer:         {rel_good['answer_relevance']:.2f}  - {rel_good['reasoning']}")
    print(f"  Hallucinated answer: {rel_bad['answer_relevance']:.2f}  - {rel_bad['reasoning']}")

    print("\n--- RAG Triad Summary ---")
    print(f"  context_relevance:  {retrieval_result['precision_at_k']:.2f} (precision)")
    print(f"  faithfulness:       {faith_good['faithfulness']:.2f} (good answer)")
    print(f"  answer_relevance:   {rel_good['answer_relevance']:.2f} (good answer)")

    # --- Agent Trajectory ---
    print("\n--- Agent Trajectory Evals ---")
    expected = ["search_knowledge_base", "read_document", "summarize"]

    traces = {
        "correct":     ["search_knowledge_base", "read_document", "summarize"],
        "wrong_order": ["read_document", "search_knowledge_base", "summarize"],
        "extra_call":  ["search_knowledge_base", "search_knowledge_base", "read_document", "summarize"],
        "missing_tool":["search_knowledge_base", "summarize"],
    }

    print(f"  Expected: {expected}")
    print()
    for label, actual in traces.items():
        result = eval_trajectory(expected, actual)
        print(f"  {label:<15}: exact={result['exact_match']}  coverage={result['tool_coverage']}  order={result['order_score']}  extra={result['extra_calls']}")
        print(f"    actual: {actual}")

    # --- Termination ---
    print("\n--- Termination Evals ---")
    test_traces = {
        "correct_stop": [
            {"type": "tool_call", "tool": "search"},
            {"type": "tool_call", "tool": "read"},
            {"type": "final_answer", "content": "The answer..."},
        ],
        "too_early": [
            {"type": "tool_call", "tool": "search"},
            {"type": "final_answer", "content": "I think..."},
            {"type": "tool_call", "tool": "read"},
        ],
        "looping": [
            {"type": "tool_call", "tool": "search"},
            {"type": "tool_call", "tool": "search"},
            {"type": "tool_call", "tool": "search"},
            {"type": "tool_call", "tool": "search"},
            {"type": "final_answer", "content": "After much searching..."},
        ],
        "never_stops": [
            {"type": "tool_call", "tool": "search"},
            {"type": "tool_call", "tool": "search"},
            {"type": "tool_call", "tool": "search"},
        ],
    }

    for label, trace in test_traces.items():
        result = eval_termination(trace, should_have_stopped_at=3)
        print(f"  {label:<15}: outcome={result['termination']:<15}  score={result['score']}")


if __name__ == "__main__":
    demo()
