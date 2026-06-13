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

If it prints build instructions, build llama.cpp with CUDA and set `LLAMA_SERVER_BIN` in `.env`.

## vLLM Missing Or Broken

Run:

```bash
./scripts/install-vllm
```

On DGX Spark, vLLM wheels and torch builds can be architecture-sensitive. Prefer a known-good wheel/container for your current OS image if the direct install fails.

## Gemma 4 Audio Issues

Use a recent llama.cpp build. Prefer `mmproj-BF16.gguf` for Gemma 4 audio. Start with text-only smoke tests before direct audio tests.

## Qwen OOM

Try profiles in this order:

```text
qwen-shared-128k
qwen-shared-200k
qwen-shared-200k-fp8kv
```

Stop `voice-llm` before testing `qwen-solo-262k`.
