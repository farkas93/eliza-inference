# Vocode Pipeline

The intended Vocode integration is service-oriented. Vocode should orchestrate HTTP calls to the independently hosted STT, LLM, and TTS services.

```text
Vocode microphone input
  -> STT service (:8011)
  -> eliza-small service (:8002)
  -> TTS service (:8012)
  -> Vocode speaker output
```

## Local URLs

```bash
STT_BASE_URL="http://127.0.0.1:8011/v1"
ELIZA_SMALL_BASE_URL="http://127.0.0.1:8002/v1"
TTS_BASE_URL="http://127.0.0.1:8012/v1"
```

## LAN URLs

```bash
STT_BASE_URL="http://dgx-spark:8011/v1"
ELIZA_SMALL_BASE_URL="http://dgx-spark:8002/v1"
TTS_BASE_URL="http://dgx-spark:8012/v1"
```

## Adapter Strategy

Use OpenAI-compatible Vocode adapters where possible. If Vocode does not expose base URLs cleanly for STT or TTS, add thin custom adapters that call:

```text
POST /v1/audio/transcriptions
POST /v1/chat/completions
POST /v1/audio/speech
```

Start with utterance-level STT and response-level TTS. Add streaming and barge-in after the separate services are stable.

For the Vocode experiment, see `docs/vocode-bridge.md`. The first bridge milestone validates WebSocket audio transport and hosted STT/TTS before committing to deeper Vocode internals.

## Full Pipeline Smoke Test

Before wiring live microphone/speaker Vocode adapters, test the same service boundaries over HTTP:

```bash
./scripts/start stt --profile stt/faster-whisper-small-cpu
./scripts/start eliza-small --profile small/gemma4-e2b-fast
./scripts/start tts --profile tts/piper-lessac
./scripts/smoke-test voice-assistant --profile voice/assistant-local
```

The `voice-assistant` smoke test does not use a live microphone. It performs a deterministic end-to-end pipeline:

```text
input text
  -> TTS creates prompt WAV
  -> STT transcribes prompt WAV
  -> eliza-small answers transcript
  -> TTS creates response WAV
```

The response audio is written to:

```text
tmp/voice-pipeline-response.wav
```

If this passes, the hosted components are ready for Vocode adapter work. If this fails, debug the individual services first:

```bash
./scripts/smoke-test stt
./scripts/smoke-test eliza-small
./scripts/smoke-test tts
```
