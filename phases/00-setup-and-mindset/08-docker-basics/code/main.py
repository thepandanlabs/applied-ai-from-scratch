"""
Lesson 08 - Docker Basics for AI Apps
Minimal Anthropic app that summarizes a hardcoded passage.
Run inside a container: docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY ai-summarizer
"""

import anthropic
import os
import sys

def get_client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        print("Run with: docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY ai-summarizer", file=sys.stderr)
        sys.exit(1)
    return anthropic.Anthropic(api_key=key)


TEXT = """
The transformer architecture, introduced in 2017, replaced recurrence with
self-attention. This allowed training to be fully parallelized across tokens,
which unlocked training on much larger datasets with more parameters. By 2020,
scaling these architectures produced models that generalized across tasks
without task-specific fine-tuning.
"""


def summarize(client: anthropic.Anthropic, text: str) -> str:
    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": f"Summarize the following in one sentence:\n\n{text.strip()}"
            }
        ]
    )
    return message.content[0].text


def main() -> None:
    client = get_client()

    print("Input:")
    print(TEXT.strip())
    print()

    print("Calling claude-3-5-haiku-20241022...")
    summary = summarize(client, TEXT)

    print("\nSummary:")
    print(summary)
    print()
    print("Done. Container exiting with code 0.")


if __name__ == "__main__":
    main()
