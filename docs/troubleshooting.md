# Troubleshooting

## Service Does Not Start

Check the tmux session and logs:

```bash
./scripts/status voice-llm
./scripts/logs voice-llm
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

On DGX Spark, vLLM wheels and torch builds can be architecture-sensitive. Prefer a known-good wheel/container for your current OS image if the direct install fails.

If install succeeds but verification fails with `torch CUDA is not available`, the installed Torch stack is not GPU-ready for this machine. Check:

```bash
nvidia-smi
uv run --project . python -c "import torch; print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
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

If the installer succeeds but the TTS service fails, make sure `.env` contains the printed `PIPER_BIN` value, then restart the service:

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
qwen-shared-128k
qwen-shared-200k
qwen-shared-200k-fp8kv
```

Stop `voice-llm` before testing `qwen-solo-262k`.
