# vocode-bridge

WebSocket bridge for local voice turns using native Vocode turn-based orchestration.

Current protocol supports:

- PCM16 audio chunks over WebSocket
- final transcript through hosted STT
- assistant text through hosted `eliza-small`
- assistant audio through hosted TTS

Start:

```bash
./scripts/start vocode-bridge --profile vocode/bridge-local
./scripts/smoke-test vocode-bridge --profile vocode/bridge-local
```

The bridge runtime uses `vocode.turn_based.TurnBasedConversation` with local HTTP adapters for STT, LLM, and TTS.
