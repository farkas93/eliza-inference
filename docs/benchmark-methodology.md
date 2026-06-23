# Benchmark Methodology

Benchmark profiles instead of assuming a single best configuration.

## Qwen

```bash
./scripts/start eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k
./scripts/benchmark-context eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k --tokens 32000

./scripts/restart eliza-medium --profile medium/qwen3_6-35b-a3b-q4-llamacpp-256k
./scripts/benchmark-context eliza-medium --profile medium/qwen3_6-35b-a3b-q4-llamacpp-256k --tokens 131072

./scripts/restart eliza-medium --profile medium/qwen3_6-27b-fp8-vllm-128k
./scripts/benchmark-context eliza-medium --profile medium/qwen3_6-27b-fp8-vllm-128k --tokens 131072

./scripts/restart eliza-medium --profile medium/gemma4-26b-a4b-q4-llamacpp-256k
./scripts/benchmark-context eliza-medium --profile medium/gemma4-26b-a4b-q4-llamacpp-256k --tokens 131072
```

Compare elapsed time, success/failure, memory from `./scripts/benchmark-memory`, and qualitative output.

## Streaming

Inspect raw streaming chunks and estimate output throughput:

```bash
./scripts/benchmark-stream eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k --show-raw
./scripts/benchmark-stream eliza-medium --profile medium/qwen3_6-35b-a3b-q4-llamacpp-256k --max-tokens 1024
```

The stream benchmark records first-event latency, first-content latency, estimated output tokens/sec, and whether the endpoint sent a dedicated reasoning channel or `<think>` tags in normal content.

## Voice

```bash
./scripts/start eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k
./scripts/benchmark-latency eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k

./scripts/restart eliza-small --profile small/gemma4-e4b-q4-llamacpp-8k
./scripts/benchmark-latency eliza-small --profile small/gemma4-e4b-q4-llamacpp-8k

```

Compare average latency and quality for short spoken-assistant style prompts.
