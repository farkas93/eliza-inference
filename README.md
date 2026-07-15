# Eliza Inference

DGX Spark-first local inference stack exposing `eliza-small` for low-latency voice turns and `eliza-medium` for larger reasoning/coding tasks.

Handoff context for the GenieTor + Vocode effort is tracked in `next-task.md`.

## Defaults

| Service | Default Runtime | Default Model | Port |
| --- | --- | --- | ---: |
| `eliza-medium` | DS4 | `deepseek-v4-flash` (DS4 server) | `8001` |
| `eliza-small` | llama.cpp | `gemma-4-E4B-it` (128k context) | `8002` |
| `stt` | faster-whisper | `Systran/faster-whisper-small` CPU int8 | `8011` |
| `tts` | Piper | `en_US-lessac-medium` | `8012` |
| `vocode-bridge` | FastAPI WS bridge | Vocode turn-based orchestration over local STT -> eliza-small -> TTS | `8021` |

Services bind to `0.0.0.0` by default for LAN access. Do not expose them directly to the public internet.

## Storage Paths

By default, model and cache storage is configured as:

- `MODEL_HOME="$HOME/models"`
- `HF_HOME="$MODEL_HOME/huggingface"`
- `LLAMA_CACHE="$MODEL_HOME/llamacpp_cache"`

You can override these in `.env` for custom disk layouts (for example, pointing to a larger SSD or shared workspace).
When overriding, keep in mind that profile readiness checks, downloads, and cache reuse all follow these values.

## Quick Start

```bash
./install-cli
./scripts/doctor
./scripts/setup prerequisites
./scripts/setup llamacpp
./scripts/setup sglang
./scripts/setup stt --profile stt/faster-whisper-small-cpu
./scripts/setup tts --backend piper --profile tts/piper-lessac
./scripts/setup vocode
./scripts/download-models eliza-small
./scripts/download-models eliza-medium --profile medium/deepseek-v4-flash-ds4-256k
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
./scripts/download-models eliza-medium
./scripts/start eliza-medium
./scripts/smoke-test eliza-medium
```

Compare `eliza-medium` runtimes (llama.cpp vs SGLang):

```bash
./scripts/start eliza-medium --profile medium/qwen3.6-27b-fp8-sglang-32k
./scripts/smoke-test eliza-medium --profile medium/qwen3.6-27b-fp8-sglang-32k

./scripts/start eliza-medium --profile medium/qwen3.6-35b-a3b-q4-llamacpp-256k
./scripts/smoke-test eliza-medium --profile medium/qwen3.6-35b-a3b-q4-llamacpp-256k
```

## Profiles

Profiles live under `configs/profiles/` and are grouped by capability/runtime class:

- `configs/profiles/small/`
- `configs/profiles/medium/`
- `configs/profiles/stt/`
- `configs/profiles/tts/`
- `configs/profiles/vocode/`
- `configs/profiles/voice/`

Use path-style profile IDs in commands, for example `small/gemma4-e4b-q4-llamacpp-128k` or `medium/deepseek-v4-flash-ds4-256k`.

Voice profiles include llama.cpp and vLLM variants so Gemma backends can be compared without changing client code.

## Common Commands

```bash
# Defaults (no --profile needed)
./scripts/start eliza-medium
./scripts/start eliza-small

# Explicit profile selection
./scripts/start eliza-medium --profile medium/qwen3.6-35b-a3b-q4-llamacpp-256k
./scripts/start eliza-small --profile small/gemma4-e4b-q4-llamacpp-128k

# Status, logs, stop
./scripts/status eliza-medium
./scripts/logs eliza-small
./scripts/stop eliza-small

# Benchmarks
./scripts/run-benchmark voice-latency eliza-small
./scripts/run-benchmark memory-footprint eliza-medium --context-tokens 32768
```

vLLM profiles are experimental on GB10 in this repo. To remove the local vLLM environment and return to the llama.cpp-first path:

```bash
./scripts/cleanup-vllm
```

Test the local vocode bridge voice turn:

```bash
./scripts/start vocode-bridge --profile vocode/bridge-local
./scripts/smoke-test vocode-bridge --profile vocode/bridge-local

# optional: validate bridge-side endpointing (no audio_input_end)
.venvs/vocode/bin/python clients/audio/vocode_bridge_test.py --url ws://127.0.0.1:8021/ws --auto-endpoint
```

Reinstall vocode bridge dependencies after local development changes:

```bash
./scripts/setup vocode --reinstall
```

GenieTor local backend smoke test (run GenieTor with `ELIZA_BACKEND=local-vocode` first):

```bash
.venvs/vocode/bin/python clients/audio/genietor_local_backend_test.py --url ws://127.0.0.1:8080/ws
```

## Vocode Pipeline

The bridge orchestrates each local service over HTTP:

```text
STT:       http://dgx-spark:8011/v1/audio/transcriptions
Eliza Small: http://dgx-spark:8002/v1/chat/completions
TTS:       http://dgx-spark:8012/v1/audio/speech
```

This keeps STT, LLM, and TTS independently reusable by other LAN applications.

## TUI (Terminal UI)

The CLI includes a Textual-based TUI for interactive service monitoring:

```bash
eliza-cli tui
```

The TUI shows:
- Service status (running/stopped) and port mappings
- Model inventory with download readiness
- Active service logs (auto-scrolled)
- Stack configuration overview

Run it alongside your services — it refreshes automatically.

See `docs/` for setup, stack, networking, model, and troubleshooting notes.
