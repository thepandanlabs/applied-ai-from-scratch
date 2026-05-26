"""
Lesson 03: First API Call - Streaming, Tokens, and the Response Object

Demonstrates:
- Non-streaming call with full response object inspection
- Stop reason detection (end_turn vs max_tokens)
- Streaming call with chunk accumulation
- Pre-flight token counting
- Production streaming helper pattern

Run with: uv run python main.py
"""

import os
import anthropic
from dotenv import load_dotenv


def inspect_response(response: anthropic.types.Message) -> None:
    """Print all fields of a Message response object."""
    print("=== Response Object Fields ===")
    print(f"  id:            {response.id}")
    print(f"  type:          {response.type}")
    print(f"  role:          {response.role}")
    print(f"  model:         {response.model}")
    print(f"  stop_reason:   {response.stop_reason}")
    print(f"  stop_sequence: {response.stop_sequence}")
    print(f"  input_tokens:  {response.usage.input_tokens}")
    print(f"  output_tokens: {response.usage.output_tokens}")
    print(f"  content blocks:{len(response.content)}")
    for i, block in enumerate(response.content):
        print(f"    [{i}] type={block.type}, text_length={len(block.text) if block.type == 'text' else 'N/A'}")
    print(f"\n  Text:\n  {response.content[0].text[:200]}")


def safe_extract_text(response: anthropic.types.Message) -> str:
    """
    Extract text from response, raising if truncated (stop_reason == max_tokens).
    In production, truncation is a bug -- never silently return partial output.
    """
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Response truncated at {response.usage.output_tokens} output tokens. "
            "Increase max_tokens or split the task into smaller pieces."
        )
    if not response.content or response.content[0].type != "text":
        raise ValueError(f"Unexpected response content: {response.content}")
    return response.content[0].text


def stream_to_stdout(client: anthropic.Anthropic, prompt: str) -> tuple[str, anthropic.types.Usage]:
    """
    Stream a response to stdout, return (full_text, usage).
    This is the production pattern for server-sent events in a web API.
    """
    accumulated: list[str] = []

    print("=== Streaming (tokens appear as generated) ===")
    with client.messages.stream(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text_chunk in stream.text_stream:
            print(text_chunk, end="", flush=True)
            accumulated.append(text_chunk)

    print()  # newline after stream
    final_message = stream.get_final_message()
    return "".join(accumulated), final_message.usage


def demonstrate_max_tokens_truncation(client: anthropic.Anthropic) -> None:
    """Show what max_tokens truncation looks like in the response object."""
    print("\n=== max_tokens Truncation Demo ===")
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=10,  # intentionally tiny to force truncation
        messages=[
            {"role": "user", "content": "Write a 100-word explanation of how APIs work."}
        ],
    )
    print(f"stop_reason: {response.stop_reason}")  # "max_tokens"
    print(f"output_tokens generated: {response.usage.output_tokens}")
    print(f"truncated text: '{response.content[0].text}'")
    print("NOTE: this response is incomplete -- increase max_tokens in production")


def count_tokens_preflight(client: anthropic.Anthropic, prompt: str) -> int:
    """Count tokens before sending to catch context window violations."""
    count = client.messages.count_tokens(
        model="claude-3-5-haiku-20241022",
        messages=[{"role": "user", "content": prompt}],
    )
    return count.input_tokens


def main() -> None:
    load_dotenv()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set. Complete Lesson 02 first.")
        return

    client = anthropic.Anthropic(api_key=api_key)
    prompt = "Explain what a context window is in one sentence."

    # 1. Pre-flight token count
    print("=== Pre-flight Token Count ===")
    token_count = count_tokens_preflight(client, prompt)
    print(f"Input tokens for this prompt: {token_count}")
    print(f"Context window remaining: {200_000 - token_count:,} tokens")

    # 2. Non-streaming call with full inspection
    print("\n=== Non-Streaming Call ===")
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    inspect_response(response)

    # 3. Safe text extraction
    print("\n=== Safe Text Extraction ===")
    text = safe_extract_text(response)
    print(f"Extracted text: {text[:100]}...")

    # 4. Streaming the same prompt
    streamed_text, usage = stream_to_stdout(client, prompt)
    print(f"\nStream stats:")
    print(f"  input_tokens:  {usage.input_tokens}")
    print(f"  output_tokens: {usage.output_tokens}")
    print(f"  accumulated characters: {len(streamed_text)}")

    # 5. Truncation demo
    demonstrate_max_tokens_truncation(client)

    # 6. Compare token counts: non-streaming vs streaming
    print("\n=== Token Count Comparison ===")
    print(f"Non-streaming: {response.usage.input_tokens} in / {response.usage.output_tokens} out")
    print(f"Streaming:     {usage.input_tokens} in / {usage.output_tokens} out")
    print("(Should be identical for the same prompt)")


if __name__ == "__main__":
    main()
