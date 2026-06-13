#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import wave
from pathlib import Path

import websockets


async def recv_until(websocket, expected_type: str, timeout: float = 300.0) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for {expected_type}")
        raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
        message = json.loads(raw)
        print(json.dumps(message, indent=2))
        if message.get("type") == "error":
            raise RuntimeError(message.get("message", "bridge returned error"))
        if message.get("type") == expected_type:
            return message


def wav_to_chunks(wav_bytes: bytes, chunk_frames: int) -> tuple[int, list[bytes]]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        if channels != 1 or sample_width != 2:
            raise ValueError(f"Expected mono PCM16 WAV, got channels={channels} sample_width={sample_width}")
        chunks: list[bytes] = []
        while True:
            data = wav.readframes(chunk_frames)
            if not data:
                break
            chunks.append(data)
    return sample_rate, chunks


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the vocode bridge WebSocket protocol.")
    parser.add_argument("--url", required=True, help="WebSocket URL, e.g. ws://127.0.0.1:8021/ws")
    parser.add_argument("--text", default="Hello from the Vocode bridge smoke test.")
    parser.add_argument("--audio-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("tmp/vocode-bridge-synth.wav"))
    parser.add_argument("--chunk-frames", type=int, default=2048)
    args = parser.parse_args()

    async with websockets.connect(args.url, max_size=16 * 1024 * 1024) as websocket:
        await recv_until(websocket, "ready", timeout=30)
        await websocket.send(json.dumps({"type": "start", "session_id": "smoke-test"}))
        await recv_until(websocket, "started", timeout=30)

        if args.audio_file:
            wav_bytes = args.audio_file.read_bytes()
        else:
            await websocket.send(json.dumps({"type": "synthesize", "text": args.text}))
            audio_message = await recv_until(websocket, "audio", timeout=300)
            wav_bytes = base64.b64decode(audio_message["audio"])
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(wav_bytes)
            print(f"wrote synthesized prompt WAV to {args.output}")

        sample_rate, chunks = wav_to_chunks(wav_bytes, args.chunk_frames)
        for chunk in chunks:
            await websocket.send(
                json.dumps(
                    {
                        "type": "audio_input",
                        "audio": base64.b64encode(chunk).decode("ascii"),
                        "mime_type": f"audio/pcm;rate={sample_rate}",
                    }
                )
            )
            await recv_until(websocket, "audio_received", timeout=30)

        await websocket.send(json.dumps({"type": "audio_input_end"}))
        transcript = await recv_until(websocket, "transcript", timeout=300)
        text = str(transcript.get("text") or "").strip()
        if not text:
            raise RuntimeError("Bridge returned an empty transcript")

        await websocket.send(json.dumps({"type": "stop"}))
        await recv_until(websocket, "closed", timeout=30)

    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
