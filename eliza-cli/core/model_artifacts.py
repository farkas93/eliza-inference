"""Local artifact checks shared by the TUI and native model launcher."""
from __future__ import annotations

import argparse
import pathlib
import re
from collections.abc import Iterable

_SHARD_FILE_RE = re.compile(r"^(.+)-(\d{5})-of-(\d{5})\.gguf$")


def gguf_shards(path: pathlib.Path) -> tuple[pathlib.Path, ...]:
    match = _SHARD_FILE_RE.fullmatch(path.name)
    if match is None:
        return (path,)
    prefix, index, count = match.groups()
    total = int(count)
    if not 1 <= int(index) <= total:
        return (path,)
    return tuple(path.with_name(f"{prefix}-{part:05d}-of-{count}.gguf") for part in range(1, total + 1))


def required_paths(paths: Iterable[pathlib.Path]) -> tuple[pathlib.Path, ...]:
    return tuple(dict.fromkeys(shard for path in paths for shard in gguf_shards(path)))


def missing_paths(paths: Iterable[pathlib.Path]) -> tuple[pathlib.Path, ...]:
    missing = []
    for path in required_paths(paths):
        try:
            if not path.exists() or (path.is_file() and path.stat().st_size == 0):
                missing.append(path)
        except OSError:
            missing.append(path)
    return tuple(missing)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local model files, including every GGUF shard.")
    parser.add_argument("paths", nargs="+", type=pathlib.Path)
    args = parser.parse_args()
    missing = missing_paths(args.paths)
    if missing:
        for path in missing:
            print(f"Missing or empty model artifact: {path}")
        return 78  # configuration error: restart attempts cannot repair a download
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
