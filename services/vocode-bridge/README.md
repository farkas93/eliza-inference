# vocode-bridge

Experimental WebSocket bridge for validating browser audio transport before deeper Vocode integration.

Current protocol supports:

- PCM16 audio chunks over WebSocket
- final transcript through the hosted STT endpoint
- text synthesis through the hosted TTS endpoint

Start:

```bash
./scripts/start vocode-bridge --profile vocode/bridge-local
./scripts/smoke-test vocode-bridge --profile vocode/bridge-local
```

This intentionally starts with the bridge contract and hosted endpoints. The next step is deciding whether to replace the transcript endpointing layer with Vocode internals or keep the simpler service pipeline.
