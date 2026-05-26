"""
Lesson 10-01: Vision-Language Models in Apps
Sends an image to Claude and returns structured analysis as JSON.
Demo mode generates a synthetic PNG so no external image file is required.

Usage:
    python main.py                    # demo mode (generates synthetic PNG)
    python main.py sample.png         # analyze a local image file
"""

import anthropic
import base64
import json
import math
import struct
import sys
import zlib
from pathlib import Path


# --------------------------------------------------------------------------- #
# Demo image generator (stdlib only, no Pillow required)                      #
# --------------------------------------------------------------------------- #

def _make_minimal_png(width: int = 64, height: int = 64) -> bytes:
    """Generate a minimal valid PNG in memory using only stdlib."""

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = len(data)
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return (
            struct.pack(">I", length)
            + chunk_type
            + data
            + struct.pack(">I", crc)
        )

    # IHDR: width, height, bit depth=8, color type=2 (RGB), compression=0, filter=0, interlace=0
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    # Build raw image data: each row has a filter byte (0 = None) + RGB pixels
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # filter byte
        for x in range(width):
            rows.append(int(x * 255 / max(width - 1, 1)))   # R
            rows.append(int(y * 255 / max(height - 1, 1)))  # G
            rows.append(128)                                  # B

    compressed = zlib.compress(bytes(rows))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr_data)
        + png_chunk(b"IDAT", compressed)
        + png_chunk(b"IEND", b"")
    )
    return png


# --------------------------------------------------------------------------- #
# Token cost formula                                                           #
# --------------------------------------------------------------------------- #

def estimate_vision_tokens(width: int, height: int) -> int:
    """
    Anthropic vision token formula.
    Divides image into 32x32 tiles, charges 65 tokens per tile.
    """
    tiles_wide = math.ceil(width / 32)
    tiles_tall = math.ceil(height / 32)
    return tiles_wide * tiles_tall * 65


# --------------------------------------------------------------------------- #
# Core vision function                                                         #
# --------------------------------------------------------------------------- #

def analyze_image(
    image_bytes: bytes,
    media_type: str = "image/png",
    prompt: str = (
        "Analyze this image. Return JSON with keys: "
        "description (string), dominant_colors (list of strings), "
        "detected_text (list of strings), notable_elements (list of strings)."
    ),
    model: str = "claude-3-5-haiku-20241022",
) -> dict:
    """
    Send an image to Claude as a base64-encoded block.
    Returns the parsed JSON response from the model.
    """
    client = anthropic.Anthropic()

    b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")

    print(f"  Image size: {len(image_bytes):,} bytes")

    message = client.messages.create(
        model=model,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    raw_text = message.content[0].text

    # Strip markdown code fences if present
    if "```" in raw_text:
        parts = raw_text.split("```")
        raw_text = parts[1].lstrip("json").strip()

    try:
        analysis = json.loads(raw_text)
    except json.JSONDecodeError:
        analysis = {"raw_response": raw_text}

    return {
        "analysis": analysis,
        "usage": {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
        },
        "model": message.model,
    }


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #

def main():
    print("=== Lesson 10-01: Vision-Language Models in Apps ===\n")

    # Show token cost comparisons
    print("--- Vision token cost by image size ---")
    for label, w, h in [
        ("256x256", 256, 256),
        ("512x512", 512, 512),
        ("768x768", 768, 768),
        ("1920x1080", 1920, 1080),
        ("3840x2160", 3840, 2160),
    ]:
        tokens = estimate_vision_tokens(w, h)
        cost = tokens * 0.00000025  # Haiku input: $0.25/1M tokens
        print(f"  {label:12s}: {tokens:>7,} tokens  (~${cost:.4f})")
    print()

    # Determine image source
    if len(sys.argv) > 1:
        image_path = Path(sys.argv[1])
        if not image_path.exists():
            print(f"Error: file not found: {image_path}")
            sys.exit(1)
        print(f"Using image file: {image_path}")
        image_bytes = image_path.read_bytes()
        media_type = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    else:
        print("No image file provided. Generating synthetic demo PNG (64x64 gradient).")
        image_bytes = _make_minimal_png(64, 64)
        media_type = "image/png"

    print()
    print("Sending image to Claude for structured analysis...")
    result = analyze_image(image_bytes, media_type=media_type)

    print("\n--- Analysis Result ---")
    print(json.dumps(result["analysis"], indent=2))
    print("\n--- Token Usage ---")
    print(f"  Input tokens:  {result['usage']['input_tokens']:,}")
    print(f"  Output tokens: {result['usage']['output_tokens']:,}")
    print(f"  Model:         {result['model']}")
    cost = result["usage"]["input_tokens"] * 0.00000025
    print(f"  Estimated input cost: ${cost:.6f}")


if __name__ == "__main__":
    main()
