# eliza-small

Low-latency model endpoint for voice turns, with pluggable llama.cpp and experimental vLLM backends.

Default profile: `small/gemma4-e2b-q4-llamacpp-8k`.

```bash
./scripts/start eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k
./scripts/smoke-test eliza-small
```

The voice assistant loop should call this service through its OpenAI-compatible `/v1` API.
