---
name: skill-agentic-rag-loop
description: Documented pattern for when to use agentic RAG, how to implement the tool interface, set stopping conditions, and prevent runaway retrieval.
version: "1.0"
phase: "02"
lesson: "12"
tags: [rag, agentic-rag, tool-use, retrieval-loop, stopping-conditions]
---

# Skill: The Agentic RAG Loop

A documented pattern for when to use agentic RAG, how to implement the tool interface, how to set stopping conditions, and how to prevent runaway retrieval loops.

---

## When to Use Agentic RAG

Use agentic RAG when your question type violates the single-retrieval assumption:

| Question Type | Use? | Example |
|---|---|---|
| Single-topic lookup | No | "What does policy X say about vacation days?" |
| Multi-hop (answer requires chaining) | Yes | "What policies addressed the 2022 audit findings?" |
| Aggregation across documents | Yes | "What is the consensus on topic X across all papers?" |
| Disambiguation needed | Maybe | "What does the policy say about termination?" (employment vs. contract?) |
| Real-time (<1s latency required) | No | Each retrieval iteration adds 1-3 seconds |
| Simple chatbot, predictable queries | No | Overhead is pure cost |

**Rule of thumb:** if you can predict the retrieval query before the LLM runs, use static RAG. If the retrieval query depends on the result of a previous retrieval, use agentic RAG.

---

## The Tool Interface

### Tool definition (OpenAI function calling)

```python
SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": (
            "Search the document corpus for information relevant to the query. "
            "Use specific, targeted queries. "
            "Call multiple times with different queries to gather all needed information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A focused search query.",
                }
            },
            "required": ["query"],
        },
    },
}
```

### System prompt requirements

The system prompt must:
1. Tell the agent to search before answering
2. Tell the agent it can call the tool multiple times
3. Instruct the agent to use entities found in earlier results in subsequent queries
4. Define the stopping condition: only answer when you have enough information

```python
AGENT_SYSTEM_PROMPT = """You are a research assistant with access to a document search tool.

To answer a question:
1. Think about what information you need.
2. Use the search_documents tool to retrieve relevant information.
3. Based on what you find, decide whether to search again with a refined query.
4. When you have enough information, write a complete answer citing your sources.

Rules:
- Always search before answering. Do not answer from memory.
- If a search reveals a specific term or entity needed for follow-up, include it in the next query.
- If after 3-4 searches the information isn't in the corpus, say so explicitly."""
```

---

## The Loop Implementation

```python
def run_agentic_rag(question, corpus, max_iterations=5, token_budget=8000):
    """
    Standard agentic RAG loop.
    Copy and adapt this pattern for your use case.
    """
    client = OpenAI()
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    traces = []

    for iteration in range(max_iterations):
        # 1. Check token budget before each iteration
        estimated_tokens = sum(len(str(m.get("content", ""))) for m in messages) / 4
        if estimated_tokens > token_budget:
            return _force_final_answer(client, messages), traces, "token_budget"

        # 2. Call LLM
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=[SEARCH_TOOL],
            tool_choice="auto",
            temperature=0.0,
        )
        message = response.choices[0].message

        # 3. No tool calls = agent is done
        if not message.tool_calls:
            return message.content, traces, "agent_done"

        # 4. Process tool calls
        messages.append(message)
        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            query = args["query"]
            results = search_corpus(query, corpus)

            traces.append({"iteration": iteration + 1, "query": query, "results": results})

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(results),
            })

    # 5. Max iterations reached
    return _force_final_answer(client, messages), traces, "max_iterations"


def _force_final_answer(client, messages):
    """Request a final answer after the loop exits without the agent finishing."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages + [{
            "role": "user",
            "content": "Please provide your best answer based on what you've found so far."
        }],
        temperature=0.0,
    )
    return response.choices[0].message.content
```

---

## Stopping Conditions

You need at least two governors. Without them, a stuck agent will retrieve until you run out of tokens or money.

### 1. Max Iterations (hard stop)

```python
MAX_ITERATIONS = 5  # adjust based on your use case complexity

for iteration in range(MAX_ITERATIONS):
    ...  # agent loop
else:
    # Loop exhausted: force an answer
    final_answer = force_final_answer(client, messages)
```

Setting guidance:
- Simple document Q&A: max 3
- Multi-hop across well-structured corpus: max 4-5
- Open-ended research tasks: max 6-8

Each additional iteration adds 1-3 seconds of latency. Set max_iterations × typical_per_iteration_latency and check against your SLA.

### 2. Token Budget

```python
TOKEN_BUDGET = 8000  # in tokens; leaves room for generation

estimated_tokens = sum(len(str(m.get("content", ""))) for m in messages) / 4
if estimated_tokens > TOKEN_BUDGET:
    # Don't retrieve: generate with what we have
    return force_final_answer(client, messages)
```

Set the budget at 60-70% of your model's context window. This leaves space for the final generation pass.

### 3. Query Deduplication (loop prevention)

If the agent issues a query very similar to a previous one, it's stuck in a loop. Detect and break:

```python
def _is_duplicate_query(new_query: str, previous_queries: list[str], threshold=0.85) -> bool:
    """
    Simple string-overlap duplicate detection.
    For production: use embedding similarity instead.
    """
    for prev in previous_queries:
        overlap = len(set(new_query.lower().split()) & set(prev.lower().split()))
        total = len(set(new_query.lower().split()) | set(prev.lower().split()))
        if total > 0 and overlap / total > threshold:
            return True
    return False

# In the loop:
previous_queries = []
for tool_call in message.tool_calls:
    query = json.loads(tool_call.function.arguments)["query"]
    if _is_duplicate_query(query, previous_queries):
        # Skip this retrieval, return a message indicating no new info found
        tool_result = json.dumps([{"warning": "Duplicate query detected. No new results."}])
    else:
        previous_queries.append(query)
        tool_result = json.dumps(search_corpus(query, corpus))
```

---

## Preventing Runaway Retrieval Loops

The failure mode: the corpus doesn't contain what the agent is looking for. The agent retrieves, gets partial results, retrieves again with a variation, gets similar partial results, and repeats until max_iterations.

Signs you're seeing this:
- Most queries hitting max_iterations
- Traces show similar queries being issued repeatedly
- Agent never generates a confident answer

Fixes:
1. **Tell the agent to abstain**: Add to the system prompt: "If after 2-3 searches you cannot find the answer, say 'The corpus does not contain sufficient information to answer this question.'"
2. **Return confidence scores from retrieval**: If top-1 score < 0.3, tell the agent explicitly that no relevant documents were found.
3. **Fix the underlying problem**: Low match scores usually mean corpus/embedding mismatch or the question is genuinely out of scope.

```python
def search_with_confidence(query, corpus):
    results = search_corpus(query, corpus)
    if not results or results[0]["relevance_score"] < 0.3:
        return [{"message": "No highly relevant documents found for this query.", "results": results}]
    return results
```

---

## Trace Logging (Production Requirement)

Log every execution as a trace. Without this, debugging is guesswork.

```python
@dataclass
class AgentTrace:
    query_id: str           # Unique ID for this execution
    question: str
    iterations: list[dict]  # Each: {iteration, query, results, timestamp}
    final_answer: str
    total_tokens: int
    terminated_by: str      # "agent_done" | "max_iterations" | "token_budget"
    latency_ms: float
```

Minimum fields to log to your observability platform:
- `query_id` (for correlation)
- `retrieval_calls` (count: track over time for anomalies)
- `terminated_by` (high `max_iterations` rate = retrieval is broken)
- `total_tokens` (cost tracking)
- `latency_ms` (SLA monitoring)

---

## Cost Model

Rough cost estimate (gpt-4o-mini at $0.15/1M input tokens + $0.60/1M output):

| Calls | Input tokens | Output tokens | Cost per query |
|---|---|---|---|
| 1 (static RAG) | ~2,000 | ~200 | ~$0.0004 |
| 2 (simple multi-hop) | ~4,500 | ~300 | ~$0.0009 |
| 3 (complex multi-hop) | ~7,000 | ~400 | ~$0.0014 |
| 5 (max iterations) | ~11,000 | ~500 | ~$0.0022 |

At 10,000 queries/day with average 2.5 calls per query, expect ~$3.50/day in LLM costs: roughly 4x static RAG. Acceptable for multi-hop use cases; unjustifiable for simple Q&A.

---

## Common Mistakes

| Mistake | What Goes Wrong | Fix |
|---|---|---|
| No max_iterations | Agent loops forever on unanswerable questions | Always set max_iterations |
| max_iterations too high | Runaway cost and latency on stuck queries | Start at 4-5; only increase if you see legitimate need |
| No query deduplication | Agent rephrases and retrieves the same content repeatedly | Add similarity-based dedup on tool call queries |
| Not forcing a final answer | When max_iterations hits, return empty string | Always call force_final_answer() when loop exits |
| No trace logging | Can't debug failures or optimize the loop | Log every trace; it's the only way to see what's happening |
| Agentic RAG for every query | Latency and cost on simple queries that don't need it | Route: detect multi-hop queries and use agentic only for those |
