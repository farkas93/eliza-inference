# Eliza Small

`eliza-small` is the low-latency model service intended for voice turns. It is model/runtime agnostic at the service boundary, but the default profile currently uses Gemma 4 E2B through llama.cpp.

## Default Profile

```text
eliza-small-gemma4-e2b-fast
```

```text
Model: unsloth/gemma-4-E2B-it-GGUF
Backend: llama.cpp
Quant: Q4_K_M
Projector: mmproj-BF16.gguf
Context: 8192
Port: 8002
```

## Profiles

| Profile | Backend | Model | Use |
| --- | --- | --- | --- |
| `eliza-small-gemma4-e2b-fast` | llama.cpp | Gemma 4 E2B | Default low-latency voice model |
| `eliza-small-gemma4-e4b-quality` | llama.cpp | Gemma 4 E4B | Higher-quality voice model |
| `eliza-small-gemma4-12b-quality` | llama.cpp | Gemma 4 12B | Higher-quality experimental profile |
| `eliza-small-gemma4-e4b-vllm-experimental` | vLLM | Gemma 4 E4B HF | Experimental vLLM comparison |
| `eliza-small-gemma3-4b-stable` | llama.cpp | Gemma 3 4B QAT | Stable fallback |

## Start And Test

```bash
./scripts/download-models eliza-small --profile eliza-small-gemma4-e2b-fast
./scripts/start eliza-small --profile eliza-small-gemma4-e2b-fast
./scripts/smoke-test eliza-small --profile eliza-small-gemma4-e2b-fast
./scripts/benchmark-latency eliza-small --profile eliza-small-gemma4-e2b-fast
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
./scripts/smoke-test voice-assistant --profile voice-assistant-local
```

`eliza-small` is the model service that Vocode or another orchestrator should use for short, low-latency assistant responses.
