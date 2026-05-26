"""
Lesson 04: The Probabilistic Mindset

Demonstrates:
- Running the same prompt N times to observe output variance
- Measuring the distribution of outputs across runs
- Comparing temperature settings (0.0 vs 1.0) on variance
- The robust_classify pattern that handles output variations
- Why single-trace testing is insufficient for AI systems

Run with: uv run python main.py
Note: This makes ~40 API calls. Estimated cost: <$0.01 using Haiku.
"""

import os
from collections import Counter
from dotenv import load_dotenv
import anthropic


load_dotenv()


def run_n_times(
    client: anthropic.Anthropic,
    prompt: str,
    n: int = 10,
    temperature: float = 1.0,
    max_tokens: int = 32,
) -> list[str]:
    """Run the same prompt N times and return all raw outputs."""
    results = []
    for i in range(n):
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        results.append(text)
        print(f"  Run {i+1:2d}: {text!r}")
    return results


def measure_distribution(
    client: anthropic.Anthropic,
    prompt: str,
    n: int = 15,
    temperature: float = 1.0,
) -> dict:
    """
    Run a prompt N times and print a distribution histogram.
    Returns stats dict with consistency_pct (fraction that matched the top output).
    """
    print(f"\nRunning {n} times at temperature={temperature}:")
    results = run_n_times(client, prompt, n, temperature)

    counter = Counter(results)
    total = len(results)

    print(f"\nDistribution ({total} runs):")
    for output, count in counter.most_common():
        pct = count / total * 100
        bar = "#" * int(pct / 5)
        print(f"  {output!r:35} {count:3}x ({pct:5.1f}%) {bar}")

    most_common_output, most_common_count = counter.most_common(1)[0]
    consistency_pct = most_common_count / total * 100

    print(f"\nSummary:")
    print(f"  Unique outputs:        {len(counter)}")
    print(f"  Most common output:    {most_common_output!r}")
    print(f"  Consistency:           {consistency_pct:.1f}%")

    return {
        "outputs": results,
        "distribution": dict(counter),
        "unique_count": len(counter),
        "consistency_pct": consistency_pct,
        "most_common": most_common_output,
    }


def compare_temperatures(
    client: anthropic.Anthropic,
    prompt: str,
    temperatures: list[float] = [0.0, 0.5, 1.0],
    n_per_temp: int = 8,
) -> None:
    """Show how temperature affects output variance for the same prompt."""
    print(f"\n=== Temperature Variance Comparison ===")
    print(f"Prompt: '{prompt[:70]}'")
    print(f"Runs per temperature: {n_per_temp}\n")

    for temp in temperatures:
        results = run_n_times(client, prompt, n_per_temp, temp)
        unique = len(set(r.lower().strip(".,!?") for r in results))
        consistency = Counter(results).most_common(1)[0][1] / n_per_temp * 100
        print(f"  Temperature {temp}: {unique}/{n_per_temp} unique, {consistency:.0f}% consistency\n")


def robust_classify(client: anthropic.Anthropic, text: str) -> str:
    """
    Classify text as POSITIVE, NEGATIVE, or NEUTRAL.

    Uses temperature=0.0 for minimal variance on a classification task.
    Normalizes the output to handle "Positive", "POSITIVE", "positive.", etc.
    Returns "UNKNOWN" and logs when the model produces an unexpected format.

    In production: log UNKNOWN outputs and review them to improve your prompt.
    """
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        temperature=0.0,
        messages=[{
            "role": "user",
            "content": (
                "Classify the sentiment as POSITIVE, NEGATIVE, or NEUTRAL. "
                "Reply with exactly one word: POSITIVE, NEGATIVE, or NEUTRAL.\n\n"
                f"Text: {text}"
            ),
        }],
    )
    raw = response.content[0].text.strip().upper()

    # Normalize variations
    if "POSITIVE" in raw:
        return "POSITIVE"
    if "NEGATIVE" in raw:
        return "NEGATIVE"
    if "NEUTRAL" in raw:
        return "NEUTRAL"

    # Unexpected output -- log in production, return safe default
    print(f"WARNING: unexpected classification output: {raw!r} for text: {text!r}")
    return "UNKNOWN"


def demonstrate_brittle_vs_robust(client: anthropic.Anthropic) -> None:
    """
    Show the failure mode: brittle exact string matching vs. robust normalization.
    """
    print("\n=== Brittle vs. Robust Output Handling ===")

    test_texts = [
        "The product works perfectly.",
        "Absolutely terrible experience.",
        "It was okay, nothing special.",
    ]

    for text in test_texts:
        # Run 3 times to show natural variation
        raw_outputs = []
        for _ in range(3):
            r = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=16,
                temperature=0.7,  # some variance to show variation
                messages=[{
                    "role": "user",
                    "content": f"Is this positive, negative, or neutral? Just the word.\nText: {text}",
                }],
            )
            raw_outputs.append(r.content[0].text.strip())

        print(f"\nText: {text!r}")
        print(f"  Raw outputs: {raw_outputs}")

        # BRITTLE: exact match would fail on most of these
        brittle_results = [o == "positive" for o in raw_outputs]
        brittle_pass_rate = sum(brittle_results) / len(brittle_results) * 100
        print(f"  Brittle (exact match 'positive'): {sum(brittle_results)}/{len(brittle_results)} pass ({brittle_pass_rate:.0f}%)")

        # ROBUST: normalization handles variants
        robust_result = robust_classify(client, text)
        print(f"  Robust (normalized):              {robust_result}")


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        return

    client = anthropic.Anthropic(api_key=api_key)

    print("=== Lesson 04: The Probabilistic Mindset ===")
    print("This script makes ~40 API calls. Estimated cost: <$0.01 (Haiku)\n")

    # 1. Observe variance with a simple question
    print("--- Part 1: Observe Output Variance (temperature=1.0) ---")
    prompt = "Is 'The meeting was fine' POSITIVE, NEGATIVE, or NEUTRAL? One word only."
    stats = measure_distribution(client, prompt, n=10, temperature=1.0)

    # 2. Compare temperatures
    print("\n--- Part 2: Temperature Effect on Variance ---")
    compare_temperatures(client, prompt, [0.0, 1.0], n_per_temp=5)

    # 3. Brittle vs. robust handling
    print("\n--- Part 3: Brittle vs. Robust Output Handling ---")
    demonstrate_brittle_vs_robust(client)

    # 4. Summary
    print("\n=== Summary ===")
    print(f"In Part 1, the prompt generated {stats['unique_count']} unique outputs.")
    print(f"Consistency at temperature=1.0: {stats['consistency_pct']:.0f}%")
    print()
    print("Key takeaways:")
    print("1. The same prompt does not always produce the same output.")
    print("2. Temperature=0.0 minimizes variance for structured tasks.")
    print("3. Always normalize model output before comparing -- never exact-match.")
    print("4. One test run tells you nothing about your system's failure rate.")
    print("5. Eval N outputs, not 1.")


if __name__ == "__main__":
    main()
