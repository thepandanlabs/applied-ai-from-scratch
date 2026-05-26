---
name: prompt-demo-to-prod-checklist
description: Pre-ship checklist that maps each demo assumption to its production failure mode and required fix
version: "1.0"
phase: "06"
lesson: "01"
tags: [shipping, production, checklist, defensive-engineering]
---

# Demo-to-Production Checklist

Use this checklist before merging any AI feature to a production branch. Each item maps one demo assumption to its production failure mode and the minimum fix required.

---

## How to use

For each item below, answer: "Does our current implementation handle this?" If the answer is no, that gap must be closed before ship. A partial implementation counts as no.

---

## The 8 Gaps

### GAP 1: Input validation

**Demo assumption:** The developer controls the input.

**Production reality:** Users send empty strings, 200,000-character blobs, HTML injection, prompt injection attempts, and non-string types.

**Minimum fix required:**
- [ ] Type check: reject non-string input with a user-safe error
- [ ] Length limit: reject inputs over a documented maximum (e.g., 4,000 chars)
- [ ] Empty check: reject blank or whitespace-only input
- [ ] Injection heuristic: flag inputs that contain "ignore all previous instructions" or similar markers

---

### GAP 2: Configuration validation

**Demo assumption:** The API key and all required environment variables are set.

**Production reality:** Staging and CI environments regularly miss env vars that exist on developer laptops. Missing keys cause silent failures or confusing errors at request time.

**Minimum fix required:**
- [ ] Validate all required env vars at process startup (not per-request)
- [ ] Fail fast with a clear error message that names the missing variable
- [ ] Document all required env vars in a `.env.example` file

---

### GAP 3: Network resilience

**Demo assumption:** API calls complete quickly and reliably.

**Production reality:** APIs return 503, 429, timeout, or hang. A single transient failure should not take down a user request.

**Minimum fix required:**
- [ ] Set an explicit timeout on every API client (e.g., 30 seconds)
- [ ] Retry on `APITimeoutError`, `APIConnectionError`, and 429 with exponential backoff
- [ ] Do not retry on 4xx errors (authentication, validation) -- they are not transient

---

### GAP 4: Concurrency safety

**Demo assumption:** One request runs at a time.

**Production reality:** Web services handle many simultaneous requests. Module-level mutable state (lists, dicts, counters) is shared across all of them.

**Minimum fix required:**
- [ ] No shared mutable state at module level that gets written per-request
- [ ] If state must be shared, use thread-safe primitives (locks, queues) or move to a proper store (Redis, database)
- [ ] Conversation history is per-request or per-session, not global

---

### GAP 5: Output parsing

**Demo assumption:** The model returns exactly the format requested.

**Production reality:** Models wrap JSON in markdown code blocks, add preambles ("Sure, here is the JSON:"), refuse requests, or return partial output when `max_tokens` is hit.

**Minimum fix required:**
- [ ] Strip markdown code fences before parsing JSON (` ```json ... ``` `)
- [ ] Handle `json.JSONDecodeError` and return a structured error instead of crashing
- [ ] Check `finish_reason == "stop"` (not "length") before trusting the output
- [ ] Never call `eval()` on model output

---

### GAP 6: Error containment

**Demo assumption:** Exceptions print to the terminal and the developer sees them.

**Production reality:** Unhandled exceptions become HTTP 500 responses that expose stack traces, file paths, and library versions to users and attackers.

**Minimum fix required:**
- [ ] Every API endpoint has a top-level exception handler
- [ ] Exceptions are logged internally with full context
- [ ] Users receive a safe, generic error message -- never a raw exception type or traceback
- [ ] Error responses use consistent structure: `{"ok": false, "error": "..."}`

---

### GAP 7: Observability

**Demo assumption:** You can see what happened by looking at terminal output.

**Production reality:** Production runs 24/7 without a developer watching. When something fails, you need structured logs to triage without reproducing the failure.

**Minimum fix required:**
- [ ] Log every request with: request ID, model name, input character count
- [ ] Log every success with: request ID, response character count, latency
- [ ] Log every error with: request ID, error type, full stack trace (at ERROR level)
- [ ] Use a structured format (not bare `print()`) so logs are parseable

---

### GAP 8: Graceful degradation

**Demo assumption:** If the API is down, the feature is down.

**Production reality:** A full outage is worse than a degraded experience. Users expect a "try again later" message, not a blank screen or a crash.

**Minimum fix required:**
- [ ] Define a fallback response for every AI feature (a static string, a cached result, or a "temporarily unavailable" message)
- [ ] Return the fallback when the model call fails after retries
- [ ] The fallback is a design decision -- document it and get product sign-off

---

## Ship criteria

A feature is ready to ship when all 8 gaps have a checked implementation. A feature with any unchecked gap is a demo, not a production service.

---

## Prompt for AI-assisted review

Paste this prompt into Claude with your feature code to get a gap analysis:

```
You are a senior applied AI engineer reviewing a feature for production readiness.

Review the attached code against each of these 8 production readiness gaps:

1. Input validation: type check, length limit, empty check, injection heuristics
2. Configuration validation: env vars validated at startup, not per-request
3. Network resilience: timeout set, retry with backoff on transient errors
4. Concurrency safety: no shared mutable state written per-request
5. Output parsing: handles malformed model responses without crashing
6. Error containment: no raw exceptions exposed to users; structured error responses
7. Observability: every request and error has a structured log line
8. Graceful degradation: fallback defined and returned on model failure

For each gap, state: CLOSED (implementation present), PARTIAL (some protection, gaps remain), or OPEN (no implementation).

For each OPEN or PARTIAL gap, write one specific code change that would close it.
```
