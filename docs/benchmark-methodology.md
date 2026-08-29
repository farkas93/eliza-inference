# Benchmark Methodology

Benchmark profiles instead of assuming a single best configuration.

## Consistency guard

Every benchmark verifies before running that the service is reachable and is
actually serving the model from the requested profile (it queries
`/v1/models` and compares against the profile's `MODEL_NAME`/`MODEL_ID` or the
llama.cpp `MODEL_FILE` basename). If the service is down or serving a
different model, the benchmark refuses to run and prints the matching
`./scripts/start` or `./scripts/restart` command, so results are never
collected against the wrong runtime. Pass `--force` to skip the check.

## GB10 unified memory

On DGX Spark (GB10) the GPU shares unified system memory, so `nvidia-smi`
reports `N/A` for `memory.used`/`memory.total`. `memory-footprint` detects
this automatically and samples system memory instead (`free -b`:
used = total - available), while still taking GPU name and utilization from
`nvidia-smi`. The report records which source was used in `memory_source`
(`nvidia-smi` or `system-unified`). On unified memory the numbers include the
whole OS, so compare deltas (`post_load` / `contexts` minus `baseline`)
between profiles rather than absolute values.

## Qwen

```bash
./scripts/start eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k --context-tokens 32768

./scripts/restart eliza-medium --profile medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k --context-tokens 131072

./scripts/restart eliza-medium --profile medium/qwen3.6-27b-nvfp4-vllm-256k
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/qwen3.6-27b-nvfp4-vllm-256k --context-tokens 131072

./scripts/restart eliza-medium --profile medium/gemma4-26b-a4b-q4-llamacpp-256k
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/gemma4-26b-a4b-q4-llamacpp-256k --context-tokens 131072
```

Compare elapsed time, success/failure, and memory snapshots from `./scripts/run-benchmark memory-footprint ...`.

## Streaming

Inspect raw streaming chunks and estimate output throughput:

```bash
./scripts/run-benchmark token-generation eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k --show-raw
./scripts/run-benchmark token-generation eliza-medium --profile medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k --max-tokens 1024
```

The stream benchmark records first-event latency, first-content latency, estimated output tokens/sec, and whether the endpoint sent a dedicated reasoning channel or `<think>` tags in normal content.

## Voice

```bash
./scripts/start eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k
./scripts/run-benchmark voice-latency eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k

./scripts/restart eliza-small --profile small/gemma4-e4b-q4-llamacpp-8k
./scripts/run-benchmark voice-latency eliza-small --profile small/gemma4-e4b-q4-llamacpp-8k

```

Compare average latency and quality for short spoken-assistant style prompts.

## Comparing results

Every benchmark run appends one normalized record to
`benchmarks/results/runs.jsonl` (the run ledger) in addition to its per-run
result JSON. Each record carries the service, profile, benchmark type, model,
timestamp, and flat metrics for that run.

Aggregate the ledger into a curated comparison with:

```bash
./scripts/run-benchmark compare
./scripts/run-benchmark compare --service eliza-medium
./scripts/run-benchmark compare --all-runs
```

`compare` keeps the latest run per profile/type by default
(`--all-runs` shows every run) and writes one flat markdown table per
benchmark type across all services to `benchmarks/RESULTS.md` by default
(`--output` overrides). It merges the ledger with any per-run result JSON
files, collapsing legacy `eliza-medium-*` / `eliza-small-*` references
into canonical `category/name` profile ids.

The working copy `benchmarks/RESULTS.md` is gitignored. To publish the
curated comparison to the git host, use `eliza-cli bench publish` (which
copies to `BENCHMARKS.md` at the repository root, commits on `main`, and
pushes):

```bash
eliza-cli bench all
eliza-cli bench publish --dry-run
eliza-cli bench publish
```
