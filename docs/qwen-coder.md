# Qwen Coder

`qwen-coder` is llama.cpp-first on DGX Spark. vLLM profiles remain available for experimental GB10 work, but the operational default is GGUF via llama.cpp.

The initial llama.cpp profile uses Unsloth's dynamic quantized `Qwen3.6-27B-UD-Q4_K_XL.gguf` file.

## Profiles

| Profile | Runtime | Context | Use |
| --- | --- | ---: | --- |
| `qwen-llamacpp-32k` | llama.cpp | `32768` | First Qwen GGUF compatibility test |
| `vllm-smoke-tinyllama` | vLLM | `2048` | Experimental vLLM runtime sanity test |
| `qwen-smoke-8k` | vLLM | `8192` | Experimental vLLM/Qwen compatibility test |
| `qwen-smoke-32k` | vLLM | `32768` | Experimental vLLM/Qwen step-up test |
| `qwen-shared-128k` | vLLM | `128000` | Experimental vLLM long-context baseline |
| `qwen-shared-200k` | vLLM | `200000` | Experimental vLLM target |
| `qwen-shared-200k-fp8kv` | vLLM | `200000` | Experimental vLLM KV comparison |
| `qwen-solo-262k` | vLLM | `262144` | Experimental full native context |

## Start

```bash
./scripts/download-models qwen-coder --profile qwen-llamacpp-32k
./scripts/start qwen-coder --profile qwen-llamacpp-32k
./scripts/smoke-test qwen-coder --profile qwen-llamacpp-32k
```

Start with `qwen-llamacpp-32k`. If that works, add/test larger llama.cpp context profiles before revisiting vLLM.

If Qwen/Gemma vLLM profiles hang during model load, treat vLLM as experimental on GB10. The current practical path is llama.cpp GGUF.

To remove local vLLM state and stop stale Qwen vLLM sessions:

```bash
./scripts/cleanup-vllm
```

## Benchmark

```bash
./scripts/benchmark-context qwen-coder --profile qwen-llamacpp-32k --tokens 32000
./scripts/benchmark-memory
```

FP8 KV cache is a profile to benchmark, not a guaranteed default. On DGX Spark, unified-memory bandwidth and backend behavior can make unquantized KV faster for some workloads.
