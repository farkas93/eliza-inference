# Voice Stack

The voice stack is split into reusable service layers.

```text
stt
  OpenAI-compatible speech-to-text endpoint on :8011

voice-llm
  Gemma endpoint on :8002 through llama.cpp or vLLM

tts
  OpenAI-compatible speech endpoint on :8012

voice-assistant
  Vocode or another orchestrator that calls STT, voice-llm, and TTS
```

Vocode should call the service URLs through HTTP instead of owning the model runtimes directly. That makes each component independently reusable by other LAN applications.

## Default Model

Default profile: `voice-gemma4-e4b-default`.

```text
Model: unsloth/gemma-4-E4B-it-GGUF
Backend: llama.cpp
Quant: Q4_K_M
Projector: mmproj-BF16.gguf
Context: 8192
Reasoning: off
```

Gemma 4 E4B is the default because it supports audio-capable multimodal operation, is small enough for low latency, and should coexist well with the Qwen coding endpoint.

## Profiles

| Profile | Backend | Model | Use |
| --- | --- | --- | --- |
| `voice-gemma4-e4b-default` | llama.cpp | Gemma 4 E4B | Default |
| `voice-gemma4-e2b-fast` | llama.cpp | Gemma 4 E2B | Fastest Gemma 4 test |
| `voice-gemma4-12b-quality` | llama.cpp | Gemma 4 12B | Higher-quality test |
| `voice-gemma4-e4b-vllm-text` | vLLM | Gemma 4 E4B HF | Text-only vLLM comparison |
| `voice-gemma3-4b-stable` | llama.cpp | Gemma 3 4B QAT | Stable fallback |

## Start And Test

```bash
./scripts/download-models voice-llm --profile voice-gemma4-e4b-default
./scripts/start voice-llm --profile voice-gemma4-e4b-default
./scripts/smoke-test voice-llm
./scripts/benchmark-latency voice-llm
```

Start the full service set for a Vocode pipeline:

```bash
./scripts/start stt --profile stt-faster-whisper-small-cpu
./scripts/start voice-llm --profile voice-gemma4-e4b-default
./scripts/start tts --profile tts-piper-lessac
```

Run the HTTP pipeline smoke test:

```bash
./scripts/smoke-test voice-assistant --profile voice-assistant-local
```

This tests the hosted service chain that Vocode will orchestrate, without requiring live microphone/speaker setup.

Vocode client URLs:

```bash
STT_BASE_URL="http://dgx-spark:8011/v1"
VOICE_LLM_BASE_URL="http://dgx-spark:8002/v1"
TTS_BASE_URL="http://dgx-spark:8012/v1"
```

## Backend Choice

llama.cpp is the default for Gemma 4 voice because it supports GGUF and multimodal projector files. vLLM is included for text-only comparisons, throughput testing, and future compressed-tensor Gemma profiles.

If Gemma 4 audio or MTP paths misbehave, use text mode first and consider setting `FLASH_ATTN="off"` in the selected profile.
