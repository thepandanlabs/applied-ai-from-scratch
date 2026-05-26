# API Keys, Providers, and the 2026 Model Landscape

> The model you pick is a cost/latency/capability tradeoff, not a correctness decision. Most tasks work fine with Haiku at 20x lower cost than Opus.

**Type:** Learn
**Languages:** Python
**Prerequisites:** 00-01 (Dev Environment)
**Time:** ~45 min
**Learning Objectives:**
- Load API keys safely using environment variables and python-dotenv
- Understand the 2026 model tier matrix for Claude, OpenAI, and Gemini
- Build a ModelConfig class that captures provider/model/cost metadata
- Make cost-aware model selection decisions for different task types

---

## The Problem

You are building a document summarization feature for a legal tech company. You wire it up with GPT-4o because that is the model you know works. The feature launches, usage climbs, and three weeks later your CTO asks why the AI budget jumped from $200/month to $3,400/month.

The problem is not that GPT-4o is bad. The problem is that most of your summarization tasks are routine: extracting key dates, parties, and clauses from standard contract templates. A model that costs 20x less and responds 3x faster handles 80% of those tasks with no quality difference. You picked the expensive option by default, not by design.

This lesson covers two things that are easy to get wrong early: keeping API keys out of your code, and understanding the model tier matrix well enough to make deliberate cost/capability decisions from day one.

---

## The Concept

### Keeping Keys Out of Code

An API key in source code is a credential leak waiting to happen. When you push to GitHub, key scanners find it within minutes. The correct pattern uses three layers:

```
WRONG:
  client = Anthropic(api_key="sk-ant-api03-abc123...")
  # ^ This is now in git history forever, even if you delete it later.

CORRECT (3-layer pattern):
  .env file          -->  ANTHROPIC_API_KEY=sk-ant-...  (in .gitignore)
     |
  os.environ         -->  loaded by python-dotenv at startup
     |
  client             -->  Anthropic()  (SDK reads from env automatically)
```

The `.env` file lives only on your machine and in your CI/CD secrets manager. Never in git.

### The 2026 Model Tier Matrix

Every major provider now publishes a three-tier model family: fast/cheap, balanced, and powerful/expensive. The dimensions that matter for selection are cost (per million tokens), latency (time-to-first-token), context window, and capability ceiling.

```
FAST / CHEAP              BALANCED                  POWERFUL / EXPENSIVE
(routine tasks,           (most production          (complex reasoning,
 high volume)             workloads)                 long context, research)

Claude Haiku 3.5          Claude Sonnet 4           Claude Opus 4
~$0.80/1M in              ~$3/1M in                 ~$15/1M in
~$4/1M out                ~$15/1M out               ~$75/1M out
200K context              200K context              200K context

GPT-4o mini               GPT-4o                    o3
~$0.15/1M in              ~$2.50/1M in              ~$10/1M in
~$0.60/1M out             ~$10/1M out               ~$40/1M out
128K context              128K context              200K context

Gemini 2.0 Flash          Gemini 2.0 Pro            Gemini 2.0 Ultra
~$0.10/1M in              ~$1.25/1M in              ~$5/1M in
~$0.40/1M out             ~$5/1M out                ~$15/1M out
1M context                2M context                1M context

Open-weight (self-hosted via vLLM):
Llama 3.3 70B             Llama 3.1 405B            ---
$0 API cost               $0 API cost
(infra cost only)         (infra cost only)
```

Note: prices shift frequently. Treat these as order-of-magnitude references, not billing guarantees. Check provider pricing pages for current rates.

### The Decision Heuristic

```
Is the task well-defined with a clear correct answer?
  YES --> Start with Fast/Cheap. Test it. Only upgrade if quality fails.
  NO  --> Is it a one-shot user interaction where quality matters?
            YES --> Balanced tier.
            NO  --> Is it complex multi-step reasoning or long document analysis?
                      YES --> Powerful tier or balanced with extended thinking.
                      NO  --> Re-examine whether you need AI at all.
```

Most production AI features -- classification, extraction, summarization, routing -- run fine on the fast/cheap tier. The powerful tier earns its cost on: multi-document synthesis, code generation for complex systems, nuanced long-form writing, and tasks requiring 100K+ token context.

---

## Build It

### Step 1: Set Up Key Loading

```bash
# Install python-dotenv
uv add python-dotenv

# Create .env (one time, never commit this)
touch .env
echo "ANTHROPIC_API_KEY=your-key-here" >> .env

# Add to .gitignore
echo ".env" >> .gitignore
```

```python
# key_loader.py
import os
from dotenv import load_dotenv

def load_api_keys() -> dict[str, str | None]:
    """
    Load API keys from environment variables.
    .env file is loaded first, then actual environment variables override.
    Returns a dict of provider -> key (None if not set).
    """
    load_dotenv()  # reads .env into os.environ (does not overwrite existing vars)

    keys = {
        "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
        "openai": os.environ.get("OPENAI_API_KEY"),
        "gemini": os.environ.get("GEMINI_API_KEY"),
    }

    for provider, key in keys.items():
        if key:
            masked = key[:8] + "..." + key[-4:]
            print(f"  {provider}: {masked}")
        else:
            print(f"  {provider}: NOT SET")

    return keys
```

### Step 2: Build a ModelConfig Class

```python
# model_config.py
from dataclasses import dataclass

@dataclass
class ModelConfig:
    provider: str           # "anthropic", "openai", "gemini", "vllm"
    model_id: str           # exact model string for the API call
    tier: str               # "fast", "balanced", "powerful"
    input_cost_per_1m: float    # USD per 1M input tokens
    output_cost_per_1m: float   # USD per 1M output tokens
    context_window: int     # max tokens (input + output)
    notes: str = ""

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Return estimated USD cost for a single call."""
        input_cost = (input_tokens / 1_000_000) * self.input_cost_per_1m
        output_cost = (output_tokens / 1_000_000) * self.output_cost_per_1m
        return input_cost + output_cost

# The 2026 catalog (approximate -- verify current pricing before committing to a budget)
MODEL_CATALOG: dict[str, ModelConfig] = {
    "claude-haiku": ModelConfig(
        provider="anthropic",
        model_id="claude-3-5-haiku-20241022",
        tier="fast",
        input_cost_per_1m=0.80,
        output_cost_per_1m=4.00,
        context_window=200_000,
        notes="Best for classification, extraction, high-volume tasks",
    ),
    "claude-sonnet": ModelConfig(
        provider="anthropic",
        model_id="claude-sonnet-4-5",
        tier="balanced",
        input_cost_per_1m=3.00,
        output_cost_per_1m=15.00,
        context_window=200_000,
        notes="Production workhorse for most AI features",
    ),
    "claude-opus": ModelConfig(
        provider="anthropic",
        model_id="claude-opus-4-5",
        tier="powerful",
        input_cost_per_1m=15.00,
        output_cost_per_1m=75.00,
        context_window=200_000,
        notes="Complex reasoning, long-form synthesis, research tasks",
    ),
    "gpt-4o-mini": ModelConfig(
        provider="openai",
        model_id="gpt-4o-mini",
        tier="fast",
        input_cost_per_1m=0.15,
        output_cost_per_1m=0.60,
        context_window=128_000,
        notes="OpenAI fast tier; very low cost",
    ),
    "gpt-4o": ModelConfig(
        provider="openai",
        model_id="gpt-4o",
        tier="balanced",
        input_cost_per_1m=2.50,
        output_cost_per_1m=10.00,
        context_window=128_000,
        notes="OpenAI production standard",
    ),
    "gemini-flash": ModelConfig(
        provider="gemini",
        model_id="gemini-2.0-flash",
        tier="fast",
        input_cost_per_1m=0.10,
        output_cost_per_1m=0.40,
        context_window=1_000_000,
        notes="Extremely fast and cheap; best for very long context at low cost",
    ),
}
```

### Step 3: Demonstrate Missing Key Behavior

```python
# show what happens without a key set
import anthropic
import os

os.environ.pop("ANTHROPIC_API_KEY", None)  # simulate missing key

try:
    client = anthropic.Anthropic()  # SDK reads from env
    client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=16,
        messages=[{"role": "user", "content": "ping"}],
    )
except anthropic.AuthenticationError as e:
    print(f"AuthenticationError (expected): {e}")
except Exception as e:
    print(f"Error type: {type(e).__name__}: {e}")
```

> **Real-world check:** Your team's AI feature is used by 500 enterprise users per day. Each request sends about 1,000 input tokens and receives about 300 output tokens. Your manager asks: "Can we estimate the monthly AI cost?" Walk through the math using the ModelConfig.estimate_cost() method for both claude-haiku and claude-sonnet. What is the monthly cost difference, and does it justify which tier you choose?

### Step 4: Build a Cost-Aware Selector

```python
def select_model(task_type: str, token_volume: str = "low") -> ModelConfig:
    """
    Simple rule-based model selector.
    In production, this logic lives in a config file, not hardcoded here.
    """
    ROUTING_TABLE = {
        # (task_type, token_volume) -> model key
        ("classification", "high"): "claude-haiku",
        ("classification", "low"): "claude-haiku",
        ("extraction", "high"): "claude-haiku",
        ("extraction", "low"): "claude-haiku",
        ("summarization", "high"): "claude-haiku",
        ("summarization", "low"): "claude-sonnet",
        ("generation", "high"): "claude-sonnet",
        ("generation", "low"): "claude-sonnet",
        ("reasoning", "high"): "claude-sonnet",
        ("reasoning", "low"): "claude-opus",
    }
    key = ROUTING_TABLE.get((task_type, token_volume), "claude-sonnet")
    return MODEL_CATALOG[key]

# Example usage
for task in ["classification", "summarization", "reasoning"]:
    config = select_model(task, "high")
    monthly_cost = config.estimate_cost(1000, 300) * 500 * 30
    print(f"{task:20} -> {config.model_id:35} ${monthly_cost:,.2f}/month")
```

---

## Use It

The Anthropic SDK reads `ANTHROPIC_API_KEY` from the environment automatically when you call `Anthropic()` with no arguments:

```python
import anthropic
from dotenv import load_dotenv

load_dotenv()  # load .env into os.environ

# No api_key= argument needed -- SDK reads from ANTHROPIC_API_KEY
client = anthropic.Anthropic()

# Create a message using the haiku model (fast tier)
response = client.messages.create(
    model="claude-3-5-haiku-20241022",
    max_tokens=256,
    messages=[{"role": "user", "content": "Classify this as POSITIVE, NEGATIVE, or NEUTRAL: 'The product works as described.'"}],
)

print(response.content[0].text)
print(f"Tokens used: {response.usage.input_tokens} in / {response.usage.output_tokens} out")
```

The SDK raises `anthropic.AuthenticationError` if the key is missing or invalid, `anthropic.RateLimitError` if you exceed your tier quota, and `anthropic.APIConnectionError` for network issues. Catch these specifically rather than using a bare `except Exception`.

> **Perspective shift:** python-dotenv's `load_dotenv()` only reads the `.env` file if the variable is not already in `os.environ`. This means the same code works in three environments without modification: local dev (reads from `.env`), CI/CD (reads from pipeline secrets injected into env vars), and production (reads from platform secrets like AWS Secrets Manager or Kubernetes secrets, which are also injected as env vars). The code never changes -- only the source of the environment variable changes.

---

## Ship It

The artifact for this lesson is a model selection decision guide.

See `outputs/prompt-model-selection-guide.md`.

---

## Evaluate It

Your key management and model selection setup is production-ready when:

```bash
# 1. No keys in any Python file
grep -r "sk-ant\|sk-proj\|AIza" code/ outputs/ docs/
# Expected: no matches

# 2. .env is gitignored
grep -c "\.env" .gitignore
# Expected: 1 or more

# 3. Key loads correctly via dotenv
uv run python -c "
from dotenv import load_dotenv
import os
load_dotenv()
key = os.environ.get('ANTHROPIC_API_KEY', '')
print('Key present:', bool(key))
print('Key format OK:', key.startswith('sk-ant-') if key else False)
"

# 4. ModelConfig cost math is correct
uv run python -c "
from model_config import MODEL_CATALOG
haiku = MODEL_CATALOG['claude-haiku']
cost = haiku.estimate_cost(1000, 300)
print(f'1K in + 300 out with haiku: \${cost:.6f}')
assert cost < 0.01, 'Haiku cost estimate seems too high'
print('Cost estimate: OK')
"

# 5. Authentication error is raised cleanly when key is missing
uv run python -c "
import anthropic, os
os.environ.pop('ANTHROPIC_API_KEY', None)
try:
    anthropic.Anthropic().messages.create(model='claude-3-5-haiku-20241022', max_tokens=8, messages=[{'role':'user','content':'x'}])
    print('ERROR: should have raised')
except anthropic.AuthenticationError:
    print('OK: AuthenticationError raised as expected')
"
```
