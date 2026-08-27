#!/usr/bin/env python3
"""Append-only JSONL ledger of benchmark runs.

Each benchmark run appends one normalized record so downstream tooling
(compare/report) can read a single file instead of globbing result JSONs.

Usage:
  benchmark_ledger.py add --ledger PATH --type TYPE --service S --profile P --result-json PATH
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any


BENCHMARK_TYPES = ("token-generation", "memory-footprint", "voice-latency")


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def extract_metrics(benchmark_type: str, result: dict[str, Any]) -> dict[str, Any]:
    """Normalize a result JSON into flat metrics for the ledger."""
    if benchmark_type == "token-generation":
        return {
            "tokens_per_second_est": _num(result.get("tokens_per_second_est")),
            "time_to_first_content_seconds": _num(result.get("time_to_first_content_seconds")),
            "elapsed_seconds": _num(result.get("elapsed_seconds")),
            "output_tokens_est": _num(result.get("output_tokens_est")),
            "saw_reasoning_channel": bool(result.get("saw_reasoning_channel", False)),
        }

    if benchmark_type == "memory-footprint":
        baseline = result.get("baseline") if isinstance(result.get("baseline"), dict) else {}
        post_load = result.get("post_load") if isinstance(result.get("post_load"), dict) else {}
        contexts = result.get("contexts") if isinstance(result.get("contexts"), list) else []
        base_used = _num(baseline.get("memory_used_mb_mean"))
        post_used = _num(post_load.get("memory_used_mb_mean"))
        delta = (
            round(post_used - base_used, 2)
            if base_used is not None and post_used is not None
            else None
        )
        max_context_used = max(
            (
                _num(
                    (entry.get("memory_snapshot") if isinstance(entry.get("memory_snapshot"), dict) else {}).get(
                        "memory_used_mb_max"
                    )
                )
                or 0.0
                for entry in contexts
                if isinstance(entry, dict)
            ),
            default=0.0,
        )
        max_context_tokens = max(
            (_num(entry.get("requested_tokens")) or 0.0 for entry in contexts if isinstance(entry, dict)),
            default=0.0,
        )
        return {
            "memory_source": result.get("memory_source", "unknown"),
            "baseline_used_mb": base_used,
            "post_load_used_mb": post_used,
            "load_delta_mb": delta,
            "max_context_used_mb": max_context_used,
            "max_context_tokens": max_context_tokens,
        }

    if benchmark_type == "voice-latency":
        return {
            "median_seconds": _num(result.get("median_seconds")),
            "average_seconds": _num(result.get("average_seconds")),
            "round_count": _num(result.get("round_count")),
        }

    raise ValueError(f"unknown benchmark type: {benchmark_type}")


def build_record(
    benchmark_type: str,
    service: str,
    profile: str,
    result: dict[str, Any],
    result_file: str = "",
    timestamp: str | None = None,
) -> dict[str, Any]:
    return {
        "service": service or str(result.get("service", "")),
        "profile": profile or str(result.get("profile", "")),
        "type": benchmark_type,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": str(result.get("model", "")),
        "result_file": pathlib.Path(result_file).name if result_file else "",
        "metrics": extract_metrics(benchmark_type, result),
    }


def append_run(ledger_path: pathlib.Path, record: dict[str, Any]) -> dict[str, Any]:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Append one normalized run record")
    add_parser.add_argument("--ledger", required=True, type=pathlib.Path)
    add_parser.add_argument("--type", required=True, dest="benchmark_type", choices=BENCHMARK_TYPES)
    add_parser.add_argument("--service", default="")
    add_parser.add_argument("--profile", default="")
    add_parser.add_argument("--result-json", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)

    if args.command == "add":
        result = json.loads(args.result_json.read_text(encoding="utf-8"))
        record = build_record(
            args.benchmark_type,
            args.service,
            args.profile,
            result,
            result_file=str(args.result_json),
        )
        append_run(args.ledger, record)
        print(f"ledger: appended {record['type']} run for {record['service']}/{record['profile']}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
