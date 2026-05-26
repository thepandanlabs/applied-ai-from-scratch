"""
Lesson 01-01: Request Anatomy - System, User, Assistant
Phase 01: Prompt and Context Engineering

Demonstrates the three-role conversation structure of the Anthropic Messages API.
Every concept in the lesson is executable here.
"""

import anthropic

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Demo 1: Single-turn request - raw dict construction
# ---------------------------------------------------------------------------

def demo_single_turn() -> None:
    """A single-turn request built as plain Python dicts."""
    print("=" * 60)
    print("DEMO 1: Single-turn request")
    print("=" * 60)

    messages = [
        {"role": "user", "content": "What is the capital of France?"}
    ]

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        system="You are a geography assistant. Answer in one sentence.",
        messages=messages
    )

    print(f"Response: {response.content[0].text}")
    print(f"Stop reason: {response.stop_reason}")
    print(f"Tokens: {response.usage.input_tokens} in / {response.usage.output_tokens} out")


# ---------------------------------------------------------------------------
# Demo 2: Multi-turn request - manually built conversation history
# ---------------------------------------------------------------------------

def demo_multi_turn() -> None:
    """Manually build a 3-turn conversation and send it as a single API call."""
    print("\n" + "=" * 60)
    print("DEMO 2: Multi-turn request (manual history)")
    print("=" * 60)

    # The messages array is just a list. The model reads it top to bottom.
    messages = [
        {"role": "user",      "content": "My name is Alex. Remember it."},
        {"role": "assistant", "content": "Got it, Alex. How can I help you?"},
        {"role": "user",      "content": "What is my name?"},
    ]

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        system="You are a helpful assistant.",
        messages=messages
    )

    print(f"Response: {response.content[0].text}")
    print("\nNow remove the first two turns and ask the same question...")

    # Remove the context - the model will not know the name
    messages_no_context = [
        {"role": "user", "content": "What is my name?"},
    ]

    response2 = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=128,
        system="You are a helpful assistant.",
        messages=messages_no_context
    )

    print(f"Response (no context): {response2.content[0].text}")
    print("=> Context removed = information lost. There is no memory between calls.")


# ---------------------------------------------------------------------------
# Demo 3: Role validation - catching structural errors
# ---------------------------------------------------------------------------

def validate_messages(messages: list) -> list[str]:
    """
    Validate a messages array for structural correctness.
    Returns a list of error strings (empty list = valid).
    """
    errors = []

    if not messages:
        errors.append("messages array is empty")
        return errors

    if messages[0]["role"] != "user":
        errors.append(f"First message must be 'user', got '{messages[0]['role']}'")

    for i in range(1, len(messages)):
        prev_role = messages[i - 1]["role"]
        curr_role = messages[i]["role"]
        if prev_role == curr_role:
            errors.append(
                f"Turn {i}: consecutive '{curr_role}' messages not allowed "
                f"(index {i-1} and {i})"
            )

    return errors


def demo_validation() -> None:
    """Show role validation catching structural problems."""
    print("\n" + "=" * 60)
    print("DEMO 3: Role structure validation")
    print("=" * 60)

    valid_messages = [
        {"role": "user",      "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
        {"role": "user",      "content": "How are you?"},
    ]
    errors = validate_messages(valid_messages)
    print(f"Valid messages: {errors or 'OK'}")

    invalid_messages = [
        {"role": "user",  "content": "First message"},
        {"role": "user",  "content": "Second message"},   # two user turns in a row
    ]
    errors = validate_messages(invalid_messages)
    print(f"Invalid messages (double user): {errors}")

    starts_with_assistant = [
        {"role": "assistant", "content": "I speak first"},
        {"role": "user",      "content": "OK"},
    ]
    errors = validate_messages(starts_with_assistant)
    print(f"Invalid messages (starts with assistant): {errors}")


# ---------------------------------------------------------------------------
# Demo 4: Interactive chat loop - shows manual turn management
# ---------------------------------------------------------------------------

def chat(system_prompt: str = "You are a helpful assistant.") -> None:
    """
    Simple REPL demonstrating manual turn management.
    The messages list grows by 2 each turn (user + assistant).
    """
    messages = []
    print("\n" + "=" * 60)
    print("DEMO 4: Chat loop with manual history")
    print("Type 'quit' to exit. Watch the input token count grow each turn.")
    print("=" * 60 + "\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system=system_prompt,
            messages=messages
        )

        assistant_text = response.content[0].text

        # Append the assistant response - required for coherent next turn
        messages.append({"role": "assistant", "content": assistant_text})

        print(f"\nClaude: {assistant_text}")
        print(f"[{len(messages)} turns | {response.usage.input_tokens} input tokens "
              f"| {response.usage.output_tokens} output tokens]\n")


# ---------------------------------------------------------------------------
# Demo 5: System prompt isolation - same question, 3 different behaviors
# ---------------------------------------------------------------------------

def demo_system_prompt_impact() -> None:
    """Show that the system parameter fundamentally changes model behavior."""
    print("\n" + "=" * 60)
    print("DEMO 5: System prompt isolation")
    print("=" * 60)

    question = "What is machine learning?"

    system_prompts = [
        ("Formal",     "You are a technical writer. Use formal academic language."),
        ("One word",   "You are a minimalist. Respond in exactly one word."),
        ("JSON",       'You respond only in JSON format: {"answer": "..."}'),
    ]

    for label, system in system_prompts:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=128,
            system=system,
            messages=[{"role": "user", "content": question}]
        )
        print(f"\n[{label}] {response.content[0].text[:120]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    demo_single_turn()
    demo_multi_turn()
    demo_validation()
    demo_system_prompt_impact()

    print("\n" + "=" * 60)
    print("DEMO 4: Interactive chat (optional)")
    print("=" * 60)
    run_chat = input("Run interactive chat demo? (y/n): ").strip().lower()
    if run_chat == "y":
        chat("You are a helpful assistant. Be concise.")
