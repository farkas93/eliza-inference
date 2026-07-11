# eliza-small

Low-latency model endpoint for voice turns, with pluggable llama.cpp and experimental vLLM backends.

Default profile: `small/gemma4-e2b-q4-llamacpp-8k`.

```bash
./scripts/start eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k
./scripts/smoke-test eliza-small

# long-context variant for tool-heavy voice prompts
./scripts/start eliza-small --profile small/gemma4-e2b-q4-llamacpp-128k
./scripts/smoke-test eliza-small --profile small/gemma4-e2b-q4-llamacpp-128k
```

The voice assistant loop should call this service through its OpenAI-compatible `/v1` API.
