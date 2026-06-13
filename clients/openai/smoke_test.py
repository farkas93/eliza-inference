#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def request_json(url: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an OpenAI-compatible chat endpoint.")
    parser.add_argument("--base-url", required=True, help="Base URL, for example http://127.0.0.1:8002/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", default="Reply with exactly: ok")
    parser.add_argument("--max-tokens", type=int, default=32)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    try:
        models = request_json(f"{base_url}/models")
        print(f"models: {len(models.get('data', []))} available")
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"failed to query /models: {exc}", file=sys.stderr)
        return 1

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "max_tokens": args.max_tokens,
        "temperature": 0.0,
    }

    started = time.perf_counter()
    try:
        response = request_json(f"{base_url}/chat/completions", payload)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"failed to query /chat/completions: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - started
    message = response["choices"][0]["message"]
    content = message.get("content") or message.get("reasoning_content") or ""
    print(f"elapsed_seconds: {elapsed:.3f}")
    print(f"response: {content.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
