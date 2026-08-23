# Benchmark Methodology

Benchmark profiles instead of assuming a single best configuration.

## Qwen

```bash
./scripts/start eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k --context-tokens 32768

./scripts/restart eliza-medium --profile medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k --context-tokens 131072

./scripts/restart eliza-medium --profile medium/qwen3.6-27b-nvfp4-vllm-256k
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/qwen3.6-27b-nvfp4-vllm-256k --context-tokens 131072

./scripts/restart eliza-medium --profile medium/gemma4-26b-a4b-q4-llamacpp-256k
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/gemma4-26b-a4b-q4-llamacpp-256k --context-tokens 131072
```

Compare elapsed time, success/failure, and memory snapshots from `./scripts/run-benchmark memory-footprint ...`.

## Streaming

Inspect raw streaming chunks and estimate output throughput:

```bash
./scripts/run-benchmark token-generation eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k --show-raw
./scripts/run-benchmark token-generation eliza-medium --profile medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k --max-tokens 1024
```

The stream benchmark records first-event latency, first-content latency, estimated output tokens/sec, and whether the endpoint sent a dedicated reasoning channel or `<think>` tags in normal content.

## Voice

```bash
./scripts/start eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k
./scripts/run-benchmark voice-latency eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k

./scripts/restart eliza-small --profile small/gemma4-e4b-q4-llamacpp-8k
./scripts/run-benchmark voice-latency eliza-small --profile small/gemma4-e4b-q4-llamacpp-8k

```

Compare average latency and quality for short spoken-assistant style prompts.
