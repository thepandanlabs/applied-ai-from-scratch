"""
Lesson 10-03: Image Generation in Products
DALL-E 3 image generation with content policy handling, retry logic,
and async service pattern demonstration.

Usage:
    python main.py                      # demo mode (no API calls)
    python main.py "a product photo"    # generate with DALL-E 3
    python main.py --demo               # force demo mode

Requirements:
    pip install openai
    Optional: pip install replicate
"""

import json
import os
import sys
import time
import threading
import urllib.request
import uuid
from pathlib import Path
from typing import Optional


# --------------------------------------------------------------------------- #
# Content policy prompt sanitizer                                              #
# --------------------------------------------------------------------------- #

SENSITIVE_KEYWORDS = [
    "violent", "nude", "explicit", "blood", "weapon",
    "realistic person", "real person", "celebrity",
]


def sanitize_prompt(prompt: str) -> str:
    """Remove known sensitive keywords and add a safety suffix."""
    cleaned = prompt
    for kw in SENSITIVE_KEYWORDS:
        cleaned = cleaned.replace(kw, "").replace(kw.title(), "")
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    return cleaned.strip() + ", professional context, brand-safe"


# --------------------------------------------------------------------------- #
# DALL-E 3 generation                                                          #
# --------------------------------------------------------------------------- #

def generate_dalle3(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
    output_path: Optional[Path] = None,
    demo_mode: bool = False,
) -> dict:
    """Generate an image with DALL-E 3."""
    if demo_mode:
        return {
            "status": "success",
            "image_url": "https://example.com/placeholder.png",
            "revised_prompt": f"[DEMO] {prompt}",
            "cost_estimate": 0.040,
            "latency_seconds": 0.0,
            "provider": "dalle3-demo",
        }

    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("Install openai: pip install openai")

    client = OpenAI()
    start = time.time()

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
        )
        latency = time.time() - start
        image_url = response.data[0].url
        revised_prompt = getattr(response.data[0], "revised_prompt", prompt)

        cost_map = {"1024x1024": 0.040, "1792x1024": 0.080, "1024x1792": 0.080}
        cost = cost_map.get(size, 0.040) * (2 if quality == "hd" else 1)

        if output_path:
            urllib.request.urlretrieve(image_url, output_path)
            print(f"  Saved to: {output_path}")

        return {
            "status": "success",
            "image_url": image_url,
            "revised_prompt": revised_prompt,
            "cost_estimate": cost,
            "latency_seconds": round(latency, 2),
            "provider": "dalle3",
        }

    except Exception as e:
        err = str(e)
        if "content_policy_violation" in err or "safety system" in err.lower():
            return {
                "status": "content_policy_violation",
                "error": err,
                "original_prompt": prompt,
            }
        raise


def generate_with_retry(
    prompt: str,
    output_path: Optional[Path] = None,
    demo_mode: bool = False,
) -> dict:
    """
    Generate with automatic sanitized-prompt retry on content policy violations.
    Two attempts maximum: original prompt, then sanitized prompt.
    """
    result = generate_dalle3(prompt, output_path=output_path, demo_mode=demo_mode)

    if result["status"] == "content_policy_violation":
        print("  Content policy violation on original prompt.")
        sanitized = sanitize_prompt(prompt)
        print(f"  Retrying with sanitized prompt: {sanitized[:80]}...")
        result = generate_dalle3(sanitized, output_path=output_path, demo_mode=demo_mode)
        result["was_sanitized"] = True
        result["original_prompt"] = prompt
        result["sanitized_prompt"] = sanitized

        if result["status"] == "content_policy_violation":
            print("  Second violation. Generation failed.")
            return {
                "status": "failed_content_policy",
                "error": "Could not generate safe image after sanitization",
                "original_prompt": prompt,
                "image_url": None,
            }

    return result


# --------------------------------------------------------------------------- #
# Replicate (Stable Diffusion) pattern                                         #
# --------------------------------------------------------------------------- #

def generate_replicate_sd(
    prompt: str,
    negative_prompt: str = "blurry, low quality, distorted, watermark",
    demo_mode: bool = False,
) -> dict:
    """
    Generate via Replicate SDXL. Shows open-weight alternative pattern.
    Much cheaper than DALL-E 3 (~$0.0023/image) but requires Replicate account.
    """
    if demo_mode:
        return {
            "status": "success",
            "image_url": "https://example.com/sd-placeholder.png",
            "cost_estimate": 0.0023,
            "provider": "replicate-sdxl-demo",
            "negative_prompt": negative_prompt,
        }

    try:
        import replicate
    except ImportError:
        raise SystemExit("Install replicate: pip install replicate")

    output = replicate.run(
        "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
        input={
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "num_outputs": 1,
            "width": 1024,
            "height": 1024,
        },
    )
    return {
        "status": "success",
        "image_url": output[0],
        "cost_estimate": 0.0023,
        "provider": "replicate-sdxl",
    }


# --------------------------------------------------------------------------- #
# Async service simulation                                                     #
# --------------------------------------------------------------------------- #

_store: dict[str, dict] = {}


def submit_generation_async(prompt: str, demo_mode: bool = False) -> str:
    """
    Async pattern: accept prompt, return generation_id immediately.
    Background thread runs generation (use Celery/ARQ in production).
    """
    gen_id = str(uuid.uuid4())[:8]
    _store[gen_id] = {"status": "pending", "prompt": prompt}

    def _worker():
        _store[gen_id]["status"] = "generating"
        result = generate_with_retry(prompt, demo_mode=demo_mode)
        _store[gen_id].update(result)
        # In production: upload image to S3, store permanent URL, send webhook

    threading.Thread(target=_worker, daemon=True).start()
    return gen_id


def get_generation_status(gen_id: str) -> dict:
    """Poll status. In production: GET /generations/{id}"""
    return _store.get(gen_id, {"status": "not_found"})


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def main():
    print("=== Lesson 10-03: Image Generation in Products ===\n")

    demo_mode = "--demo" in sys.argv or "OPENAI_API_KEY" not in os.environ
    if demo_mode:
        print("Demo mode active (set OPENAI_API_KEY to use real API)\n")

    prompt_parts = [a for a in sys.argv[1:] if not a.startswith("--")]
    prompt = " ".join(prompt_parts) or (
        "A confident product manager presenting quarterly results at a whiteboard, "
        "modern open office, soft natural lighting, professional photography style, "
        "sharp focus, high quality"
    )

    print(f"Prompt: {prompt}\n")

    # --- Direct generation ---
    print("=== 1. Direct generation with content policy retry ===")
    output_file = Path("generated_image.png")
    result = generate_with_retry(
        prompt,
        output_path=output_file if not demo_mode else None,
        demo_mode=demo_mode,
    )
    print(json.dumps(result, indent=2))

    # --- Async service pattern ---
    print("\n=== 2. Async generation service pattern ===")
    gen_id = submit_generation_async(prompt, demo_mode=demo_mode)
    print(f"Submitted. generation_id: {gen_id}")
    print("Client receives 202 Accepted; polls for status:")

    for attempt in range(8):
        status = get_generation_status(gen_id)
        current_status = status.get("status", "unknown")
        print(f"  Poll {attempt + 1}: {current_status}")
        if current_status not in ("pending", "generating"):
            break
        time.sleep(0.2 if demo_mode else 2.0)

    final = get_generation_status(gen_id)
    print(f"\nFinal: image_url = {final.get('image_url', 'N/A')}")

    # --- Provider comparison ---
    print("\n=== 3. Alternative: Replicate SD (open-weight) ===")
    sd = generate_replicate_sd(prompt, demo_mode=True)
    print(json.dumps(sd, indent=2))

    print("\n=== Provider cost comparison ===")
    providers = [
        ("DALL-E 3 (1024px standard)", 0.040),
        ("DALL-E 3 (1024px HD)", 0.080),
        ("DALL-E 2 (1024px)", 0.020),
        ("Replicate SDXL", 0.0023),
        ("Replicate Flux", 0.003),
    ]
    for name, cost in providers:
        monthly_1k = cost * 1000
        print(f"  {name:<30} ${cost:.4f}/img  ${monthly_1k:.2f}/1k imgs")


if __name__ == "__main__":
    main()
