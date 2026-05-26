---
name: skill-realtime-latency-tuning
description: Voice pipeline latency budget reference with per-stage optimization techniques, streaming architecture checklist, and SLO definitions for interactive voice systems.
version: "1.0"
phase: "10"
lesson: "06"
tags: [voice, latency, streaming, tts, stt, realtime]
---

# Skill: Realtime Voice Latency Tuning

## Latency Budget Reference

### Interactive Voice (call center, realtime assistant)

| Metric | Target | Alert |
|--------|--------|-------|
| P50 end-to-end | < 400ms | - |
| P95 end-to-end | < 600ms | > 800ms |
| P99 end-to-end | < 900ms | > 1200ms |

### Voice Search / Query Answering

| Metric | Target | Alert |
|--------|--------|-------|
| P50 end-to-end | < 600ms | - |
| P95 end-to-end | < 900ms | > 1200ms |

### Voice Narration (non-interactive)

| Metric | Target | Alert |
|--------|--------|-------|
| P50 end-to-end | < 1000ms | - |
| P95 end-to-end | < 1500ms | > 2000ms |

---

## Per-Stage Breakdown and Optimization

### Stage 1: STT Endpoint Detection (VAD)

Typical P50: 80-150ms

**Optimizations:**
- Tune VAD sensitivity: lower sensitivity reduces false pause detections
- Use server-side VAD when available (reduces a round trip)
- Target: < 100ms P50

### Stage 2: STT Model Inference

Typical P50: 100-250ms

**Optimizations:**
- Use streaming STT (WebSocket): start processing audio mid-utterance
- Choose a faster STT tier: Deepgram Nova-2 < Whisper large-v3 in latency
- Run STT in the same cloud region as your LLM
- Target: < 150ms P50

**Provider approximate latency (streaming, US East):**

| Provider | Model | Approx P50 |
|----------|-------|------------|
| Deepgram | Nova-2 streaming | 80-120ms |
| AssemblyAI | Nano streaming | 100-150ms |
| OpenAI | Whisper (non-streaming) | 300-600ms |

### Stage 3: Network RTT to LLM

Typical P50: 20-80ms

**Optimizations:**
- Co-locate your voice server and LLM API in the same cloud region
- US East + Anthropic US East: ~15-25ms RTT
- US West + Anthropic US East: ~60-80ms RTT
- Use connection pooling (keep HTTP/2 connections alive)

### Stage 4: LLM Time-to-First-Token (TTFT)

Typical P50: 150-600ms (highest variance stage)

**Optimizations:**

1. **Prompt caching** (highest impact, free): Cache the system prompt with Claude. Cached tokens are processed 10x faster. A 500-token system prompt uncached costs ~200ms. Cached: ~30ms.

   ```python
   # Mark system prompt for caching
   system = [
       {
           "type": "text",
           "text": your_system_prompt,
           "cache_control": {"type": "ephemeral"}
       }
   ]
   ```

2. **Model selection by turn complexity:**

   | Turn type | Recommended model | Approx TTFT P50 |
   |-----------|------------------|-----------------|
   | Simple Q&A, navigation | claude-3-5-haiku-20241022 | 150-250ms |
   | Reasoning, multi-step | claude-sonnet-4-5 | 250-500ms |
   | Complex analysis | claude-opus-4-5 | 400-800ms |

3. **Max tokens control:** Set `max_tokens` to the minimum needed. Lower max_tokens can reduce TTFT on some models.

4. **Conversation history pruning:** Long conversation history increases prefill cost. Keep only the last 4-6 turns for interactive voice.

### Stage 5: TTS Synthesis Start (TTFB)

Typical P50: 80-200ms

**Optimizations:**
- Use TTS streaming (not batch): request audio as a stream, start playback on first chunk
- Shorter input = faster start: dispatch sentences individually, not full paragraphs
- Cache common phrases (greetings, acknowledgments) as pre-rendered audio files

**Provider approximate TTFB:**

| Provider | Model | Approx TTFB |
|----------|-------|-------------|
| OpenAI | tts-1 (optimized) | 80-150ms |
| ElevenLabs | Flash v2.5 | 75-120ms |
| PlayHT | 2.0 turbo | 100-180ms |
| Cartesia | Sonic | 50-100ms |

### Stage 6: Audio Playback Start

Typical P50: 20-50ms

**Optimizations:**
- Pre-buffer: collect 2-3 audio chunks before starting playback (prevents glitches)
- Use raw PCM format when possible (skip MP3 decode overhead)
- Client-side: start playback thread before first chunk arrives

---

## Streaming Architecture Checklist

Use this checklist when implementing a minimum-latency voice pipeline:

- [ ] STT uses WebSocket streaming (not REST batch)
- [ ] STT sends partial results to allow early VAD
- [ ] LLM system prompt is marked for prompt caching
- [ ] LLM model is appropriate for turn complexity (Haiku for simple turns)
- [ ] LLM output is consumed token by token (streaming enabled)
- [ ] Sentence boundary detection is implemented (`.`, `!`, `?`)
- [ ] Each complete sentence is dispatched to TTS immediately
- [ ] TTS uses streaming mode (not wait for full audio file)
- [ ] Audio playback starts on first TTS chunk, not after full response
- [ ] Conversation history is pruned to last N turns
- [ ] All API calls use connection pooling / persistent connections
- [ ] Voice server and all API providers are in the same cloud region

---

## Geographic Routing Strategy

Deploy voice servers close to both users and API providers:

```
US users:       Deploy in us-east-1 (AWS) or us-central1 (GCP)
EU users:       Deploy in eu-west-1 (AWS) or europe-west1 (GCP)
APAC users:     Deploy in ap-southeast-1 (AWS) or asia-southeast1 (GCP)

Anthropic API endpoints: us-east-1 and eu-west-3
OpenAI API endpoints:    us-east-1 and eu-west-3
Deepgram:                Multi-region, auto-routed
```

For > 10,000 daily users: use a CDN or anycast routing to direct each user to the nearest voice server. LiveKit Cloud handles this automatically.

---

## SLO Template

```yaml
slos:
  - name: voice_interactive_p95
    description: P95 end-to-end voice latency for interactive assistant
    metric: voice_turn_latency_ms
    percentile: 95
    target_ms: 600
    alert_ms: 800
    window: 1h
    evaluation_period: 5m
    on_breach:
      - page: on-call-voice
      - action: check_bottleneck_stage

  - name: voice_interactive_p50
    description: P50 (median) latency - tracks typical user experience
    metric: voice_turn_latency_ms
    percentile: 50
    target_ms: 400
    alert_ms: 550
    window: 1h
    evaluation_period: 5m
```

---

## Regression Testing Protocol

On every deploy that touches the voice pipeline:

1. Run profiler against synthetic data: `python main.py --demo --n 500`
2. Compare P95 streaming latency against baseline (stored in CI artifacts)
3. If P95 increases > 50ms, fail the deploy gate
4. After deploy, replay 100 real production turns from the previous hour
5. Compare per-stage P50 before and after

---

## When to Escalate

| Symptom | Action |
|---------|--------|
| LLM TTFT P95 > 400ms with prompt caching | Switch to Haiku for this turn type |
| STT P95 > 300ms | Evaluate Deepgram Nova-2 vs current provider |
| TTS TTFB P95 > 200ms | Evaluate Cartesia Sonic or ElevenLabs Flash |
| P95 passes SLO but users still complain | Check P99 and max latency (tail latency) |
| Latency fine but audio quality poor | Sentence splitting is too aggressive |
