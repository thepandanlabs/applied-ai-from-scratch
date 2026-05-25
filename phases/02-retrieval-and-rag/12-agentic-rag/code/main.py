# pip install openai
"""
Lesson 12: Agentic RAG
======================
Build an agentic RAG system:
1. Define retrieval as a tool callable by an LLM
2. Build an agent loop: LLM decides whether to retrieve, calls the tool, decides again
3. Implement multi-hop retrieval: agent retrieves for part 1, uses results for part 2
4. Add stopping conditions (max iterations + token budget)
5. Compare single-pass vs. multi-hop on questions that require 2-3 retrieval calls

Run: python main.py
Requires OPENAI_API_KEY in environment.
"""

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI


# ---------------------------------------------------------------------------
# Document corpus
# Designed to require multi-hop retrieval for the demo questions
# ---------------------------------------------------------------------------

@dataclass
class Document:
    doc_id: str
    title: str
    text: str


CORPUS = [
    Document(
        doc_id="audit-2022",
        title="2022 Internal Audit Report",
        text=(
            "The 2022 internal audit identified three material control weaknesses: "
            "(1) inadequate segregation of duties in the accounts payable process, "
            "(2) missing dual-approval controls for wire transfers above $100,000, "
            "(3) insufficient logging of privileged database access. "
            "The audit committee requested remediation plans within 90 days."
        ),
    ),
    Document(
        doc_id="policy-ap-2023",
        title="Accounts Payable Policy Update (2023)",
        text=(
            "Following the 2022 audit findings regarding accounts payable segregation, "
            "the AP policy was revised in March 2023. Key changes: all invoice approvals "
            "now require dual authorization from different cost center managers. "
            "No single approver may both initiate and approve a payment."
        ),
    ),
    Document(
        doc_id="policy-wire-2023",
        title="Wire Transfer Control Policy (2023)",
        text=(
            "In response to the 2022 audit wire transfer finding, a new dual-approval "
            "workflow was implemented in February 2023. All wire transfers above $50,000 "
            "(down from $100,000) now require CFO sign-off. Transfers above $500,000 "
            "require both CFO and CEO authorization."
        ),
    ),
    Document(
        doc_id="policy-db-2023",
        title="Database Access Logging Policy (2023)",
        text=(
            "Following audit finding (3) regarding privileged database access, the "
            "security team deployed comprehensive audit logging on all production databases "
            "in January 2023. All privileged queries are now logged with user ID, timestamp, "
            "and query hash. Logs are retained for 24 months and reviewed weekly."
        ),
    ),
    Document(
        doc_id="metformin-overview",
        title="Metformin Clinical Overview",
        text=(
            "Metformin is a biguanide antidiabetic agent. Common side effects include "
            "gastrointestinal symptoms (nausea, diarrhea, abdominal discomfort) in up to "
            "30% of patients, particularly at initiation. Rare but serious: lactic acidosis "
            "(risk elevated in renal impairment). Metformin does not cause hypoglycemia "
            "when used as monotherapy."
        ),
    ),
    Document(
        doc_id="metformin-interactions",
        title="Metformin Drug Interaction Reference",
        text=(
            "Metformin interactions with cardiovascular drugs: ACE inhibitors and ARBs "
            "are generally safe with metformin — no pharmacokinetic interaction. "
            "Thiazide diuretics may reduce metformin efficacy and increase risk of "
            "volume depletion. Beta-blockers may mask hypoglycemic symptoms in combination "
            "therapy but do not interact pharmacokinetically with metformin."
        ),
    ),
    Document(
        doc_id="johnson-2023",
        title="Johnson et al. 2023: Diabetes-Hypertension Comorbidity Study",
        text=(
            "Johnson et al. (2023) examined 450 patients with type 2 diabetes and "
            "hypertension. The blood pressure medications used in the cohort: "
            "lisinopril (ACE inhibitor, 62%), amlodipine (calcium channel blocker, 28%), "
            "and hydrochlorothiazide (thiazide diuretic, 18%). The study measured glycemic "
            "outcomes over 24 months."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Retrieval function (replace with your vector store)
# ---------------------------------------------------------------------------

def _keyword_score(query: str, doc: Document) -> float:
    """Naive keyword overlap. Replace with cosine similarity in production."""
    q_tokens = set(re.findall(r'\b[a-z]+\b', query.lower()))
    d_tokens = Counter(
        re.findall(r'\b[a-z]+\b', (doc.title + " " + doc.text).lower())
    )
    overlap = sum(d_tokens[t] for t in q_tokens if t in d_tokens)
    return overlap / (len(q_tokens) + 1)


def search_corpus(query: str, corpus: list[Document], top_k: int = 2) -> list[dict]:
    """
    Search the corpus and return top-k results as serializable dicts.
    This is the function the LLM agent calls via the tool interface.
    """
    scored = [(_keyword_score(query, doc), doc) for doc in corpus]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "text": doc.text,
            "relevance_score": round(score, 3),
        }
        for score, doc in scored[:top_k]
        if score > 0  # Don't return zero-match results
    ]


# ---------------------------------------------------------------------------
# Tool schema and agent system prompt
# ---------------------------------------------------------------------------

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": (
            "Search the document corpus for information relevant to the query. "
            "Use focused, specific queries for best results. "
            "You can call this tool multiple times with different queries to gather "
            "all information needed before writing your final answer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A focused search query. Be specific. "
                        "If a previous search gave you a name or entity, "
                        "include it in the next query."
                    ),
                }
            },
            "required": ["query"],
        },
    },
}

AGENT_SYSTEM_PROMPT = """You are a research assistant with access to a document search tool.

To answer a question:
1. Think about what you need to find.
2. Use the search_documents tool to retrieve relevant information.
3. Read the results. If you need more information, search again with a refined query.
4. Once you have enough information, write a complete, well-cited answer.

Rules:
- Always search before answering. Do not answer from memory.
- If a search reveals a specific entity, term, or finding, use it in subsequent searches.
- Cite the document titles in your final answer.
- If you cannot find the answer after searching, say so explicitly."""


# ---------------------------------------------------------------------------
# Agent trace
# ---------------------------------------------------------------------------

@dataclass
class AgentTrace:
    """Complete execution record for one agentic RAG run."""
    question: str
    iterations: list[dict] = field(default_factory=list)
    final_answer: str = ""
    total_tokens: int = 0
    terminated_by: str = ""  # "agent_done" | "max_iterations" | "token_budget"

    def retrieval_count(self) -> int:
        return len(self.iterations)

    def all_retrieved_docs(self) -> list[str]:
        """Return all unique doc_ids retrieved across all iterations."""
        seen = set()
        result = []
        for iteration in self.iterations:
            for doc in iteration.get("results", []):
                if doc["doc_id"] not in seen:
                    seen.add(doc["doc_id"])
                    result.append(doc["doc_id"])
        return result


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def run_agentic_rag(
    question: str,
    corpus: list[Document],
    max_iterations: int = 5,
    token_budget: int = 8000,
    model: str = "gpt-4o-mini",
    verbose: bool = True,
) -> AgentTrace:
    """
    The agentic RAG loop.

    The LLM is given the question and a search tool.
    It decides when to retrieve, what to query for, and when to stop.
    The loop continues until the LLM stops calling tools or a governor kicks in.
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    trace = AgentTrace(question=question)

    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    if verbose:
        print(f"\n{'='*64}")
        print(f"AGENTIC RAG | Question: {question[:70]}")

    for iteration in range(max_iterations):
        # Rough token estimate for budget check
        total_chars = sum(
            len(str(m.get("content", ""))) for m in messages
        )
        estimated_tokens = total_chars / 4  # ~4 chars per token
        if estimated_tokens > token_budget:
            trace.terminated_by = "token_budget"
            if verbose:
                print(f"  [STOP] Token budget exhausted (~{estimated_tokens:.0f} tokens)")
            break

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[SEARCH_TOOL],
            tool_choice="auto",
            temperature=0.0,
        )

        message = response.choices[0].message
        trace.total_tokens += response.usage.total_tokens

        # No tool calls → agent is ready to answer
        if not message.tool_calls:
            trace.final_answer = message.content or ""
            trace.terminated_by = "agent_done"
            if verbose:
                print(f"  [DONE] Finished after {iteration + 1} iteration(s)")
            messages.append({"role": "assistant", "content": message.content})
            break

        # Append assistant message with tool calls
        messages.append(message)

        # Process each tool call
        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            query = args.get("query", "")

            if verbose:
                print(f"  [ITER {iteration+1}] Search: {query!r}")

            results = search_corpus(query, corpus)

            if verbose:
                for r in results:
                    print(f"    → [{r['doc_id']}] {r['title']} (score={r['relevance_score']})")

            trace.iterations.append({
                "iteration": iteration + 1,
                "query": query,
                "results": results,
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(results, indent=2),
            })

    else:
        # Exhausted max_iterations
        trace.terminated_by = "max_iterations"
        if verbose:
            print(f"  [STOP] Max iterations ({max_iterations}) reached")

        # Request a final answer based on what's been gathered
        follow_up = client.chat.completions.create(
            model=model,
            messages=messages + [{
                "role": "user",
                "content": "Based on the information gathered, please provide your best answer."
            }],
            temperature=0.0,
        )
        trace.final_answer = follow_up.choices[0].message.content or ""
        trace.total_tokens += follow_up.usage.total_tokens

    return trace


# ---------------------------------------------------------------------------
# Single-pass comparison
# ---------------------------------------------------------------------------

def single_pass_rag(
    question: str,
    corpus: list[Document],
    top_k: int = 3,
    model: str = "gpt-4o-mini",
    verbose: bool = True,
) -> str:
    """
    Naive single-pass RAG: one retrieval call, one generation call.
    Used as comparison baseline for multi-hop questions.
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    results = search_corpus(question, corpus, top_k=top_k)
    context = "\n\n".join(
        f"[{r['title']}]\n{r['text']}" for r in results
    )

    if verbose:
        print(f"\n  Retrieved for single-pass:")
        for r in results:
            print(f"    → [{r['doc_id']}] {r['title']}")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Answer the question using only the provided context. "
                           "Cite document titles in your answer.",
            },
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {question}",
            },
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def compute_retrieval_stats(traces: list[AgentTrace]) -> dict:
    """
    Compute aggregate statistics over a batch of agent traces.

    Use to monitor:
    - mean_calls: average number of retrieval calls per query
    - pct_3plus_calls: fraction of queries requiring 3+ calls (signal of retrieval issues)
    """
    call_counts = [t.retrieval_count() for t in traces]
    n = len(call_counts)
    return {
        "n_queries": n,
        "mean_calls": sum(call_counts) / n if n > 0 else 0,
        "max_calls": max(call_counts) if call_counts else 0,
        "pct_1_call": sum(1 for c in call_counts if c == 1) / n if n > 0 else 0,
        "pct_2_calls": sum(1 for c in call_counts if c == 2) / n if n > 0 else 0,
        "pct_3plus_calls": sum(1 for c in call_counts if c >= 3) / n if n > 0 else 0,
        "terminated_by": {
            t: sum(1 for trace in traces if trace.terminated_by == t)
            for t in ["agent_done", "max_iterations", "token_budget"]
        },
    }


def print_comparison_table():
    """Print the question type → approach comparison table."""
    print("\n" + "=" * 64)
    print("WHEN TO USE AGENTIC RAG")
    print("=" * 64)

    rows = [
        ("Simple Q&A, single topic", "No", "Adds latency, no benefit"),
        ("Multi-hop: answer requires chaining", "Yes", "Static RAG cannot chain"),
        ("Aggregation across 5+ documents", "Yes", "Agent retrieves iteratively"),
        ("Real-time (< 1s latency required)", "No", "Agent loops add 2-5s each"),
        ("Ambiguous query needing disambiguation", "Maybe", "Agent can retrieve to clarify"),
        ("Chatbot with predictable queries", "No", "Overhead not justified"),
    ]

    print(f"\n  {'Question Type':<45} {'Use Agentic?':>12} {'Reason'}")
    print("  " + "-" * 80)
    for qtype, use, reason in rows:
        print(f"  {qtype:<45} {use:>12}  {reason}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("Lesson 12: Agentic RAG")
    print("=" * 64)

    # -------------------------------------------------------------------------
    # Test 1: Multi-hop audit question (requires 2 retrieval steps)
    # -------------------------------------------------------------------------
    q1 = (
        "What policies did the company implement in response to the issues "
        "found in the 2022 audit?"
    )

    print("\n--- TEST 1: Multi-hop audit question ---")
    print("(Requires: retrieve audit findings → retrieve policies addressing those findings)\n")

    print("[SINGLE-PASS RAG]")
    naive1 = single_pass_rag(q1, CORPUS, verbose=True)
    print(f"\nAnswer:\n{naive1}\n")

    print("[AGENTIC RAG]")
    trace1 = run_agentic_rag(q1, CORPUS, max_iterations=5, verbose=True)
    print(f"\nAnswer:\n{trace1.final_answer}")
    print(f"\nRetrieval calls: {trace1.retrieval_count()}")
    print(f"Docs retrieved: {trace1.all_retrieved_docs()}")
    print(f"Tokens used: {trace1.total_tokens}")

    # -------------------------------------------------------------------------
    # Test 2: 3-hop medical question
    # -------------------------------------------------------------------------
    q2 = (
        "What are the side effects of metformin, and how do those interact with "
        "the blood pressure medications used in the Johnson et al. 2023 study?"
    )

    print("\n\n--- TEST 2: 3-hop medical question ---")
    print("(Requires: metformin side effects → Johnson study BP meds → interactions)\n")

    print("[SINGLE-PASS RAG]")
    naive2 = single_pass_rag(q2, CORPUS, verbose=True)
    print(f"\nAnswer:\n{naive2}\n")

    print("[AGENTIC RAG]")
    trace2 = run_agentic_rag(q2, CORPUS, max_iterations=5, verbose=True)
    print(f"\nAnswer:\n{trace2.final_answer}")
    print(f"\nRetrieval calls: {trace2.retrieval_count()}")
    print(f"Docs retrieved: {trace2.all_retrieved_docs()}")
    print(f"Tokens used: {trace2.total_tokens}")

    # -------------------------------------------------------------------------
    # Aggregate statistics
    # -------------------------------------------------------------------------
    print("\n\n--- RETRIEVAL STATISTICS ---")
    traces = [trace1, trace2]
    stats = compute_retrieval_stats(traces)
    print(f"Mean retrieval calls per query: {stats['mean_calls']:.1f}")
    print(f"Max calls on a single query:    {stats['max_calls']}")
    print(f"Queries needing 3+ calls:       {stats['pct_3plus_calls']:.0%}")
    print(f"Termination reasons:            {stats['terminated_by']}")

    # When to use agentic RAG
    print_comparison_table()

    print("\n" + "=" * 64)
    print("Key takeaway: Agentic RAG adds 1-3 extra retrieval calls on multi-hop")
    print("questions. Single-pass RAG answers only the first hop.")


if __name__ == "__main__":
    main()
