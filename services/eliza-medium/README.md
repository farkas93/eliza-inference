# eliza-medium

Larger local reasoning/coding endpoint. The stable runtime path is llama.cpp; vLLM profiles are experimental on GB10.

Default profile: `eliza-medium-qwen-llamacpp-32k`.

```bash
./scripts/start eliza-medium --profile eliza-medium-qwen-llamacpp-32k
./scripts/smoke-test eliza-medium
```
