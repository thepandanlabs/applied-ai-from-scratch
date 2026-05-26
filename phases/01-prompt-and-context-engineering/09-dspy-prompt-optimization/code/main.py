# Programmatic Prompt Optimization with DSPy
# Lesson 09: Phase 01 - Prompt and Context Engineering
#
# pip install dspy anthropic
# export ANTHROPIC_API_KEY=sk-ant-...

import os
import random
from typing import Literal

import dspy
from dspy.teleprompt import BootstrapFewShot


# ---------------------------------------------------------------------------
# Configure DSPy with Claude
# ---------------------------------------------------------------------------

def setup_dspy():
    """Configure DSPy to use Claude 3.5 Haiku via the Anthropic provider."""
    lm = dspy.LM(
        model="anthropic/claude-3-5-haiku-20241022",
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        max_tokens=256,
        temperature=0.0,
    )
    dspy.configure(lm=lm)
    print("DSPy configured with claude-3-5-haiku-20241022")


# ---------------------------------------------------------------------------
# Signature: declares inputs and outputs
# ---------------------------------------------------------------------------

class ClassifyTicket(dspy.Signature):
    """Classify a customer support ticket into exactly one category."""

    message: str = dspy.InputField(
        desc="The raw text of a customer support ticket."
    )
    category: Literal[
        "billing", "technical", "shipping", "returns", "general"
    ] = dspy.OutputField(
        desc=(
            "The support category that best fits the ticket. "
            "Must be one of: billing, technical, shipping, returns, general."
        )
    )


# ---------------------------------------------------------------------------
# Labeled examples
# ---------------------------------------------------------------------------

def build_dataset() -> tuple[list[dspy.Example], list[dspy.Example]]:
    """
    Build a labeled dataset and split into train (optimizer) and dev (evaluation).
    In production you would load this from a CSV or database.
    """
    all_examples = [
        dspy.Example(message="My invoice shows a double charge from last month.", category="billing"),
        dspy.Example(message="The app crashes every time I try to upload a file.", category="technical"),
        dspy.Example(message="My package was supposed to arrive 3 days ago. Where is it?", category="shipping"),
        dspy.Example(message="I want to return the jacket I bought last week.", category="returns"),
        dspy.Example(message="Can you tell me your store hours?", category="general"),
        dspy.Example(message="I was charged twice for the same subscription.", category="billing"),
        dspy.Example(message="The login page keeps showing an error code 503.", category="technical"),
        dspy.Example(message="My order has been in transit for 12 days with no updates.", category="shipping"),
        dspy.Example(message="How do I return a damaged item I received?", category="returns"),
        dspy.Example(message="Do you offer student discounts?", category="general"),
        dspy.Example(message="My credit card was charged but the order was never confirmed.", category="billing"),
        dspy.Example(message="The mobile app does not work on iOS 17.", category="technical"),
        dspy.Example(message="I need to change the delivery address for my current order.", category="shipping"),
        dspy.Example(message="I accidentally ordered the wrong size. Can I exchange it?", category="returns"),
        dspy.Example(message="What payment methods do you accept?", category="general"),
        dspy.Example(message="Why was my refund only partial?", category="billing"),
        dspy.Example(message="The password reset email never arrives.", category="technical"),
        dspy.Example(message="My package shows delivered but I never received it.", category="shipping"),
        dspy.Example(message="Your return policy page gives a 404 error.", category="technical"),
        dspy.Example(message="I have a question about your loyalty rewards program.", category="general"),
    ]

    random.seed(42)
    shuffled = all_examples[:]
    random.shuffle(shuffled)

    # 14 for the optimizer, 6 held out for evaluation
    train_set = [ex.with_inputs("message") for ex in shuffled[:14]]
    dev_set   = [ex.with_inputs("message") for ex in shuffled[14:]]

    print(f"Dataset split: {len(train_set)} train, {len(dev_set)} dev")
    return train_set, dev_set


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------

def accuracy_metric(example: dspy.Example, prediction, trace=None) -> bool:
    """
    Returns True if the predicted category matches the gold label.
    Case-insensitive comparison. DSPy optimizers call this on every
    training example to score candidate programs.
    """
    pred_label = getattr(prediction, "category", "").strip().lower()
    gold_label = example.category.strip().lower()
    return pred_label == gold_label


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_module(module, eval_set: list, label: str) -> float:
    """
    Run a module against an eval set.
    Prints per-example results and final accuracy.
    Returns accuracy as a float between 0 and 1.
    """
    correct = 0
    print(f"\n{'=' * 55}")
    print(f"Evaluating: {label}")
    print(f"{'=' * 55}")

    for ex in eval_set:
        try:
            pred = module(message=ex.message)
            is_correct = accuracy_metric(ex, pred)
            correct += int(is_correct)
            status = "OK   " if is_correct else "WRONG"
            short_msg = ex.message[:48] + "..." if len(ex.message) > 48 else ex.message
            pred_cat = getattr(pred, "category", "ERROR")
            print(f"  [{status}] gold={ex.category:<10} pred={pred_cat:<10} '{short_msg}'")
        except Exception as e:
            print(f"  [ERROR] {ex.message[:50]}: {e}")

    acc = correct / len(eval_set) if eval_set else 0.0
    print(f"\n  Accuracy: {correct}/{len(eval_set)} = {acc:.1%}")
    return acc


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

def run_optimization(train_set: list) -> dspy.Predict:
    """
    Run BootstrapFewShot to compile an optimized version of the classifier.

    BootstrapFewShot:
    - Generates candidate demonstrations by running the student module on train_set
    - Filters to examples where the module predicted correctly
    - Selects the best subset of demonstrations to include in the compiled prompt

    Returns the compiled (optimized) module.
    """
    optimizer = BootstrapFewShot(
        metric=accuracy_metric,
        max_bootstrapped_demos=4,   # max auto-generated few-shot examples
        max_labeled_demos=4,        # also use provided gold-labeled examples
        max_rounds=1,
    )

    print("\nCompiling optimized module (this runs LLM calls on train_set)...")
    student = dspy.Predict(ClassifyTicket)
    optimized = optimizer.compile(student=student, trainset=train_set)
    print("Compilation complete.")
    return optimized


# ---------------------------------------------------------------------------
# Save / load (production pattern)
# ---------------------------------------------------------------------------

def demo_save_load(optimized_module, path: str = "/tmp/optimized_classifier.json"):
    """
    Demonstrate saving the compiled program and loading it for production use.
    Compilation is expensive; save the result and load it at startup.
    """
    optimized_module.save(path)
    print(f"\nCompiled module saved to: {path}")

    # Simulate loading in a fresh process
    loaded = dspy.Predict(ClassifyTicket)
    loaded.load(path)
    print("Compiled module loaded successfully.")

    # Quick smoke test
    test_msg = "I was charged twice and need a refund."
    result = loaded(message=test_msg)
    print(f"Smoke test: '{test_msg}' -> {result.category}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 55)
    print("LESSON 09: PROGRAMMATIC PROMPT OPTIMIZATION WITH DSPY")
    print("=" * 55)

    # 1. Configure DSPy
    setup_dspy()

    # 2. Load data
    train_set, dev_set = build_dataset()

    # 3. Baseline: unoptimized module
    baseline_module = dspy.Predict(ClassifyTicket)

    # 4. Evaluate baseline
    baseline_acc = evaluate_module(
        baseline_module, dev_set, "Baseline (no optimization)"
    )

    # 5. Run optimizer
    optimized_module = run_optimization(train_set)

    # 6. Evaluate optimized module
    optimized_acc = evaluate_module(
        optimized_module, dev_set, "Optimized (BootstrapFewShot)"
    )

    # 7. Summary
    print("\n" + "=" * 55)
    print("SUMMARY")
    print("=" * 55)
    delta = optimized_acc - baseline_acc
    print(f"  Baseline accuracy:  {baseline_acc:.1%}")
    print(f"  Optimized accuracy: {optimized_acc:.1%}")
    print(f"  Delta:              {delta:+.1%}")

    if delta > 0.05:
        print("  Result: DSPy optimization helped significantly.")
    elif delta > 0:
        print("  Result: Minor improvement. Try more training data or MIPROv2.")
    else:
        print("  Result: No improvement on this small dev set. Expected with <20 examples.")
        print("  Tip: Use 100+ labeled examples for reliable results.")

    # 8. Inspect compiled state
    print("\n--- Compiled prompt state (what the optimizer chose) ---")
    try:
        optimized_module.dump_state()
    except Exception:
        print("(dump_state not available in this DSPy version; use .inspect_history())")

    # 9. Save/load demo
    demo_save_load(optimized_module)


if __name__ == "__main__":
    main()
