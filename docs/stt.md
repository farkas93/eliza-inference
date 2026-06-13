# STT

`stt` exposes an OpenAI-compatible speech-to-text endpoint that other LAN applications and Vocode can call directly.

## Endpoint

```text
POST /v1/audio/transcriptions
```

Example:

```bash
curl http://127.0.0.1:8011/v1/audio/transcriptions \
  -F model=whisper-large-v3 \
  -F file=@speech.wav
```

## Profiles

| Profile | Backend | Model |
| --- | --- | --- |
| `stt-faster-whisper-large-v3` | faster-whisper | `Systran/faster-whisper-large-v3` |
| `stt-faster-whisper-small` | faster-whisper | `Systran/faster-whisper-small` |
| `stt-whispercpp-large-v3` | whisper.cpp | Manual placeholder |

The implemented API wrapper currently supports `faster-whisper`. The whisper.cpp profile is a placeholder for a future backend wrapper.

## Commands

```bash
./scripts/download-models stt --profile stt-faster-whisper-large-v3
./scripts/start stt --profile stt-faster-whisper-large-v3
./scripts/smoke-test stt
```
