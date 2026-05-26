"""
L09: Capstone - Fine-Tune for a Domain Task, Prove ROI with Evals

End-to-end fine-tuning project pipeline:
  1. Generate distilled training data (medical NER via teacher model)
  2. Submit managed fine-tuning job (Anthropic API)
  3. Run three-way evaluation (baseline vs prompt-eng vs fine-tuned)
  4. Calculate ROI and produce go/no-go recommendation

Usage:
    python main.py                    # run full pipeline (stages 1 + 3 + 4)
    python main.py --stage generate   # stage 1: generate training data only
    python main.py --stage evaluate   # stage 3: run eval against model IDs
    python main.py --stage roi        # stage 4: print ROI report
    python main.py --submit           # also submit the fine-tuning job (stage 2)
    python main.py --ft-model MODEL   # evaluate against a specific fine-tuned model

Requires: ANTHROPIC_API_KEY environment variable
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import anthropic

client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Task definition
# ---------------------------------------------------------------------------

DOMAIN_TASK = "medical_ner"
TASK_DESCRIPTION = (
    "Extract medical named entities from clinical notes. "
    "Return a JSON object with keys: drugs (list), dosages (list), conditions (list). "
    "Be precise - only extract entities explicitly mentioned in the text."
)

SYSTEM_PROMPT = (
    "You are a clinical NLP specialist. Extract drug names, dosages, and "
    "medical conditions from clinical notes. Respond only with valid JSON in "
    'the format: {"drugs": [], "dosages": [], "conditions": []}'
)

# Training notes (teacher distillation source)
TRAINING_NOTES = [
    "Patient prescribed metformin 500mg twice daily for type 2 diabetes. Monitoring HbA1c every 3 months.",
    "Started lisinopril 10mg QD for hypertension. Patient reports mild dry cough as known side effect.",
    "Atorvastatin 20mg nightly for hyperlipidemia. LFTs ordered at 3 months per protocol.",
    "Amoxicillin 875mg BID x10 days for streptococcal pharyngitis. Culture pending.",
    "Sertraline 50mg daily initiated for major depressive disorder. Follow up in 4 weeks.",
    "Metoprolol 25mg BID for atrial fibrillation rate control. HR target 60-80 bpm.",
    "Prednisone 40mg daily tapering course for acute exacerbation of COPD.",
    "Levothyroxine 88mcg daily for hypothyroidism. TSH target 0.5-2.5 mIU/L.",
    "Omeprazole 20mg daily for gastroesophageal reflux disease. Advised dietary modifications.",
    "Amlodipine 5mg once daily added for persistent hypertension despite lisinopril.",
]

# Test notes (held out from training)
TEST_NOTES = [
    "Warfarin 5mg daily for DVT prophylaxis post-surgery. INR goal 2-3.",
    "Albuterol inhaler PRN for asthma. Prescribed ICS for daily control.",
    "Furosemide 40mg QD for congestive heart failure with peripheral edema.",
    "Clonazepam 0.5mg BID for generalized anxiety disorder. Short-term use.",
    "Methotrexate 15mg weekly for rheumatoid arthritis. Monitor CBC and LFTs.",
]


# ---------------------------------------------------------------------------
# Stage 1: Distillation pipeline
# ---------------------------------------------------------------------------

@dataclass
class DistillationStats:
    generated: int = 0
    kept: int = 0
    discarded: int = 0


def _make_extraction_prompt(note: str) -> str:
    return f"Extract medical named entities from this clinical note:\n\n{note}"


def generate_training_data(
    notes: list[str],
    output_path: str = "medical_ner_training.jsonl",
    quality_threshold: float = 3.5,
    teacher_model: str = "claude-opus-4-5",
    judge_model: str = "claude-3-5-haiku-20241022",
) -> DistillationStats:
    """Generate and quality-filter training data via teacher-student distillation."""
    stats = DistillationStats()
    examples = []

    for i, note in enumerate(notes):
        prompt = _make_extraction_prompt(note)
        print(f"  [{i + 1}/{len(notes)}] Generating...", end=" ", flush=True)

        # Teacher generation
        try:
            response = client.messages.create(
                model=teacher_model,
                max_tokens=256,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            completion = response.content[0].text
            stats.generated += 1
        except Exception as e:
            print(f"error: {e}")
            continue

        # Quality judge
        judge_prompt = f"""Rate this medical NER extraction 1-5.

Clinical note: {note}
Extraction result: {completion}

5 = Perfect JSON, all entities extracted, no hallucinations
4 = Good, minor omissions only
3 = Acceptable but incomplete or slightly wrong format
2 = Wrong format or missed major entities
1 = Incorrect, hallucinated, or malformed

Respond with ONLY a single digit."""

        try:
            judge_response = client.messages.create(
                model=judge_model,
                max_tokens=5,
                messages=[{"role": "user", "content": judge_prompt}],
            )
            score = float(judge_response.content[0].text.strip())
        except (ValueError, Exception):
            score = 1.0

        if score >= quality_threshold:
            stats.kept += 1
            status = f"KEEP (score={score:.0f})"
            examples.append({
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": completion},
                ]
            })
        else:
            stats.discarded += 1
            status = f"DROP (score={score:.0f})"

        print(status)
        time.sleep(0.5)

    with open(output_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    keep_rate = stats.kept / max(stats.generated, 1) * 100
    print(f"\n  Generated: {stats.generated}, Kept: {stats.kept} "
          f"({keep_rate:.0f}%), Discarded: {stats.discarded}")
    print(f"  Training data saved: {output_path}")
    return stats


# ---------------------------------------------------------------------------
# Stage 2: Submit fine-tuning job
# ---------------------------------------------------------------------------

def submit_finetune_job(
    training_file: str,
    model: str = "claude-haiku-20250307",
    n_epochs: int = 3,
) -> str:
    """Upload training JSONL and submit a managed fine-tuning job."""
    fname = os.path.basename(training_file)

    print(f"  Uploading {fname}...")
    with open(training_file, "rb") as f:
        file_response = client.beta.files.upload(
            file=(fname, f, "application/jsonl"),
        )
    file_id = file_response.id
    print(f"  File uploaded: {file_id}")

    print(f"  Submitting fine-tuning job (model={model}, epochs={n_epochs})...")
    job = client.beta.fine_tuning.jobs.create(
        model=model,
        training_file=file_id,
        hyperparameters={"n_epochs": n_epochs},
    )
    print(f"  Job created: {job.id}")
    return job.id


def poll_job(job_id: str, poll_interval: int = 60) -> dict:
    """Poll until the fine-tuning job completes or fails."""
    print(f"  Polling job {job_id} every {poll_interval}s...")
    while True:
        job = client.beta.fine_tuning.jobs.retrieve(job_id)
        status = job.status
        print(f"  Status: {status}")
        if status in ("succeeded", "failed", "cancelled"):
            return {
                "job_id": job_id,
                "status": status,
                "fine_tuned_model": getattr(job, "fine_tuned_model", None),
            }
        time.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Stage 3: Three-way evaluation
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    model_label: str
    model_id: str
    note: str
    output: str
    valid_json: bool
    entity_count: int
    has_all_keys: bool


def _parse_ner_output(text: str) -> tuple[bool, int, bool]:
    """Parse NER output. Returns (valid_json, entity_count, has_all_keys)."""
    try:
        parsed = json.loads(text)
        required_keys = {"drugs", "dosages", "conditions"}
        has_all_keys = all(k in parsed for k in required_keys)
        entity_count = sum(
            len(parsed.get(k, [])) for k in required_keys
            if isinstance(parsed.get(k), list)
        )
        return True, entity_count, has_all_keys
    except json.JSONDecodeError:
        return False, 0, False


def run_model(
    model_id: str,
    note: str,
    system: str,
    use_system: bool = True,
) -> str:
    """Run one inference call against a model."""
    prompt = _make_extraction_prompt(note)
    kwargs: dict = {
        "model": model_id,
        "max_tokens": 256,
        "messages": [{"role": "user", "content": prompt}],
    }
    if use_system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text


def evaluate_three_way(
    test_notes: list[str],
    ft_model_id: str,
    baseline_model: str = "claude-3-5-haiku-20241022",
) -> dict:
    """
    Compare three conditions on the same test set:
    - baseline: no system prompt
    - prompt_eng: system prompt only, no fine-tuning
    - fine_tuned: fine-tuned model (or stand-in)
    """
    conditions = {
        "baseline": {"model": baseline_model, "use_system": False},
        "prompt_eng": {"model": baseline_model, "use_system": True},
        "fine_tuned": {"model": ft_model_id, "use_system": True},
    }

    all_results: dict[str, list[EvalResult]] = {c: [] for c in conditions}

    for i, note in enumerate(test_notes):
        print(f"  Evaluating note {i + 1}/{len(test_notes)}...")
        for label, cfg in conditions.items():
            try:
                output = run_model(
                    cfg["model"], note, SYSTEM_PROMPT, use_system=cfg["use_system"]
                )
                valid, count, has_keys = _parse_ner_output(output)
            except Exception as e:
                output = f"ERROR: {e}"
                valid, count, has_keys = False, 0, False

            all_results[label].append(EvalResult(
                model_label=label,
                model_id=cfg["model"],
                note=note,
                output=output,
                valid_json=valid,
                entity_count=count,
                has_all_keys=has_keys,
            ))
            time.sleep(0.3)

    # Aggregate metrics per condition
    summary = {}
    for label, results in all_results.items():
        n = len(results)
        valid_rate = sum(1 for r in results if r.valid_json) / n * 100
        all_keys_rate = sum(1 for r in results if r.has_all_keys) / n * 100
        avg_entities = sum(r.entity_count for r in results) / n
        summary[label] = {
            "n": n,
            "valid_json_pct": round(valid_rate, 1),
            "all_keys_pct": round(all_keys_rate, 1),
            "avg_entities": round(avg_entities, 2),
        }

    return summary


# ---------------------------------------------------------------------------
# Stage 4: ROI calculation
# ---------------------------------------------------------------------------

def compute_roi(
    stats: DistillationStats,
    training_cost_usd: float,
    daily_calls: int,
    avg_output_tokens: int,
    teacher_price_per_1m: float = 75.0,   # Opus-level
    student_price_per_1m: float = 1.25,   # Haiku-level
) -> dict:
    """Calculate payback period and go/no-go recommendation."""
    tokens_per_day = daily_calls * avg_output_tokens

    teacher_monthly = (tokens_per_day / 1_000_000) * teacher_price_per_1m * 30
    student_monthly = (tokens_per_day / 1_000_000) * student_price_per_1m * 30
    monthly_savings = teacher_monthly - student_monthly

    total_project_cost = training_cost_usd  # distillation API cost included

    if monthly_savings <= 0:
        payback_months = float("inf")
        recommendation = "NO-GO: student model costs more than teacher"
    else:
        payback_months = total_project_cost / monthly_savings
        if payback_months <= 3:
            recommendation = "GO: payback within 3 months"
        elif payback_months <= 6:
            recommendation = "MARGINAL: review volume assumptions"
        else:
            recommendation = "NO-GO: payback too long at current volume"

    return {
        "total_project_cost_usd": round(total_project_cost, 2),
        "teacher_monthly_cost_usd": round(teacher_monthly, 2),
        "student_monthly_cost_usd": round(student_monthly, 2),
        "monthly_savings_usd": round(monthly_savings, 2),
        "payback_months": round(payback_months, 1),
        "recommendation": recommendation,
    }


def print_go_nogo(eval_summary: dict, roi: dict) -> None:
    """Print the go/no-go decision table."""
    ft = eval_summary.get("fine_tuned", {})
    pe = eval_summary.get("prompt_eng", {})

    quality_gain = ft.get("valid_json_pct", 0) - pe.get("valid_json_pct", 0)
    payback = roi["payback_months"]

    print("\n=== Go / No-Go Decision ===")
    print(f"  Quality gain over prompt-eng: {quality_gain:+.1f}pp valid JSON")
    print(f"  Payback period:               {payback} months")
    print(f"  Monthly savings:              ${roi['monthly_savings_usd']}")
    print()

    checks = [
        ("Quality gain >= 10pp", quality_gain >= 10),
        ("Quality gain >= 5pp (minimum)", quality_gain >= 5),
        ("Payback <= 3 months (strong)", payback <= 3),
        ("Payback <= 6 months (acceptable)", payback <= 6),
    ]
    for label, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {label}")

    print(f"\n  Final recommendation: {roi['recommendation']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="End-to-end fine-tuning project with ROI calculation."
    )
    parser.add_argument(
        "--stage",
        choices=["generate", "evaluate", "roi", "all"],
        default="all",
        help="Which stage to run (default: all)",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Also submit the fine-tuning job (stage 2, costs money)",
    )
    parser.add_argument(
        "--ft-model",
        default=None,
        help="Fine-tuned model ID for evaluation (default: use haiku as stand-in)",
    )
    parser.add_argument(
        "--training-file",
        default="medical_ner_training.jsonl",
        help="Path to training JSONL file",
    )
    parser.add_argument(
        "--daily-calls",
        type=int,
        default=500,
        help="Daily call volume for ROI calculation (default: 500)",
    )
    parser.add_argument(
        "--training-cost",
        type=float,
        default=50.0,
        help="Estimated fine-tuning cost in USD (default: 50.0)",
    )
    args = parser.parse_args()

    ft_model_id = args.ft_model or "claude-3-5-haiku-20241022"
    distill_stats = DistillationStats()

    # Stage 1: Generate training data
    if args.stage in ("generate", "all"):
        print("\n=== Stage 1: Generate Distilled Training Data ===")
        distill_stats = generate_training_data(
            TRAINING_NOTES,
            output_path=args.training_file,
            quality_threshold=3.5,
        )

    # Stage 2: Submit fine-tuning job (optional, requires flag)
    if args.submit:
        print("\n=== Stage 2: Submit Fine-Tuning Job ===")
        if not os.path.exists(args.training_file):
            print(f"  Training file not found: {args.training_file}")
            print("  Run with --stage generate first.")
            return 1
        job_id = submit_finetune_job(args.training_file)
        print(f"\n  Job submitted. To poll: check Anthropic console or call poll_job('{job_id}')")
        print("  Fine-tuning typically takes 30-60 minutes.")
        print("  When complete, re-run with --ft-model <returned_model_id>")
    else:
        if args.stage in ("all",):
            print("\n=== Stage 2: Fine-Tuning Job ===")
            print("  Skipped (use --submit to run a real fine-tuning job).")
            print(f"  Using {ft_model_id} as stand-in for evaluation.")

    # Stage 3: Three-way evaluation
    eval_summary = {}
    if args.stage in ("evaluate", "all"):
        print(f"\n=== Stage 3: Three-Way Evaluation (n={len(TEST_NOTES)}) ===")
        eval_summary = evaluate_three_way(TEST_NOTES, ft_model_id)
        print("\n  Results:")
        print(f"  {'Condition':<15} {'Valid JSON %':<15} {'All Keys %':<15} {'Avg Entities'}")
        print("  " + "-" * 60)
        for label, metrics in eval_summary.items():
            print(
                f"  {label:<15} {metrics['valid_json_pct']:<15.1f} "
                f"{metrics['all_keys_pct']:<15.1f} {metrics['avg_entities']}"
            )

    # Stage 4: ROI
    if args.stage in ("roi", "all"):
        print("\n=== Stage 4: ROI Calculation ===")
        roi = compute_roi(
            stats=distill_stats,
            training_cost_usd=args.training_cost,
            daily_calls=args.daily_calls,
            avg_output_tokens=150,
        )
        for key, value in roi.items():
            print(f"  {key}: {value}")

        if eval_summary:
            print_go_nogo(eval_summary, roi)

    return 0


if __name__ == "__main__":
    sys.exit(main())
