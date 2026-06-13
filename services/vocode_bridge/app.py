from __future__ import annotations

import base64
import io
import json
import os
import re
import urllib.request
import uuid
import wave
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="Eliza Vocode Bridge", version="0.1.0")


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


def transcribe_wav(wav_bytes: bytes) -> dict[str, Any]:
    stt_base_url = os.environ.get("STT_BASE_URL", "http://127.0.0.1:8011/v1").rstrip("/")
    stt_model = os.environ.get("STT_MODEL", "whisper-small")
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
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def synthesize_text(text: str) -> tuple[bytes, str]:
    tts_base_url = os.environ.get("TTS_BASE_URL", "http://127.0.0.1:8012/v1").rstrip("/")
    tts_model = os.environ.get("TTS_MODEL", "piper-lessac-medium")
    tts_voice = os.environ.get("TTS_VOICE", "lessac")
    return _post_json(
        f"{tts_base_url}/audio/speech",
        {
            "model": tts_model,
            "voice": tts_voice,
            "input": text,
            "response_format": "wav",
        },
    )


@dataclass
class BridgeSession:
    session_id: str = field(default_factory=lambda: f"bridge_{uuid.uuid4().hex}")
    sample_rate: int = 16000
    pcm: bytearray = field(default_factory=bytearray)

    def reset_audio(self) -> None:
        self.pcm.clear()


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "vocode-bridge",
        "mode": "websocket-audio-bridge",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    session = BridgeSession()
    await websocket.send_json(
        {
            "type": "ready",
            "session_id": session.session_id,
            "mode": "websocket-audio-bridge",
            "note": "Transcript/TTS bridge for validating browser audio transport before deeper Vocode integration.",
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
                await websocket.send_json(
                    {
                        "type": "transcript",
                        "text": result.get("text", ""),
                        "is_final": True,
                        "language": result.get("language"),
                        "duration": result.get("duration"),
                    }
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
