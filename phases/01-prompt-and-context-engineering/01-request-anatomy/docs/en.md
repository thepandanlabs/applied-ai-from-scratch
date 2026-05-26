# Request Anatomy: System, User, Assistant

> The model doesn't remember anything. It re-reads the entire conversation every time.

**Type:** Build
**Languages:** Python
**Prerequisites:** Basic Python, `pip install anthropic`
**Time:** ~45 min
**Learning Objectives:**
- Describe the purpose of the system, user, and assistant roles and what each controls
- Construct a valid messages array manually without SDK abstractions
- Explain why the system prompt is not special memory but simply the first context the model reads
- Use the Anthropic SDK to send a correctly structured request
- Identify what breaks when roles are misused or conversation turns are malformed

---

## THE PROBLEM

You start using Claude's API and it works. You paste examples, tweak prompts, and get decent results. Then production breaks in ways that don't make sense: the model ignores your instructions partway through a conversation, starts responding in the wrong format, or "forgets" what you told it three turns ago.

The root cause is almost always the same: you don't have a mental model of what the model actually receives on each API call. You think the system prompt is a persistent configuration. You think the model "remembers" earlier turns. Neither is true.

Every API call sends a complete, fresh payload. The model reads it top to bottom, every time. If your context is wrong, your output is wrong. Understanding request anatomy is not optional background knowledge. It is the prerequisite for debugging every other prompt engineering problem.

---

## THE CONCEPT

### The Three Roles

Every request to the Anthropic Messages API is a list of messages, each with a role. There are three roles and each serves a distinct purpose:

```
SYSTEM        Sets the model's behavior, persona, and constraints.
              Not part of the messages array. Sent as a top-level parameter.
              The model treats it as authoritative context.

USER          The human turn. Your input, the user's input,
              or any content from outside the model.
              Alternates with assistant.

ASSISTANT     The model's output. In a multi-turn conversation,
              previous model responses are included here so the
              model can maintain coherence.
```

The key structural rule: `user` and `assistant` roles must alternate. You cannot have two user messages in a row. Every assistant turn follows a user turn.

### How the Model Sees a Conversation

This is what gets sent on the third turn of a conversation:

```
┌────────────────────────────────────────────────────────┐
│  SYSTEM (top-level parameter)                          │
│  "You are a code review assistant. Be concise."        │
├────────────────────────────────────────────────────────┤
│  USER  (turn 1)                                        │
│  "Review this function: def add(a, b): return a + b"   │
├────────────────────────────────────────────────────────┤
│  ASSISTANT  (turn 1)                                   │
│  "The function is correct. Consider adding type hints."│
├────────────────────────────────────────────────────────┤
│  USER  (turn 2)                                        │
│  "How would I add type hints?"                         │
├────────────────────────────────────────────────────────┤
│  ASSISTANT  (turn 2)   <-- model generates this now    │
└────────────────────────────────────────────────────────┘
```

There is no memory. There is no session state. The model reads this entire block and generates the next assistant turn. If you remove turn 1 from the messages array, the model has no idea what function it reviewed.

### The Forgetting Illusion

"But ChatGPT remembers my previous messages!" Yes: the application is storing them and sending them back on every call. The model itself has no memory between calls. The conversation only exists because your code (or the chat UI) appends each turn and resends the full history.

This means: context window size limits your effective conversation length, not any model memory limit. When the conversation gets too long, you either truncate old turns or the model stops seeing them.

---

## BUILD IT

### Constructing Requests Manually

Before using the SDK, build the request as raw Python dicts. This makes the structure concrete and removes any illusion that the SDK is doing something magical.

**Step 1: A single-turn request, no history.**

```python
import anthropic
import json

client = anthropic.Anthropic()

# The messages array: one user turn, no history
messages = [
    {"role": "user", "content": "What is the capital of France?"}
]

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    system="You are a geography assistant. Answer in one sentence.",
    messages=messages
)

print(response.content[0].text)
```

The `system` parameter is separate from `messages`. It sets the behavior, not the conversation.

**Step 2: A multi-turn request, manually constructed.**

Notice you are not calling a chat session object. You are building a plain list and passing it:

```python
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

print(response.content[0].text)
# Output: "Your name is Alex."
```

Now try removing the first two messages from that list. The model will say it doesn't know your name. There is no session. The context you send is the only context the model has.

**Step 3: Break it intentionally.**

Try sending two user messages in a row:

```python
# This will raise an API error
messages = [
    {"role": "user", "content": "First message"},
    {"role": "user", "content": "Second message"},  # invalid: two user turns in a row
]
```

The API rejects this. The alternating structure is a hard requirement, not a convention.

> **Real-world check:** Your multi-turn chatbot "forgets" the user's name after 10 turns. You haven't changed the code. What is the most likely cause, and where would you look first?

The most likely cause is context window management code that is trimming old turns to save tokens, and it's trimming the turns that contain the name. Look at how your application builds the `messages` array before each API call. Check whether you're sliding a window over the history, and if so, whether you've preserved critical context (like an initial user introduction) before truncating.

---

## USE IT

### The Anthropic SDK's `messages.create`

The SDK wraps the exact same structure. Nothing changes about the roles, the alternation rule, or the system parameter. The SDK adds type checking, retry logic, and response parsing.

```python
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    system="You are a precise technical writer. Use plain language.",
    messages=[
        {"role": "user", "content": "Explain what an API is in two sentences."}
    ]
)

# response.content is a list of content blocks
# For text responses, block.text contains the output
print(response.content[0].text)
print(f"\nTokens used: {response.usage.input_tokens} in / {response.usage.output_tokens} out")
```

The response object exposes `stop_reason` (`end_turn`, `max_tokens`, `stop_sequence`), `usage` for token counts, and `content` as a list of typed blocks. You'll use all three in production.

**Appending turns for a real conversation loop:**

```python
def chat(system_prompt: str) -> None:
    """Simple REPL demonstrating manual turn management."""
    client = anthropic.Anthropic()
    messages = []

    print("Type 'quit' to exit.\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() == "quit":
            break

        messages.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system=system_prompt,
            messages=messages
        )

        assistant_text = response.content[0].text
        # Append the assistant turn so the next call has full history
        messages.append({"role": "assistant", "content": assistant_text})

        print(f"Claude: {assistant_text}\n")
        print(f"[Context: {len(messages)} turns, "
              f"{response.usage.input_tokens} input tokens]\n")
```

Notice the pattern: append user turn, call API, append assistant response, repeat. The `messages` list is your conversation state. You own it.

> **Perspective shift:** A framework like LangChain "manages conversation history" for you automatically. What do you give up when you let the framework handle the messages array?

You give up visibility. When the model produces an unexpected response, the first question is always "what did the model actually receive?" With manual management, you can print `messages` at any point and see the exact payload. With a framework managing history, you need to know how to extract the framework's internal representation, which adds a debugging layer between you and the model. The model receives a JSON array. The closer you stay to that fact, the faster you debug.

---

## SHIP IT

The artifact this lesson produces is a request anatomy reference card. See `outputs/skill-request-anatomy.md`.

The reference captures the role definitions, the alternating structure rule, the system parameter semantics, and the common failure modes. Use it as a checklist when debugging multi-turn conversation bugs.

---

## EVALUATE IT

A solid understanding of request anatomy shows up in the ability to debug conversation failures without guessing. Here is how to verify the concepts stuck:

**Role structure.** Write a function `validate_messages(messages: list) -> list[str]` that returns a list of error strings for any violations: consecutive same-role messages, missing user turn at the start, assistant turn at the end (which would produce an empty continuation). Test it against 5 valid and 5 invalid message arrays.

**Context persistence.** Build a 5-turn conversation where the user mentions their name in turn 1 and asks about it in turn 5. Run it twice: once with full history, once with turns 2-3 removed. Verify the model answers correctly in the first case and says it doesn't know in the second. This is the "forgetting is data loss" test.

**Token growth.** Instrument the `chat` function to print `usage.input_tokens` after each turn. After 10 turns, plot the growth. It should be approximately linear with conversation length. Verify the growth rate matches the sum of all messages in the array, not just the latest user turn.

**System prompt isolation.** Run the same user message with 3 different system prompts: one asking for formal language, one asking for one-word answers, one asking for JSON output. Verify the outputs differ dramatically. This confirms the system parameter is actually setting model behavior, not just being ignored.
