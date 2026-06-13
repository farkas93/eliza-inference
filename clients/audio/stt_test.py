#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import struct
import tempfile
import urllib.request
import wave
from pathlib import Path


def write_test_wav(path: Path, seconds: float = 1.0, sample_rate: int = 16000) -> None:
    # A short tone is enough to validate upload/decoding without checking transcript quality.
    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(frames):
            sample = int(0.08 * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
            wav.writeframes(struct.pack("<h", sample))


def multipart_body(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = "----eliza-stt-smoke-test"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="test.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n".encode()
    )
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an OpenAI-compatible STT endpoint.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--audio-file", type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = args.audio_file or Path(temp_dir) / "test.wav"
        if args.audio_file is None:
            write_test_wav(audio_path)

        body, boundary = multipart_body({"model": args.model, "response_format": "json"}, audio_path)
        request = urllib.request.Request(
            f"{args.base_url.rstrip('/')}/audio/transcriptions",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = json.loads(response.read().decode("utf-8"))

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
