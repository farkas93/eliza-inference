#!/usr/bin/env python3
"""Build a memory-footprint benchmark report from snapshot CSVs and request JSONs.

Usage:
  benchmark_report.py OUTPUT_JSON SERVICE PROFILE MODEL MEMORY_SOURCE \
    BASELINE_CSV POST_LOAD_CSV WARMUP_JSON [TOKENS:REQUEST_JSON:SNAPSHOT_CSV] ...

MEMORY_SOURCE is "nvidia-smi" or "system-unified" (GB10 unified memory).
"""
from __future__ import annotations

import csv
import json
import pathlib
import statistics
import sys
from typing import Any


def _to_float(value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        return None


def summarize_csv(path: pathlib.Path) -> dict[str, Any]:
    """Summarize an nvidia-smi/system snapshot CSV.

    Rows are expected to have at least five columns:
    timestamp,name,memory_used_mb,memory_total_mb,utilization_gpu_pct
    Non-numeric memory/utilization cells (for example "N/A") are skipped.
    """
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if len(row) < 5:
                continue
            used = _to_float(row[2])
            total = _to_float(row[3])
            util = _to_float(row[4])
            if used is None or total is None or util is None:
                continue
            rows.append(
                {
                    "timestamp": row[0].strip(),
                    "name": row[1].strip(),
                    "memory_used_mb": used,
                    "memory_total_mb": total,
                    "utilization_gpu_pct": util,
                }
            )

    used = [row["memory_used_mb"] for row in rows]
    util = [row["utilization_gpu_pct"] for row in rows]
    return {
        "samples": rows,
        "sample_count": len(rows),
        "memory_total_mb": rows[0]["memory_total_mb"] if rows else 0.0,
        "memory_used_mb_mean": statistics.fmean(used) if used else 0.0,
        "memory_used_mb_min": min(used) if used else 0.0,
        "memory_used_mb_max": max(used) if used else 0.0,
        "utilization_gpu_pct_mean": statistics.fmean(util) if util else 0.0,
        "utilization_gpu_pct_max": max(util) if util else 0.0,
    }


def build_report(
    service: str,
    profile: str,
    model: str,
    memory_source: str,
    baseline: dict[str, Any],
    post_load: dict[str, Any],
    warmup: dict[str, Any],
    contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "service": service,
        "profile": profile,
        "model": model,
        "memory_source": memory_source,
        "baseline": baseline,
        "post_load": post_load,
        "warmup": warmup,
        "contexts": contexts,
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 8:
        print(f"usage: {sys.argv[0]} OUTPUT_JSON SERVICE PROFILE MODEL MEMORY_SOURCE "
              "BASELINE_CSV POST_LOAD_CSV WARMUP_JSON [TOKENS:REQUEST_JSON:SNAPSHOT_CSV] ...",
              file=sys.stderr)
        return 2

    output = pathlib.Path(args[0])
    service, profile, model, memory_source = args[1:5]
    baseline_csv, post_load_csv, warmup_json = (pathlib.Path(p) for p in args[5:8])
    context_specs = args[8:]

    contexts: list[dict[str, Any]] = []
    for spec in context_specs:
        tokens, request_path, snapshot_path = spec.split(":", 2)
        contexts.append(
            {
                "requested_tokens": int(tokens),
                "request": json.loads(pathlib.Path(request_path).read_text(encoding="utf-8")),
                "memory_snapshot": summarize_csv(pathlib.Path(snapshot_path)),
            }
        )

    report = build_report(
        service=service,
        profile=profile,
        model=model,
        memory_source=memory_source,
        baseline=summarize_csv(baseline_csv),
        post_load=summarize_csv(post_load_csv),
        warmup=json.loads(warmup_json.read_text(encoding="utf-8")),
        contexts=contexts,
    )

    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
