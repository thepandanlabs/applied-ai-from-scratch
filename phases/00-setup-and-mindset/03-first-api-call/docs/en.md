# First API Call: Streaming, Tokens, and the Response Object

> Non-streaming blocks. Streaming flows. Understanding what the response object tells you is how you debug every AI feature you will ever build.

**Type:** Build
**Languages:** Both (Python + TypeScript)
**Prerequisites:** 00-01 (Dev Environment), 00-02 (API Keys)
**Time:** ~45 min
**Learning Objectives:**
- Make a non-streaming API call and inspect every field of the response object
- Make a streaming API call and accumulate the stream correctly
- Read input and output token counts from the response
- Understand when to use streaming vs. non-streaming in production

---

## The Problem

You wire up your first AI feature. It works fine in your test notebook: you call the API, get a response, display it. You ship it. Users complain the page freezes for 4 seconds, then text appears all at once. Someone on your team suggests "just add a loading spinner." You add the spinner. Users still complain: they can see the response starting to form elsewhere and want to read along as it generates.

The fix is streaming. But streaming is not a drop-in swap -- you have to accumulate the chunks, handle the stop event, and count tokens differently. The second problem is that even on non-streaming calls, most engineers look only at the text and ignore the metadata: token counts, stop reasons, and model version. Those fields are where you find cost anomalies, truncated responses, and context window violations before they become production bugs.

This lesson walks through both patterns completely, using the same prompt.

---

## The Concept

### The Request-Response Cycle

```
NON-STREAMING (blocks until complete):

Client                          Anthropic API
  |                                   |
  |--- POST /v1/messages ------------>|
  |                                   | (model generates entire response)
  |                                   | (might take 3-8 seconds for long outputs)
  |<-- 200 OK + full response --------|
  |                                   |
  Display text                        |

STREAMING (tokens arrive as generated):

Client                          Anthropic API
  |                                   |
  |--- POST /v1/messages ------------>|
  |<-- event: message_start ----------|
  |<-- event: content_block_start ----|
  |<-- event: content_block_delta ----|  (token by token)
  |<-- event: content_block_delta ----|  (token by token)
  |<-- event: content_block_delta ----|  (continues...)
  |<-- event: message_delta ----------|  (stop_reason + usage)
  |<-- event: message_stop -----------|
  |                                   |
  Display tokens as they arrive       |
```

### The Response Object Fields

Every non-streaming response from the Anthropic API has these top-level fields:

```
Message
  .id             str    "msg_01XYZ..."  (unique per call)
  .type           str    "message"
  .role           str    "assistant"
  .model          str    "claude-3-5-haiku-20241022" (actual model used)
  .content        list   [ContentBlock, ...]
  .stop_reason    str    "end_turn" | "max_tokens" | "stop_sequence" | "tool_use"
  .stop_sequence  str?   None unless a stop_sequence was triggered
  .usage          Usage
      .input_tokens   int  (tokens in the prompt + system prompt)
      .output_tokens  int  (tokens the model generated)
```

The `stop_reason` field is critical. `"max_tokens"` means the model hit your limit and the response is truncated -- increase `max_tokens` or reduce your prompt. `"end_turn"` is the normal completion. Always check this field in production code.

### Streaming Events

During streaming, you receive a sequence of server-sent events. The SDK abstracts these into an iterable. The key delta type is `text_delta`, which contains a `text` field with the new chunk:

```
message_start         -> gives you message id and input_tokens
content_block_start   -> marks start of a content block (type="text")
content_block_delta   -> type="text_delta", delta.text = new chunk
message_delta         -> gives you stop_reason and output_tokens
message_stop          -> stream is done
```

---

## Build It

### Step 1: Non-Streaming Call

```python
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    messages=[
        {"role": "user", "content": "Explain what a context window is in one sentence."}
    ],
)

# The response object -- inspect every field
print("=== Response Object ===")
print(f"id:           {response.id}")
print(f"model:        {response.model}")
print(f"stop_reason:  {response.stop_reason}")
print(f"stop_sequence:{response.stop_sequence}")
print(f"input_tokens: {response.usage.input_tokens}")
print(f"output_tokens:{response.usage.output_tokens}")
print(f"content type: {response.content[0].type}")
print(f"\nText:\n{response.content[0].text}")
```

The `response.model` field tells you the exact model version used -- useful when you have multiple models configured and want to confirm which one handled a given request.

### Step 2: Check Stop Reason

```python
def safe_text(response: anthropic.types.Message) -> str:
    """
    Extract text from a response, raising if it was truncated.
    In production, you handle max_tokens by increasing the limit
    or splitting the task -- never silently return partial output.
    """
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Response truncated: {response.usage.output_tokens} tokens generated "
            f"but max_tokens was hit. Increase max_tokens or shorten the prompt."
        )
    return response.content[0].text
```

> **Real-world check:** You call the API with `max_tokens=50` and get back a stop_reason of `"max_tokens"`. Your user sees a sentence that ends mid-word. How would you explain to a non-technical product manager what happened and what the two options are to fix it?

### Step 3: Streaming Call

```python
print("\n=== Streaming Call ===")

accumulated_text = ""

with client.messages.stream(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    messages=[
        {"role": "user", "content": "Explain what a context window is in one sentence."}
    ],
) as stream:
    for text_chunk in stream.text_stream:
        print(text_chunk, end="", flush=True)
        accumulated_text += text_chunk

print()  # newline after streaming

# After the stream closes, get the final message for metadata
final_message = stream.get_final_message()
print(f"\nStop reason:  {final_message.stop_reason}")
print(f"Input tokens: {final_message.usage.input_tokens}")
print(f"Output tokens:{final_message.usage.output_tokens}")
print(f"Accumulated text length: {len(accumulated_text)} chars")
```

The `stream.text_stream` property yields only the text deltas, skipping all the event scaffolding. It is the correct abstraction for most use cases. Use `stream.get_final_message()` after the `with` block exits to get usage and stop reason.

### Step 4: Token Counting Without an API Call

```python
# Count tokens before sending (to avoid context window violations)
token_count = client.messages.count_tokens(
    model="claude-3-5-haiku-20241022",
    messages=[
        {"role": "user", "content": "Explain what a context window is in one sentence."}
    ],
)
print(f"\nToken count (pre-flight): {token_count.input_tokens} tokens")
```

Use this before sending large prompts to verify you are within the context window limit.

---

## Use It

The `client.messages.stream()` context manager is the production pattern for streaming. Here is the full TypeScript equivalent alongside Python, showing how both patterns look in each language:

```python
# Python -- production streaming pattern
import anthropic
from dotenv import load_dotenv

load_dotenv()

def stream_response(prompt: str, system: str = "") -> tuple[str, anthropic.types.Usage]:
    """
    Stream a response, returning (full_text, usage).
    Suitable for web server endpoints that stream to the client.
    """
    client = anthropic.Anthropic()
    accumulated = []

    messages_kwargs = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        messages_kwargs["system"] = system

    with client.messages.stream(**messages_kwargs) as stream:
        for chunk in stream.text_stream:
            accumulated.append(chunk)
            # In a web server: yield chunk to the HTTP response here

    final = stream.get_final_message()
    return "".join(accumulated), final.usage


text, usage = stream_response("What is the capital of France? One word.")
print(f"Response: {text}")
print(f"Usage: {usage.input_tokens} in / {usage.output_tokens} out")
```

The TypeScript version (`code/main.ts`) uses the same pattern with `async/await` and `for await` over the stream.

> **Perspective shift:** Non-streaming is not just slower -- it ties up your server process while waiting for the full response. In a web server handling concurrent requests, a 5-second non-streaming call blocks that thread for 5 seconds. Streaming lets you start sending bytes to the user immediately while the model continues generating, which is both a UX improvement and a server efficiency improvement. The tradeoff: streaming requires you to handle partial state, which adds complexity to error handling and logging.

---

## Ship It

The artifact for this lesson is a skill card for the first API call patterns.

See `outputs/skill-first-api-call.md`.

---

## Evaluate It

Your first API call setup is correct when all of these pass:

```python
# Run with: uv run python -c "exec(open('checks.py').read())"
# Or step through manually:

import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

# 1. Non-streaming response has expected fields
r = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=32,
    messages=[{"role": "user", "content": "Reply with exactly: CHECK OK"}],
)
assert r.stop_reason in ("end_turn", "max_tokens", "stop_sequence"), f"Unexpected: {r.stop_reason}"
assert r.usage.input_tokens > 0, "Input tokens should be > 0"
assert r.usage.output_tokens > 0, "Output tokens should be > 0"
assert len(r.content) > 0, "Content should not be empty"
print(f"OK: non-streaming response valid. stop_reason={r.stop_reason}")

# 2. Stop reason "max_tokens" is detectable
r2 = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=5,  # intentionally tiny
    messages=[{"role": "user", "content": "Write a 500-word essay about the ocean."}],
)
assert r2.stop_reason == "max_tokens", f"Expected max_tokens, got {r2.stop_reason}"
print(f"OK: max_tokens stop reason detected correctly")

# 3. Streaming accumulates correctly
with client.messages.stream(
    model="claude-3-5-haiku-20241022",
    max_tokens=32,
    messages=[{"role": "user", "content": "Reply with exactly: STREAM OK"}],
) as stream:
    chunks = list(stream.text_stream)
full_text = "".join(chunks)
final = stream.get_final_message()
assert len(full_text) > 0, "Accumulated stream text should not be empty"
assert final.usage.output_tokens > 0, "Output tokens should be > 0 after streaming"
print(f"OK: streaming accumulated {len(chunks)} chunks, {final.usage.output_tokens} tokens")

print("\nAll API call checks passed.")
```
