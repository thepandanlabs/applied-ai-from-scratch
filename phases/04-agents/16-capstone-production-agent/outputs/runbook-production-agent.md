---
name: runbook-production-agent
description: Operational runbook for deploying, configuring, monitoring, and debugging the production codebase assistant agent
version: "1.0"
phase: "04"
lesson: "16"
tags: [agents, runbook, operations, production, guardrails, tracing]
---

# Runbook: Production Codebase Assistant Agent

This runbook covers how to configure, deploy, monitor, and debug the codebase assistant agent. It is the first document to reference when an on-call incident involves this agent.

---

## Configuration

All configuration is via environment variables. Set these before running or in your `.env` file.

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Anthropic API key. Never hardcode. |
| `AGENT_MAX_ITER` | 15 | Governor: max iterations per request. Raise only after profiling why the default is insufficient. |
| `AGENT_MAX_TOKENS` | 50000 | Governor: max total tokens (input + output) per request. |
| `AGENT_MAX_SECONDS` | 180 | Governor: max wall-clock seconds per request. |
| `APPROVAL_REQUIRED_TOOLS` | suggest_fix | Comma-separated list of tool names that require human approval. |
| `LOG_LEVEL` | INFO | Logging verbosity: DEBUG, INFO, WARNING, ERROR. |

Load via `python-dotenv` in development:

```python
from dotenv import load_dotenv
load_dotenv()  # reads .env in current directory
```

---

## Deployment

### Docker (recommended)

```bash
# Build
docker build -t codebase-assistant:latest ./code/

# Run interactively
docker run -it \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  codebase-assistant:latest

# Run with custom governor settings
docker run -it \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e AGENT_MAX_ITER=20 \
  -e AGENT_MAX_SECONDS=300 \
  codebase-assistant:latest
```

### Local (development)

```bash
uv venv && uv pip install -r code/requirements.txt
ANTHROPIC_API_KEY=sk-ant-... python code/main.py
```

---

## Governor Thresholds and Tuning

The governor enforces three hard limits. Each has a default and guidance for when to change it.

**`AGENT_MAX_ITER` (default: 15)**

Most queries should complete in 3-8 iterations. 15 provides headroom for complex multi-step tasks. If you see governor stops at iteration 15 regularly, check the trace: is the agent looping (MAST/Memory failure) or legitimately needing more steps? If looping: fix the memory issue, do not raise the limit. If legitimately needing more steps: raise to 20 and monitor.

Signs the limit is too low: governor fires on requests that should complete, with no looping in the trace.
Signs the limit is correct: governor fires after clear looping behavior.

**`AGENT_MAX_TOKENS` (default: 50,000)**

Covers roughly 3-5 deep tool calls with full context. If reading large files causes budget overruns, consider truncating file contents in the `read_file` stub at 10,000 characters. Do not raise the token budget as the first response to overruns.

**`AGENT_MAX_SECONDS` (default: 180)**

Set at 3x the expected p90 latency. If p90 is 45 seconds, 180 is correct. If your workload changes and p90 rises, measure first and raise the threshold to match.

---

## Monitoring

The agent emits structured trace output on every request. In production, pipe this to your observability stack (Langfuse or Phoenix recommended).

**Key metrics to track:**

| Metric | Alert Threshold | What to Do |
|---|---|---|
| `governor.iterations` p95 | > 10 | Check for looping. Run FailureDetector on recent traces. |
| `governor.tokens_used` p95 | > 40,000 | Check for large file reads or long context. Truncate tool outputs. |
| `governor.elapsed_s` p95 | > 120s | Check for slow tool calls. Profile which tools take the longest. |
| Governor stop rate | > 5% of requests | Investigate whether tasks are too complex or the agent is looping. |
| Approval gate rejection rate | > 20% | The agent may be proposing low-quality fixes. Check the read_file step. |

**Trace fields (gen_ai.* naming convention for OTel compatibility):**

```
gen_ai.request.model       - model used
gen_ai.usage.input_tokens  - tokens in per turn
gen_ai.usage.output_tokens - tokens out per turn
agent.turn_number          - iteration number
agent.tool_called          - tool name or "none"
agent.thought              - extracted Thought: from ReAct reasoning
agent.outcome              - completed | budget_exceeded | max_turns_reached
```

---

## Common Failure Symptoms and Diagnosis

**Symptom: Agent stops with "iteration limit reached" on simple queries.**

Diagnosis: check the trace for repeated identical tool calls (MAST/Memory). If `search_files` appears 10 times with the same query, the agent is looping. Root cause: the agent's context window does not contain enough of its prior history. Fix: verify `trim_history()` retains at least 10 turns and that tool results are included in the messages passed to the API.

**Symptom: Agent declares "task complete" after a tool returns an error.**

Diagnosis: MAST/Action failure (error ignored) or MAST/Task failure (false completion). Run the `FailureDetector` from Lesson 14 on the trace. Fix: ensure the tool executor returns error messages in a format the agent treats as failure (not as success). Check that the AGENT_SYSTEM_PROMPT instructs the agent to acknowledge errors before continuing.

**Symptom: `suggest_fix` tool fires but the approval gate never appears.**

Diagnosis: the `execute_tool()` function is not being called, or `APPROVAL_FLAGS['suggest_fix']` is False. Verify: `print(APPROVAL_FLAGS)` at startup. Verify: all tool dispatch routes through `execute_tool()`, not directly to `_stub_tool()`.

**Symptom: Traces show very high token usage on `read_file` calls.**

Diagnosis: the file content stub (or real file content) is very large. Fix: truncate `read_file` responses to 10,000 characters with a note that the content was truncated. Add a `max_chars` parameter to the tool schema.

**Symptom: Router classifies "suggest a fix" as "general" instead of "suggest."**

Diagnosis: the router's single-token output is unreliable for edge cases. Fix: expand the router prompt with examples, or add a fallback: if intent is "general" but the user message contains "fix", "refactor", or "change", reclassify as "suggest."

---

## Regression Eval Protocol

Run before every change to: the system prompt, the router prompt, the model version, or the tool definitions.

```bash
# Run the golden set eval
python code/main.py
# Choose option 2 at the prompt

# Or import directly in CI
python -c "from main import run_regression_eval; r = run_regression_eval(); exit(0 if r['pass_rate'] >= 0.8 else 1)"
```

**Pass/fail thresholds:**
- Pass rate must remain at or above the baseline (measured before the change).
- No golden case that was PASS before the change may become FAIL.
- If mean score drops by more than 0.05: investigate before shipping.

**Expanding the golden set:**
Add cases for every new tool, every new intent type, and every failure mode you fix in production. The golden set should grow with the agent.

---

## Escalation Path

If the agent cannot complete a task within budget, it surfaces to the human with partial results and an explanation of why it stopped. The message format:

```
I was unable to complete your request within the resource budget.
Reason: [governor reason].
Here is what I found so far in [N] steps: [partial results].
To complete this task, try narrowing your question to [specific scope].
```

This is not an error. It is the correct behavior. Do not suppress the message or silently retry.

If the human needs a full result and the partial result is insufficient: narrow the query, increase governor limits (with the tuning guidance above), or decompose the task manually into smaller queries.

---

## Security Checklist

Before exposing this agent to any user-generated input:

- [ ] `ANTHROPIC_API_KEY` is loaded from environment, never hardcoded
- [ ] `suggest_fix` tool has `requires_approval=True` and the gate is verified to fire in testing
- [ ] Tool stubs are replaced with sandboxed implementations (no real filesystem write access)
- [ ] Governor limits are set for your workload (not the defaults if your workload differs)
- [ ] Agent output is not directly executed or applied without human review of the HITL gate result
- [ ] Traces do not log full file contents (may contain secrets): truncate at 500 characters in production logs
