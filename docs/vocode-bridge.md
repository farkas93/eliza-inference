# Vocode Bridge

`vocode-bridge` is a WebSocket bridge that orchestrates a full local voice turn using hosted services:

```text
Browser or test client
  -> WebSocket PCM16 chunks
  -> vocode-bridge
  -> STT endpoint (:8011)
  -> eliza-small chat endpoint (:8002)
  -> TTS endpoint (:8012)
  -> transcript + assistant text + assistant audio events
```

The bridge now uses `vocode.turn_based.TurnBasedConversation` with local HTTP adapters for STT, `eliza-small`, and TTS.

## Environment

Profile: `configs/profiles/vocode/bridge-local.env`

```bash
STT_BASE_URL=http://127.0.0.1:8011/v1
STT_MODEL=whisper-small
ELIZA_SMALL_BASE_URL=http://127.0.0.1:8002/v1
ELIZA_SMALL_MODEL=gemma-4-e2b-it-q4-k-m
TTS_BASE_URL=http://127.0.0.1:8012/v1
TTS_MODEL=piper-lessac-medium
TTS_VOICE=lessac
VOICE_SYSTEM_PROMPT="You are a concise local voice assistant. Answer in one short sentence."
```

## Start

Make sure STT, `eliza-small`, and TTS are running first:

```bash
./scripts/start stt --profile stt/faster-whisper-small-cpu
./scripts/start eliza-small --profile small/gemma4-e2b-q4-llamacpp-8k
./scripts/start tts --profile tts/piper-lessac
```

If bridge dependencies changed locally, rebuild the bridge environment first:

```bash
./scripts/setup vocode --reinstall
```

Then start the bridge:

```bash
./scripts/start vocode-bridge --profile vocode/bridge-local
```

## Smoke Test

```bash
./scripts/smoke-test vocode-bridge --profile vocode/bridge-local
```

The bridge smoke test:

```text
1. Connects to ws://127.0.0.1:8021/ws
2. Requests bridge-side TTS for a prompt sentence
3. Streams the synthesized WAV back as PCM chunks
4. Ends audio input
5. Waits for transcript, assistant text, assistant audio, and turn completion
```

It writes the prompt WAV to:

```text
tmp/vocode-bridge-synth.wav
```

## Protocol

Client messages:

```json
{ "type": "start", "session_id": "optional-id" }
{ "type": "audio_input", "audio": "base64-pcm16", "mime_type": "audio/pcm;rate=16000" }
{ "type": "audio_input_end" }
{ "type": "user_text", "text": "Hello" }
{ "type": "synthesize", "text": "Hello." }
{ "type": "stop" }
```

Bridge messages:

```json
{ "type": "ready", "session_id": "..." }
{ "type": "started", "session_id": "..." }
{ "type": "audio_received", "bytes": 12345 }
{ "type": "transcript", "text": "...", "is_final": true }
{ "type": "assistant_text", "text": "..." }
{ "type": "assistant_audio", "audio": "base64-wav", "mime_type": "audio/wav" }
{ "type": "turn_complete" }
{ "type": "closed" }
{ "type": "error", "message": "..." }
```

`synthesize` requests still return `{ "type": "audio", ... }` for prompt-generation utilities.

## Failure Smoke Tests

Use `--expect-error` to validate upstream failures:

```bash
# STT failure (bridge started with bad STT_BASE_URL)
.venvs/vocode/bin/python clients/audio/vocode_bridge_test.py \
  --url ws://127.0.0.1:8021/ws \
  --expect-error "STT request failed"

# LLM failure (bridge started with bad ELIZA_SMALL_BASE_URL)
.venvs/vocode/bin/python clients/audio/vocode_bridge_test.py \
  --url ws://127.0.0.1:8021/ws \
  --text-only-turn \
  --expect-error "LLM request failed"

# TTS failure (bridge started with bad TTS_BASE_URL)
.venvs/vocode/bin/python clients/audio/vocode_bridge_test.py \
  --url ws://127.0.0.1:8021/ws \
  --text-only-turn \
  --expect-error "TTS request failed"
```

## Health Endpoint

`GET /health` reports dependency reachability for STT, `eliza-small`, and TTS via each service's `/v1/models` endpoint. The top-level status becomes `degraded` if any dependency probe fails.

The health payload includes:

- `mode: "vocode-turn-based-bridge"`
- `engine: "vocode.turn_based.TurnBasedConversation"`
