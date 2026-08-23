#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class RuntimeStateError(RuntimeError):
    pass


def load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise RuntimeStateError(f"Unable to read runtime state {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeStateError(f"Invalid runtime state JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeStateError(f"Runtime state must be a JSON object: {path}")
    return {str(k): str(v) for k, v in data.items()}


def save_state(path: Path, state: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


@contextmanager
def state_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f"{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read and write runtime service profile state.")
    parser.add_argument("command", choices=["set", "clear", "get", "all"])
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--service")
    parser.add_argument("--profile")
    args = parser.parse_args()

    try:
        with state_lock(args.state):
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
    except RuntimeStateError as exc:
        parser.exit(1, f"runtime_state: {exc}\n")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
