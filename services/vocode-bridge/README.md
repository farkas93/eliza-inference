# vocode-bridge

WebSocket bridge for local voice turns using a streaming-first bridge contract.

Current protocol supports:

- continuous PCM16 audio chunks over WebSocket
- final transcript through hosted STT
- assistant text through hosted `eliza-small`
- assistant audio through hosted TTS
- compatibility fallback `audio_input_end` for forced end-of-turn
- optional tool context forwarding (`tools` and `tool_choice`) to the local model

Start:

```bash
./scripts/start vocode-bridge --profile vocode/bridge-local
./scripts/smoke-test vocode-bridge --profile vocode/bridge-local
```

The bridge runtime maintains compatibility with existing turn-based clients while exposing a streaming-ready contract for GenieTor.
