#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def synthetic_prompt(token_target: int) -> str:
    chunk = "The quick brown fox jumps over the lazy dog. "
    approx_chars = token_target * 4
    repeated = chunk * ((approx_chars // len(chunk)) + 1)
    return repeated[:approx_chars]


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def extract_delta_text(choice: dict[str, Any]) -> tuple[str, str]:
    delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = delta.get("content") or message.get("content") or ""
    reasoning = (
        delta.get("reasoning_content")
        or delta.get("reasoning")
        or message.get("reasoning_content")
        or message.get("reasoning")
        or ""
    )
    return str(content or ""), str(reasoning or "")


def parse_sse_line(raw_line: bytes) -> dict[str, Any] | None:
    line = raw_line.decode("utf-8", errors="replace").strip()
    if not line or line.startswith(":") or not line.startswith("data:"):
        return None

    data = line[len("data:") :].strip()
    if not data or data == "[DONE]":
        return None

    return json.loads(data)


def print_raw_event(event: dict[str, Any], max_chars: int) -> None:
    serialized = json.dumps(event, ensure_ascii=False)
    if max_chars > 0 and len(serialized) > max_chars:
        serialized = serialized[:max_chars] + "..."
    print(f"raw_event={serialized}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect streaming responses and estimate tokens/sec for an OpenAI-compatible endpoint."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--prompt",
        default=(
            "Think step by step internally, then answer briefly. "
            "If your runtime exposes thinking tokens, include them in the stream. "
            "Question: what is 17 * 23?"
        ),
    )
    parser.add_argument("--prompt-file", type=pathlib.Path)
    parser.add_argument("--context-tokens", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--show-raw", action="store_true")
    parser.add_argument("--raw-max-chars", type=int, default=1200)
    parser.add_argument("--show-deltas", action="store_true")
    parser.add_argument("--output-json", type=pathlib.Path)
    args = parser.parse_args()

    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    else:
        prompt = args.prompt

    if args.context_tokens > 0:
        context = synthetic_prompt(args.context_tokens)
        prompt = (
            "Read the synthetic context below, then answer the final question.\n\n"
            f"{context}\n\nFinal question: {prompt}"
        )

    payload: dict[str, Any] = {
        "model": args.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "stream": True,
    }
    if args.top_p is not None:
        payload["top_p"] = args.top_p

    url = f"{args.base_url.rstrip('/')}/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
    )

    started = time.perf_counter()
    first_event_at: float | None = None
    first_content_at: float | None = None
    event_count = 0
    content_chunks = 0
    reasoning_chunks = 0
    content_text = ""
    reasoning_text = ""
    finish_reasons: list[str] = []

    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as response:
            for raw_line in response:
                try:
                    event = parse_sse_line(raw_line)
                except json.JSONDecodeError as exc:
                    print(f"failed_to_parse_sse line={raw_line!r} error={exc}", file=sys.stderr)
                    continue

                if event is None:
                    continue

                now = time.perf_counter()
                if first_event_at is None:
                    first_event_at = now
                event_count += 1
                if args.show_raw:
                    print_raw_event(event, args.raw_max_chars)

                choices = event.get("choices") if isinstance(event, dict) else None
                if not isinstance(choices, list):
                    continue

                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    finish_reason = choice.get("finish_reason")
                    if finish_reason:
                        finish_reasons.append(str(finish_reason))

                    content_delta, reasoning_delta = extract_delta_text(choice)
                    if content_delta:
                        if first_content_at is None:
                            first_content_at = now
                        content_chunks += 1
                        content_text += content_delta
                        if args.show_deltas:
                            print(f"content_delta={content_delta!r}")
                    if reasoning_delta:
                        if first_content_at is None:
                            first_content_at = now
                        reasoning_chunks += 1
                        reasoning_text += reasoning_delta
                        if args.show_deltas:
                            print(f"reasoning_delta={reasoning_delta!r}")
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"stream request failed: {exc}", file=sys.stderr)
        return 1

    ended = time.perf_counter()
    elapsed = ended - started
    generation_elapsed = ended - (first_content_at or started)
    visible_tokens_est = estimate_tokens(content_text)
    reasoning_tokens_est = estimate_tokens(reasoning_text)
    output_tokens_est = visible_tokens_est + reasoning_tokens_est
    tokens_per_second = (
        output_tokens_est / generation_elapsed if generation_elapsed > 0 else 0.0
    )

    result = {
        "model": args.model,
        "base_url": args.base_url.rstrip("/"),
        "prompt_chars": len(prompt),
        "prompt_tokens_est": estimate_tokens(prompt),
        "max_tokens": args.max_tokens,
        "elapsed_seconds": elapsed,
        "time_to_first_event_seconds": None
        if first_event_at is None
        else first_event_at - started,
        "time_to_first_content_seconds": None
        if first_content_at is None
        else first_content_at - started,
        "generation_elapsed_seconds": generation_elapsed,
        "event_count": event_count,
        "content_chunks": content_chunks,
        "reasoning_chunks": reasoning_chunks,
        "visible_output_chars": len(content_text),
        "reasoning_output_chars": len(reasoning_text),
        "visible_tokens_est": visible_tokens_est,
        "reasoning_tokens_est": reasoning_tokens_est,
        "output_tokens_est": output_tokens_est,
        "tokens_per_second_est": tokens_per_second,
        "finish_reasons": finish_reasons,
        "saw_reasoning_channel": reasoning_chunks > 0,
        "saw_think_tags_in_content": "<think" in content_text.lower()
        or "</think" in content_text.lower(),
        "content_preview": content_text[:1000],
        "reasoning_preview": reasoning_text[:1000],
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
