#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request


def request_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=1800) as response:
        return json.loads(response.read().decode("utf-8"))


def synthetic_prompt(token_target: int) -> str:
    # This is an approximation. It deliberately avoids huge checked-in prompt files.
    chunk = "The quick brown fox jumps over the lazy dog. "
    approx_chars = token_target * 4
    repeated = chunk * ((approx_chars // len(chunk)) + 1)
    return repeated[:approx_chars]


def main() -> int:
    parser = argparse.ArgumentParser(description="Approximate long-context test for an OpenAI-compatible endpoint.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--tokens", type=int, default=8192)
    parser.add_argument("--prompt-file", type=pathlib.Path)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--output-json", type=pathlib.Path)
    args = parser.parse_args()

    if args.prompt_file:
        context = args.prompt_file.read_text(encoding="utf-8")
    else:
        context = synthetic_prompt(args.tokens)

    payload = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": f"Read this context and then answer with one sentence saying you received it.\n\n{context}",
            }
        ],
        "max_tokens": args.max_tokens,
        "temperature": 0.0,
    }

    started = time.perf_counter()
    try:
        response = request_json(f"{args.base_url.rstrip('/')}/chat/completions", payload)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"long-context request failed: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - started
    content = response["choices"][0]["message"].get("content", "")
    result = {
        "model": args.model,
        "requested_tokens_approx": args.tokens,
        "prompt_chars": len(context),
        "elapsed_seconds": elapsed,
        "response": content.strip(),
    }

    print(json.dumps(result, indent=2))
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
