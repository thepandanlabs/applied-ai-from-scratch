---
name: runbook-fde-engagement-playbook
description: Complete handoff package for the email triage and auto-response engagement, covering architecture, operations, evaluation baseline, monitoring, and 30/60/90 day success criteria
version: "1.0"
phase: "12"
lesson: "05"
tags: [fde, handoff, runbook, email-triage, operations, capstone]
---

# Handoff Package: Email Triage and Auto-Response System

**Customer:** [B2B SaaS Co - replace with actual customer name]
**FDE:** [Your name]
**Handoff date:** [Date]
**System version:** 1.0
**Go/No-Go decision date:** [Date]
**Go/No-Go evidence:** Golden set evaluation - routine accuracy 92.3%, escalation recall 100%

---

## System Architecture

### What this system does

Receives incoming support emails, classifies them into one of four categories (password_reset, billing, feature_how_to, escalate), generates a draft response for the three routine categories, and routes complex emails to the human support queue without any automated response.

### What this system does NOT do

- Send emails automatically (all draft responses require human review and send)
- Access the CRM or customer account data (context is email body only)
- Handle attachments or images
- Support languages other than English
- Escalate with priority scoring (all escalations enter the same queue)

### Architecture diagram

```
INCOMING EMAIL
     |
     v
[CLASSIFIER]   Claude claude-3-5-haiku-20241022
(single API call, JSON output)
     |
     +---> password_reset  ---> [DRAFT GENERATOR] ---> Agent inbox (draft for review)
     |
     +---> billing         ---> [DRAFT GENERATOR] ---> Agent inbox (draft for review)
     |
     +---> feature_how_to  ---> [DRAFT GENERATOR] ---> Agent inbox (draft for review)
     |
     +---> escalate        ---> [HUMAN QUEUE]     ---> Agent notified, no draft
```

### Dependencies

| Component | Purpose | Contact / docs |
|-----------|---------|----------------|
| Anthropic Claude API | Classification + draft generation | console.anthropic.com |
| Python 3.12 | Runtime | python.org |
| anthropic SDK | API client | pypi.org/project/anthropic |

### Infrastructure

- **Runs on:** [Deployment platform - e.g., fly.io, EC2, Cloud Run]
- **Estimated monthly cost:** ~$15-30/month at 200 emails/day (claude-3-5-haiku-20241022 pricing)
- **Scaling limit:** No hard limit at current volume; review if email volume exceeds 2,000/day
- **API rate limits:** Anthropic standard tier handles 200 emails/day with headroom

### Ownership after handoff

- **System owner:** [Customer tech lead name, role, email]
- **Backup owner:** [Customer backup contact]
- **Escalation to FDE team:** [Your contact and response time commitment]

---

## Operating Instructions

### Starting the system

```bash
# Set the API key
export ANTHROPIC_API_KEY=your_key_here

# Run a single email
python main.py --email "I forgot my password"

# Run demo mode to verify system is working
python main.py --demo

# Run evaluation against golden set
python main.py --demo --eval
```

### Docker deployment

```bash
# Build
docker build -t email-triage .

# Run demo
docker run -e ANTHROPIC_API_KEY=your_key email-triage

# Run eval
docker run -e ANTHROPIC_API_KEY=your_key email-triage python main.py --demo --eval

# Process a single email
docker run -e ANTHROPIC_API_KEY=your_key email-triage \
  python main.py --email "Your email text here" --output-json
```

### Configuration

| Variable | Purpose | Where set | Current value |
|----------|---------|-----------|---------------|
| ANTHROPIC_API_KEY | Claude API authentication | Environment / secrets manager | [contact owner] |
| MODEL | Claude model version | code/main.py line 14 | claude-3-5-haiku-20241022 |

### Health check

Run this to verify the system is working end-to-end:

```bash
python main.py --email "I forgot my password" --output-json
```

Expected healthy output:
```json
{
  "category": "password_reset",
  "confidence": 0.95,
  "reason": "...",
  "routed_to": "automated",
  "draft_response": "..."
}
```

If the API key is invalid or expired, you will see:
```
Error: ANTHROPIC_API_KEY environment variable not set
```
or an `AuthenticationError` from the Anthropic SDK.

---

## Common Failures

### Failure 1: API key expired or invalid

**Symptom:** `AuthenticationError` or `401` in logs; all emails fail to process
**Cause:** API key rotated, expired, or incorrectly set
**Fix:**
1. Log in to console.anthropic.com
2. Generate a new API key under Settings > API Keys
3. Update the environment variable: `export ANTHROPIC_API_KEY=new_key`
4. Restart the service
5. Verify with health check: `python main.py --email "test" --output-json`

### Failure 2: Classification returns wrong category

**Symptom:** Support team notices emails categorized incorrectly; accuracy drops below 85%
**Cause:** Email patterns changed (new product feature, new support topic) or prompt drift
**Fix:**
1. Collect 5-10 examples of misclassified emails
2. Review the CLASSIFICATION_SYSTEM_PROMPT in code/main.py
3. Add clarifying instructions for the new edge cases
4. Run the golden set eval: `python main.py --demo --eval`
5. If accuracy improves and escalation recall stays 100%: deploy update
6. If unsure: contact FDE team before deploying

### Failure 3: Draft response quality degrades

**Symptom:** Support agents rejecting most drafts, editing heavily, or reporting drafts are off-topic
**Cause:** Model behavior change after Anthropic update, or new email topics not covered by prompts
**Fix:**
1. Identify which category has poor quality (password_reset, billing, or feature_how_to)
2. Review the corresponding DRAFT_SYSTEM_PROMPTS entry in code/main.py
3. Add examples of desired response format or specific instructions
4. Test 5 representative emails from that category manually
5. Deploy if quality improves; contact FDE team if problem persists

### Failure 4: Rate limit errors

**Symptom:** `RateLimitError` in logs; emails process slowly or fail during volume spikes
**Cause:** Email volume exceeded API tier limits
**Fix:**
1. Check current API usage at console.anthropic.com > Usage
2. If volume spike is temporary (more than 3x normal): queue emails and retry
3. If sustained growth: upgrade API tier at console.anthropic.com > Plans
4. Short-term mitigation: add `time.sleep(0.5)` between API calls in the processing loop

### Failure 5: Escalation emails receive automated drafts

**Symptom:** A complex or sensitive email received a draft response instead of routing to queue
**Cause:** Critical failure - classifier returned wrong category for escalation case
**Severity:** HIGH - requires immediate investigation
**Fix:**
1. Collect the misclassified email
2. Add it to the GOLDEN_SET in main.py with `expected_category: "escalate"`
3. Update the CLASSIFICATION_SYSTEM_PROMPT to handle this pattern
4. Run golden set eval and verify escalation recall = 100% before redeploying
5. Notify FDE team - this is a go/no-go blocker if it happens more than once

---

## Evaluation Baseline

Run this monthly to verify the system has not drifted from go/no-go performance:

```bash
python main.py --demo --eval --verbose
```

**Baseline results (go/no-go date):**

| Metric | Target | Baseline | 30-day check | 60-day check |
|--------|--------|----------|--------------|--------------|
| Routine accuracy | >= 90% | 92.3% | [fill in] | [fill in] |
| Escalation recall | 100% | 100% | [fill in] | [fill in] |
| Escalation precision | >= 95% | 93.8% | [fill in] | [fill in] |

If any metric drops below target: review recent email samples, update prompts, and re-run eval before continuing production use.

---

## Monitoring Setup

### What to watch (weekly)

1. **Draft acceptance rate:** Percentage of generated drafts sent without major edits
   - Track in your ticket system: tag emails as "draft-accepted" or "draft-edited"
   - Target: >= 70% by day 30

2. **Escalation queue volume:** Number of emails routed to human queue
   - Baseline: ~80/day (40% of 200)
   - Alert if drops below 60 (may indicate over-automation) or above 100 (may indicate under-automation)

3. **Classification distribution:** Weekly count by category
   - Alert if any category jumps more than 20% from baseline (may indicate email pattern change)

4. **API costs:** Check console.anthropic.com > Usage monthly
   - Budget: $30/month at current volume

### Retraining triggers

Update the classification or draft prompts when:
- Draft acceptance rate drops below 60% for 2 consecutive weeks
- Any category accuracy drops below 85% on spot-check of 20 emails
- A new support topic emerges that does not fit existing categories
- Escalation recall drops below 100% on any spot-check

Do NOT update prompts when:
- One agent complained about a single draft
- Volume spikes without quality changes
- Anthropic releases a new model (test first, do not auto-update)

---

## 30/60/90 Day Success Criteria

### 30 days

- [ ] First-response time for automated path: < 2 minutes (measure from email received timestamp)
- [ ] Draft acceptance rate: >= 60% (learning curve expected)
- [ ] Escalation recall verified at 100% via 2-week audit
- [ ] Support team has used the runbook to handle at least 1 incident without FDE help
- [ ] Monthly eval run completed, results documented in the baseline table above

### 60 days

- [ ] Draft acceptance rate: >= 70%
- [ ] Support team volume: automated path handling 55-65% of all emails
- [ ] No FDE intervention required for prompt updates (team handles independently)
- [ ] API cost within $5 of monthly budget estimate
- [ ] First prompt update deployed by customer team using the runbook

### 90 days

- [ ] Draft acceptance rate: >= 75%
- [ ] First-response time: <= 10 minutes average across all email types (automated + manual)
- [ ] Team can articulate: what to check when accuracy drops, how to update a prompt, when to escalate to FDE
- [ ] System has operated without FDE involvement for 30+ consecutive days
- [ ] Go/No-Go decision revisited with 90-day data: confirm the system is delivering the business case

---

## Escalation Contacts

| Name | Role | Contact | Response time |
|------|------|---------|---------------|
| [Customer tech lead] | System owner | [email] | 4 hours (business hours) |
| [FDE name] | Original engineer | [email] | 24 hours / 4 hours for P0 |
| Anthropic support | API issues | console.anthropic.com/support | Per support tier |

**What to include in an FDE escalation:**
- Symptom: what is broken or degraded
- When it started: timestamp
- Email volume affected: number of emails impacted
- What you tried: steps from this runbook
- Eval results: paste the output of `python main.py --demo --eval`
- Sample emails: 3-5 representative examples of the problem

---

## Pre-Handoff Verification Checklist

- [ ] All four documents complete (system overview, runbook, prompt change guide, escalation path)
- [ ] Health check runs successfully in production environment
- [ ] Golden set eval runs and matches baseline
- [ ] Customer tech lead has run the health check independently
- [ ] Customer tech lead has simulated one common failure using this runbook
- [ ] API key is in secrets manager, not hardcoded
- [ ] 30-day check date is calendared
