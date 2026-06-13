#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an OpenAI-compatible TTS endpoint.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--voice", default="default")
    parser.add_argument("--text", default="Hello from the DGX Spark text to speech service.")
    parser.add_argument("--output", type=Path, default=Path("tmp/tts-smoke-test.wav"))
    args = parser.parse_args()

    payload = {
        "model": args.model,
        "voice": args.voice,
        "input": args.text,
        "response_format": "wav",
    }
    request = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        audio = response.read()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(audio)
    print(f"wrote {len(audio)} bytes to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
