# DGX Spark Setup

This repository targets DGX Spark first. It assumes a 128 GB unified-memory GB10 system with NVIDIA drivers, CUDA-capable runtimes, `uv`, and `tmux`.

## Model Storage

Default model storage is `~/models`.

Override with `.env`:

```bash
MODEL_HOME="/models"
HF_HOME="$MODEL_HOME/huggingface"
LLAMA_CACHE="$MODEL_HOME/llama"
```

Use `/models` only if you want a system-wide model directory and are prepared to manage permissions for your service user.

## First Checks

```bash
./scripts/doctor
```

The doctor checks common tools, NVIDIA visibility, default ports, model directory disk space, and Python availability.

## Installation

```bash
./scripts/install
./scripts/install-vllm
./scripts/install-llamacpp
./scripts/install-tts --backend piper --profile tts-piper-lessac
```

`scripts/install` bootstraps `uv` if it is missing and installs `git-lfs` through `apt` when `sudo` is available. If `uv` is installed but not visible in the current shell, open a new shell or add `~/.local/bin` to `PATH` and rerun the command.

`install-llamacpp` builds a recent CUDA-enabled llama.cpp checkout under `~/src/llama.cpp` when `llama-server` is not already available. It installs apt build prerequisites when `sudo` is available, configures CMake with `GGML_CUDA=ON` and `LLAMA_CURL=ON`, and builds `llama-server`, `llama-cli`, and `llama-mtmd-cli`.

Useful options:

```bash
./scripts/install-llamacpp --clean
./scripts/install-llamacpp --no-update
./scripts/install-llamacpp --dir ~/src/llama.cpp
```

If the build succeeds and `llama-server` is not on `PATH`, add the printed `LLAMA_SERVER_BIN` line to `.env`.

`install-vllm` installs vLLM with `uv`, verifies package versions, imports Torch and vLLM, checks `torch.cuda.is_available()`, prints the detected CUDA device, and fails clearly if Torch cannot see the GPU.

Useful options:

```bash
./scripts/install-vllm --no-install
./scripts/install-vllm --pre
./scripts/install-vllm --package vllm
./scripts/install-vllm --torch-backend auto
```

`install-tts` installs and verifies the selected TTS backend. The default supported backend is Piper through the `piper-tts` Python package. It downloads the selected voice profile, verifies the voice files, synthesizes `tmp/piper-install-test.wav`, and prints the `PIPER_BIN` setting to add to `.env` if needed.

Useful options:

```bash
./scripts/install-tts --backend piper --profile tts-piper-lessac
./scripts/install-tts --backend piper --profile tts-piper-amy
./scripts/install-tts --backend piper --profile tts-piper-lessac --no-download
./scripts/install-tts --backend piper --profile tts-piper-lessac --no-install
```
