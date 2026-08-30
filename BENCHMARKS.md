# Benchmark Results

_Generated 2026-08-30T09:24:21+00:00 from ledger and result files in `/home/zskalo/eliza-inference/benchmarks/results` (12 runs)._

## Token generation

| Model | Service | tok/s (est) | TTFT (s) | Elapsed (s) | Output tokens (est) | Reasoning channel |
| --- | --- | --- | --- | --- | --- | --- |
| `medium/qwen3.6-35b-a3b-q4-llamacpp-256k` | eliza-medium | 54.9 | 16.62 | 20.52 | 214 | yes |
| `medium/qwen3.8-27b-fp8-sglang-256k` | eliza-medium | 7.9 | 0.21 | 16.84 | 131 | yes |
| `medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k` | eliza-medium | 11.9 | 2.93 | 9.22 | 75 | yes |
| `medium/qwen3.8-flash-next-ud-q4-k-xl-llamacpp-256k` | eliza-medium | 17.8 | 1.26 | 4.24 | 53 | yes |
| `medium/qwen3_6-27b-q4-llamacpp-32k` | eliza-medium | 7.3 | 0.73 | 36.86 | 263 | yes |
| `small/gemma4-e4b-q4-llamacpp-128k` | eliza-small | 34.7 | 0.18 | 4.33 | 144 | no |

## Sources

- `medium/qwen3.6-35b-a3b-q4-llamacpp-256k` (eliza-medium) — token-generation: 2026-06-23 13:05:38 (`eliza-medium-eliza-medium-qwen36-35b-a3b-llamacpp-200k-experimental-stream-20260623-130538.json`)
- `medium/qwen3.8-27b-fp8-sglang-256k` (eliza-medium) — token-generation: 2026-08-29 12:52:42 (`eliza-medium-medium-qwen3.8-27b-fp8-sglang-256k-stream-20260829-125242.json`)
- `medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k` (eliza-medium) — token-generation: 2026-08-29 10:44:16 (`eliza-medium-medium-qwen3.8-27b-ud-q4-k-xl-llamacpp-256k-stream-20260829-124406.json`)
- `medium/qwen3.8-flash-next-ud-q4-k-xl-llamacpp-256k` (eliza-medium) — token-generation: 2026-08-29 11:38:56 (`eliza-medium-medium-qwen3.8-flash-next-ud-q4-k-xl-llamacpp-256k-stream-20260829-133851.json`)
- `medium/qwen3_6-27b-q4-llamacpp-32k` (eliza-medium) — token-generation: 2026-06-23 17:51:13 (`eliza-medium-medium-qwen3_6-27b-q4-llamacpp-32k-stream-20260623-175113.json`)
- `small/gemma4-e4b-q4-llamacpp-128k` (eliza-small) — token-generation: 2026-08-30 09:24:03 (`small-gemma4-e4b-q4-llamacpp-128k-stream-20260830-112359.json`)

---
_Regenerate: `eliza-cli bench compare`_
