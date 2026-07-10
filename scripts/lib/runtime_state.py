#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def save_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read and write runtime service profile state.")
    parser.add_argument("command", choices=["set", "clear", "get", "all"])
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--service")
    parser.add_argument("--profile")
    args = parser.parse_args()

    state = load_state(args.state)

    if args.command == "set":
        if not args.service or not args.profile:
            parser.error("set requires --service and --profile")
        state[args.service] = args.profile
        save_state(args.state, state)
        return 0

    if args.command == "clear":
        if not args.service:
            parser.error("clear requires --service")
        state.pop(args.service, None)
        save_state(args.state, state)
        return 0

    if args.command == "get":
        if not args.service:
            parser.error("get requires --service")
        value = state.get(args.service)
        if value is None:
            return 1
        print(value)
        return 0

    if args.command == "all":
        for service, profile in sorted(state.items()):
            print(f"{service}\t{profile}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
