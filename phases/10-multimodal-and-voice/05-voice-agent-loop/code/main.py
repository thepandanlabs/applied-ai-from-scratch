"""
Lesson 10-05: Building a Voice Agent Loop
Minimal STT-LLM-TTS voice agent loop with streaming TTS pattern,
barge-in state machine, and human handoff trigger.

Usage:
    python main.py          # demo mode (text I/O, no API calls)
    python main.py --real   # real mode (requires API keys)

Requirements:
    pip install anthropic
    Real mode also requires: pip install openai
"""

import anthropic
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional


# --------------------------------------------------------------------------- #
# State machine                                                                #
# --------------------------------------------------------------------------- #

class AgentState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()
    HANDOFF = auto()


@dataclass
class ConversationTurn:
    role: str
    text: str


@dataclass
class VoiceAgentSession:
    state: AgentState = AgentState.IDLE
    history: list[ConversationTurn] = field(default_factory=list)
    turn_count: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    def add_turn(self, role: str, text: str):
        self.history.append(ConversationTurn(role=role, text=text))
        self.turn_count += 1

    def to_messages(self) -> list[dict]:
        return [{"role": t.role, "content": t.text} for t in self.history]


# --------------------------------------------------------------------------- #
# Sentence buffering for streaming TTS                                         #
# --------------------------------------------------------------------------- #

class SentenceBuffer:
    """
    Accumulates LLM token stream and emits complete sentences.
    Key optimization: TTS synthesis begins before LLM finishes.
    """
    ENDS = {".", "!", "?", ":", "\n"}

    def __init__(self):
        self._buf = ""
        self._emitted: list[str] = []

    def push(self, token: str) -> list[str]:
        self._buf += token
        ready = []
        if any(self._buf.rstrip().endswith(e) for e in self.ENDS):
            sentence = self._buf.strip()
            if len(sentence) > 5:
                ready.append(sentence)
                self._buf = ""
        return ready

    def flush(self) -> list[str]:
        remainder = self._buf.strip()
        self._buf = ""
        return [remainder] if remainder else []


# --------------------------------------------------------------------------- #
# LLM with streaming                                                           #
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = (
    "You are a concise customer service voice agent. "
    "Keep every response under 3 sentences. "
    "If the user asks to speak to a human, respond exactly: HANDOFF_REQUESTED "
    "Do not use markdown or bullet points. Speak naturally."
)


def generate_response(
    session: VoiceAgentSession,
    user_text: str,
    model: str = "claude-3-5-haiku-20241022",
    on_sentence: Optional[callable] = None,
    demo_mode: bool = True,
) -> str:
    """
    Generate agent response.
    Calls on_sentence(text) for each complete sentence (streaming TTS pattern).
    Returns full response text.
    """
    session.add_turn("user", user_text)

    if demo_mode:
        demo_map = {
            "hello": "Hello! Thank you for calling. How can I assist you today?",
            "hi": "Hi there! How can I help you today?",
            "billing": "I can help with billing questions. What would you like to know?",
            "invoice": "I can pull up your invoice details. What is your account number?",
            "wrong": "I'm sorry to hear that. Let me look into this for you.",
            "human": "HANDOFF_REQUESTED",
            "agent": "HANDOFF_REQUESTED",
            "bye": "Thank you for calling. Have a great day!",
            "goodbye": "Thanks for reaching out. Goodbye!",
        }
        lower = user_text.lower()
        response = "I understand. How can I help you further?"
        for kw, resp in demo_map.items():
            if kw in lower:
                response = resp
                break
        if on_sentence:
            on_sentence(response)
        session.add_turn("assistant", response)
        return response

    client = anthropic.Anthropic()
    buf = SentenceBuffer()
    full = ""

    with client.messages.stream(
        model=model,
        max_tokens=150,
        system=SYSTEM_PROMPT,
        messages=session.to_messages(),
    ) as stream:
        for token in stream.text_stream:
            full += token
            for sentence in buf.push(token):
                if on_sentence:
                    on_sentence(sentence)
        for sentence in buf.flush():
            if on_sentence:
                on_sentence(sentence)

    session.add_turn("assistant", full)
    return full


# --------------------------------------------------------------------------- #
# TTS                                                                          #
# --------------------------------------------------------------------------- #

def synthesize_sentence(text: str, demo_mode: bool = True) -> None:
    """Synthesize and play a single sentence."""
    if demo_mode:
        print(f"    [TTS] {text}")
        return

    from openai import OpenAI
    import tempfile
    import subprocess
    import platform

    client = OpenAI()
    response = client.audio.speech.create(model="tts-1", voice="nova", input=text)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp = Path(f.name)
        response.stream_to_file(tmp)

    if platform.system() == "Darwin":
        subprocess.run(["afplay", str(tmp)], check=False)
    elif platform.system() == "Linux":
        subprocess.run(["mpg123", str(tmp)], check=False)
    else:
        print(f"  [Audio: {tmp}]")

    tmp.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Main agent loop                                                              #
# --------------------------------------------------------------------------- #

def run_agent(
    demo_inputs: Optional[list[str]] = None,
    demo_mode: bool = True,
) -> VoiceAgentSession:
    """Run the voice agent loop."""
    session = VoiceAgentSession()

    print("\n" + "=" * 55)
    print("Voice Agent Session")
    print("=" * 55)

    input_iter = iter(demo_inputs or [])

    while session.turn_count < 20:
        session.state = AgentState.LISTENING

        # --- Get input ---
        if demo_mode:
            try:
                user_text = next(input_iter).strip()
            except StopIteration:
                print("\n  [Demo inputs exhausted]")
                break
        else:
            audio_path = Path(f"turn_{session.turn_count:02d}.mp3")
            if not audio_path.exists():
                print(f"  No audio file found at {audio_path}. Ending.")
                break
            from openai import OpenAI
            client = OpenAI()
            with open(audio_path, "rb") as f:
                user_text = client.audio.transcriptions.create(
                    model="whisper-1", file=f
                ).text

        if not user_text:
            continue

        print(f"\n[Turn {session.turn_count + 1}]")
        print(f"  User: {user_text}")

        if user_text.lower() in ("bye", "goodbye", "exit", "quit"):
            print("  [User ended session]")
            break

        # --- Generate + stream TTS ---
        session.state = AgentState.PROCESSING
        t_start = time.time()

        sentences_spoken = []

        def on_sentence(s: str):
            sentences_spoken.append(s)
            synthesize_sentence(s, demo_mode=demo_mode)

        response = generate_response(session, user_text, on_sentence=on_sentence, demo_mode=demo_mode)
        latency_ms = (time.time() - t_start) * 1000
        session.latencies_ms.append(latency_ms)

        print(f"  Agent: {response}")
        print(f"  Latency: {latency_ms:.0f}ms | Sentences streamed: {len(sentences_spoken)}")

        # --- Check handoff ---
        if "HANDOFF_REQUESTED" in response:
            session.state = AgentState.HANDOFF
            print("\n  [HANDOFF] Transferring to human agent...")
            print("  [Session history passed to human agent queue]")
            break

        session.state = AgentState.IDLE

    # --- Summary ---
    print("\n" + "=" * 55)
    print("Session Summary")
    print("=" * 55)
    print(f"  Turns:       {session.turn_count}")
    print(f"  Final state: {session.state.name}")
    if session.latencies_ms:
        avg = sum(session.latencies_ms) / len(session.latencies_ms)
        p95_idx = max(0, int(len(session.latencies_ms) * 0.95) - 1)
        p95 = sorted(session.latencies_ms)[p95_idx]
        print(f"  Avg latency: {avg:.0f}ms")
        print(f"  P95 latency: {p95:.0f}ms")
        print(f"  Target met (P95 < 500ms): {'YES' if p95 < 500 else 'NO'}")

    return session


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def main():
    print("=== Lesson 10-05: Building a Voice Agent Loop ===")

    demo_mode = "--real" not in sys.argv or (
        "ANTHROPIC_API_KEY" not in os.environ or "OPENAI_API_KEY" not in os.environ
    )

    if "--real" in sys.argv and demo_mode:
        print("Warning: API keys missing. Using demo mode.")

    print(f"\nMode: {'demo (text I/O)' if demo_mode else 'real (audio I/O)'}")

    # Latency budget
    print("\n--- Latency budget comparison ---")
    print(f"  {'Stage':<25} {'Naive':>10} {'Optimized':>12}")
    print("  " + "-" * 50)
    stages = [
        ("STT", "300ms", "100ms"),
        ("LLM TTFT", "700ms", "250ms"),
        ("TTS first chunk", "400ms", "80ms"),
        ("Audio buffer", "150ms", "30ms"),
        ("TOTAL", "~1550ms", "~460ms"),
    ]
    for stage, naive, opt in stages:
        marker = " <-- OVER TARGET" if stage == "TOTAL" and "1550" in naive else ""
        print(f"  {stage:<25} {naive:>10} {opt:>12}{marker}")

    # Run demo conversation
    demo_inputs = [
        "Hello, I need help with my account.",
        "I have a question about my last invoice.",
        "The amount seems wrong.",
        "Can I speak to a human agent please?",
    ]

    print(f"\n--- Running {len(demo_inputs)}-turn demo conversation ---")
    session = run_agent(demo_inputs=demo_inputs, demo_mode=demo_mode)

    # Barge-in state machine
    print("\n--- Barge-in state machine ---")
    transitions = [
        ("IDLE", "VAD detects speech", "LISTENING"),
        ("LISTENING", "Silence > 500ms", "PROCESSING"),
        ("PROCESSING", "First audio chunk ready", "SPEAKING"),
        ("SPEAKING", "VAD detects new speech", "LISTENING (cancel TTS + LLM)"),
        ("SPEAKING", "TTS playback complete", "IDLE"),
        ("any", "User says 'human'", "HANDOFF"),
    ]
    print(f"  {'From':<15} {'Event':<38} {'To'}")
    print("  " + "-" * 65)
    for from_s, event, to_s in transitions:
        print(f"  {from_s:<15} {event:<38} {to_s}")


if __name__ == "__main__":
    main()
