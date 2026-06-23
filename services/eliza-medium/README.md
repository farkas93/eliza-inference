# eliza-medium

Larger local reasoning/coding endpoint. The stable runtime path is llama.cpp; vLLM profiles are experimental on GB10.

Default profile: `medium/qwen3_6-27b-q4-llamacpp-32k`.

```bash
./scripts/start eliza-medium --profile medium/qwen3_6-27b-q4-llamacpp-32k
./scripts/smoke-test eliza-medium
```
