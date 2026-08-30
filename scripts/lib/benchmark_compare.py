#!/usr/bin/env python3
"""Aggregate benchmark runs into a curated markdown comparison.

Reads the append-only runs.jsonl ledger and scans per-run result JSON
files (deduplicating by result file), keeps the latest run per
(profile, type) by default, and renders one flat markdown table per
benchmark type across all services. Profile names are normalized to
canonical `category/name` ids (legacy `eliza-medium-*` style references
and aliases.sh shorthands collapse into their canonical profile).

Usage:
  benchmark_compare.py [--results-dir DIR] [--output PATH]
                       [--service NAME] [--profile NAME] [--all-runs]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import datetime, timezone
from typing import Any

import benchmark_ledger
import profile_references

ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]

TYPE_ORDER = ("token-generation", "memory-footprint", "voice-latency")
TYPE_LABELS = {
    "token-generation": "Token generation",
    "memory-footprint": "Memory footprint",
    "voice-latency": "Voice latency",
}
CATEGORY_DIRS = ("small", "medium", "stt", "tts", "vocode", "voice")

COLUMNS: dict[str, list[tuple[str, str, str]]] = {
    "token-generation": [
        ("tok/s (est)", "tokens_per_second_est", "{:.1f}"),
        ("TTFT (s)", "time_to_first_content_seconds", "{:.2f}"),
        ("Elapsed (s)", "elapsed_seconds", "{:.2f}"),
        ("Output tokens (est)", "output_tokens_est", "{:.0f}"),
        ("Reasoning channel", "saw_reasoning_channel", "bool"),
    ],
    "memory-footprint": [
        ("Source", "memory_source", "str"),
        ("Baseline (MiB)", "baseline_used_mb", "{:.0f}"),
        ("Post-load (MiB)", "post_load_used_mb", "{:.0f}"),
        ("Δ load (MiB)", "load_delta_mb", "{:+.0f}"),
        ("Max ctx used (MiB)", "max_context_used_mb", "{:.0f}"),
        ("Max ctx (tokens)", "max_context_tokens", "{:.0f}"),
    ],
    "voice-latency": [
        ("Median (s)", "median_seconds", "{:.3f}"),
        ("Avg (s)", "average_seconds", "{:.3f}"),
        ("Rounds", "round_count", "{:.0f}"),
    ],
}

# Matches current `<category>-<name>-<kind>-<ts>.json` files as well as
# legacy `<service>-<service>-<name>-<kind>-<ts>.json` and
# `<service>-<category>-<name>-<contexttokens>-<ts>.json` (no kind token,
# old stream runs where the context size took the kind slot).
FILE_NAME_PATTERN = re.compile(
    r"^(?:(?P<service>eliza-[a-z]+)-)?"
    r"(?P<middle>.+)-"
    r"(?P<kind>stream|memory-footprint|voice-latency|\d{2,})-"
    r"(?P<ts>\d{8}[-T]?\d{6})\.json$"
)
KIND_TO_TYPE = {
    "stream": "token-generation",
    "memory-footprint": "memory-footprint",
    "voice-latency": "voice-latency",
}


def _alias_map() -> dict[str, str]:
    try:
        return profile_references.aliases()
    except OSError:
        return {}


def canonical_profile_name(raw: str) -> str:
    """Collapse legacy prefixes and aliases.sh shorthands to a canonical id."""
    if not raw or raw == "default":
        return raw
    name = raw[:-4] if raw.endswith(".env") else raw
    name = profile_references.normalize_reference(name)
    first_segment = name.split("-", 1)[0]
    if "/" not in name and first_segment in CATEGORY_DIRS:
        name = name.replace("-", "/", 1)
    name = _alias_map().get(name, name)
    if "/" not in name:
        first_segment = name.split("-", 1)[0]
        if first_segment in CATEGORY_DIRS:
            name = name.replace("-", "/", 1)
    return name


def service_for_profile(profile: str, fallback: str = "") -> str:
    category = profile.split("/", 1)[0] if "/" in profile else ""
    if category in ("small", "medium"):
        return f"eliza-{category}"
    return fallback or profile


def normalize_timestamp(value: Any) -> str:
    """Reduce a timestamp to sortable digits (YYYYMMDDHHMMSS when possible)."""
    digits = re.findall(r"\d+", str(value))
    return "".join(digits[:6])


def load_ledger(ledger_path: pathlib.Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if not ledger_path.exists():
        return runs
    with ledger_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print(f"warning: skipping malformed ledger line {line_number}", file=sys.stderr)
                continue
            if isinstance(record, dict) and record.get("type") in TYPE_ORDER:
                record.setdefault("result_file", "")
                record.setdefault("metrics", {})
                runs.append(record)
    return runs


def _profile_from_filename(service: str, middle: str, kind: str) -> str:
    profile = canonical_profile_name(middle)
    if "/" not in profile and kind == "voice-latency":
        category = service.removeprefix("eliza-") or "voice"
        profile = f"{category}/{profile}"
    return profile


def scan_result_files(results_dir: pathlib.Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if not results_dir.is_dir():
        return runs
    for path in sorted(results_dir.glob("*.json")):
        match = FILE_NAME_PATTERN.match(path.name)
        if not match:
            continue
        kind = match.group("kind")
        benchmark_type = KIND_TO_TYPE.get(kind, "token-generation")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        service = str(data.get("service") or "") or match.group("service") or ""
        profile = canonical_profile_name(str(data.get("profile") or "")) or _profile_from_filename(
            service or "", match.group("middle"), kind
        )
        service = service or service_for_profile(profile)
        runs.append(
            {
                "service": service,
                "profile": profile,
                "type": benchmark_type,
                "timestamp": match.group("ts"),
                "model": str(data.get("model", "")),
                "result_file": path.name,
                "metrics": benchmark_ledger.extract_metrics(benchmark_type, data),
            }
        )
    return runs


def collect_runs(results_dir: pathlib.Path) -> tuple[list[dict[str, Any]], str]:
    ledger_runs = load_ledger(results_dir / "runs.jsonl")
    file_runs = scan_result_files(results_dir)
    seen_files = {str(run.get("result_file", "")) for run in ledger_runs if run.get("result_file")}
    extra_runs = [run for run in file_runs if run["result_file"] not in seen_files]
    runs = ledger_runs + extra_runs
    for run in runs:
        run["profile"] = canonical_profile_name(str(run.get("profile", "")))
        run["service"] = str(run.get("service") or "") or service_for_profile(run["profile"])
    return runs, f"ledger and result files in `{results_dir}` ({len(runs)} runs)"


def select_runs(runs: list[dict[str, Any]], all_runs: bool) -> list[dict[str, Any]]:
    sort_key = lambda run: (run["profile"], run["service"], run["type"], normalize_timestamp(run.get("timestamp")))
    if all_runs:
        return sorted(runs, key=sort_key)
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for run in runs:
        key = (run["profile"], run["service"], run["type"])
        current = latest.get(key)
        if current is None or normalize_timestamp(run.get("timestamp")) >= normalize_timestamp(current.get("timestamp")):
            latest[key] = run
    return sorted(latest.values(), key=sort_key)


def _format_cell(value: Any, spec: str) -> str:
    if value is None:
        return "-"
    if spec == "bool":
        return "yes" if value else "no"
    if spec == "str":
        return str(value) if str(value) else "-"
    try:
        return spec.format(value)
    except (ValueError, TypeError):
        return "-"


def _format_run_time(value: Any) -> str:
    normalized = normalize_timestamp(value)
    if len(normalized) == 14:
        return f"{normalized[0:4]}-{normalized[4:6]}-{normalized[6:8]} {normalized[8:10]}:{normalized[10:12]}:{normalized[12:14]}"
    return str(value) if value else "-"


def _type_table(benchmark_type: str, runs: list[dict[str, Any]], all_runs: bool) -> list[str]:
    columns = COLUMNS[benchmark_type]
    headers = ["Model", "Service"]
    if all_runs:
        headers.append("Run (UTC)")
    headers.extend(label for label, _, _ in columns)

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for run in runs:
        cells = [f"`{run['profile']}`", run["service"]]
        if all_runs:
            cells.append(_format_run_time(run.get("timestamp")))
        metrics = run.get("metrics", {})
        cells.extend(_format_cell(metrics.get(key), spec) for _, key, spec in columns)
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def render_markdown(
    runs: list[dict[str, Any]],
    all_runs: bool,
    source_description: str,
    results_dir: pathlib.Path,
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Benchmark Results",
        "",
        f"_Generated {generated_at} from {source_description}._",
        "",
    ]

    for benchmark_type in TYPE_ORDER:
        type_runs = [run for run in runs if run["type"] == benchmark_type]
        if not type_runs:
            continue
        lines.append(f"## {TYPE_LABELS[benchmark_type]}")
        lines.append("")
        lines.extend(_type_table(benchmark_type, type_runs, all_runs))
        lines.append("")

    lines.extend(["## Sources", ""])
    for run in runs:
        source = f"- `{run['profile']}` ({run['service']}) — {run['type']}: {_format_run_time(run.get('timestamp'))}"
        if run.get("result_file"):
            source += f" (`{run['result_file']}`)"
        lines.append(source)

    lines.extend(
        [
            "",
            "---",
            "_Regenerate: `eliza-cli bench compare`_",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=pathlib.Path,
        default=ROOT_DIR / "benchmarks" / "results",
        help="Directory containing runs.jsonl and result JSON files",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=None,
        help="Output markdown path (default: <results-dir>/../RESULTS.md)",
    )
    parser.add_argument("--service", default="", help="Only include this service")
    parser.add_argument("--profile", default="", help="Only include this profile")
    parser.add_argument("--all-runs", action="store_true", help="Show every run instead of the latest per profile")
    args = parser.parse_args(argv)

    output = args.output or args.results_dir.parent / "RESULTS.md"

    runs, source_description = collect_runs(args.results_dir)
    if args.service:
        runs = [run for run in runs if run["service"] == args.service]
    if args.profile:
        wanted_profile = canonical_profile_name(args.profile)
        runs = [run for run in runs if run["profile"] == wanted_profile]

    if not runs:
        print(
            f"No benchmark runs found in {args.results_dir}. "
            "Run benchmarks first (e.g. ./scripts/run-benchmark all).",
            file=sys.stderr,
        )
        return 2

    selected = select_runs(runs, args.all_runs)
    markdown = render_markdown(selected, args.all_runs, source_description, args.results_dir)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(f"Wrote comparison for {len(selected)} runs to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
