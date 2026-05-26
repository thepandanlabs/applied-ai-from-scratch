# Few-Shot and Chain-of-Thought

> Chain-of-thought works because it forces the model to spend tokens on reasoning before committing to an answer.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lesson 01 (Request Anatomy), Lesson 02 (Prompt Fundamentals), `pip install anthropic`
**Time:** ~60 min
**Learning Objectives:**
- Implement zero-shot, few-shot, and chain-of-thought prompting and observe the difference in output quality
- Explain why CoT improves reasoning on multi-step tasks
- Construct few-shot examples using the assistant turn in the messages array
- Combine few-shot and CoT for tasks that require both consistent format and careful reasoning
- Identify when each technique helps and when each fails

---

## THE PROBLEM

You're building a triage system that classifies customer support tickets by severity: Critical, High, Medium, Low. A zero-shot prompt gets it right 70% of the time. You need 95%+. You add examples to the prompt and get to 85%. Still not there. You try telling the model to "think carefully" and nothing changes.

The problem is that you're applying techniques without understanding the mechanism. Few-shot and chain-of-thought are not magic incantations. They work by changing what the model does with its compute before generating the answer. Knowing why they work tells you when to use them, how to combine them, and why they sometimes fail.

---

## THE CONCEPT

### Three Prompt Shapes

The structural difference between zero-shot, few-shot, and CoT:

```
ZERO-SHOT
┌──────────────────────────────────────────────────────┐
│ [Task instruction]                                   │
│ [Input]                                              │
│ -> Model generates answer directly                   │
└──────────────────────────────────────────────────────┘

FEW-SHOT
┌──────────────────────────────────────────────────────┐
│ [Task instruction]                                   │
│ [Example input 1] -> [Example output 1]              │
│ [Example input 2] -> [Example output 2]              │
│ [Example input 3] -> [Example output 3]              │
│ [Real input]                                         │
│ -> Model infers pattern and applies it               │
└──────────────────────────────────────────────────────┘

CHAIN-OF-THOUGHT
┌──────────────────────────────────────────────────────┐
│ [Task instruction + "reason step by step"]           │
│ [Input]                                              │
│ -> Model generates: reasoning... -> answer           │
└──────────────────────────────────────────────────────┘

FEW-SHOT + COT (combined)
┌──────────────────────────────────────────────────────┐
│ [Task instruction]                                   │
│ [Example input 1] -> [Reasoning 1] -> [Answer 1]     │
│ [Example input 2] -> [Reasoning 2] -> [Answer 2]     │
│ [Real input]                                         │
│ -> Model generates: reasoning... -> answer           │
└──────────────────────────────────────────────────────┘
```

### Why Few-Shot Works

Language models predict the next token based on patterns in context. When you include examples in the prompt, the model sees the input-output pattern and uses it as a template. The examples communicate format, vocabulary, and reasoning style more precisely than description alone.

Few-shot is most useful when: the output format is non-standard, the task requires a specific style or vocabulary, or zero-shot produces inconsistent structure.

Few-shot fails when: your examples don't cover the distribution of real inputs, the examples are too similar to each other, or the task requires reasoning that can't be demonstrated by examples alone.

### Why Chain-of-Thought Works

This is the mechanism, not the magic: CoT works because tokens are the model's compute. The model generates one token at a time. Each token it generates becomes part of its "scratchpad." By generating reasoning steps before the answer token, the model has more intermediate information available when it commits to the final answer.

Think of it as forcing the model to show its work. A math student who writes out steps is less likely to make an arithmetic error than one who tries to hold everything in their head and write only the final answer. Same mechanism.

CoT is most useful when: the task requires multi-step reasoning, calculations, or comparing multiple factors. CoT fails when: the task is a lookup (zero-shot or few-shot is faster and cheaper), or when the reasoning chain itself becomes confused and leads the model away from the right answer.

---

## BUILD IT

### Three Experiments

Run these in order. Each experiment uses the same task but changes the prompting approach.

**The task:** Severity classification for customer support tickets.

```python
import anthropic
import json

client = anthropic.Anthropic()

# Test tickets covering the full severity range
TEST_TICKETS = [
    "My account was charged twice for the same order. I need a refund.",
    "The entire payment service is down. No transactions are going through.",
    "How do I change my billing address?",
    "Users in the EU region cannot log in. This has been broken for 30 minutes.",
    "The font in the mobile app looks slightly different than the web version.",
]

SEVERITY_LEVELS = ["Critical", "High", "Medium", "Low"]
```

**Experiment 1: Zero-shot baseline.**

```python
ZERO_SHOT_PROMPT = """Classify the severity of this customer support ticket.
Severity levels: Critical, High, Medium, Low.

Output only the severity level. No explanation.

Ticket: {ticket}"""

def classify_zero_shot(ticket: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        messages=[{
            "role": "user",
            "content": ZERO_SHOT_PROMPT.format(ticket=ticket)
        }]
    )
    return response.content[0].text.strip()
```

**Experiment 2: Few-shot with examples in the prompt.**

```python
FEW_SHOT_PROMPT = """Classify the severity of this customer support ticket.
Severity levels: Critical, High, Medium, Low.

Examples:
Ticket: Our API is returning 500 errors for all requests. Production is down.
Severity: Critical

Ticket: The export to CSV function is producing incorrect totals.
Severity: High

Ticket: Can you add a dark mode option to the app?
Severity: Low

Ticket: The search results sometimes show duplicates.
Severity: Medium

Output only the severity level. No explanation.

Ticket: {ticket}"""

def classify_few_shot(ticket: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        messages=[{
            "role": "user",
            "content": FEW_SHOT_PROMPT.format(ticket=ticket)
        }]
    )
    return response.content[0].text.strip()
```

**Experiment 3: Chain-of-thought - reasoning before label.**

```python
COT_SYSTEM = """You are a support ticket triage specialist. When classifying tickets:
1. Assess: who is affected (one user vs. many vs. all)?
2. Assess: is revenue or core functionality impacted?
3. Assess: is this time-sensitive?
Then assign: Critical (total outage/data loss), High (major feature broken),
Medium (partial impact/workaround exists), Low (minor/cosmetic/question)."""

COT_USER_TEMPLATE = """Classify this ticket. Reason through the 3 questions,
then output your final answer as: SEVERITY: [level]

Ticket: {ticket}"""

def classify_cot(ticket: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        system=COT_SYSTEM,
        messages=[{
            "role": "user",
            "content": COT_USER_TEMPLATE.format(ticket=ticket)
        }]
    )
    return response.content[0].text.strip()
```

> **Real-world check:** You run all three experiments. Zero-shot and few-shot both classify "The entire payment service is down" as Critical. CoT also gets it right but uses 8x more output tokens. Your product gets 10,000 tickets per day. When is the CoT approach worth the cost, and when would you revert to few-shot?

Use CoT for the ambiguous middle tier: tickets that might be High or might be Critical, or Medium vs. High. For clear-cut cases at the extremes ("entire service down" or "how do I change my password"), a well-constructed few-shot prompt is accurate and cheaper. In production: route tickets to CoT only when few-shot returns Medium or High (the ambiguous range), and use fast/cheap classification for the extremes. A routing layer that applies the right technique per case is better than applying the most expensive technique to everything.

---

## USE IT

### Few-Shot with the SDK's Assistant Turn Pattern

The SDK's messages array supports a cleaner way to express few-shot examples: alternate user/assistant turns. This separates examples from instructions, making it easier to add, remove, or modify individual shots without touching the prompt logic.

```python
def classify_few_shot_sdk(ticket: str) -> str:
    """
    Few-shot using the messages array: examples as user/assistant pairs.
    Same examples as the inline prompt but structured as conversation turns.
    """
    messages = [
        # Example 1
        {"role": "user",      "content": "Ticket: Our API is returning 500 errors for all requests. Production is down."},
        {"role": "assistant", "content": "Critical"},

        # Example 2
        {"role": "user",      "content": "Ticket: The export to CSV function is producing incorrect totals."},
        {"role": "assistant", "content": "High"},

        # Example 3
        {"role": "user",      "content": "Ticket: Can you add a dark mode option to the app?"},
        {"role": "assistant", "content": "Low"},

        # Example 4
        {"role": "user",      "content": "Ticket: The search results sometimes show duplicates."},
        {"role": "assistant", "content": "Medium"},

        # The real ticket
        {"role": "user",      "content": f"Ticket: {ticket}"},
    ]

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        system="You are a support ticket triage specialist. Classify severity: Critical, High, Medium, Low. Output only the label.",
        messages=messages
    )
    return response.content[0].text.strip()
```

This is the same information as the inline few-shot prompt, organized differently. The messages array approach has one practical advantage: you can load examples from a database or config file and construct the array dynamically. The inline prompt approach requires string manipulation to add or remove examples.

> **Perspective shift:** A colleague argues that CoT is wasteful for a classification task because "the model already knows what Critical means." When would you push back on this?

Push back when the task has edge cases that require comparing multiple factors before deciding. "The model knows what Critical means" is true for prototypical cases. The hard cases are the middle ones: a payment bug that affects 2% of users (High or Critical?), a slow API that times out for large queries (Medium or High?). These require reasoning about scope and business impact. CoT earns its cost when the zero-shot and few-shot error rates are concentrated in ambiguous middle cases, not in clear-cut extremes. Run the ablation: if removing CoT only errors on edge cases, that's exactly when it matters.

---

## SHIP IT

The artifact this lesson produces is a few-shot and CoT pattern reference. See `outputs/skill-few-shot-cot.md`.

The reference captures the three prompt shapes, when to use each, the SDK messages-array pattern for structured few-shot, and the CoT trigger phrases that reliably activate step-by-step reasoning.

---

## EVALUATE IT

These techniques are only worth using if they improve accuracy on your specific task. Measuring improvement requires a labeled test set.

**Build a test set.** Collect or generate 20-30 labeled examples: real or realistic inputs with correct answers. For severity classification: 5 examples per tier is sufficient for basic evaluation. Label them yourself or with a domain expert. This is the minimum viable eval set.

**Baseline measurement.** Run zero-shot on all examples. Record accuracy per tier (Critical, High, Medium, Low) not just overall accuracy. Overall accuracy hides tier-specific failures.

**Few-shot measurement.** Run the few-shot version. Compare per-tier accuracy. Common finding: few-shot improves consistency more than accuracy. The model was classifying correctly but inconsistently formatting the output. Few-shot fixes that.

**CoT measurement.** Run the CoT version. Compare on the cases where zero-shot and few-shot failed. CoT should reduce errors on multi-factor cases (e.g., ambiguous scope). If CoT does not reduce errors on your specific failure cases, it is not the right tool for your task.

**Cost/accuracy trade-off.** For each technique: record average output tokens and average accuracy. Plot accuracy vs. token cost. The goal is the technique that achieves your accuracy target at the lowest token cost. For most production classification tasks, few-shot with 4-6 well-chosen examples hits the target without the token overhead of CoT.
