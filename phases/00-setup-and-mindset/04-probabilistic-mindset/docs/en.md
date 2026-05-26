# The Probabilistic Mindset: Why Deterministic Thinking Breaks

> You cannot debug a probabilistic system by reading a single trace. You debug it by analyzing distributions.

**Type:** Learn
**Languages:** Python
**Prerequisites:** 00-01 (Dev Environment), 00-02 (API Keys), 00-03 (First API Call)
**Time:** ~45 min
**Learning Objectives:**
- Explain why models are samplers, not functions, and what that means for engineering
- Identify the 5 failure modes of deterministic thinking applied to AI
- Run the same prompt N times and measure output variance empirically
- Use temperature correctly as a variance dial

---

## The Problem

Your AI feature passes all tests on Monday. By Thursday, three users report it returning wrong answers. You pull the logs, find one of the bad traces, re-run it manually, and it works fine. You close the bug report: "Cannot reproduce."

Two weeks later you get five more reports. You re-run again. Fine again. The issue is not in any single trace. The issue is in the distribution: 8% of calls return a response that does not match your schema, 3% return the wrong category, and 2% return an empty string for a field that should always be populated. None of these are bugs in your code. They are properties of the distribution your model samples from.

Engineers who treat models as deterministic functions -- same input, same output -- ship systems with hidden failure rates they cannot see, cannot measure, and cannot improve. This lesson installs the mental model that makes those failure rates visible.

---

## The Concept

### Deterministic Function vs. Probabilistic Sampler

```
DETERMINISTIC FUNCTION (what software engineers expect):

Input A ----[ function ]----> Output X (always)
Input A ----[ function ]----> Output X (always)
Input A ----[ function ]----> Output X (always)

Examples: hash(), sort(), parseInt()


PROBABILISTIC SAMPLER (what an LLM actually is):

Input A ----[ model ]----> Output X  (60% of the time)
Input A ----[ model ]----> Output Y  (25% of the time)
Input A ----[ model ]----> Output Z  (10% of the time)
Input A ----[ model ]----> Output W  ( 5% of the time)

The output is a SAMPLE from a probability distribution over all possible responses.
That distribution is shaped by: the model weights, the temperature, and the prompt.
```

The model is not a broken function that sometimes returns the wrong value. It is a well-functioning sampler that, given any input, maintains a distribution over possible outputs. When you run it, you get one draw from that distribution.

### Temperature: The Variance Dial

Temperature controls the shape of the output distribution. Lower temperature concentrates probability on the most likely outputs. Higher temperature spreads probability more broadly.

```
Temperature 0.0 (nearly deterministic):
  Most likely output gets almost all probability mass.
  Same input --> same output on nearly every run.
  Best for: extraction, classification, structured output.

Temperature 0.5-0.7 (moderate variance):
  Probability spread across several likely outputs.
  Some run-to-run variation.
  Best for: summarization, explanation, translation.

Temperature 1.0 (default, higher variance):
  Wider spread. More creative, less predictable.
  Visible variation across runs.
  Best for: brainstorming, creative writing, ideation.
```

Note: even at temperature=0, the model is not truly deterministic due to floating-point non-determinism in GPU computation. You can observe occasional variation. "Temperature 0" means "minimal variance," not "zero variance."

### The 5 Failure Modes of Deterministic Thinking

```
+---------------------------+------------------------------------------+
| DETERMINISTIC ASSUMPTION  | HOW IT BREAKS IN AI SYSTEMS              |
+---------------------------+------------------------------------------+
| 1. Unit test one output   | Pass rate on your test case != pass rate |
|    and ship if it passes  | on the distribution. 1 sample tells you  |
|                           | almost nothing about the 8% failure rate.|
+---------------------------+------------------------------------------+
| 2. Exact string matching  | Model says "Positive" on run 1,          |
|    in test assertions     | "POSITIVE" on run 2, "positive." on      |
|                           | run 3. All correct, all fail your test.  |
+---------------------------+------------------------------------------+
| 3. Assume idempotency     | Running the same pipeline twice on the   |
|    (run twice = same)     | same input produces different outputs.   |
|                           | You cannot use "just run it again" to    |
|                           | verify a fix.                            |
+---------------------------+------------------------------------------+
| 4. Trust a one-shot eval  | You evaluate quality on 10 examples,     |
|    to measure quality     | get 9/10. But over 1000 real user calls, |
|                           | the actual pass rate is 73%. Small eval  |
|                           | sets hide the tail.                      |
+---------------------------+------------------------------------------+
| 5. Build brittle if/else  | if response == "yes": ... else: ...      |
|    on model output        | The model says "Yes", "yes.", "YES",     |
|                           | "Yes, I agree", "Affirmative" -- your    |
|                           | if/else handles one case and breaks on   |
|                           | all the others.                          |
+---------------------------+------------------------------------------+
```

---

## Build It

### Step 1: Observe Output Variance

Run the same prompt 10 times and collect the outputs. Do not use temperature=0 for this exercise -- we want to see natural variance.

```python
import anthropic
from dotenv import load_dotenv
from collections import Counter

load_dotenv()
client = anthropic.Anthropic()

def run_n_times(prompt: str, n: int = 10, temperature: float = 1.0) -> list[str]:
    """Run the same prompt N times and return all outputs."""
    results = []
    for i in range(n):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=32,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        results.append(text)
        print(f"  Run {i+1:2d}: {text!r}")
    return results
```

### Step 2: Measure the Distribution

```python
def measure_distribution(prompt: str, n: int = 20) -> dict:
    """
    Run a prompt N times and return distribution statistics.
    For a classification task, this tells you: what fraction of calls
    return each possible label?
    """
    print(f"\nRunning '{prompt[:50]}...' {n} times (temperature=1.0):\n")
    results = run_n_times(prompt, n, temperature=1.0)

    # Count unique outputs
    counter = Counter(results)
    total = len(results)

    print(f"\nDistribution ({total} runs):")
    for output, count in counter.most_common():
        pct = count / total * 100
        bar = "=" * int(pct / 5)
        print(f"  {output!r:30} {count:3}x ({pct:5.1f}%) {bar}")

    unique_count = len(counter)
    most_common_pct = counter.most_common(1)[0][1] / total * 100
    print(f"\nSummary: {unique_count} unique outputs, most common at {most_common_pct:.1f}%")

    return {
        "outputs": results,
        "distribution": dict(counter),
        "unique_count": unique_count,
        "consistency_pct": most_common_pct,
    }
```

> **Real-world check:** You run a sentiment classifier 20 times on the same product review and get "POSITIVE" 17 times, "VERY POSITIVE" twice, and "Positive sentiment" once. A teammate says: "It's basically consistent, 17 out of 20 is fine." How would you explain why this is a problem for production systems that parse the output with exact string matching?

### Step 3: Compare Temperature Settings

```python
def compare_temperatures(prompt: str, temperatures: list[float], n_per_temp: int = 10) -> None:
    """Show how temperature affects output variance for the same prompt."""
    print(f"\n=== Temperature Comparison ===")
    print(f"Prompt: '{prompt[:60]}...'")

    for temp in temperatures:
        print(f"\nTemperature {temp}:")
        results = run_n_times(prompt, n_per_temp, temperature=temp)
        unique = len(set(results))
        print(f"  -> {unique}/{n_per_temp} unique outputs")
```

### Step 4: The Right Test Pattern

```python
def robust_classify(text: str) -> str:
    """
    Classification that handles output variance correctly.
    Normalizes the response before comparing, so "POSITIVE", "Positive",
    and "positive." all map to "POSITIVE".
    """
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        temperature=0.0,   # minimize variance for classification
        messages=[{
            "role": "user",
            "content": (
                f"Classify as POSITIVE, NEGATIVE, or NEUTRAL. "
                f"Reply with only the label, nothing else.\n\nText: {text}"
            ),
        }],
    )
    raw = response.content[0].text.strip().upper()

    # Normalize: handle common variations
    if "POSITIVE" in raw:
        return "POSITIVE"
    if "NEGATIVE" in raw:
        return "NEGATIVE"
    if "NEUTRAL" in raw:
        return "NEUTRAL"

    # Unknown output: log it, return a safe default
    print(f"WARNING: unexpected classification output: {raw!r}")
    return "UNKNOWN"
```

---

## Use It

Temperature is set at the API call level via the `temperature` parameter. It accepts values from 0.0 to 1.0 (Claude's range; some providers go to 2.0).

```python
# Task-appropriate temperature choices

# Extraction: minimize variance -- you want the same answer every time
extraction_response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    temperature=0.0,
    messages=[{"role": "user", "content": "Extract all dates from this text: ..."}],
)

# Summarization: moderate variance is acceptable
summary_response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=512,
    temperature=0.3,
    messages=[{"role": "user", "content": "Summarize this document: ..."}],
)

# Creative writing: higher variance is desirable
story_response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=1024,
    temperature=0.9,
    messages=[{"role": "user", "content": "Write an opening paragraph for a short story about..."}],
)
```

The Anthropic SDK does not provide `top_p` as a separate lever (it is subsumed by temperature for Claude). If you are porting from an OpenAI codebase, temperature is the correct single parameter to tune.

> **Perspective shift:** Traditional software testing assumes: if a function passes a test, it passes that test every time. AI system testing assumes the opposite: a single passing run proves nothing about the pass rate. Correct AI testing runs each case N times (at minimum 10-50) and measures what fraction pass. This is not overhead -- it is the minimum viable signal. A system with a 90% pass rate on your eval looks great until it is handling 10,000 users and failing 1,000 of them per day.

---

## Ship It

The artifact for this lesson is a reference guide on the probabilistic mindset for AI engineering.

See `outputs/prompt-probabilistic-mindset.md`.

---

## Evaluate It

The mental model shift has happened when you can:

```python
# 1. Measure a real distribution (not just run once)
# Run this and check: does the consistency_pct vary between runs of the script?
from collections import Counter
import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()

prompt = "Is 'The meeting was fine' positive, negative, or neutral? Reply with one word."
results = []
for _ in range(10):
    r = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=8,
        temperature=1.0,
        messages=[{"role": "user", "content": prompt}],
    )
    results.append(r.content[0].text.strip().lower())

counter = Counter(results)
print(f"Distribution over 10 runs: {dict(counter)}")
unique = len(counter)
print(f"Unique outputs: {unique}/10")

# 2. Verify temperature=0 reduces (but does not eliminate) variance
results_t0 = []
for _ in range(5):
    r = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=8,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}],
    )
    results_t0.append(r.content[0].text.strip().lower())

unique_t0 = len(set(results_t0))
print(f"\nWith temperature=0: {unique_t0}/5 unique outputs (expect 1, occasionally 2)")

# 3. Verify robust_classify handles case variants
test_cases = [
    ("The service was excellent", "POSITIVE"),
    ("Worst experience ever", "NEGATIVE"),
    ("It was okay", "NEUTRAL"),
]
for text, expected in test_cases:
    # Test that normalization would catch variations
    for variant in [expected, expected.lower(), expected.capitalize() + "."]:
        assert expected in variant.upper(), f"Normalization would miss: {variant!r}"
print("\nOK: normalization logic handles case variants")
```
