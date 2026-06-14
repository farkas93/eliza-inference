# voice-assistant

Placeholder for the Vocode orchestration layer.

The model runtimes are intentionally separate services:

```text
STT:       http://127.0.0.1:8011/v1
Eliza Small: http://127.0.0.1:8002/v1
TTS:       http://127.0.0.1:8012/v1
```

Vocode should use adapters that call those endpoints rather than embedding STT/TTS/LLM runtimes directly.

Run the hosted-service pipeline smoke test:

```bash
./scripts/smoke-test voice-assistant --profile voice-assistant-local
```

This creates a synthetic prompt WAV through TTS, transcribes it through STT, sends the transcript to the voice LLM, and synthesizes the assistant response.
