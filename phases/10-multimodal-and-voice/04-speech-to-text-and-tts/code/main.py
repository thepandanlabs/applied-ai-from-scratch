"""
Lesson 10-04: Speech-to-Text and Text-to-Speech
Transcribes audio with Whisper (chunking for long files), summarizes with Claude,
and synthesizes a follow-up message with OpenAI TTS.

Usage:
    python main.py                  # demo mode (no API calls needed)
    python main.py call.mp3         # transcribe a real audio file
    python main.py call.mp3 --demo  # force demo mode

Requirements:
    pip install anthropic openai
    Optional: pip install pydub     (for long audio chunking)
"""

import anthropic
import os
import sys
import time
from pathlib import Path
from typing import Optional


# --------------------------------------------------------------------------- #
# Audio chunking                                                               #
# --------------------------------------------------------------------------- #

MAX_FILE_BYTES = 24 * 1024 * 1024  # 24MB (Whisper limit is 25MB)


def chunk_audio_file(
    audio_path: Path,
    chunk_duration_ms: int = 600_000,  # 10 minutes
) -> list[Path]:
    """
    Split long audio files on silence boundaries.
    Returns list of chunk file paths (or [audio_path] if file is small enough).
    Requires pydub: pip install pydub
    """
    if audio_path.stat().st_size <= MAX_FILE_BYTES:
        return [audio_path]

    try:
        from pydub import AudioSegment
        from pydub.silence import split_on_silence
    except ImportError:
        print("  pydub not installed (pip install pydub). Sending full file.")
        return [audio_path]

    audio = AudioSegment.from_file(audio_path)
    print(f"  Total duration: {len(audio) / 1000:.1f}s")

    raw_chunks = split_on_silence(
        audio,
        min_silence_len=500,
        silence_thresh=-40,
        keep_silence=200,
    )

    # Merge into ~10-minute segments
    merged: list[AudioSegment] = []
    current: Optional[AudioSegment] = None
    for chunk in raw_chunks:
        if current is None:
            current = chunk
        elif len(current) + len(chunk) < chunk_duration_ms:
            current = current + chunk
        else:
            merged.append(current)
            current = chunk
    if current:
        merged.append(current)

    paths = []
    for i, seg in enumerate(merged):
        p = audio_path.parent / f"{audio_path.stem}_chunk{i:02d}.mp3"
        seg.export(p, format="mp3")
        paths.append(p)
        print(f"  Chunk {i}: {len(seg) / 1000:.1f}s, {p.stat().st_size:,} bytes")

    return paths


# --------------------------------------------------------------------------- #
# Transcription                                                                #
# --------------------------------------------------------------------------- #

def transcribe_file(audio_path: Path, demo_mode: bool = False) -> str:
    """Transcribe a single audio chunk using Whisper."""
    if demo_mode:
        return (
            "Thank you for calling customer support. My name is Alex. "
            "How can I help you today? Hi Alex, I have a problem with my recent order. "
            "The package arrived damaged and I need a replacement. "
            "I'm sorry to hear that. I'll process a replacement order for you right away. "
            "Thank you so much."
        )

    from openai import OpenAI
    client = OpenAI()

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text",
        )
    return response


def transcribe_audio(audio_path: Path, demo_mode: bool = False) -> dict:
    """Transcribe audio, chunking automatically for large files."""
    if demo_mode:
        return {
            "text": transcribe_file(audio_path, demo_mode=True),
            "duration_seconds": 45.0,
            "chunks": 1,
        }

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    start = time.time()
    chunks = chunk_audio_file(audio_path)
    print(f"  Chunks: {len(chunks)}")

    texts = []
    for chunk_path in chunks:
        texts.append(transcribe_file(chunk_path))
        if chunk_path != audio_path:
            chunk_path.unlink(missing_ok=True)

    elapsed = time.time() - start
    full_text = " ".join(texts)
    return {
        "text": full_text,
        "duration_seconds": elapsed,  # approximate; real duration needs audio metadata
        "chunks": len(chunks),
    }


# --------------------------------------------------------------------------- #
# Summarization                                                                #
# --------------------------------------------------------------------------- #

def summarize_transcript(transcript: str, model: str = "claude-3-5-haiku-20241022") -> str:
    """Summarize transcript and write a follow-up message using Claude."""
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are a customer service assistant. "
                    "Summarize this call transcript in 2-3 sentences, then write a brief "
                    "follow-up message the customer should receive (under 60 words, warm and professional).\n\n"
                    f"TRANSCRIPT:\n{transcript}"
                ),
            }
        ],
    )
    return message.content[0].text


# --------------------------------------------------------------------------- #
# Text-to-Speech                                                               #
# --------------------------------------------------------------------------- #

def synthesize_speech(
    text: str,
    voice: str = "nova",
    output_path: Path = Path("follow_up.mp3"),
    demo_mode: bool = False,
) -> Path:
    """Synthesize text to MP3 using OpenAI TTS."""
    if demo_mode:
        output_path.write_bytes(b"\xff\xfb\x10\x00" + b"\x00" * 100)
        return output_path

    from openai import OpenAI
    client = OpenAI()

    response = client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text,
    )
    response.stream_to_file(output_path)
    return output_path


# --------------------------------------------------------------------------- #
# WER                                                                          #
# --------------------------------------------------------------------------- #

def word_error_rate(reference: str, hypothesis: str) -> float:
    """Compute WER using word-level edit distance."""
    ref = reference.lower().split()
    hyp = hypothesis.lower().split()
    n = len(ref)
    if n == 0:
        return 0.0

    dp = list(range(len(hyp) + 1))
    for i, r in enumerate(ref):
        new_dp = [i + 1] + [0] * len(hyp)
        for j, h in enumerate(hyp):
            if r == h:
                new_dp[j + 1] = dp[j]
            else:
                new_dp[j + 1] = 1 + min(dp[j], dp[j + 1], new_dp[j])
        dp = new_dp

    return dp[len(hyp)] / n


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def main():
    print("=== Lesson 10-04: Speech-to-Text and Text-to-Speech ===\n")

    demo_mode = "--demo" in sys.argv or (
        "OPENAI_API_KEY" not in os.environ
    )

    audio_args = [a for a in sys.argv[1:] if not a.startswith("-")]
    audio_path = Path(audio_args[0]) if audio_args else Path("demo_call.mp3")

    if not audio_path.exists() and not demo_mode:
        print(f"File not found: {audio_path}. Switching to demo mode.")
        demo_mode = True

    print(f"File:      {audio_path}")
    print(f"Demo mode: {demo_mode}\n")

    # Step 1: Transcribe
    print("--- Step 1: Transcription ---")
    result = transcribe_audio(audio_path, demo_mode=demo_mode)
    transcript = result["text"]
    print(f"Words: {len(transcript.split())}")
    print(f"Preview: {transcript[:200]}...\n" if len(transcript) > 200 else f"Transcript: {transcript}\n")

    # Cost estimate
    estimated_minutes = result["duration_seconds"] / 60
    print(f"Cost estimate (Whisper): ${estimated_minutes * 0.006:.4f}\n")

    # Step 2: Summarize
    print("--- Step 2: Summarization (Claude) ---")
    if demo_mode:
        summary = (
            "A customer reported receiving a damaged package and requested a replacement. "
            "The support agent confirmed and processed a replacement order immediately.\n\n"
            "Follow-up: Hi, thank you for reaching out today. Your replacement order "
            "has been confirmed and will arrive within 3-5 business days. "
            "We apologize for the inconvenience and appreciate your patience."
        )
        print("[Demo summary]\n")
    else:
        summary = summarize_transcript(transcript)

    print(summary)
    print()

    # Step 3: Synthesize
    print("--- Step 3: Text-to-Speech ---")
    out = Path("follow_up.mp3")
    synthesize_speech(summary, voice="nova", output_path=out, demo_mode=demo_mode)
    print(f"Output: {out} ({out.stat().st_size:,} bytes)\n")

    # WER demo
    print("--- WER demonstration ---")
    ref = "The customer reported a damaged package and requested a replacement."
    hyp_good = "The customer reported a damaged package and requested a replacement."
    hyp_bad  = "The customer report a damage package and request replacement."
    print(f"Reference:    '{ref}'")
    print(f"Good WER:     {word_error_rate(ref, hyp_good):.1%}")
    print(f"Degraded WER: {word_error_rate(ref, hyp_bad):.1%}\n")

    # Provider comparison
    print("--- STT provider cost comparison (1 hour of audio) ---")
    stt_providers = [
        ("Whisper (OpenAI)", 0.006),
        ("Deepgram Nova-2", 0.004),
        ("AssemblyAI", 0.012),
        ("Google STT v2", 0.016),
    ]
    for name, rate in stt_providers:
        print(f"  {name:<26} ${rate:.3f}/min  ${rate*60:.2f}/hour")

    print("\n--- TTS provider cost comparison (1,000 characters) ---")
    tts_providers = [
        ("OpenAI TTS-1", 0.015),
        ("ElevenLabs", 0.180),
        ("Google Cloud TTS", 0.004),
        ("Azure Neural TTS", 0.008),
    ]
    for name, rate in tts_providers:
        print(f"  {name:<26} ${rate:.3f}/1k chars")


if __name__ == "__main__":
    main()
