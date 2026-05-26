---
name: skill-vision-api-integration
description: Reference for adding vision to an existing text API integration - encoding patterns, token cost formula, size limits, and prompting strategies
version: "1.0"
phase: "10"
lesson: "01"
tags: [vision, multimodal, base64, token-cost, image-encoding]
---

# Vision API Integration Reference

## Encoding patterns

### Base64 (local or private images)

```python
import base64, anthropic

image_bytes = open("screenshot.png", "rb").read()
b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

client = anthropic.Anthropic()
message = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=512,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b64},
            },
            {"type": "text", "text": "Describe what you see."},
        ],
    }],
)
```

### URL reference (publicly hosted images)

```python
message = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=512,
    messages=[{
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "url", "url": "https://cdn.example.com/img.jpg"},
            },
            {"type": "text", "text": "Describe what you see."},
        ],
    }],
)
```

### Files API (reuse across requests)

```python
# Upload once
with open("doc.png", "rb") as f:
    file_resp = client.beta.files.upload(file=("doc.png", f, "image/png"))
file_id = file_resp.id

# Reference in every subsequent request - no re-encoding
content = [
    {"type": "image", "source": {"type": "file", "file_id": file_id}},
    {"type": "text", "text": "What does this page show?"},
]
```

## Token cost formula

```python
import math

def vision_tokens(width: int, height: int) -> int:
    tiles_wide = math.ceil(width / 32)
    tiles_tall = math.ceil(height / 32)
    return tiles_wide * tiles_tall * 65
```

| Image size | Tokens | Cost at $0.25/1M (Haiku input) |
|------------|--------|-------------------------------|
| 256x256 | 4,160 | $0.001 |
| 512x512 | 16,640 | $0.004 |
| 768x768 | 37,440 | $0.009 |
| 1920x1080 | 132,600 | $0.033 |
| 3840x2160 | 530,400 | $0.133 |

Practical rule: resize to 768px longest edge before sending unless pixel-level detail is required.

## Supported formats and limits

| Format | Notes |
|--------|-------|
| JPEG | Recommended for photos |
| PNG | Recommended for screenshots and UI |
| GIF | First frame only |
| WebP | Supported; common in browser uploads |

- Maximum file size: 5 MB per image
- Maximum images per request: 20
- Minimum useful size: 200x200 px (below this quality degrades)

## Prompting strategies by visual task

### UI / screenshot analysis

```
Describe the UI elements visible in this screenshot.
Return JSON: {"page_title": "", "primary_action": "", "error_messages": [], "form_fields": []}
```

### Document field extraction

```
Extract the following fields from this document image.
Return JSON: {"date": "", "sender": "", "recipient": "", "subject": "", "key_amounts": []}
If a field is not visible, use null.
```

### Object presence check

```
Does this image contain [X]? Answer with JSON: {"present": true/false, "confidence": "high/medium/low", "location_description": ""}
```

### Error message extraction

```
Extract all visible error messages or warning text from this screenshot.
Return JSON: {"errors": ["..."], "warnings": ["..."]}
```

## Capability matrix

| Task | Reliability | Notes |
|------|-------------|-------|
| OCR on printed text | High | 95%+ on clean fonts |
| UI element description | High | Good for support automation |
| Object presence detection | High | Reliable for distinct objects |
| Error message reading | High | Excellent for tech support |
| Handwriting OCR | Medium | Depends on legibility |
| Pixel coordinate extraction | Low | Do not rely on exact coords |
| Counting >10 items | Low | Use structured table prompts |
| Low-contrast text | Low | Preprocess with contrast boost |

## Cost control checklist

- [ ] Resize images to 768px longest edge before encoding
- [ ] Use URL references for images already on a CDN
- [ ] Use Files API when same image is analyzed multiple times
- [ ] Log `usage.input_tokens` per request in production
- [ ] Set a per-image token budget alert (e.g., alert if >100k tokens for a single image)
- [ ] Strip EXIF metadata before sending (no privacy value, adds bytes)
