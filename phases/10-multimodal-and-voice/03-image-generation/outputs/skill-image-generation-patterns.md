---
name: skill-image-generation-patterns
description: Provider comparison, content policy handling, async generation service pattern, and approval workflow for production image generation
version: "1.0"
phase: "10"
lesson: "03"
tags: [image-generation, dalle3, stable-diffusion, content-policy, async, workflow]
---

# Image Generation Patterns Reference

## Provider comparison

| Provider | Cost/image | P95 latency | Content policy | Best for |
|----------|-----------|-------------|----------------|----------|
| DALL-E 3 (1024px) | $0.040 | 12-20s | Strict, auto-applied | Product UX, brand safety |
| DALL-E 3 (1024px HD) | $0.080 | 15-25s | Strict | High-quality marketing |
| DALL-E 2 (1024px) | $0.020 | 5-10s | Strict | Lower cost, faster |
| Replicate SDXL | $0.0023 | 3-8s | Configurable | High volume, cost-sensitive |
| Replicate Flux | $0.003 | 4-10s | Configurable | Quality + speed balance |
| Ideogram v2 | $0.080 | 15-25s | Moderate | Text-in-image, logos |

## Content policy handling pattern

```python
def generate_with_retry(prompt: str) -> dict:
    result = generate_dalle3(prompt)

    if result["status"] == "content_policy_violation":
        sanitized = sanitize_prompt(prompt)
        result = generate_dalle3(sanitized)
        result["was_sanitized"] = True

        if result["status"] == "content_policy_violation":
            return {
                "status": "failed_content_policy",
                "image_url": None,
                "user_message": "This prompt cannot be used to generate an image. Try describing the concept differently.",
            }

    return result

def sanitize_prompt(prompt: str) -> str:
    """Remove sensitive keywords, add safety guidance."""
    BLOCKED = ["violent", "nude", "explicit", "blood", "weapon",
               "realistic person", "celebrity"]
    for kw in BLOCKED:
        prompt = prompt.replace(kw, "").replace(kw.title(), "")
    while "  " in prompt:
        prompt = prompt.replace("  ", " ")
    return prompt.strip() + ", professional context, brand-safe"
```

## Async generation service

```
POST /generations
  Body: {"prompt": "..."}
  Response 202: {"generation_id": "abc123", "status_url": "/generations/abc123"}

GET /generations/{id}
  Response: {"status": "pending|generating|success|failed", "image_url": "..."}
```

Implementation (FastAPI + background tasks):

```python
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import uuid, redis

app = FastAPI()
r = redis.Redis()

class GenRequest(BaseModel):
    prompt: str

@app.post("/generations", status_code=202)
async def submit(req: GenRequest, tasks: BackgroundTasks):
    gen_id = str(uuid.uuid4())
    r.hset(f"gen:{gen_id}", mapping={"status": "pending", "prompt": req.prompt})
    tasks.add_background_task(run_generation, gen_id, req.prompt)
    return {"generation_id": gen_id, "status_url": f"/generations/{gen_id}"}

@app.get("/generations/{gen_id}")
async def status(gen_id: str):
    data = r.hgetall(f"gen:{gen_id}")
    return {k.decode(): v.decode() for k, v in data.items()}

async def run_generation(gen_id: str, prompt: str):
    r.hset(f"gen:{gen_id}", "status", "generating")
    result = generate_with_retry(prompt)
    if result["status"] == "success":
        permanent_url = upload_to_storage(result["image_url"])  # S3/GCS
        r.hset(f"gen:{gen_id}", mapping={
            "status": "success",
            "image_url": permanent_url,
        })
    else:
        r.hset(f"gen:{gen_id}", "status", result["status"])
```

## Storage: always download before serving

DALL-E response URLs expire in ~1 hour. Always download and re-host:

```python
import urllib.request, boto3

def upload_to_storage(temporary_url: str, generation_id: str) -> str:
    filename = f"generated/{generation_id}.png"
    urllib.request.urlretrieve(temporary_url, "/tmp/img.png")
    s3 = boto3.client("s3")
    s3.upload_file("/tmp/img.png", "my-bucket", filename,
                   ExtraArgs={"ContentType": "image/png"})
    return f"https://my-bucket.s3.amazonaws.com/{filename}"
```

## Approval workflow design

```
User submits prompt
  -> Generation service creates image
  -> Image enters approval queue (status: pending_review)
  -> Reviewer sees: original prompt, generated image, revised_prompt from DALL-E
  -> Reviewer actions: approve / reject / regenerate with notes
  -> On approve: status = published, image served to users
  -> On reject: optional notification to user with reason
```

When to require approval:
- Always for external-facing content (brand risk)
- Skip for internal tools where users are employees
- Consider auto-approve for low-risk categories (abstract backgrounds, icons)

## Prompting guide for DALL-E 3

Structure: `[Subject], [setting], [lighting], [style], [quality markers]`

Examples:
- Product photo: `Premium wireless headphones on a clean white surface, studio lighting, product photography, sharp focus, commercial quality`
- Marketing hero: `Young professional using a laptop in a bright coffee shop, golden hour window light, lifestyle photography, warm tones`
- Abstract: `Blue gradient wave pattern, minimal design, professional, 4k`

Note: DALL-E 3 rewrites your prompt internally. Log the `revised_prompt` field for debugging unexpected outputs.

## Cost at scale

| Volume | DALL-E 3 (std) | Replicate SDXL |
|--------|----------------|----------------|
| 100/day | $4.00/day | $0.23/day |
| 1,000/day | $40.00/day | $2.30/day |
| 10,000/day | $400.00/day | $23.00/day |

Break-even for self-hosted SD: roughly 50,000+ images/month justifies GPU infrastructure overhead.

## Production checklist

- [ ] Implement content policy retry before first demo
- [ ] Download and store generated images in your own CDN (DALL-E URLs expire)
- [ ] Use async pattern for any UI where generation takes >3 seconds
- [ ] Log original prompt, revised_prompt, policy violations, and cost per request
- [ ] Set monthly spend limit alert on OpenAI account
- [ ] Define approval workflow before launch if images appear in public-facing product
- [ ] Track content policy hit rate by prompt category
