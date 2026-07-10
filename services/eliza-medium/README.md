# eliza-medium

Larger local reasoning/coding endpoint. Stable runtime paths are llama.cpp and SGLang; vLLM profiles remain experimental on GB10.

Default profile: `medium/qwen3_6-35b-a3b-q4-llamacpp-256k`.

```bash
./scripts/start eliza-medium --profile medium/qwen3_6-35b-a3b-q4-llamacpp-256k
./scripts/smoke-test eliza-medium

./scripts/setup sglang
./scripts/start eliza-medium --profile medium/qwen3_6-27b-fp8-sglang-32k
./scripts/smoke-test eliza-medium --profile medium/qwen3_6-27b-fp8-sglang-32k
```
