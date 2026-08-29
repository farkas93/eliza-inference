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
