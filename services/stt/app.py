from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

app = FastAPI(title="Eliza STT", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "backend": os.environ.get("BACKEND", "faster-whisper"),
        "model": os.environ.get("MODEL_NAME", os.environ.get("MODEL_ID", "unknown")),
    }


@app.get("/v1/models")
def models() -> dict[str, object]:
    model_name = os.environ.get("MODEL_NAME", os.environ.get("MODEL_ID", "local-stt"))
    return {"object": "list", "data": [{"id": model_name, "object": "model"}]}


@lru_cache(maxsize=1)
def get_faster_whisper_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed") from exc

    model_path = os.environ.get("MODEL_DIR") or os.environ.get("MODEL_ID", "Systran/faster-whisper-large-v3")
    device = os.environ.get("DEVICE", "cuda")
    compute_type = os.environ.get("COMPUTE_TYPE", "float16")
    return WhisperModel(model_path, device=device, compute_type=compute_type)


def transcribe_faster_whisper(path: Path, language: str | None) -> dict[str, object]:
    model = get_faster_whisper_model()
    segments, info = model.transcribe(str(path), language=language, vad_filter=True)
    segment_payload: list[dict[str, object]] = []
    texts: list[str] = []

    for segment in segments:
        text = segment.text.strip()
        if text:
            texts.append(text)
        segment_payload.append(
            {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            }
        )

    return {
        "text": " ".join(texts).strip(),
        "language": getattr(info, "language", language),
        "duration": getattr(info, "duration", None),
        "segments": segment_payload,
    }


@app.post("/v1/audio/transcriptions")
async def audio_transcriptions(
    file: Annotated[UploadFile, File()],
    model: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    response_format: Annotated[str, Form()] = "json",
) -> dict[str, object]:
    backend = os.environ.get("BACKEND", "faster-whisper")
    if backend != "faster-whisper":
        raise HTTPException(status_code=501, detail=f"STT backend is not implemented in API wrapper: {backend}")

    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        result = transcribe_faster_whisper(tmp_path, language or os.environ.get("LANGUAGE") or None)
    except Exception as exc:  # pragma: no cover - runtime dependency errors are surfaced to callers
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    if response_format == "text":
        return {"text": result["text"]}
    return result
