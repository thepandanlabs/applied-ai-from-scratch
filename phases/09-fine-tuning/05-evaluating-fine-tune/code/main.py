"""
Lesson 09-05: Evaluating a Fine-Tune vs Baseline
Eval harness: compare two models on a JSONL test set.

Usage:
  python main.py --demo                       # simulated eval, no API keys
  python main.py \\
    --baseline claude-3-5-haiku-20241022 \\
    --fine-tuned ft:gpt-4o-mini-2024-07-18:org::abc123 \\
    --test-set test.jsonl \\
    --threshold 0.15

JSONL test set format (one JSON object per line):
  {"input": "...", "expected_output": "..."}

Dependencies:
  pip install anthropic openai

The demo path requires no external libraries.
"""

from __future__ import annotations
import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TestExample:
    input: str
    expected_output: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ModelResult:
    """Result for a single example from one model."""
    output: str
    latency_ms: float
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class EvalResult:
    """Aggregated evaluation results for one model over the full test set."""
    model_id: str
    total: int
    exact_match: int
    format_valid: int
    errors: int
    total_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int

    @property
    def accuracy(self) -> float:
        return self.exact_match / self.total if self.total > 0 else 0.0

    @property
    def validity_rate(self) -> float:
        return self.format_valid / self.total if self.total > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.total if self.total > 0 else 0.0

    @property
    def error_rate(self) -> float:
        return self.errors / self.total if self.total > 0 else 0.0


# ---------------------------------------------------------------------------
# Output normalization and comparison
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """
    Normalize model output for comparison.
    If text is valid JSON, parse and re-serialize with sorted keys
    so {"b":1,"a":2} == {"a":2,"b":1}.
    Otherwise, strip whitespace and lowercase.
    """
    text = text.strip()
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        return text.lower()


def is_valid_json(text: str) -> bool:
    """Return True if text is parseable as JSON."""
    try:
        json.loads(text.strip())
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def is_exact_match(output: str, expected: str) -> bool:
    """Compare normalized output against expected."""
    return normalize(output) == normalize(expected)


# ---------------------------------------------------------------------------
# Model inference
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a data extraction assistant. Extract the requested information "
    "from the input and return it as valid JSON. Return only the JSON object, "
    "no explanation."
)


def call_anthropic(model_id: str, user_input: str, api_key: str) -> ModelResult:
    """Call an Anthropic model and return result with latency."""
    try:
        import anthropic
    except ImportError:
        return ModelResult(output="", latency_ms=0, error="anthropic package not installed")

    client = anthropic.Anthropic(api_key=api_key)
    start = time.time()
    try:
        response = client.messages.create(
            model=model_id,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_input}],
        )
        elapsed_ms = (time.time() - start) * 1000
        output = response.content[0].text if response.content else ""
        return ModelResult(
            output=output,
            latency_ms=elapsed_ms,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return ModelResult(output="", latency_ms=elapsed_ms, error=str(e))


def call_openai(model_id: str, user_input: str, api_key: str) -> ModelResult:
    """Call an OpenAI or OpenAI-compatible fine-tuned model."""
    try:
        from openai import OpenAI
    except ImportError:
        return ModelResult(output="", latency_ms=0, error="openai package not installed")

    client = OpenAI(api_key=api_key)
    start = time.time()
    try:
        response = client.chat.completions.create(
            model=model_id,
            max_tokens=512,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
        )
        elapsed_ms = (time.time() - start) * 1000
        output = response.choices[0].message.content or ""
        usage = response.usage
        return ModelResult(
            output=output,
            latency_ms=elapsed_ms,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return ModelResult(output="", latency_ms=elapsed_ms, error=str(e))


def run_model(model_id: str, user_input: str) -> ModelResult:
    """
    Route to the correct inference backend based on model_id prefix.
    Anthropic models: claude-*
    OpenAI models: gpt-*, ft:gpt-*, ft:*
    """
    if model_id.startswith("claude"):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return ModelResult(output="", latency_ms=0, error="ANTHROPIC_API_KEY not set")
        return call_anthropic(model_id, user_input, api_key)
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return ModelResult(output="", latency_ms=0, error="OPENAI_API_KEY not set")
        return call_openai(model_id, user_input, api_key)


# ---------------------------------------------------------------------------
# Eval loop
# ---------------------------------------------------------------------------

def run_eval(
    model_id: str,
    examples: list[TestExample],
    verbose: bool = False,
) -> EvalResult:
    """Run a model against all examples and aggregate metrics."""
    exact_match = 0
    format_valid = 0
    errors = 0
    total_latency = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    for i, ex in enumerate(examples, 1):
        if verbose:
            print(f"  [{i}/{len(examples)}] Running {model_id}...", end="\r")

        result = run_model(model_id, ex.input)

        if result.error:
            errors += 1
            continue

        if is_exact_match(result.output, ex.expected_output):
            exact_match += 1
        if is_valid_json(result.output):
            format_valid += 1

        total_latency += result.latency_ms
        total_input_tokens += result.input_tokens
        total_output_tokens += result.output_tokens

    if verbose:
        print()  # clear the progress line

    return EvalResult(
        model_id=model_id,
        total=len(examples),
        exact_match=exact_match,
        format_valid=format_valid,
        errors=errors,
        total_latency_ms=total_latency,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_comparison(baseline: EvalResult, fine_tuned: EvalResult, threshold: float) -> dict:
    """Print side-by-side comparison and go/no-go recommendation."""
    acc_improvement = (fine_tuned.accuracy - baseline.accuracy) / baseline.accuracy if baseline.accuracy > 0 else 0
    val_improvement_pp = fine_tuned.validity_rate - baseline.validity_rate

    width = max(len(baseline.model_id), len(fine_tuned.model_id), 30)
    header = f"  {'MODEL':<{width}}  {'ACCURACY':>9}  {'VALID JSON':>10}  {'AVG LATENCY':>12}  {'ERRORS':>7}"
    rule = "  " + "-" * (width + 46)

    print()
    print("=" * (width + 50))
    print("Fine-Tune Evaluation Results")
    print("=" * (width + 50))
    print(header)
    print(rule)
    print(
        f"  {baseline.model_id:<{width}}"
        f"  {baseline.accuracy:>8.1%}"
        f"  {baseline.validity_rate:>9.1%}"
        f"  {baseline.avg_latency_ms:>10.0f}ms"
        f"  {baseline.errors:>6}/{baseline.total}"
    )
    print(
        f"  {fine_tuned.model_id:<{width}}"
        f"  {fine_tuned.accuracy:>8.1%}"
        f"  {fine_tuned.validity_rate:>9.1%}"
        f"  {fine_tuned.avg_latency_ms:>10.0f}ms"
        f"  {fine_tuned.errors:>6}/{fine_tuned.total}"
    )
    print(rule)
    print()

    print(f"  Relative accuracy improvement:  {acc_improvement:+.1%}")
    print(f"  Format validity change:         {val_improvement_pp:+.1%} pp")
    print(f"  Threshold for GO:               {threshold:.0%}")
    print()

    if acc_improvement >= threshold:
        verdict = "GO"
        reason = f"Fine-tune is {acc_improvement:.1%} better (>= {threshold:.0%} threshold). Deploy the fine-tuned model."
        exit_code = 0
    elif acc_improvement > 0:
        verdict = "NO-GO"
        reason = (
            f"Fine-tune is {acc_improvement:.1%} better but below the {threshold:.0%} threshold. "
            "Improvement does not justify operational overhead."
        )
        exit_code = 1
    else:
        verdict = "NO-GO"
        reason = "Fine-tune is not better than baseline. Keep the baseline model."
        exit_code = 1

    print(f"  Decision: {verdict}")
    print(f"  Reason:   {reason}")
    print()

    summary = {
        "baseline_accuracy": baseline.accuracy,
        "fine_tuned_accuracy": fine_tuned.accuracy,
        "relative_improvement": acc_improvement,
        "threshold": threshold,
        "verdict": verdict,
        "baseline_validity": baseline.validity_rate,
        "fine_tuned_validity": fine_tuned.validity_rate,
    }
    return summary, exit_code


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------

DEMO_EXAMPLES = [
    {
        "input": "Patient: John Smith, DOB 1965-03-12. Chief complaint: chest pain radiating to left arm, started 2 hours ago. Vitals: BP 145/92, HR 98, O2 sat 96%.",
        "expected_output": '{"triage_level": "emergent", "chief_complaint": "chest pain", "key_symptoms": ["radiating to left arm", "2 hours duration"], "vitals_flag": "hypertension"}'
    },
    {
        "input": "Patient: Maria Chen, DOB 1990-07-22. Chief complaint: sprained ankle after fall, mild swelling, able to bear weight. Vitals: BP 118/76, HR 72, O2 sat 99%.",
        "expected_output": '{"triage_level": "non-urgent", "chief_complaint": "ankle sprain", "key_symptoms": ["mild swelling", "weight bearing intact"], "vitals_flag": null}'
    },
    {
        "input": "Patient: Robert Johnson, DOB 1958-11-03. Chief complaint: confusion and slurred speech, sudden onset 45 minutes ago. Vitals: BP 168/104, HR 88, O2 sat 97%.",
        "expected_output": '{"triage_level": "emergent", "chief_complaint": "acute neurological symptoms", "key_symptoms": ["confusion", "slurred speech", "sudden onset"], "vitals_flag": "hypertensive crisis"}'
    },
    {
        "input": "Patient: Sofia Reyes, DOB 2003-05-30. Chief complaint: sore throat and low-grade fever for 2 days, tolerating fluids. Vitals: BP 110/70, HR 80, O2 sat 98%, temp 38.1C.",
        "expected_output": '{"triage_level": "urgent", "chief_complaint": "pharyngitis", "key_symptoms": ["sore throat", "low-grade fever", "2 days duration"], "vitals_flag": "low-grade fever"}'
    },
    {
        "input": "Patient: David Park, DOB 1947-09-15. Chief complaint: shortness of breath at rest, bilateral leg edema, worse over 3 days. Vitals: BP 156/98, HR 102, O2 sat 91%.",
        "expected_output": '{"triage_level": "emergent", "chief_complaint": "acute dyspnea", "key_symptoms": ["rest dyspnea", "bilateral edema", "3 day progression"], "vitals_flag": "hypoxia"}'
    },
]


def make_demo_result(model_id: str, examples: list[TestExample], accuracy: float, validity: float) -> EvalResult:
    """
    Generate a simulated EvalResult for demo purposes.
    accuracy and validity are the target rates (0.0 to 1.0).
    """
    total = len(examples)
    exact_match = round(total * accuracy)
    format_valid = round(total * validity)
    avg_latency = random.uniform(280, 420)

    return EvalResult(
        model_id=model_id,
        total=total,
        exact_match=exact_match,
        format_valid=format_valid,
        errors=0,
        total_latency_ms=avg_latency * total,
        total_input_tokens=total * 180,
        total_output_tokens=total * 65,
    )


def demo_mode() -> None:
    """Run a simulated evaluation with no API keys."""
    print()
    print("=" * 65)
    print("Lesson 09-05: Evaluating a Fine-Tune vs Baseline - Demo Mode")
    print("Simulated results. No API keys required.")
    print("=" * 65)

    examples = [TestExample(e["input"], e["expected_output"]) for e in DEMO_EXAMPLES]

    print(f"\nTest set: {len(examples)} examples (clinical JSON extraction)")
    print("Baseline: claude-3-5-haiku-20241022")
    print("Fine-tune: ft-clinical-qa-qlora-r16-epoch3 (simulated)")
    print()
    print("Running baseline evaluation...")
    time.sleep(0.3)
    baseline_result = make_demo_result(
        "claude-3-5-haiku-20241022", examples, accuracy=0.62, validity=0.915
    )
    print(f"  Baseline complete: {baseline_result.exact_match}/{baseline_result.total} exact match")

    print("Running fine-tuned model evaluation...")
    time.sleep(0.3)
    ft_result = make_demo_result(
        "ft-clinical-qa-qlora-r16-epoch3", examples, accuracy=0.74, validity=0.97
    )
    print(f"  Fine-tune complete: {ft_result.exact_match}/{ft_result.total} exact match")

    summary, exit_code = print_comparison(baseline_result, ft_result, threshold=0.15)

    print("=" * 65)
    print("To run with real models:")
    print("  export ANTHROPIC_API_KEY=sk-...")
    print("  export OPENAI_API_KEY=sk-...")
    print("  python main.py \\")
    print("    --baseline claude-3-5-haiku-20241022 \\")
    print("    --fine-tuned ft:gpt-4o-mini-2024-07-18:org::abc123 \\")
    print("    --test-set test.jsonl \\")
    print("    --threshold 0.15")
    print("=" * 65)


# ---------------------------------------------------------------------------
# Test set loading
# ---------------------------------------------------------------------------

def load_test_set(path: str) -> list[TestExample]:
    """Load JSONL test set. Each line must have 'input' and 'expected_output'."""
    examples = []
    p = Path(path)
    if not p.exists():
        print(f"ERROR: Test file not found: {path}")
        sys.exit(1)

    with open(p) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"ERROR: Invalid JSON on line {i}: {e}")
                sys.exit(1)

            if "input" not in obj or "expected_output" not in obj:
                print(f"ERROR: Line {i} missing 'input' or 'expected_output' field")
                sys.exit(1)

            examples.append(TestExample(
                input=obj["input"],
                expected_output=obj["expected_output"],
                metadata={k: v for k, v in obj.items() if k not in ("input", "expected_output")},
            ))

    print(f"Loaded {len(examples)} examples from {path}")
    return examples


def generate_sample_test_set(output_path: str) -> None:
    """Write the demo examples as a JSONL test set for testing."""
    p = Path(output_path)
    with open(p, "w") as f:
        for ex in DEMO_EXAMPLES:
            f.write(json.dumps(ex) + "\n")
    print(f"Sample test set written to {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fine-tune evaluation harness: compare two models on a test set",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --demo
  python main.py --generate-sample test.jsonl
  python main.py --baseline claude-3-5-haiku-20241022 \\
                 --fine-tuned ft:gpt-4o-mini-2024-07-18:org::abc123 \\
                 --test-set test.jsonl \\
                 --threshold 0.15
        """,
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run simulated evaluation without API keys",
    )
    parser.add_argument(
        "--generate-sample",
        type=str,
        metavar="OUTPUT_PATH",
        help="Write sample JSONL test set to file and exit",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default=None,
        help="Baseline model ID (e.g., claude-3-5-haiku-20241022)",
    )
    parser.add_argument(
        "--fine-tuned",
        type=str,
        default=None,
        help="Fine-tuned model ID (e.g., ft:gpt-4o-mini-2024-07-18:org::abc123)",
    )
    parser.add_argument(
        "--test-set",
        type=str,
        default=None,
        help="Path to JSONL test file",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.15,
        help="Minimum relative accuracy improvement for GO decision (default: 0.15 = 15%%)",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Write summary JSON to this file",
    )
    parser.add_argument(
        "--fail-below-threshold",
        action="store_true",
        help="Exit with code 1 if fine-tune does not meet threshold (for CI use)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress during evaluation",
    )
    args = parser.parse_args()

    if args.generate_sample:
        generate_sample_test_set(args.generate_sample)
        return

    if args.demo or (args.baseline is None and args.fine_tuned is None):
        demo_mode()
        return

    # Validate arguments for real run
    missing = []
    if not args.baseline:
        missing.append("--baseline")
    if not args.fine_tuned:
        missing.append("--fine-tuned")
    if not args.test_set:
        missing.append("--test-set")
    if missing:
        print(f"ERROR: Missing required arguments: {', '.join(missing)}")
        parser.print_help()
        sys.exit(1)

    # Load test set
    examples = load_test_set(args.test_set)
    if len(examples) < 50:
        print(f"WARNING: Only {len(examples)} examples. Results may not be statistically reliable.")
        print("         Recommendation: use at least 200 examples for a go/no-go decision.")
    print()

    # Run both models
    print(f"Evaluating baseline: {args.baseline}")
    baseline_result = run_eval(args.baseline, examples, verbose=args.verbose)

    print(f"Evaluating fine-tuned: {args.fine_tuned}")
    ft_result = run_eval(args.fine_tuned, examples, verbose=args.verbose)

    # Compare and decide
    summary, exit_code = print_comparison(baseline_result, ft_result, threshold=args.threshold)

    # Write JSON output if requested
    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Summary written to {args.output_json}")

    if args.fail_below_threshold and exit_code != 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
