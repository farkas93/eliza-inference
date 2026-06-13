# TTS

`tts` exposes an OpenAI-compatible text-to-speech endpoint backed by Piper.

## Endpoint

```text
POST /v1/audio/speech
```

Example:

```bash
curl http://127.0.0.1:8012/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"piper-lessac-medium","voice":"lessac","input":"Hello from DGX Spark.","response_format":"wav"}' \
  --output speech.wav
```

## Profiles

| Profile | Backend | Voice |
| --- | --- | --- |
| `tts-piper-lessac` | Piper | `en_US-lessac-medium` |
| `tts-piper-amy` | Piper | `en_US-amy-medium` |

## Commands

```bash
./scripts/download-models tts --profile tts-piper-lessac
./scripts/start tts --profile tts-piper-lessac
./scripts/smoke-test tts
```

`piper` must be available on `PATH`, or set `PIPER_BIN` in `.env`.
