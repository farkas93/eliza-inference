from __future__ import annotations

import base64
import io
import json
import logging
import math
import os
import re
import struct
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydub import AudioSegment
from vocode.turn_based.agent.base_agent import BaseAgent
from vocode.turn_based.input_device.base_input_device import BaseInputDevice
from vocode.turn_based.output_device.abstract_output_device import AbstractOutputDevice
from vocode.turn_based.synthesizer.base_synthesizer import BaseSynthesizer
from vocode.turn_based.transcriber.base_transcriber import BaseTranscriber
from vocode.turn_based.turn_based_conversation import TurnBasedConversation

app = FastAPI(title="Eliza Vocode Bridge", version="0.2.0")


def _bridge_log_level() -> int:
    raw = os.environ.get("BRIDGE_LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)


logging.basicConfig(
    level=_bridge_log_level(),
    format="%(asctime)s %(levelname)s [vocode-bridge] %(message)s",
)
logger = logging.getLogger("vocode-bridge")


def _stt_base_url() -> str:
    return os.environ.get("STT_BASE_URL", "http://127.0.0.1:8011/v1").rstrip("/")


def _stt_model() -> str:
    return os.environ.get("STT_MODEL", "whisper-small")


def _tts_base_url() -> str:
    return os.environ.get("TTS_BASE_URL", "http://127.0.0.1:8012/v1").rstrip("/")


def _tts_model() -> str:
    return os.environ.get("TTS_MODEL", "piper-lessac-medium")


def _tts_voice() -> str:
    return os.environ.get("TTS_VOICE", "lessac")


def _eliza_small_base_url() -> str:
    return os.environ.get("ELIZA_SMALL_BASE_URL", "http://127.0.0.1:8002/v1").rstrip("/")


def _eliza_small_model() -> str:
    return os.environ.get("ELIZA_SMALL_MODEL", "gemma-4-e2b-it-q4-k-m")


def _voice_system_prompt() -> str:
    return os.environ.get(
        "VOICE_SYSTEM_PROMPT",
        "You are a concise local voice assistant. Answer in one short sentence.",
    )


def _tools_mode() -> str:
    mode = os.environ.get("BRIDGE_TOOLS_MODE", "auto").strip().lower()
    if mode not in {"auto", "on", "off"}:
        return "auto"
    return mode


def _tool_call_fallback_text() -> str:
    return os.environ.get("BRIDGE_TOOL_CALL_FALLBACK_TEXT", "I need to run a tool before I can answer.")


def _vad_enabled() -> bool:
    return os.environ.get("BRIDGE_VAD_ENABLED", "true").lower() not in {"false", "0", "no", "off"}


def _vad_rms_threshold() -> float:
    return float(os.environ.get("BRIDGE_VAD_RMS_THRESHOLD", "450"))


def _vad_silence_ms() -> float:
    return float(os.environ.get("BRIDGE_VAD_SILENCE_MS", "700"))


def _vad_min_speech_ms() -> float:
    return float(os.environ.get("BRIDGE_VAD_MIN_SPEECH_MS", "300"))


def _parse_sample_rate(mime_type: str | None, default: int = 16000) -> int:
    if not mime_type:
        return default
    match = re.search(r"rate=(\d+)", mime_type)
    if not match:
        return default
    return int(match.group(1))


def _pcm16_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _pcm16_rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0

    sample_count = len(pcm) // 2
    if sample_count <= 0:
        return 0.0

    sum_squares = 0.0
    for (sample,) in struct.iter_unpack("<h", pcm[: sample_count * 2]):
        sum_squares += float(sample * sample)
    return math.sqrt(sum_squares / sample_count)


def _pcm_duration_ms(pcm: bytes, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    sample_count = len(pcm) / 2.0
    return (sample_count / float(sample_rate)) * 1000.0


def _multipart_body(fields: dict[str, str], file_bytes: bytes, filename: str) -> tuple[bytes, str]:
    boundary = f"----eliza-vocode-bridge-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: audio/wav\r\n\r\n".encode()
    )
    parts.append(file_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def _post_json(url: str, payload: dict[str, Any], timeout: int = 300) -> tuple[bytes, str]:
    logger.debug(
        "POST %s payload_keys=%s",
        url,
        sorted(payload.keys()),
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get_content_type()


def _http_error_text(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
        if body:
            return f"HTTP {exc.code}: {body}"
    except Exception:
        pass
    return f"HTTP {exc.code}"


def _get_json(url: str, timeout: int = 5) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def transcribe_wav(wav_bytes: bytes) -> dict[str, Any]:
    stt_base_url = _stt_base_url()
    stt_model = _stt_model()
    body, boundary = _multipart_body(
        {"model": stt_model, "response_format": "json"},
        wav_bytes,
        "utterance.wav",
    )
    request = urllib.request.Request(
        f"{stt_base_url}/audio/transcriptions",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"STT request failed: {exc}") from exc


def synthesize_text(text: str) -> tuple[bytes, str]:
    tts_base_url = _tts_base_url()
    tts_model = _tts_model()
    tts_voice = _tts_voice()
    try:
        return _post_json(
            f"{tts_base_url}/audio/speech",
            {
                "model": tts_model,
                "voice": tts_voice,
                "input": text,
                "response_format": "wav",
            },
        )
    except Exception as exc:
        raise RuntimeError(f"TTS request failed: {exc}") from exc


def generate_assistant_response(
    user_text: str,
    system_prompt: str,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: Any | None = None,
) -> dict[str, Any]:
    llm_base_url = _eliza_small_base_url()
    payload = {
        "model": _eliza_small_model(),
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
        "max_tokens": 120,
    }

    logger.debug(
        "LLM request model=%s tools=%s tool_choice=%s prompt_chars=%s",
        payload.get("model"),
        len(tools or []),
        "set" if tool_choice is not None else "unset",
        len(user_text),
    )

    if _tools_mode() != "off" and tools:
        payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice

    tools_rejected = False

    try:
        body, _ = _post_json(f"{llm_base_url}/chat/completions", payload)
    except urllib.error.HTTPError as exc:
        logger.warning("LLM HTTP error with tools: %s", _http_error_text(exc))
        if exc.code == 400 and "tools" in payload:
            fallback_payload = dict(payload)
            fallback_payload.pop("tools", None)
            fallback_payload.pop("tool_choice", None)
            try:
                logger.info("Retrying LLM request without tools after HTTP 400")
                body, _ = _post_json(f"{llm_base_url}/chat/completions", fallback_payload)
                tools_rejected = True
            except urllib.error.HTTPError as fallback_exc:
                logger.error("LLM HTTP error without tools: %s", _http_error_text(fallback_exc))
                raise RuntimeError(f"LLM request failed: {_http_error_text(fallback_exc)}") from fallback_exc
            except Exception as fallback_exc:
                logger.exception("LLM request failed during fallback request")
                raise RuntimeError(f"LLM request failed: {fallback_exc}") from fallback_exc
        else:
            raise RuntimeError(f"LLM request failed: {_http_error_text(exc)}") from exc
    except Exception as exc:
        logger.exception("LLM request failed")
        raise RuntimeError(f"LLM request failed: {exc}") from exc

    result = json.loads(body.decode("utf-8"))
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned no choices")

    message = choices[0].get("message") or {}
    tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    content = message.get("content")
    if isinstance(content, str):
        assistant_text = content.strip()
    elif isinstance(content, list):
        assistant_text = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        ).strip()
    else:
        assistant_text = str(message.get("reasoning_content") or "").strip()

    if not assistant_text and tool_calls:
        assistant_text = _tool_call_fallback_text().strip() or "I need to run a tool before I can answer."

    if not assistant_text:
        raise RuntimeError("LLM returned an empty assistant response")

    logger.debug("LLM response text_chars=%s tool_calls=%s", len(assistant_text), len(tool_calls))

    return {
        "assistant_text": assistant_text,
        "tool_calls": tool_calls,
        "tools_rejected": tools_rejected,
    }


def _service_status(name: str, base_url: str, model: str) -> dict[str, Any]:
    models_url = f"{base_url}/models"
    try:
        payload = _get_json(models_url)
        return {
            "name": name,
            "ok": True,
            "base_url": base_url,
            "model": model,
            "models_endpoint": models_url,
            "available": [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)],
        }
    except urllib.error.HTTPError as exc:
        return {
            "name": name,
            "ok": False,
            "base_url": base_url,
            "model": model,
            "models_endpoint": models_url,
            "error": f"HTTP {exc.code}",
        }
    except Exception as exc:
        return {
            "name": name,
            "ok": False,
            "base_url": base_url,
            "model": model,
            "models_endpoint": models_url,
            "error": str(exc),
        }


class BridgeInputDevice(BaseInputDevice):
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._pcm = bytearray()
        self.active = False

    def set_sample_rate(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate

    def start_listening(self):
        self.active = True
        self._pcm.clear()

    def append_pcm(self, pcm_chunk: bytes) -> None:
        if not self.active:
            self.start_listening()
        self._pcm.extend(pcm_chunk)

    def has_audio(self) -> bool:
        return len(self._pcm) > 0

    def buffered_bytes(self) -> int:
        return len(self._pcm)

    def end_listening(self) -> AudioSegment:
        self.active = False
        wav_bytes = _pcm16_to_wav(bytes(self._pcm), self.sample_rate)
        self._pcm.clear()
        return AudioSegment.from_wav(io.BytesIO(wav_bytes))


class BridgeTranscriber(BaseTranscriber):
    def __init__(self):
        self.last_result: dict[str, Any] = {}

    def transcribe(self, audio_segment: AudioSegment) -> str:
        wav_buffer = io.BytesIO()
        audio_segment.export(wav_buffer, format="wav")
        result = transcribe_wav(wav_buffer.getvalue())
        self.last_result = result
        return str(result.get("text", "")).strip()


class BridgeAgent(BaseAgent):
    def __init__(self):
        super().__init__(initial_message=None)
        self.last_response = ""
        self.last_tool_calls: list[dict[str, Any]] = []
        self.tools: list[dict[str, Any]] = []
        self.tool_choice: Any | None = None
        self.system_prompt: str = _voice_system_prompt()
        self.tools_disabled_reason: str | None = None

    def respond(self, human_input: str):
        result = generate_assistant_response(human_input, self.system_prompt, self.tools, self.tool_choice)
        response = str(result.get("assistant_text") or "").strip()
        self.last_response = response
        raw_tool_calls = result.get("tool_calls")
        if isinstance(raw_tool_calls, list):
            self.last_tool_calls = [item for item in raw_tool_calls if isinstance(item, dict)]
        else:
            self.last_tool_calls = []

        if bool(result.get("tools_rejected")) and self.tools:
            self.tools = []
            self.tool_choice = None
            self.tools_disabled_reason = "context_overflow"
            logger.warning("Disabled tools for current session due to context overflow")

        return response


class BridgeSynthesizer(BaseSynthesizer):
    def __init__(self):
        self.last_audio_bytes = b""
        self.last_mime_type = "audio/wav"

    def synthesize(self, text) -> AudioSegment:
        audio_bytes, mime_type = synthesize_text(str(text))
        self.last_audio_bytes = audio_bytes
        self.last_mime_type = mime_type
        return AudioSegment.from_wav(io.BytesIO(audio_bytes))

    async def async_synthesize(self, text) -> AudioSegment:
        return self.synthesize(text)


class BridgeOutputDevice(AbstractOutputDevice):
    def __init__(self):
        self.last_audio_bytes = b""

    def send_audio(self, audio: AudioSegment) -> None:
        wav_buffer = io.BytesIO()
        audio.export(wav_buffer, format="wav")
        self.last_audio_bytes = wav_buffer.getvalue()


@dataclass
class BridgeSession:
    session_id: str = field(default_factory=lambda: f"bridge_{uuid.uuid4().hex}")
    sample_rate: int = 16000
    input_device: BridgeInputDevice = field(default_factory=BridgeInputDevice)
    transcriber: BridgeTranscriber = field(default_factory=BridgeTranscriber)
    agent: BridgeAgent = field(default_factory=BridgeAgent)
    synthesizer: BridgeSynthesizer = field(default_factory=BridgeSynthesizer)
    output_device: BridgeOutputDevice = field(default_factory=BridgeOutputDevice)
    conversation: TurnBasedConversation | None = None
    vad_enabled: bool = field(default_factory=_vad_enabled)
    vad_rms_threshold: float = field(default_factory=_vad_rms_threshold)
    vad_silence_ms: float = field(default_factory=_vad_silence_ms)
    vad_min_speech_ms: float = field(default_factory=_vad_min_speech_ms)
    speech_active: bool = False
    speech_ms: float = 0.0
    trailing_silence_ms: float = 0.0
    last_user_text: str = ""

    def set_tool_context(
        self,
        tools: list[dict[str, Any]] | None,
        tool_choice: Any | None = None,
        system_instruction: str | None = None,
    ) -> None:
        if _tools_mode() == "off":
            self.agent.tools = []
            self.agent.tool_choice = None
        else:
            self.agent.tools = [item for item in (tools or []) if isinstance(item, dict)]
            self.agent.tool_choice = tool_choice
        self.agent.tools_disabled_reason = None

        if isinstance(system_instruction, str) and system_instruction.strip():
            self.agent.system_prompt = system_instruction.strip()

    def ensure_conversation(self) -> TurnBasedConversation:
        if self.conversation is None:
            self.conversation = TurnBasedConversation(
                input_device=self.input_device,
                transcriber=self.transcriber,
                agent=self.agent,
                synthesizer=self.synthesizer,
                output_device=self.output_device,
            )
        return self.conversation

    def reset_audio(self) -> None:
        self.input_device.start_listening()
        self.speech_active = False
        self.speech_ms = 0.0
        self.trailing_silence_ms = 0.0

    def should_finalize_from_chunk(self, pcm_chunk: bytes) -> bool:
        if not self.vad_enabled:
            return False

        chunk_ms = _pcm_duration_ms(pcm_chunk, self.sample_rate)
        if chunk_ms <= 0:
            return False

        rms = _pcm16_rms(pcm_chunk)
        is_voice = rms >= self.vad_rms_threshold
        if is_voice:
            self.speech_active = True
            self.speech_ms += chunk_ms
            self.trailing_silence_ms = 0.0
            return False

        if not self.speech_active:
            return False

        self.speech_ms += chunk_ms
        self.trailing_silence_ms += chunk_ms
        return self.speech_ms >= self.vad_min_speech_ms and self.trailing_silence_ms >= self.vad_silence_ms


@app.get("/health")
def health() -> dict[str, Any]:
    dependencies = {
        "stt": _service_status("stt", _stt_base_url(), _stt_model()),
        "eliza_small": _service_status("eliza-small", _eliza_small_base_url(), _eliza_small_model()),
        "tts": _service_status("tts", _tts_base_url(), _tts_model()),
    }
    all_ok = all(dep.get("ok") for dep in dependencies.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "service": "vocode-bridge",
        "mode": "vocode-streaming-bridge" if _vad_enabled() else "vocode-turn-based-bridge",
        "engine": "vocode.turn_based.TurnBasedConversation",
        "vad": {
            "enabled": _vad_enabled(),
            "rms_threshold": _vad_rms_threshold(),
            "silence_ms": _vad_silence_ms(),
            "min_speech_ms": _vad_min_speech_ms(),
        },
        "dependencies": dependencies,
    }


async def _emit_assistant_turn_with_tools(
    websocket: WebSocket,
    assistant_text: str,
    audio_bytes: bytes,
    mime_type: str,
    tool_calls: list[dict[str, Any]],
    tool_status: str | None,
) -> None:
    if assistant_text:
        await websocket.send_json({"type": "assistant_text", "text": assistant_text})
    if tool_calls:
        logger.info("Emitting assistant tool calls count=%s", len(tool_calls))
        await websocket.send_json({"type": "assistant_tool_calls", "tool_calls": tool_calls})
        await websocket.send_json({"type": "assistant_waiting_tools"})
        return

    if tool_status:
        await websocket.send_json({"type": "assistant_tool_status", "status": tool_status})

    await websocket.send_json(
        {
            "type": "assistant_audio",
            "audio": base64.b64encode(audio_bytes).decode("ascii"),
            "mime_type": mime_type,
        }
    )
    await websocket.send_json({"type": "turn_complete"})


async def _process_audio_turn(websocket: WebSocket, session: BridgeSession) -> None:
    if not session.input_device.has_audio():
        await websocket.send_json({"type": "error", "message": "No audio buffered"})
        return

    session.ensure_conversation().end_speech_and_respond()
    transcript_text = str(session.transcriber.last_result.get("text", "")).strip()
    logger.info("Audio turn processed transcript_chars=%s", len(transcript_text))
    await websocket.send_json(
        {
            "type": "transcript",
            "text": transcript_text,
            "is_final": True,
            "language": session.transcriber.last_result.get("language"),
            "duration": session.transcriber.last_result.get("duration"),
        }
    )

    if not transcript_text:
        await websocket.send_json({"type": "no_speech_detected"})
        await websocket.send_json({"type": "turn_complete"})
        session.reset_audio()
        return

    session.last_user_text = transcript_text

    await _emit_assistant_turn_with_tools(
        websocket,
        session.agent.last_response,
        session.output_device.last_audio_bytes,
        session.synthesizer.last_mime_type,
        session.agent.last_tool_calls,
        session.agent.tools_disabled_reason,
    )
    session.reset_audio()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    session = BridgeSession()
    session.ensure_conversation()
    logger.info("WebSocket session connected session_id=%s", session.session_id)

    await websocket.send_json(
        {
            "type": "ready",
            "session_id": session.session_id,
            "mode": "vocode-streaming-bridge" if session.vad_enabled else "vocode-turn-based-bridge",
            "engine": "vocode.turn_based.TurnBasedConversation",
            "note": "Streaming bridge with endpointing over local STT, eliza-small, and TTS services.",
            "vad": {
                "enabled": session.vad_enabled,
                "rms_threshold": session.vad_rms_threshold,
                "silence_ms": session.vad_silence_ms,
                "min_speech_ms": session.vad_min_speech_ms,
            },
        }
    )

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            logger.debug("Received message type=%s", message_type)

            if message_type == "start":
                session.session_id = str(message.get("session_id") or session.session_id)
                system_instruction = message.get("system_instruction") or message.get("systemInstruction")
                session.set_tool_context(message.get("tools"), message.get("tool_choice"), system_instruction)
                session.reset_audio()
                await websocket.send_json({"type": "started", "session_id": session.session_id})

            elif message_type == "audio_input":
                audio_b64 = str(message.get("audio") or "")
                mime_type = str(message.get("mime_type") or message.get("mimeType") or "audio/pcm;rate=16000")
                session.sample_rate = _parse_sample_rate(mime_type, session.sample_rate)
                session.input_device.set_sample_rate(session.sample_rate)
                pcm_chunk = b""
                if audio_b64:
                    pcm_chunk = base64.b64decode(audio_b64)
                    session.input_device.append_pcm(pcm_chunk)
                await websocket.send_json({"type": "audio_received", "bytes": session.input_device.buffered_bytes()})

                if pcm_chunk and session.should_finalize_from_chunk(pcm_chunk):
                    logger.info(
                        "VAD finalized turn speech_ms=%.1f silence_ms=%.1f threshold=%.1f",
                        session.speech_ms,
                        session.trailing_silence_ms,
                        session.vad_rms_threshold,
                    )
                    await _process_audio_turn(websocket, session)

            elif message_type == "audio_input_end":
                await _process_audio_turn(websocket, session)

            elif message_type in {"user_text", "user_message"}:
                user_text = str(message.get("text") or "").strip()
                if not user_text:
                    await websocket.send_json({"type": "error", "message": "Missing text"})
                    continue

                system_instruction = message.get("system_instruction") or message.get("systemInstruction")
                session.set_tool_context(message.get("tools"), message.get("tool_choice"), system_instruction)
                session.last_user_text = user_text

                assistant_text = session.agent.respond(user_text)
                session.output_device.send_audio(session.synthesizer.synthesize(assistant_text))
                await _emit_assistant_turn_with_tools(
                    websocket,
                    session.agent.last_response,
                    session.output_device.last_audio_bytes,
                    session.synthesizer.last_mime_type,
                    session.agent.last_tool_calls,
                    session.agent.tools_disabled_reason,
                )

            elif message_type == "tool_context":
                system_instruction = message.get("system_instruction") or message.get("systemInstruction")
                session.set_tool_context(message.get("tools"), message.get("tool_choice"), system_instruction)
                await websocket.send_json({"type": "tool_context_updated", "tool_count": len(session.agent.tools)})

            elif message_type == "tool_result":
                results = message.get("results")
                if not isinstance(results, list):
                    await websocket.send_json({"type": "error", "message": "Missing tool results"})
                    continue

                logger.info("Received tool results count=%s", len(results))

                tool_result_prompt = (
                    "Original user request:\n"
                    f"{session.last_user_text or '(unknown)'}\n\n"
                    "Tool results:\n"
                    f"{json.dumps(results, ensure_ascii=True)}\n\n"
                    "Use the tool results to answer the user request concisely."
                )
                assistant_text = session.agent.respond(tool_result_prompt)
                session.output_device.send_audio(session.synthesizer.synthesize(assistant_text))
                await _emit_assistant_turn_with_tools(
                    websocket,
                    session.agent.last_response,
                    session.output_device.last_audio_bytes,
                    session.synthesizer.last_mime_type,
                    [],
                    session.agent.tools_disabled_reason,
                )

            elif message_type == "synthesize":
                text = str(message.get("text") or "")
                if not text.strip():
                    await websocket.send_json({"type": "error", "message": "Missing text for synthesis"})
                    continue
                audio_bytes, mime_type = synthesize_text(text)
                await websocket.send_json(
                    {
                        "type": "audio",
                        "audio": base64.b64encode(audio_bytes).decode("ascii"),
                        "mime_type": mime_type,
                    }
                )

            elif message_type == "stop":
                logger.info("Stop requested session_id=%s", session.session_id)
                await websocket.send_json({"type": "closed"})
                await websocket.close()
                return

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {message_type}"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected session_id=%s", session.session_id)
        return
    except Exception as exc:
        logger.exception("WebSocket session error session_id=%s", session.session_id)
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
