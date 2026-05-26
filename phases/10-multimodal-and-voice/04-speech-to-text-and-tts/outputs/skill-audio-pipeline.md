---
name: skill-audio-pipeline
description: Production reference for STT and TTS pipelines - provider selection, chunking for long audio, WER measurement, voice selection, and cost estimates
version: "1.0"
phase: "10"
lesson: "04"
tags: [speech-to-text, text-to-speech, whisper, deepgram, tts, wer, audio]
---

# Audio Pipeline Reference

## STT provider selection guide

| Need | Best provider |
|------|---------------|
| Simple batch transcription, lowest cost | Deepgram Nova-2 |
| Technical/domain-specific vocabulary | Whisper (OpenAI) |
| Speaker diarization (who said what) | AssemblyAI or Deepgram |
| Real-time streaming + diarization | Deepgram Nova-2 |
| HIPAA compliance | AssemblyAI or Deepgram (check BAA availability) |

## STT cost per hour

| Provider | Cost/min | Cost/hour |
|----------|---------|----------|
| Whisper (OpenAI) | $0.006 | $0.36 |
| Deepgram Nova-2 | $0.004 | $0.24 |
| AssemblyAI | $0.012 | $0.72 |
| Google STT v2 | $0.016 | $0.96 |

## Long audio chunking pattern

```python
from pydub import AudioSegment
from pydub.silence import split_on_silence
from pathlib import Path

MAX_BYTES = 24 * 1024 * 1024  # 24MB (Whisper API limit: 25MB)

def chunk_and_transcribe(audio_path: Path) -> str:
    if audio_path.stat().st_size <= MAX_BYTES:
        return transcribe_file(audio_path)

    audio = AudioSegment.from_file(audio_path)
    chunks = split_on_silence(
        audio,
        min_silence_len=500,   # 500ms silence minimum
        silence_thresh=-40,     # dBFS
        keep_silence=200,       # 200ms buffer
    )

    # Merge into ~10-min segments
    segments, current = [], None
    for chunk in chunks:
        if current is None:
            current = chunk
        elif len(current) + len(chunk) < 600_000:  # 10 min in ms
            current += chunk
        else:
            segments.append(current)
            current = chunk
    if current:
        segments.append(current)

    texts = []
    for i, seg in enumerate(segments):
        tmp = Path(f"/tmp/chunk_{i}.mp3")
        seg.export(tmp, format="mp3")
        texts.append(transcribe_file(tmp))
        tmp.unlink()

    return " ".join(texts)
```

## Audio format reference

| Format | Browser source | Whisper | Notes |
|--------|---------------|---------|-------|
| WebM/Opus | Chrome MediaRecorder | Yes | Default browser recording format |
| MP3 | Encoding step | Yes | Best for storage |
| WAV | Microphone raw | Yes | Lossless, large files |
| M4A | iOS recordings | Yes | Common mobile format |
| FLAC | Studio recordings | No | Must transcode first |

Transcode with ffmpeg:
```bash
ffmpeg -i input.webm -ar 16000 -ac 1 output.mp3
```

## Speaker diarization options

**Option A: AssemblyAI (best quality)**
```python
import assemblyai as aai
config = aai.TranscriptionConfig(speaker_labels=True)
transcript = aai.Transcriber().transcribe("call.mp3", config)
for utt in transcript.utterances:
    print(f"Speaker {utt.speaker}: {utt.text}")
```

**Option B: Deepgram (built-in, real-time capable)**
```python
# Add ?diarize=true to WebSocket URL or REST request
# Returns words with speaker: 0, speaker: 1, etc.
```

**Option C: Whisper + pyannote.audio (self-hosted)**
```python
# Transcribe with Whisper, then align speaker diarization with pyannote
# Requires a Hugging Face token for pyannote model access
```

## WER calculation

```python
def word_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = reference.lower().split(), hypothesis.lower().split()
    n = len(ref)
    if not n:
        return 0.0
    dp = list(range(len(hyp) + 1))
    for r in ref:
        new_dp = [dp[0] + 1] + [0] * len(hyp)
        for j, h in enumerate(hyp):
            if r == h:
                new_dp[j+1] = dp[j]
            else:
                new_dp[j+1] = 1 + min(dp[j], dp[j+1], new_dp[j])
        dp = new_dp
    return dp[-1] / n
```

WER targets by use case:
- Search indexing: < 10% acceptable
- Customer service transcripts: < 7% target
- Legal records: < 3% required (human review recommended)
- Medical documentation: < 2% required (specialized models + review)

## TTS provider selection

| Need | Best provider |
|------|---------------|
| Fast, simple, general purpose | OpenAI TTS |
| Highest naturalness for customer-facing | ElevenLabs |
| SSML control (pauses, emphasis, pitch) | Google Cloud TTS |
| Voice cloning | ElevenLabs |
| High-volume batch synthesis | Google Cloud TTS (cheapest at scale) |

## TTS cost comparison

| Provider | Cost/1k chars | Cost for 500-word message (~3,000 chars) |
|----------|--------------|------------------------------------------|
| OpenAI TTS-1 | $0.015 | $0.045 |
| OpenAI TTS-1 HD | $0.030 | $0.090 |
| ElevenLabs | $0.180 | $0.540 |
| Google Cloud TTS | $0.004 | $0.012 |
| Azure Neural TTS | $0.008 | $0.024 |

## OpenAI TTS voice guide

| Voice | Character | Best for |
|-------|-----------|----------|
| alloy | Neutral, balanced | Notifications, general purpose |
| echo | Masculine, clear | Technical content |
| fable | Warm, expressive | Customer service |
| onyx | Deep, authoritative | Business communication |
| nova | Warm, friendly | Customer-facing voice agents |
| shimmer | Soft, pleasant | Healthcare, calm applications |

## Production checklist

- [ ] Implement chunking for any audio > 20MB before sending to Whisper API
- [ ] Test your actual audio samples against multiple STT providers before choosing
- [ ] Build a WER golden set with 10-20 labeled samples from production audio
- [ ] Log transcription duration, word count, and cost per call
- [ ] Decide upfront whether speaker diarization is required (changes provider choice)
- [ ] Download generated TTS audio to your own storage rather than serving provider URLs
- [ ] Set a monthly alert on Deepgram/AssemblyAI usage if volume is unpredictable
