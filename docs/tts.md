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
| `tts/piper-lessac` | Piper | `en_US-lessac-medium` |
| `tts/piper-amy` | Piper | `en_US-amy-medium` |

## Commands

```bash
./scripts/setup tts --backend piper --profile tts/piper-lessac
./scripts/start tts --profile tts/piper-lessac
./scripts/smoke-test tts
```

`install-tts` installs `piper-tts` into `.venvs/tts`, downloads the selected voice, and verifies synthesis by writing:

```text
tmp/piper-install-test.wav
```

If the installer prints a `PIPER_BIN=...` line, add it to `.env`.

The TTS smoke test writes:

```text
tmp/tts-smoke-test.wav
```

If the Spark has local audio output, play it with:

```bash
aplay tmp/tts-smoke-test.wav
```

## Piper Notes

The current installer uses the modern `piper-tts` Python package from the Open Home Foundation Piper project. That package is GPL-3.0-or-later. The older Rhasspy Piper repository is archived; it can still be used manually, but it is not the default installer path.
