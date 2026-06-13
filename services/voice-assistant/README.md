# voice-assistant

Placeholder for the Vocode orchestration layer.

The model runtimes are intentionally separate services:

```text
STT:       http://127.0.0.1:8011/v1
Voice LLM: http://127.0.0.1:8002/v1
TTS:       http://127.0.0.1:8012/v1
```

Vocode should use adapters that call those endpoints rather than embedding STT/TTS/LLM runtimes directly.
