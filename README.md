# Eliza Inference

DGX Spark-first local inference stack exposing `eliza-small` for low-latency voice turns and `eliza-medium` for larger reasoning/coding tasks.

## Defaults

| Service | Default Runtime | Default Model | Port |
| --- | --- | --- | ---: |
| `eliza-medium` | llama.cpp | `unsloth/Qwen3.6-27B-GGUF` | `8001` |
| `eliza-small` | llama.cpp | `unsloth/gemma-4-E2B-it-GGUF` | `8002` |
| `stt` | faster-whisper | `Systran/faster-whisper-small` CPU int8 | `8011` |
| `tts` | Piper | `en_US-lessac-medium` | `8012` |
| `vocode-bridge` | FastAPI WS bridge | STT/TTS transport spike | `8021` |

Services bind to `0.0.0.0` by default for LAN access. Do not expose them directly to the public internet.

## Quick Start

```bash
./scripts/doctor
./scripts/setup prerequisites
./scripts/setup llamacpp
./scripts/setup stt --profile stt/faster-whisper-small-cpu
./scripts/setup tts --backend piper --profile tts/piper-lessac
./scripts/setup vocode
./scripts/download-models eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k
./scripts/download-models eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k
./scripts/start-stack
./scripts/smoke-test-stack
```

The default stack is defined in `configs/eliza-stack.toml`.

Start speech services independently:

```bash
./scripts/setup stt --profile stt/faster-whisper-small-cpu
./scripts/start stt --profile stt/faster-whisper-small-cpu
./scripts/smoke-test stt

./scripts/setup tts --backend piper --profile tts/piper-lessac
./scripts/start tts --profile tts/piper-lessac
./scripts/smoke-test tts
```

Start `eliza-medium` separately:

```bash
./scripts/download-models eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k
./scripts/start eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k
./scripts/smoke-test eliza-medium
```

## Profiles

Profiles live under `configs/profiles/` and are grouped by capability/runtime class:

- `configs/profiles/small/`
- `configs/profiles/medium/`
- `configs/profiles/stt/`
- `configs/profiles/tts/`
- `configs/profiles/vocode/`
- `configs/profiles/voice/`

Use path-style profile IDs in commands, for example `small/gemma4-e2b-q4-llamacpp-8k` or `medium/qwen3_6-27b-q4-llamacpp-32k`.

Voice profiles include llama.cpp and vLLM variants so Gemma backends can be compared without changing client code.

## Common Commands

```bash
./scripts/start eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k
./scripts/start eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k
./scripts/status eliza-medium
./scripts/logs eliza-small
./scripts/stop eliza-small
./scripts/run-benchmark voice-latency eliza-small
./scripts/run-benchmark memory-footprint eliza-medium --context-tokens 32768
```

vLLM profiles are experimental on GB10 in this repo. To remove the local vLLM environment and return to the llama.cpp-first path:

```bash
./scripts/cleanup-vllm
```

Test the Vocode bridge transport spike:

```bash
./scripts/start vocode-bridge --profile vocode/bridge-local
./scripts/smoke-test vocode-bridge --profile vocode/bridge-local
```

## Vocode Pipeline

Vocode should call each local service over HTTP:

```text
STT:       http://dgx-spark:8011/v1/audio/transcriptions
Eliza Small: http://dgx-spark:8002/v1/chat/completions
TTS:       http://dgx-spark:8012/v1/audio/speech
```

This keeps STT, LLM, and TTS independently reusable by other LAN applications.

See `docs/` for setup, stack, networking, model, and troubleshooting notes.
