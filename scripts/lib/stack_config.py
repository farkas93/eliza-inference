#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path


def load_config(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def enabled_services(config: dict) -> list[dict]:
    return [service for service in config.get("services", []) if service.get("enabled", True)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Read eliza stack config.")
    parser.add_argument("command", choices=["services", "models"])
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()

    config = load_config(args.config)

    if args.command == "services":
        for service in enabled_services(config):
            print(
                "\t".join(
                    [
                        str(service["name"]),
                        str(service["profile"]),
                        str(service.get("health_url", "")),
                    ]
                )
            )
        return 0

    if args.command == "models":
        models = config.get("models", {})
        for name, model in models.items():
            print(
                "\t".join(
                    [
                        str(name),
                        str(model.get("service", "")),
                        str(model.get("profile", "")),
                        str(model.get("actual_model", "")),
                        str(model.get("base_url", "")),
                    ]
                )
            )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
