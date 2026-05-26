# Capstone: Fine-Tune for a Domain Task, Prove ROI with Evals

> A fine-tune is not complete until the math says it was worth doing.

**Type:** Build
**Languages:** Python
**Prerequisites:** All P09 lessons (01 through 08)
**Time:** ~90 min
**Learning Objectives:**
- Assemble the full P09 pipeline: dataset prep, training job, evaluation, ROI calculation
- Apply the distillation pipeline from L07 to generate training data for a domain task
- Submit and monitor a managed fine-tuning job using the Anthropic API
- Compare fine-tuned model quality against prompt-only baseline using the eval framework from L05
- Calculate payback period and go/no-go criteria for fine-tune deployment

---

## The Problem

Each lesson in this phase taught one part of the fine-tuning loop. Now you need to close the loop.

A fine-tuned model that performs better in isolation is not enough. You need to answer three questions before deploying it to production:

1. Is it actually better? Compared to what baseline? By how much?
2. Is the improvement worth the cost? How long until the fine-tune pays for itself?
3. Will it stay good? What signals will tell you it is degrading?

A team that skips these questions ships a model they cannot justify to stakeholders, cannot monitor in production, and cannot defend when something goes wrong. This capstone walks the complete loop: dataset, train, eval, ROI, deployment criteria, and drift monitoring.

The domain task is medical named entity recognition: extract drug names, dosages, and conditions from clinical notes. It is a narrow, well-defined, high-volume task - the ideal fine-tuning candidate.

---

## The Concept

### The Fine-Tuning Project Lifecycle

```mermaid
flowchart TD
    A[Define domain task\n+ success metric] --> B[Dataset preparation\nDistillation pipeline from L07]
    B --> C[Quality filter\nLLM judge, keep score 3.5+]
    C --> D[Managed fine-tuning job\nAnthropic API from L03]
    D --> E[Evaluation: 3-way comparison\nBaseline vs Prompt-eng vs Fine-tuned]
    E --> F{Go / No-go\ndecision}
    F -- no-go --> G[Diagnose: data quality,\ntraining epochs, eval design]
    F -- go --> H[Deploy + monitor\nfor model drift]
    G --> B
    H --> I[Weekly drift check\nre-train on failure]
```

### The ROI Framework

```
FINE-TUNE ROI CALCULATION
-----------------------------------------

Cost inputs:
  Teacher generation cost   = N_examples * avg_tokens * teacher_price
  Fine-tune training cost   = (total_training_tokens / 1M) * ft_price
  Evaluation cost           = eval_calls * avg_tokens * judge_price

Cost savings (monthly):
  baseline_cost_monthly     = daily_calls * avg_tokens * baseline_price * 30
  finetuned_cost_monthly    = daily_calls * avg_tokens * finetuned_price * 30
  monthly_savings           = baseline_cost_monthly - finetuned_cost_monthly

Payback period:
  total_project_cost        = teacher_cost + training_cost + eval_cost
  payback_months            = total_project_cost / monthly_savings

GO if:
  - Quality improvement >= 10 percentage points over prompt baseline
  - Payback period <= 3 months
  - No regression on safety/guardrail tests

NO-GO if:
  - Quality improvement < 5 percentage points (prompt engineering is cheaper)
  - Payback period > 6 months (volume too low to justify)
  - Any regression on safety tests
```

### Go / No-Go Criteria

```
DIMENSION         GO                    NO-GO               ACTION
----------------  --------------------  ------------------  --------------------
Task accuracy     >= 90%, +10pp gain    < 85% or < 5pp gain More data / epochs
Latency           Within 20% of base    > 2x baseline       Check model size
Safety            No new violations     Any new violation   Review training data
Cost payback      <= 3 months           > 6 months          Reduce scope
Drift signal      < 2% weekly drop      > 5% drop in week   Re-distill
```

---

## Build It

Assemble the complete fine-tuning project as a single runnable pipeline. The code integrates the distillation pipeline from L07 and the managed fine-tuning API from L03.

```python
import anthropic
import json
import time
from dataclasses import dataclass, field
from typing import Optional

client = anthropic.Anthropic()

# --- Task definition ---
DOMAIN_TASK = "medical_ner"
TASK_DESCRIPTION = """Extract medical named entities from clinical notes.
Return a JSON object with keys: drugs (list), dosages (list), conditions (list).
Be precise - only extract entities explicitly mentioned."""

SYSTEM_PROMPT = """You are a clinical NLP specialist. Extract drug names,
dosages, and medical conditions from clinical notes. Respond only with
valid JSON in the format: {"drugs": [], "dosages": [], "conditions": []}"""

# --- Sample clinical notes for distillation ---
SAMPLE_NOTES = [
    "Patient prescribed metformin 500mg twice daily for type 2 diabetes. Monitoring HbA1c.",
    "Started lisinopril 10mg QD for hypertension. Patient reports mild dry cough.",
    "Atorvastatin 20mg nightly for hyperlipidemia. LFTs ordered at 3 months.",
    "Amoxicillin 875mg BID x10 days for streptococcal pharyngitis.",
    "Sertraline 50mg daily initiated for major depressive disorder. Follow up in 4 weeks.",
    "Metoprolol 25mg BID for atrial fibrillation rate control. HR target 60-80.",
    "Prednisone 40mg daily tapering course for acute exacerbation of COPD.",
    "Levothyroxine 88mcg daily for hypothyroidism. TSH target 0.5-2.5.",
]
```

Stage 1 - generate distilled training data:

```python
@dataclass
class DistillationStats:
    generated: int = 0
    kept: int = 0
    discarded: int = 0
    teacher_cost_usd: float = 0.0

def generate_training_data(notes: list[str],
                            output_path: str = "medical_ner_training.jsonl",
                            quality_threshold: float = 3.5) -> DistillationStats:
    stats = DistillationStats()
    examples = []

    for note in notes:
        prompt = f"Extract medical named entities from this clinical note:\n\n{note}"

        # Teacher generation
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        completion = response.content[0].text
        stats.generated += 1

        # Quality judge
        judge_prompt = f"""Rate this medical NER extraction 1-5.

Note: {note}
Extraction: {completion}

5=Perfect JSON, all entities extracted
4=Good, minor omissions
3=Acceptable but incomplete
2=Wrong format or missed entities
1=Incorrect or malformed

Respond with ONLY a number."""

        judge_response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=5,
            messages=[{"role": "user", "content": judge_prompt}]
        )
        try:
            score = float(judge_response.content[0].text.strip())
        except ValueError:
            score = 1.0

        if score >= quality_threshold:
            stats.kept += 1
            examples.append({
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": completion}
                ]
            })
        else:
            stats.discarded += 1

        time.sleep(0.3)

    with open(output_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    return stats
```

Stage 2 - submit fine-tuning job:

```python
def submit_finetune_job(training_file: str,
                        model: str = "claude-haiku-20250307") -> str:
    """Upload training data and submit a managed fine-tuning job."""
    import os

    # Upload the training file
    with open(training_file, "rb") as f:
        file_response = client.beta.files.upload(
            file=(os.path.basename(training_file), f, "application/jsonl"),
        )
    file_id = file_response.id
    print(f"Training file uploaded: {file_id}")

    # Create the fine-tuning job
    job_response = client.beta.fine_tuning.jobs.create(
        model=model,
        training_file=file_id,
        hyperparameters={
            "n_epochs": 3,
        }
    )
    job_id = job_response.id
    print(f"Fine-tuning job created: {job_id}")
    return job_id

def poll_job(job_id: str, poll_interval: int = 60) -> dict:
    """Poll until the fine-tuning job completes."""
    while True:
        job = client.beta.fine_tuning.jobs.retrieve(job_id)
        status = job.status
        print(f"  Job {job_id}: {status}")
        if status in ("succeeded", "failed", "cancelled"):
            return {"job_id": job_id, "status": status,
                    "fine_tuned_model": getattr(job, "fine_tuned_model", None)}
        time.sleep(poll_interval)
```

> **Real-world check:** Your fine-tuning job completes and you get a model ID back. You run one test prompt and it responds perfectly. Your manager asks if you are ready to deploy. What do you say?
>
> Not yet. One prompt is anecdote, not evidence. You need to run the full eval suite comparing baseline, prompt-engineered baseline, and fine-tuned model across at least 100 diverse examples before you can make a deployment decision. "Looks good on one test" is how untested models reach production.

Stage 3 - three-way evaluation:

```python
def evaluate_three_way(test_notes: list[str],
                       ft_model_id: str) -> dict:
    """Compare baseline, prompt-engineered, and fine-tuned on the same test set."""
    results = {"baseline": [], "prompt_eng": [], "fine_tuned": []}

    for note in test_notes:
        prompt = f"Extract medical named entities from this clinical note:\n\n{note}"

        # Baseline: no system prompt, direct question
        baseline_resp = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )

        # Prompt-engineered: with system prompt and few-shot
        pe_resp = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

        # Fine-tuned model
        ft_resp = client.messages.create(
            model=ft_model_id,
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}]
        )

        for key, resp in [("baseline", baseline_resp),
                          ("prompt_eng", pe_resp),
                          ("fine_tuned", ft_resp)]:
            text = resp.content[0].text
            try:
                parsed = json.loads(text)
                valid_json = True
                entity_count = (len(parsed.get("drugs", [])) +
                                len(parsed.get("dosages", [])) +
                                len(parsed.get("conditions", [])))
            except json.JSONDecodeError:
                valid_json = False
                entity_count = 0
            results[key].append({"valid_json": valid_json,
                                  "entity_count": entity_count})

    # Compute summary metrics
    summary = {}
    for condition, data in results.items():
        valid_rate = sum(1 for d in data if d["valid_json"]) / len(data) * 100
        avg_entities = sum(d["entity_count"] for d in data) / len(data)
        summary[condition] = {
            "valid_json_rate": round(valid_rate, 1),
            "avg_entities_extracted": round(avg_entities, 2)
        }
    return summary
```

Stage 4 - ROI calculation and go/no-go:

```python
def compute_roi(stats: DistillationStats,
                training_cost_usd: float,
                daily_calls: int,
                avg_output_tokens: int) -> dict:
    """Calculate payback period and go/no-go recommendation."""
    # Approximate token costs (illustrative, check current pricing)
    HAIKU_PRICE_PER_1M_OUTPUT = 1.25
    OPUS_PRICE_PER_1M_OUTPUT = 75.00

    total_project_cost = (
        stats.teacher_cost_usd +
        training_cost_usd
    )

    baseline_monthly = (daily_calls * avg_output_tokens / 1_000_000) * OPUS_PRICE_PER_1M_OUTPUT * 30
    finetuned_monthly = (daily_calls * avg_output_tokens / 1_000_000) * HAIKU_PRICE_PER_1M_OUTPUT * 30
    monthly_savings = baseline_monthly - finetuned_monthly

    if monthly_savings <= 0:
        payback_months = float("inf")
    else:
        payback_months = total_project_cost / monthly_savings

    return {
        "total_project_cost_usd": round(total_project_cost, 2),
        "baseline_monthly_cost_usd": round(baseline_monthly, 2),
        "finetuned_monthly_cost_usd": round(finetuned_monthly, 2),
        "monthly_savings_usd": round(monthly_savings, 2),
        "payback_months": round(payback_months, 1),
        "recommendation": "GO" if payback_months <= 3 else "NO-GO",
    }
```

---

## Use It

Run the complete pipeline end-to-end:

```python
if __name__ == "__main__":
    print("=== Stage 1: Generate distilled training data ===")
    stats = generate_training_data(
        SAMPLE_NOTES,
        output_path="medical_ner_training.jsonl"
    )
    print(f"Generated: {stats.generated}, Kept: {stats.kept}, "
          f"Discarded: {stats.discarded}")

    print("\n=== Stage 2: Submit fine-tuning job ===")
    # Uncomment to run a real job (costs money and time):
    # job_id = submit_finetune_job("medical_ner_training.jsonl")
    # job_result = poll_job(job_id)
    # ft_model_id = job_result["fine_tuned_model"]
    # print(f"Fine-tuned model: {ft_model_id}")

    # For demonstration, use the base Haiku model as a stand-in
    ft_model_id = "claude-3-5-haiku-20241022"

    print("\n=== Stage 3: Three-way evaluation ===")
    # Use held-out notes not in the training set
    test_notes = [
        "Warfarin 5mg daily for DVT prophylaxis post-surgery. INR goal 2-3.",
        "Albuterol inhaler PRN for asthma. Prescribed ICS for daily control.",
        "Furosemide 40mg QD for congestive heart failure with peripheral edema.",
    ]
    eval_results = evaluate_three_way(test_notes, ft_model_id)
    for model_name, metrics in eval_results.items():
        print(f"  {model_name:15s}: valid JSON {metrics['valid_json_rate']}%, "
              f"avg entities {metrics['avg_entities_extracted']}")

    print("\n=== Stage 4: ROI calculation ===")
    roi = compute_roi(
        stats=stats,
        training_cost_usd=25.0,  # estimate; actual from Anthropic invoice
        daily_calls=500,
        avg_output_tokens=150,
    )
    for key, value in roi.items():
        print(f"  {key}: {value}")
```

> **Perspective shift:** This pipeline took two days to build and a few dollars to run. The ROI calculation at the end is not busywork - it is the artifact that lets you present this work to a product manager or engineering lead and say "this pays for itself in N months." Without that number, you have a technical result. With it, you have a business case.

---

## Ship It

The artifact for this lesson is `outputs/runbook-finetune-project.md`, a complete runbook for executing a fine-tuning project: dataset prep, training, evaluation, go/no-go decision, deployment, and drift monitoring.

---

## Evaluate It

The capstone is complete when all five checks pass:

**1. Dataset quality check.** Keep rate is above 60%. The training JSONL has valid messages format (user/assistant pairs). All assistant completions are valid JSON matching the target schema.

**2. Eval baseline established.** You have numeric scores for all three conditions (baseline, prompt-engineered, fine-tuned) on at least 50 held-out examples. The fine-tuned model beats prompt-engineering by at least 5 percentage points on your primary metric.

**3. ROI is positive.** Payback period is under 6 months. If it is not, document why (volume too low, cost difference too small) and note what would need to change to make it positive.

**4. Go/no-go decision is explicit.** Not "looks good" - a written decision with numeric criteria. Reference the go/no-go table from The Concept section.

**5. Drift monitoring plan exists.** You have a weekly eval job (even if just a cron script) that runs 20 test prompts against the fine-tuned model and alerts if valid JSON rate drops below your threshold. Fine-tuned models do not degrade on their own, but input distributions shift. Monitor or be surprised.
