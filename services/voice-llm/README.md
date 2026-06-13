# voice-llm

Gemma voice LLM endpoint with pluggable llama.cpp and vLLM backends.

Default profile: `voice-gemma4-e4b-default`.

```bash
./scripts/start voice-llm --profile voice-gemma4-e4b-default
./scripts/smoke-test voice-llm
```

The voice assistant loop should call this service through its OpenAI-compatible `/v1` API.
