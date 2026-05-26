---
name: skill-prompt-injection-defense
description: Code review checklist for identifying prompt injection vulnerabilities in LLM agents
version: "1.0"
phase: "08"
lesson: "02"
tags: [security, prompt-injection, agent, code-review, checklist]
---

# Prompt Injection Defense Checklist

Use this during code review for any agent that processes external content. Takes 5 minutes. Run it before every agent ships.

---

## 1. Identify the Injection Surfaces

Mark each surface present in this agent:

- [ ] User turn: user can supply free-form text
- [ ] Retrieved content: agent reads documents, web pages, emails, DB rows, or search results
- [ ] Tool outputs: agent processes responses from external APIs, scrapers, or data sources
- [ ] Cross-modal: agent processes images (alt text), audio (transcripts), or structured data

Any surface marked is an injection vector. At least one defense must be applied to each.

---

## 2. Direct Injection (User Turn)

- [ ] Input filtering applied to user turn before model call
- [ ] Known injection patterns checked (see `code/main.py` INJECTION_PATTERNS)
- [ ] User input length bounded (no unbounded context stuffing)
- [ ] Refusal behavior defined and tested for detected injection attempts

---

## 3. Indirect Injection (Retrieved Content)

- [ ] Detection heuristics applied to retrieved chunks before they enter the prompt
- [ ] OR: retrieved content is processed by a sandboxed model (no tools) before the action-capable model sees it
- [ ] Suspicious retrieved content is logged (not silently dropped) for security review
- [ ] Documents in the retrieval index have a known provenance (who can write to the index?)

---

## 4. Cross-Modal and Tool Output Injection

- [ ] Tool outputs are treated as untrusted data, not trusted instructions
- [ ] Web scraping / external API tool outputs are sandboxed before feeding to action-capable model
- [ ] Image processing pipeline does not pass raw alt text or OCR output directly as instructions
- [ ] Audio transcription output is treated as user content, not system content

---

## 5. Blast Radius Audit

For each tool the agent has, fill in the worst-case injection scenario:

| Tool | What can injection trigger? | Acceptable? | Mitigation |
|------|---------------------------|-------------|------------|
| | | | |
| | | | |

If any tool's worst-case blast radius is unacceptable (email sends, deletes records, calls external APIs), one of these mitigations is required:
- Human-in-the-loop confirmation step before the tool fires
- Dual-LLM pattern: sandboxed model processes retrieved content, action model acts on cleaned summary only
- Remove the tool and redesign the feature without LLM agency

---

## 6. Defense Patterns Applied

Mark which defenses are in place:

- [ ] Input sanitization: strip or encode known injection markers in user input
- [ ] Spotlighting: untrusted content is wrapped in delimiters (`<document>`, `<tool_output>`) so the model can distinguish data from instructions
- [ ] Sandboxing: model that processes untrusted content has no tools
- [ ] Allow-list: model is only permitted to call specific tools, in specific ways, with specific argument shapes
- [ ] Dual-LLM: sandboxed model summarizes untrusted input, action model acts on summary only
- [ ] Output validation: model output is checked before any tool calls are executed

---

## 7. Test Coverage

- [ ] Direct injection test case exists (user turn override attempt)
- [ ] Indirect injection test case exists (malicious document in retrieval pipeline)
- [ ] Clean document test case exists (no false positives)
- [ ] Bypass attempt test case exists (reworded injection, no regex match)
- [ ] Tests run in CI

---

## Red Flags That Require Escalation

Stop the review and escalate if any of these are true:

- Agent has a `send_email` or `send_message` tool AND processes user-supplied documents with no sandboxing
- Agent can write to a database or file system AND retrieves content from the open web
- Agent has a tool that calls external APIs with authentication AND there is no output validation before the tool fires
- System prompt contains API keys, passwords, or internal URLs
- No injection test cases exist and the agent processes external content

---

## Usage

Run before every agent code review. Copy the checklist into the PR review comment. Every unchecked box is a finding. Every red flag is a blocker.
