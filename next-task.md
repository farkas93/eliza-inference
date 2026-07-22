# Vocode + Stack Handoff Status (2026-07-12)

## Purpose

This document captures:

- our original goals and ambitions,
- where implementation currently stands,
- discrepancies/issues in the current state,
- concrete next steps for the new developer taking over.

---

## 1) Goals and ambitions we defined

### Product/architecture goals

- Run a reliable **local voice loop** using hosted services:
  - STT
  - `eliza-small` LLM
  - TTS
- Keep a **service-oriented** architecture (independent reusable endpoints).
- Keep `eliza-small` optimized for low-latency voice turns.
- Improve ops consistency: setup, smoke testing, health checks, profiles, and benchmark scripts.
- Move toward stable external aliasing/router model for broader clients.

### Operational goals

- Clean script naming and grouping.
- Better benchmark semantics and clearer command UX.
- Keep docs aligned with actual defaults and behavior.

---

## 2) Where we are now

## 2.1 Vocode bridge matured from transport spike to orchestration

`vocode-bridge` now performs full turn orchestration with hosted dependencies:

- STT transcription
- LLM response via `eliza-small`
- TTS synthesis
- bridge-side VAD endpointing for streaming input
- tool-context and tool-call fields in protocol
- dependency-aware health endpoint

Key files:

- `services/vocode_bridge/app.py`
- `configs/profiles/vocode/bridge-local.env`
- `docs/vocode-bridge.md`
- `clients/audio/vocode_bridge_test.py`

## 2.3 Protocol and validation improved

- Streaming-first websocket contract is documented.
- `audio_input_end` retained as compatibility fallback.
- smoke test supports:
  - full assistant turn success,
  - auto-endpoint mode,
  - expected-failure cases (broken STT/LLM/TTS upstreams).

## 2.4 Script cleanup completed

- Root superscripts:
  - `scripts/setup`
  - `scripts/run-benchmark`
- Suite folders:
  - `scripts/installation-suite/`
  - `scripts/benchmark-suite/`

---

## 3) Discrepancies / issues observed

## 3.1 Medium-model default drift across config/docs

Current mismatch between:

- `configs/eliza-stack.toml`
- `README.md`
- `docs/eliza-stack.md`

The configured default medium profile/model and documented default are not consistently the same.

Impact: confusing operator behavior and benchmark comparisons.

## 3.2 Audio payload contract risk between bridge/server/frontend

`assistant_audio` is forwarded as base64 payload with mime metadata, while frontend playback path currently assumes a specific sample-rate/PCM interpretation in places.

Impact: potential distortion/silence under format mismatch.

## 3.4 Dual endpointing/VAD logic

There is VAD logic in both:

- bridge (`BRIDGE_VAD_*`), and
- local-vocode handling (`LOCAL_VOCODE_VAD_*`).

Impact: race conditions, clipping, inconsistent turn-end behavior.

## 3.5 Tool-call behavior in local path is only partially aligned

- bridge supports tool context + tool call payloads,
- local backend advertises `toolCalling: false` and does not fully model bridge tool events into full app-level tool loop.

Impact: ambiguous tool semantics in local mode.

## 3.6 Security hardening still pending

Services are LAN-reachable and unauthenticated by default.

Impact: acceptable only in trusted LAN; unsafe for broader exposure without controls.

## 3.7 Local-vocode conversation context is not retained across turns

Current bridge behavior sends only:

- `system` message
- current turn `user` message

to `eliza-small` per request, without a rolling multi-turn history buffer.

Impact: the model appears to "forget" prior turns despite large runtime context availability (for example 128k), because history is not being included in the prompt payload.

## 3.8 Local-vocode tool-call note is stale

This document currently says local backend advertises `toolCalling: false`, but implementation now advertises `toolCalling: true`.

Impact: handoff confusion about whether local mode tools are disabled vs partially wired.

## 3.9 Transcript visibility path needs architecture review

Spoken user transcript visibility was added via a bridge->backend->frontend event chain.

Need to confirm this architecture remains the right long-term boundary:

- bridge emits `transcript`,
- local backend maps to typed SDK event,
- server forwards as websocket `userTranscript`,
- frontend renders transcripted user messages distinctly from typed messages.

Impact: without a design check, transcript behavior may drift from future backend abstraction and duplicate/ordering edge cases may appear.

---

## 4) Recommended next steps

## P0 (must-do)

1. **Choose one canonical medium default** and align it everywhere:
   - `configs/eliza-stack.toml`
   - `README.md`
   - `docs/eliza-stack.md`
 2. **Add/verify `.env.example`** for both modes:
    - `gemini-live`
    - `local-vocode`
3. **Fix and document one audio contract** end-to-end (WAV vs PCM):
   - bridge output
   - server forwarding
   - frontend decode/playback.
4. **Implement multi-turn context retention in local-vocode bridge**:
   - maintain bounded rolling chat history per websocket session,
   - include prior user/assistant turns in `/chat/completions` payload,
   - apply deterministic token-budget trimming (drop oldest turns first, keep system + most recent turns).

## P1 (stability and consistency)

4. Pick one endpointing authority:
   - recommended: bridge-side VAD as canonical,
   - simplify server-side local-vocode endpointing logic.
5. Finalize local tool-call policy:
   - either wire full tool lifecycle in local mode,
   - or explicitly disable + document no-tools for local mode.
6. Add integration tests for:
   - local-vocode happy path,
   - upstream failure paths,
   - turn-completion timing behavior.
7. Add context observability/auditing for local-vocode:
   - per-turn log fields like `prompt_messages`, `prompt_tokens_est`, `history_turns_kept`,
   - explicit log when trimming occurs,
   - optional debug endpoint or test mode to inspect current in-memory session history.
8. Add regression tests for context continuity:
   - follow-up turn references a fact from an earlier turn,
   - behavior remains correct when history trimming starts.
9. Validate transcript-display architecture and behavior:
   - ensure one canonical event contract for user transcript across backends,
   - verify no duplicate user entries when both typed and spoken turns happen,
   - verify ordering (`transcript` appears before assistant response for the same turn),
   - document UI labeling for typed vs transcribed user messages.

## P2 (architecture completion)

7. Implement/finalize `eliza-router` if still desired:
   - `/health`
   - `/v1/models`
   - `/v1/chat/completions`
8. Define exposure policy for `eliza-small`:
   - internal-only vs LAN-visible vs router-gated.

---

## 5) Definition of done for local voice milestone

The local voice milestone is complete when:

- Backend runs with `ELIZA_BACKEND=local-vocode` and no Google key.
- End-to-end turn succeeds:
  - audio input -> transcript -> assistant text -> assistant audio -> turn complete.
- Multi-turn context continuity is validated:
  - follow-up turns can reference earlier user/assistant turns,
  - history trimming behavior is deterministic and observable.
- Audio format contract is explicit and tested.
- Docs are executable and consistent with actual defaults.
- Smoke and failure tests are deterministic and pass.

---

## 6) Key files for the next developer

- `configs/eliza-stack.toml`
- `services/vocode_bridge/app.py`
- `configs/profiles/vocode/bridge-local.env`
- `clients/audio/vocode_bridge_test.py`
- `docs/vocode-bridge.md`
- `docs/vocode-pipeline.md`
- `docs/eliza-stack.md`
- `README.md`
