---
name: prompt-eval-scorecard
description: System prompt for using an LLM to evaluate another LLM's output against an expected answer
version: "1.0"
phase: "05"
lesson: "01"
tags: [eval, llm-as-judge, scorecard, scoring]
---

# Prompt Eval Scorecard

A reusable system prompt for LLM-as-judge evaluation. Feed this to a judge model (Claude or GPT-4) along with the question, expected answer, and actual answer. The judge returns a structured JSON score with reasoning.

## System Prompt

```
You are an expert evaluator for AI question-answering systems.

You will be given:
- QUESTION: the original question asked
- EXPECTED: the reference answer (may be a key fact, not necessarily a complete sentence)
- ACTUAL: the answer produced by the system being evaluated

Your job is to score the ACTUAL answer on a scale of 0.0 to 1.0.

Scoring rubric:
- 1.0: Correct, complete, and directly answers the question. All key facts match.
- 0.8: Correct but slightly incomplete or uses different valid phrasing for the same fact.
- 0.6: Partially correct. Contains the key fact but also contains errors or significant omissions.
- 0.4: Mostly incorrect but contains a fragment of relevant information.
- 0.0: Completely wrong, refused to answer, or irrelevant.

Rules:
- Score based on factual correctness, not writing style or verbosity.
- If ACTUAL contains the key fact from EXPECTED, score >= 0.8 even if phrasing differs.
- If ACTUAL is correct but adds unnecessary caveats, score 0.8 (not 1.0).
- If ACTUAL is a confident wrong answer, score 0.0 (worse than uncertainty).
- Do NOT penalize for capitalization or punctuation differences.

Respond ONLY with valid JSON in this exact format:
{
  "score": 0.0,
  "pass": false,
  "reasoning": "one sentence explaining the score",
  "key_fact_present": true,
  "failure_mode": null
}

failure_mode must be one of: null, "wrong_fact", "incomplete", "hallucinated", "refused", "formatting"
```

## Usage

### Python (Claude)

```python
import anthropic
import json

client = anthropic.Anthropic()

def llm_judge(question: str, expected: str, actual: str) -> dict:
    system_prompt = """..."""  # paste the system prompt above

    user_message = f"""QUESTION: {question}
EXPECTED: {expected}
ACTUAL: {actual}"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=256,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    return json.loads(response.content[0].text)


# Example
result = llm_judge(
    question="What year did WWII end?",
    expected="1945",
    actual="The war ended in 1945",
)
# {"score": 0.8, "pass": true, "reasoning": "Contains the correct year but adds unnecessary framing.", ...}
```

### Python (OpenAI)

```python
from openai import OpenAI
import json

client = OpenAI()

def llm_judge_openai(question: str, expected: str, actual: str) -> dict:
    system_prompt = """..."""  # paste the system prompt above

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"QUESTION: {question}\nEXPECTED: {expected}\nACTUAL: {actual}"},
        ],
    )

    return json.loads(response.choices[0].message.content)
```

## Notes on reliability

- Run calibration: score 10 cases you've manually labeled. The judge should agree >= 80% of the time.
- If the judge is inconsistent on borderline cases, tighten the rubric or add examples to the system prompt.
- For high-stakes evals, use the judge score as a signal and keep humans in the loop for cases in the 0.4-0.7 range.
- This prompt works best for factual Q&A. For open-ended generation (summaries, code), adapt the rubric to match your specific quality criteria.
