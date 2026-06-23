# Eliza Stack

The default stack is defined in:

```text
configs/eliza-stack.toml
```

The stack file selects which profile backs each stable service name:

```text
eliza-small   low-latency model for voice turns
eliza-medium  larger model for reasoning and coding
stt           speech-to-text endpoint
vocode-bridge browser-audio transport experiment
```

## Default Services

| Service | Profile | Port |
| --- | --- | ---: |
| `stt` | `stt/faster-whisper-small-cpu` | `8011` |
| `tts` | `tts/piper-lessac` | `8012` |
| `eliza-small` | `small/gemma4-e2b-q4-llamacpp-8k` | `8002` |
| `eliza-medium` | `medium/qwen3_6-27b-q4-llamacpp-32k` | `8001` |
| `vocode-bridge` | `vocode/bridge-local` | `8021` |

## Lifecycle

Start every enabled service:

```bash
./scripts/start-stack
```

Show status and model mapping:

```bash
./scripts/status-stack
```

Run smoke tests for every enabled service:

```bash
./scripts/smoke-test-stack
```

Stop services in reverse order:

```bash
./scripts/stop-stack
```

Use a different stack file:

```bash
./scripts/start-stack --config configs/my-stack.toml
```

## Model Aliases

The stack config already records the intended public aliases:

```text
eliza-small
eliza-medium
```

At the moment, clients still talk directly to the backend ports:

```text
eliza-small   http://127.0.0.1:8002/v1
eliza-medium  http://127.0.0.1:8001/v1
```

The next router slice will expose those aliases through one OpenAI-compatible endpoint, likely:

```text
http://127.0.0.1:8010/v1
```

Then clients will use `model=eliza-small` or `model=eliza-medium` without knowing the backing model/runtime.

## Adding A New Model

Create a profile under:

```text
configs/profiles/
```

Then point the stack config at it:

```toml
[models.eliza-small]
service = "eliza-small"
profile = "small/some-new-profile"
public_name = "eliza-small"
actual_model = "actual-backend-model-name"
base_url = "http://127.0.0.1:8002/v1"
```

Profiles describe how to run a concrete model. The stack config decides which profile currently fulfills `eliza-small` or `eliza-medium`.
