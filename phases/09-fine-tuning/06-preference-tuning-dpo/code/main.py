"""
L06: Preference Tuning with DPO
DPODatasetBuilder: convert human preference annotations to DPO JSONL format.

Usage:
    python main.py                  # run demo with synthetic annotations
    python main.py --input raw.json # convert a real annotation file
    python main.py --stats          # show stats only, no output file
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path


@dataclass
class PreferenceAnnotation:
    """Raw human annotation: two candidates, one preferred."""
    prompt: str
    response_a: str
    response_b: str
    preferred: str  # "A", "B", or "tie"
    annotator_id: Optional[str] = None


@dataclass
class DPOExample:
    """DPO training triplet (prompt, chosen, rejected)."""
    prompt: str
    chosen: str
    rejected: str


class DPODatasetBuilder:
    """
    Convert raw preference annotations to DPO JSONL format.

    Validation rules:
    - Ties are excluded (no clear preference signal)
    - Empty prompts are excluded
    - Identical chosen/rejected are excluded
    - Text length must be within [min_length, max_length]
    """

    def __init__(self, min_length: int = 20, max_length: int = 2000):
        self.min_length = min_length
        self.max_length = max_length
        self.stats = {
            "total": 0,
            "kept": 0,
            "rejected_tie": 0,
            "rejected_empty_prompt": 0,
            "rejected_identical": 0,
            "rejected_length": 0,
        }

    def validate(self, ann: PreferenceAnnotation) -> tuple[bool, str]:
        """
        Validate a single annotation.
        Returns (is_valid, rejection_reason).
        """
        if ann.preferred == "tie":
            return False, "tie"

        if not ann.prompt.strip():
            return False, "empty_prompt"

        if ann.preferred == "A":
            chosen = ann.response_a
            rejected = ann.response_b
        else:
            chosen = ann.response_b
            rejected = ann.response_a

        if chosen.strip() == rejected.strip():
            return False, "identical_responses"

        for label, text in [("chosen", chosen), ("rejected", rejected)]:
            stripped = text.strip()
            if len(stripped) < self.min_length:
                return False, f"too_short_{label}"
            if len(stripped) > self.max_length:
                return False, f"too_long_{label}"

        return True, "ok"

    def convert(self, ann: PreferenceAnnotation) -> Optional[DPOExample]:
        """Convert one annotation to a DPOExample, or None if invalid."""
        valid, reason = self.validate(ann)
        self.stats["total"] += 1

        if not valid:
            if reason == "tie":
                self.stats["rejected_tie"] += 1
            elif reason == "empty_prompt":
                self.stats["rejected_empty_prompt"] += 1
            elif reason == "identical_responses":
                self.stats["rejected_identical"] += 1
            else:  # too_short / too_long
                self.stats["rejected_length"] += 1
            return None

        self.stats["kept"] += 1
        chosen = ann.response_a if ann.preferred == "A" else ann.response_b
        rejected = ann.response_b if ann.preferred == "A" else ann.response_a
        return DPOExample(prompt=ann.prompt, chosen=chosen, rejected=rejected)

    def build(self, annotations: list[PreferenceAnnotation],
              output_path: str) -> dict:
        """
        Convert all annotations, write valid triplets to JSONL.
        Returns stats dict.
        """
        # Reset stats for each build call
        self.stats = {k: 0 for k in self.stats}

        examples = []
        for ann in annotations:
            ex = self.convert(ann)
            if ex:
                examples.append({
                    "prompt": ex.prompt,
                    "chosen": ex.chosen,
                    "rejected": ex.rejected,
                })

        with open(output_path, "w") as f:
            for ex in examples:
                f.write(json.dumps(ex) + "\n")

        keep_rate = (
            self.stats["kept"] / max(self.stats["total"], 1) * 100
        )
        return {
            **self.stats,
            "keep_rate_pct": round(keep_rate, 1),
            "output_path": output_path,
        }

    def print_report(self, result: dict) -> None:
        """Print a human-readable build report."""
        print("\n=== DPO Dataset Build Report ===")
        print(f"  Total annotations:     {result['total']}")
        print(f"  Kept:                  {result['kept']} ({result['keep_rate_pct']}%)")
        print(f"  Rejected - ties:       {result['rejected_tie']}")
        print(f"  Rejected - empty:      {result['rejected_empty_prompt']}")
        print(f"  Rejected - identical:  {result['rejected_identical']}")
        print(f"  Rejected - length:     {result['rejected_length']}")
        print(f"  Output file:           {result['output_path']}")

        if result["keep_rate_pct"] < 60:
            print("\n  WARNING: Keep rate below 60%. Review annotation guidelines.")
            print("  High tie rate suggests annotators see the options as too similar.")
        elif result["keep_rate_pct"] > 95:
            print("\n  INFO: Very high keep rate. Verify quality threshold is set correctly.")
        else:
            print("\n  Quality check: PASS")


def make_demo_annotations() -> list[PreferenceAnnotation]:
    """Synthetic preference annotations for demonstration."""
    return [
        PreferenceAnnotation(
            prompt="How do I reset my password?",
            response_a=(
                "Click 'Forgot password' on the login page. "
                "You'll receive an email within 2 minutes with a reset link. "
                "The link expires after 24 hours."
            ),
            response_b="Use the forgot password link.",
            preferred="A",
            annotator_id="ann_001",
        ),
        PreferenceAnnotation(
            prompt="What is the refund policy?",
            response_a=(
                "We offer full refunds within 30 days of purchase, "
                "no questions asked. After 30 days, store credit only."
            ),
            response_b=(
                "Our refund policy allows returns within 30 days for a full "
                "refund. Items returned after 30 days are eligible for store "
                "credit. Contact support@example.com to initiate a return."
            ),
            preferred="B",
            annotator_id="ann_002",
        ),
        PreferenceAnnotation(
            prompt="Is the product compatible with Windows 11?",
            response_a="Yes.",
            response_b=(
                "Yes, the product is fully compatible with Windows 11 "
                "(versions 21H2 and later). No additional drivers are required."
            ),
            preferred="B",
            annotator_id="ann_001",
        ),
        # Tie - will be excluded
        PreferenceAnnotation(
            prompt="How long does shipping take?",
            response_a="Standard shipping is 5-7 business days.",
            response_b="Shipping typically takes 5-7 business days.",
            preferred="tie",
            annotator_id="ann_003",
        ),
        # Another valid preference
        PreferenceAnnotation(
            prompt="Can I use the product offline?",
            response_a=(
                "Core features work offline. Sync and collaboration features "
                "require an internet connection."
            ),
            response_b="Some features need internet.",
            preferred="A",
            annotator_id="ann_002",
        ),
        # Too short - will be excluded
        PreferenceAnnotation(
            prompt="What formats are supported?",
            response_a="PDF, DOCX, PNG.",
            response_b="Only PDF.",
            preferred="A",
            annotator_id="ann_001",
        ),
        PreferenceAnnotation(
            prompt="How do I cancel my subscription?",
            response_a=(
                "To cancel, go to Account Settings > Subscription > Cancel Plan. "
                "Your access continues until the end of the current billing period."
            ),
            response_b=(
                "You can cancel anytime. Log in, go to settings, find your "
                "subscription, and click cancel. You won't be charged again but "
                "keep access until the period ends."
            ),
            preferred="A",
            annotator_id="ann_003",
        ),
    ]


def load_annotations_from_file(path: str) -> list[PreferenceAnnotation]:
    """
    Load annotations from a JSON file.
    Expected format: list of objects with keys:
      prompt, response_a, response_b, preferred, annotator_id (optional)
    """
    with open(path) as f:
        data = json.load(f)
    annotations = []
    for item in data:
        annotations.append(PreferenceAnnotation(
            prompt=item["prompt"],
            response_a=item["response_a"],
            response_b=item["response_b"],
            preferred=item["preferred"],
            annotator_id=item.get("annotator_id"),
        ))
    return annotations


def analyze_dataset(output_path: str) -> None:
    """Print length statistics for the built dataset."""
    chosen_lengths = []
    rejected_lengths = []

    with open(output_path) as f:
        for line in f:
            ex = json.loads(line)
            chosen_lengths.append(len(ex["chosen"]))
            rejected_lengths.append(len(ex["rejected"]))

    if not chosen_lengths:
        print("No examples in dataset.")
        return

    def stats(values: list[int]) -> str:
        mean = sum(values) / len(values)
        sorted_v = sorted(values)
        median = sorted_v[len(sorted_v) // 2]
        return f"mean={mean:.0f}, median={median}, min={min(values)}, max={max(values)}"

    print("\n=== Dataset Length Analysis ===")
    print(f"  Chosen   (chars): {stats(chosen_lengths)}")
    print(f"  Rejected (chars): {stats(rejected_lengths)}")

    ratio = sum(chosen_lengths) / max(sum(rejected_lengths), 1)
    if ratio > 2.0:
        print(f"\n  WARNING: Chosen responses are {ratio:.1f}x longer than rejected.")
        print("  Model may learn 'be verbose' rather than 'be better'.")
    else:
        print(f"  Length ratio (chosen/rejected): {ratio:.2f} - OK")


def main():
    parser = argparse.ArgumentParser(
        description="Build a DPO training dataset from preference annotations."
    )
    parser.add_argument(
        "--input", "-i",
        help="Path to input JSON annotation file (default: use demo data)",
        default=None,
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSONL path (default: dpo_dataset.jsonl)",
        default="dpo_dataset.jsonl",
    )
    parser.add_argument(
        "--min-length",
        type=int,
        default=20,
        help="Minimum text length in characters (default: 20)",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=2000,
        help="Maximum text length in characters (default: 2000)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Also print dataset length statistics after building",
    )
    args = parser.parse_args()

    # Load annotations
    if args.input:
        print(f"Loading annotations from: {args.input}")
        annotations = load_annotations_from_file(args.input)
    else:
        print("Using demo annotations (8 examples, 2 will be filtered)...")
        annotations = make_demo_annotations()

    # Build dataset
    builder = DPODatasetBuilder(
        min_length=args.min_length,
        max_length=args.max_length,
    )
    result = builder.build(annotations, output_path=args.output)
    builder.print_report(result)

    # Optional: show length analysis
    if args.stats and result["kept"] > 0:
        analyze_dataset(args.output)

    # Show a preview of the output
    if result["kept"] > 0:
        print(f"\n=== Preview (first example from {args.output}) ===")
        with open(args.output) as f:
            first = json.loads(f.readline())
        print(f"  Prompt:   {first['prompt'][:80]}...")
        print(f"  Chosen:   {first['chosen'][:80]}...")
        print(f"  Rejected: {first['rejected'][:80]}...")

    return 0 if result["kept"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
