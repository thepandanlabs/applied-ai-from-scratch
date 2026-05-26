"""
Lesson 01-04: Context Engineering
Phase 01: Prompt and Context Engineering

Demonstrates context assembly: ordering, budgeting, and positioning
of instructions, retrieved documents, history, and user query.
Compares naive vs. engineered assembly on a retrieval task.
"""

import anthropic

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Sample data: a product knowledge base and a multi-turn conversation
# ---------------------------------------------------------------------------

# Simulated retrieved documents (ordered by relevance score, desc)
SAMPLE_DOCUMENTS = [
    """Product: DataPipe Pro v2.4
Pricing: $49/month (Starter), $149/month (Pro), $499/month (Enterprise).
Enterprise includes: unlimited pipelines, SLA of 99.9%, dedicated support.
Pro includes: up to 50 pipelines, 99.5% SLA, email support.""",

    """DataPipe Pro Changelog v2.4 (released March 2025):
- New: Real-time CDC (Change Data Capture) connector for PostgreSQL
- New: Parquet file export support
- Fixed: Memory leak in high-throughput Kafka consumers
- Improved: Dashboard load time reduced by 40%""",

    """DataPipe Pro Support Policy:
Enterprise customers: 24/7 phone and chat support, 2-hour response SLA.
Pro customers: Email support, 8-hour response SLA, business hours only.
Starter customers: Community forum only.
All tiers: Documentation at docs.datapipe.io""",

    """DataPipe Pro Integration Guide - PostgreSQL CDC:
Prerequisites: PostgreSQL 12+, logical replication enabled.
Step 1: Create a replication slot: SELECT pg_create_logical_replication_slot(...)
Step 2: Configure the DataPipe connector with slot name and publication name.
Step 3: Test connection from DataPipe dashboard.
Limitations: DDL changes (schema migrations) are not captured.""",

    """General cloud data pipeline comparison (industry context):
Alternatives to DataPipe Pro include Fivetran, Airbyte, and Stitch.
Fivetran: enterprise-focused, higher cost, 300+ connectors.
Airbyte: open-source, self-hosted option, strong community.
Stitch: simpler, fewer connectors, good for small teams.""",
]

# Simulated conversation history (prior turns)
SAMPLE_HISTORY = [
    {"role": "user",      "content": "We're evaluating DataPipe Pro for our engineering team."},
    {"role": "assistant", "content": "Happy to help. What aspects are most important to you?"},
    {"role": "user",      "content": "We need PostgreSQL CDC support and strong SLA guarantees."},
    {"role": "assistant", "content": "DataPipe Pro v2.4 added PostgreSQL CDC support. For SLA, what tier are you considering?"},
    {"role": "user",      "content": "We'd need the Enterprise tier."},
    {"role": "assistant", "content": "Enterprise provides 99.9% SLA and 24/7 support with 2-hour response time."},
]

INSTRUCTIONS = (
    "You are a helpful product support assistant for DataPipe Pro. "
    "Answer questions using only the provided documents. "
    "If the answer is not in the documents, say so. "
    "Be specific and cite which document your answer comes from."
)

CURRENT_QUERY = "What are the limitations of the PostgreSQL CDC connector, and does our Enterprise plan cover phone support?"


# ---------------------------------------------------------------------------
# Token estimation (rough)
# ---------------------------------------------------------------------------

def count_tokens_estimate(text: str) -> int:
    """Rough estimate: ~4 chars per token for English prose."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Naive assembly: everything dumped into one user message
# ---------------------------------------------------------------------------

def assemble_naive(
    query: str,
    documents: list[str],
    history: list[dict],
    instructions: str
) -> list[dict]:
    """
    Naive assembly: all content in one user message, arbitrary order.
    No token budgeting, no layer separation, history flattened to a string.
    """
    parts = []
    parts.append(f"Instructions: {instructions}\n")
    parts.append("Documents:\n" + "\n\n".join(
        f"Document {i+1}:\n{doc}" for i, doc in enumerate(documents)
    ))
    # History flattened to text (loses role alternation structure)
    if history:
        history_text = "\n".join(
            f"{turn['role'].title()}: {turn['content']}" for turn in history
        )
        parts.append(f"Previous conversation:\n{history_text}")
    parts.append(f"Question: {query}")

    return [{"role": "user", "content": "\n\n".join(parts)}]


# ---------------------------------------------------------------------------
# Engineered assembly: explicit layers, budget control, optimal ordering
# ---------------------------------------------------------------------------

def truncate_history(history: list[dict], max_tokens: int) -> list[dict]:
    """
    Keep the most recent turns that fit within max_tokens.
    Preserves the first turn pair (anchor) if possible.
    """
    if not history:
        return []

    # Count from the end, keeping recent turns
    result = []
    token_count = 0
    for turn in reversed(history):
        turn_tokens = count_tokens_estimate(turn["content"])
        if token_count + turn_tokens > max_tokens:
            break
        result.insert(0, turn)
        token_count += turn_tokens

    # Ensure we have valid alternating structure (start with user)
    while result and result[0]["role"] != "user":
        result = result[1:]

    return result


def truncate_documents(documents: list[str], max_tokens: int) -> list[str]:
    """
    Keep the most relevant documents (assumes ordered by relevance) that fit.
    """
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
    total_budget: int = 3000,
) -> tuple[str, list[dict]]:
    """
    Engineered context assembly.

    Layer ordering (by priority):
    1. System prompt: task instructions (primacy bias, highest authority)
    2. Retrieved documents: relevant content (main substance)
    3. Conversation history: recent turns (trimmed to budget)
    4. Current user query: last message (recency bias, freshest signal)

    Returns (system_prompt, messages_array).
    """
    # Budget allocation
    document_budget = int(total_budget * 0.55)   # documents get most of the budget
    history_budget  = int(total_budget * 0.30)   # recent history
    # instructions go in system prompt (no budget competition with messages)
    # query uses remaining tokens

    # Layer 1: Instructions as system prompt
    system = instructions

    # Layer 2: Retrieved documents (most relevant first, truncated)
    docs_included = truncate_documents(documents, document_budget)
    if docs_included:
        docs_block = "RELEVANT DOCUMENTS:\n\n" + "\n\n---\n\n".join(
            f"[Doc {i+1}]\n{doc}" for i, doc in enumerate(docs_included)
        )
    else:
        docs_block = ""

    # Layer 3: Conversation history (recent turns only)
    trimmed_history = truncate_history(history, history_budget)

    # Layer 4: Current query (last message for recency bias)
    if docs_block:
        final_user_content = f"{docs_block}\n\n---\n\nQUESTION: {query}"
    else:
        final_user_content = f"QUESTION: {query}"

    messages = list(trimmed_history) + [{"role": "user", "content": final_user_content}]

    return system, messages


# ---------------------------------------------------------------------------
# Demo: side-by-side comparison
# ---------------------------------------------------------------------------

def demo_comparison() -> None:
    print("=" * 70)
    print("DEMO: Naive vs. Engineered Context Assembly")
    print("=" * 70)
    print(f"\nQuery: {CURRENT_QUERY}\n")

    # Naive
    naive_messages = assemble_naive(
        CURRENT_QUERY, SAMPLE_DOCUMENTS, SAMPLE_HISTORY, INSTRUCTIONS
    )
    naive_input_tokens = count_tokens_estimate(
        "\n".join(m["content"] for m in naive_messages)
    )

    naive_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=naive_messages
    )

    # Engineered
    system, eng_messages = assemble_engineered(
        CURRENT_QUERY, SAMPLE_DOCUMENTS, SAMPLE_HISTORY, INSTRUCTIONS
    )
    eng_input_tokens = count_tokens_estimate(
        system + "\n".join(
            m["content"] for m in eng_messages
        )
    )

    eng_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system=system,
        messages=eng_messages
    )

    print("NAIVE ASSEMBLY OUTPUT:")
    print("-" * 40)
    print(naive_response.content[0].text)
    print(f"\n[Input tokens: {naive_response.usage.input_tokens}]")

    print("\n" + "=" * 70)
    print("ENGINEERED ASSEMBLY OUTPUT:")
    print("-" * 40)
    print(eng_response.content[0].text)
    print(f"\n[Input tokens: {eng_response.usage.input_tokens}]")

    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("-" * 40)
    print(f"Token difference: {naive_response.usage.input_tokens - eng_response.usage.input_tokens}")
    print(f"History turns included (naive): all (flattened)")
    print(f"History turns included (engineered): {len(trimmed_history(SAMPLE_HISTORY, 900))} of {len(SAMPLE_HISTORY)}")
    print(f"Documents included (naive): all {len(SAMPLE_DOCUMENTS)}")

    docs_inc = truncate_documents(SAMPLE_DOCUMENTS, int(3000 * 0.55))
    print(f"Documents included (engineered): {len(docs_inc)} of {len(SAMPLE_DOCUMENTS)} (by relevance)")


def trimmed_history(history, budget):
    result = []
    token_count = 0
    for turn in reversed(history):
        turn_tokens = count_tokens_estimate(turn["content"])
        if token_count + turn_tokens > budget:
            break
        result.insert(0, turn)
        token_count += turn_tokens
    return result


# ---------------------------------------------------------------------------
# Demo: lost-in-middle test
# ---------------------------------------------------------------------------

def demo_lost_in_middle() -> None:
    """
    Show how document position affects whether the model uses its contents.
    Place the most relevant document at position 1, 3, and 5 in a 5-doc context.
    """
    print("\n" + "=" * 70)
    print("DEMO: Lost-in-Middle Position Test")
    print("=" * 70)

    relevant_doc = SAMPLE_DOCUMENTS[3]  # PostgreSQL CDC limitations doc
    filler_docs = [SAMPLE_DOCUMENTS[1], SAMPLE_DOCUMENTS[4],
                   SAMPLE_DOCUMENTS[0], SAMPLE_DOCUMENTS[2]]

    query = "What are the specific limitations of the PostgreSQL CDC connector?"

    positions = {
        "First (position 1/5)": [relevant_doc] + filler_docs,
        "Middle (position 3/5)": filler_docs[:2] + [relevant_doc] + filler_docs[2:],
        "Last (position 5/5)":  filler_docs + [relevant_doc],
    }

    for label, docs in positions.items():
        system, messages = assemble_engineered(
            query, docs, [], INSTRUCTIONS, total_budget=2000
        )
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            system=system,
            messages=messages
        )
        mentions_ddl = "DDL" in response.content[0].text or "schema" in response.content[0].text.lower()
        print(f"\n[{label}]")
        print(f"  Mentions DDL limitation: {mentions_ddl}")
        print(f"  Response: {response.content[0].text[:150]}...")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Lesson 01-04: Context Engineering\n")
    print("Options:")
    print("  1. Compare naive vs. engineered assembly")
    print("  2. Lost-in-middle position test")
    print("  3. Run both\n")

    choice = input("Choice [1/2/3]: ").strip()

    if choice == "1":
        demo_comparison()
    elif choice == "2":
        demo_lost_in_middle()
    else:
        demo_comparison()
        demo_lost_in_middle()
