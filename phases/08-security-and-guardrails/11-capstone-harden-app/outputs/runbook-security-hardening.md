---
name: runbook-security-hardening
description: Deployment checklist, threshold tuning guide, and incident response procedures for hardening an AI service against the OWASP LLM Top 10
version: "1.0"
phase: "08"
lesson: "11"
tags: [security, hardening, owasp, runbook, incident-response, deployment]
---

# Security Hardening Runbook

Operational guide for deploying, tuning, and responding to incidents in an AI service hardened with `SecurityLayer`.

---

## Deployment Checklist

Complete every item before promoting to production.

### Code and Configuration

- [ ] `SecurityLayer` instantiated with explicit `ConsumptionGuard` (not default)
- [ ] `ConsumptionGuard` limits reviewed against cost calculator (see L10 skill)
- [ ] `ToolPolicy` configured with explicit allowed_tools list (no wildcard)
- [ ] System prompt does not contain secrets, API keys, or internal infrastructure details
- [ ] `max_tokens` is set in every `messages.create()` call - never omitted
- [ ] ANTHROPIC_API_KEY is injected via environment variable, never hardcoded

### Container

- [ ] Image built from `python:3.12-slim` base (not `python:3.12`)
- [ ] Non-root user (`appuser`) confirmed: `docker inspect <image> | grep User`
- [ ] No secrets in image history: `docker history <image>` shows no API keys
- [ ] `HEALTHCHECK` instruction present in Dockerfile
- [ ] `/health` endpoint returns 200 without making any LLM API call

### Monitoring

- [ ] Warning logging enabled: every non-empty `warnings` list is logged at WARN level
- [ ] `blocked_by` field logged for every blocked request
- [ ] Session cost logged after every successful LLM call
- [ ] Alert configured for hourly spend exceeding 2x expected baseline
- [ ] Alert configured for `rate` limit violations exceeding 1% of requests

### Pre-launch Security Test

- [ ] `python main.py --test` passes all probes (0 failures)
- [ ] Manual test: send a 50,000-character input and verify `input_tokens` limit fires
- [ ] Manual test: send a known PII string and verify it is redacted in logs
- [ ] Manual test: send a hard-block phrase and verify `llm_called=False` in response

---

## Threshold Tuning Guide

### ConsumptionGuard limits by product type

See L10 skill for the full calculator. Quick reference:

| Limit | Consumer chatbot | Developer tool | Internal |
|-------|-----------------|----------------|----------|
| input_token_limit | 2,000 | 8,000 | 16,000 |
| max_output_tokens | 512 | 2,048 | 4,096 |
| rate_limit_rpm | 5 | 30 | 60 |
| session_cost_cap | $0.25 | $2.00 | $10.00 |
| loop_iteration_limit | 0 | 20 | 50 |

### Tuning process

1. Deploy with conservative limits (consumer profile above).
2. Run for 7 days. Review false positive rate from logs (legitimate users hitting limits).
3. For each limit where false positives exceed 1% of requests, raise that limit by 25%.
4. Recalculate worst-case hourly cost after any limit increase.
5. Document the new limits and rationale in your team's config file.

### Moderation threshold calibration

1. Pull 200 recent blocked requests from logs.
2. For each, decide: was this block correct or a false positive?
3. For false positives: remove or narrow the keyword(s) that triggered it.
4. For missed blocks (reported by users): add the phrase that was missed.
5. Test all changes against the 20-prompt normal traffic sample before shipping.
6. Target: false positive rate below 2% for consumer, 0.5% for developer tools.

---

## Incident Response

### LLM01: Prompt Injection

**Symptom:** User reports the assistant is ignoring its topic restrictions or revealing information it should not know. Logs show unusual response content.

**Triage:**
1. Pull the raw user input from logs.
2. Check whether the input contained injection phrases ("ignore instructions", "disregard previous").
3. Check whether the `retrieved_docs` for that request contained injected content.

**Response:**
- If via user input: add the injection phrase to the moderation keyword list.
- If via retrieved document: verify spotlighting is applied to all retrieved content before it enters the prompt.
- If spotlighting was applied and injection still succeeded: escalate to model provider.

**Recovery:** No data is at risk. Log the injection attempt for pattern analysis. No user notification required unless data was exposed.

---

### LLM02: Insecure Output / System Prompt Leakage

**Symptom:** User shares a screenshot showing the model output included the system prompt or internal instructions. Logs show `system_prompt_leak` or `system_prompt_verbatim` in warnings.

**Triage:**
1. Confirm the leaked content in the output log.
2. Determine whether the leak was in the raw LLM response (before output filter) or in the final response (output filter missed it).

**Response:**
- If raw LLM response contained the leak but output filter caught it: output filter is working. Review why the model leaked the prompt and tighten the system prompt wording.
- If the output filter missed the leak: the system prompt likely has unusual phrasing not covered by the filter. Add the leaked phrase to `SYSTEM_PROMPT_LEAK_PATTERNS`.

**Recovery:** Rotate any sensitive values that were in the system prompt. If the system prompt contained no secrets (recommended: it should not), no further action needed.

---

### LLM06: PII Exposure

**Symptom:** User reports seeing someone else's PII in a response. Or logs show `output_pii:EMAIL` / `output_pii:PHONE` in warnings but the warning was not acted on.

**Triage:**
1. Pull the response from logs (before and after output filter).
2. Determine source: was PII in a retrieved document, in the user's own input, or hallucinated by the model?

**Response:**
- PII from retrieved document: verify that spotlighting is applied. Spotlighting does not prevent PII from appearing in output if the model was asked to extract it. Add an output filter rule for the specific PII type.
- PII from user's own input that leaked into output: verify input redaction is applied before the input enters the prompt. Check `redact_pii()` coverage for the specific pattern.
- Hallucinated PII: this is rare but serious. If the model is generating plausible-looking PII, add a post-output regex scan for PII patterns.

**Recovery:** If another user's PII was exposed, treat as a data breach. Notify your DPO. Document the affected records. Patch the filter before re-enabling the service.

---

### LLM10: Unbounded Consumption / Cost Spike

**Symptom:** Billing alert fires. Hourly cost is 5x normal baseline. Logs show a high volume of requests from a small number of user IDs.

**Triage:**
1. Pull per-user request counts and session costs from the last hour.
2. Identify the top 5 users by cost and request count.
3. Check whether they are legitimate users or anonymous/test accounts.

**Response:**
- If rate limit and cost cap are configured correctly, the exposure is bounded: worst case = rate_limit_rpm * 60 * hours * cost_per_request.
- If the spike exceeded the expected cap, the rate limit may not be shared across workers (see in-memory vs Redis issue in L10 skill).

**Immediate mitigation:**
```python
# Temporarily block the offending user_id at the application layer
BLOCKED_USER_IDS = {"attacker-001", "attacker-002"}

@app.post("/chat")
async def chat(request: Request):
    user_id = request.headers.get("X-User-ID", "anonymous")
    if user_id in BLOCKED_USER_IDS:
        return {"error": "access_denied"}, 403
    ...
```

**Recovery:** Migrate rate limit state from in-memory to Redis if not already done. Lower `session_cost_cap` by 50% temporarily. Re-raise after confirming attack is over.

---

### LLM08: Excessive Agency / Unexpected Tool Use

**Symptom:** Agent performed an action it should not have (wrote to a database, sent an email, called an external API not in the allowed list).

**Triage:**
1. Pull the tool call log for the session.
2. Identify which tool was called and whether it was in `ToolPolicy.allowed_tools`.

**Response:**
- If tool was not in allowed_tools but was called: `validate_tool_call()` was either not called or bypassed. Audit every tool call site.
- If tool was in allowed_tools but performed an unexpected action: the tool's own implementation needs a permission check. Read-only tools should reject write operations.

**Recovery:** Roll back any changes made by the agent (if possible). Update the ToolPolicy to remove the offending tool. Add an integration test that confirms the tool is blocked.

---

## Updating Blocklists

### When to update

- After any confirmed injection attempt (add the injection phrase to moderation)
- After any false positive report (remove or narrow the triggering keyword)
- After a new threat pattern emerges (add to moderation or output filter)
- Weekly review of the top 20 blocked phrases

### How to update

1. Edit `DEFAULT_CATEGORIES` in `main.py` (or your shared config file).
2. Add a comment with the date and reason for the change.
3. Run the edge case test suite: `python main.py --test`.
4. Run your 20-prompt normal traffic sample and confirm false positive rate.
5. Create a PR with the change and the test results.
6. Deploy; monitor warning logs for 24 hours after.

### Never update blocklists by

- Adding overly broad terms (e.g., "kill" blocks legitimate Linux commands)
- Removing terms without confirming the threat is gone
- Skipping the test suite step
- Deploying directly to production without a staging test
