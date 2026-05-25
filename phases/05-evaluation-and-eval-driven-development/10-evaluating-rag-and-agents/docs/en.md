**Type:** Build
**Languages:** Python
**Prerequisites:** 08-eval-harnesses, 09-ci-for-prompts
**Time:** ~60 min
**Learning Objectives:**
- Implement component-level evals for the three failure points in a RAG pipeline: retrieval, faithfulness, and answer relevance
- Build trajectory and termination evals for agent systems
- Combine RAGAS with a custom harness for full multi-step system evaluation
- Diagnose failures using component scores rather than end-to-end scores alone

---

## MOTTO

**When a pipeline fails, you need to know which stage broke. End-to-end scores hide the location of the problem.**

---

## THE PROBLEM

Your RAG chatbot scores 0.91 on "answer quality" in your end-to-end eval. Users are complaining about wrong answers. You look at 10 failure cases and all of them got a 0.88-0.92 quality score. Your eval didn't catch anything.

The problem is that "answer quality" is one number for a three-stage pipeline. You cannot tell from a 0.88 score whether the retrieval returned bad chunks, whether the generator ignored good chunks, or whether the answer simply didn't address the question.

The same issue applies to agents. An agent makes 4 tool calls to answer a question. Unit tests for each tool pass. But end-to-end eval shows 30% failure rate. Why? Because the failure isn't in any individual tool. It's in the sequence: the agent called the right tools in the wrong order, or called a tool twice when it should have stopped, or terminated before getting the information it needed.

Multi-step systems require component-level evals. Each stage gets its own score. When something breaks, you know exactly where to look.

---

## THE CONCEPT

### The RAG Triad

Every RAG pipeline has three distinct failure modes. The RAG Triad names them:

```
                    USER QUESTION
                          |
            +-------------v--------------+
            |      RETRIEVAL             |  <- Failure 1
            |  Context Relevance         |
            |  "Did we fetch the right   |
            |   chunks?"                 |
            +-------------+--------------+
                          |
            retrieved chunks
                          |
            +-------------v--------------+
            |      GENERATION            |  <- Failure 2
            |  Faithfulness              |
            |  "Does the answer stay     |
            |   grounded in the chunks?" |
            +-------------+--------------+
                          |
            generated answer
                          |
            +-------------v--------------+
            |      RELEVANCE             |  <- Failure 3
            |  Answer Relevance          |
            |  "Does the answer address  |
            |   the original question?"  |
            +-----------------------------+
```

These three metrics are independent. A system can have:
- High context relevance but low faithfulness (retrieved great chunks, then hallucinated)
- Low context relevance but high faithfulness (retrieved bad chunks, stayed grounded in them: confidently wrong)
- High faithfulness and high context relevance but low answer relevance (grounded in relevant chunks but didn't answer the actual question)

### Agent Trajectory Evals

Agents don't produce one output. They produce a sequence of tool calls plus a final answer.

```
Expected trajectory:  [search_web, read_url, summarize]
Actual trajectory:    [search_web, search_web, read_url]
```

The final answer might be fine. But the agent wasted a call and didn't follow the right pattern. At scale, wasted calls cost money and time.

Three trajectory eval patterns:

```
EXACT MATCH           PARTIAL CREDIT         TERMINATION CHECK
-----------           --------------         -----------------
Did it call the       Right tools,           Did it stop when
exact right tools     wrong order?           it should have?
in the right order?   Penalize lightly.      Too early or too late?

Score: 0 or 1         Score: fraction        Score: 0 or 1
                      of tools matched
```

### Component vs End-to-End: Both Are Needed

```
COMPONENT EVALS                    END-TO-END EVAL
-----------------------            ---------------
Which stage broke?                 Did the user get a good answer?
Fast to debug                      Hard to debug
May miss cross-stage failures      Catches emergent failures
Required for RAG + agents          Required for final quality gate
```

Both are needed. Component evals tell you where to fix. End-to-end evals tell you if the fix worked.

---

## BUILD IT

### RAG Component Evals

```python
# code/main.py
import json
import re
from anthropic import Anthropic

client = Anthropic()

# --- Eval 1: Context Relevance (Retrieval Quality) ---

def eval_retrieval(
    question: str,
    retrieved_chunks: list[str],
    relevant_chunks: list[str]  # from golden retrieval set
) -> dict:
    """
    Precision@k and Recall@k for retrieved chunks vs ground truth relevant chunks.
    Uses simple substring overlap as relevance signal (replace with embeddings in production).
    """
    def is_relevant(chunk: str, relevant: list[str], threshold: float = 0.5) -> bool:
        for ref in relevant:
            words_chunk = set(chunk.lower().split())
            words_ref = set(ref.lower().split())
            if not words_ref:
                continue
            overlap = len(words_chunk & words_ref) / len(words_ref)
            if overlap >= threshold:
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
        "total_relevant": len(relevant_chunks)
    }
```

```python
# --- Eval 2: Faithfulness (Generation Grounded in Context?) ---

def eval_faithfulness(answer: str, retrieved_chunks: list[str]) -> dict:
    """
    Check what fraction of factual claims in the answer appear in the retrieved chunks.
    Uses simple word overlap as a first-pass approximation.
    For production: use LLM to extract claims, then check each claim against chunks.
    """
    # Approximation: does each sentence in the answer have word overlap with chunks?
    combined_context = " ".join(retrieved_chunks).lower()
    context_words = set(combined_context.split())

    sentences = [s.strip() for s in re.split(r'[.!?]', answer) if s.strip()]
    if not sentences:
        return {"faithfulness": 0.0, "grounded_sentences": 0, "total_sentences": 0}

    grounded = 0
    for sentence in sentences:
        words = set(sentence.lower().split())
        # Remove stopwords proxy: only consider words > 4 chars
        content_words = {w for w in words if len(w) > 4}
        if not content_words:
            grounded += 1  # treat short/stopword sentences as neutral
            continue
        overlap = len(content_words & context_words) / len(content_words)
        if overlap >= 0.4:  # 40% of content words appear in context
            grounded += 1

    faithfulness = grounded / len(sentences)
    return {
        "faithfulness": round(faithfulness, 3),
        "grounded_sentences": grounded,
        "total_sentences": len(sentences)
    }
```

```python
# --- Eval 3: Answer Relevance (Answers the Question?) ---

def eval_answer_relevance(question: str, answer: str) -> dict:
    """
    LLM judge: does this answer address the question?
    Returns score 0.0-1.0 and reasoning.
    """
    prompt = f"""Does the following answer address the question asked?

Question: {question}

Answer: {answer}

Rate on a scale of 0 to 1:
- 1.0: Fully addresses the question
- 0.7: Partially addresses it, missing key aspects
- 0.3: Tangentially related but doesn't answer the question
- 0.0: Completely off-topic

Respond with JSON only:
{{"score": <float>, "reasoning": "<one sentence>"}}"""

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()

    result = json.loads(text)
    return {
        "answer_relevance": round(float(result["score"]), 3),
        "reasoning": result["reasoning"]
    }
```

### Agent Trajectory Evals

```python
# --- Eval 4: Trajectory Eval ---

def eval_trajectory(
    expected_tools: list[str],
    actual_tools: list[str]
) -> dict:
    """
    Compare expected vs actual tool call sequences.

    Returns:
    - exact_match: 1.0 if sequences are identical
    - tool_coverage: fraction of expected tools that appear anywhere in actual
    - order_score: fraction of expected tools that appear in correct relative order
    - extra_calls: number of unexpected tool calls
    """
    exact = 1.0 if expected_tools == actual_tools else 0.0

    # Tool coverage: which expected tools appeared at all?
    actual_set = set(actual_tools)
    coverage = sum(1 for t in expected_tools if t in actual_set) / len(expected_tools) if expected_tools else 0.0

    # Order score: longest common subsequence length / expected length
    def lcs_length(a: list, b: list) -> int:
        m, n = len(a), len(b)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if a[i-1] == b[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        return dp[m][n]

    lcs = lcs_length(expected_tools, actual_tools)
    order_score = lcs / len(expected_tools) if expected_tools else 0.0

    extra_calls = max(0, len(actual_tools) - len(expected_tools))

    return {
        "exact_match": exact,
        "tool_coverage": round(coverage, 3),
        "order_score": round(order_score, 3),
        "extra_calls": extra_calls
    }


# --- Eval 5: Termination Eval ---

def eval_termination(
    trace: list[dict],  # list of {type: "tool_call"|"final_answer", tool: str, ...}
    should_have_stopped_at: int  # 1-indexed step number
) -> dict:
    """
    Did the agent stop at the right step?

    Cases:
    - Stopped too early: final_answer before expected step
    - Stopped correctly: final_answer at expected step
    - Looped: ran past expected step without stopping
    - Never stopped: no final_answer in trace
    """
    final_answer_at = None
    for i, step in enumerate(trace):
        if step.get("type") == "final_answer":
            final_answer_at = i + 1  # 1-indexed
            break

    if final_answer_at is None:
        return {"termination": "never_stopped", "score": 0.0, "steps": len(trace)}
    elif final_answer_at < should_have_stopped_at:
        return {"termination": "too_early", "score": 0.5, "actual_step": final_answer_at, "expected_step": should_have_stopped_at}
    elif final_answer_at == should_have_stopped_at:
        return {"termination": "correct", "score": 1.0, "actual_step": final_answer_at}
    else:
        return {"termination": "looped", "score": 0.3, "actual_step": final_answer_at, "expected_step": should_have_stopped_at}
```

### Run It on Example Traces

```python
def demo():
    # --- RAG trace example ---
    question = "What is the capital of the Roman Empire?"
    retrieved_chunks = [
        "Rome was the capital of the Roman Empire from its founding until 286 AD.",
        "The Roman Empire covered much of Europe, North Africa, and the Middle East.",
        "Constantinople became the eastern capital in 330 AD under Constantine."
    ]
    relevant_chunks = [
        "Rome was the capital of the Roman Empire from its founding until 286 AD.",
        "Constantinople became the eastern capital in 330 AD under Constantine."
    ]
    answer = "The capital of the Roman Empire was Rome. Later, Constantinople became a second capital in the eastern part of the empire."

    print("=== RAG Component Evals ===")
    retrieval = eval_retrieval(question, retrieved_chunks, relevant_chunks)
    faithfulness = eval_faithfulness(answer, retrieved_chunks)
    relevance = eval_answer_relevance(question, answer)

    print(f"Context Relevance:  precision={retrieval['precision_at_k']:.2f}  recall={retrieval['recall_at_k']:.2f}")
    print(f"Faithfulness:       {faithfulness['faithfulness']:.2f}  ({faithfulness['grounded_sentences']}/{faithfulness['total_sentences']} sentences grounded)")
    print(f"Answer Relevance:   {relevance['answer_relevance']:.2f}  ({relevance['reasoning']})")

    # --- Agent trajectory example ---
    print("\n=== Agent Trajectory Evals ===")
    expected_tools = ["search_knowledge_base", "read_document", "summarize"]
    actual_tools_good = ["search_knowledge_base", "read_document", "summarize"]
    actual_tools_bad = ["search_knowledge_base", "search_knowledge_base", "read_document"]

    traj_good = eval_trajectory(expected_tools, actual_tools_good)
    traj_bad = eval_trajectory(expected_tools, actual_tools_bad)
    print(f"Good trajectory:  exact={traj_good['exact_match']}  coverage={traj_good['tool_coverage']}  order={traj_good['order_score']}  extra={traj_good['extra_calls']}")
    print(f"Bad trajectory:   exact={traj_bad['exact_match']}  coverage={traj_bad['tool_coverage']}  order={traj_bad['order_score']}  extra={traj_bad['extra_calls']}")

    # --- Termination eval ---
    trace_good = [
        {"type": "tool_call", "tool": "search"},
        {"type": "tool_call", "tool": "read"},
        {"type": "final_answer", "content": "The answer is..."}
    ]
    trace_looping = [
        {"type": "tool_call", "tool": "search"},
        {"type": "tool_call", "tool": "search"},
        {"type": "tool_call", "tool": "search"},
        {"type": "tool_call", "tool": "search"}
    ]

    term_good = eval_termination(trace_good, should_have_stopped_at=3)
    term_loop = eval_termination(trace_looping, should_have_stopped_at=3)
    print(f"\nTermination (correct): {term_good}")
    print(f"Termination (looping): {term_loop}")

if __name__ == "__main__":
    demo()
```

> **Real-world check:** Your RAG system scores 0.95 answer relevance but users say answers are often wrong. You also compute faithfulness: 0.62. What does this combination tell you about where the failure is, and what do you fix first? High answer relevance means the answers address the right topic. Low faithfulness (0.62) means 38% of the answer content is not grounded in the retrieved chunks: the model is hallucinating. The answers are on-topic but not factually grounded. Fix the generation step first: add stronger grounding instructions to the prompt, add a post-generation check, or reduce temperature. Do not fix retrieval; the problem is not there.

---

## USE IT

### RAGAS for RAG Evals

RAGAS provides the same RAG Triad metrics with more sophisticated implementations:

```python
# pip install ragas
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision
from datasets import Dataset

# Prepare your RAG traces in RAGAS format
data = {
    "question": ["What is the capital of the Roman Empire?"],
    "answer": ["The capital was Rome, later Constantinople became the eastern capital."],
    "contexts": [["Rome was the capital from founding until 286 AD.", "Constantinople became eastern capital in 330 AD."]],
    "ground_truth": ["Rome was the capital, with Constantinople as the eastern capital after 330 AD."]
}

dataset = Dataset.from_dict(data)
results = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision])
print(results)
# Output: {"faithfulness": 0.85, "answer_relevancy": 0.92, "context_precision": 0.90}
```

RAGAS uses LLM calls internally to compute faithfulness and answer relevance, which is more accurate than the overlap-based approximation from the raw build. It handles edge cases, multi-sentence answers, and partial grounding correctly.

For agent trajectory logging in Braintrust:

```python
import braintrust

# Log each tool call as a span
with braintrust.start_span(name="agent_run") as span:
    for tool_call in agent_trace:
        with span.start_span(name=tool_call["tool"]) as tool_span:
            tool_span.log(input=tool_call["input"], output=tool_call["output"])
    
    # Custom trajectory scorer
    expected = ["search_knowledge_base", "read_document", "summarize"]
    actual = [step["tool"] for step in agent_trace if step["type"] == "tool_call"]
    traj = eval_trajectory(expected, actual)
    span.log(scores={"trajectory_order": traj["order_score"]})
```

**RAGAS vs custom for agents:**

```
RAGAS                              CUSTOM
-----                              ------
Designed for RAG pipelines         Required for agent trajectory evals
Opinionated, fast to set up        More work, but fits your specific agent
Faithfulness uses LLM calls        You control what "correct" means
context_precision is well-tested   Your trajectory eval knows your tools
Does not handle tool sequences     Handles any multi-step pattern
```

The rule of thumb: use RAGAS for RAG. Build custom evals for agents. Agent eval is system-specific because the correct tool sequence depends on your application's logic, not a generic metric.

> **Perspective shift:** Your agent passed all its unit tests (each tool tested independently), but end-to-end evals show 30% failure rate. What is the gap between tool-level tests and trajectory evals, and why can't one replace the other? Unit tests verify each tool in isolation: given this input, return this output. They cannot test whether the agent calls the right tools in the right order given a real user query. A tool can work perfectly and still cause an agent failure if it is called at the wrong time, called twice when once would suffice, or never called when it should have been. Trajectory evals test the agent's decision-making over a sequence of steps. The two tests are orthogonal.

---

## SHIP IT

The artifact for this lesson is `outputs/skill-multistep-eval.md`: a complete guide for evaluating RAG and agent systems with the RAG Triad and trajectory eval patterns.

---

## EVALUATE IT

**How to know your multi-step evals are working:**

Component isolation test: deliberately break one component. Return random chunks from the retriever (ignore the query). Verify that context relevance drops toward 0 while faithfulness temporarily stays stable (the generator is still grounded in the random chunks, just the wrong ones) and answer relevance also drops. If your metrics move in the expected direction, they are measuring independently.

Trajectory coverage check: list your agent's five most common failure modes from production logs (wrong tool, correct tool in wrong order, double call, premature termination, infinite loop). Verify your trajectory eval has a test case for each one. A trajectory eval that only checks for exact sequence match will miss partial-credit failures.

Correlation with user satisfaction: run your component evals on 50 real traces. Separately collect user satisfaction ratings or thumbs up/down signals for the same traces. Compute the correlation between each component score and user satisfaction. High faithfulness correlation confirms the metric is measuring something users care about. Low correlation means the metric is not capturing the real failure mode.

RAGAS calibration: RAGAS uses an LLM judge internally. Run RAGAS on 10 cases where you know the correct faithfulness rating by hand. If RAGAS agrees with your manual ratings at least 80% of the time, it is calibrated for your domain. If not, use a custom faithfulness prompt tuned to your content domain.
