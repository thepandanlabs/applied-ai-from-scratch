---
name: skill-multistep-eval
description: guide for evaluating RAG pipelines and agent systems with component-level metrics, trajectory evals, and failure taxonomy
version: "1.0"
phase: "05"
lesson: "10"
tags: [eval, rag, agents, trajectory, faithfulness, ragas, multistep]
---

# Multi-Step System Eval Reference

## The RAG Triad

Every RAG pipeline has three independent failure modes. Measure all three.

### Metric Definitions

| Metric | What it measures | Failure when low |
|--------|-----------------|-----------------|
| Context Relevance | Did retrieval return relevant chunks? | Retriever is broken or under-tuned |
| Faithfulness | Does the answer stay grounded in the chunks? | Generator is hallucinating |
| Answer Relevance | Does the answer address the original question? | Generator is off-topic or evasive |

### Diagnostic Patterns

```
High context relevance + low faithfulness:
  Retrieval works. Generator ignores the context and hallucinates.
  Fix: strengthen grounding instructions in the prompt.

Low context relevance + high faithfulness:
  Generator is grounded but in the wrong chunks. Confidently wrong.
  Fix: improve the retriever (embeddings, chunking strategy, reranker).

High faithfulness + high context relevance + low answer relevance:
  Grounded in relevant chunks but doesn't answer the actual question.
  Fix: check if chunks are actually answer-bearing or just topic-adjacent.

All three high + users still complain:
  Your eval set does not cover the real failure cases. Expand the golden set
  with examples from actual user complaints.
```

## RAG Triad Implementation

```python
import json, re
from anthropic import Anthropic
client = Anthropic()

def eval_retrieval(question, retrieved_chunks, relevant_chunks, threshold=0.5):
    """Precision@k and Recall@k against ground-truth relevant chunks."""
    def is_relevant(chunk, refs):
        for ref in refs:
            w1, w2 = set(chunk.lower().split()), set(ref.lower().split())
            if w2 and len(w1 & w2) / len(w2) >= threshold:
                return True
        return False

    k = len(retrieved_chunks)
    rel_ret = sum(1 for c in retrieved_chunks if is_relevant(c, relevant_chunks))
    return {
        "precision_at_k": round(rel_ret / k, 3) if k else 0.0,
        "recall_at_k": round(rel_ret / len(relevant_chunks), 3) if relevant_chunks else 0.0
    }

def eval_faithfulness(answer, retrieved_chunks):
    """Fraction of answer sentences grounded in retrieved context (overlap-based)."""
    context_words = set(" ".join(retrieved_chunks).lower().split())
    sentences = [s.strip() for s in re.split(r"[.!?]", answer) if s.strip()]
    if not sentences:
        return {"faithfulness": 0.0}
    grounded = 0
    for s in sentences:
        content = {w for w in s.lower().split() if len(w) > 4}
        if not content or len(content & context_words) / len(content) >= 0.4:
            grounded += 1
    return {"faithfulness": round(grounded / len(sentences), 3),
            "grounded_sentences": grounded, "total_sentences": len(sentences)}

def eval_answer_relevance(question, answer):
    """LLM judge: does the answer address the question?"""
    resp = client.messages.create(
        model="claude-3-5-haiku-20241022", max_tokens=128,
        messages=[{"role": "user", "content":
            f'Does this answer address the question?\nQ: {question}\nA: {answer}\n'
            f'Respond JSON only: {{"score": 0.0-1.0, "reasoning": "one sentence"}}'
        }]
    )
    result = json.loads(resp.content[0].text.strip())
    return {"answer_relevance": round(float(result["score"]), 3), "reasoning": result["reasoning"]}
```

## RAGAS Quick Start

For production RAG evals, RAGAS is faster to set up and more accurate:

```python
# pip install ragas datasets
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from datasets import Dataset

data = Dataset.from_dict({
    "question": [list_of_questions],
    "answer": [list_of_answers],
    "contexts": [list_of_retrieved_chunk_lists],   # list of lists
    "ground_truth": [list_of_reference_answers]    # optional
})

results = evaluate(data, metrics=[faithfulness, answer_relevancy, context_precision])
# Returns: {"faithfulness": 0.xx, "answer_relevancy": 0.xx, "context_precision": 0.xx}
```

## Agent Trajectory Eval

```python
def lcs_length(a, b):
    dp = [[0]*(len(b)+1) for _ in range(len(a)+1)]
    for i in range(1, len(a)+1):
        for j in range(1, len(b)+1):
            dp[i][j] = dp[i-1][j-1]+1 if a[i-1]==b[j-1] else max(dp[i-1][j], dp[i][j-1])
    return dp[len(a)][len(b)]

def eval_trajectory(expected_tools, actual_tools):
    """
    exact_match:    1.0 if sequences identical
    tool_coverage:  fraction of expected tools that appeared anywhere
    order_score:    LCS / len(expected) -- right tools, right order
    extra_calls:    calls beyond expected sequence length
    """
    exact = 1.0 if expected_tools == actual_tools else 0.0
    coverage = sum(1 for t in expected_tools if t in set(actual_tools)) / len(expected_tools) if expected_tools else 0.0
    order = lcs_length(expected_tools, actual_tools) / len(expected_tools) if expected_tools else 0.0
    extra = max(0, len(actual_tools) - len(expected_tools))
    return {"exact_match": exact, "tool_coverage": round(coverage,3),
            "order_score": round(order,3), "extra_calls": extra}

def eval_termination(trace, should_have_stopped_at):
    """Did the agent emit final_answer at the right step?"""
    stopped_at = next((i+1 for i,s in enumerate(trace) if s.get("type")=="final_answer"), None)
    if stopped_at is None:
        return {"termination": "never_stopped", "score": 0.0}
    elif stopped_at < should_have_stopped_at:
        return {"termination": "too_early", "score": 0.5, "actual": stopped_at, "expected": should_have_stopped_at}
    elif stopped_at == should_have_stopped_at:
        return {"termination": "correct", "score": 1.0}
    else:
        return {"termination": "looped", "score": 0.3, "actual": stopped_at, "expected": should_have_stopped_at}
```

## Component vs End-to-End Strategy

Run both. Use component evals for debugging; use end-to-end evals as the final quality gate.

```
When component evals flag a regression:
  context_relevance drops -> investigate retriever (embeddings, chunk size, top-k)
  faithfulness drops      -> investigate generator prompt (grounding instructions, temperature)
  answer_relevance drops  -> investigate prompt or retrieval (are the right chunks answer-bearing?)
  trajectory score drops  -> investigate agent planning prompt or tool definitions
  termination score drops -> investigate stopping conditions or agent loop logic

When end-to-end eval flags a regression but components look fine:
  Cross-stage failure: the interaction between stages is wrong.
  Example: retriever returns correct chunks but generator prompt does not use them.
  Inspect individual failing cases, not aggregate scores.
```

## Multi-Step System Failure Taxonomy

| Failure type | Component that flags it | Common cause |
|-------------|------------------------|--------------|
| Wrong chunks retrieved | context_relevance | Embedding model mismatch, chunk size too large |
| Hallucination | faithfulness | Missing grounding instruction, high temperature |
| Off-topic answer | answer_relevance | Prompt drift, model change |
| Wrong tool sequence | trajectory order_score | Agent planning prompt changed |
| Redundant tool calls | trajectory extra_calls | Agent loops without stopping condition |
| Premature termination | termination: too_early | Stopping condition too aggressive |
| Infinite loop | termination: looped | No maximum step limit |
| Silent failure | none (end-to-end only) | Correct tool, wrong reasoning |

Silent failures are the hardest: the agent calls all the right tools in the right order and produces a final answer, but the answer is wrong because of a reasoning error inside a tool call. To catch these, add an end-to-end LLM judge that verifies the final answer against a ground truth.

## Eval Coverage Checklist

For RAG systems:
- [ ] Context relevance tested with intentionally bad retrieval (random chunks)
- [ ] Faithfulness tested with a hallucinated answer known to be off-context
- [ ] Answer relevance tested with an on-topic but non-answering response
- [ ] All three metrics tested together on 20+ real traces

For agent systems:
- [ ] Trajectory eval covers exact match, wrong order, missing tool, extra call
- [ ] Termination eval covers correct stop, too early, looped, never stopped
- [ ] End-to-end eval covers a representative golden set with known correct final answers
- [ ] Correlation checked between component scores and user satisfaction on real traces
