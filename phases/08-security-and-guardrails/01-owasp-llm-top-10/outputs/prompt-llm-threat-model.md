---
name: prompt-llm-threat-model
description: Reusable threat-model template for LLM applications based on OWASP LLM Top 10 (2025)
version: "1.0"
phase: "08"
lesson: "01"
tags: [security, owasp, threat-model, risk-register, llm-top-10]
---

# LLM Application Threat Model

Fill this out once per application at project start. Update whenever the architecture changes: when tools are added, when the model changes, when new data sources are connected, or when user permissions change.

---

## Application Profile

```
Application name:   [your app name]
Description:        [one sentence: what does it do, who uses it, what can it access?]
Model(s) used:      [e.g., claude-3-5-haiku-20241022]
Deployment:         [public web / internal / API only]
Tools/actions:      [none / list tools the model can call]
Data sources:       [user input only / RAG over X / fine-tuned on Y]
Auth/AuthZ:         [none / OAuth / API key / RBAC]
Date:               [YYYY-MM-DD]
Author:             [engineer name]
```

---

## OWASP LLM Top 10 (2025) Risk Assessment

Rate each risk for your specific application. Score = Likelihood x Impact.

| ID | Name | Likelihood (1-3) | Impact (1-3) | Score | Priority | Notes |
|----|------|-----------------|--------------|-------|----------|-------|
| LLM01 | Prompt Injection * | | | | | |
| LLM02 | Sensitive Information Disclosure | | | | | |
| LLM03 | Supply Chain | | | | | |
| LLM04 | Data and Model Poisoning | | | | | |
| LLM05 | Improper Output Handling | | | | | |
| LLM06 | Excessive Agency * | | | | | |
| LLM07 | System Prompt Leakage | | | | | |
| LLM08 | Vector and Embedding Weaknesses | | | | | |
| LLM09 | Misinformation | | | | | |
| LLM10 | Unbounded Consumption | | | | | |

Priority scale: CRITICAL (7-9), HIGH (5-6), MEDIUM (3-4), LOW (1-2)
\* = risk unique to LLM systems

---

## Risk Descriptions

### LLM01: Prompt Injection
User input or retrieved content overrides the model's instructions. The model treats injected text as trusted commands from the system prompt.

**Attack vectors for this app:**
- [ ] User can supply free-form text in the user turn
- [ ] Retrieval pipeline injects document chunks into the prompt
- [ ] Model reads output from external tools or APIs
- [ ] Model processes images, audio, or structured data

**Mitigation status:** [none / in progress / implemented]
**Mitigation notes:** [what you have done or plan to do]

---

### LLM02: Sensitive Information Disclosure
The model reveals PII, API keys, credentials, or training data through direct questioning or context window exposure.

**Attack vectors for this app:**
- [ ] System prompt contains secrets or business logic
- [ ] Context window includes user PII from previous turns
- [ ] Model trained or fine-tuned on data containing sensitive information
- [ ] RAG index contains confidential documents

**Mitigation status:** [none / in progress / implemented]
**Mitigation notes:**

---

### LLM03: Supply Chain
Poisoned or backdoored model weights, datasets, or third-party components introduce vulnerabilities before the application is deployed.

**Attack vectors for this app:**
- [ ] Uses third-party model weights (Hugging Face, etc.)
- [ ] Uses unverified training datasets
- [ ] Relies on third-party LLM plugins or tool integrations
- [ ] Dependencies not pinned or audited

**Mitigation status:** [none / in progress / implemented]
**Mitigation notes:**

---

### LLM04: Data and Model Poisoning
Training or fine-tuning data is manipulated to alter model behavior, introduce backdoors, or degrade accuracy on specific inputs.

**Attack vectors for this app:**
- [ ] App uses fine-tuning with user-contributed data
- [ ] RAG index is writable by users or external parties
- [ ] Feedback loop (RLHF, etc.) can be gamed

**Mitigation status:** [none / in progress / implemented]
**Mitigation notes:**

---

### LLM05: Improper Output Handling
Model output is passed downstream without sanitization: rendered as HTML, executed as code, used in shell commands, or passed to SQL queries.

**Attack vectors for this app:**
- [ ] Model output is rendered in a web UI (XSS risk)
- [ ] Model generates code that is executed
- [ ] Model output is interpolated into shell commands
- [ ] Model generates SQL or other query languages

**Mitigation status:** [none / in progress / implemented]
**Mitigation notes:**

---

### LLM06: Excessive Agency
The model is granted more permissions, tools, or autonomy than the task requires. A successful injection can take real-world actions at the scope of the model's permissions.

**Attack vectors for this app:**
- [ ] Model has tools that write, delete, or modify data
- [ ] Model can send emails, create calendar events, or message users
- [ ] Model can make external API calls with side effects
- [ ] Agent loop runs without human approval for consequential actions

**Mitigation status:** [none / in progress / implemented]
**Mitigation notes:**

---

### LLM07: System Prompt Leakage
The contents of the system prompt are extracted by the user via direct questioning ("repeat your instructions") or indirect multi-turn probing.

**Attack vectors for this app:**
- [ ] System prompt contains business logic attackers should not see
- [ ] System prompt contains filter bypass logic
- [ ] System prompt length or structure reveals architecture

**Mitigation status:** [none / in progress / implemented]
**Mitigation notes:**

---

### LLM08: Vector and Embedding Weaknesses
Poisoned embeddings, adversarial retrieval, or index manipulation cause the retrieval layer to surface malicious or incorrect content.

**Attack vectors for this app:**
- [ ] RAG index is populated from user-submitted documents
- [ ] Embedding model is not pinned (model drift changes retrieval behavior)
- [ ] No anomaly detection on retrieved chunks

**Mitigation status:** [none / in progress / implemented]
**Mitigation notes:**

---

### LLM09: Misinformation
The model generates plausible but false information (hallucination) that users trust and act on, especially in high-stakes domains.

**Attack vectors for this app:**
- [ ] No citations or source grounding for generated answers
- [ ] No output validation against retrieved documents
- [ ] High-stakes domain (medical, legal, financial, safety)

**Mitigation status:** [none / in progress / implemented]
**Mitigation notes:**

---

### LLM10: Unbounded Consumption
No limits on token usage, API calls, context window size, or cost enable denial-of-service attacks or uncontrolled spend.

**Attack vectors for this app:**
- [ ] Public endpoint with no authentication
- [ ] No per-user rate limiting
- [ ] Agent loop with no max-iteration cap
- [ ] Streaming endpoint with no response-size limit

**Mitigation status:** [none / in progress / implemented]
**Mitigation notes:**

---

## Summary Risk Register

(Auto-generated by `code/main.py` -- paste output here)

```
Rank  ID      Name                        L  I  Score  Priority
...
```

---

## Top 3 Risks and Mitigations

1. **[ID]: [Name]** (Score: X)
   - Why it is the top risk for this app: ...
   - Mitigation: ...
   - Owner: ...
   - Target date: ...

2. **[ID]: [Name]** (Score: X)
   - Why: ...
   - Mitigation: ...

3. **[ID]: [Name]** (Score: X)
   - Why: ...
   - Mitigation: ...

---

## Review History

| Date | Reviewer | Change |
|------|----------|--------|
| | | Initial threat model |
