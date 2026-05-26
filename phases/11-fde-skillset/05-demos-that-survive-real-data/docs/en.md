# Demos That Survive Real Data

> A demo that works on 3 hand-picked examples and fails on the customer's first real file is worse than no demo.

**Type:** Build
**Languages:** Python
**Prerequisites:** 11-02 Scoping Before Solving, Phase 05 (Evaluation basics)
**Time:** ~60 min
**Phase:** 11 - FDE Skillset

## Learning Objectives

- Name the 4 demo failure modes and explain how each one manifests
- Build a DemoTester class that runs a demo function against a sample dataset and reports failure rate, latency, and output format consistency
- Apply the DemoTester to a mock extraction demo before a customer presentation
- Create a pre-demo testing protocol using the checklist artifact
- Explain why testing on 20+ real customer samples is non-negotiable before a demo

---

## The Problem

It's demo day. You've built a document extraction system that pulls key fields from contract PDFs. In your test environment, it works perfectly on the 3 sample contracts you used during development. The demo runs. On the first contract the customer uploads from their own system, the model outputs an empty JSON object. The second contract causes a KeyError. The third takes 45 seconds because it's 60 pages long and you never tested on long documents.

The demo is over. The customer is polite but the energy has shifted. They say they'd like to "see it again when it's more stable." You don't get a second first impression.

This scenario is the most preventable demo failure in AI engineering. The fix is not writing better code. The fix is testing on real customer data, at realistic input sizes, before you walk into the demo room. The DemoTester exists so this never happens to you.

---

## The Concept

### The 4 Demo Failure Modes

```
FAILURE MODE        WHAT IT LOOKS LIKE              DETECTION METHOD
------------------  ------------------------------  -----------------------
Hardcoded samples   Works on your 3 test files,     Run on 20+ real customer
                    fails on customer's first file  samples before demo

No error handling   Crashes on malformed input,     Test with malformed,
                    empty files, or unexpected      empty, and edge-case
                    formats                         inputs explicitly

Latency cliff       Fast on your short examples,    Measure latency on the
                    stalls or times out on long     full distribution of
                    customer documents              realistic input sizes

Output format       Model produces valid output     Ask customer to confirm
mismatch            but not in the format the       expected format before
                    customer expected               demo, test against it
```

Each failure mode has a specific test that catches it before the demo. The DemoTester runs all four.

### The Pre-Demo Testing Protocol

```
Step 1: GET REAL DATA (at least 20 samples)
  - Ask customer: "Can you share 20-30 real examples from your system?"
  - If they can't: ask for anonymized or redacted versions
  - If they won't: be explicit that the demo will be on synthetic data

Step 2: RUN FAILURE RATE TEST
  - Run your demo function on all 20+ samples
  - Target: failure rate below 5% before demo
  - If above 5%: fix the failures or delay the demo

Step 3: MEASURE LATENCY DISTRIBUTION
  - Run on samples at the realistic size range (not just short ones)
  - Target: p95 latency below your requirement (typically 2-10s)
  - If above: test caching, chunking, or async approaches

Step 4: VERIFY OUTPUT FORMAT
  - Confirm with customer: "Here is the output format the system produces.
    Is this what you expected?"
  - Check field names, data types, nesting
  - Test that your parsing code handles empty fields, null values

Step 5: TEST EDGE CASES EXPLICITLY
  - Empty input
  - Minimum length input
  - Maximum length input (your latency cliff)
  - Input with unexpected characters or encoding

Step 6: REHEARSE
  - Do one full demo run with the customer's actual data before demo day
  - Use the same laptop and network you will use in the demo
```

---

## Build It

Build a `DemoTester` class that runs a demo function against a sample dataset and produces a test report covering failure rate, latency distribution, and output format consistency.

The tester accepts any callable as the demo function, runs it against a list of test inputs, and measures:
- Success rate (function returns without exception)
- Latency per call (p50, p95, p99)
- Output format consistency (presence of expected fields)

```python
from demo_tester import DemoTester

# Define what your demo function does
def my_extraction_demo(document_text: str) -> dict:
    # your LLM call here
    ...

# Define what a valid output looks like
expected_fields = ["contract_date", "party_a", "party_b", "total_value", "duration"]

# Run the tester
tester = DemoTester(
    demo_fn=my_extraction_demo,
    expected_fields=expected_fields,
    latency_threshold_p95=5.0,  # seconds
)
report = tester.run(samples=my_20_real_samples)
tester.print_report(report)
```

Sample output:

```
=== DEMO TEST REPORT ===

Samples tested: 24
Success rate:   87.5% (21/24 passed)
  Failed samples: #8, #15, #22

Latency:
  p50:  1.2s
  p95:  4.8s
  p99:  12.3s  [!] WARNING: p95 is near threshold (5.0s)
  Max:  18.7s  [!] LATENCY CLIFF: 3 samples over 10s (samples #14, #19, #23)

Output format:
  All required fields present: 83.3% (20/24 samples)
  Missing fields by frequency:
    contract_date: missing in 4 samples
    total_value:   missing in 1 sample

DEMO READINESS:
  [FAIL] Failure rate 12.5% exceeds 5% threshold.
  [WARN] p95 latency (4.8s) near threshold (5.0s).
  [WARN] 3 samples cause latency cliff (over 10s). Check if demo inputs include long documents.
  [FAIL] Output format incomplete in 4 samples (contract_date missing).

ACTION ITEMS (before demo):
  1. Investigate failures in samples #8, #15, #22.
  2. Fix or handle missing contract_date extraction.
  3. Test longest customer documents to understand latency cliff.
  4. Do not demo until failure rate is below 5%.
```

The `DEMO READINESS` section gives a go/no-go signal. A demo is not ready if failure rate exceeds 5% or required fields are missing in more than 10% of samples.

> **Real-world check:** You run DemoTester and get a 12.5% failure rate, 3 days before the demo. You investigate and find all 3 failures are on contracts with non-standard headers. You have two options: fix the parser to handle non-standard headers, or filter these samples out of the demo and only show contracts that work. Which is right? Fix the parser if you can do it in 2 days. If you cannot, have an explicit conversation with the customer: "We've identified a category of document that the current version handles less reliably. We'll show you the cases where it works well today and address the edge cases in the next iteration." Hiding the failures by cherry-picking demo inputs is the wrong move. The customer will find them after the demo.

The full implementation is in `code/main.py`. It includes the `DemoTester` class, a mock extraction demo function for testing, and a command-line interface for running the tester against a JSON dataset.

---

## Use It

Apply the DemoTester to a mock contract extraction demo.

Define a mock demo function that extracts fields from contract text using Claude:

```python
import anthropic

client = anthropic.Anthropic()

def extract_contract_fields(document_text: str) -> dict:
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""Extract these fields from the contract as JSON:
contract_date, party_a, party_b, total_value, duration

Contract:
{document_text}

Return only valid JSON."""
        }]
    )
    import json
    return json.loads(response.content[0].text)
```

Build a small test dataset with 20+ realistic samples including edge cases:

```python
SAMPLES = [
    # Normal contracts
    "This Agreement is entered into on January 15, 2024...",
    # Short contracts (edge case)
    "Service agreement. Party A: Acme Corp. Party B: Globex. Amount: $5,000.",
    # Long contracts (latency cliff test)
    "MASTER SERVICE AGREEMENT\n" + "..." * 2000,
    # Malformed input
    "",
    # Non-standard format
    "CONTRATO DE SERVICIOS\nFecha: 15 enero 2024...",
]

tester = DemoTester(
    demo_fn=extract_contract_fields,
    expected_fields=["contract_date", "party_a", "party_b", "total_value", "duration"],
    latency_threshold_p95=5.0,
    failure_rate_threshold=0.05,
)
report = tester.run(SAMPLES)
tester.print_report(report)
```

Run it:
```bash
python main.py --samples contracts.json --fields contract_date,party_a,party_b,total_value
```

The tester reveals which inputs fail, where the latency cliff is, and which fields are inconsistently extracted. Fix the failures, then run again. Repeat until the demo readiness check passes.

> **Perspective shift:** A QA engineer reading this might recognize it as a test suite. An FDE would add one thing the QA engineer might not: the concept of "demo readiness" as a binary gate. Unit tests check correctness in isolation. The DemoTester checks production-proxy behavior: failure rate on realistic inputs, latency at realistic sizes, format consistency against customer expectations. A passing unit test suite does not guarantee a passing demo. The DemoTester is the specific check between "code works in my environment" and "demo works in front of a customer."

---

## Ship It

The reusable artifact for this lesson is `outputs/skill-demo-prep-checklist.md`: a pre-demo preparation checklist with the 4 failure modes, the 6-step testing protocol, and a go/no-go decision matrix. Run through it before every customer-facing demo.

---

## Evaluate It

How to know the demo prep process is working:

1. **Demo pass rate** - the clearest signal. Track what percentage of demos run without a system failure in front of the customer. Target: 100%. Any in-demo failure is a preventable event if the pre-demo testing protocol was followed.

2. **DemoTester failure rate at time of demo** - record the failure rate reported by DemoTester on the day before the demo. If demos are consistently run with failure rates above 5%, the protocol is being skipped. Target: all demos run with failure rate below 5%.

3. **Latency surprises in demo** - track cases where the demo experienced latency the customer noticed (stalls, timeouts). Each instance represents a latency cliff that the pre-demo protocol should have caught. Root cause: either DemoTester wasn't run, or realistic input sizes weren't tested.

4. **Post-demo output format feedback** - "that's not the format we expected" is a preventable comment. Track frequency. Each occurrence means the output format confirmation step (Step 4 in the protocol) was skipped. Target: zero post-demo format surprises.
