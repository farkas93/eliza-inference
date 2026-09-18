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

## Benchmark

```bash
./scripts/run-benchmark memory-footprint eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k --context-tokens 32768
```
