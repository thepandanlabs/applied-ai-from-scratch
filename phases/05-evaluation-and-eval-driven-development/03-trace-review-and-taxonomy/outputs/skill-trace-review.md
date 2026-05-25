---
name: skill-trace-review
description: Guide for conducting systematic trace reviews on multi-step AI systems, including the standard failure taxonomy and triage process
version: "1.0"
phase: "05"
lesson: "03"
tags: [eval, traces, debugging, observability, failure-taxonomy, rag, agents]
---

# Skill: Systematic Trace Review

Use this guide when a multi-step AI system is producing wrong outputs and you need to identify which step is responsible. Trace review is the debugging layer above error analysis: error analysis names the failure category, trace review locates the root cause.

---

## The Standard Trace Schema

Every trace should capture:

```json
{
  "trace_id": "short unique id",
  "timestamp": "ISO 8601",
  "input": {"query": "the original user input"},
  "steps": [
    {
      "name": "retrieve",
      "input": {"query": "..."},
      "output": ["chunk1", "chunk2"],
      "latency_ms": 120,
      "error": null
    },
    {
      "name": "rerank",
      "input": {"chunks": ["..."]},
      "output": ["chunk2"],
      "latency_ms": 45,
      "error": null
    },
    {
      "name": "generate",
      "input": {"query": "...", "context": ["chunk2"]},
      "output": "the final answer",
      "latency_ms": 890,
      "error": null
    }
  ],
  "output": "the final answer",
  "total_latency_ms": 1055,
  "failure": false,
  "failure_step": null,
  "notes": ""
}
```

Fields to never omit: `trace_id`, `timestamp`, `input`, `steps`, `output`, `failure`.

---

## The Standard Failure Taxonomy

These categories cover the majority of failures in RAG and agent systems. Adapt as needed for your specific architecture.

### retrieval_failure

**Definition:** The retrieval step failed to return chunks relevant to the query.

**Symptoms:**
- Final output says "I don't have information about that" when the information exists
- Final output answers a different question than was asked
- Retrieved chunks are topically irrelevant to the query

**Probable causes:** Weak embedding model, query too short or ambiguous, chunks too coarse, missing content in the knowledge base.

**Proposed fixes:** Query rewriting, hybrid search (BM25 + vector), finer chunking, re-embed with a better model.

**Test case template:** For query X, assert that the top-1 retrieved chunk has cosine similarity > 0.75 with the ground-truth answer.

---

### rerank_failure

**Definition:** Relevant chunks were retrieved but dropped by the reranker.

**Symptoms:**
- Retrieval step output includes the correct chunk
- Rerank step output does NOT include the correct chunk
- Final output is missing the correct information

**Probable causes:** Rerank threshold too aggressive, rerank model not suited to the domain, cross-encoder confused by long chunks.

**Proposed fixes:** Raise the rerank threshold, use a domain-specific rerank model, log the score that caused the relevant chunk to be dropped.

**Test case template:** For query X, assert that if chunk C is in the retrieve output, it remains in the rerank output.

---

### reasoning_failure

**Definition:** The context was correct and complete, but the model drew the wrong conclusion.

**Symptoms:**
- All relevant chunks are present in the generate step input
- Final answer is logically incorrect despite correct context
- No hallucinated content; the model just reasoned wrong

**Probable causes:** Ambiguous prompt instructions, conflicting information in chunks, model inference failure on complex multi-hop questions.

**Proposed fixes:** Add chain-of-thought instructions, simplify the question, break multi-hop queries into sub-queries.

**Test case template:** For query X with context C (correct chunks), assert the final answer matches expected answer Y.

---

### formatting_failure

**Definition:** The answer is factually correct but presented in the wrong format.

**Symptoms:**
- Answer contains correct information in the wrong structure
- Bullet list returned when a single value was expected
- Markdown formatting in a plain-text response context

**Probable causes:** Inconsistent output format instructions, model defaulting to its training distribution.

**Proposed fixes:** Add explicit format instructions to the system prompt, add output examples, use structured output (JSON mode, Pydantic).

**Test case template:** Assert that the output matches a regex or schema for the expected format.

---

### hallucination

**Definition:** The model generates content not present in (and contradicted by) the retrieved context.

**Symptoms:**
- Final answer contains specific facts not present in any retrieved chunk
- Final answer contradicts a retrieved chunk
- Confidently stated wrong information

**Probable causes:** Model prior knowledge overriding context, insufficient grounding instruction in system prompt, chunks don't contain enough detail.

**Proposed fixes:** Add "answer only from the provided context" instruction, reduce temperature, use citation grounding (ask model to cite specific chunks).

**Test case template:** For query X with context C, assert that every specific claim in the output is present (as a substring or semantic match) in at least one chunk in C.

---

### refusal

**Definition:** The model declines to answer when it should answer.

**Symptoms:**
- "I can't help with that" for a question clearly within scope
- Model asks for clarification when the query is unambiguous
- Over-cautious safety response for a benign query

**Probable causes:** System prompt too restrictive, safety fine-tuning overgeneralizing, query triggers a false-positive safety pattern.

**Proposed fixes:** Adjust system prompt scope instructions, add examples of in-scope questions, use a model with configurable safety settings.

**Test case template:** For query X, assert that the output does NOT contain refusal phrases ("I can't", "I'm not able to", "I don't have access to").

---

### tool_failure

**Definition (agents only):** A tool call errored, returned an unexpected format, or timed out.

**Symptoms:**
- Step error field is non-null
- Tool returned an error JSON that the model didn't handle
- Tool timed out and model hallucinated an answer

**Probable causes:** API outage, malformed tool call parameters, exceeded rate limit.

**Proposed fixes:** Add retry logic, add error handling in the tool wrapper, add a fallback response for tool failures.

**Test case template:** Assert that tool errors result in a graceful fallback response, not a hallucinated answer.

---

## The Triage Process (Step by Step)

Given a trace where the final output is wrong:

1. Read the final output. What kind of failure is it? (Wrong fact, missing info, wrong format, etc.)
2. Look at the generate step input. Was the relevant information present in the context? If yes, the failure is in generate (reasoning_failure, hallucination, or formatting_failure). If no, go to step 3.
3. Look at the rerank step output. Was the relevant chunk present? If yes, the failure is in generate (see step 2). If no, go to step 4.
4. Look at the retrieve step output. Was the relevant chunk present? If yes, failure is rerank_failure. If no, failure is retrieval_failure.
5. Write the failure_step into the trace and add a note explaining what you found.

---

## Blank Taxonomy Template

Copy and fill in for your specific system:

```markdown
## Failure Taxonomy: [Your System Name]

### [category_name]
**Definition:**
**Symptoms:**
**Probable causes:**
**Proposed fixes:**
**Test case template:**
**Example trace IDs:** [fill in after review]
**Count in sample:** 0

---
```

---

## Reviewing a Batch of Traces

For each review session:

1. Sample 20-30 traces from production (random sample, not just failures)
2. For each failure trace, run the triage process and assign a failure_step
3. Fill in the taxonomy with example trace IDs per category
4. Compute: total traces, failure rate, failure counts per category
5. Prioritize: which category has the highest count? What is the proposed fix?

Stop when the last 10 traces added no new categories (saturation) or when you've reviewed 50 traces, whichever comes first.
