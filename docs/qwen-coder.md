# Qwen Coder

`qwen-coder` serves `Qwen/Qwen3.6-27B-FP8` through vLLM.

## Profiles

| Profile | Context | KV Cache | Memory Utilization | Use |
| --- | ---: | --- | ---: | --- |
| `qwen-shared-128k` | `128000` | auto | `0.50` | Safer shared baseline |
| `qwen-shared-200k` | `200000` | auto | `0.50` | Default target |
| `qwen-shared-200k-fp8kv` | `200000` | fp8 | `0.50` | KV memory comparison |
| `qwen-solo-262k` | `262144` | auto | `0.75` | Full native context, solo mode |

## Start

```bash
./scripts/start qwen-coder --profile qwen-shared-200k
./scripts/smoke-test qwen-coder
```

## Benchmark

```bash
./scripts/benchmark-context qwen-coder --profile qwen-shared-200k --tokens 200000
./scripts/benchmark-memory
```

FP8 KV cache is a profile to benchmark, not a guaranteed default. On DGX Spark, unified-memory bandwidth and backend behavior can make unquantized KV faster for some workloads.
