# Troubleshooting

## Service Does Not Start

Check the tmux session and logs:

```bash
./scripts/status eliza-small
./scripts/logs eliza-small
```

## Port Already In Use

Run:

```bash
./scripts/doctor
```

Change `.env` or the profile port if needed.

## llama.cpp Missing

Run:

```bash
./scripts/install-llamacpp
```

The installer clones or updates llama.cpp under `~/src/llama.cpp`, installs common apt build prerequisites when possible, and builds CUDA-enabled `llama-server`, `llama-cli`, and `llama-mtmd-cli`.

If CMake configuration fails, confirm CUDA/toolkit visibility:

```bash
nvidia-smi
which nvcc || true
```

If the source checkout has local changes, either commit/stash them, use another directory, or skip updates:

```bash
./scripts/install-llamacpp --no-update
```

If the build cache is stale, rebuild from a clean build directory:

```bash
./scripts/install-llamacpp --clean
```

After a successful build, add the printed `LLAMA_SERVER_BIN` line to `.env` if `llama-server` is not on `PATH`.

## vLLM Missing Or Broken

Run:

```bash
./scripts/install-vllm
```

The vLLM installer creates `.venvs/vllm`, and service launchers default to `.venvs/vllm/bin/vllm`. Set `VLLM_BIN` in `.env` only if you want to override that path.

If logs show `exec: vllm: not found`, rerun with the updated launchers or set an explicit binary path in `.env`:

```bash
VLLM_BIN="/path/to/vllm"
```

If vLLM exits with a `tokenizers`/`transformers` version error, rerun `./scripts/install-vllm` after pulling the latest installer changes. This only affects `.venvs/vllm`.

If vLLM exits while inspecting a model architecture with `fatal error: Python.h: No such file or directory`, Triton is compiling a runtime CUDA helper and Python development headers are missing. Install native build prerequisites, then rerun verification:

```bash
sudo apt-get update
sudo apt-get install -y build-essential python3.12-dev
./scripts/install-vllm --no-install
```

Use the `pythonX.Y-dev` package matching the Python version printed by `./scripts/install-vllm`.

If vLLM exits with `FileNotFoundError: No such file or directory: 'ninja'`, FlashInfer is JIT-compiling a sampler/kernel and cannot find Ninja. Pull the latest repo and rerun:

```bash
./scripts/install-vllm
```

The installer now installs `ninja` into `.venvs/vllm`, and service launchers prepend `.venvs/vllm/bin` to `PATH` so FlashInfer subprocesses can find it.

On DGX Spark, vLLM wheels and torch builds can be architecture-sensitive. Prefer a known-good wheel/container for your current OS image if the direct install fails.

If install succeeds but verification fails with `torch CUDA is not available`, the installed Torch stack is not GPU-ready for this machine. Check:

```bash
nvidia-smi
.venvs/vllm/bin/python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

To rerun verification without reinstalling packages:

```bash
./scripts/install-vllm --no-install
```

If a pre-release vLLM is needed for GB10 support:

```bash
./scripts/install-vllm --pre
```

## Gemma 4 Audio Issues

Use a recent llama.cpp build. Prefer `mmproj-BF16.gguf` for Gemma 4 audio. Start with text-only smoke tests before direct audio tests.

## Piper TTS Missing Or Broken

Install and verify Piper with:

```bash
./scripts/install-tts --backend piper --profile tts-piper-lessac
```

If the installer succeeds but the TTS service fails, make sure `.venvs/tts/bin/piper` exists or set `PIPER_BIN` in `.env`, then restart the service:

```bash
./scripts/restart tts --profile tts-piper-lessac
./scripts/smoke-test tts --profile tts-piper-lessac
```

If synthesis fails, verify the voice files exist:

```bash
ls -lh ~/models/tts/piper-voices/en/en_US/lessac/medium/
```

The expected files are:

```text
en_US-lessac-medium.onnx
en_US-lessac-medium.onnx.json
```

## faster-whisper CUDA Not Available

If STT returns this error:

```text
This CTranslate2 package was not compiled with CUDA support
```

the installed CTranslate2 wheel is CPU-only. Use the CPU STT profile:

```bash
./scripts/stop stt --profile stt-faster-whisper-small
./scripts/start stt --profile stt-faster-whisper-small-cpu
./scripts/smoke-test stt --profile stt-faster-whisper-small-cpu
```

For the full voice pipeline, `voice-assistant-local` now expects `whisper-small` by default. GPU STT should be treated as a later optimization via CUDA-enabled CTranslate2 or a whisper.cpp backend.

## Qwen OOM

Try profiles in this order:

```text
eliza-medium-qwen-llamacpp-32k
eliza-medium-qwen-llamacpp-128k
eliza-medium-qwen-q6-llamacpp-32k
eliza-medium-qwen-q8-llamacpp-32k
eliza-medium-vllm-smoke-tinyllama
eliza-medium-qwen-vllm-smoke-8k
eliza-medium-qwen-vllm-smoke-32k
eliza-medium-qwen-vllm-128k-experimental
eliza-medium-qwen-vllm-200k-experimental
eliza-medium-qwen-vllm-200k-fp8kv-experimental
eliza-medium-qwen36-35b-a3b-llamacpp-200k-experimental
```

Stop `eliza-small` before testing larger `eliza-medium` profiles.

If Qwen hangs during vLLM model load with no API port listening, first test `eliza-medium-qwen-vllm-smoke-8k`. The smoke profiles disable prefix caching and enable eager mode. Prefix caching for Qwen hybrid/Mamba models is experimental in vLLM and should be tested only after basic serving works.

If vLLM remains unreliable, clean it up and use the llama.cpp Qwen profile:

```bash
./scripts/cleanup-vllm
./scripts/download-models eliza-medium --profile eliza-medium-qwen-llamacpp-32k
./scripts/start eliza-medium --profile eliza-medium-qwen-llamacpp-32k
```
