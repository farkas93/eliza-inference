# Eliza Inference

DGX Spark-first local inference stack for a long-context Qwen coding endpoint and a low-latency Gemma voice LLM endpoint.

## Defaults

| Service | Default Runtime | Default Model | Port |
| --- | --- | --- | ---: |
| `qwen-coder` | vLLM | `Qwen/Qwen3.6-27B-FP8` | `8001` |
| `voice-llm` | llama.cpp | `unsloth/gemma-4-E4B-it-GGUF` | `8002` |
| `stt` | faster-whisper | `Systran/faster-whisper-small` CPU int8 | `8011` |
| `tts` | Piper | `en_US-lessac-medium` | `8012` |

Services bind to `0.0.0.0` by default for LAN access. Do not expose them directly to the public internet.

## Quick Start

```bash
./scripts/doctor
./scripts/install
./scripts/install-vllm
./scripts/install-llamacpp
./scripts/download-models voice-llm --profile voice-gemma4-e4b-default
./scripts/start voice-llm --profile voice-gemma4-e4b-default
./scripts/smoke-test voice-llm
```

Start speech services independently:

```bash
./scripts/download-models stt --profile stt-faster-whisper-small-cpu
./scripts/start stt --profile stt-faster-whisper-small-cpu
./scripts/smoke-test stt

./scripts/install-tts --backend piper --profile tts-piper-lessac
./scripts/start tts --profile tts-piper-lessac
./scripts/smoke-test tts
```

Start Qwen separately:

```bash
./scripts/download-models qwen-coder --profile qwen-shared-200k
./scripts/start qwen-coder --profile qwen-shared-200k
./scripts/smoke-test qwen-coder
```

## Profiles

Profiles live under `configs/profiles/` and control runtime, model, context size, network binding, and backend-specific flags.

Voice profiles include llama.cpp and vLLM variants so Gemma backends can be compared without changing client code.

## Common Commands

```bash
./scripts/start qwen-coder --profile qwen-shared-200k
./scripts/start voice-llm --profile voice-gemma4-e4b-default
./scripts/status qwen-coder
./scripts/logs voice-llm
./scripts/stop voice-llm
./scripts/benchmark-latency voice-llm
./scripts/benchmark-context qwen-coder --tokens 200000
```

## Vocode Pipeline

Vocode should call each local service over HTTP:

```text
STT:       http://dgx-spark:8011/v1/audio/transcriptions
Voice LLM: http://dgx-spark:8002/v1/chat/completions
TTS:       http://dgx-spark:8012/v1/audio/speech
```

This keeps STT, LLM, and TTS independently reusable by other LAN applications.

See `docs/` for setup, networking, model, and troubleshooting notes.
