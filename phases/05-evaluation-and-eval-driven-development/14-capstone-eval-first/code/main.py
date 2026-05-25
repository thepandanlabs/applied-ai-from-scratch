"""
Lesson 14: Capstone - Eval-First Development of a Feature
-----------------------------------------------------------
Complete eval-first FAQ answering system.

Modules in this file:
  success_criteria   - defines what "working" means as numbers
  golden_set         - 10 labeled test cases across 6 categories
  faq_assistant      - the feature: simple RAG over a FAQ document
  eval_scorers       - three scorers: format_compliance, faithfulness, relevance
  eval_runner        - runs the full eval suite, prints results, exits 1 on failure
  online_eval        - FastAPI service with 20% sampling for async online eval

Run the eval suite:
    uv run python main.py --mode eval

Run the FastAPI service:
    uv run python main.py --mode serve
    # then: curl -X POST http://localhost:8000/ask -H "Content-Type: application/json"
    #              -d '{"question": "What is your return policy?"}'

Dependencies (uv add):
    anthropic fastapi uvicorn pydantic python-dotenv
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# 1. Success criteria
# ---------------------------------------------------------------------------

SUCCESS_CRITERIA: dict[str, float] = {
    "faithfulness": 0.90,       # answers stay grounded in FAQ content
    "answer_relevance": 0.85,   # answers address the question asked
    "format_compliance": 1.00,  # always returns valid JSON with required keys
}

REQUIRED_OUTPUT_KEYS = {"answer", "source_section"}


# ---------------------------------------------------------------------------
# 2. Golden set
# ---------------------------------------------------------------------------

GOLDEN_CASES: list[dict] = [
    {
        "id": "gc-01",
        "input": "What is your return policy?",
        "expected_answer_contains": ["30 days", "receipt", "original condition"],
        "expected_source_section": "Returns and Refunds",
        "category": "policy",
    },
    {
        "id": "gc-02",
        "input": "How long does shipping take?",
        "expected_answer_contains": ["3-5 business days", "standard shipping"],
        "expected_source_section": "Shipping",
        "category": "shipping",
    },
    {
        "id": "gc-03",
        "input": "Do you offer international shipping?",
        "expected_answer_contains": ["international", "countries"],
        "expected_source_section": "Shipping",
        "category": "shipping",
    },
    {
        "id": "gc-04",
        "input": "How do I cancel my subscription?",
        "expected_answer_contains": ["account settings", "cancel", "billing cycle"],
        "expected_source_section": "Account Management",
        "category": "account",
    },
    {
        "id": "gc-05",
        "input": "What payment methods do you accept?",
        "expected_answer_contains": ["credit card", "PayPal"],
        "expected_source_section": "Payment",
        "category": "payment",
    },
    {
        "id": "gc-06",
        "input": "Is my credit card information secure?",
        "expected_answer_contains": ["encrypted", "PCI"],
        "expected_source_section": "Payment",
        "category": "security",
    },
    {
        "id": "gc-07",
        "input": "How do I track my order?",
        "expected_answer_contains": ["tracking number", "email", "shipping confirmation"],
        "expected_source_section": "Order Tracking",
        "category": "orders",
    },
    {
        "id": "gc-08",
        "input": "Can I change my order after placing it?",
        "expected_answer_contains": ["24 hours", "contact support"],
        "expected_source_section": "Order Management",
        "category": "orders",
    },
    {
        "id": "gc-09",
        "input": "What is your privacy policy regarding my data?",
        "expected_answer_contains": ["personal data", "third parties", "GDPR"],
        "expected_source_section": "Privacy",
        "category": "legal",
    },
    {
        "id": "gc-10",
        "input": "How do I contact customer support?",
        "expected_answer_contains": ["email", "support@", "business hours"],
        "expected_source_section": "Contact",
        "category": "support",
    },
]


# ---------------------------------------------------------------------------
# 3. FAQ document and feature
# ---------------------------------------------------------------------------

FAQ_DOCUMENT = """
# Shipping
Standard shipping takes 3-5 business days. Express shipping takes 1-2 business days.
We ship to over 50 countries internationally. International shipping times vary by destination (7-14 days).
A shipping confirmation with tracking number is sent via email when your order ships.

# Returns and Refunds
You can return items within 30 days of purchase with a receipt in original condition.
Refunds are processed within 5-7 business days to your original payment method.
Items must be unused and in original packaging. Sale items are final sale.

# Payment
We accept credit cards (Visa, Mastercard, Amex), PayPal, and bank transfers.
All payment information is encrypted using SSL and we are PCI DSS compliant.
Your card number is never stored on our servers.

# Account Management
To cancel your subscription, go to Account Settings > Subscription > Cancel.
Changes take effect at the end of your current billing cycle.
You can also downgrade your plan instead of canceling to retain access.

# Order Tracking
You will receive a tracking number via email in your shipping confirmation.
Track your order at our website or directly on the carrier's site.
If your tracking number is not working after 48 hours, contact support.

# Order Management
You can modify or cancel your order within 24 hours of placing it.
After 24 hours, please contact support at support@example.com.
We cannot modify orders that have already shipped.

# Privacy
We collect personal data to fulfill orders and improve our service.
We do not sell data to third parties. We comply with GDPR and CCPA.
You can request a copy of your data or request deletion via our privacy portal.

# Contact
Email us at support@example.com. We respond within 1 business day.
Support hours: Monday-Friday, 9am-6pm EST.
For urgent issues, use the live chat on our website.
"""


def chunk_faq(faq: str) -> list[dict]:
    """Split FAQ into sections. Each chunk is a complete section."""
    chunks: list[dict] = []
    current_section: Optional[str] = None
    current_lines: list[str] = []

    for line in faq.strip().splitlines():
        if line.startswith("# "):
            if current_section:
                chunks.append(
                    {
                        "section": current_section,
                        "content": "\n".join(current_lines).strip(),
                    }
                )
            current_section = line[2:].strip()
            current_lines = []
        elif line.strip():
            current_lines.append(line.strip())

    if current_section:
        chunks.append(
            {"section": current_section, "content": "\n".join(current_lines).strip()}
        )

    return chunks


def retrieve_relevant_chunks(question: str, chunks: list[dict], top_k: int = 2) -> list[dict]:
    """
    Keyword-based retrieval. Weights section-name matches more than body matches.
    In production: replace with embeddings + pgvector.
    """
    question_words = set(question.lower().split())
    scored: list[tuple[int, dict]] = []

    for chunk in chunks:
        score = 0
        for word in question_words:
            if len(word) > 3:
                if word in chunk["content"].lower():
                    score += 1
                if word in chunk["section"].lower():
                    score += 3  # section-name match is stronger signal
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def answer_question(question: str, client: anthropic.Anthropic) -> dict:
    """
    Retrieve relevant FAQ sections and generate an answer with Claude.
    Returns: {"answer": str, "source_section": str}
    """
    chunks = chunk_faq(FAQ_DOCUMENT)
    relevant = retrieve_relevant_chunks(question, chunks)

    context = "\n\n".join(
        f"Section: {c['section']}\n{c['content']}" for c in relevant
    )

    prompt = f"""You are a customer support assistant. Answer the user's question using ONLY the information in the FAQ sections below.

FAQ Sections:
{context}

User Question: {question}

Return your response as JSON with exactly these keys:
- "answer": your response to the question (1-3 sentences, grounded in the FAQ)
- "source_section": the FAQ section name that contains the answer

JSON only, no other text."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    return json.loads(response.content[0].text)


# ---------------------------------------------------------------------------
# 4. Eval scorers
# ---------------------------------------------------------------------------

JUDGE_FAITHFULNESS_PROMPT = """You are evaluating whether an AI answer is faithful to a source document.

FAQ Document:
{faq_content}

AI Answer:
{answer}

Is every claim in the answer supported by the FAQ document? Score:
- 1.0: fully grounded, no unsupported claims
- 0.7: mostly grounded, minor unsupported detail
- 0.4: partially grounded, significant unsupported claims
- 0.0: not grounded or contradicts the FAQ

Return ONLY JSON: {{"score": 0.9, "rationale": "one sentence"}}"""

JUDGE_RELEVANCE_PROMPT = """Rate how well this answer addresses the question.

Question: {question}
Answer: {answer}

Score:
- 1.0: directly and completely answers the question
- 0.7: answers the question but misses key aspects
- 0.4: partially relevant but incomplete
- 0.0: does not answer the question

Return ONLY JSON: {{"score": 0.85, "rationale": "one sentence"}}"""


def format_compliance_score(response: dict) -> float:
    """1.0 if response has required keys with non-empty string values."""
    try:
        answer = response.get("answer", "")
        source = response.get("source_section", "")
        if isinstance(answer, str) and answer.strip() and isinstance(source, str) and source.strip():
            return 1.0
        return 0.0
    except Exception:
        return 0.0


def faithfulness_score(answer: str, faq_content: str, client: anthropic.Anthropic) -> float:
    """LLM judge: is the answer grounded in the FAQ content?"""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=128,
            messages=[
                {
                    "role": "user",
                    "content": JUDGE_FAITHFULNESS_PROMPT.format(
                        faq_content=faq_content, answer=answer
                    ),
                }
            ],
        )
        result = json.loads(response.content[0].text)
        return float(result["score"])
    except Exception as exc:
        print(f"[faithfulness-scorer] error: {exc}")
        return 0.0


def answer_relevance_score(question: str, answer: str, client: anthropic.Anthropic) -> float:
    """LLM judge: does the answer address the question?"""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=128,
            messages=[
                {
                    "role": "user",
                    "content": JUDGE_RELEVANCE_PROMPT.format(
                        question=question, answer=answer
                    ),
                }
            ],
        )
        result = json.loads(response.content[0].text)
        return float(result["score"])
    except Exception as exc:
        print(f"[relevance-scorer] error: {exc}")
        return 0.0


# ---------------------------------------------------------------------------
# 5. Eval runner
# ---------------------------------------------------------------------------

def run_eval_suite(
    experiment_name: str = "faq-v1",
    fail_on_regression: bool = True,
) -> list[dict]:
    """
    Run all scorers on all golden cases and print a summary.
    Exits with code 1 if any metric falls below its success criterion.
    """
    client = anthropic.Anthropic()
    results: list[dict] = []

    print(f"\nRunning eval suite: {experiment_name}")
    print("=" * 70)

    for case in GOLDEN_CASES:
        try:
            response = answer_question(case["input"], client)
        except Exception as exc:
            print(f"  {case['id']}: feature call failed: {exc}")
            response = {}

        fmt = format_compliance_score(response)
        faith = faithfulness_score(response.get("answer", ""), FAQ_DOCUMENT, client)
        rel = answer_relevance_score(case["input"], response.get("answer", ""), client)

        passed = (
            fmt >= SUCCESS_CRITERIA["format_compliance"]
            and faith >= SUCCESS_CRITERIA["faithfulness"]
            and rel >= SUCCESS_CRITERIA["answer_relevance"]
        )
        status = "PASS" if passed else "FAIL"

        print(
            f"  {case['id']} [{case['category']:10s}]: "
            f"fmt={fmt:.2f} faith={faith:.2f} rel={rel:.2f} [{status}]"
        )

        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "input": case["input"],
                "output": response,
                "scores": {
                    "format_compliance": fmt,
                    "faithfulness": faith,
                    "answer_relevance": rel,
                },
                "passed": passed,
            }
        )

    # Aggregate
    print("\nAGGREGATE:")
    all_pass = True
    for metric, threshold in SUCCESS_CRITERIA.items():
        scores = [r["scores"][metric] for r in results]
        avg = sum(scores) / len(scores)
        ok = avg >= threshold
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  {metric:<25} avg={avg:.3f}  threshold={threshold:.2f}  [{status}]")

    # Persist
    out_path = f"{experiment_name}_results.json"
    Path(out_path).write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {out_path}")

    if fail_on_regression and not all_pass:
        print("\nCI FAILED: one or more metrics below threshold.")
        sys.exit(1)

    print("\nCI PASSED: all metrics meet success criteria.")
    return results


# ---------------------------------------------------------------------------
# 6. Online eval FastAPI service
# ---------------------------------------------------------------------------

app = FastAPI(title="FAQ Assistant (eval-first capstone)")
_client: Optional[anthropic.Anthropic] = None

ONLINE_EVAL_SAMPLE_RATE = 0.20
ONLINE_EVAL_LOG = "online_eval.jsonl"


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


class FAQRequest(BaseModel):
    question: str


@app.post("/ask")
async def ask(request: FAQRequest, background_tasks: BackgroundTasks):
    """Answer a question. Samples 20% of traffic for background eval."""
    client = get_client()
    response = answer_question(request.question, client)

    if random.random() < ONLINE_EVAL_SAMPLE_RATE:
        background_tasks.add_task(
            _score_online,
            question=request.question,
            response=response,
        )

    return response


async def _score_online(question: str, response: dict) -> None:
    """Background: score this interaction and append to online eval log."""
    client = get_client()
    fmt = format_compliance_score(response)
    faith = faithfulness_score(response.get("answer", ""), FAQ_DOCUMENT, client)

    entry = {
        "trace_id": str(uuid.uuid4())[:8],
        "timestamp": datetime.utcnow().isoformat(),
        "question": question,
        "scores": {"format_compliance": fmt, "faithfulness": faith},
        "flagged": faith < 0.80 or fmt < 1.0,
    }

    with open(ONLINE_EVAL_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")

    if entry["flagged"]:
        print(f"[online-eval] FLAGGED {entry['trace_id']}: faith={faith:.2f} fmt={fmt:.2f}")


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="FAQ Assistant eval-first capstone")
    parser.add_argument(
        "--mode",
        choices=["eval", "serve", "stub-check"],
        default="eval",
        help="eval: run eval suite | serve: start FastAPI | stub-check: verify evals fail on stub",
    )
    parser.add_argument("--experiment", default="faq-v1")
    args = parser.parse_args()

    if args.mode == "stub-check":
        # Verify that evals fail on an empty stub -- proving they actually test something
        print("\n=== STUB CHECK: all evals should FAIL ===")
        for case in GOLDEN_CASES:
            stub_response = {"answer": "", "source_section": ""}
            fmt = format_compliance_score(stub_response)
            status = "FAIL (expected)" if fmt == 0.0 else "UNEXPECTED PASS"
            print(f"  {case['id']}: format_compliance={fmt} [{status}]")

    elif args.mode == "eval":
        run_eval_suite(experiment_name=args.experiment, fail_on_regression=True)

    elif args.mode == "serve":
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
