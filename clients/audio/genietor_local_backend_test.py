#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json

import websockets


async def recv_json(websocket, timeout: float = 60.0) -> dict:
    raw = await asyncio.wait_for(websocket.recv(), timeout=timeout)
    message = json.loads(raw)
    print(json.dumps(message, indent=2))
    if message.get("type") == "error":
        raise RuntimeError(str(message.get("message") or "server returned error"))
    return message


async def main_async() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test GenieTor websocket server with ELIZA_BACKEND=local-vocode."
    )
    parser.add_argument("--url", default="ws://127.0.0.1:8080/ws")
    parser.add_argument("--text", default="Say hello from the local vocode smoke test.")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    assistant_text = ""
    got_audio = False

    async with websockets.connect(args.url, max_size=16 * 1024 * 1024) as websocket:
        deadline = asyncio.get_running_loop().time() + args.timeout
        saw_connected_banner = False

        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            message = await recv_json(websocket, timeout=max(1.0, remaining))
            message_type = message.get("type")

            if message_type == "agentResponse":
                text = str(message.get("text") or "").strip()
                if text == "Connected! Ask me anything.":
                    saw_connected_banner = True
                    await websocket.send(json.dumps({"type": "userMessage", "text": args.text}))
                    continue
                if text:
                    assistant_text = text
            elif message_type == "audioResponse":
                got_audio = bool(message.get("audio"))

            if saw_connected_banner and assistant_text and got_audio:
                break

    if not saw_connected_banner:
        raise RuntimeError("Did not receive GenieTor session-ready banner before timeout")
    if not assistant_text:
        raise RuntimeError(
            "Did not receive non-empty assistant text from GenieTor server before timeout"
        )
    if not got_audio:
        raise RuntimeError("Did not receive assistant audio from GenieTor server before timeout")

    print(
        json.dumps(
            {
                "status": "ok",
                "assistant_text": assistant_text,
                "received_audio": got_audio,
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
