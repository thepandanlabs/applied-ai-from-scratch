"""
Lesson 09-04: LoRA and QLoRA Intuition
Demo: LoRA parameter counting and configuration reference.

Usage:
  python main.py --demo                                  # math demo, no GPU
  python main.py --model meta-llama/Llama-3.1-8B --rank 16

Dependencies (for real model path):
  pip install peft transformers bitsandbytes torch

The demo path requires no external libraries.
"""

from __future__ import annotations
import argparse
import sys
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Core LoRA math - no ML dependencies required
# ---------------------------------------------------------------------------

@dataclass
class LayerShape:
    """Dimensions of a single weight matrix."""
    name: str
    d_in: int
    d_out: int


# Typical weight matrices in a 7B Llama-class model
LLAMA_7B_LAYERS = [
    LayerShape("q_proj",   4096,  4096),
    LayerShape("k_proj",   4096,  4096),
    LayerShape("v_proj",   4096,  4096),
    LayerShape("o_proj",   4096,  4096),
    LayerShape("gate_proj", 4096, 11008),
    LayerShape("up_proj",  4096, 11008),
    LayerShape("down_proj", 11008, 4096),
]

# Target modules by architecture (for reference)
TARGET_MODULES_BY_ARCH = {
    "llama":   ["q_proj", "k_proj", "v_proj", "o_proj"],
    "mistral": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "falcon":  ["query_key_value", "dense"],
    "qwen":    ["c_attn", "c_proj"],
    "phi":     ["q_proj", "k_proj", "v_proj", "dense"],
}

NUM_LAYERS = 32  # Llama 3.1 7B has 32 transformer layers
MODEL_TOTAL_PARAMS = 7_000_000_000


def count_lora_params(layers: list[LayerShape], rank: int, num_layers: int,
                      target_names: list[str] | None = None) -> dict:
    """
    Calculate trainable vs total parameters for a given LoRA rank.

    Args:
        layers: Weight matrix shapes for one transformer layer
        rank: LoRA rank r
        num_layers: Number of transformer layers in the model
        target_names: Which layer names to apply LoRA to (default: attention only)

    Returns:
        Dict with lora_trainable, pct_trainable, memory_savings_factor
    """
    if target_names is None:
        target_names = ["q_proj", "k_proj", "v_proj", "o_proj"]

    total_lora = 0
    for layer in layers:
        if layer.name in target_names:
            lora_params = rank * (layer.d_in + layer.d_out)
            total_lora += lora_params * num_layers

    return {
        "rank": rank,
        "lora_trainable": total_lora,
        "full_params": MODEL_TOTAL_PARAMS,
        "pct_trainable": total_lora / MODEL_TOTAL_PARAMS * 100,
        "memory_savings_factor": MODEL_TOTAL_PARAMS / total_lora if total_lora > 0 else float("inf"),
    }


# ---------------------------------------------------------------------------
# Display functions
# ---------------------------------------------------------------------------

def show_rank_comparison() -> None:
    """Print a comparison table of parameter counts across ranks."""
    print("\n" + "=" * 68)
    print("LoRA Parameter Savings - Llama 3.1 7B (attention layers: q/k/v/o)")
    print("=" * 68)
    print(f"  {'Rank':>6} | {'Trainable Params':>18} | {'% of Model':>12} | {'Savings Factor':>15}")
    print("  " + "-" * 62)

    for r in [4, 8, 16, 32, 64]:
        stats = count_lora_params(LLAMA_7B_LAYERS, r, NUM_LAYERS)
        print(
            f"  r={r:<4} | "
            f"{stats['lora_trainable']:>18,} | "
            f"{stats['pct_trainable']:>11.3f}% | "
            f"     {stats['memory_savings_factor']:>7.0f}x"
        )

    print("  " + "-" * 62)
    print(f"  {'Full FT':>6} | {MODEL_TOTAL_PARAMS:>18,} | {'100.000%':>12} | {'1x':>15}")
    print()


def show_qlora_memory_breakdown() -> None:
    """Show memory requirements for different model sizes with and without QLoRA."""
    print("\n" + "=" * 62)
    print("QLoRA Memory Requirements by Model Size")
    print("=" * 62)
    print(f"  {'Model':>8} | {'Full FT (GB)':>12} | {'QLoRA (GB)':>12} | {'24GB GPU?':>10}")
    print("  " + "-" * 52)

    configs = [
        ("7B",   28,  11),
        ("13B",  52,  18),
        ("34B", 136,  42),
        ("70B", 280,  80),
    ]

    for model, full_gb, qlora_gb in configs:
        fits = "Yes" if qlora_gb <= 24 else ("A100 80GB" if qlora_gb <= 80 else "Multi-GPU")
        print(f"  {model:>8} | {full_gb:>12} | {qlora_gb:>12} | {fits:>10}")

    print("  " + "-" * 52)
    print("  Full FT  = bfloat16 weights + gradients + optimizer states")
    print("  QLoRA    = 4-bit frozen weights + bfloat16 adapters + gradients")
    print()


def show_lora_config_reference() -> None:
    """Print reference LoRA configs with explanations."""
    print("\n" + "=" * 62)
    print("Reference LoRA Configuration (Llama 3.1 7B)")
    print("=" * 62)
    print("""
from peft import LoraConfig, TaskType

lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,

    # Rank: the bottleneck of the adapter matrices.
    # r=16 is the recommended starting point.
    r=16,

    # Alpha: scaling factor applied to adapter output.
    # Convention: alpha = 2 * r keeps effective LR stable
    # as you change r.
    lora_alpha=32,

    # Dropout: regularization on adapter activations.
    # 0.05 prevents overfitting on small datasets.
    lora_dropout=0.05,

    # target_modules: which weight matrices get adapters.
    # Attention projections (q/k/v/o) give the best
    # quality-to-parameter ratio for most tasks.
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
)
""")

    print("Target modules by model architecture:")
    for arch, modules in TARGET_MODULES_BY_ARCH.items():
        print(f"  {arch:<10} {modules}")
    print()


def show_hyperparameter_guide() -> None:
    """Print recommended hyperparameters for different model sizes."""
    print("\n" + "=" * 70)
    print("Recommended Hyperparameters by Model Size")
    print("=" * 70)
    print(f"  {'Model':>6} | {'Rank':>6} | {'Alpha':>6} | {'LR':>8} | {'Batch':>6} | {'Epochs':>6}")
    print("  " + "-" * 58)

    configs = [
        ("7B",  16, 32, "2e-4", 16, 3),
        ("13B", 16, 32, "2e-4",  8, 3),
        ("34B",  8, 16, "1e-4",  4, 2),
        ("70B",  4,  8, "1e-4",  2, 1),
    ]

    for model, r, alpha, lr, batch, epochs in configs:
        print(f"  {model:>6} | {r:>6} | {alpha:>6} | {lr:>8} | {batch:>6} | {epochs:>6}")

    print("  " + "-" * 58)
    print("  Batch = effective batch size (per_device * gradient_accumulation_steps)")
    print()


def demo_mode() -> None:
    """Run the full demo without loading any models."""
    print()
    print("=" * 68)
    print("Lesson 09-04: LoRA and QLoRA Intuition - Demo Mode")
    print("No GPU or model download required.")
    print("=" * 68)

    show_rank_comparison()
    show_qlora_memory_breakdown()
    show_lora_config_reference()
    show_hyperparameter_guide()

    print("=" * 68)
    print("To run with a real model (requires GPU and ~14GB download):")
    print("  pip install peft transformers bitsandbytes torch")
    print("  python main.py --model meta-llama/Llama-3.1-8B --rank 16")
    print("=" * 68)


def run_with_model(model_name: str, rank: int) -> None:
    """Load a real model with QLoRA and wrap with LoRA adapters."""
    try:
        import torch
        from transformers import AutoModelForCausalLM, BitsAndBytesConfig
        from peft import LoraConfig, TaskType, get_peft_model
    except ImportError as e:
        print(f"\nERROR: Missing dependency: {e}")
        print("Install: pip install peft transformers bitsandbytes torch")
        sys.exit(1)

    print(f"\nModel:       {model_name}")
    print(f"LoRA rank:   {rank}")
    print(f"LoRA alpha:  {rank * 2}")
    print("Loading in 4-bit (QLoRA). This will download if not cached...")

    # 4-bit quantization config
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
    )
    print("Base model loaded.")

    # Apply LoRA
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=rank,
        lora_alpha=rank * 2,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    model = get_peft_model(model, lora_config)

    # Count and display parameters
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    print("\n" + "=" * 52)
    print("Parameter Count After LoRA Wrapping")
    print("=" * 52)
    print(f"  Total parameters:      {total_params:>15,}")
    print(f"  Trainable parameters:  {trainable_params:>15,}")
    print(f"  Frozen parameters:     {total_params - trainable_params:>15,}")
    print(f"  Trainable percentage:  {trainable_params / total_params * 100:>14.4f}%")
    print("=" * 52)
    print()
    model.print_trainable_parameters()

    print("\nNext steps:")
    print("  1. Prepare your training data as JSONL (see Lesson 09-02)")
    print("  2. Use SFTTrainer from the trl library to run training")
    print("  3. After training, merge the adapter with merge_and_unload()")
    print("  4. Evaluate with the harness from Lesson 09-05")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="LoRA and QLoRA parameter analysis for fine-tuning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --demo
  python main.py --model meta-llama/Llama-3.1-8B --rank 16
  python main.py --model meta-llama/Llama-3.1-8B --rank 32
        """,
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run math demo without loading any model (no GPU required)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="HuggingFace model ID to load with QLoRA",
    )
    parser.add_argument(
        "--rank",
        type=int,
        default=16,
        help="LoRA rank r (default: 16)",
    )
    args = parser.parse_args()

    if args.demo or args.model is None:
        demo_mode()
    else:
        run_with_model(args.model, args.rank)


if __name__ == "__main__":
    main()
