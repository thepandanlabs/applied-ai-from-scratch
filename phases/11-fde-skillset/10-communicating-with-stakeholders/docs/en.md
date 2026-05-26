# Communicating with Non-Technical Stakeholders

> "The model accuracy improved from 0.79 to 0.84" and "Support agents now correctly handle 84% of Tier 1 tickets without escalation, up from 79%" describe the same result. One gets a budget renewal; the other gets a confused follow-up question.

**Type:** Learn
**Languages:** Python
**Prerequisites:** 11-08 (measuring business impact), 11-05 (demos that survive real data)
**Time:** ~45 min
**Phase:** 11 · FDE Skillset

---

## Learning Objectives

- Identify the three translation problems that make technical updates opaque to business stakeholders
- Apply five communication templates for status updates, risk escalations, and results summaries
- Build a StakeholderTranslator CLI that rewrites technical updates into stakeholder-ready language
- Score translated output on clarity, business relevance, and jargon density
- Deliver an AI uncertainty message that does not trigger alarm

---

## The Problem

You are two weeks from launch. Your weekly status update says: "We completed integration of the hybrid retrieval module with cross-encoder reranking. RAGAS scores improved: faithfulness 0.82 -> 0.89, answer relevance 0.77 -> 0.85. Latency p95 is 1.4s. Still investigating occasional hallucinations on edge cases."

Your primary stakeholder, a VP of Operations, forwards this to the CFO with the message: "The AI team says the system is sometimes hallucinating. Should we be concerned?"

The CFO emails the CEO. The CEO asks for a meeting.

You caused a crisis by sending an accurate technical update. The problem was not the content; it was the audience. The VP read "hallucinations on edge cases" as "the system lies sometimes and we do not know when." You meant "rare, bounded failure mode we are tracking and will address before launch."

This is one of the most common and costly communication failures in AI engineering. The solution is not to stop being accurate. It is to have a translation layer for every update that goes to non-technical stakeholders.

---

## The Concept

### The Three Translation Problems

```
TRANSLATION PROBLEM 1: METRIC TRANSLATION
  Technical: "RAGAS faithfulness improved from 0.82 to 0.89"
  Stakeholder hears: "They changed a number. I do not know if that is good."
  Translation: "The system now gives accurate, well-sourced answers 89% of the time,
                up from 82%. The improvement means fewer corrections needed by your team."

TRANSLATION PROBLEM 2: UNCERTAINTY TRANSLATION
  Technical: "Occasional hallucinations on edge cases under investigation"
  Stakeholder hears: "The system makes things up and they do not know when or why"
  Translation: "We have identified a narrow category of unusual questions where the
                system occasionally gives incomplete answers. We have a fix scheduled
                for next week. This affects less than 3% of expected query volume."

TRANSLATION PROBLEM 3: PROGRESS TRANSLATION
  Technical: "Completed hybrid retrieval integration. Working on prompt optimization."
  Stakeholder hears: "I have no idea what this means."
  Translation: "We finished the search component that lets the system find relevant
                documents. We are now tuning the instructions that tell the AI how
                to answer questions from those documents. On track for the scheduled
                launch date."
```

### The Five Communication Templates

```
TEMPLATE 1: WEEKLY STATUS UPDATE (one page, every Monday)
  Section 1: One-sentence summary (what is the headline this week?)
  Section 2: What shipped (in plain language, user-facing impact)
  Section 3: What ships next (concrete deliverables with dates)
  Section 4: Risks on the radar (framed as "we are watching X and will have Y by Z")
  Section 5: What we need from you (specific asks, not vague "input")
  Length: 200-300 words maximum

TEMPLATE 2: RISK ESCALATION
  Risk name (plain language, not "p95 latency spike")
  Impact if unresolved (who it affects, when it becomes a problem)
  Probability (is this likely or a tail risk?)
  Current status (what are we doing about it right now?)
  What we need (specific decision or resource)
  Deadline for the decision

TEMPLATE 3: RESULTS SUMMARY (for QBRs and pilots)
  Before: [metric in business terms] - not "baseline accuracy was 0.72"
  After:  [metric in business terms] - not "accuracy is now 0.85"
  Delta:  [what changed for users or the business]
  Projection: [what this means at full scale]
  Next step: [clear ask or decision]

TEMPLATE 4: AI UNCERTAINTY FRAMING
  Never say "hallucination" to a non-technical stakeholder without context.
  Instead: "The system handles [X]% of questions with high confidence.
            For the remaining [Y]%, it flags the answer as needing review,
            or routes to a human. This is by design."

TEMPLATE 5: LAUNCH READINESS UPDATE
  Green: On track for [date]. [N] items remaining, all on schedule.
  Yellow: [specific risk] may affect [date]. Mitigation: [action] by [date].
  Red: [specific blocker]. Options: [A], [B], [C]. Recommendation: [X].
```

### The Jargon Replacement Table

```
+----------------------------+------------------------------------------+
| TECHNICAL PHRASE           | STAKEHOLDER-FRIENDLY EQUIVALENT          |
+----------------------------+------------------------------------------+
| Model accuracy: 0.84       | The system gives the right answer 84%    |
|                            | of the time                              |
+----------------------------+------------------------------------------+
| Hallucination              | The system generates an incorrect or     |
|                            | unsupported answer                       |
+----------------------------+------------------------------------------+
| Latency p95: 1.4s          | 95% of responses arrive within 1.4      |
|                            | seconds                                  |
+----------------------------+------------------------------------------+
| RAG pipeline               | The system that finds relevant documents |
|                            | before answering a question              |
+----------------------------+------------------------------------------+
| Embedding model            | The component that understands the       |
|                            | meaning of text                          |
+----------------------------+------------------------------------------+
| Context window exceeded    | The question or document was too long    |
|                            | for the AI to process in one step        |
+----------------------------+------------------------------------------+
| RAGAS faithfulness: 0.89   | 89% of answers are directly supported   |
|                            | by the source documents                  |
+----------------------------+------------------------------------------+
| Fine-tuning                | Training the AI on your specific data   |
|                            | and use case                             |
+----------------------------+------------------------------------------+
| Eval set / eval score      | Our quality test: [N] sample questions  |
|                            | with known correct answers               |
+----------------------------+------------------------------------------+
| Token limit                | The maximum length the AI can process   |
|                            | at once                                  |
+----------------------------+------------------------------------------+
```

---

## Build It

### Step 1: Setup

```python
# pip install anthropic
# Set ANTHROPIC_API_KEY in environment

import argparse
import json
import os
import sys
from dataclasses import dataclass

import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"
```

### Step 2: The Translation Prompt

```python
@dataclass
class TranslationResult:
    original: str
    translated: str
    clarity_score: float          # 0-1: how clear is it to a non-technical reader?
    business_relevance_score: float  # 0-1: does it speak to business outcomes?
    jargon_score: float           # 0-1: 0 = no jargon, 1 = full jargon
    improvements: list[str]


TRANSLATE_PROMPT = """You are an expert at translating technical AI project updates into clear, business-focused language for non-technical stakeholders.

The audience is a VP or C-level executive who:
- Has no background in machine learning or software engineering
- Cares about business outcomes: time saved, cost reduced, risk managed, users helped
- Makes decisions based on confidence and clarity, not technical details
- Will escalate or block a project if they feel uncertain or out of the loop

Technical update to translate:
{update}

Translate this into a stakeholder-ready update. Then score the original and your translation.

Return a JSON object:
{{
  "translation": "<your stakeholder-friendly rewrite of the update>",
  "clarity_score": <float 0.0-1.0: how clear is the translated version to a non-technical reader>,
  "business_relevance_score": <float 0.0-1.0: does it speak to business outcomes and impact?>,
  "jargon_score": <float 0.0-1.0: how much technical jargon remains? 0=none, 1=all jargon>,
  "improvements": ["<specific change 1>", "<specific change 2>", "<specific change 3>"]
}}

Translation rules:
- Replace every metric with its business meaning (e.g., "accuracy 0.84" becomes "correctly handles 84% of requests")
- Replace "hallucination" with a concrete description of what happens and how often
- Replace infrastructure terms (RAG, embedding, p95, tokens) with plain-language equivalents
- Keep the update under 150 words
- End with either a concrete status (on track / at risk) or a specific ask
- Do not introduce uncertainty you did not have - be honest about risks using plain language
- Never start with "I hope this email finds you well" or similar filler"""
```

### Step 3: The Translator Function

```python
def translate_update(technical_update: str) -> TranslationResult:
    """Translate a technical update into stakeholder-ready language and score it."""
    prompt = TRANSLATE_PROMPT.format(update=technical_update)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    data = json.loads(raw)

    return TranslationResult(
        original=technical_update,
        translated=data["translation"],
        clarity_score=float(data["clarity_score"]),
        business_relevance_score=float(data["business_relevance_score"]),
        jargon_score=float(data["jargon_score"]),
        improvements=data.get("improvements", []),
    )
```

### Step 4: Report Formatter

```python
def print_translation(result: TranslationResult) -> None:
    """Print the original, translation, and scores."""
    print("\n" + "=" * 60)
    print("STAKEHOLDER TRANSLATOR")
    print("=" * 60)

    print("\n--- ORIGINAL (TECHNICAL) ---")
    print(result.original)

    print("\n--- TRANSLATED (STAKEHOLDER-READY) ---")
    print(result.translated)

    print("\n--- SCORES ---")
    print(f"Clarity:           {result.clarity_score:.2f} / 1.0")
    print(f"Business relevance:{result.business_relevance_score:.2f} / 1.0")
    print(f"Jargon remaining:  {result.jargon_score:.2f} / 1.0  (lower is better)")

    if result.improvements:
        print("\n--- KEY CHANGES MADE ---")
        for improvement in result.improvements:
            print(f"  - {improvement}")

    # Overall assessment
    avg_score = (result.clarity_score + result.business_relevance_score + (1.0 - result.jargon_score)) / 3
    print(f"\nOverall translation quality: {avg_score:.2f} / 1.0")
    if avg_score >= 0.80:
        print("STATUS: Ready to send to stakeholders.")
    elif avg_score >= 0.65:
        print("STATUS: Review and refine before sending.")
    else:
        print("STATUS: Needs significant rework.")
    print("=" * 60 + "\n")
```

### Step 5: Batch Translation and Demo Updates

```python
DEMO_UPDATES = [
    {
        "name": "Status Update 1: Technical Progress",
        "text": (
            "Completed integration of the hybrid retrieval module with cross-encoder reranking. "
            "RAGAS scores improved: faithfulness 0.82 -> 0.89, answer relevance 0.77 -> 0.85. "
            "Latency p95 is 1.4s, within SLA. Still investigating occasional hallucinations "
            "on edge cases involving multi-hop reasoning over documents > 50 pages."
        ),
    },
    {
        "name": "Status Update 2: Risk Escalation",
        "text": (
            "We identified a risk: the customer's Oracle CRM database does not have an API. "
            "We need to build an ETL pipeline to export data nightly to S3 as a workaround. "
            "This adds approximately 8 engineering days and introduces a data freshness "
            "constraint: the system will only have access to data as of the previous day's "
            "export. This may impact the real-time classification use case."
        ),
    },
    {
        "name": "Status Update 3: Pilot Results",
        "text": (
            "Pilot results for the 4-week support ticket classification evaluation: "
            "precision 0.87, recall 0.83, F1 0.85. Escalation rate dropped from 34% to 18%. "
            "Average time-to-resolution improved from 185s to 62s. "
            "Correlation between model confidence score and task success: 0.71. "
            "Token usage averaging 2,800 tokens per query, within budget."
        ),
    },
]


def run_demo() -> None:
    """Run the translator on three demo updates."""
    for item in DEMO_UPDATES:
        print(f"\n{'#' * 60}")
        print(f"  {item['name']}")
        print(f"{'#' * 60}")
        result = translate_update(item["text"])
        print_translation(result)
```

> **Real-world check:** A non-technical program manager says: "The AI team said there is a 'data freshness constraint' due to the ETL pipeline. What does that mean, and should I be worried?" How would you explain this in plain language, and does it need to be escalated?

---

## Use It

Run the translator on all three demo updates:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python main.py --demo
```

For the first update (technical progress), expect:
- "Hallucinations on edge cases" translated to something like: "The system occasionally gives incomplete answers on a narrow category of long, complex documents. This affects less than 5% of expected queries and we have a fix scheduled before launch."
- RAGAS scores translated to user-outcome language
- Jargon score near 0.0 (no remaining technical terms)
- Clarity score above 0.80

Test with your own update:

```bash
python main.py --update "We hit a context window limit when processing documents over 100k tokens. We are implementing a sliding window with overlap to handle this edge case."
```

> **Perspective shift:** Your engineering manager says: "Writing two versions of every update (technical and stakeholder) doubles the communication overhead. Just train the stakeholders to understand technical terms." How do you respond, and what is the cost of the alternative?

---

## Ship It

The output for this lesson is `outputs/prompt-stakeholder-communication-guide.md`. It is a reusable reference for any engineer who needs to communicate AI project status to a non-technical audience.

The runnable tool is `code/main.py`:

```bash
python main.py --demo
python main.py --update "your technical update here"
```

---

## Evaluate It

**Check 1: Is "hallucination" gone from all translated outputs?**
Run all three demo updates through the translator. Search the translations for "hallucination," "embedding," "RAG," "RAGAS," "p95," "precision," "recall," "F1," and "tokens." Any of these in the translated output is a jargon failure. If they appear, the translation prompt needs to be more explicit.

**Check 2: Does the translated pilot results update include business numbers?**
The translation of Update 3 should mention: the escalation rate drop (34% to 18%), the resolution time improvement (185s to 62s), and what these mean for the business. If the translation stays at the F1/precision/recall level, it has not crossed into Layer 3 (business KPI language).

**Check 3: Does the risk escalation translation include a clear ask?**
A good risk escalation translation ends with a specific decision request and a deadline. "We need a decision on whether to proceed with the nightly batch approach by Wednesday" is a clear ask. "Let us know if you have concerns" is not.

**Check 4: Would a VP forward this to the CEO?**
Read the translated pilot results as a VP would. Would you forward it to the CEO? If it still has technical content that would require explanation, the translation is not complete.
