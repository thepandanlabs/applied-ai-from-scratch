"""
Lesson 03-01: Function Calling Fundamentals
Raw tool dispatch loop using only the anthropic SDK. No frameworks.

Run: python main.py
Run with a specific question: python main.py --question "What are my recent transactions for acc_42?"
"""

import argparse
import json

import anthropic

# ---------------------------------------------------------------------------
# Tool schemas (raw dicts, the format the Anthropic API expects)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_account_balance",
        "description": (
            "Returns the current balance for a given account. "
            "Use this when the user asks about their balance, funds, or how much money is in an account."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "string",
                    "description": "The account identifier, e.g. 'acc_42' or 'acc_7891'.",
                }
            },
            "required": ["account_id"],
        },
    },
    {
        "name": "list_recent_transactions",
        "description": (
            "Returns the N most recent transactions for an account. "
            "Use this when the user asks about recent activity, charges, deposits, or spending history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "string",
                    "description": "The account identifier.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of transactions to return. Defaults to 5. Maximum 20.",
                    "default": 5,
                },
            },
            "required": ["account_id"],
        },
    },
]

# ---------------------------------------------------------------------------
# Stub functions (replace with real DB queries in production)
# ---------------------------------------------------------------------------

def get_account_balance(account_id: str) -> dict:
    """
    Stub: returns a realistic fake balance.
    Production: return db.query("SELECT balance FROM accounts WHERE id = ?", account_id)
    """
    stub_data = {
        "acc_42":   {"balance": 14.22,    "currency": "USD", "account_id": "acc_42"},
        "acc_99":   {"balance": 8_204.50, "currency": "USD", "account_id": "acc_99"},
        "acc_7891": {"balance": 0.00,     "currency": "USD", "account_id": "acc_7891"},
    }
    if account_id not in stub_data:
        return {"error": f"Account {account_id!r} not found.", "account_id": account_id}
    return stub_data[account_id]


def list_recent_transactions(account_id: str, limit: int = 5) -> dict:
    """
    Stub: returns realistic fake transaction history.
    Production: return db.query("SELECT ... FROM transactions WHERE account_id = ? LIMIT ?", ...)
    """
    stub_transactions: dict[str, list[dict]] = {
        "acc_42": [
            {"date": "2026-05-24", "description": "Coffee Shop",       "amount": -4.50,    "type": "debit"},
            {"date": "2026-05-23", "description": "Payroll Deposit",   "amount": 2_000.00, "type": "credit"},
            {"date": "2026-05-22", "description": "Grocery Store",     "amount": -87.33,   "type": "debit"},
            {"date": "2026-05-21", "description": "Streaming Service", "amount": -15.99,   "type": "debit"},
            {"date": "2026-05-20", "description": "ATM Withdrawal",    "amount": -60.00,   "type": "debit"},
        ],
        "acc_99": [
            {"date": "2026-05-24", "description": "Wire Transfer In",  "amount": 5_000.00, "type": "credit"},
            {"date": "2026-05-22", "description": "Online Purchase",   "amount": -129.99,  "type": "debit"},
        ],
    }
    txns = stub_transactions.get(account_id, [])
    return {
        "account_id": account_id,
        "transactions": txns[:limit],
        "count": min(limit, len(txns)),
    }


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

FUNCTION_MAP = {
    "get_account_balance": get_account_balance,
    "list_recent_transactions": list_recent_transactions,
}


def dispatch_tool_call(tool_name: str, tool_input: dict) -> str:
    """Look up and call the right function. Returns a JSON string."""
    if tool_name not in FUNCTION_MAP:
        return json.dumps({"error": f"Unknown tool: {tool_name!r}"})
    result = FUNCTION_MAP[tool_name](**tool_input)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool dispatch loop
# ---------------------------------------------------------------------------

def run_with_tools(user_message: str, verbose: bool = True) -> str:
    """
    Full two-round-trip tool-use dispatch loop.

    Round 1: Send user message + tool schemas. LLM returns tool_use block.
    Round 2: Execute tools, send results. LLM returns final text answer.
    """
    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": "user", "content": user_message}]

    if verbose:
        print(f"\n[user] {user_message}")

    # --- Round 1: get tool call request ---
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )

    if verbose:
        print(f"[api]  stop_reason={response.stop_reason}")

    # Model answered directly without needing a tool.
    if response.stop_reason == "end_turn":
        final_text = response.content[0].text
        if verbose:
            print(f"[assistant] {final_text}")
        return final_text

    # Collect tool_use blocks.
    tool_uses = [block for block in response.content if block.type == "tool_use"]

    if not tool_uses:
        # Unexpected: fall through to text.
        text = next((b.text for b in response.content if hasattr(b, "text")), "")
        return text

    # Append the full assistant response (tool_use blocks included) to message history.
    messages.append({"role": "assistant", "content": response.content})

    # Execute each tool and collect results.
    tool_results = []
    for tool_use in tool_uses:
        if verbose:
            print(f"[tool] {tool_use.name}({json.dumps(tool_use.input)})")
        result_str = dispatch_tool_call(tool_use.name, tool_use.input)
        if verbose:
            print(f"[result] {result_str[:120]}")
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": result_str,
        })

    # Append all results as a single user turn.
    messages.append({"role": "user", "content": tool_results})

    # --- Round 2: get final natural-language answer ---
    final_response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        tools=TOOLS,
        messages=messages,
    )

    final_text = next(
        (b.text for b in final_response.content if hasattr(b, "text")), ""
    )
    if verbose:
        print(f"[assistant] {final_text}")
    return final_text


# ---------------------------------------------------------------------------
# Pydantic schema generation (USE IT section)
# ---------------------------------------------------------------------------

def pydantic_schema_demo() -> None:
    """
    Demonstrates generating Claude-compatible tool schemas from Pydantic models.
    No API call is made; this just prints the generated schema.
    """
    try:
        from pydantic import BaseModel, Field
        from functools import wraps
    except ImportError:
        print("Install pydantic: pip install pydantic")
        return

    class GetAccountBalanceInput(BaseModel):
        account_id: str = Field(
            description="The account identifier, e.g. 'acc_42' or 'acc_7891'."
        )

    class ListRecentTransactionsInput(BaseModel):
        account_id: str = Field(description="The account identifier.")
        limit: int = Field(
            default=5, ge=1, le=20,
            description="Number of transactions to return. Defaults to 5. Maximum 20."
        )

    def make_tool_schema(name: str, description: str, input_model: type) -> dict:
        schema = input_model.model_json_schema()
        schema.pop("title", None)
        return {"name": name, "description": description, "input_schema": schema}

    tools_from_pydantic = [
        make_tool_schema(
            "get_account_balance",
            "Returns the current balance for a given account.",
            GetAccountBalanceInput,
        ),
        make_tool_schema(
            "list_recent_transactions",
            "Returns the N most recent transactions for an account.",
            ListRecentTransactionsInput,
        ),
    ]

    print("\n=== Pydantic-generated schemas ===")
    print(json.dumps(tools_from_pydantic, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 03-01: Function Calling Fundamentals")
    parser.add_argument(
        "--question",
        default="What's my account balance for account acc_42?",
        help="The user question to send.",
    )
    parser.add_argument(
        "--pydantic",
        action="store_true",
        help="Show Pydantic schema generation instead of making an API call.",
    )
    args = parser.parse_args()

    if args.pydantic:
        pydantic_schema_demo()
        return

    print("=== 03-01: Function Calling Fundamentals ===")
    print("Tools registered:", list(FUNCTION_MAP.keys()))

    answer = run_with_tools(args.question)
    print(f"\nFinal answer:\n{answer}")

    # Second demo: transactions
    print("\n" + "=" * 50)
    run_with_tools(
        "Show me the last 3 transactions for account acc_42.",
    )


if __name__ == "__main__":
    main()
