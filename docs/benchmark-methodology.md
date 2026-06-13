# Benchmark Methodology

Benchmark profiles instead of assuming a single best configuration.

## Qwen

```bash
./scripts/start qwen-coder --profile qwen-shared-128k
./scripts/benchmark-context qwen-coder --profile qwen-shared-128k --tokens 128000

./scripts/restart qwen-coder --profile qwen-shared-200k
./scripts/benchmark-context qwen-coder --profile qwen-shared-200k --tokens 200000
```

Compare elapsed time, success/failure, memory from `./scripts/benchmark-memory`, and qualitative output.

## Voice

```bash
./scripts/start voice-llm --profile voice-gemma4-e4b-default
./scripts/benchmark-latency voice-llm --profile voice-gemma4-e4b-default

./scripts/restart voice-llm --profile voice-gemma4-e2b-fast
./scripts/benchmark-latency voice-llm --profile voice-gemma4-e2b-fast
```

Compare average latency and quality for short spoken-assistant style prompts.
