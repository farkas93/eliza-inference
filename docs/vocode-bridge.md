# Vocode Bridge

`vocode-bridge` is a bounded experiment for validating whether browser-provided audio can be routed through a server-side voice bridge before integrating deeper Vocode internals.

The current implementation intentionally starts with the bridge contract and the hosted STT/TTS endpoints:

```text
Browser or test client
  -> WebSocket PCM16 chunks
  -> vocode-bridge
  -> STT endpoint (:8011)
  -> transcript event

Client text
  -> vocode-bridge
  -> TTS endpoint (:8012)
  -> audio event
```

This lets us validate the transport protocol independently before deciding whether Vocode should own endpointing/turn-taking internally.

## Start

Make sure STT and TTS are running first:

```bash
./scripts/start stt --profile stt-faster-whisper-small-cpu
./scripts/start tts --profile tts-piper-lessac
```

Then start the bridge:

```bash
./scripts/start vocode-bridge --profile vocode-bridge-local
```

## Smoke Test

```bash
./scripts/smoke-test vocode-bridge --profile vocode-bridge-local
```

The smoke test:

```text
1. Connects to ws://127.0.0.1:8021/ws
2. Requests bridge-side TTS for a prompt sentence
3. Streams the synthesized WAV back as PCM chunks
4. Ends audio input
5. Waits for a transcript
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
{ "type": "synthesize", "text": "Hello." }
{ "type": "stop" }
```

Bridge messages:

```json
{ "type": "ready", "session_id": "..." }
{ "type": "started", "session_id": "..." }
{ "type": "audio_received", "bytes": 12345 }
{ "type": "transcript", "text": "...", "is_final": true }
{ "type": "audio", "audio": "base64-wav", "mime_type": "audio/wav" }
{ "type": "closed" }
{ "type": "error", "message": "..." }
```

## Next Decision

If this bridge contract is useful, the next step is to replace or augment the transcript path with Vocode `StreamingConversation` adapters. If that becomes more complex than helpful, we can keep this bridge contract and implement a simpler local backend directly.
