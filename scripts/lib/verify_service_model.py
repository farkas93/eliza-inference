#!/usr/bin/env python3
"""Verify that a running OpenAI-compatible service serves an expected model.

Exit codes:
  0  expected model is served
  1  service is not reachable or not ready
  2  service is reachable but serves a different model
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def fetch_model_ids(base_url: str, timeout: float = 5.0) -> tuple[str, list[str], str]:
    """Probe {base_url}/models.

    Returns (status, model_ids, detail) where status is "ok", "down", or
    "unavailable" (reachable but no model ids reported).
    """
    url = f"{base_url.rstrip('/')}/models"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                return "down", [], f"HTTP {response.status}"
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return "down", [], str(exc)

    try:
        data: Any = json.loads(body)
    except json.JSONDecodeError:
        return "unavailable", [], "invalid JSON from /models"

    ids: list[str] = []
    if isinstance(data, dict):
        entries = data.get("data")
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                    ids.append(entry["id"])
        if not ids and isinstance(data.get("id"), str):
            ids.append(data["id"])
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                ids.append(entry["id"])

    if not ids:
        return "unavailable", [], "no model ids reported"
    return "ok", ids, ""


def match_expected(model_ids: list[str], expected: list[str]) -> str | None:
    """Return the first expected candidate that matches a served model id.

    A candidate matches when it equals a served id or is a path suffix of it
    (llama.cpp serves the full model file path instead of an alias).
    """
    for candidate in expected:
        candidate = candidate.strip()
        if not candidate:
            continue
        for model_id in model_ids:
            if model_id == candidate or model_id.endswith(f"/{candidate}"):
                return candidate
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="OpenAI-compatible base URL, e.g. http://127.0.0.1:8001/v1")
    parser.add_argument(
        "--expected",
        action="append",
        required=True,
        help="Expected model id (repeatable or comma separated); matches exact id or path suffix",
    )
    parser.add_argument("--service", default="service", help="Service name for messages")
    parser.add_argument("--profile", default="", help="Profile name for messages")
    parser.add_argument("--timeout", type=float, default=5.0, help="Seconds to wait for /models")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    expected = [
        value.strip()
        for item in args.expected
        for value in item.split(",")
        if value.strip()
    ]
    status, model_ids, detail = fetch_model_ids(args.base_url, timeout=args.timeout)
    result = {
        "service": args.service,
        "profile": args.profile,
        "base_url": args.base_url.rstrip("/"),
        "expected": expected,
        "live_models": model_ids,
        "detail": detail,
    }

    def start_hint(command: str) -> str:
        if args.profile:
            return f"Run: ./scripts/{command} {args.service} --profile {args.profile}"
        return f"Run: ./scripts/{command} {args.service}"

    if status == "down":
        result["status"] = "down"
        print(
            f"service {args.service} is not ready at {args.base_url} ({detail}). {start_hint('start')}",
            file=sys.stderr,
        )
        print(json.dumps(result, indent=2))
        return 1

    matched = match_expected(model_ids, expected)
    if matched is None:
        result["status"] = "mismatch"
        print(
            f"model mismatch for service {args.service}: expected one of {expected} "
            f"but the service serves {model_ids}. {start_hint('restart')}",
            file=sys.stderr,
        )
        print(json.dumps(result, indent=2))
        return 2

    result["status"] = "match"
    print(f"service {args.service} is serving expected model {matched}")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
