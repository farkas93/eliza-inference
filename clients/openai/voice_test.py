#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description="Voice LLM latency sanity test.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()

    latencies: list[float] = []
    for idx in range(args.rounds):
        payload = {
            "model": args.model,
            "messages": [
                {"role": "system", "content": "You are a concise voice assistant. Keep answers short."},
                {"role": "user", "content": "Say a short greeting in under ten words."},
            ],
            "max_tokens": 48,
            "temperature": 0.2,
        }
        req = urllib.request.Request(
            f"{args.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        started = time.perf_counter()
        with urllib.request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
        elapsed = time.perf_counter() - started
        latencies.append(elapsed)
        content = data["choices"][0]["message"].get("content", "").strip()
        print(f"round={idx + 1} elapsed_seconds={elapsed:.3f} response={content}")

    avg = sum(latencies) / len(latencies)
    print(f"average_seconds={avg:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
