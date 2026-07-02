# eliza-medium

Larger local reasoning/coding endpoint. The stable runtime path is llama.cpp; vLLM profiles are experimental on GB10.

Default profile: `medium/openpangu-2_0-flash-q4-llamacpp-256k`.

```bash
./scripts/start eliza-medium --profile medium/openpangu-2_0-flash-q4-llamacpp-256k
./scripts/smoke-test eliza-medium
```
