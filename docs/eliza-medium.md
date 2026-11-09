# Eliza Medium

`eliza-medium` is the larger, more capable local model service intended for coding, reasoning, and longer-context tasks. It is model/runtime agnostic at the service boundary. The default profile is Qwen3.8 27B FP8 through SGLang with 256k context.

## Profiles

| Profile | Runtime | Context | Use |
| --- | --- | ---: | --- |
| `medium/openpangu-2_0-flash-q4-llamacpp-256k` | llama.cpp | `262144` | Alternative openPangu profile |
| `medium/gemma4-26b-a4b-q4-llamacpp-256k` | llama.cpp | `262144` | Gemma 4 26B A4B long-context profile |
| `medium/tinyllama-1_1b-vllm-2k` | vLLM | `2048` | vLLM runtime sanity profile |
| `medium/qwen3.6-35b-a3b-q4-llamacpp-256k` | llama.cpp | `262144` | Default long-context profile |
| `medium/qwen3.8-27b-fp8-sglang-256k` | sglang | `262144` | Default Qwen3.8 FP8 high-throughput profile |
| `medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k` | llama.cpp | `262144` | Qwen3.8 llama.cpp compatibility profile |
| `medium/qwen3.6-27b-nvfp4-sglang-256k` | SGLang | `262144` | Qwen3.6 NVFP4 SGLang alternative |
| `medium/qwen3.6-27b-nvfp4-vllm-256k` | vLLM | `262144` | Experimental Qwen3.6 vLLM profile |
| `medium/qwen3-coder-next-sglang-256k` | SGLang | `262144` | Agentic coding profile |
| `medium/qwen3-coder-next-ud-q4-k-m-llamacpp-256k` | llama.cpp | `262144` | Agentic coding llama.cpp fallback |
| `medium/deepseek-v4-flash-ds4-128k` | ds4 | `131072` | Conservative DS4 profile |
| `medium/deepseek-v4-flash-ds4-256k` | ds4 | `262144` | Alternative DS4 256K long-context profile |
| `medium/glm-5.3-flash-ds4-256k` | ds4 | `262144` | GLM 5.3 Flash Q2, MTP + disk KV, dedicated GPU |
| `medium/glm-5.3-flash-ds4-32k` | ds4 | `32768` | GLM 5.3 Flash Q2 for hosts sharing memory with other services |
| `medium/qwen3.8-flash-next-flash-docker-500k` | flash | `500000` | Qwen3.8-Flash-Next on patched vLLM in Docker, hybrid + YaRN |
| `medium/qwen3.8-flash-next-flash-docker-262k` | flash | `262144` | Same recipe at the native context, no YaRN |
| `medium/qwen3.8-flash-next-flash-docker-1m` | flash | `1000000` | fp8 KV cache variant for maximum context |
| `medium/qwen3.8-flash-next-ds4dfm-262k` | ds4dfm | `262144` | Native Rust-host DwarfStar, Q5 + BF16 SSD-PLE, MTP |
| `medium/qwen3.8-flash-next-ds4dfm-524k` | ds4dfm | `524288` | Same artifact at the YaRN factor-2 context |

## Start

```bash
# Default profile (Qwen3.8 FP8 through SGLang)
./scripts/start eliza-medium
./scripts/smoke-test eliza-medium

# Explicit profile selection
./scripts/start eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k
./scripts/smoke-test eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k
```

For llama.cpp alternatives, use an explicit profile:

```bash
./scripts/start eliza-medium --profile medium/qwen3.6-35b-a3b-q4-llamacpp-256k
./scripts/smoke-test eliza-medium --profile medium/qwen3.6-35b-a3b-q4-llamacpp-256k
```

openPangu alternative profile:

```bash
./scripts/restart eliza-medium --profile medium/openpangu-2_0-flash-q4-llamacpp-256k
./scripts/smoke-test eliza-medium --profile medium/openpangu-2_0-flash-q4-llamacpp-256k
```

Qwen3.8 runtime comparison (SGLang vs llama.cpp):

```bash
./scripts/download-models eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k
./scripts/start eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k
./scripts/smoke-test eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k

./scripts/download-models eliza-medium --profile medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k
./scripts/restart eliza-medium --profile medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k
./scripts/smoke-test eliza-medium --profile medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k
```

To remove local vLLM state and stop stale vLLM sessions:

```bash
./scripts/cleanup-vllm
```

## ds4 (DwarfStar) profiles

ds4 is a model-specific engine (DeepSeek V4 Flash/PRO, GLM 5.2/5.3, GLM 5.3
Flash), not a general GGUF runner: it only loads GGUFs published by that
project. Build it from source and link the binaries:

```bash
./scripts/setup ds4              # clone, build, link ds4 + ds4-server
./scripts/setup ds4 --check      # report how far the checkout is behind upstream
```

`--check` exits non-zero when the checkout is stale, so it can gate a refresh.
ds4 moves fast (tens of commits a week); re-run it before debugging a ds4
profile.

Download and start GLM 5.3 Flash (target `glm53-q2`, about 90 GiB):

```bash
./scripts/download-models eliza-medium --profile medium/glm-5.3-flash-ds4-256k
./scripts/start eliza-medium --profile medium/glm-5.3-flash-ds4-256k
./scripts/smoke-test eliza-medium
```

The model lands in `$DS4_DIR/gguf/`, and `start-ds4.sh` also finds it there
when `MODEL_DIR` is unset. The served model alias is `glm-5.3-flash`
(`glm-5.3-flash-reasoner` / `glm-5.3-flash-nothink` select thinking mode).

Context sizing on one DGX Spark: GLM 5.3 Flash mixes recurrent KDA layers with
sparse DSA attention, so only 11 of its 46 layers keep per-token KV (512 dims,
F16) — roughly 12 KiB per token. A 256k context costs about 3 GiB, so the
90 GiB Q2 model plus KV plus runtime buffers fits inside the 128 GB unified
memory budget; the 32k profile is there to leave room for `eliza-small`, STT
and TTS on the same box. Stop the other services before loading a model, and
inspect the fit with:

```bash
DS4_GLM_MEMORY_GUARD_REPORT=1 ./ds4-server -m "$DS4_DIR/gguf/GLM-5.3-Flash-Q2.gguf" --ctx 262144
```

The guard prints `required` versus `budget` and refuses a context that does not
fit. `DS4_GLM_MEMORY_GUARD_FRACTION` (0.5..1.0) and `DS4_GLM_MEMORY_GUARD=0`
relax or disable it.

GLM specifics handled by the profiles: `--power 100` is mandatory (ds4 refuses
lower values), `DS4_MTP="true"` enables the embedded MTP draft block (no second
model file), and GLM rejects `--prefill-chunk` and `--mtp-model`.

## flash (Docker/vLLM) backend

`BACKEND=flash` serves **Qwen3.8-Flash-Next** from the
[`blazux/qwen3.8-Flash-DGX`](https://github.com/blazux/qwen3.8-Flash-DGX) recipe: a patched
vLLM image that keeps the ~48 GiB n-gram (PLE) embedding table mmapped from NVMe instead of
resident, so the ~125 GiB NVFP4 checkpoint fits next to a real KV pool on a single Spark.
It is Docker-only — it does not use `.venvs/vllm` — and needs docker plus the NVIDIA
container toolkit.

```bash
./scripts/setup flash            # clone the recipe, build the image (~1 min once the base image is cached)
./scripts/setup flash --check    # what is missing: checkout drift, image, weights, hybrid layout
```

The checkpoint is ~124 GiB and opt-in:

```bash
./scripts/download-models eliza-medium --profile medium/qwen3.8-flash-next-flash-docker-500k
./scripts/start eliza-medium --profile medium/qwen3.8-flash-next-flash-docker-500k
./scripts/logs eliza-medium      # first boot loads ~75 GiB: 8-13 minutes
./scripts/smoke-test eliza-medium
./scripts/stop eliza-medium      # stops the container as well as the tmux session
```

Weights land under `FLASH_HF_CACHE` (default `HF_HOME`, i.e. `$MODEL_HOME/huggingface`) and
the download also prepares the hybrid layout (`+13 GiB`, ~10 min) unless
`FLASH_PREPARE_HYBRID=false`. The API is served as `qwen3.8-flash-next` on `ELIZA_MEDIUM_PORT`
(8001 by default), with tool calling and the reasoning parser enabled, so the existing clients
need no changes.

The recipe claims `FLASH_GPU_MEM=0.80` of the 128 GB pool, so nothing else can hold memory at
the same time: stop `eliza-small`, STT, TTS and any ds4 profile first. Knobs map 1:1 onto the
upstream variables through `FLASH_*`: `FLASH_MODE` (`nvfp4`/`hybrid`), `FLASH_YARN`, `FLASH_MTP`,
`FLASH_SEQS`, `FLASH_GPU_MEM`, `FLASH_KV_DTYPE`, `FLASH_KV_CACHE_MEM`, `FLASH_PREFIX_CACHE`,
`FLASH_DRAFT_VOCAB`, `FLASH_PREWARM`, `FLASH_WORKERS`, `FLASH_COMPILE_CACHE`, `FLASH_EXTRA_ARGS`.
`FLASH_COMPILE_CACHE` defaults to `qwen38-flash`, which keeps vLLM's compiled graphs in docker
volumes and cuts init from ~122 s to ~41 s.

The container runs with `--restart unless-stopped`, and the wrapper tails its logs, so the
service is only healthy while the container runs. If the wrapper dies hard and the port stays
taken, `./scripts/stop eliza-medium` or `docker rm -f qwen38-flash` clears it.

## Qwen3.8 Flash Next medium default: UD-IQ4_XS + MTP

The medium default is Unsloth Dynamic v3.1 `UD-IQ4_XS` at the model's native
262,144-token context, paired with the standalone Q8 MTP head. The current Hub
main model is four shards totaling about 93.7 GB (87.2 GiB); the updated
standalone Q8 MTP head is about 4.14 GB. These are file sizes, not a guarantee
of equivalent free unified memory while serving.

```bash
./scripts/setup llamacpp --qwen4-mtp
./scripts/download-models eliza-medium --profile medium/qwen3.8-flash-next-ud-iq4-xs-llamacpp-mtp-256k
./scripts/restart eliza-medium --profile medium/qwen3.8-flash-next-ud-iq4-xs-llamacpp-mtp-256k
./scripts/smoke-test eliza-medium
```

Setup builds `ggml-org/llama.cpp` at pinned commit
`6023692b1e13a6d4ee6b93f989c4713e474e6165` from upstream (November 5),
which includes Qwen4Exp MTP PR #29761 and subsequent QSA and KV-shift fixes. It is isolated in
`~/src/llama.cpp-qwen4-mtp`; set `LLAMA_QWEN4_MTP_DIR` or
`LLAMA_QWEN4_MTP_SERVER_BIN` to override. This runtime uses the current
standalone draft artifact `MTP/mtp-Qwen3.8-Flash-Next-Q8_0.gguf`, not the older
shared-head artifact used by the legacy `unsloth-mtp` profiles. Do not mix the
runtime and draft-file contracts.

The main and draft downloads are pinned to Hub revision
`084c631ac221016019d6e0a863afe92d90edd3b0` (Dynamic v3.1). The launcher checks
the actual binary's revision as well as MTP support and every main GGUF shard.
An interrupted download is `INCOMPLETE` in the catalog and not ready in the
profile picker, even if the small metadata shard and draft file already exist.

The sibling `medium/qwen3.8-flash-next-ud-iq3-xxs-llamacpp-mtp-256k` profile
keeps the same runtime and draft but uses the lower-memory IQ3_XXS v3.1 main
quant (about 83.6 GB / 77.9 GiB). It is available if the IQ4_XS profile leaves
too little headroom for the workload. The old Q4_K_XL profile remains available
as a rollback path.

The IQ4_XS + MTP combination has promising upstream Spark evidence: PR #29761
reports 28.36 tok/s without MTP and 43.88 tok/s with MTP over a 24-prompt
speed-bench sample (mean draft acceptance 0.640). Those results are not a
measurement of our exact v3.1 GGUF revision or workload. Start with draft depth
3; confirm `draft acceptance` in logs, then compare depths 2, 3 and 4 against
MTP-off using identical prompts and sampling. Measure peak memory, prefill,
decode, TTFT, long-prompt behavior and multi-turn tool calls before treating
this as qualified production behavior. This MTP implementation uses QSA; measure
long-context behavior separately rather than extrapolating short-prompt speed.

The older 32k/128k/256k profiles ending in `llamacpp-mtp-*` use an isolated
September Unsloth shared-head runtime and are retained for compatibility and
comparison. The new default does not use that shared-head contract.

## Automatic crash recovery

`./scripts/start` and `./scripts/restart` launch eliza-medium under a supervisor
inside the service's tmux session. Recovery continues when the TUI closes.
If the model aborts, segfaults, is killed, or exits unexpectedly (including an
unexpected exit code 0), the supervisor reaps it, terminates remaining worker
processes, then starts the same profile and waits for its health endpoint.

Retries use exponential backoff: 2, 4, 8, 16, 32, then at most 60 seconds.
Five minutes of healthy uptime resets the delay. During recovery the Services
tab shows `restarting`, with `retry #N` or `loading` as health information.
`./scripts/status eliza-medium` reports restart count, last exit code and the
scheduled retry timestamp; `./scripts/status-stack` also shows recovery.
Detailed crash/retry messages are appended to `logs/eliza-medium.log`, and the
current supervisor snapshot is `.runtime/eliza-medium.supervisor.json`.

Deliberate `stop` and profile switches stop the supervisor first, wait for model
workers to exit, then close tmux. A stop during backoff cancels the pending retry.
Only one supervisor can own a service at a time. Setup/artifact errors (exit
codes 2, 64 or 78) stop recovery and report `failed`: fix the configuration and
restart instead of repeatedly loading an invalid model. Health checks mark a
reload ready; a temporarily slow HTTP response does not kill a running model.

Optional settings in `.env` (also shown in `.env.example`):

```bash
ELIZA_MEDIUM_AUTORESTART="true"
ELIZA_MEDIUM_RESTART_DELAY_SECONDS="2"
ELIZA_MEDIUM_RESTART_MAX_DELAY_SECONDS="60"
ELIZA_MEDIUM_RESTART_RESET_SECONDS="300"
SERVICE_SHUTDOWN_TIMEOUT_SECONDS="10"
SERVICE_STOP_TIMEOUT_SECONDS="30"
```

Restart the service once after updating to attach the supervisor to an existing
deployment. `ELIZA_MEDIUM_AUTORESTART=false` runs the medium process directly.
Recovery reloads the model rather than resuming an interrupted generation;
clients must retry requests that failed during the crash. The supplied systemd
unit starts/stops the tmux-managed service, while the supervisor owns model
restart policy. A whole-host restart still requires the service to be started
at boot through the normal stack/systemd setup.

## ds4dfm (Rust-host DwarfStar) backend

`BACKEND=ds4dfm` runs [`Baekpica/ds4-dfm-rs`](https://github.com/Baekpica/ds4-dfm-rs), the
Rust-host continuation of DwarfStar (`antirez → Entrpi → Baekpica`): Rust owns serving,
scheduling, KV policy and memory admission, the C/CUDA kernels stay native, and the release
target is exactly the DGX Spark / GB10. It is a native build — no Docker — and serves OpenAI
Chat/Completions/Responses **and Anthropic Messages**, with N-bank continuous serving,
disk-KV prefix reuse and an embedded MTP block.

```bash
./scripts/setup ds4dfm            # clone, cargo + make cuda-spark (pins Rust 1.98)
./scripts/setup ds4dfm --check    # upstream drift, binaries, weights
```

Weights are Baekpica's `MQ-Q5-SSD-PLE-BF16` artifact (~173 GiB total: three Q5 main shards
plus the shared BF16 SSD-PLE sidecars, which live under `MQ-Q6-SSD-PLE-BF16/ple/`; the
download links `ple/` into the Q5 folder as upstream prescribes):

```bash
./scripts/download-models eliza-medium --profile medium/qwen3.8-flash-next-ds4dfm-262k
./scripts/start eliza-medium --profile medium/qwen3.8-flash-next-ds4dfm-262k
./scripts/logs eliza-medium
./scripts/smoke-test eliza-medium
```

The server is addressed as `qwen3.8-flash-next` on `ELIZA_MEDIUM_PORT` (8001), so clients
and smoke tests are backend-agnostic. Qualified scope on one Spark: 262,144 one-bank and
196,608 two-bank serving with MTP draft 2, YaRN factor 2 through 524,288 (the 524k profile;
a complete 1M-token prompt is not claimed), still-image input (user messages only, at most
four PNG/JPEG data URIs, 10 MiB decoded per image), and disk KV via `--kv-disk-dir`.
Everything beyond those gates is marked unqualified upstream; keep to the qualified shapes.

Knobs map through `DS4DFM_*`: `MODEL_ID`, `MAX_SEQS` (bank width), `MTP_DRAFT` (0 = off),
`PREFIX_REUSE` (`off|exact|partial|auto`), `QWEN_BATCH`, `QWEN_PLE_CACHE_MB`,
`QWEN_PLE_WORKERS`, `QWEN_PREFILL_CHUNK`, `MEM_FLOOR_GB`, `MEMGOV` (`observe|enforce`),
`KV_TO_DISK`/`KV_DIR`/`KV_MB`, `EXTRA_ARGS`, and `PREFLIGHT` (runs `--check-config` and prints the resolved serving plan
before starting). The official FP8 PLE sidecar can replace BF16 later with `DS4DFM_PLE_DIR`
pointing at the extracted `PLE-FP8` directory — use a separate `--kv-disk-dir` per PLE
format, since snapshots are format-tagged and cross-format restore is refused.

### Weight owner and worker (manual)

For restart-heavy operation, keep one weight owner alive and restart only workers. In a
durable tmux session (not the service session):

```bash
DS4DFM=~/src/ds4-dfm-rs
MODEL=$MODEL_HOME/ds4dfm/MQ-Q5-SSD-PLE-BF16/Qwen3.8-Flash-Next-MQ-Q5-SSD-PLE-BF16-00001-of-00003.gguf

$DS4DFM/ds4_weight_server \
  --base "$MODEL" \
  --manifest /tmp/ds4dfm-weights.manifest \
  --backend vmm \
  --scope base \
  --reserve-gb 32
```

Wait for both `broker listening` and `ready manifest=...`, then add to `.env` (tmux sessions
do not inherit exported shell variables):

```bash
DS4_CUDA_WEIGHT_IPC_MANIFEST="/tmp/ds4dfm-weights.manifest"
DS4_CUDA_WEIGHT_IPC_SCOPE="base"
```

and `./scripts/restart eliza-medium --profile ...` — the worker imports the owner's VMM
ranges instead of re-uploading ~80 GiB. Never run a second full-model owner beside the
first on the same box, and stop the worker and owner (in that order) before reclaiming
memory.

### Caveats

- The fork is young (single maintainer, fast-moving); rerun `./scripts/setup ds4dfm --check`
  before debugging, and rebuild after pulling.
- Only the pinned artifact layouts are accepted; the base Q5 is the validated pairing (the
  Uncensored BF16 main has a known partial-fork gate failure upstream).
- Inherited default: a tool-call protocol reminder is injected into deep tools-armed
  conversations (`DS4_TOOL_CALL_REMINDER=0` disables it). Disclose the knob position when
  comparing benchmark numbers.
- `GET /v1/stats` exposes `last_request` (`effective_lane`, `reuse_kind`,
  `speculation_active`) — useful for verifying prefix reuse and MTP are actually active.

## Benchmark

```bash
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k --context-tokens 32768
```
