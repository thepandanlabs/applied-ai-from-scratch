---
name: skill-vllm-deployment-config
description: Reference configuration for deploying a vLLM server with Docker, GPU requirements, and client integration
version: "1.0"
phase: "09"
lesson: "08"
tags: [vllm, serving, open-weight, deployment, gpu]
---

# Skill: vLLM Deployment Configuration

Reference for deploying an open-weight or fine-tuned model with vLLM in production, covering Docker setup, GPU sizing, client integration, and health checks.

---

## Docker Compose Configuration

```yaml
version: "3.8"
services:
  vllm:
    image: vllm/vllm-openai:latest
    runtime: nvidia
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HF_TOKEN}
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface
    ports:
      - "8000:8000"
    ipc: host
    command: >
      --model ${MODEL_PATH}
      --quantization ${QUANTIZATION:-none}
      --tensor-parallel-size ${TENSOR_PARALLEL_SIZE:-1}
      --max-model-len ${MAX_MODEL_LEN:-4096}
      --max-num-seqs ${MAX_NUM_SEQS:-256}
      --host 0.0.0.0
      --port 8000
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: ${GPU_COUNT:-1}
              capabilities: [gpu]
```

---

## Environment Variables

| Variable | Purpose | Default | Notes |
|---|---|---|---|
| `MODEL_PATH` | HuggingFace model ID or local path | required | e.g. `Qwen/Qwen2.5-7B-Instruct` |
| `QUANTIZATION` | Quantization method | `none` | Options: `awq`, `gptq`, `fp8` |
| `TENSOR_PARALLEL_SIZE` | Number of GPUs for tensor parallelism | `1` | Must equal GPU count |
| `MAX_MODEL_LEN` | Maximum context window in tokens | `4096` | Reduce to fit smaller VRAM |
| `MAX_NUM_SEQS` | Maximum concurrent sequences | `256` | Reduce if OOM errors occur |
| `GPU_COUNT` | Number of GPUs to allocate | `1` | Must match `TENSOR_PARALLEL_SIZE` |
| `HF_TOKEN` | HuggingFace access token | optional | Required for gated models |

---

## GPU Memory Requirements by Model Size

These are approximate minimum VRAM requirements at FP16 precision (full precision, no quantization). Add 20-30% overhead for KV cache and activation memory.

```
Model size    FP16 VRAM    AWQ/GPTQ VRAM    Recommended GPU
----------    ----------   ---------------   ---------------
1-3B params   3-6 GB       2-4 GB            RTX 3090 (24GB)
7B params     14 GB        6-8 GB            A10G (24GB) or RTX 4090
13B params    26 GB        12-14 GB          A100 (40GB) or 2x A10G
34B params    68 GB        32-36 GB          A100 80GB or 2x A100 40GB
70B params    140 GB       70-80 GB          4x A100 40GB or 2x A100 80GB
```

Quantization trade-off: AWQ and GPTQ reduce memory by roughly 50% with typical quality loss of 1-3 percentage points on standard benchmarks. FP8 (supported on H100) reduces memory by 50% with minimal quality impact.

---

## OpenAI-Compatible API Endpoint Pattern

vLLM exposes an OpenAI-compatible REST API. This means any code using the `openai` Python SDK works with vLLM by changing only the `base_url`.

Base URL: `http://<host>:8000/v1`

Supported endpoints:
- `POST /v1/chat/completions` - chat completions (primary)
- `POST /v1/completions` - raw completions
- `GET /v1/models` - list available models
- `GET /health` - health check

The model name in requests must match the model ID passed to vLLM at startup. For fine-tuned adapter models, this is the adapter directory name or the merged model path.

---

## Client Integration

Minimal client that works with both vLLM and OpenAI (change `base_url` only):

```python
import os
from openai import OpenAI

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen2.5-7B-Instruct")

client = OpenAI(
    base_url=VLLM_BASE_URL,
    api_key="dummy",  # vLLM does not require a real key locally
)

def complete(prompt: str, system: str = "", max_tokens: int = 512) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return response.choices[0].message.content
```

To swap back to the OpenAI managed API: set `VLLM_BASE_URL=https://api.openai.com/v1` and provide a real `api_key`. No code changes required.

---

## Serving a Fine-Tuned Adapter

For LoRA fine-tuned models, two options:

**Option 1: Merge adapter weights before serving (recommended for production)**
```bash
python -c "
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
base = AutoModelForCausalLM.from_pretrained('base-model-id')
model = PeftModel.from_pretrained(base, 'lora-adapter-path')
merged = model.merge_and_unload()
merged.save_pretrained('merged-model-path')
AutoTokenizer.from_pretrained('base-model-id').save_pretrained('merged-model-path')
"
# Then serve the merged model:
# MODEL_PATH=merged-model-path docker compose up
```

**Option 2: vLLM native LoRA serving (experimental)**
```bash
--enable-lora --lora-modules adapter_name=./lora-adapter-path
```

Native LoRA serving avoids the merge step but adds complexity. Use merged weights for stable production deployments.

---

## Health Check Pattern

Poll the `/health` endpoint before routing traffic to a new vLLM instance:

```python
import time
import requests

def wait_for_vllm(base_url: str, timeout: int = 120) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url.rstrip('/v1')}/health", timeout=3)
            if r.status_code == 200:
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(3)
    return False

if not wait_for_vllm("http://localhost:8000/v1"):
    raise RuntimeError("vLLM server did not become healthy within timeout")
```

vLLM startup time ranges from 30 seconds (small model, cached weights) to several minutes (large model, first download). Always health-check before sending production traffic.

---

## Autoscaling Considerations

vLLM does not auto-scale natively. Scaling strategies:

**Horizontal scaling:** Run multiple vLLM instances behind a load balancer. Use round-robin routing for stateless requests. Each instance must have its own GPU allocation.

**Vertical scaling:** Increase `MAX_NUM_SEQS` to allow more concurrent sequences. Monitor GPU memory. If OOM errors appear, reduce `MAX_NUM_SEQS` or switch to a quantized model.

**Trigger signals for scaling:**
- P99 latency exceeds 2x your SLA target
- GPU utilization is consistently above 90% (capacity bound, not efficiency)
- Queue depth (requests waiting for a sequence slot) is non-zero for extended periods

For Kubernetes: use the `nvidia/k8s-device-plugin` for GPU scheduling, and a custom metrics adapter to expose vLLM's `/metrics` (Prometheus format) for horizontal pod autoscaling.

---

## Common Failure Modes

| Symptom | Most likely cause | Fix |
|---|---|---|
| Empty or truncated outputs | Context window overflow | Reduce `MAX_MODEL_LEN` or shorten prompts |
| OOM crash on startup | Model too large for VRAM | Add quantization or reduce `MAX_MODEL_LEN` |
| Slow first request, fast after | Weights not cached | Pre-pull model weights on instance startup |
| Garbled or incoherent outputs | Wrong chat template applied | Verify model has a chat template; check tokenizer config |
| High latency under load | Insufficient `MAX_NUM_SEQS` | Increase `MAX_NUM_SEQS` if VRAM allows |
