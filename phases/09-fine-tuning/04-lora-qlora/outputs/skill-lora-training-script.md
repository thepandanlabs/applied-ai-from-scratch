---
name: skill-lora-training-script
description: Reference configuration for LoRA and QLoRA fine-tuning, covering hyperparameters by model size, target modules by architecture, adapter merging, and common failure modes.
version: "1.0"
phase: "09"
lesson: "04"
tags: [fine-tuning, lora, qlora, peft, open-weight]
---

# LoRA and QLoRA Training Reference

Use this when setting up a LoRA fine-tuning run on an open-weight model. Covers configuration decisions, architecture-specific settings, the adapter lifecycle, and failure modes.

---

## Recommended Hyperparameters by Model Size

| Model Size | Rank (r) | Alpha | Learning Rate | Eff. Batch | Epochs | GPU |
|-----------|---------|-------|--------------|------------|--------|-----|
| 7B | 16 | 32 | 2e-4 | 16 | 3 | RTX 3090 24GB |
| 13B | 16 | 32 | 2e-4 | 8 | 3 | RTX 3090 24GB |
| 34B | 8 | 16 | 1e-4 | 4 | 2 | A100 80GB |
| 70B | 4 | 8 | 1e-4 | 2 | 1 | 2x A100 80GB |

**Notes:**
- Effective batch = `per_device_train_batch_size * gradient_accumulation_steps`
- Alpha convention: `alpha = 2 * r` keeps learning rate stable when changing rank
- For very small datasets (<500 examples), reduce epochs to 1-2 and add `lora_dropout=0.1`
- Warmup ratio 0.03-0.05, cosine LR scheduler, no weight decay on adapters

---

## Target Modules by Architecture

Only attention projections are listed below (the default and recommended starting point). Add MLP layers only if you see task loss stagnate after 3 epochs with attention-only adapters.

```
ARCHITECTURE     TARGET MODULES (attention only)
---------------------------------------------------
Llama 2/3        q_proj, k_proj, v_proj, o_proj
Mistral          q_proj, k_proj, v_proj, o_proj
Mixtral (MoE)    q_proj, k_proj, v_proj, o_proj
Falcon           query_key_value, dense
Qwen 1/2         c_attn, c_proj
Phi-2/3          q_proj, k_proj, v_proj, dense
GPT-NeoX         query_key_value, dense
Gemma            q_proj, k_proj, v_proj, o_proj
```

To include MLP layers in Llama-class models, add: `gate_proj`, `up_proj`, `down_proj`

---

## Baseline LoRA Config (Llama 3.1 7B)

```python
from peft import LoraConfig, TaskType

lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    bias="none",               # do not train bias terms
    modules_to_save=None,      # set to ["embed_tokens"] only for vocab adaptation
)
```

---

## QLoRA Config (4-bit Quantization)

```python
from transformers import BitsAndBytesConfig
import torch

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",              # NormalFloat4: better distribution for LLM weights
    bnb_4bit_compute_dtype=torch.bfloat16,  # compute in bfloat16, not float32
    bnb_4bit_use_double_quant=True,         # quantize quantization constants: saves ~0.4GB
)
```

---

## SFTConfig Training Arguments

```python
from trl import SFTConfig

training_args = SFTConfig(
    output_dir="./checkpoints",
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,   # effective batch = 16
    per_device_eval_batch_size=8,
    learning_rate=2e-4,
    warmup_ratio=0.03,
    lr_scheduler_type="cosine",
    evaluation_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,     # critical: reverts to best checkpoint
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    bf16=True,
    max_seq_length=512,
    dataset_text_field="text",
    logging_steps=10,
    report_to="wandb",               # or "tensorboard"
)
```

---

## Adapter Lifecycle: Train, Save, Merge, Deploy

### Save after training (adapter only, ~30MB)

```python
trainer.model.save_pretrained("./my-adapter")
tokenizer.save_pretrained("./my-adapter")
# Saves adapter_config.json + adapter_model.safetensors
```

### Merge adapter into base model for production

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# Load base model in bfloat16 for merge (full precision, no quantization)
base_model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-3.1-8B",
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B")

# Apply adapter and merge
model = PeftModel.from_pretrained(base_model, "./my-adapter")
model = model.merge_and_unload()    # computes W + B@A in-place

# Save standalone merged model (no adapter dependency)
model.save_pretrained("./merged-model")
tokenizer.save_pretrained("./merged-model")
```

### Push to HuggingFace Hub

```python
model.push_to_hub("your-org/my-finetuned-model")
tokenizer.push_to_hub("your-org/my-finetuned-model")
```

---

## Common Failure Modes

### CUDA out of memory during training

**Cause:** Batch size or sequence length too large for available VRAM.

**Fix:** Reduce `per_device_train_batch_size` to 1, increase `gradient_accumulation_steps` to maintain effective batch size. Reduce `max_seq_length`. Enable `gradient_checkpointing=True` in training args (saves ~30% VRAM at ~20% speed cost).

### NaN loss after epoch 1

**Cause:** Learning rate too high, or input data contains sequences that overflow the attention mechanism.

**Fix:** Reduce `learning_rate` by 5-10x. Add `max_grad_norm=0.3` to training args. Check for empty examples or extremely long sequences in training data.

### Validation loss worse than baseline after training

**Cause 1:** Training data distribution mismatch. The format of your JSONL differs from how the model was pre-trained on chat data.

**Fix 1:** Ensure your training data uses the model's official chat template. For Llama 3.1, apply `tokenizer.apply_chat_template()` to your examples before training.

**Cause 2:** Overfitting on a small dataset with a high rank.

**Fix 2:** Reduce rank (try r=8 or r=4), add `lora_dropout=0.1`, reduce epochs to 1-2.

### Adapter loads but inference is wrong

**Cause:** Adapter was saved with a different base model revision than what you are loading.

**Fix:** Pin the base model revision when loading. Use the same revision for training and inference. Check `adapter_config.json` for the `base_model_name_or_path` field.

### merge_and_unload() runs out of memory

**Cause:** Merge requires loading the base model in full precision alongside the quantized version.

**Fix:** Merge on a machine with more CPU RAM (not GPU VRAM). The merge itself is a CPU operation. Offload to CPU explicitly:

```python
base_model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-3.1-8B",
    torch_dtype=torch.float16,
    device_map="cpu",           # merge on CPU
)
```

---

## Decision Checklist Before Training

- [ ] Training data never overlaps with your evaluation set
- [ ] Dataset format matches the model's chat template
- [ ] Estimated training cost calculated and approved
- [ ] Baseline metrics recorded (before training, on the same test set)
- [ ] Checkpoint directory has enough disk space (100GB+ for 7B checkpoints)
- [ ] `load_best_model_at_end=True` set to prevent deploying an overfit checkpoint
- [ ] Post-training eval plan defined (Lesson 09-05 harness ready)
