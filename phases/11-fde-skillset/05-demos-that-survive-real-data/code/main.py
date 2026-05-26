#!/usr/bin/env python3
"""
DemoTester

Runs a demo function against a sample dataset and reports:
- Failure rate (success/exception)
- Latency distribution (p50, p95, p99, max)
- Output format consistency (required fields present)
- Demo readiness go/no-go

Usage:
    python main.py --samples contracts.json --fields contract_date,party_a,party_b
    python main.py --demo           # Run the built-in mock extraction demo
"""
import json
import sys
import time
import argparse
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import anthropic

MODEL = "claude-3-5-haiku-20241022"


# --- DemoTester core ---

@dataclass
class SampleResult:
    index: int
    success: bool
    latency_s: float
    output: Any
    error: Optional[str] = None
    missing_fields: list[str] = field(default_factory=list)


@dataclass
class DemoReport:
    total: int
    results: list[SampleResult]
    expected_fields: list[str]
    latency_threshold_p95: float
    failure_rate_threshold: float

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def failure_rate(self) -> float:
        return 1.0 - (self.success_count / self.total) if self.total else 1.0

    @property
    def latencies(self) -> list[float]:
        return [r.latency_s for r in self.results if r.success]

    @property
    def p50(self) -> float:
        lats = sorted(self.latencies)
        return lats[len(lats) // 2] if lats else 0.0

    @property
    def p95(self) -> float:
        lats = sorted(self.latencies)
        idx = max(0, int(len(lats) * 0.95) - 1)
        return lats[idx] if lats else 0.0

    @property
    def p99(self) -> float:
        lats = sorted(self.latencies)
        idx = max(0, int(len(lats) * 0.99) - 1)
        return lats[idx] if lats else 0.0

    @property
    def max_latency(self) -> float:
        return max(self.latencies) if self.latencies else 0.0

    @property
    def format_pass_rate(self) -> float:
        if not self.expected_fields:
            return 1.0
        passing = sum(1 for r in self.results if r.success and not r.missing_fields)
        return passing / self.total if self.total else 0.0

    @property
    def missing_field_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.results:
            for f in r.missing_fields:
                counts[f] = counts.get(f, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    @property
    def latency_cliff_samples(self) -> list[int]:
        cliff = self.max_latency * 0.5
        return [r.index for r in self.results if r.success and r.latency_s > cliff and r.latency_s > 5.0]


class DemoTester:
    def __init__(
        self,
        demo_fn: Callable[[Any], Any],
        expected_fields: Optional[list[str]] = None,
        latency_threshold_p95: float = 5.0,
        failure_rate_threshold: float = 0.05,
    ):
        self.demo_fn = demo_fn
        self.expected_fields = expected_fields or []
        self.latency_threshold_p95 = latency_threshold_p95
        self.failure_rate_threshold = failure_rate_threshold

    def _check_fields(self, output: Any) -> list[str]:
        """Return list of missing required fields."""
        if not self.expected_fields:
            return []
        if not isinstance(output, dict):
            return list(self.expected_fields)
        return [f for f in self.expected_fields if f not in output or output[f] is None]

    def run(self, samples: list[Any]) -> DemoReport:
        results = []
        for i, sample in enumerate(samples):
            start = time.perf_counter()
            try:
                output = self.demo_fn(sample)
                latency = time.perf_counter() - start
                missing = self._check_fields(output)
                results.append(SampleResult(
                    index=i,
                    success=True,
                    latency_s=round(latency, 3),
                    output=output,
                    missing_fields=missing,
                ))
            except Exception as e:
                latency = time.perf_counter() - start
                results.append(SampleResult(
                    index=i,
                    success=False,
                    latency_s=round(latency, 3),
                    output=None,
                    error=str(e),
                ))
        return DemoReport(
            total=len(samples),
            results=results,
            expected_fields=self.expected_fields,
            latency_threshold_p95=self.latency_threshold_p95,
            failure_rate_threshold=self.failure_rate_threshold,
        )

    def print_report(self, report: DemoReport) -> None:
        print("\n" + "=" * 55)
        print("DEMO TEST REPORT")
        print("=" * 55)

        # Success rate
        print(f"\nSamples tested: {report.total}")
        pct = (1 - report.failure_rate) * 100
        print(f"Success rate:   {pct:.1f}% ({report.success_count}/{report.total} passed)")
        failures = [r for r in report.results if not r.success]
        if failures:
            failed_ids = ", ".join(f"#{r.index}" for r in failures)
            print(f"  Failed samples: {failed_ids}")
            for r in failures[:3]:
                print(f"    #{r.index}: {r.error}")

        # Latency
        if report.latencies:
            print(f"\nLatency:")
            print(f"  p50:  {report.p50:.2f}s")
            p95_flag = " [!] WARNING: p95 above threshold" if report.p95 > report.latency_threshold_p95 else ""
            print(f"  p95:  {report.p95:.2f}s{p95_flag}")
            print(f"  p99:  {report.p99:.2f}s")
            cliff = report.latency_cliff_samples
            max_flag = f"  [!] LATENCY CLIFF: {len(cliff)} slow samples" if cliff else ""
            print(f"  Max:  {report.max_latency:.2f}s{max_flag}")
            if cliff:
                print(f"    Slow samples: {', '.join(f'#{i}' for i in cliff)}")

        # Output format
        if report.expected_fields:
            print(f"\nOutput format:")
            format_pct = report.format_pass_rate * 100
            print(f"  All required fields present: {format_pct:.1f}% ({int(report.format_pass_rate * report.total)}/{report.total} samples)")
            for field_name, count in report.missing_field_counts.items():
                print(f"    {field_name}: missing in {count} sample{'s' if count > 1 else ''}")

        # Go/no-go
        issues = []
        warnings = []

        if report.failure_rate > report.failure_rate_threshold:
            issues.append(
                f"Failure rate {report.failure_rate * 100:.1f}% exceeds {report.failure_rate_threshold * 100:.0f}% threshold."
            )

        if report.p95 > report.latency_threshold_p95:
            issues.append(
                f"p95 latency ({report.p95:.2f}s) exceeds threshold ({report.latency_threshold_p95:.1f}s)."
            )
        elif report.p95 > report.latency_threshold_p95 * 0.8:
            warnings.append(f"p95 latency ({report.p95:.2f}s) near threshold ({report.latency_threshold_p95:.1f}s).")

        cliff = report.latency_cliff_samples
        if cliff:
            warnings.append(f"{len(cliff)} samples show latency cliff (>5s). Check longest inputs.")

        if report.expected_fields:
            bad_format = 1 - report.format_pass_rate
            if bad_format > 0.10:
                issues.append(
                    f"Output format incomplete in {bad_format * 100:.0f}% of samples."
                )

        print("\nDEMO READINESS:")
        if not issues and not warnings:
            print("  [PASS] Demo is ready.")
        else:
            for issue in issues:
                print(f"  [FAIL] {issue}")
            for warning in warnings:
                print(f"  [WARN] {warning}")

        if issues:
            print("\nACTION ITEMS (resolve before demo):")
            for i, issue in enumerate(issues, 1):
                print(f"  {i}. {issue}")


# --- Mock demo for demonstration ---

_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def extract_contract_fields(document_text: str) -> dict:
    """Mock extraction demo: extract fields from a contract using Claude."""
    if not document_text or not document_text.strip():
        raise ValueError("Empty document")

    response = get_client().messages.create(
        model=MODEL,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": f"""Extract these fields from the contract as JSON.
If a field is not present, use null.

Fields: contract_date, party_a, party_b, total_value, duration

Contract text:
{document_text[:3000]}

Return only valid JSON, no explanation.""",
            }
        ],
    )
    raw = response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


MOCK_SAMPLES = [
    "This Agreement is entered into on January 15, 2024 between Acme Corp ('Party A') and Globex Ltd ('Party B'). Total value: $50,000. Duration: 12 months.",
    "SERVICE AGREEMENT dated March 1, 2024. Vendor: TechCo Inc. Client: RetailGroup LLC. Contract value: $12,500.00. Term: 6 months from execution.",
    "Consulting Agreement - February 28, 2024. Consultant: Jane Smith. Company: StartupXYZ. Monthly fee: $5,000. Duration: 3 months.",
    "MASTER SERVICES AGREEMENT\nThis MSA is effective April 10, 2024.\nService Provider: CloudSystems Corp.\nCustomer: MegaRetail Inc.\nAnnual value: $240,000.\nInitial term: 2 years.",
    "Agreement between Alpha Corp and Beta LLC. Signed 2024-05-01. Amount: one hundred thousand dollars ($100,000). Period: eighteen (18) months.",
    # Edge cases
    "",  # Empty - should fail
    "Just some random text with no contract information.",  # No fields
    "Short contract. Party A: X Corp. Party B: Y Inc. Date: 2024-06-01. $1,000. 1 month.",
]


def run_mock_demo() -> None:
    print("Running DemoTester on mock contract extraction demo...")
    print(f"Testing {len(MOCK_SAMPLES)} samples (including edge cases)\n")

    tester = DemoTester(
        demo_fn=extract_contract_fields,
        expected_fields=["contract_date", "party_a", "party_b", "total_value", "duration"],
        latency_threshold_p95=8.0,
        failure_rate_threshold=0.15,  # relaxed for demo purposes
    )
    report = tester.run(MOCK_SAMPLES)
    tester.print_report(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="DemoTester CLI")
    parser.add_argument("--samples", metavar="FILE", help="JSON file with array of sample inputs")
    parser.add_argument("--fields", metavar="FIELDS", help="Comma-separated list of required output fields")
    parser.add_argument("--latency-threshold", type=float, default=5.0, metavar="SECONDS", help="p95 latency threshold in seconds")
    parser.add_argument("--failure-threshold", type=float, default=0.05, metavar="RATE", help="Maximum acceptable failure rate (0.0-1.0)")
    parser.add_argument("--output", metavar="FILE", help="Export report to JSON")
    parser.add_argument("--demo", action="store_true", help="Run the built-in mock extraction demo")
    args = parser.parse_args()

    if args.demo:
        run_mock_demo()
        return

    if not args.samples:
        parser.print_help()
        sys.exit(0)

    with open(args.samples) as f:
        samples = json.load(f)

    if not isinstance(samples, list):
        print("Error: samples file must contain a JSON array.", file=sys.stderr)
        sys.exit(1)

    fields = [f.strip() for f in args.fields.split(",")] if args.fields else []

    tester = DemoTester(
        demo_fn=extract_contract_fields,
        expected_fields=fields,
        latency_threshold_p95=args.latency_threshold,
        failure_rate_threshold=args.failure_threshold,
    )

    report = tester.run(samples)
    tester.print_report(report)

    if args.output:
        data = {
            "total": report.total,
            "success_count": report.success_count,
            "failure_rate": report.failure_rate,
            "latency": {
                "p50": report.p50,
                "p95": report.p95,
                "p99": report.p99,
                "max": report.max_latency,
            },
            "format_pass_rate": report.format_pass_rate,
            "missing_fields": report.missing_field_counts,
        }
        with open(args.output, "w") as f:
            json.dump(data, f, indent=2)
        print(f"\nReport exported to {args.output}")


if __name__ == "__main__":
    main()
