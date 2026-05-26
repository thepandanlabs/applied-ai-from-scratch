---
name: prompt-model-selection-guide
description: Decision guide and cost reference for selecting the right AI model tier for production tasks
version: "1.0"
phase: "00"
lesson: "02"
tags: [model-selection, cost, providers, claude, openai, gemini]
---

# Model Selection Guide

## The Core Rule

Start with the cheapest model that meets your quality bar. Upgrade only when you have evidence the cheaper model fails on your task.

The fast tier (Haiku, GPT-4o mini, Gemini Flash) handles the majority of production AI tasks: classification, extraction, summarization, routing, and structured output generation. The powerful tier earns its cost on: complex multi-step reasoning, long document synthesis (100K+ tokens), nuanced long-form generation, and tasks where a single wrong answer has high consequence.

---

## The 2026 Tier Matrix

| Tier | Claude | OpenAI | Gemini | Best For |
|------|--------|--------|--------|----------|
| Fast | Haiku 3.5 | GPT-4o mini | Gemini 2.0 Flash | Classification, extraction, routing, high-volume |
| Balanced | Sonnet 4 | GPT-4o | Gemini 2.0 Pro | Most production features, agentic tasks |
| Powerful | Opus 4 | o3 | Gemini 2.0 Ultra | Complex reasoning, research, synthesis |
| Open-weight | Llama 3.3 70B | -- | -- | Cost-sensitive, on-prem, no data-sharing constraints |

---

## Task-to-Tier Routing

```
TASK TYPE                        RECOMMENDED TIER    NOTES
---------                        ----------------    -----
Binary classification             Fast               e.g. spam/not-spam
Multi-class classification        Fast               up to ~20 classes
Named entity extraction           Fast               structured output
Key-value extraction              Fast               JSON output
Short summarization (<2K src)     Fast
Long summarization (>10K src)     Balanced           needs more context
Document Q&A (with RAG)           Balanced           context matters
Code generation (simple)          Balanced
Code generation (complex)         Powerful
Multi-document synthesis          Powerful
Long-form writing                 Balanced or Powerful
Agentic task with tool use        Balanced           Sonnet is the standard
Complex reasoning chains          Powerful
Routing / intent detection        Fast               always
```

---

## Cost Reference (approximate, as of early 2026)

Prices in USD per 1M tokens. Verify at provider pricing pages before committing to a budget.

| Model | Input | Output | Context |
|-------|-------|--------|---------|
| claude-3-5-haiku-20241022 | $0.80 | $4.00 | 200K |
| claude-sonnet-4-5 | $3.00 | $15.00 | 200K |
| claude-opus-4-5 | $15.00 | $75.00 | 200K |
| gpt-4o-mini | $0.15 | $0.60 | 128K |
| gpt-4o | $2.50 | $10.00 | 128K |
| gemini-2.0-flash | $0.10 | $0.40 | 1M |
| gemini-2.0-pro | $1.25 | $5.00 | 2M |

---

## API Key Management

**Rule: API keys never appear in source code.**

```
.env file (gitignored)
  ANTHROPIC_API_KEY=sk-ant-...
  OPENAI_API_KEY=sk-proj-...

code:
  from dotenv import load_dotenv
  load_dotenv()
  client = anthropic.Anthropic()   # reads from env automatically
```

Environment variable priority (highest to lowest):
1. Existing `os.environ` variables (set by CI/CD, platform secrets)
2. `.env` file values (loaded by `load_dotenv()`)
3. SDK defaults (none -- will raise AuthenticationError if missing)

**In production:** inject keys via platform secrets (AWS Secrets Manager, GCP Secret Manager, Kubernetes secrets, Render/Fly.io environment variables). Never via `.env` files in containers.

---

## Monthly Cost Formula

```python
monthly_cost = (
    (input_tokens / 1_000_000) * input_price
    + (output_tokens / 1_000_000) * output_price
) * calls_per_day * 30
```

Example: 500 calls/day, 1K input tokens, 300 output tokens:
- Haiku:  (1000/1M * $0.80 + 300/1M * $4.00) * 500 * 30 = ~$30/month
- Sonnet: (1000/1M * $3.00 + 300/1M * $15.00) * 500 * 30 = ~$113/month
- Opus:   (1000/1M * $15.00 + 300/1M * $75.00) * 500 * 30 = ~$563/month

The choice between Haiku and Sonnet here is a $83/month question. That difference buys meaningful capability -- but only if your task actually needs it.

---

## Provider Selection Guide

**Use Anthropic (Claude) when:**
- You need 200K+ context window
- Safety and instruction-following are paramount
- You are building with MCP (Claude is the reference implementation)
- You are uncertain -- Claude Sonnet is the most forgiving default

**Use OpenAI when:**
- Your team already has GPT integrations and switching cost is high
- You need the Assistants API or fine-tuning
- gpt-4o-mini's cost ($0.15/1M) is a decisive budget constraint

**Use Gemini when:**
- You need very long context (1M+ tokens for Flash, 2M for Pro)
- You are in a Google Cloud / Vertex AI ecosystem
- Cost per token is the dominant constraint (Flash is the cheapest tier)

**Use open-weight (vLLM + Llama) when:**
- Data cannot leave your infrastructure (compliance, PII)
- You have the GPU budget and want $0 per-token API cost
- You need to fine-tune on proprietary data
- You are willing to manage infra and handle model updates yourself

---

## Common Mistakes

**Mistake: Default to the most powerful model.**
Fix: Start with Haiku. Run 50 representative examples. Check quality. Upgrade only if you find failures.

**Mistake: Hardcode model strings.**
Fix: Use a ModelConfig or config file. Model IDs change across versions and you want one place to update.

**Mistake: Ignore output token cost.**
Fix: For most models, output tokens cost 4-5x more than input tokens. A prompt that generates 2K output tokens instead of 200 costs 10x more in output fees alone.

**Mistake: Test on toy examples, deploy on production data.**
Fix: Your test set must include real user inputs sampled from production traffic. Model performance on synthetic data often does not transfer.
