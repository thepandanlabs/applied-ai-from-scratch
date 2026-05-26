"""
Lesson 01-07: Validation + Retry Loops: Pydantic
===================================================
Demonstrates the retry-with-feedback pattern for structured extraction:

  1. Extract using tool_use
  2. Validate with Pydantic
  3. On failure: append the validation error to the conversation and retry
  4. Compare against blind retry (same prompt, no error feedback)

The key insight: feeding the validation error back to the model is 2-3x
more effective than retrying with the same prompt because the model knows
exactly which field failed and why.

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    python main.py
"""

import anthropic
import os
import json
from pydantic import BaseModel, field_validator, model_validator
from typing import Literal

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-3-5-haiku-20241022"

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RiskFinding(BaseModel):
    """A single risk identified in a security assessment."""
    title: str
    severity: Literal["low", "medium", "high", "critical"]
    likelihood: float  # 0.0 to 1.0
    affected_component: str

    @field_validator("likelihood")
    @classmethod
    def likelihood_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(
                f"likelihood must be between 0.0 and 1.0, got {v}. "
                "Express as a decimal (0.75 = 75%), not as a percentage (75)."
            )
        return v


class RiskAssessment(BaseModel):
    """Structured risk assessment extracted from a security report."""
    asset_name: str
    assessment_date: str
    overall_risk_score: float  # 0.0 to 1.0
    findings: list[RiskFinding]
    recommended_action: Literal["monitor", "remediate", "escalate", "accept"]
    reviewer: str

    @field_validator("overall_risk_score")
    @classmethod
    def risk_score_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(
                f"overall_risk_score must be between 0.0 and 1.0, got {v}. "
                "Use decimal notation: 0.75 not 75."
            )
        return v

    @model_validator(mode="after")
    def findings_not_empty(self) -> "RiskAssessment":
        if not self.findings:
            raise ValueError("findings must contain at least one risk finding")
        return self


# ---------------------------------------------------------------------------
# Extraction tool schema
# ---------------------------------------------------------------------------

RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "asset_name": {"type": "string", "description": "Name of the system or asset being assessed"},
        "assessment_date": {"type": "string", "description": "Date of assessment in YYYY-MM-DD format"},
        "overall_risk_score": {
            "type": "number",
            "description": "Numeric risk score from 0.0 (no risk) to 1.0 (maximum risk). "
                           "IMPORTANT: use decimal notation - write 0.75 not 75.",
        },
        "findings": {
            "type": "array",
            "description": "List of identified risk findings",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "likelihood": {
                        "type": "number",
                        "description": "Likelihood from 0.0 to 1.0. Write 0.75 not 75.",
                    },
                    "affected_component": {"type": "string"},
                },
                "required": ["title", "severity", "likelihood", "affected_component"],
            },
        },
        "recommended_action": {
            "type": "string",
            "enum": ["monitor", "remediate", "escalate", "accept"],
            "description": "One of: monitor, remediate, escalate, accept",
        },
        "reviewer": {"type": "string"},
    },
    "required": [
        "asset_name", "assessment_date", "overall_risk_score",
        "findings", "recommended_action", "reviewer",
    ],
}

EXTRACTION_TOOL = {
    "name": "extract_risk_assessment",
    "description": "Extract a structured risk assessment from a security report.",
    "input_schema": RISK_SCHEMA,
}

# ---------------------------------------------------------------------------
# Sample document
# ---------------------------------------------------------------------------

SAMPLE_REPORT = """
Security Assessment Report
Asset: Customer Data API v2.3
Reviewer: Alex Kim
Date: 2024-11-15

Executive Summary:
This assessment covers the Customer Data API serving approximately 50,000 requests/day.
Overall risk level is HIGH at 82 percent.

Findings:

1. SQL Injection Vulnerability in /search endpoint
   Component: Database query layer
   Likelihood: 68 percent
   Severity: CRITICAL

2. Missing rate limiting on authentication endpoints
   Component: Auth service
   Likelihood: 90 percent
   Severity: HIGH

3. Outdated TLS certificate (expires in 14 days)
   Component: Load balancer
   Likelihood: 95 percent
   Severity: MEDIUM

Recommendation: Immediate remediation required before next deployment.
"""

# ---------------------------------------------------------------------------
# Method A: Validated completion with error feedback (the right way)
# ---------------------------------------------------------------------------

def validated_completion(
    document: str,
    max_retries: int = 3,
    verbose: bool = True,
) -> tuple[RiskAssessment | None, dict]:
    """
    Extract and validate a RiskAssessment from `document`.
    On Pydantic validation failure, feeds the error back to the model and retries.

    Returns:
        (result, stats) where stats contains attempt count and error history
    """
    messages = [
        {
            "role": "user",
            "content": "Extract a risk assessment from this security report:\n\n" + document,
        }
    ]

    stats = {"attempts": 0, "errors": [], "strategy": "error_feedback"}

    for attempt in range(1, max_retries + 1):
        stats["attempts"] = attempt
        if verbose:
            print(f"    Attempt {attempt}/{max_retries}...")

        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "any"},
            messages=messages,
        )

        # Extract the tool_use block
        extracted_data = None
        for block in response.content:
            if block.type == "tool_use" and block.name == "extract_risk_assessment":
                extracted_data = block.input
                break

        if extracted_data is None:
            msg = f"No tool_use block (stop_reason={response.stop_reason})"
            stats["errors"].append(msg)
            if verbose:
                print(f"    {msg}")
            break

        # Pydantic validation
        try:
            result = RiskAssessment(**extracted_data)
            if verbose:
                print(f"    Validation passed on attempt {attempt}.")
            return result, stats

        except Exception as e:
            error_msg = str(e)
            stats["errors"].append(error_msg)
            if verbose:
                print(f"    Validation failed: {error_msg[:150]}")

            if attempt == max_retries:
                if verbose:
                    print(f"    Max retries exhausted.")
                return None, stats

            # Feed the error back: append model response + user correction
            messages.append({
                "role": "assistant",
                "content": response.content,
            })
            messages.append({
                "role": "user",
                "content": (
                    f"Validation failed with this error:\n\n{error_msg}\n\n"
                    "Please correct only the fields that failed. "
                    "Remember: scores and likelihoods must be decimals (0.75), not percentages (75). "
                    "Call the tool again with the corrected values."
                ),
            })

    return None, stats


# ---------------------------------------------------------------------------
# Method B: Blind retry (the naive approach - for comparison)
# ---------------------------------------------------------------------------

def blind_retry(
    document: str,
    max_retries: int = 3,
    verbose: bool = True,
) -> tuple[RiskAssessment | None, dict]:
    """
    Naive approach: retry the same prompt on failure.
    Does NOT feed validation errors back to the model.
    For comparison with validated_completion.
    """
    stats = {"attempts": 0, "errors": [], "strategy": "blind_retry"}
    base_messages = [
        {
            "role": "user",
            "content": "Extract a risk assessment from this security report:\n\n" + document,
        }
    ]

    for attempt in range(1, max_retries + 1):
        stats["attempts"] = attempt
        if verbose:
            print(f"    Attempt {attempt}/{max_retries}...")

        # Always restart from the same prompt (no error context)
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "any"},
            messages=base_messages,
        )

        for block in response.content:
            if block.type == "tool_use":
                try:
                    result = RiskAssessment(**block.input)
                    if verbose:
                        print(f"    Validation passed on attempt {attempt}.")
                    return result, stats
                except Exception as e:
                    error_msg = str(e)
                    stats["errors"].append(error_msg)
                    if verbose:
                        print(f"    Validation failed: {error_msg[:150]}")
                    break  # move to next attempt without any feedback

    return None, stats


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_result(result: RiskAssessment | None, stats: dict) -> None:
    """Print a formatted result summary."""
    strategy = stats["strategy"]
    attempts = stats["attempts"]

    if result:
        print(f"  SUCCESS after {attempts} attempt(s) [{strategy}]")
        print(f"  Asset: {result.asset_name}")
        print(f"  Risk score: {result.overall_risk_score} (should be 0.0-1.0)")
        print(f"  Action: {result.recommended_action}")
        print(f"  Findings: {len(result.findings)}")
        for f in result.findings:
            print(f"    - [{f.severity}] {f.title} (likelihood={f.likelihood})")
    else:
        print(f"  FAILED after {attempts} attempt(s) [{strategy}]")
        print(f"  Errors:")
        for err in stats["errors"]:
            print(f"    - {err[:120]}")


# ---------------------------------------------------------------------------
# Run comparison
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Validation + Retry Loops: Error-Feedback vs. Blind Retry")
    print("=" * 65)
    print(f"\nDocument: Security Assessment Report (contains % values that should be decimals)")

    print("\n--- Strategy A: Error-Feedback Retry ---")
    result_a, stats_a = validated_completion(SAMPLE_REPORT, max_retries=3, verbose=True)
    print_result(result_a, stats_a)

    print("\n--- Strategy B: Blind Retry ---")
    result_b, stats_b = blind_retry(SAMPLE_REPORT, max_retries=3, verbose=True)
    print_result(result_b, stats_b)

    print("\n--- Summary ---")
    print(f"Error-feedback: {'SUCCESS' if result_a else 'FAILED'} in {stats_a['attempts']} attempt(s)")
    print(f"Blind retry:    {'SUCCESS' if result_b else 'FAILED'} in {stats_b['attempts']} attempt(s)")
