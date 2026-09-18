# eliza-medium

Larger local reasoning/coding endpoint. Stable runtime paths are llama.cpp and SGLang; vLLM profiles remain experimental on GB10.

Default profile: `medium/qwen3.8-flash-next-ud-q4-k-xl-llamacpp-256k`.

```bash
./scripts/start eliza-medium --profile medium/qwen3.8-flash-next-ud-q4-k-xl-llamacpp-256k
./scripts/smoke-test eliza-medium

./scripts/setup llamacpp
./scripts/start eliza-medium --profile medium/qwen3.8-flash-next-ud-q4-k-xl-llamacpp-256k
./scripts/smoke-test eliza-medium --profile medium/qwen3.8-flash-next-ud-q4-k-xl-llamacpp-256k
```

ds4 (DwarfStar) backends need their own runtime and model downloads:

```bash
./scripts/setup ds4
./scripts/download-models eliza-medium --profile medium/glm-5.3-flash-ds4-256k
./scripts/start eliza-medium --profile medium/glm-5.3-flash-ds4-256k
```

See `docs/eliza-medium.md` for context sizing and the ds4 memory guard.

The `flash` backend serves Qwen3.8-Flash-Next from a patched vLLM image in Docker:

```bash
./scripts/setup flash
./scripts/download-models eliza-medium --profile medium/qwen3.8-flash-next-flash-docker-500k
./scripts/start eliza-medium --profile medium/qwen3.8-flash-next-flash-docker-500k
```

First boot takes 8-13 minutes and the recipe claims 0.80 of the unified pool, so stop the
other services first.
