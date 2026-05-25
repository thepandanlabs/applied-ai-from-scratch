"""
Lesson 07: Pairwise & Reference-Based Evals
Phase 05: Evaluation & Eval-Driven Development

Demonstrates:
- pairwise_judge: head-to-head comparison with LLM
- pairwise_judge_debiased: position-bias mitigation via order swap
- pairwise_eval: preference rate over a golden set
- reference_similarity: BLEU-approx + difflib scoring
- demo: compare two prompt variants on 5 questions

Run:
    uv run main.py

Requires: ANTHROPIC_API_KEY
"""

import json
import math
import os
import difflib
from collections import Counter

from anthropic import Anthropic

client = Anthropic()


# ---------------------------------------------------------------------------
# Pairwise judge
# ---------------------------------------------------------------------------

def pairwise_judge(
    question: str,
    output_a: str,
    output_b: str,
    model: str = "claude-3-5-sonnet-20241022"
) -> dict:
    """
    Compare two outputs head-to-head and return winner + reasoning.

    Returns:
        {"winner": "A" | "B" | "tie", "reasoning": str, "criteria": list[str]}
    """
    prompt = f"""You are evaluating two AI system responses to the same question.

Question: {question}

Response A:
{output_a}

Response B:
{output_b}

Compare these responses. Consider: accuracy, completeness, clarity, and usefulness.
Which response is better?

Respond with JSON only:
{{
  "winner": "A" or "B" or "tie",
  "reasoning": "one sentence explaining the decision",
  "criteria": ["criterion 1", "criterion 2"]
}}"""

    response = client.messages.create(
        model=model,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]

    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# Bias mitigation: run judge twice with swapped order
# ---------------------------------------------------------------------------

def pairwise_judge_debiased(
    question: str,
    output_a: str,
    output_b: str
) -> dict:
    """
    Run judge twice with swapped order. Return consensus result or flag a flip.

    A "flip" means: judge said A wins when A was first, but said B wins when B
    was first (i.e., the judge is just picking whoever appears first).

    Returns:
        {
            "winner": "A" | "B" | "tie",
            "reasoning": str,
            "flipped": bool,
            "confidence": "high" | "low"
        }
    """
    # Round 1: A first
    result_ab = pairwise_judge(question, output_a, output_b)

    # Round 2: B first (swap the label meanings)
    result_ba = pairwise_judge(question, output_b, output_a)

    # Normalize result_ba: judge's "A" is actually our B and vice versa
    flipped_map = {"A": "B", "B": "A", "tie": "tie"}
    normalized_ba_winner = flipped_map[result_ba["winner"]]

    agreed = result_ab["winner"] == normalized_ba_winner

    if agreed:
        return {
            "winner": result_ab["winner"],
            "reasoning": result_ab["reasoning"],
            "flipped": False,
            "confidence": "high"
        }
    else:
        # Disagreement: call it a tie and flag for review
        return {
            "winner": "tie",
            "reasoning": (
                f"Position bias detected. "
                f"A-first order said winner={result_ab['winner']}, "
                f"B-first order said winner={normalized_ba_winner}."
            ),
            "flipped": True,
            "confidence": "low"
        }


# ---------------------------------------------------------------------------
# Pairwise eval over a golden set
# ---------------------------------------------------------------------------

def pairwise_eval(
    golden_set: list[dict],
    system_a_fn,
    system_b_fn
) -> dict:
    """
    Run head-to-head pairwise eval for all cases in the golden set.

    Args:
        golden_set: list of {"input": str, ...}
        system_a_fn: callable(question: str) -> str
        system_b_fn: callable(question: str) -> str

    Returns:
        {
            "preference_rate_a": float,   # A wins / (A wins + B wins)
            "wins_a": int,
            "wins_b": int,
            "ties": int,
            "tie_rate": float,
            "flip_rate": float,
            "n": int,
            "cases": list[dict]
        }
    """
    results = []
    wins_a = wins_b = ties = flips = 0

    for i, case in enumerate(golden_set):
        question = case["input"]
        print(f"  Case {i+1}/{len(golden_set)}: {question[:60]}...")

        output_a = system_a_fn(question)
        output_b = system_b_fn(question)
        judgment = pairwise_judge_debiased(question, output_a, output_b)

        if judgment["winner"] == "A":
            wins_a += 1
        elif judgment["winner"] == "B":
            wins_b += 1
        else:
            ties += 1

        if judgment["flipped"]:
            flips += 1

        results.append({
            "question": question,
            "output_a": output_a,
            "output_b": output_b,
            **judgment
        })

    total = len(golden_set)
    decisive = wins_a + wins_b  # exclude ties for preference rate

    return {
        "preference_rate_a": wins_a / decisive if decisive > 0 else 0.5,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "ties": ties,
        "tie_rate": round(ties / total, 3),
        "flip_rate": round(flips / total, 3),
        "n": total,
        "cases": results
    }


# ---------------------------------------------------------------------------
# Reference-based scoring
# ---------------------------------------------------------------------------

def ngram_overlap(text: str, reference: str, n: int) -> float:
    """Fraction of text's n-grams that also appear in reference."""
    def get_ngrams(t: str, n: int) -> Counter:
        words = t.lower().split()
        return Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))

    text_ngrams = get_ngrams(text, n)
    ref_ngrams = get_ngrams(reference, n)

    if not text_ngrams:
        return 0.0

    overlap = sum(min(count, ref_ngrams[gram]) for gram, count in text_ngrams.items())
    return overlap / sum(text_ngrams.values())


def bleu_approx(output: str, reference: str) -> float:
    """
    Simplified BLEU: geometric mean of 1-gram through 4-gram precision.

    Intuition: what fraction of the output's word sequences appear in the
    reference? A score near 1.0 means the output closely echoes the reference
    phrasing. A score near 0.0 means the vocabulary diverges completely.

    Note: real BLEU also applies a brevity penalty; this version omits it
    to stay readable. Use sacrebleu for production reference scoring.
    """
    precisions = []
    for n in range(1, 5):
        p = ngram_overlap(output, reference, n)
        # Avoid log(0): floor at a small epsilon
        precisions.append(p if p > 0 else 1e-10)

    log_avg = sum(math.log(p) for p in precisions) / 4
    return math.exp(log_avg)


def reference_similarity(output: str, reference: str) -> dict:
    """
    Combined reference-based score using difflib ratio and BLEU approximation.

    Returns:
        {
            "difflib_ratio": float,   # character-level sequence similarity
            "bleu_approx": float,     # n-gram word overlap
            "combined": float         # simple average
        }
    """
    ratio = difflib.SequenceMatcher(None, output.lower(), reference.lower()).ratio()
    bleu = bleu_approx(output, reference)

    return {
        "difflib_ratio": round(ratio, 3),
        "bleu_approx": round(bleu, 3),
        "combined": round((ratio + bleu) / 2, 3),
    }


# ---------------------------------------------------------------------------
# System prompt variants for the demo
# ---------------------------------------------------------------------------

def system_v1(question: str) -> str:
    """Prompt variant 1: plain concise answers."""
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=200,
        system="Answer concisely in 2-3 sentences.",
        messages=[{"role": "user", "content": question}]
    )
    return response.content[0].text


def system_v2(question: str) -> str:
    """Prompt variant 2: answers include one concrete example."""
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=200,
        system="Answer in 2-3 sentences. Include one concrete example to illustrate your point.",
        messages=[{"role": "user", "content": question}]
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo():
    """Compare v1 (concise) vs v2 (with examples) on 5 technical questions."""

    golden_set = [
        {"input": "What is caching in software systems?"},
        {"input": "Why does database indexing improve query speed?"},
        {"input": "What is the difference between authentication and authorization?"},
        {"input": "How does a load balancer work?"},
        {"input": "What is eventual consistency in distributed systems?"},
    ]

    print("=" * 60)
    print("PAIRWISE EVAL: v1 (concise) vs v2 (with examples)")
    print("=" * 60)
    print()

    results = pairwise_eval(golden_set, system_v1, system_v2)

    print()
    print("-" * 40)
    print(f"Results over {results['n']} cases:")
    print(f"  V1 wins:         {results['wins_a']}")
    print(f"  V2 wins:         {results['wins_b']}")
    print(f"  Ties:            {results['ties']}")
    print(f"  Preference (V1): {results['preference_rate_a']:.0%}")
    print(f"  Tie rate:        {results['tie_rate']:.0%}  (healthy: 10-20%)")
    print(f"  Flip rate:       {results['flip_rate']:.0%}  (healthy: <30%)")
    print()

    # Per-case summary
    print("Per-case breakdown:")
    for i, case in enumerate(results["cases"]):
        flag = " [FLIP]" if case["flipped"] else ""
        print(f"  Q{i+1}: winner={case['winner']}{flag} | {case['reasoning'][:80]}")

    print()

    # Reference similarity demo on Q1
    print("-" * 40)
    print("Reference similarity demo (Q1: 'What is caching?')")
    ref = "Caching stores frequently accessed data in fast memory to avoid recomputing or re-fetching it from a slower source."
    output = system_v1("What is caching in software systems?")
    sim = reference_similarity(output, ref)
    print(f"  Output:            {output[:100]}...")
    print(f"  Reference:         {ref}")
    print(f"  difflib_ratio:     {sim['difflib_ratio']}")
    print(f"  bleu_approx:       {sim['bleu_approx']}")
    print(f"  combined:          {sim['combined']}")


if __name__ == "__main__":
    demo()
