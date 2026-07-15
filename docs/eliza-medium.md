# Eliza Medium

`eliza-medium` is the larger, more capable local model service intended for coding, reasoning, and longer-context tasks. It is model/runtime agnostic at the service boundary. The default profile is DS4 with `deepseek-v4-flash` (DeepSeek V4 Flash via the DS4 server, 256k context).

## Profiles

| Profile | Runtime | Context | Use |
| --- | --- | ---: | --- |
| `medium/openpangu-2_0-flash-q4-llamacpp-256k` | llama.cpp | `262144` | Alternative openPangu profile |
| `medium/openpangu-2_0-flash-q4-llamacpp-512k` | llama.cpp | `524288` | Max-context profile (capacity test) |
| `medium/openpangu-2_0-flash-q4-llamacpp-20k` | llama.cpp | `20480` | Conservative stability fallback |
| `medium/qwen3_6-27b-q4-llamacpp-32k` | llama.cpp | `32768` | Default compatibility profile |
| `medium/qwen3_6-27b-q4-llamacpp-128k` | llama.cpp | `131072` | Larger context test using the default Q4 GGUF |
| `medium/gemma4-26b-a4b-q4-llamacpp-256k` | llama.cpp | `262144` | Gemma 4 26B A4B long-context profile |
| `medium/qwen3_6-27b-q6-llamacpp-32k` | llama.cpp | `32768` | Higher precision Q6 comparison |
| `medium/qwen3_6-27b-q8-llamacpp-32k` | llama.cpp | `32768` | Higher precision Q8 comparison |
| `medium/tinyllama-1_1b-vllm-2k` | vLLM | `2048` | vLLM runtime sanity profile |
| `medium/qwen3_6-27b-fp8-vllm-8k` | vLLM | `8192` | vLLM/Qwen compatibility test |
| `medium/qwen3_6-27b-fp8-vllm-32k` | vLLM | `32768` | vLLM/Qwen step-up test |
| `medium/qwen3_6-27b-fp8-vllm-128k` | vLLM | `131072` | vLLM long-context baseline |
| `medium/qwen3_6-27b-fp8-vllm-256k` | vLLM | `262144` | vLLM 256K target |
| `medium/qwen3_6-27b-fp8-vllm-256k-kvfp8` | vLLM | `262144` | vLLM KV fp8 comparison |
| `medium/qwen3.6-35b-a3b-q4-llamacpp-256k` | llama.cpp | `262144` | Default long-context profile |
| `medium/qwen3_6-27b-fp8-vllm-256k-native` | vLLM | `262144` | vLLM native max-context profile |
| `medium/deepseek-v4-flash-ds4-256k` | ds4 | `262144` | Default DS4 256K long-context profile |

## Start

```bash
# Default profile (DS4 deepseek-v4-flash)
./scripts/start eliza-medium
./scripts/smoke-test eliza-medium

# Explicit profile selection
./scripts/start eliza-medium --profile medium/deepseek-v4-flash-ds4-256k
./scripts/smoke-test eliza-medium --profile medium/deepseek-v4-flash-ds4-256k
```

Start with the default DS4 profile. For llama.cpp alternatives, use an explicit profile:

```bash
./scripts/start eliza-medium --profile medium/qwen3.6-35b-a3b-q4-llamacpp-256k
./scripts/smoke-test eliza-medium --profile medium/qwen3.6-35b-a3b-q4-llamacpp-256k
```

openPangu alternative profile and max-context sweep:

Max-context sweep for openPangu:

```bash
./scripts/restart eliza-medium --profile medium/openpangu-2_0-flash-q4-llamacpp-512k
./scripts/smoke-test eliza-medium --profile medium/openpangu-2_0-flash-q4-llamacpp-512k
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/openpangu-2_0-flash-q4-llamacpp-512k --context-tokens-list 131072,196608,262144,327680,393216,458752,524288
```

Suggested llama.cpp test ladder:

```bash
./scripts/download-models eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k
./scripts/start eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k
./scripts/smoke-test eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k

./scripts/restart eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-128k
./scripts/smoke-test eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-128k
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-128k --context-tokens-list 32768,131072
```

For higher precision, download and test Q6/Q8 at 32K before trying large contexts:

```bash
./scripts/download-models eliza-medium --profile medium/qwen3_6-27b-q6-llamacpp-32k
./scripts/restart eliza-medium --profile medium/qwen3_6-27b-q6-llamacpp-32k
./scripts/smoke-test eliza-medium --profile medium/qwen3_6-27b-q6-llamacpp-32k
```

To remove local vLLM state and stop stale vLLM sessions:

```bash
./scripts/cleanup-vllm
```

## Benchmark

```bash
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k --context-tokens 32768
```
