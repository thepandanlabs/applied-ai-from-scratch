---
name: skill-first-api-call
description: Reference patterns for non-streaming and streaming Anthropic API calls, with stop reason handling and token accounting
version: "1.0"
phase: "00"
lesson: "03"
tags: [api, streaming, tokens, stop-reason, python, typescript]
---

# First API Call Patterns

## Non-Streaming (Python)

```python
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    system="You are a helpful assistant.",  # optional
    messages=[
        {"role": "user", "content": "Your prompt here"}
    ],
)

# Always check stop_reason before using the text
if response.stop_reason == "max_tokens":
    raise RuntimeError("Response truncated -- increase max_tokens")

text = response.content[0].text
input_tokens = response.usage.input_tokens
output_tokens = response.usage.output_tokens
```

## Streaming (Python)

```python
accumulated = []

with client.messages.stream(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Your prompt here"}],
) as stream:
    for chunk in stream.text_stream:
        print(chunk, end="", flush=True)  # or yield to HTTP response
        accumulated.append(chunk)

full_text = "".join(accumulated)
final = stream.get_final_message()   # get usage + stop_reason after stream closes
input_tokens = final.usage.input_tokens
output_tokens = final.usage.output_tokens
stop_reason = final.stop_reason
```

## Non-Streaming (TypeScript)

```typescript
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();  // reads ANTHROPIC_API_KEY from env

const response = await client.messages.create({
  model: "claude-3-5-haiku-20241022",
  max_tokens: 1024,
  messages: [{ role: "user", content: "Your prompt here" }],
});

if (response.stop_reason === "max_tokens") {
  throw new Error("Response truncated");
}

const text = response.content[0].type === "text" ? response.content[0].text : "";
const { input_tokens, output_tokens } = response.usage;
```

## Streaming (TypeScript)

```typescript
const chunks: string[] = [];

const stream = await client.messages.stream({
  model: "claude-3-5-haiku-20241022",
  max_tokens: 1024,
  messages: [{ role: "user", content: "Your prompt here" }],
});

for await (const event of stream) {
  if (event.type === "content_block_delta" && event.delta.type === "text_delta") {
    process.stdout.write(event.delta.text);
    chunks.push(event.delta.text);
  }
}

const finalMessage = await stream.finalMessage();
const fullText = chunks.join("");
const { input_tokens, output_tokens } = finalMessage.usage;
```

---

## Response Object Reference

```
Message
  .id             str    Unique ID for this response (useful for logging)
  .model          str    Exact model used (verify this matches what you requested)
  .stop_reason    str    "end_turn" | "max_tokens" | "stop_sequence" | "tool_use"
  .stop_sequence  str?   Set if a stop sequence was triggered
  .content        list   Always a list; index 0 is the main text block
    [0].type      str    "text" (or "tool_use" for tool calls)
    [0].text      str    The generated text
  .usage
    .input_tokens  int   Tokens in system prompt + all messages
    .output_tokens int   Tokens the model generated
```

---

## Stop Reason Decision Table

| stop_reason | Meaning | Action |
|-------------|---------|--------|
| `end_turn` | Normal completion | None needed |
| `max_tokens` | Truncated at limit | Increase max_tokens or split task |
| `stop_sequence` | Hit a custom stop sequence | Expected -- check your sequences |
| `tool_use` | Model wants to call a tool | Handle tool call and continue turn |

---

## Pre-flight Token Count

```python
# Count tokens without making a full API call
count = client.messages.count_tokens(
    model="claude-3-5-haiku-20241022",
    messages=[{"role": "user", "content": your_prompt}],
)
print(f"Input tokens: {count.input_tokens}")
# Claude context window: 200,000 tokens (input + output combined)
if count.input_tokens > 190_000:
    raise ValueError("Prompt too long -- reduce input before calling")
```

---

## When to Use Each Pattern

| Scenario | Pattern | Why |
|----------|---------|-----|
| Batch processing (offline) | Non-streaming | Simpler code, no partial state |
| API endpoint returning full JSON | Non-streaming | Client expects complete response |
| Web chat interface | Streaming | User sees text appear incrementally |
| CLI tool | Streaming | User sees progress immediately |
| Background job | Non-streaming | No display needed, simpler |
| Long generation (>500 tokens) | Streaming | Avoid timeout on slow connections |

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `AuthenticationError` | Bad or missing API key | Set ANTHROPIC_API_KEY env var |
| `RateLimitError` | Exceeded request quota | Retry with exponential backoff |
| `APIConnectionError` | Network issue | Check internet; retry |
| `InvalidRequestError` | Bad request format | Check model ID, max_tokens > 0 |
| Truncated text (no error) | stop_reason == "max_tokens" | Increase max_tokens |
| Empty content[0].text | Tool use response | Check content[0].type first |
