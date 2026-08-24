#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
import urllib.error
import urllib.request


def summarize_latencies(latencies: list[float]) -> dict:
    return {
        "round_count": len(latencies),
        "average_seconds": statistics.fmean(latencies) if latencies else 0.0,
        "median_seconds": statistics.median(latencies) if latencies else 0.0,
        "min_seconds": min(latencies) if latencies else 0.0,
        "max_seconds": max(latencies) if latencies else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Voice LLM latency sanity test.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output-json", type=pathlib.Path)
    args = parser.parse_args()

    rounds: list[dict] = []
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
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"round {idx + 1} failed: {exc}", file=sys.stderr)
            return 1
        elapsed = time.perf_counter() - started
        content = data["choices"][0]["message"].get("content", "").strip()
        print(f"round={idx + 1} elapsed_seconds={elapsed:.3f} response={content}", file=sys.stderr)
        rounds.append({"round": idx + 1, "elapsed_seconds": elapsed, "response": content})

    result = {
        "model": args.model,
        "base_url": args.base_url.rstrip("/"),
        "rounds": rounds,
        **summarize_latencies([round_entry["elapsed_seconds"] for round_entry in rounds]),
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
