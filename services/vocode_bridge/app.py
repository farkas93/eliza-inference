from __future__ import annotations

import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
import uuid
import wave
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="Eliza Vocode Bridge", version="0.1.0")


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
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get_content_type()


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


def generate_assistant_text(user_text: str) -> str:
    llm_base_url = _eliza_small_base_url()
    payload = {
        "model": _eliza_small_model(),
        "messages": [
            {
                "role": "system",
                "content": _voice_system_prompt(),
            },
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
        "max_tokens": 120,
    }
    try:
        body, _ = _post_json(f"{llm_base_url}/chat/completions", payload)
    except Exception as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc
    result = json.loads(body.decode("utf-8"))
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned no choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        assistant_text = content.strip()
    elif isinstance(content, list):
        assistant_text = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        ).strip()
    else:
        assistant_text = str(message.get("reasoning_content") or "").strip()

    if not assistant_text:
        raise RuntimeError("LLM returned an empty assistant response")
    return assistant_text


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


@dataclass
class BridgeSession:
    session_id: str = field(default_factory=lambda: f"bridge_{uuid.uuid4().hex}")
    sample_rate: int = 16000
    pcm: bytearray = field(default_factory=bytearray)

    def reset_audio(self) -> None:
        self.pcm.clear()


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
        "mode": "websocket-turn-bridge",
        "dependencies": dependencies,
    }


async def _emit_assistant_turn(websocket: WebSocket, assistant_text: str) -> None:
    audio_bytes, mime_type = synthesize_text(assistant_text)
    audio_base64 = base64.b64encode(audio_bytes).decode("ascii")

    await websocket.send_json({"type": "assistant_text", "text": assistant_text})
    await websocket.send_json(
        {
            "type": "assistant_audio",
            "audio": audio_base64,
            "mime_type": mime_type,
        }
    )

    # Backward compatibility event for existing bridge tests/clients.
    await websocket.send_json(
        {
            "type": "audio",
            "audio": audio_base64,
            "mime_type": mime_type,
        }
    )
    await websocket.send_json({"type": "turn_complete"})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    session = BridgeSession()
    await websocket.send_json(
        {
            "type": "ready",
            "session_id": session.session_id,
            "mode": "websocket-turn-bridge",
            "note": "STT -> local LLM -> TTS bridge for local full-turn voice sessions.",
        }
    )

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")

            if message_type == "start":
                session.session_id = str(message.get("session_id") or session.session_id)
                session.reset_audio()
                await websocket.send_json({"type": "started", "session_id": session.session_id})

            elif message_type == "audio_input":
                audio_b64 = str(message.get("audio") or "")
                mime_type = str(message.get("mime_type") or message.get("mimeType") or "audio/pcm;rate=16000")
                session.sample_rate = _parse_sample_rate(mime_type, session.sample_rate)
                if audio_b64:
                    session.pcm.extend(base64.b64decode(audio_b64))
                await websocket.send_json({"type": "audio_received", "bytes": len(session.pcm)})

            elif message_type == "audio_input_end":
                if not session.pcm:
                    await websocket.send_json({"type": "error", "message": "No audio buffered"})
                    continue
                wav_bytes = _pcm16_to_wav(bytes(session.pcm), session.sample_rate)
                session.reset_audio()
                result = transcribe_wav(wav_bytes)
                transcript_text = str(result.get("text", "")).strip()
                await websocket.send_json(
                    {
                        "type": "transcript",
                        "text": transcript_text,
                        "is_final": True,
                        "language": result.get("language"),
                        "duration": result.get("duration"),
                    }
                )
                if not transcript_text:
                    await websocket.send_json({"type": "error", "message": "STT returned an empty transcript"})
                    continue

                assistant_text = generate_assistant_text(transcript_text)
                await _emit_assistant_turn(websocket, assistant_text)

            elif message_type in {"user_text", "user_message"}:
                user_text = str(message.get("text") or "").strip()
                if not user_text:
                    await websocket.send_json({"type": "error", "message": "Missing text"})
                    continue
                assistant_text = generate_assistant_text(user_text)
                await _emit_assistant_turn(websocket, assistant_text)

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
                await websocket.send_json({"type": "closed"})
                await websocket.close()
                return

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {message_type}"})

    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
