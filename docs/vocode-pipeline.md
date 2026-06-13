# Vocode Pipeline

The intended Vocode integration is service-oriented. Vocode should orchestrate HTTP calls to the independently hosted STT, LLM, and TTS services.

```text
Vocode microphone input
  -> STT service (:8011)
  -> Voice LLM service (:8002)
  -> TTS service (:8012)
  -> Vocode speaker output
```

## Local URLs

```bash
STT_BASE_URL="http://127.0.0.1:8011/v1"
VOICE_LLM_BASE_URL="http://127.0.0.1:8002/v1"
TTS_BASE_URL="http://127.0.0.1:8012/v1"
```

## LAN URLs

```bash
STT_BASE_URL="http://dgx-spark:8011/v1"
VOICE_LLM_BASE_URL="http://dgx-spark:8002/v1"
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
