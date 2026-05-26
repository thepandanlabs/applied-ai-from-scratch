---
name: skill-voice-agent-architecture
description: Architecture reference for production voice agents - STT-LLM-TTS latency budget, barge-in state machine, phone/WebRTC integration, and testing patterns
version: "1.0"
phase: "10"
lesson: "05"
tags: [voice-agent, latency, barge-in, pipecat, streaming-tts, webrtc, phone]
---

# Voice Agent Architecture Reference

## Latency budget (target: P95 < 500ms)

| Stage | Naive (batch) | Optimized (streaming) |
|-------|--------------|----------------------|
| STT | 200-400ms | 80-150ms |
| LLM TTFT | 400-800ms | 150-350ms |
| TTS first chunk | 200-400ms | 50-120ms |
| Audio start | 100-200ms | 20-50ms |
| **Total** | **1000-1800ms** | **300-670ms** |

Optimization choices:
- STT: use Deepgram streaming (not Whisper batch)
- LLM: use claude-3-5-haiku-20241022 (not large models)
- TTS: stream sentence by sentence (not wait for full response)

## Streaming TTS pattern

```python
# Don't wait for full LLM response before starting TTS
# Stream tokens into TTS as sentences complete

class SentenceBuffer:
    ENDS = {".", "!", "?", ":", "\n"}

    def __init__(self):
        self._buf = ""

    def push(self, token: str) -> list[str]:
        self._buf += token
        if any(self._buf.rstrip().endswith(e) for e in self.ENDS):
            sentence, self._buf = self._buf.strip(), ""
            return [sentence] if len(sentence) > 5 else []
        return []

    def flush(self) -> list[str]:
        s, self._buf = self._buf.strip(), ""
        return [s] if s else []

# Usage in streaming LLM call:
buf = SentenceBuffer()
with client.messages.stream(...) as stream:
    for token in stream.text_stream:
        for sentence in buf.push(token):
            tts_synthesize_async(sentence)  # TTS starts before LLM finishes
    for sentence in buf.flush():
        tts_synthesize_async(sentence)
```

## Barge-in state machine

```
States: IDLE, LISTENING, PROCESSING, SPEAKING, HANDOFF

IDLE          --(VAD: speech detected)--> LISTENING
LISTENING     --(VAD: silence > 500ms)--> PROCESSING
LISTENING     --(timeout: 10s no speech)--> IDLE
PROCESSING    --(first audio chunk ready)--> SPEAKING
SPEAKING      --(VAD: user speech detected)--> LISTENING + cancel TTS + cancel LLM
SPEAKING      --(TTS playback complete)--> IDLE
any state     --(user says "human" / intent detected)--> HANDOFF
```

Implementation requirements for barge-in:
1. VAD runs continuously in a separate thread (even during TTS playback)
2. TTS has a cancel/interrupt method that stops streaming immediately
3. LLM streaming call is wrapped with a cancellation token

## Pipecat minimal example

```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat.services.anthropic import AnthropicLLMService
from pipecat.services.deepgram import DeepgramSTTService
from pipecat.services.openai import OpenAITTSService
from pipecat.vad.silero import SileroVADAnalyzer

transport = FastAPIWebsocketTransport(params=FastAPIWebsocketParams(
    audio_in_enabled=True,
    audio_out_enabled=True,
    vad_enabled=True,
    vad_analyzer=SileroVADAnalyzer(),  # handles barge-in detection
))

pipeline = Pipeline([
    transport.input(),
    DeepgramSTTService(api_key=DEEPGRAM_KEY),
    context_aggregator.user(),
    AnthropicLLMService(api_key=ANTHROPIC_KEY, model="claude-3-5-haiku-20241022"),
    OpenAITTSService(api_key=OPENAI_KEY, voice="nova"),
    transport.output(),
    context_aggregator.assistant(),
])
```

Pipecat handles: VAD, barge-in state machine, streaming at every stage, conversation history aggregation.

## Phone (PSTN) integration patterns

**Twilio Media Streams**: WebSocket stream of mu-law encoded audio at 8kHz.
```python
# Twilio sends audio in 20ms chunks as base64-encoded PCM
# Must transcode: mulaw 8kHz -> PCM 16kHz for Deepgram
import audioop
pcm_16k = audioop.upsample(
    audioop.ulaw2lin(mulaw_bytes, 2), 2, 8000, 16000
)
```

**Vonage / Nexmo**: similar WebSocket streaming, different codec handling.

**LiveKit**: WebRTC-native, better for web and mobile apps. Use LiveKit Agents SDK.

Recommended stack for phone agents:
- Inbound call: Twilio + WebSocket -> Deepgram STT -> Claude Haiku -> OpenAI TTS -> Twilio
- Human handoff: Twilio Conference API (bridge user + agent into same conference)

## Human handoff design

Trigger conditions:
- User explicitly requests ("let me talk to a human", "speak to an agent")
- Confidence threshold crossed (agent says "I'm not sure..." 2+ times)
- Session length > 10 turns without resolution
- Specific topic keywords (legal, billing dispute, account security)

On handoff:
1. Play acknowledgment: "Connecting you now, one moment."
2. Pause TTS and stop LLM generation
3. Transfer call (Twilio: forward to human agent number)
4. Pass session context: transcript, extracted intent, CRM data

```python
def handle_handoff(session: VoiceAgentSession):
    # Summarize session for the human agent
    import anthropic
    client = anthropic.Anthropic()
    summary = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=150,
        messages=[{
            "role": "user",
            "content": f"Summarize this call in 2-3 sentences for a human agent:\n{format_transcript(session)}"
        }]
    )
    # Pass to CRM / ticketing system
    create_ticket(summary=summary.content[0].text, transcript=format_transcript(session))
```

## Testing without a phone line

```python
def test_voice_agent_scenario(inputs: list[str]) -> VoiceAgentSession:
    """
    Inject text directly into the LLM step.
    Bypass STT and TTS for fast regression testing.
    """
    session = VoiceAgentSession()
    for user_text in inputs:
        response = generate_response(session, user_text, demo_mode=True)
        assert response  # basic smoke test
    return session

# Run 100 test scenarios in seconds
TEST_SCENARIOS = [
    (["billing question", "last invoice", "wrong amount"], "should_resolve"),
    (["I want a human", "agent please"], "should_handoff"),
    (["goodbye"], "should_end"),
]
for inputs, expected in TEST_SCENARIOS:
    session = test_voice_agent_scenario(inputs)
    print(f"{expected}: final_state={session.state.name}")
```

## Key metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| E2E latency P95 | < 500ms | VAD end to first audio byte |
| Turn completion rate | > 70% | Agent finishes speaking uninterrupted |
| Session completion | > 60% | Goal accomplished without handoff |
| ASR error propagation | < 5% | STT error causes wrong agent response |
| Handoff rate | < 20% | Sessions transferred to human |

## Production checklist

- [ ] Measure P95 latency (not mean) - users experience tail latency
- [ ] Implement barge-in before first user test (users will talk over the agent)
- [ ] Design human handoff path before launch
- [ ] Test with actual phone audio (mulaw 8kHz) if deploying to PSTN
- [ ] Set up session history persistence (users should not repeat themselves on reconnect)
- [ ] Instrument every pipeline stage with latency metrics
- [ ] Build synthetic test suite with 50+ scenario inputs for regression testing
- [ ] Define escalation keywords for automatic handoff trigger
