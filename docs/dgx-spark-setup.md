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
```

`install-llamacpp` currently verifies that `llama-server` is available and prints the recommended CUDA build commands if it is not. This avoids hiding architecture-specific build failures behind an opaque installer.
