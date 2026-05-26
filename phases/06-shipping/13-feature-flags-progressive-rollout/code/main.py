"""
Lesson 13: Feature Flags and Progressive Rollout
Phase 06: Shipping

Three rollout modes for AI services:
  - Shadow: run new version in parallel, serve old to users, compare outputs
  - Canary: route X% of real traffic to new version by deterministic user hash
  - A/B: split traffic for outcome metric measurement

Usage:
    python main.py              # run the demo showing all three modes
    uvicorn main:app --reload   # start the FastAPI service

Requires: ANTHROPIC_API_KEY environment variable
"""

from __future__ import annotations

import hashlib
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MODEL_ID = "claude-3-5-haiku-20241022"

# ---------------------------------------------------------------------------
# Prompt templates - in production these would be loaded from a file
# or the version manifest registry from Lesson 12.
# ---------------------------------------------------------------------------

PROMPTS: dict[str, str] = {
    "v1.0": "You are a helpful assistant. Answer concisely in 1-3 sentences.",
    "v1.1": (
        "You are a helpful assistant. Answer concisely in 1-3 sentences. "
        "End your response with a one-line summary starting with 'In short:'"
    ),
}


# ---------------------------------------------------------------------------
# Feature flag types
# ---------------------------------------------------------------------------


class RolloutMode(str, Enum):
    SHADOW = "shadow"  # run new version in parallel, serve old to users
    CANARY = "canary"  # route X% of real traffic to new version
    AB = "ab"          # split traffic by user ID, measure outcome metric


@dataclass
class FeatureFlag:
    """
    Routes requests to prompt variants based on rollout_pct and mode.

    Attributes:
        name:        Unique flag identifier, included in the hash key so
                     different flags produce independent bucket assignments.
        rollout_pct: 0-100. Percentage of user IDs assigned to variant B.
        mode:        shadow, canary, or ab.
        variant_a:   The control prompt version (current production).
        variant_b:   The treatment prompt version (new version under test).
    """

    name: str
    rollout_pct: float
    mode: RolloutMode
    variant_a: str
    variant_b: str

    def _bucket(self, user_id: str) -> int:
        """
        Deterministic hash of user_id to a bucket 0-99.
        Including the flag name ensures different flags assign users independently.
        """
        key = f"{self.name}:{user_id}"
        digest = hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()
        return int(digest[:8], 16) % 100

    def variant_for(self, user_id: str) -> str:
        """
        Return 'a' or 'b' for this user.
        Deterministic: same user_id always returns the same variant.
        """
        bucket = self._bucket(user_id)
        return "b" if bucket < self.rollout_pct else "a"

    def prompt_for(self, user_id: str) -> str:
        """Return the prompt version string for this user."""
        v = self.variant_for(user_id)
        return self.variant_b if v == "b" else self.variant_a


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------


def call_model(prompt_version: str, user_message: str, model_id: str = MODEL_ID) -> dict:
    """
    Call Claude with the given prompt version.
    Returns response text, latency, and token counts.
    """
    client = anthropic.Anthropic()
    system = PROMPTS.get(prompt_version, PROMPTS["v1.0"])

    start = time.monotonic()
    response = client.messages.create(
        model=model_id,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    return {
        "text": response.content[0].text,
        "prompt_version": prompt_version,
        "latency_ms": latency_ms,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


# ---------------------------------------------------------------------------
# Shadow mode
# ---------------------------------------------------------------------------


def run_shadow(
    flag: FeatureFlag,
    user_id: str,
    user_message: str,
    model_id: str = MODEL_ID,
) -> dict:
    """
    Shadow mode: call both variants.
    Return variant A response to the caller (this is what users see).
    Log both outputs for comparison. Variant B is never shown to users.
    """
    result_a = call_model(flag.variant_a, user_message, model_id)
    result_b = call_model(flag.variant_b, user_message, model_id)

    logger.info(
        "shadow_compare  flag=%s  user=%s  "
        "a_tokens=%d  b_tokens=%d  a_latency=%dms  b_latency=%dms",
        flag.name,
        user_id,
        result_a["output_tokens"],
        result_b["output_tokens"],
        result_a["latency_ms"],
        result_b["latency_ms"],
    )

    # Log truncated outputs at DEBUG level - these feed into your eval harness
    logger.debug("shadow A (%s): %s", flag.variant_a, result_a["text"][:150])
    logger.debug("shadow B (%s): %s", flag.variant_b, result_b["text"][:150])

    # Return A to the caller - B comparison data is for internal analysis only
    return {
        **result_a,
        "variant": "a",
        "shadow_b_text": result_b["text"],
        "shadow_b_tokens": result_b["output_tokens"],
        "shadow_b_latency_ms": result_b["latency_ms"],
    }


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------


def route_request(
    flag: FeatureFlag,
    user_id: str,
    user_message: str,
    model_id: str = MODEL_ID,
) -> dict:
    """
    Route a request based on flag mode and user_id.

    shadow: run both variants, return A to caller, log B for comparison
    canary: deterministic routing, user sees the variant they are assigned
    ab:     same as canary, also logs variant assignment for outcome tracking
    """
    if flag.mode == RolloutMode.SHADOW:
        return run_shadow(flag, user_id, user_message, model_id)

    # Canary and A/B: user sees their assigned variant
    variant = flag.variant_for(user_id)
    prompt_version = flag.variant_b if variant == "b" else flag.variant_a
    result = call_model(prompt_version, user_message, model_id)
    result["variant"] = variant
    result["flag_name"] = flag.name

    if flag.mode == RolloutMode.AB:
        # Log assignment so it can be joined with downstream outcome metrics
        logger.info(
            "ab_assignment  flag=%s  user=%s  variant=%s  prompt=%s",
            flag.name,
            user_id,
            variant,
            prompt_version,
        )

    return result


# ---------------------------------------------------------------------------
# FastAPI service
# ---------------------------------------------------------------------------

# Flag config - change mode and rollout_pct as the rollout progresses:
#   Shadow (week 1):  mode=SHADOW, rollout_pct=0
#   10% canary:       mode=CANARY, rollout_pct=10
#   50% canary:       mode=CANARY, rollout_pct=50
#   Full rollout:     remove flag, use variant_b directly
ACTIVE_FLAG = FeatureFlag(
    name="prompt-v1.1-rollout",
    rollout_pct=10.0,
    mode=RolloutMode.SHADOW,
    variant_a="v1.0",
    variant_b="v1.1",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log the active flag configuration at startup."""
    flag = ACTIVE_FLAG
    logger.info("=== FEATURE FLAG ACTIVE ===")
    logger.info("name:        %s", flag.name)
    logger.info("mode:        %s", flag.mode)
    logger.info("rollout_pct: %.0f%%", flag.rollout_pct)
    logger.info("variant_a:   %s", flag.variant_a)
    logger.info("variant_b:   %s", flag.variant_b)
    logger.info("===========================")
    app.state.flag = flag
    yield


app = FastAPI(title="AI Service with Feature Flags", lifespan=lifespan)


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    response: str
    variant: str
    prompt_version: str
    latency_ms: int


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint with flag-based routing.

    In shadow mode: all users see variant A response.
    In canary/ab mode: users see their deterministically assigned variant.
    """
    flag = app.state.flag

    try:
        result = route_request(
            flag=flag,
            user_id=request.user_id,
            user_message=request.message,
            model_id=MODEL_ID,
        )
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        response=result["text"],
        variant=result.get("variant", "a"),
        prompt_version=result["prompt_version"],
        latency_ms=result["latency_ms"],
    )


@app.get("/flag-status")
async def flag_status():
    """Returns the active flag configuration. Useful for debugging routing."""
    flag = app.state.flag
    return {
        "name": flag.name,
        "mode": flag.mode,
        "rollout_pct": flag.rollout_pct,
        "variant_a": flag.variant_a,
        "variant_b": flag.variant_b,
    }


@app.get("/flag-preview/{user_id}")
async def flag_preview(user_id: str):
    """Show which variant a given user_id maps to without making an API call."""
    flag = app.state.flag
    return {
        "user_id": user_id,
        "variant": flag.variant_for(user_id),
        "prompt_version": flag.prompt_for(user_id),
        "mode": flag.mode,
    }


# ---------------------------------------------------------------------------
# Demo: run from command line to see all three modes
# ---------------------------------------------------------------------------


def demo_distribution(flag: FeatureFlag, n: int = 1000) -> None:
    """Check that bucket distribution is approximately uniform."""
    counts = {"a": 0, "b": 0}
    for i in range(n):
        v = flag.variant_for(f"user-{i:05d}")
        counts[v] += 1
    pct_b = counts["b"] / n * 100
    print(f"  Distribution over {n} users: A={counts['a']} ({100-pct_b:.1f}%) B={counts['b']} ({pct_b:.1f}%)")
    print(f"  Expected: B={flag.rollout_pct:.0f}%  Actual: B={pct_b:.1f}%")


if __name__ == "__main__":
    print("=== FeatureFlag Demo ===\n")

    # Show deterministic assignment
    print("1. Deterministic variant assignment (same user always gets same variant):")
    flag = FeatureFlag(
        name="demo-flag",
        rollout_pct=20.0,
        mode=RolloutMode.CANARY,
        variant_a="v1.0",
        variant_b="v1.1",
    )
    test_users = ["user-001", "user-042", "user-007", "user-999", "user-001"]
    for uid in test_users:
        variant = flag.variant_for(uid)
        prompt = flag.prompt_for(uid)
        print(f"  {uid} -> variant={variant} prompt={prompt}")

    print()
    print("2. Bucket distribution at 20% rollout:")
    demo_distribution(flag, n=10000)

    print()
    print("3. Routing modes:")
    for mode in [RolloutMode.SHADOW, RolloutMode.CANARY, RolloutMode.AB]:
        test_flag = FeatureFlag(
            name=f"mode-test-{mode.value}",
            rollout_pct=50.0,
            mode=mode,
            variant_a="v1.0",
            variant_b="v1.1",
        )
        v = test_flag.variant_for("user-100")
        print(f"  mode={mode.value:<8}  user-100 -> variant={v}  (B response shown to user: {mode != RolloutMode.SHADOW and v == 'b'})")

    print()
    print("4. Shadow mode note:")
    print("  In shadow mode, both prompts run but only variant_a is returned to users.")
    print("  Set logging level to DEBUG to see shadow comparison output.")
    print("  Use those logs to evaluate whether variant_b is ready for canary.")
