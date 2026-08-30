from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "eliza-cli"))

from core.benchmarks import (  # noqa: E402
    BENCHMARK_TYPES,
    TYPE_ALIASES,
    TYPE_CHOICES,
    build_all_command,
    build_compare_command,
    build_run_command,
    extract_profile,
    filter_records,
    key_metric,
    ledger_path,
    read_ledger,
    render_runs_table,
    resolve_type,
    service_from_profile,
)
from core.completion import completion_data, render_bash, render_zsh
from core.publish import PublishError, publish_results


def make_record(
    bench_type: str,
    service: str,
    profile: str,
    timestamp: str,
    metrics: dict | None = None,
) -> dict:
    return {
        "service": service,
        "profile": profile,
        "type": bench_type,
        "timestamp": timestamp,
        "model": "test-model",
        "result_file": f"{service}-{timestamp}.json",
        "metrics": metrics or {},
    }


class BuildCommandTest(unittest.TestCase):
    def test_run_command_with_extra(self):
        cmd = build_run_command(
            "token-generation",
            "eliza-medium",
            extra=("--profile", "medium/qwen3.8", "--max-tokens", "512"),
        )
        self.assertEqual(
            cmd,
            [
                "./scripts/run-benchmark",
                "token-generation",
                "eliza-medium",
                "--profile",
                "medium/qwen3.8",
                "--max-tokens",
                "512",
            ],
        )

    def test_run_command_without_extra(self):
        self.assertEqual(
            build_run_command("voice-latency", "eliza-small"),
            ["./scripts/run-benchmark", "voice-latency", "eliza-small"],
        )

    def test_all_command(self):
        self.assertEqual(build_all_command(), ["./scripts/run-benchmark", "all"])
        self.assertEqual(
            build_all_command(extra=("--force",)),
            ["./scripts/run-benchmark", "all", "--force"],
        )

    def test_compare_command_options(self):
        cmd = build_compare_command(
            results_dir="benchmarks/results",
            output="benchmarks/RESULTS.md",
            service="eliza-medium",
            all_runs=True,
        )
        self.assertEqual(
            cmd,
            [
                "./scripts/run-benchmark",
                "compare",
                "--results-dir",
                "benchmarks/results",
                "--output",
                "benchmarks/RESULTS.md",
                "--service",
                "eliza-medium",
                "--all-runs",
            ],
        )

    def test_compare_command_minimal(self):
        self.assertEqual(build_compare_command(), ["./scripts/run-benchmark", "compare"])

    def test_benchmark_types_are_the_service_types(self):
        self.assertEqual(
            BENCHMARK_TYPES,
            ("token-generation", "memory-footprint", "voice-latency"),
        )


class LedgerReadTest(unittest.TestCase):
    def _write_ledger(self, directory: pathlib.Path, lines: list[str]) -> pathlib.Path:
        ledger = directory / "runs.jsonl"
        ledger.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return ledger

    def test_read_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._write_ledger(
                pathlib.Path(tmp),
                [
                    json.dumps(make_record("token-generation", "eliza-medium", "p", "2026-08-24T12:00:00+00:00")),
                    json.dumps(make_record("voice-latency", "eliza-small", "p", "2026-08-24T13:00:00+00:00")),
                ],
            )
            records = read_ledger(ledger)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["type"], "token-generation")
            self.assertEqual(records[1]["type"], "voice-latency")

    def test_read_skips_malformed_and_blank_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = self._write_ledger(
                pathlib.Path(tmp),
                [
                    "",
                    "not-json",
                    json.dumps(make_record("token-generation", "eliza-medium", "p", "2026-08-24T12:00:00+00:00")),
                    "[1, 2, 3]",
                    "",
                ],
            )
            records = read_ledger(ledger)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["type"], "token-generation")

    def test_read_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = read_ledger(pathlib.Path(tmp) / "does-not-exist.jsonl")
            self.assertEqual(records, [])

    def test_ledger_path_joins_runs_jsonl(self):
        self.assertEqual(
            ledger_path(pathlib.Path("benchmarks/results")),
            pathlib.Path("benchmarks/results/runs.jsonl"),
        )


class FilterRecordsTest(unittest.TestCase):
    def setUp(self):
        self.records = [
            make_record("token-generation", "eliza-medium", "medium/a", "2026-08-24T12:00:00+00:00"),
            make_record("voice-latency", "eliza-small", "small/b", "2026-08-24T13:00:00+00:00"),
            make_record("memory-footprint", "eliza-medium", "medium/a", "2026-08-24T14:00:00+00:00"),
        ]

    def test_no_filters_returns_all(self):
        self.assertEqual(len(filter_records(self.records)), 3)

    def test_filter_by_service(self):
        result = filter_records(self.records, service="eliza-medium")
        self.assertEqual(len(result), 2)
        self.assertTrue(all(r["service"] == "eliza-medium" for r in result))

    def test_filter_by_type(self):
        result = filter_records(self.records, bench_type="voice-latency")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["service"], "eliza-small")

    def test_filter_combined(self):
        result = filter_records(
            self.records, service="eliza-medium", bench_type="memory-footprint"
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["profile"], "medium/a")

    def test_filter_no_match(self):
        self.assertEqual(filter_records(self.records, service="nope"), [])


class KeyMetricTest(unittest.TestCase):
    def test_token_generation(self):
        record = make_record(
            "token-generation", "eliza-medium", "p", "t",
            metrics={"tokens_per_second_est": 12.5},
        )
        self.assertEqual(key_metric(record), "12.50 tok/s")

    def test_memory_footprint_positive(self):
        record = make_record(
            "memory-footprint", "eliza-medium", "p", "t",
            metrics={"load_delta_mb": 412.0},
        )
        self.assertEqual(key_metric(record), "+412 MB")

    def test_memory_footprint_negative(self):
        record = make_record(
            "memory-footprint", "eliza-medium", "p", "t",
            metrics={"load_delta_mb": -50.0},
        )
        self.assertEqual(key_metric(record), "-50 MB")

    def test_voice_latency(self):
        record = make_record(
            "voice-latency", "eliza-small", "p", "t",
            metrics={"median_seconds": 3.216},
        )
        self.assertEqual(key_metric(record), "3.22s median")

    def test_missing_metric_is_na(self):
        record = make_record("token-generation", "eliza-medium", "p", "t")
        self.assertEqual(key_metric(record), "n/a")

    def test_unknown_type_is_na(self):
        record = make_record("mystery", "eliza-medium", "p", "t")
        self.assertEqual(key_metric(record), "n/a")


class RenderRunsTableTest(unittest.TestCase):
    def test_empty_records(self):
        out = render_runs_table([])
        self.assertIn("No benchmark runs recorded yet", out)
        self.assertIn("eliza-cli benchmark run", out)

    def test_renders_rows_newest_first(self):
        records = [
            make_record("token-generation", "eliza-medium", "medium/a", "2026-08-24T12:00:00+00:00",
                        {"tokens_per_second_est": 10.0}),
            make_record("voice-latency", "eliza-small", "small/b", "2026-08-24T15:00:00+00:00",
                        {"median_seconds": 2.5}),
            make_record("memory-footprint", "eliza-medium", "medium/a", "2026-08-24T13:30:00+00:00",
                        {"load_delta_mb": 100.0}),
        ]
        out = render_runs_table(records, limit=20)
        lines = out.splitlines()
        # Newest (15:00) should appear before older rows.
        idx_voice = next(i for i, l in enumerate(lines) if "voice-latency" in l)
        idx_mem = next(i for i, l in enumerate(lines) if "memory-footprint" in l)
        idx_tok = next(i for i, l in enumerate(lines) if "token-generation" in l)
        self.assertLess(idx_voice, idx_mem)
        self.assertLess(idx_mem, idx_tok)
        self.assertIn("3 of 3", out)
        self.assertIn("2.50s median", out)

    def test_respects_limit(self):
        records = [
            make_record("token-generation", "eliza-medium", f"p{i}", f"2026-08-24T12:0{i}:00+00:00",
                        {"tokens_per_second_est": float(i)})
            for i in range(5)
        ]
        out = render_runs_table(records, limit=2)
        self.assertIn("2 of 5", out)
        # Only the two newest (i=4, i=3) are shown.
        self.assertIn("p4", out)
        self.assertIn("p3", out)
        self.assertNotIn("p0", out)

    def test_limit_zero_shows_none(self):
        records = [make_record("token-generation", "eliza-medium", "p", "2026-08-24T12:00:00+00:00")]
        out = render_runs_table(records, limit=0)
        self.assertIn("0 of 1", out)


class LiveProfileBenchmarkTest(unittest.TestCase):
    def test_common_sh_resolves_live_profile_when_unspecified(self):
        common_sh = (ROOT_DIR / "scripts" / "lib" / "common.sh").read_text(encoding="utf-8")
        self.assertIn('live_profile="$(runtime_state get --state "$RUNTIME_STATE_FILE" --service "$SERVICE"', common_sh)
        self.assertIn('PROFILE="$live_profile"', common_sh)


class CliEnhancementsTest(unittest.TestCase):
    def test_type_resolution(self):
        self.assertEqual(resolve_type("tok"), "token-generation")
        self.assertEqual(resolve_type("mem"), "memory-footprint")
        self.assertEqual(resolve_type("voice"), "voice-latency")
        self.assertEqual(resolve_type("token-generation"), "token-generation")
        self.assertEqual(set(TYPE_CHOICES), set(BENCHMARK_TYPES) | set(TYPE_ALIASES))

    def test_service_from_profile(self):
        self.assertEqual(service_from_profile("medium/qwen3.8-flash-next"), "eliza-medium")
        self.assertEqual(service_from_profile("small/gemma4-e4b"), "eliza-small")
        self.assertIsNone(service_from_profile("bare-name"))
        self.assertIsNone(service_from_profile("unknown/foo"))

    def test_extract_profile(self):
        self.assertEqual(
            extract_profile(("--force", "--profile", "medium/a", "--max-tokens", "10")),
            "medium/a",
        )
        self.assertEqual(
            extract_profile(("--profile=small/b", "--force")),
            "small/b",
        )
        self.assertIsNone(extract_profile(("--force", "--other")))

    def test_completion_data_emits_candidates(self):
        commands = completion_data(ROOT_DIR, "commands")
        self.assertIn("bench", commands)
        self.assertIn("publish", completion_data(ROOT_DIR, "bench-subcommands"))
        self.assertIn("tok", completion_data(ROOT_DIR, "types"))
        services = completion_data(ROOT_DIR, "services")
        self.assertIn("eliza-medium", services)
        profiles = completion_data(ROOT_DIR, "profiles")
        self.assertTrue(any(p.startswith("medium/") for p in profiles))

    def test_completion_scripts_render_non_empty(self):
        bash = render_bash()
        self.assertIn("complete -F _eliza_cli_complete eliza-cli", bash)
        zsh = render_zsh()
        self.assertIn("#compdef eliza-cli", zsh)

    def _init_git_repo(self, root: pathlib.Path, branch: str = "feature/test") -> None:
        import subprocess
        subprocess.run(["git", "init", "-b", branch], cwd=root, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=root, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, capture_output=True, check=True)
        dummy = root / "README.md"
        dummy.write_text("# Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=root, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, capture_output=True, check=True)

    def test_publish_rejects_non_main_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = pathlib.Path(tmp)
            self._init_git_repo(tmp_root, branch="feature/my-branch")
            with self.assertRaises(PublishError) as ctx:
                publish_results(tmp_root, target_branch="main", force=False)
            self.assertIn("publish commits directly to 'main'", str(ctx.exception))
            self.assertIn("current branch is 'feature/my-branch'", str(ctx.exception))

    def test_publish_dry_run_reports_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = pathlib.Path(tmp)
            self._init_git_repo(tmp_root, branch="main")
            working_dir = tmp_root / "benchmarks"
            working_dir.mkdir(parents=True)
            (working_dir / "RESULTS.md").write_text("# Results\n", encoding="utf-8")
            status = publish_results(
                tmp_root,
                target_branch="main",
                force=False,
                dry_run=True,
            )
            self.assertIn("[dry-run] Would create BENCHMARKS.md", status)
            self.assertFalse((tmp_root / "BENCHMARKS.md").exists())

    def test_tui_app_guard_checks_live_profile(self):
        app_source = (ROOT_DIR / "eliza-cli" / "tui" / "app.py").read_text(encoding="utf-8")
        self.assertIn("active_profile_id = current_service.live_profile_id or current_service.profile_id", app_source)
        self.assertIn("selected_profile.name == active_profile_id", app_source)


if __name__ == "__main__":
    unittest.main()
