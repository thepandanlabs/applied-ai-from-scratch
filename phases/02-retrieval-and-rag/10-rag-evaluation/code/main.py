# pip install openai
"""
Lesson 10: RAG Evaluation
=========================
Full RAG evaluation pipeline implementing the RAG Triad:
1. LLM-as-judge for Faithfulness: is the answer supported by the context?
2. LLM-as-judge for Answer Relevance: does the answer address the question?
3. LLM-as-judge for Context Relevance: are the retrieved chunks relevant?
4. RagEvaluator class that runs all three and returns a structured score dict
5. Batch evaluation over a sample eval set of 5 (question, context, answer) triples
6. Threshold-based CI check

Run: python main.py
Requires OPENAI_API_KEY in environment.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvalExample:
    """One unit of evaluation: a question, retrieved context chunks, and a generated answer."""
    question: str
    context: list[str]
    answer: str
    expected_answer: Optional[str] = None


@dataclass
class TriadScores:
    """Structured output from the full RAG Triad evaluation."""
    faithfulness: float
    answer_relevance: float
    context_relevance: float
    context_relevance_per_chunk: list[float] = field(default_factory=list)
    faithfulness_claims: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Sample eval set
# 5 examples: 4 answerable, 1 out-of-scope (answer not supported by context)
# ---------------------------------------------------------------------------

SAMPLE_EVAL_SET = [
    EvalExample(
        question="What is RAG and why is it useful?",
        context=[
            "Retrieval-Augmented Generation (RAG) combines a retrieval system with a "
            "language model. Instead of relying solely on parametric memory, the model "
            "retrieves relevant documents at inference time.",
            "RAG enables language models to access up-to-date information without retraining. "
            "This makes it especially useful for enterprise knowledge bases where documents "
            "change frequently.",
        ],
        answer=(
            "RAG stands for Retrieval-Augmented Generation. It combines retrieval with "
            "generation, allowing language models to access external documents at inference "
            "time rather than relying purely on training data [1]. This is useful because "
            "it enables up-to-date information access without retraining [2]."
        ),
    ),
    EvalExample(
        question="How does dense retrieval differ from BM25?",
        context=[
            "BM25 is a sparse retrieval algorithm based on term frequency and inverse "
            "document frequency. It works well for keyword-heavy queries.",
            "Dense retrieval encodes queries and documents as continuous vectors and retrieves "
            "by nearest neighbor search. It handles synonyms and paraphrases better than BM25.",
        ],
        answer=(
            "Dense retrieval uses neural encoders to create vector representations, "
            "enabling semantic matching. BM25 uses exact term matching with TF-IDF "
            "weighting. Dense retrieval handles paraphrases better while BM25 excels "
            "at keyword-specific queries."
        ),
    ),
    EvalExample(
        question="What are the main failure modes of RAG systems?",
        context=[
            "Common RAG failure modes include: retrieval failure (wrong chunks returned), "
            "hallucination (generator adds facts not in context), and truncation (relevant "
            "information is cut off by context window limits).",
        ],
        answer=(
            "RAG can fail through retrieval (returning wrong chunks), generation "
            "(hallucinating beyond the context), and context truncation. "
            "Additionally, the system may answer adjacent questions due to embedding drift."
            # Last sentence is not in context — faithfulness should catch this
        ),
    ),
    EvalExample(
        question="What does faithfulness measure in RAG evaluation?",
        context=[
            "Faithfulness measures whether the generated answer is entailed by the retrieved "
            "context. A faithfulness score of 1.0 means every claim in the answer can be "
            "traced back to the provided chunks.",
        ],
        answer=(
            "Faithfulness measures whether each claim in the answer is supported by the "
            "retrieved context, not by the model's training data. A score of 1.0 means "
            "every claim traces to the provided chunks."
        ),
    ),
    EvalExample(
        question="What is the boiling point of water at sea level?",  # Out-of-scope
        context=[
            "The Eiffel Tower is a wrought-iron lattice tower in Paris, built between "
            "1887 and 1889 for the World's Fair.",
            "Water covers approximately 71% of Earth's surface.",
        ],
        answer="The boiling point of water at sea level is 100 degrees Celsius.",
        # Answer is not supported by context — faithfulness and context relevance tests
    ),
]


# ---------------------------------------------------------------------------
# Judge: Faithfulness
# ---------------------------------------------------------------------------

FAITHFULNESS_SYSTEM = """You are an objective evaluator. Your task is to assess whether
a given ANSWER is faithful to (supported by) the provided CONTEXT.

Steps:
1. Identify each distinct factual claim in the ANSWER.
2. For each claim, determine whether the CONTEXT contains information that directly
   supports or entails it. Do not infer; require explicit support.
3. Return a JSON object with this exact schema:

{
  "claims": [
    {
      "claim": "<text of claim>",
      "supported": true or false,
      "reason": "<1-sentence reason>"
    }
  ],
  "faithfulness_score": <fraction of claims that are supported, 0.0-1.0>
}

Rules:
- Do not mark a claim as supported just because it sounds plausible.
- Citation markers like [1] or [2] in the answer should be ignored for this evaluation.
- If the answer contains zero factual claims, return faithfulness_score of 1.0."""


def score_faithfulness(
    question: str,
    context: list[str],
    answer: str,
    client: OpenAI,
    model: str = "gpt-4o-mini",
) -> dict:
    """
    LLM-as-judge: decompose the answer into claims and score each against context.
    Returns dict with 'faithfulness_score' (float 0-1) and 'claims' (list of dicts).
    """
    context_text = "\n\n---\n\n".join(
        f"[Chunk {i+1}]: {chunk}" for i, chunk in enumerate(context)
    )
    user_msg = (
        f"QUESTION: {question}\n\n"
        f"CONTEXT:\n{context_text}\n\n"
        f"ANSWER:\n{answer}\n\n"
        "Evaluate whether each factual claim in the ANSWER is supported by the CONTEXT."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": FAITHFULNESS_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {"faithfulness_score": 0.0, "claims": [], "error": "parse_failed"}


# ---------------------------------------------------------------------------
# Judge: Answer Relevance
# ---------------------------------------------------------------------------

ANSWER_RELEVANCE_SYSTEM = """You are an objective evaluator. Your task is to assess
whether a given ANSWER addresses the user's QUESTION.

Scoring guide (0.0–1.0):
- 1.0: Answer directly and completely addresses the question
- 0.8: Answer addresses the main question but misses secondary aspects
- 0.5: Answer is topically related but doesn't answer the specific question
- 0.2: Answer is on a related but different topic
- 0.0: Answer is completely off-topic, a refusal, or entirely irrelevant

Return a JSON object:
{
  "answer_relevance_score": <float 0.0-1.0>,
  "reasoning": "<1-2 sentence explanation>"
}"""


def score_answer_relevance(
    question: str,
    answer: str,
    client: OpenAI,
    model: str = "gpt-4o-mini",
) -> dict:
    """
    LLM-as-judge: score whether the answer addresses the question.
    Returns dict with 'answer_relevance_score' (float) and 'reasoning' (str).
    """
    user_msg = f"QUESTION: {question}\n\nANSWER: {answer}\n\nRate how well the answer addresses the question."

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ANSWER_RELEVANCE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {"answer_relevance_score": 0.0, "reasoning": "parse_failed"}


# ---------------------------------------------------------------------------
# Judge: Context Relevance
# ---------------------------------------------------------------------------

CONTEXT_RELEVANCE_SYSTEM = """You are an objective evaluator. Your task is to assess
whether each retrieved CONTEXT CHUNK is relevant to answering the given QUESTION.

A chunk is relevant if it contains information that directly helps answer the question.
A chunk is NOT relevant if it only shares a keyword with the question but doesn't
contribute to the answer.

Return a JSON object:
{
  "chunk_scores": [
    {
      "chunk_index": <0-based integer>,
      "relevant": true or false,
      "relevance_score": <float 0.0-1.0>,
      "reasoning": "<1-sentence reason>"
    }
  ],
  "context_relevance_score": <mean relevance_score across all chunks, 0.0-1.0>
}"""


def score_context_relevance(
    question: str,
    context: list[str],
    client: OpenAI,
    model: str = "gpt-4o-mini",
) -> dict:
    """
    LLM-as-judge: score whether each retrieved chunk helps answer the question.
    Returns dict with 'context_relevance_score' (float) and 'chunk_scores' (list).
    """
    chunks_text = "\n\n".join(
        f"[Chunk {i}]: {chunk}" for i, chunk in enumerate(context)
    )
    user_msg = (
        f"QUESTION: {question}\n\n"
        f"RETRIEVED CHUNKS:\n{chunks_text}\n\n"
        "Evaluate the relevance of each chunk for answering this question."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": CONTEXT_RELEVANCE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {"context_relevance_score": 0.0, "chunk_scores": [], "error": "parse_failed"}


# ---------------------------------------------------------------------------
# RagEvaluator
# ---------------------------------------------------------------------------

class RagEvaluator:
    """
    Full RAG Triad evaluator using LLM-as-judge for all three components.

    Usage:
        evaluator = RagEvaluator()
        result = evaluator.evaluate(example)   # single example
        batch  = evaluator.evaluate_batch(examples)  # multiple examples
        check  = evaluator.check_thresholds(batch)   # CI gate
    """

    def __init__(self, model: str = "gpt-4o-mini", api_key: Optional[str] = None):
        self.model = model
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    def evaluate(self, example: EvalExample) -> dict:
        """
        Run all three RAG Triad judges on one example.

        Returns:
        {
          "question": str,
          "faithfulness": float,
          "answer_relevance": float,
          "context_relevance": float,
          "details": { ... raw judge outputs ... }
        }
        """
        faith_result = score_faithfulness(
            example.question, example.context, example.answer,
            self.client, self.model
        )
        relevance_result = score_answer_relevance(
            example.question, example.answer,
            self.client, self.model
        )
        context_result = score_context_relevance(
            example.question, example.context,
            self.client, self.model
        )

        return {
            "question": example.question,
            "faithfulness": faith_result.get("faithfulness_score", 0.0),
            "answer_relevance": relevance_result.get("answer_relevance_score", 0.0),
            "context_relevance": context_result.get("context_relevance_score", 0.0),
            "details": {
                "faithfulness": faith_result,
                "answer_relevance": relevance_result,
                "context_relevance": context_result,
            },
        }

    def evaluate_batch(self, examples: list[EvalExample]) -> dict:
        """
        Evaluate a list of examples and return aggregate statistics.

        Returns:
        {
          "mean_faithfulness": float,
          "mean_answer_relevance": float,
          "mean_context_relevance": float,
          "per_example": list[dict],
          "n": int
        }
        """
        results = []
        for i, example in enumerate(examples):
            print(f"  [{i+1}/{len(examples)}] Evaluating: {example.question[:55]}...")
            result = self.evaluate(example)
            results.append(result)
            print(
                f"          F={result['faithfulness']:.2f} "
                f"AR={result['answer_relevance']:.2f} "
                f"CR={result['context_relevance']:.2f}"
            )

        n = len(results)
        mean_faith = sum(r["faithfulness"] for r in results) / n
        mean_ar = sum(r["answer_relevance"] for r in results) / n
        mean_cr = sum(r["context_relevance"] for r in results) / n

        return {
            "mean_faithfulness": mean_faith,
            "mean_answer_relevance": mean_ar,
            "mean_context_relevance": mean_cr,
            "per_example": results,
            "n": n,
        }

    def check_thresholds(
        self,
        scores: dict,
        min_faithfulness: float = 0.80,
        min_answer_relevance: float = 0.75,
        min_context_relevance: float = 0.70,
    ) -> dict:
        """
        Gate check for CI integration.
        Returns {"passed": bool, "failures": list[str], "scores": dict}.
        Use: if not check["passed"]: sys.exit(1)
        """
        checks = {
            "faithfulness": (scores["mean_faithfulness"], min_faithfulness),
            "answer_relevance": (scores["mean_answer_relevance"], min_answer_relevance),
            "context_relevance": (scores["mean_context_relevance"], min_context_relevance),
        }

        failures = []
        for metric, (score, threshold) in checks.items():
            if score < threshold:
                failures.append(
                    f"{metric}: {score:.3f} < {threshold:.2f} (threshold)"
                )

        return {
            "passed": len(failures) == 0,
            "failures": failures,
            "scores": {k: v[0] for k, v in checks.items()},
        }


# ---------------------------------------------------------------------------
# Judge calibration helper
# ---------------------------------------------------------------------------

def calibrate_judge(
    human_scores: list[float],
    judge_scores: list[float],
    threshold: float = 0.5,
) -> dict:
    """
    Measure agreement between a human evaluator and the LLM judge.

    Both lists should contain scores in [0, 1] for the same examples.
    Returns agreement_rate, mean_absolute_error, and a trustworthiness flag.

    If agreement_rate < 0.85, the judge is not reliable for your domain.
    Fix: add few-shot examples to the judge prompt, or use a stronger model.
    """
    assert len(human_scores) == len(judge_scores), "Lists must be the same length"
    n = len(human_scores)

    # Binary agreement: both above or both below the threshold
    agreements = sum(
        1 for h, j in zip(human_scores, judge_scores)
        if (h >= threshold) == (j >= threshold)
    )
    agreement_rate = agreements / n

    # Mean absolute error (for continuous scores)
    mae = sum(abs(h - j) for h, j in zip(human_scores, judge_scores)) / n

    return {
        "agreement_rate": agreement_rate,
        "mean_absolute_error": mae,
        "n": n,
        "trustworthy": agreement_rate >= 0.85,
        "recommendation": (
            "Judge is reliable for automated evaluation."
            if agreement_rate >= 0.85
            else "Judge agreement < 85%. Add few-shot examples to judge prompt "
                 "or upgrade the judge model before using at scale."
        ),
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def print_eval_report(batch_results: dict, threshold_check: dict) -> None:
    """Print a human-readable evaluation report."""
    print("\n" + "=" * 64)
    print("RAG EVALUATION REPORT")
    print("=" * 64)

    print(f"\nEvaluated {batch_results['n']} examples")
    print(f"\n{'Metric':<25} {'Score':>8} {'Threshold':>10} {'Status':>8}")
    print("-" * 55)

    thresholds = {"faithfulness": 0.80, "answer_relevance": 0.75, "context_relevance": 0.70}
    for metric, score in batch_results.items():
        if metric.startswith("mean_"):
            clean = metric.replace("mean_", "")
            threshold = thresholds.get(clean, 0.0)
            status = "PASS" if score >= threshold else "FAIL"
            print(f"  {clean:<23} {score:>8.3f} {threshold:>10.2f} {status:>8}")

    print("\n" + "-" * 55)
    overall = "PASSED" if threshold_check["passed"] else "FAILED"
    print(f"Overall: {overall}")
    if not threshold_check["passed"]:
        for f in threshold_check["failures"]:
            print(f"  - {f}")

    print("\nPer-Example Breakdown:")
    print(f"  {'Question':<45} {'F':>5} {'AR':>5} {'CR':>5}")
    print("  " + "-" * 62)
    for ex in batch_results["per_example"]:
        q = ex["question"][:43] + ".." if len(ex["question"]) > 45 else ex["question"]
        print(
            f"  {q:<45} "
            f"{ex['faithfulness']:>5.2f} "
            f"{ex['answer_relevance']:>5.2f} "
            f"{ex['context_relevance']:>5.2f}"
        )


# ---------------------------------------------------------------------------
# Diagnostic helpers
# ---------------------------------------------------------------------------

def diagnose(scores: dict) -> str:
    """
    Return a one-sentence diagnosis based on the RAG Triad diagnostic matrix.
    """
    f = scores.get("mean_faithfulness", 1.0)
    ar = scores.get("mean_answer_relevance", 1.0)
    cr = scores.get("mean_context_relevance", 1.0)

    if f >= 0.8 and ar >= 0.75 and cr >= 0.7:
        return "System is working within acceptable bounds on all three dimensions."
    if cr < 0.7:
        return "Retriever is the primary issue — fix context relevance before touching the generator."
    if f < 0.8 and cr >= 0.7:
        return "Generator is hallucinating despite adequate retrieval — tighten grounding prompts."
    if ar < 0.75 and f >= 0.8:
        return "Generator is answering adjacent questions — check query understanding and context window."
    return "Multiple dimensions failing — start with context relevance, then faithfulness."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Lesson 10: RAG Evaluation")
    print("=" * 64)

    evaluator = RagEvaluator()

    print("\nRunning RAG Triad evaluation on sample eval set...")
    batch_results = evaluator.evaluate_batch(SAMPLE_EVAL_SET)

    threshold_check = evaluator.check_thresholds(batch_results)

    print_eval_report(batch_results, threshold_check)

    print(f"\nDiagnosis: {diagnose(batch_results)}")

    # Demo: calibration check with synthetic human scores
    print("\n" + "=" * 64)
    print("JUDGE CALIBRATION DEMO")
    print("=" * 64)
    print("Simulating human vs judge agreement on faithfulness scores...")

    # Synthetic human labels (in real usage, these come from domain expert annotation)
    human_faithfulness = [0.9, 1.0, 0.6, 1.0, 0.0]
    judge_faithfulness = [
        r["faithfulness"] for r in batch_results["per_example"]
    ]

    calibration = calibrate_judge(human_faithfulness, judge_faithfulness)
    print(f"\n  Agreement rate: {calibration['agreement_rate']:.1%}")
    print(f"  Mean absolute error: {calibration['mean_absolute_error']:.3f}")
    print(f"  Trustworthy: {calibration['trustworthy']}")
    print(f"  Recommendation: {calibration['recommendation']}")

    # CI gate simulation
    print("\n" + "=" * 64)
    print("CI GATE CHECK")
    if not threshold_check["passed"]:
        print("BUILD WOULD FAIL. Threshold violations:")
        for failure in threshold_check["failures"]:
            print(f"  - {failure}")
        print("\n(In CI, call sys.exit(1) here)")
    else:
        print("BUILD PASSES. All metrics above thresholds.")


if __name__ == "__main__":
    main()
