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
| `stt/faster-whisper-small-cpu` | faster-whisper | `Systran/faster-whisper-small`, CPU int8 |
| `stt/faster-whisper-large-v3-cpu` | faster-whisper | `Systran/faster-whisper-large-v3`, CPU int8 |
| `stt/faster-whisper-large-v3` | faster-whisper | `Systran/faster-whisper-large-v3` |
| `stt/faster-whisper-small` | faster-whisper | `Systran/faster-whisper-small` |
| `stt/whispercpp-large-v3` | whisper.cpp | Manual placeholder |

The implemented API wrapper currently supports `faster-whisper`. The whisper.cpp profile is a placeholder for a future backend wrapper.

The default STT profile is CPU `int8` because the PyPI CTranslate2 wheel may be CPU-only on DGX Spark. GPU profiles are available for environments with a CUDA-enabled CTranslate2 build.

## Commands

```bash
./scripts/install-stt --profile stt/faster-whisper-small-cpu
./scripts/start stt --profile stt/faster-whisper-small-cpu
./scripts/smoke-test stt
```
