# Eliza Small

`eliza-small` is the low-latency model service intended for voice turns. It is model/runtime agnostic at the service boundary, but the default profile currently uses Gemma 4 E4B through llama.cpp with 128k context.

## Default Profile

```text
small/gemma4-e4b-q4-llamacpp-128k
```

```text
Model: unsloth/gemma-4-E4B-it-GGUF
Backend: llama.cpp
Quant: Q4_K_M
Projector: mmproj-BF16.gguf
Context: 131072
Port: 8002
```

## Profiles

| Profile | Backend | Model | Use |
| --- | --- | --- | --- |
| `small/gemma4-e4b-q4-llamacpp-128k` | llama.cpp | Gemma 4 E4B | Default long-context voice model |
| `small/gemma4-e4b-q4-llamacpp-8k` | llama.cpp | Gemma 4 E4B | Alternative 8K llama.cpp profile |
| `small/gemma4-e4b-q4-llamacpp-128k` | llama.cpp | Gemma 4 E4B | Long-context 128K llama.cpp profile |
| `small/gemma4-12b-q4-llamacpp-8k` | llama.cpp | Gemma 4 12B | Larger Gemma profile on small tier |
| `small/gemma4-e4b-vllm-8k` | vLLM | Gemma 4 E4B HF | vLLM profile for runtime comparison |
| `small/gemma3-4b-q4-llamacpp-8k` | llama.cpp | Gemma 3 4B QAT | Smaller fallback profile |
| `small/qwen3.5-2b-ud-q4-k-xl-llamacpp-128k` | llama.cpp | Qwen3.5 2B | Fast Qwen3.5 option (aliases: `small/qwen3.5-2b`) |
| `small/qwen3.5-4b-ud-q4-k-xl-llamacpp-128k` | llama.cpp | Qwen3.5 4B | Stronger Qwen3.5 option (aliases: `small/qwen3.5-4b`) |

Qwen3.5 small models are hybrid-attention (Gated DeltaNet + Gated Attention) with a
vision projector and native 262K context; the chat template keeps thinking off
unless enabled per request, which suits the low-latency voice role.

## Start And Test

```bash
# Default profile (gemma4-e4b-128k)
./scripts/download-models eliza-small
./scripts/start eliza-small
./scripts/smoke-test eliza-small
./scripts/run-benchmark voice-latency eliza-small

# Explicit profile selection
./scripts/start eliza-small --profile small/gemma4-e4b-q4-llamacpp-128k
```

## Voice Stack

The voice stack uses these services:

```text
stt           :8011
eliza-small   :8002
tts           :8012
vocode-bridge :8021
```

Run the HTTP pipeline smoke test:

```bash
./scripts/smoke-test voice-assistant --profile voice/assistant-local
```

`eliza-small` is the model service that Vocode or another orchestrator should use for short, low-latency assistant responses.
