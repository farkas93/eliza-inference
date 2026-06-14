# Eliza Medium

`eliza-medium` is the larger, more capable local model service intended for coding, reasoning, and longer-context tasks. It is model/runtime agnostic at the service boundary. The default profile is llama.cpp with Qwen 3.6 27B GGUF.

The initial llama.cpp profile uses Unsloth's dynamic quantized `Qwen3.6-27B-UD-Q4_K_XL.gguf` file.

## Profiles

| Profile | Runtime | Context | Use |
| --- | --- | ---: | --- |
| `eliza-medium-qwen-llamacpp-32k` | llama.cpp | `32768` | Default compatibility profile |
| `eliza-medium-vllm-smoke-tinyllama` | vLLM | `2048` | Experimental vLLM runtime sanity test |
| `eliza-medium-qwen-vllm-smoke-8k` | vLLM | `8192` | Experimental vLLM/Qwen compatibility test |
| `eliza-medium-qwen-vllm-smoke-32k` | vLLM | `32768` | Experimental vLLM/Qwen step-up test |
| `eliza-medium-qwen-vllm-128k-experimental` | vLLM | `128000` | Experimental vLLM long-context baseline |
| `eliza-medium-qwen-vllm-200k-experimental` | vLLM | `200000` | Experimental vLLM target |
| `eliza-medium-qwen-vllm-200k-fp8kv-experimental` | vLLM | `200000` | Experimental vLLM KV comparison |
| `eliza-medium-qwen-vllm-262k-experimental` | vLLM | `262144` | Experimental full native context |

## Start

```bash
./scripts/download-models eliza-medium --profile eliza-medium-qwen-llamacpp-32k
./scripts/start eliza-medium --profile eliza-medium-qwen-llamacpp-32k
./scripts/smoke-test eliza-medium --profile eliza-medium-qwen-llamacpp-32k
```

Start with `eliza-medium-qwen-llamacpp-32k`. If that works, add/test larger llama.cpp context profiles before revisiting vLLM.

To remove local vLLM state and stop stale vLLM sessions:

```bash
./scripts/cleanup-vllm
```

## Benchmark

```bash
./scripts/benchmark-context eliza-medium --profile eliza-medium-qwen-llamacpp-32k --tokens 32000
./scripts/benchmark-memory
```
