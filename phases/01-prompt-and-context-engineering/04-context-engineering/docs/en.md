# Context Engineering

> Context is the product. What you put in the window, and where you put it, determines what comes out.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lesson 01 (Request Anatomy), Lesson 02 (Prompt Fundamentals), `pip install anthropic`
**Time:** ~60 min
**Learning Objectives:**
- Describe the information hierarchy of the context window and how position affects salience
- Build a context assembly function that packs user query, retrieved documents, conversation history, and instructions in optimal order
- Explain primacy and recency bias and their effect on model attention
- Compare naive vs. engineered context assembly on a retrieval task
- Apply context budgeting: allocate token budget across context layers based on their priority

---

## THE PROBLEM

You build a RAG system. You retrieve the right documents. You include the user's question. But the model's answers are vague, miss key details from the documents, or drift back to general knowledge instead of answering from the retrieved content.

The retrieval is correct. The instructions are clear. The problem is context assembly: where the information sits in the window relative to everything else.

This is context engineering: not what you include, but how you arrange it. The model's attention is not uniform across the context window. Position matters. Volume matters. The signal-to-noise ratio matters. Getting this wrong produces models that have all the right information but still give wrong answers.

---

## THE CONCEPT

### The Context Window as Layers

Everything in a single API call competes for the model's attention within a fixed token budget. Information can be organized into layers by priority:

```
HIGH PRIORITY (processed with most weight)
    ┌─────────────────────────────────────────┐
    │  LAYER 1: Task instructions             │ <-- TOP: primacy bias
    │  What to do, how to respond, what       │
    │  format to use, what to prioritize.     │
    ├─────────────────────────────────────────┤
    │  LAYER 2: Relevant retrieved content    │
    │  Documents, facts, data directly        │
    │  relevant to the user's query.          │
    ├─────────────────────────────────────────┤
    │  LAYER 3: Conversation history          │
    │  Prior turns that establish context.    │
    │  Most recent turns matter most.         │
    ├─────────────────────────────────────────┤
    │  LAYER 4: The user's current query      │ <-- BOTTOM: recency bias
    │  What they actually asked right now.    │
    └─────────────────────────────────────────┘
LOW PRIORITY (at risk of being underweighted)
    - Anything in the middle of a long context
    - Redundant or contradictory content
    - Content not relevant to the current query
```

### Primacy and Recency Bias

Research on transformer attention patterns shows two consistent effects:

**Primacy bias:** Content at the very beginning of the context (the system prompt) receives strong attention. The model uses it as the authoritative frame for interpreting everything that follows.

**Recency bias:** Content near the end of the context (the final user message) receives strong attention because it is the most recent signal the model processes before generating its response.

**The danger zone:** Content sandwiched in the middle of a long context is most likely to be underweighted. A retrieved document that is relevant but buried between 10 other documents and a long conversation history is at risk of being ignored.

```
Token position in context:
0        25%      50%      75%      100%
|--------|--------|--------|--------|
^                                   ^
High attention                 High attention
(primacy)                      (recency)

                    ^
               Lower attention
               (lost in middle)
```

This is not a bug in the model. It is a property of how attention mechanisms work. The engineering response is to arrange information so that the most important content benefits from primacy or recency.

### Context Budgeting

Token budgets are real constraints. At 128k context, you can include a lot, but you still need to decide what earns its space. A rough allocation framework:

```
TYPICAL CONTEXT BUDGET ALLOCATION

  System instructions:     5-10%  (dense, high-priority)
  Retrieved documents:    40-60%  (the core content)
  Conversation history:   20-30%  (recent turns, trimmed)
  Current user query:      5-10%  (short, always included)
  Output headroom:        10-20%  (reserved for response)
```

The allocation shifts based on task type: a summarization task needs more document space; a chat task needs more history.

---

## BUILD IT

### Context Assembly Function

A context assembly function takes all the pieces and packs them in the right order with the right budget constraints.

**Step 1: Naive assembly (what most people do first).**

```python
import anthropic

client = anthropic.Anthropic()

def assemble_naive(
    query: str,
    documents: list[str],
    history: list[dict],
    instructions: str
) -> list[dict]:
    """Naive: stuff everything into one user message in arbitrary order."""
    content_parts = []
    content_parts.append(f"Instructions: {instructions}")
    content_parts.append(f"Documents:\n" + "\n\n".join(documents))
    # Flatten history into a string (loses structure)
    for turn in history:
        content_parts.append(f"{turn['role']}: {turn['content']}")
    content_parts.append(f"Question: {query}")

    full_content = "\n\n".join(content_parts)
    return [{"role": "user", "content": full_content}]
```

Problems with naive assembly: instructions are buried before documents, history is flattened (losing role structure), the user's query is at the end but mixed in with noise, no budget control.

**Step 2: Engineered assembly.**

```python
def count_tokens_estimate(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


def truncate_history(
    history: list[dict],
    max_tokens: int
) -> list[dict]:
    """Keep the most recent turns that fit within max_tokens."""
    result = []
    token_count = 0
    for turn in reversed(history):
        turn_tokens = count_tokens_estimate(turn["content"])
        if token_count + turn_tokens > max_tokens:
            break
        result.insert(0, turn)
        token_count += turn_tokens
    return result


def truncate_documents(
    documents: list[str],
    max_tokens: int
) -> list[str]:
    """Keep the most relevant documents (assumes ordered by relevance) that fit."""
    result = []
    token_count = 0
    for doc in documents:
        doc_tokens = count_tokens_estimate(doc)
        if token_count + doc_tokens > max_tokens:
            break
        result.append(doc)
        token_count += doc_tokens
    return result


def assemble_engineered(
    query: str,
    documents: list[str],
    history: list[dict],
    instructions: str,
    total_budget: int = 4000,
) -> tuple[str, list[dict]]:
    """
    Engineered context assembly with explicit layer ordering and token budgeting.

    Layer order (by priority):
    1. System prompt: instructions (primacy bias)
    2. Retrieved documents: most relevant content
    3. Conversation history: recent turns only
    4. User's current query: last message (recency bias)

    Returns: (system_prompt, messages_array)
    """
    # Budget allocation
    instruction_budget = int(total_budget * 0.10)
    document_budget   = int(total_budget * 0.50)
    history_budget    = int(total_budget * 0.25)
    # query gets the remainder; output is on top of total_budget

    # Layer 1: Instructions in system prompt (primacy)
    system = instructions[:instruction_budget * 4]  # rough char limit

    # Layer 2: Retrieved documents (most relevant first, truncated to budget)
    docs_included = truncate_documents(documents, document_budget)
    docs_block = ""
    if docs_included:
        docs_block = "RELEVANT DOCUMENTS:\n" + "\n\n---\n\n".join(
            f"[Doc {i+1}]\n{doc}" for i, doc in enumerate(docs_included)
        )

    # Layer 3: Conversation history (recent turns only, within budget)
    trimmed_history = truncate_history(history, history_budget)

    # Layer 4: Current query (recency)
    # Combine docs + query into the final user message
    if docs_block:
        final_user_content = f"{docs_block}\n\nQUESTION: {query}"
    else:
        final_user_content = f"QUESTION: {query}"

    # Build messages array: history turns + final user message
    messages = list(trimmed_history) + [{"role": "user", "content": final_user_content}]

    return system, messages
```

> **Real-world check:** Your engineered context assembly is working well, but you notice that in conversations longer than 20 turns, the model starts contradicting information it "knew" in turn 5. The retrieved documents are fine. What is the most likely cause, and which budget parameter would you adjust?

The most likely cause is that the history budget is too small to include turn 5, so recent turns are trimmed back to turn 15 or so. The model is not seeing the earlier context. Adjust the `history_budget` percentage upward (from 25% to 35-40%), or add logic to always preserve the first N turns of history (the "anchor turns") before trimming from the middle outward. The tradeoff is fewer tokens for documents, so also check whether all retrieved documents are still necessary.

---

## USE IT

### Comparing Naive vs. Engineered Assembly

The measurable difference shows up when the model needs to answer from specific details in retrieved documents while maintaining conversational coherence.

```python
def run_comparison(
    query: str,
    documents: list[str],
    history: list[dict],
    instructions: str
) -> None:
    """Run both assembly strategies and compare outputs."""

    # Naive assembly
    naive_messages = assemble_naive(query, documents, history, instructions)
    naive_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=naive_messages
    )

    # Engineered assembly
    system, eng_messages = assemble_engineered(
        query, documents, history, instructions
    )
    eng_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system=system,
        messages=eng_messages
    )

    print("NAIVE ASSEMBLY:")
    print(naive_response.content[0].text)
    print(f"\nInput tokens: {naive_response.usage.input_tokens}")

    print("\nENGINEERED ASSEMBLY:")
    print(eng_response.content[0].text)
    print(f"\nInput tokens: {eng_response.usage.input_tokens}")
```

What to look for in the comparison:

1. Does the engineered version cite specific details from the documents while the naive version speaks in generalities?
2. Does the engineered version maintain conversational coherence (references to earlier turns) while the naive version misses context?
3. Are the input token counts similar? If the naive version has significantly more tokens, it's padding the context with unneeded content.

> **Perspective shift:** A colleague says "context engineering is premature optimization. Just include everything and let the model figure it out." When does this attitude start costing money and accuracy?

It costs money when the naive approach includes documents, history, and boilerplate at 3x the tokens needed, tripling your input costs at scale. It costs accuracy when the context becomes so long that critical information falls into the middle (the lost-in-middle problem). At 10,000 API calls per day, a 3x token inefficiency adds up to real budget impact. At 50+ documents in context, the lost-in-middle effect is measurable. Context engineering is not premature optimization when you have a concrete token budget or a retrieval task where precision matters.

---

## SHIP IT

The artifact this lesson produces is a context engineering guide. See `outputs/skill-context-engineering.md`.

The guide captures the layer ordering model, the budgeting framework, the lost-in-middle warning, and the assembly function pattern for reuse across projects.

---

## EVALUATE IT

Context engineering quality shows up in retrieval accuracy: does the model answer from the provided documents or fall back to general knowledge?

**Attribution test.** Give the model 3 documents with distinct, unique facts. Ask a question whose answer is only in document 2. Score: does the model answer from document 2 or hallucinate from general knowledge? Run this with naive vs. engineered assembly. The engineered version should show higher attribution accuracy.

**Lost-in-middle test.** Create a context with 10 documents. Put the relevant one at position 1, 5, and 10 across separate runs. Measure answer quality. If quality is notably lower when the relevant document is at position 5, you have a lost-in-middle problem. Fix: put the most relevant document last (closest to the query) or first (benefits from primacy).

**Budget utilization.** After each call, check `response.usage.input_tokens`. Is it close to your budget, far under it (over-trimming), or over it (not trimming enough)? Log this across production calls to calibrate your budget percentages.

**History truncation correctness.** Build a test conversation where a critical fact is mentioned in turn 1. Ask about it in turn 15. Verify the model still answers correctly when your history budget includes turn 1. Then reduce the history budget until turn 1 is dropped and verify the model fails. This gives you the minimum history budget for your specific application.
