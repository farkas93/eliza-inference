#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
import time
import urllib.request
from pathlib import Path


def post_json(url: str, payload: dict, timeout: int = 300) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get_content_type()


def post_multipart_transcription(base_url: str, model: str, audio_path: Path) -> dict:
    boundary = "----eliza-voice-pipeline-test"
    parts: list[bytes] = []
    fields = {"model": model, "response_format": "json"}
    for name, value in fields.items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        b'Content-Disposition: form-data; name="file"; filename="input.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n"
    )
    parts.append(audio_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/audio/transcriptions",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def synthesize(base_url: str, model: str, voice: str, text: str, output_path: Path) -> float:
    started = time.perf_counter()
    audio, content_type = post_json(
        f"{base_url.rstrip('/')}/audio/speech",
        {
            "model": model,
            "voice": voice,
            "input": text,
            "response_format": "wav",
        },
    )
    elapsed = time.perf_counter() - started
    if content_type != "audio/wav":
        raise RuntimeError(f"Expected audio/wav from TTS, got {content_type}")
    output_path.write_bytes(audio)
    return elapsed


def chat(base_url: str, model: str, transcript: str) -> tuple[str, float]:
    started = time.perf_counter()
    body, _ = post_json(
        f"{base_url.rstrip('/')}/chat/completions",
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a concise local voice assistant. Answer in one short sentence.",
                },
                {"role": "user", "content": transcript},
            ],
            "max_tokens": 80,
            "temperature": 0.2,
        },
    )
    elapsed = time.perf_counter() - started
    payload = json.loads(body.decode("utf-8"))
    message = payload["choices"][0]["message"]
    content = message.get("content") or message.get("reasoning_content") or ""
    return content.strip(), elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end local voice pipeline smoke test.")
    parser.add_argument("--stt-base-url", required=True)
    parser.add_argument("--stt-model", required=True)
    parser.add_argument("--llm-base-url", required=True)
    parser.add_argument("--llm-model", required=True)
    parser.add_argument("--tts-base-url", required=True)
    parser.add_argument("--tts-model", required=True)
    parser.add_argument("--tts-voice", default="default")
    parser.add_argument("--input-text", default="Say hello and mention that the local voice pipeline is working.")
    parser.add_argument("--output", type=Path, default=Path("tmp/voice-pipeline-response.wav"))
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        prompt_wav = Path(temp_dir) / "prompt.wav"
        prompt_tts_seconds = synthesize(args.tts_base_url, args.tts_model, args.tts_voice, args.input_text, prompt_wav)

        stt_started = time.perf_counter()
        transcription = post_multipart_transcription(args.stt_base_url, args.stt_model, prompt_wav)
        stt_seconds = time.perf_counter() - stt_started
        transcript = str(transcription.get("text", "")).strip()

        if not transcript:
            raise RuntimeError("STT returned an empty transcript")

        assistant_text, llm_seconds = chat(args.llm_base_url, args.llm_model, transcript)
        if not assistant_text:
            raise RuntimeError("voice LLM returned an empty response")

        response_tts_seconds = synthesize(args.tts_base_url, args.tts_model, args.tts_voice, assistant_text, args.output)

    result = {
        "input_text": args.input_text,
        "transcript": transcript,
        "assistant_text": assistant_text,
        "output_wav": str(args.output),
        "timings": {
            "prompt_tts_seconds": round(prompt_tts_seconds, 3),
            "stt_seconds": round(stt_seconds, 3),
            "llm_seconds": round(llm_seconds, 3),
            "response_tts_seconds": round(response_tts_seconds, 3),
        },
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
