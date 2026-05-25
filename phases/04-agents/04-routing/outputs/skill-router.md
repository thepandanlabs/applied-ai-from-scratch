---
name: skill-router
description: Reusable router template with classification prompt, handler registration, and fallback dispatch
version: "1.0"
phase: "04"
lesson: "04"
tags: [routing, classification, dispatch, agents, cost-optimization]
---

# Skill: Router

A two-stage router: classify the input with a cheap fast model, then dispatch to the appropriate handler.
Use when different input types need different system prompts, models, or response strategies.

## Usage

```python
router = (
    Router(my_classifier_fn)
    .register("intent_a", handler_fn_a, "Description")
    .register("intent_b", handler_fn_b, "Description")
    .set_fallback(default_handler_fn, "Default handler")
)

result = router.route(user_message)
print(result["intent"])    # classified intent
print(result["response"])  # handler output
print(result["model_used"])
```

## Classification Prompt Template

The classification prompt is the most important part of a router.
Tight prompts with examples outperform long descriptive prompts.

```
SYSTEM PROMPT FOR CLASSIFIER:

You are a [domain] message classifier.
Classify the user's message into exactly one of these categories:

- category_a: [one-line description]
- category_b: [one-line description]
- category_c: [one-line description]

Examples:
- "[example message]" -> category_a
- "[example message]" -> category_b
- "[example message at the boundary]" -> category_b  (teach boundary cases)

Respond with ONLY the category name, nothing else.
```

Key rules:
- Keep the category list under 7 items. More than 7 is a sign the domain needs restructuring.
- Add examples for every boundary case you can identify in your data.
- Include the ambiguous cases that your team debates during design review.
- Ask for one word back. Do not ask for JSON or explanation - parse errors are not worth the detail.

## Full Router Class

```python
import anthropic
from typing import Callable

client = anthropic.Anthropic()


class Handler:
    def __init__(self, fn: Callable[[str], tuple[str, str]], description: str = ""):
        self.fn = fn
        self.description = description

    def run(self, message: str) -> tuple[str, str]:
        return self.fn(message)


class Router:
    """
    Classifies input and dispatches to registered handlers.
    Falls back to the default handler for unknown or unregistered intents.
    """
    def __init__(self, classifier_fn: Callable[[str], str]):
        self._classifier = classifier_fn
        self._handlers: dict[str, Handler] = {}
        self._fallback: Handler | None = None

    def register(self, intent: str, fn: Callable, description: str = "") -> "Router":
        self._handlers[intent] = Handler(fn, description)
        return self

    def set_fallback(self, fn: Callable, description: str = "") -> "Router":
        self._fallback = Handler(fn, description)
        return self

    def route(self, message: str) -> dict:
        intent = self._classifier(message)
        handler = self._handlers.get(intent)

        if handler is None:
            if self._fallback is not None:
                handler = self._fallback
                resolved_intent = f"fallback (classified: {intent})"
            else:
                return {"intent": intent, "error": f"No handler for '{intent}'"}
        else:
            resolved_intent = intent

        response_text, model_used = handler.run(message)
        return {"intent": resolved_intent, "response": response_text, "model_used": model_used}

    def list_handlers(self) -> None:
        for intent, handler in self._handlers.items():
            print(f"  {intent:<20} {handler.description}")
        if self._fallback:
            print(f"  {'(fallback)':<20} {self._fallback.description}")
```

## Classification Function Template

```python
VALID_INTENTS = ["intent_a", "intent_b", "intent_c"]

CLASSIFICATION_SYSTEM = """Your tight classification prompt here."""

def classify_intent(message: str) -> str:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",  # Use the cheapest fast model
        max_tokens=16,                       # One word back
        system=CLASSIFICATION_SYSTEM,
        messages=[{"role": "user", "content": message}]
    )

    intent = response.content[0].text.strip().lower().rstrip(".")

    if intent in VALID_INTENTS:
        return intent

    # Fuzzy match
    for valid in VALID_INTENTS:
        if valid in intent:
            return valid

    return VALID_INTENTS[0]  # Safe fallback to first/default intent
```

## Handler Function Signature

Each handler receives the original message and returns `(response_text, model_name)`.

```python
def handle_intent_a(message: str) -> tuple[str, str]:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",  # Cheapest model for simple intents
        max_tokens=256,
        system="Your focused system prompt for intent_a.",
        messages=[{"role": "user", "content": message}]
    )
    return response.content[0].text, "claude-3-5-haiku-20241022"


def handle_intent_b(message: str) -> tuple[str, str]:
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",  # More capable model for complex intents
        max_tokens=512,
        system="Your focused system prompt for intent_b.",
        messages=[{"role": "user", "content": message}]
    )
    return response.content[0].text, "claude-3-5-sonnet-20241022"
```

## Routing Table (fill in for your domain)

```
Intent          Model                      System prompt focus          Max tokens
-----------     --------------------------  ---------------------------  ----------
[intent_a]      claude-3-5-haiku-20241022  [concise task description]   256
[intent_b]      claude-3-5-haiku-20241022  [technical task]             512
[intent_c]      claude-3-5-sonnet-20241022 [nuanced task]               512
[intent_d]      (no model - rule/human)    [escalation or rule]         N/A
```

## Checklist Before Shipping

- [ ] Classification prompt has examples for every boundary case
- [ ] Fuzzy match fallback handles model returning extra punctuation or whitespace
- [ ] Every registered intent has a handler (no silent gaps)
- [ ] Fallback handler is set and tested
- [ ] Fallback rate is logged (alert if it exceeds 5%)
- [ ] Classification accuracy is measured on a labeled test set (target >90%)
- [ ] Per-intent latency is measured and within acceptable bounds
- [ ] Handler system prompts are tested independently on 20 samples each
- [ ] Escalation handler opens a real ticket or alerts a human (not just a text response in production)

## Cost Estimation

```
Before routing (all messages to expensive model):
  Average cost per message = [expensive_model_cost]

After routing (intent distribution * handler cost):
  cost = sum(
    intent_fraction[i] * (classifier_cost + handler_cost[i])
    for i in intents
  )
```

For a typical support distribution (60% FAQ, 20% technical, 12% account, 5% complaint, 3% escalate),
routing from Sonnet-only to Haiku-for-simple/Sonnet-for-complex saves 50-65% per message.
