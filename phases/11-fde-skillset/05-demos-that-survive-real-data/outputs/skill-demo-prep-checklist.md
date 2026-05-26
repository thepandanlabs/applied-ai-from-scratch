---
name: skill-demo-prep-checklist
description: Pre-demo preparation checklist with the 4 failure modes, 6-step testing protocol, and go/no-go decision criteria
version: "1.0"
phase: "11"
lesson: "05"
tags: [fde, demo, testing, checklist, quality]
---

# Demo Preparation Checklist

Run this checklist before every customer-facing demo. A demo is not ready until the go/no-go section passes.

---

## The 4 Failure Modes (Know What You're Testing For)

```
1. HARDCODED SAMPLES
   Symptom: Works on your test files, fails on customer's first real file.
   Fix: Test on 20+ real customer samples before demo.

2. NO ERROR HANDLING
   Symptom: Crashes or returns garbage on malformed, empty, or edge-case inputs.
   Fix: Explicitly test empty input, minimum/maximum size, unexpected formats.

3. LATENCY CLIFF
   Symptom: Fast on short examples, stalls on long customer documents.
   Fix: Test at the full range of realistic input sizes, not just short ones.

4. OUTPUT FORMAT MISMATCH
   Symptom: Model produces valid output but not in the format customer expected.
   Fix: Confirm expected format with customer before demo, test against it.
```

---

## Step 1: Get Real Customer Data

- [ ] Requested 20-30 real samples from the customer
- [ ] Samples represent the actual distribution (not just easy cases)
- [ ] If real samples unavailable: explicit agreement that demo is on synthetic data

If you are showing synthetic data, say so explicitly:
> "We're demoing on representative synthetic data today. We'll validate on your real data in the next session."

Never show synthetic data as if it were real.

---

## Step 2: Run Failure Rate Test

Run DemoTester on all samples:
```bash
python main.py --samples customer-samples.json --fields [your required fields]
```

- [ ] Failure rate is below 5%
- [ ] All failures are understood and documented (not silent)

If failure rate is above 5%: fix the failures or delay the demo.

**Do not demo with a failure rate above 5%.**

---

## Step 3: Measure Latency Distribution

- [ ] Tested at minimum, median, and maximum realistic input sizes
- [ ] p95 latency is below your requirement (record it: ___ seconds)
- [ ] No latency cliff (no inputs that take 5x+ longer than the median)

If latency cliff exists: test caching, chunking, or async loading before the demo.

---

## Step 4: Verify Output Format with Customer

Before the demo, share a sample output with the customer and ask:
> "Here is an example of what the system produces. Does this match what you expected?"

- [ ] Customer has confirmed the output format
- [ ] All required fields confirmed (names, types, nesting)
- [ ] Handling of null/empty fields confirmed

If format is unconfirmed: do not demo. One email confirmation takes 5 minutes.

---

## Step 5: Test Edge Cases Explicitly

- [ ] Empty input tested (should fail gracefully, not crash)
- [ ] Minimum length input tested
- [ ] Maximum length input tested (your latency cliff check)
- [ ] Input with unexpected characters or encoding tested
- [ ] Input from a different format than your training data tested

---

## Step 6: Demo Rehearsal

- [ ] Full end-to-end demo run completed (not just unit tests)
- [ ] Run on the same laptop you will use in the demo
- [ ] Run on the same network type (if demoing via browser or API)
- [ ] Timed the demo: does it fit the allotted slot?
- [ ] Identified 2-3 inputs you will show (all tested and passing)

---

## Go/No-Go Decision Matrix

| Check | Status | Notes |
|-------|--------|-------|
| Real customer samples obtained | | |
| Failure rate < 5% | | |
| p95 latency < threshold | | |
| No latency cliff | | |
| Output format confirmed by customer | | |
| Edge cases tested | | |
| Full rehearsal completed | | |

**Demo is GO only when all rows are checked.**

Any unchecked row is a blocker. Fix it or explicitly acknowledge the risk in writing before the demo.

---

## Demo Day Backup Plan

Even with perfect prep, things can go wrong. Have a backup:

- [ ] Screenshots of the system working (from your rehearsal run)
- [ ] Pre-recorded screen capture of a successful run
- [ ] 2-3 inputs you are confident will work, ready to paste

If the system fails in front of the customer:
1. Do not apologize repeatedly
2. Say: "Let me show you a run from this morning" (show screenshot/recording)
3. Say: "We'll debug this after the call and follow up within 24 hours"
4. Do not promise it will work "if you just try it again"

---

## Post-Demo Failure Log

If anything went wrong, record it here and fix it before the next demo:

| What happened | Root cause | Fix applied | Verified |
|---------------|------------|-------------|---------|
| | | | |
