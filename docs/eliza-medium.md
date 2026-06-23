# Eliza Medium

`eliza-medium` is the larger, more capable local model service intended for coding, reasoning, and longer-context tasks. It is model/runtime agnostic at the service boundary. The default profile is llama.cpp with Qwen 3.6 27B GGUF.

The initial llama.cpp profile uses Unsloth's dynamic quantized `Qwen3.6-27B-UD-Q4_K_XL.gguf` file.

## Profiles

| Profile | Runtime | Context | Use |
| --- | --- | ---: | --- |
| `medium/qwen-llamacpp-32k` | llama.cpp | `32768` | Default compatibility profile |
| `medium/qwen-llamacpp-128k` | llama.cpp | `128000` | Larger context test using the default UD-Q4_K_XL GGUF |
| `medium/gemma4-26b-a4b-llamacpp-256k-experimental` | llama.cpp | `256000` | Experimental Gemma 4 26B A4B long-context profile |
| `medium/qwen-q6-llamacpp-32k` | llama.cpp | `32768` | Higher precision Q6 quality comparison |
| `medium/qwen-q8-llamacpp-32k` | llama.cpp | `32768` | Highest precision GGUF quality comparison |
| `medium/vllm-smoke-tinyllama` | vLLM | `2048` | Experimental vLLM runtime sanity test |
| `medium/qwen-vllm-smoke-8k` | vLLM | `8192` | Experimental vLLM/Qwen compatibility test |
| `medium/qwen-vllm-smoke-32k` | vLLM | `32768` | Experimental vLLM/Qwen step-up test |
| `medium/qwen-vllm-128k-experimental` | vLLM | `128000` | Experimental vLLM long-context baseline |
| `medium/qwen-vllm-200k-experimental` | vLLM | `200000` | Experimental vLLM target |
| `medium/qwen-vllm-200k-fp8kv-experimental` | vLLM | `200000` | Experimental vLLM KV comparison |
| `medium/qwen36-35b-a3b-llamacpp-200k-experimental` | llama.cpp | `200000` | Experimental Qwen3.6 35B A3B profile |
| `medium/qwen-vllm-262k-experimental` | vLLM | `262144` | Experimental full native context |

## Start

```bash
./scripts/download-models eliza-medium --profile medium/qwen-llamacpp-32k
./scripts/start eliza-medium --profile medium/qwen-llamacpp-32k
./scripts/smoke-test eliza-medium --profile medium/qwen-llamacpp-32k
```

Start with `medium/qwen-llamacpp-32k`. If that works, add/test larger llama.cpp context profiles before revisiting vLLM.

Suggested llama.cpp test ladder:

```bash
./scripts/download-models eliza-medium --profile medium/qwen-llamacpp-32k
./scripts/start eliza-medium --profile medium/qwen-llamacpp-32k
./scripts/smoke-test eliza-medium --profile medium/qwen-llamacpp-32k

./scripts/restart eliza-medium --profile medium/qwen-llamacpp-128k
./scripts/smoke-test eliza-medium --profile medium/qwen-llamacpp-128k
./scripts/benchmark-context eliza-medium --profile medium/qwen-llamacpp-128k --tokens 32000
./scripts/benchmark-context eliza-medium --profile medium/qwen-llamacpp-128k --tokens 128000
```

For higher precision, download and test Q6/Q8 at 32K before trying large contexts:

```bash
./scripts/download-models eliza-medium --profile medium/qwen-q6-llamacpp-32k
./scripts/restart eliza-medium --profile medium/qwen-q6-llamacpp-32k
./scripts/smoke-test eliza-medium --profile medium/qwen-q6-llamacpp-32k
```

To remove local vLLM state and stop stale vLLM sessions:

```bash
./scripts/cleanup-vllm
```

## Benchmark

```bash
./scripts/benchmark-context eliza-medium --profile medium/qwen-llamacpp-32k --tokens 32000
./scripts/benchmark-memory
```
