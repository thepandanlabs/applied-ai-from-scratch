"""
Voice pipeline latency profiler.

Demo mode: generates synthetic timing data with realistic distributions.
No API keys required for demo mode.

Run:
    python main.py --demo           # synthetic data profiling
    python main.py --demo --n 200   # larger sample for stable percentiles
    python main.py --demo --cached-prompt   # simulate warm prompt cache
    python main.py --streaming-demo         # streaming TTS architecture
"""

import time
import random
import argparse
import statistics
from dataclasses import dataclass, field
from typing import Optional
import json


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TurnTimings:
    """Per-turn latency measurements in milliseconds."""
    stt_endpoint_ms: float = 0.0   # VAD: speech end detection
    stt_model_ms: float = 0.0      # STT inference: audio -> text
    network_rtt_ms: float = 0.0    # client -> LLM API
    llm_ttft_ms: float = 0.0       # LLM: time to first token
    tts_start_ms: float = 0.0      # TTS: synthesis start latency
    playback_start_ms: float = 0.0 # audio buffer fill -> first sound
    # Derived
    total_naive_ms: float = 0.0    # all stages sequential
    total_streaming_ms: float = 0.0 # with sentence-level TTS streaming


@dataclass
class PipelineProfile:
    """Aggregated profile over N turns."""
    stage_names: list = field(default_factory=list)
    p50: dict = field(default_factory=dict)
    p95: dict = field(default_factory=dict)
    bottleneck: str = ""
    streaming_win_ms: float = 0.0


# ---------------------------------------------------------------------------
# Demo: synthetic timing generators
# ---------------------------------------------------------------------------

def _normal_clamp(mean: float, std: float, lo: float, hi: float) -> float:
    """Gaussian sample clamped to [lo, hi]."""
    return max(lo, min(hi, random.gauss(mean, std)))


def generate_synthetic_turn(cached_prompt: bool = False) -> TurnTimings:
    """
    Generate one turn of synthetic timing data.
    Distributions based on typical production voice pipeline measurements.
    cached_prompt: True simulates a warm prompt cache (reduces LLM TTFT).
    """
    t = TurnTimings()
    t.stt_endpoint_ms  = _normal_clamp(100, 30, 40, 250)
    t.stt_model_ms     = _normal_clamp(150, 50, 60, 400)
    t.network_rtt_ms   = _normal_clamp(40,  15, 10, 120)

    # LLM TTFT: uncached vs cached system prompt
    if cached_prompt:
        t.llm_ttft_ms = _normal_clamp(180, 60, 80, 450)
    else:
        t.llm_ttft_ms = _normal_clamp(380, 120, 150, 900)

    t.tts_start_ms      = _normal_clamp(120, 40, 50, 300)
    t.playback_start_ms = _normal_clamp(30, 10, 10, 80)

    # Naive: all stages in sequence
    t.total_naive_ms = (
        t.stt_endpoint_ms + t.stt_model_ms + t.network_rtt_ms
        + t.llm_ttft_ms + t.tts_start_ms + t.playback_start_ms
    )

    # Streaming: TTS starts after first sentence (~60% of full TTFT)
    # User hears audio after: STT + network + 60% LLM TTFT + TTS start
    streaming_llm = t.llm_ttft_ms * 0.60
    t.total_streaming_ms = (
        t.stt_endpoint_ms + t.stt_model_ms + t.network_rtt_ms
        + streaming_llm + t.tts_start_ms + t.playback_start_ms
    )

    return t


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------

STAGE_FIELDS = [
    ("stt_endpoint_ms",    "STT Endpoint Detection"),
    ("stt_model_ms",       "STT Model Inference"),
    ("network_rtt_ms",     "Network RTT"),
    ("llm_ttft_ms",        "LLM Time-to-First-Token"),
    ("tts_start_ms",       "TTS Synthesis Start"),
    ("playback_start_ms",  "Playback Start"),
    ("total_naive_ms",     "Total (Naive / Waterfall)"),
    ("total_streaming_ms", "Total (Sentence Streaming)"),
]


def percentile(data: list, p: float) -> float:
    """Compute the p-th percentile of a list of numbers."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (p / 100) * (len(sorted_data) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_data) - 1)
    frac = idx - lo
    return sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo])


def profile_pipeline(turns: list) -> PipelineProfile:
    """Compute P50/P95 per stage and identify the bottleneck."""
    profile = PipelineProfile()
    stage_p50s = {}

    for field_name, label in STAGE_FIELDS:
        values = [getattr(t, field_name) for t in turns]
        p50 = percentile(values, 50)
        p95 = percentile(values, 95)
        profile.p50[label] = p50
        profile.p95[label] = p95
        profile.stage_names.append(label)
        if "Total" not in label:
            stage_p50s[label] = p50

    # Bottleneck: stage with highest P50 (excluding totals)
    profile.bottleneck = max(stage_p50s, key=lambda k: stage_p50s[k])

    # Streaming win at P50
    total_naive_p50  = profile.p50["Total (Naive / Waterfall)"]
    total_stream_p50 = profile.p50["Total (Sentence Streaming)"]
    profile.streaming_win_ms = total_naive_p50 - total_stream_p50

    return profile


def print_profile(profile: PipelineProfile, slo_p95_ms: float = 600.0):
    """Print a formatted latency report."""
    print("\n" + "=" * 65)
    print("  VOICE PIPELINE LATENCY PROFILE")
    print("=" * 65)
    print(f"{'Stage':<35} {'P50 (ms)':>10} {'P95 (ms)':>10}")
    print("-" * 65)

    for label in profile.stage_names:
        p50 = profile.p50[label]
        p95 = profile.p95[label]
        marker = " << BOTTLENECK" if label == profile.bottleneck else ""
        if "Total" in label:
            print("-" * 65)
        print(f"  {label:<33} {p50:>10.0f} {p95:>10.0f}{marker}")

    print("=" * 65)
    print(f"\n  Bottleneck stage:     {profile.bottleneck}")
    print(f"  Streaming saves:      {profile.streaming_win_ms:.0f}ms at P50")

    # SLO check
    stream_p95 = profile.p95["Total (Sentence Streaming)"]
    slo_status = "PASS" if stream_p95 <= slo_p95_ms else "FAIL"
    print(f"\n  SLO (P95 < {slo_p95_ms:.0f}ms): {stream_p95:.0f}ms -> {slo_status}")
    if slo_status == "FAIL":
        print(f"  ACTION: P95 {stream_p95:.0f}ms exceeds {slo_p95_ms:.0f}ms SLO.")
        print(f"          Focus optimization on: {profile.bottleneck}")
    print()


# ---------------------------------------------------------------------------
# Streaming TTS pattern demo (no API keys required)
# ---------------------------------------------------------------------------

def streaming_tts_pattern_demo():
    """
    Show timing architecture of sentence-level TTS streaming.

    In production:
    - Read the LLM stream token by token
    - Detect sentence boundaries (. ! ?)
    - Send each complete sentence to TTS immediately (streaming request)
    - Queue TTS audio chunks for gapless playback
    - Start playback when the first TTS chunk arrives

    This simulates timing without making any API calls.
    """
    print("\n--- Streaming TTS Pattern: Timing Simulation ---")
    sentences = [
        "The pressure relief valve is located on the left side of the unit.",
        "Turn it counter-clockwise to release pressure.",
        "Wait ten seconds before proceeding to the next step.",
    ]

    llm_token_rate = 40   # tokens/sec
    tts_latency    = 0.12 # 120ms per sentence start

    wall = 0.0
    print(f"\n{'Time':>8}  Event")
    print("-" * 55)

    wall += 0.38  # TTFT
    print(f"{wall*1000:>8.0f}ms  LLM: first token arrives")

    for i, sentence in enumerate(sentences):
        token_count = len(sentence.split()) * 1.3
        gen_time = token_count / llm_token_rate
        wall += gen_time
        print(f"{wall*1000:>8.0f}ms  LLM: sentence {i+1} complete -> dispatch to TTS")
        wall += tts_latency
        if i == 0:
            print(f"{wall*1000:>8.0f}ms  *** First audio chunk ready - user hears voice ***")
        else:
            print(f"{wall*1000:>8.0f}ms  Audio chunk {i+1} ready (buffered seamlessly)")

    naive_total = 0.38 + sum(len(s.split()) * 1.3 / llm_token_rate for s in sentences) + 0.12
    first_sent_time = 0.38 + (len(sentences[0].split()) * 1.3 / llm_token_rate) + 0.12
    print(f"\n  Streaming: user hears first word at ~{first_sent_time*1000:.0f}ms")
    print(f"  Naive:     user hears first word at ~{naive_total*1000:.0f}ms")
    print(f"  Savings:   ~{(naive_total - first_sent_time)*1000:.0f}ms")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Voice pipeline latency profiler")
    parser.add_argument("--demo", action="store_true",
                        help="Use synthetic timing data (no API keys needed)")
    parser.add_argument("--n", type=int, default=100,
                        help="Number of synthetic turns to simulate")
    parser.add_argument("--cached-prompt", action="store_true",
                        help="Simulate warm prompt cache (lower LLM TTFT)")
    parser.add_argument("--slo", type=float, default=600.0,
                        help="P95 SLO threshold in ms (default: 600)")
    parser.add_argument("--streaming-demo", action="store_true",
                        help="Show streaming TTS timing architecture")
    args = parser.parse_args()

    if args.streaming_demo:
        streaming_tts_pattern_demo()
        return

    if args.demo:
        print(f"\nGenerating {args.n} synthetic voice turns "
              f"(cached_prompt={args.cached_prompt})...")
        random.seed(42)
        turns = [generate_synthetic_turn(cached_prompt=args.cached_prompt)
                 for _ in range(args.n)]
        profile = profile_pipeline(turns)
        print_profile(profile, slo_p95_ms=args.slo)

        if not args.cached_prompt:
            print("Tip: run with --cached-prompt to simulate Claude's")
            print("     prompt caching effect on LLM TTFT.")
            print("Tip: run with --streaming-demo to see the TTS")
            print("     sentence-streaming pattern.")
    else:
        print("Pass --demo to run with synthetic data.")
        print("For production: instrument each stage with time.perf_counter()")
        print("before/after each API call, populate TurnTimings, and pass")
        print("the list to profile_pipeline().")


if __name__ == "__main__":
    main()
