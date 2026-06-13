from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

app = FastAPI(title="Eliza TTS", version="0.1.0")


class SpeechRequest(BaseModel):
    model: str | None = None
    input: str = Field(min_length=1)
    voice: str | None = None
    response_format: str = "wav"
    speed: float | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "backend": os.environ.get("BACKEND", "piper"),
        "model": os.environ.get("MODEL_NAME", "local-tts"),
    }


@app.get("/v1/models")
def models() -> dict[str, object]:
    model_name = os.environ.get("MODEL_NAME", "local-tts")
    return {"object": "list", "data": [{"id": model_name, "object": "model"}]}


def synthesize_piper(text: str) -> bytes:
    piper_bin = os.environ.get("PIPER_BIN", "piper")
    model_path = os.environ.get("PIPER_VOICE_PATH")
    config_path = os.environ.get("PIPER_CONFIG_PATH")

    if not model_path:
        raise RuntimeError("PIPER_VOICE_PATH is required")
    if not Path(model_path).exists():
        raise RuntimeError(f"Piper voice model not found: {model_path}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        output_path = Path(tmp.name)

    cmd = [piper_bin, "--model", model_path, "--output_file", str(output_path)]
    if config_path and Path(config_path).exists():
        cmd.extend(["--config", config_path])

    try:
        subprocess.run(cmd, input=text, text=True, check=True, capture_output=True)
        return output_path.read_bytes()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Piper binary not found: {piper_bin}") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        raise RuntimeError(f"Piper synthesis failed: {stderr}") from exc
    finally:
        output_path.unlink(missing_ok=True)


@app.post("/v1/audio/speech")
def audio_speech(request: SpeechRequest) -> Response:
    backend = os.environ.get("BACKEND", "piper")
    if backend != "piper":
        raise HTTPException(status_code=501, detail=f"TTS backend is not implemented in API wrapper: {backend}")

    if request.response_format != "wav":
        raise HTTPException(status_code=400, detail="Only response_format=wav is currently supported")

    try:
        audio = synthesize_piper(request.input)
    except Exception as exc:  # pragma: no cover - runtime dependency errors are surfaced to callers
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(content=audio, media_type="audio/wav")
