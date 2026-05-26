"""
L07: Distillation for Cost
DistillationPipeline: teacher model generates, LLM judge filters, JSONL saved for fine-tuning.

Usage:
    python main.py                      # run demo distillation pipeline
    python main.py --prompts data.txt   # distill from a file of prompts (one per line)
    python main.py --threshold 4.0      # set a stricter quality threshold
    python main.py --dry-run            # validate setup without API calls

Requires: ANTHROPIC_API_KEY environment variable
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

import anthropic

client = anthropic.Anthropic()

TEACHER_MODEL = "claude-opus-4-5"
JUDGE_MODEL = "claude-3-5-haiku-20241022"


@dataclass
class DistillationExample:
    prompt: str
    completion: str
    quality_score: Optional[float] = None
    kept: bool = False


class DistillationPipeline:
    """
    Teacher-student distillation with LLM quality filtering.

    Pipeline:
    1. Run each prompt through the teacher model
    2. Score each output with an LLM judge (1-5 scale)
    3. Keep only examples that meet the quality threshold
    4. Save kept examples as JSONL for fine-tuning

    The quality filter is critical: training on poor teacher outputs
    produces a poor student. Discard rate of 40-60% is normal and healthy.
    """

    def __init__(
        self,
        quality_threshold: float = 3.5,
        teacher: str = TEACHER_MODEL,
        judge: str = JUDGE_MODEL,
        rate_limit_delay: float = 0.5,
    ):
        self.quality_threshold = quality_threshold
        self.teacher = teacher
        self.judge = judge
        self.rate_limit_delay = rate_limit_delay
        self.stats = {
            "generated": 0,
            "judged": 0,
            "kept": 0,
            "discarded": 0,
            "errors": 0,
        }

    def generate(self, prompt: str, system: str = "") -> str:
        """Run the teacher model on one prompt."""
        messages = [{"role": "user", "content": prompt}]
        kwargs: dict = {
            "model": self.teacher,
            "max_tokens": 1024,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        return response.content[0].text

    def judge_quality(
        self, prompt: str, completion: str, task_description: str
    ) -> float:
        """Score a completion 1-5 using an LLM judge. Returns 1.0 on parse failure."""
        judge_prompt = f"""You are a quality evaluator for AI training data.

Task the model was asked to do: {task_description}

User prompt:
{prompt}

Model completion:
{completion}

Score this completion from 1 to 5:
1 = Wrong, incomplete, or harmful
2 = Partially correct, missing key information
3 = Correct but could be cleaner or more complete
4 = Good quality, accurate, well-formatted
5 = Excellent - exactly what a human expert would produce

Respond with ONLY a number 1-5. No explanation."""

        response = client.messages.create(
            model=self.judge,
            max_tokens=10,
            messages=[{"role": "user", "content": judge_prompt}],
        )
        try:
            score = float(response.content[0].text.strip())
            return max(1.0, min(5.0, score))  # clamp to [1, 5]
        except ValueError:
            return 1.0

    def run(
        self,
        prompts: list[str],
        task_description: str,
        system: str = "",
        output_path: str = "distilled.jsonl",
        verbose: bool = True,
    ) -> dict:
        """
        Run the full distillation pipeline and save results to JSONL.

        Args:
            prompts: List of user prompts to generate teacher completions for
            task_description: Human-readable description of the task (for the judge)
            system: Optional system prompt for the teacher
            output_path: Where to save the filtered JSONL dataset
            verbose: Print progress

        Returns:
            Stats dict with counts and keep rate
        """
        # Reset stats
        self.stats = {k: 0 for k in self.stats}
        examples = []

        for i, prompt in enumerate(prompts):
            if verbose:
                print(f"  [{i + 1}/{len(prompts)}] Generating...", end=" ", flush=True)

            try:
                completion = self.generate(prompt, system=system)
                self.stats["generated"] += 1

                score = self.judge_quality(prompt, completion, task_description)
                self.stats["judged"] += 1

                kept = score >= self.quality_threshold
                ex = DistillationExample(
                    prompt=prompt,
                    completion=completion,
                    quality_score=score,
                    kept=kept,
                )
                examples.append(ex)

                if kept:
                    self.stats["kept"] += 1
                    status = f"KEEP (score={score:.1f})"
                else:
                    self.stats["discarded"] += 1
                    status = f"DROP (score={score:.1f})"

                if verbose:
                    print(status)

            except Exception as e:
                self.stats["errors"] += 1
                if verbose:
                    print(f"ERROR: {e}")

            time.sleep(self.rate_limit_delay)

        # Write kept examples only
        kept_examples = [e for e in examples if e.kept]
        with open(output_path, "w") as f:
            for ex in kept_examples:
                record = {
                    "messages": [
                        {"role": "user", "content": ex.prompt},
                        {"role": "assistant", "content": ex.completion},
                    ]
                }
                f.write(json.dumps(record) + "\n")

        keep_rate = self.stats["kept"] / max(self.stats["generated"], 1) * 100
        return {
            **self.stats,
            "keep_rate_pct": round(keep_rate, 1),
            "output_path": output_path,
        }

    def print_report(self, result: dict) -> None:
        print("\n=== Distillation Pipeline Report ===")
        print(f"  Generated:      {result['generated']}")
        print(f"  Judged:         {result['judged']}")
        print(f"  Kept:           {result['kept']} ({result['keep_rate_pct']}%)")
        print(f"  Discarded:      {result['discarded']}")
        print(f"  Errors:         {result['errors']}")
        print(f"  Output:         {result['output_path']}")

        if result["keep_rate_pct"] < 40:
            print("\n  WARNING: Keep rate below 40%. Check teacher model quality")
            print("  or lower the quality threshold.")
        elif result["keep_rate_pct"] > 95:
            print("\n  INFO: Very high keep rate. Consider raising threshold.")
        else:
            print(f"\n  Quality gate: PASS ({result['keep_rate_pct']}% retained)")


def compute_cost_comparison(
    daily_calls: int,
    avg_output_tokens: int,
    teacher_price_per_1m: float = 15.0,
    student_price_per_1m: float = 1.25,
    finetune_cost_usd: float = 50.0,
) -> dict:
    """
    Calculate cost comparison between teacher (pre-distillation) and
    student (post-distillation) at given production volume.
    """
    tokens_per_day = daily_calls * avg_output_tokens

    teacher_daily = (tokens_per_day / 1_000_000) * teacher_price_per_1m
    student_daily = (tokens_per_day / 1_000_000) * student_price_per_1m

    teacher_monthly = teacher_daily * 30
    student_monthly = student_daily * 30
    monthly_savings = teacher_monthly - student_monthly

    if monthly_savings <= 0:
        payback_months = float("inf")
    else:
        payback_months = finetune_cost_usd / monthly_savings

    return {
        "daily_calls": daily_calls,
        "avg_output_tokens": avg_output_tokens,
        "teacher_cost_per_day_usd": round(teacher_daily, 2),
        "student_cost_per_day_usd": round(student_daily, 2),
        "teacher_cost_per_month_usd": round(teacher_monthly, 2),
        "student_cost_per_month_usd": round(student_monthly, 2),
        "monthly_savings_usd": round(monthly_savings, 2),
        "finetune_cost_usd": finetune_cost_usd,
        "payback_months": round(payback_months, 1),
        "recommendation": "PROCEED" if payback_months <= 3 else "EVALUATE",
    }


# Demo task: legal contract entity extraction
DEMO_SYSTEM = """You are a legal contract parser. Extract structured data
from contract clauses. Respond with a JSON object containing:
  parties: list of party names
  effective_date: date string or null
  obligation: brief summary of the primary obligation"""

DEMO_TASK_DESCRIPTION = (
    "Extract party names, effective date, and primary obligation "
    "from legal contract clauses as structured JSON."
)

DEMO_PROMPTS = [
    (
        "Extract the key information:\n\n"
        "This Agreement is entered into as of January 15, 2025, between "
        "Acme Corp ('Vendor') and Beta LLC ('Client'). Vendor shall deliver "
        "software within 30 days of purchase order receipt."
    ),
    (
        "Extract the key information:\n\n"
        "Effective March 1, 2025, DataSystems Inc and CloudHost Partners agree "
        "that CloudHost will maintain 99.9% uptime SLA for hosted services."
    ),
    (
        "Extract the key information:\n\n"
        "As of the Effective Date, FinCo Inc. ('Borrower') agrees to repay "
        "LoanCorp ('Lender') the principal amount of $500,000 by December 31, 2025."
    ),
    (
        "Extract the key information:\n\n"
        "GlobalTech Ltd and RegionalBank NA entered this agreement on April 5, 2025. "
        "RegionalBank NA shall process all payment transactions within 48 hours."
    ),
    (
        "Extract the key information:\n\n"
        "This Services Agreement between ConsultCo and TechStart LLC, "
        "commencing June 1, 2025, requires ConsultCo to provide 40 hours per "
        "month of engineering consulting services."
    ),
]


def main():
    parser = argparse.ArgumentParser(
        description="Distillation pipeline: teacher generates, judge filters, JSONL saved."
    )
    parser.add_argument(
        "--prompts",
        help="Path to file with prompts (one per line). Default: use demo prompts.",
        default=None,
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSONL path (default: distilled.jsonl)",
        default="distilled.jsonl",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=3.5,
        help="Quality threshold for keeping examples (1-5, default: 3.5)",
    )
    parser.add_argument(
        "--daily-calls",
        type=int,
        default=500,
        help="Daily call volume for ROI calculation (default: 500)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate setup without making API calls",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("Dry run: checking setup...")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            print("  ANTHROPIC_API_KEY: set")
        else:
            print("  ANTHROPIC_API_KEY: NOT SET (required)")
            return 1
        print(f"  Teacher model:    {TEACHER_MODEL}")
        print(f"  Judge model:      {JUDGE_MODEL}")
        print(f"  Quality threshold: {args.threshold}")
        print("  Setup OK.")
        return 0

    # Load prompts
    if args.prompts:
        with open(args.prompts) as f:
            prompts = [line.strip() for line in f if line.strip()]
        system = ""
        task_desc = "Complete the task described in each prompt."
    else:
        print("Using demo task: legal contract entity extraction")
        prompts = DEMO_PROMPTS
        system = DEMO_SYSTEM
        task_desc = DEMO_TASK_DESCRIPTION

    print(f"Distilling {len(prompts)} prompts (threshold={args.threshold})...")
    print(f"Teacher: {TEACHER_MODEL} | Judge: {JUDGE_MODEL}\n")

    pipeline = DistillationPipeline(
        quality_threshold=args.threshold,
        teacher=TEACHER_MODEL,
        judge=JUDGE_MODEL,
    )
    result = pipeline.run(
        prompts=prompts,
        task_description=task_desc,
        system=system,
        output_path=args.output,
    )
    pipeline.print_report(result)

    # Show cost comparison
    print("\n=== Cost Comparison at Production Volume ===")
    roi = compute_cost_comparison(
        daily_calls=args.daily_calls,
        avg_output_tokens=400,
    )
    print(f"  Daily calls:             {roi['daily_calls']}")
    print(f"  Teacher (Opus) cost/mo:  ${roi['teacher_cost_per_month_usd']}")
    print(f"  Student (Haiku) cost/mo: ${roi['student_cost_per_month_usd']}")
    print(f"  Monthly savings:         ${roi['monthly_savings_usd']}")
    print(f"  Fine-tune cost:          ${roi['finetune_cost_usd']}")
    print(f"  Payback period:          {roi['payback_months']} months")
    print(f"  Recommendation:          {roi['recommendation']}")

    # Preview output
    if result["kept"] > 0:
        print(f"\n=== Preview (first kept example) ===")
        with open(args.output) as f:
            first = json.loads(f.readline())
        user_msg = first["messages"][0]["content"]
        asst_msg = first["messages"][1]["content"]
        print(f"  User:      {user_msg[:100]}...")
        print(f"  Assistant: {asst_msg[:100]}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
