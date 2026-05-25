"""
Lesson 04-04: Pattern: Routing
Phase 04: Agents - Patterns That Survive Production

A customer support router that:
  1. Classifies intent using a cheap/fast model (claude-3-5-haiku)
  2. Dispatches to the right handler (different system prompts, different models)

Intent categories: simple_faq | account_issue | complaint | escalate | technical
"""

import anthropic
from typing import Callable

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

VALID_INTENTS = ["simple_faq", "account_issue", "complaint", "escalate", "technical"]

CLASSIFICATION_SYSTEM = """You are a customer support message classifier.
Classify the user's message into exactly one of these categories:

- simple_faq: General questions about the product, pricing, hours, features, policies
- account_issue: Questions about the user's specific account, billing, subscription, or data
- complaint: Expressions of frustration, negative experience, or request for compensation
- escalate: Threats of legal action, regulatory complaints, or requests to speak to a manager
- technical: Bug reports, error messages, integration issues, or technical troubleshooting

Examples:
- "What are your business hours?" -> simple_faq
- "I've been charged twice this month" -> account_issue
- "I've been charged twice and I'm furious, this is unacceptable" -> complaint
- "I'm contacting my bank and filing a complaint with the FTC" -> escalate
- "I'm getting a 502 error when I try to log in via SSO" -> technical

Respond with ONLY the category name, nothing else. No explanation, no punctuation."""


def classify_intent(message: str) -> str:
    """
    Classify a customer message into one of 5 intent categories.
    Uses the fast/cheap model. Returns a lowercase intent string.
    Validates against known intents and falls back to 'simple_faq' on parse error.
    """
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        system=CLASSIFICATION_SYSTEM,
        messages=[{"role": "user", "content": message}]
    )

    intent = response.content[0].text.strip().lower().rstrip(".")

    if intent in VALID_INTENTS:
        return intent

    # Fuzzy match: check if any valid intent appears in the response
    for valid in VALID_INTENTS:
        if valid in intent:
            return valid

    return "simple_faq"  # safe fallback


# ---------------------------------------------------------------------------
# Handler system prompts
# ---------------------------------------------------------------------------

FAQ_SYSTEM = """You are a concise customer support assistant for a SaaS product.
Answer only what is asked. Keep responses under 3 sentences.
If you don't have specific information, say so briefly and offer to connect the customer with a human support agent.
Do not speculate or invent policy details."""

TECHNICAL_SYSTEM = """You are a technical support specialist for a SaaS product.
Provide step-by-step troubleshooting instructions.
If the user has not provided an error message, ask for it.
Confirm whether the issue is user-side (configuration) or service-side (bug).
Escalate to engineering if you identify a confirmed service bug."""

ACCOUNT_SYSTEM = """You are an account support specialist for a SaaS product.
You help with billing questions, subscription changes, account access, and data requests.
Always verify the user's identity before discussing specific account details.
Be precise about what actions are possible and what requires manual review.
Do not make promises about specific outcomes without confirming with the back-end team."""

COMPLAINT_SYSTEM = """You are a senior customer relations specialist.
Lead with empathy: acknowledge the customer's frustration directly and specifically.
Do not start with apologies alone - propose a concrete next step.
Validate their experience before explaining what happened or what will change.
Do not promise outcomes you cannot guarantee.
If the issue involves a financial impact, acknowledge it explicitly."""


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------

def handle_simple_faq(message: str) -> tuple[str, str]:
    """Handle general FAQ questions. Fast, cheap model."""
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=256,
        system=FAQ_SYSTEM,
        messages=[{"role": "user", "content": message}]
    )
    return response.content[0].text, "claude-3-5-haiku-20241022"


def handle_technical(message: str) -> tuple[str, str]:
    """Handle technical issues and bug reports. Fast model, higher max_tokens."""
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        system=TECHNICAL_SYSTEM,
        messages=[{"role": "user", "content": message}]
    )
    return response.content[0].text, "claude-3-5-haiku-20241022"


def handle_account_issue(message: str) -> tuple[str, str]:
    """Handle account and billing issues. More capable model for accuracy."""
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=512,
        system=ACCOUNT_SYSTEM,
        messages=[{"role": "user", "content": message}]
    )
    return response.content[0].text, "claude-3-5-sonnet-20241022"


def handle_complaint(message: str) -> tuple[str, str]:
    """Handle complaints and negative experiences. Empathy-first prompt."""
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=512,
        system=COMPLAINT_SYSTEM,
        messages=[{"role": "user", "content": message}]
    )
    return response.content[0].text, "claude-3-5-sonnet-20241022"


def handle_escalate(message: str) -> tuple[str, str]:
    """
    Handle escalation requests. In production: open a high-priority ticket,
    page on-call, or transfer to a human agent. This stub returns a transfer message.
    """
    response = (
        "I'm connecting you with a senior member of our team right away. "
        "You'll receive a personal response within 2 business hours. "
        "Your case reference is #[TICKET_ID]. We take your concerns seriously "
        "and will follow up directly."
    )
    return response, "no-model (escalation to human)"


# ---------------------------------------------------------------------------
# Raw dispatch function
# ---------------------------------------------------------------------------

HANDLER_REGISTRY: dict[str, Callable[[str], tuple[str, str]]] = {
    "simple_faq":    handle_simple_faq,
    "technical":     handle_technical,
    "account_issue": handle_account_issue,
    "complaint":     handle_complaint,
    "escalate":      handle_escalate,
}


def route_message(message: str, verbose: bool = True) -> dict:
    """
    Classify a customer message and dispatch to the appropriate handler.
    Returns a dict with: intent, response, model_used.
    """
    intent = classify_intent(message)

    if verbose:
        print(f"  Classified: {intent}")

    handler = HANDLER_REGISTRY.get(intent, handle_simple_faq)
    response_text, model_used = handler(message)

    return {
        "intent": intent,
        "response": response_text,
        "model_used": model_used,
        "classification_model": "claude-3-5-haiku-20241022"
    }


# ---------------------------------------------------------------------------
# Router class with registered handlers and fallback
# ---------------------------------------------------------------------------

class Handler:
    def __init__(self, fn: Callable[[str], tuple[str, str]], description: str = ""):
        self.fn = fn
        self.description = description

    def run(self, message: str) -> tuple[str, str]:
        return self.fn(message)


class Router:
    """
    A composable router: classifies input, dispatches to registered handlers.
    Falls back to the fallback handler for unknown or unregistered intents.
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
                return {
                    "intent": intent,
                    "error": f"No handler registered for '{intent}' and no fallback set."
                }
        else:
            resolved_intent = intent

        response_text, model_used = handler.run(message)
        return {
            "intent": resolved_intent,
            "response": response_text,
            "model_used": model_used
        }

    def list_handlers(self) -> None:
        print("Registered handlers:")
        for intent, handler in self._handlers.items():
            print(f"  {intent:<20} {handler.description}")
        if self._fallback:
            print(f"  {'(fallback)':<20} {self._fallback.description}")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

TEST_MESSAGES = [
    ("What are your business hours?",
     "simple_faq"),
    ("I'm getting a 502 error when I try to log in via SSO with Okta.",
     "technical"),
    ("I was charged twice for my subscription last month. Can you look into my account?",
     "account_issue"),
    ("This is the third time my data has been corrupted. I'm extremely disappointed and I want a refund.",
     "complaint"),
    ("I'm done waiting. I'm contacting my lawyer and filing a complaint with the CFPB.",
     "escalate"),
]

if __name__ == "__main__":
    # Build the router
    support_router = (
        Router(classify_intent)
        .register("simple_faq",    handle_simple_faq,    "Fast FAQ - Haiku model")
        .register("technical",     handle_technical,     "Technical support - Haiku model")
        .register("account_issue", handle_account_issue, "Account handling - Sonnet model")
        .register("complaint",     handle_complaint,     "Complaint resolution - Sonnet model")
        .register("escalate",      handle_escalate,      "Human escalation - no model")
        .set_fallback(handle_simple_faq,                  "Default: treat as FAQ")
    )

    print("Router configuration:")
    support_router.list_handlers()
    print()

    print("=" * 65)
    print("Routing test messages")
    print("=" * 65)

    for message, expected_intent in TEST_MESSAGES:
        print(f"\nMessage: \"{message[:60]}{'...' if len(message) > 60 else ''}\"")
        print(f"Expected intent: {expected_intent}")

        result = support_router.route(message)
        actual_intent = result.get("intent", "error")
        match = "MATCH" if expected_intent in actual_intent else "MISMATCH"

        print(f"Actual intent:   {actual_intent} [{match}]")
        print(f"Model used:      {result.get('model_used', 'N/A')}")
        print(f"Response:        {result.get('response', result.get('error', ''))[:120]}...")
