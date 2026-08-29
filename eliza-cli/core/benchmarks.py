"""Pure helpers for the `eliza-cli benchmark` subcommand.

Wraps scripts/run-benchmark and reads the benchmark ledger
(benchmarks/results/runs.jsonl) back for tabular display. This module is kept
free of subprocess I/O so the command-building and ledger logic are easy to
unit test.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

# Benchmark types that take a <service> argument (see scripts/run-benchmark).
BENCHMARK_TYPES = ("token-generation", "memory-footprint", "voice-latency")

# Short aliases accepted on the command line.
TYPE_ALIASES = {
    "tok": "token-generation",
    "mem": "memory-footprint",
    "voice": "voice-latency",
}

TYPE_CHOICES = BENCHMARK_TYPES + tuple(TYPE_ALIASES)

# Maps profile categories to service names.
CATEGORY_SERVICES = {"small": "eliza-small", "medium": "eliza-medium"}


def resolve_type(name: str) -> str:
    """Expand a short benchmark type alias (tok/mem/voice) to its full name."""
    return TYPE_ALIASES.get(name, name)


def service_from_profile(profile: str) -> str | None:
    """Infer the service name from a canonical `category/name` profile id."""
    category = profile.split("/", 1)[0] if "/" in profile else ""
    return CATEGORY_SERVICES.get(category)


def extract_profile(extra: tuple[str, ...] | list[str]) -> str | None:
    """Return the --profile value from extra argv, if present."""
    for index, opt in enumerate(extra):
        if opt == "--profile" and index + 1 < len(extra):
            return str(extra[index + 1])
        if opt.startswith("--profile="):
            return opt.split("=", 1)[1]
    return None


LEDGER_NAME = "runs.jsonl"
DEFAULT_RESULTS_DIR = pathlib.Path("benchmarks") / "results"


def build_run_command(
    bench_type: str,
    service: str,
    extra: tuple[str, ...] = (),
) -> list[str]:
    """Build argv for `scripts/run-benchmark <type> <service> [options]`.

    `extra` is forwarded verbatim (e.g. --profile, --max-tokens, --force).
    """
    cmd = ["./scripts/run-benchmark", bench_type, service]
    cmd += list(extra)
    return cmd


def build_all_command(extra: tuple[str, ...] = ()) -> list[str]:
    """Build argv for `scripts/run-benchmark all [options]`."""
    return ["./scripts/run-benchmark", "all", *list(extra)]


def build_compare_command(
    results_dir: str | None = None,
    output: str | None = None,
    service: str | None = None,
    profile: str | None = None,
    all_runs: bool = False,
) -> list[str]:
    """Build argv for `scripts/run-benchmark compare [options]`."""
    cmd = ["./scripts/run-benchmark", "compare"]
    if results_dir:
        cmd += ["--results-dir", results_dir]
    if output:
        cmd += ["--output", output]
    if service:
        cmd += ["--service", service]
    if profile:
        cmd += ["--profile", profile]
    if all_runs:
        cmd += ["--all-runs"]
    return cmd


def ledger_path(results_dir: pathlib.Path | str) -> pathlib.Path:
    """Return the ledger file path for a results directory."""
    return pathlib.Path(results_dir) / LEDGER_NAME


def read_ledger(ledger_file: pathlib.Path | str) -> list[dict[str, Any]]:
    """Parse a JSONL ledger, skipping blank or malformed lines.

    A missing file yields an empty list (no runs recorded yet).
    """
    path = pathlib.Path(ledger_file)
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


def filter_records(
    records: list[dict[str, Any]],
    service: str | None = None,
    profile: str | None = None,
    bench_type: str | None = None,
) -> list[dict[str, Any]]:
    """Filter ledger records by service/profile/type (None = no filter)."""
    result: list[dict[str, Any]] = []
    for record in records:
        if service is not None and record.get("service") != service:
            continue
        if profile is not None and record.get("profile") != profile:
            continue
        if bench_type is not None and record.get("type") != bench_type:
            continue
        result.append(record)
    return result


def key_metric(record: dict[str, Any]) -> str:
    """Return a one-line headline metric for a ledger record."""
    metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
    bench_type = record.get("type", "")

    if bench_type == "token-generation":
        value = metrics.get("tokens_per_second_est")
        return f"{float(value):.2f} tok/s" if value is not None else "n/a"
    if bench_type == "memory-footprint":
        value = metrics.get("load_delta_mb")
        if value is None:
            return "n/a"
        value = float(value)
        return f"+{value:.0f} MB" if value >= 0 else f"{value:.0f} MB"
    if bench_type == "voice-latency":
        value = metrics.get("median_seconds")
        return f"{float(value):.2f}s median" if value is not None else "n/a"
    return "n/a"


def render_runs_table(records: list[dict[str, Any]], limit: int = 20) -> str:
    """Render ledger records as a plain-text table, newest first."""
    if not records:
        return (
            "No benchmark runs recorded yet.\n"
            "Run one with: eliza-cli benchmark run <type> <service>"
        )

    # Timestamps are ISO-8601 UTC, so a plain string sort orders them correctly.
    ordered = sorted(records, key=lambda r: str(r.get("timestamp", "")), reverse=True)
    shown = ordered[: max(limit, 0)]

    lines: list[str] = []
    lines.append(f"[+] Benchmark Runs ({len(shown)} of {len(ordered)})")
    lines.append("-" * 100)
    lines.append(
        f"{'TIMESTAMP':<19} | {'TYPE':<16} | {'SERVICE':<12} | {'PROFILE':<34} | {'METRIC'}"
    )
    lines.append("-" * 100)
    for record in shown:
        timestamp = str(record.get("timestamp", ""))[:19]
        lines.append(
            f"{timestamp:<19} | {str(record.get('type', '')):<16} | "
            f"{str(record.get('service', '')):<12} | {str(record.get('profile', '')):<34} | "
            f"{key_metric(record)}"
        )
    return "\n".join(lines)
