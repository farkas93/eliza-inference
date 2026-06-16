# Benchmark Methodology

Benchmark profiles instead of assuming a single best configuration.

## Qwen

```bash
./scripts/start eliza-medium --profile eliza-medium-qwen-llamacpp-32k
./scripts/benchmark-context eliza-medium --profile eliza-medium-qwen-llamacpp-32k --tokens 32000

./scripts/restart eliza-medium --profile eliza-medium-qwen36-35b-a3b-llamacpp-200k-experimental
./scripts/benchmark-context eliza-medium --profile eliza-medium-qwen36-35b-a3b-llamacpp-200k-experimental --tokens 128000

./scripts/restart eliza-medium --profile eliza-medium-qwen-vllm-128k-experimental
./scripts/benchmark-context eliza-medium --profile eliza-medium-qwen-vllm-128k-experimental --tokens 128000

./scripts/restart eliza-medium --profile eliza-medium-gemma4-26b-a4b-llamacpp-256k-experimental
./scripts/benchmark-context eliza-medium --profile eliza-medium-gemma4-26b-a4b-llamacpp-256k-experimental --tokens 128000
```

Compare elapsed time, success/failure, memory from `./scripts/benchmark-memory`, and qualitative output.

## Voice

```bash
./scripts/start eliza-small --profile eliza-small-gemma4-e2b-fast
./scripts/benchmark-latency eliza-small --profile eliza-small-gemma4-e2b-fast

./scripts/restart eliza-small --profile eliza-small-gemma4-e4b-quality
./scripts/benchmark-latency eliza-small --profile eliza-small-gemma4-e4b-quality

```

Compare average latency and quality for short spoken-assistant style prompts.
