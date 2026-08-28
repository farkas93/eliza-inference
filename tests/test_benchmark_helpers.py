from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT_DIR / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


verify_service_model = load_module("verify_service_model", "scripts/lib/verify_service_model.py")
benchmark_report = load_module("benchmark_report", "scripts/lib/benchmark_report.py")
benchmark_ledger = load_module("benchmark_ledger", "scripts/lib/benchmark_ledger.py")
sys.modules["benchmark_ledger"] = benchmark_ledger
benchmark_compare = load_module("benchmark_compare", "scripts/lib/benchmark_compare.py")
voice_test = load_module("voice_test_client", "clients/openai/voice_test.py")
stream_inspect = load_module("stream_inspect_client", "clients/openai/stream_inspect.py")


class MatchExpectedTest(unittest.TestCase):
    def test_exact_id_match(self) -> None:
        self.assertEqual(
            verify_service_model.match_expected(["eliza-medium"], ["eliza-medium"]),
            "eliza-medium",
        )

    def test_path_suffix_match_for_llamacpp_model_file(self) -> None:
        served = ["/home/user/models/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-Q4_K_XL.gguf"]
        self.assertEqual(
            verify_service_model.match_expected(
                served, ["qwen3.8-27b-ud-q4-k-xl", "Qwen3.8-27B-UD-Q4_K_XL.gguf"]
            ),
            "Qwen3.8-27B-UD-Q4_K_XL.gguf",
        )

    def test_no_match_returns_none(self) -> None:
        self.assertIsNone(
            verify_service_model.match_expected(["other-model"], ["eliza-medium"])
        )

    def test_blank_candidates_are_skipped(self) -> None:
        self.assertIsNone(verify_service_model.match_expected(["a"], ["", "  "]))


class FetchModelIdsTest(unittest.TestCase):
    def response_mock(self, status: int, body: bytes):
        response = unittest.mock.MagicMock()
        response.status = status
        response.read.return_value = body
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    def test_unreachable_service_is_down(self) -> None:
        with patch.object(
            verify_service_model.urllib.request,
            "urlopen",
            side_effect=OSError("connection refused"),
        ):
            status, ids, detail = verify_service_model.fetch_model_ids("http://127.0.0.1:9/v1")
        self.assertEqual(status, "down")
        self.assertEqual(ids, [])
        self.assertIn("connection refused", detail)

    def test_http_error_is_down_with_status(self) -> None:
        with patch.object(
            verify_service_model.urllib.request,
            "urlopen",
            return_value=self.response_mock(503, b"{}"),
        ):
            status, ids, detail = verify_service_model.fetch_model_ids("http://127.0.0.1:9/v1")
        self.assertEqual(status, "down")
        self.assertEqual(detail, "HTTP 503")

    def test_standard_models_payload(self) -> None:
        body = json.dumps({"data": [{"id": "eliza-medium"}]}).encode("utf-8")
        with patch.object(
            verify_service_model.urllib.request,
            "urlopen",
            return_value=self.response_mock(200, body),
        ):
            status, ids, detail = verify_service_model.fetch_model_ids("http://127.0.0.1:9/v1")
        self.assertEqual(status, "ok")
        self.assertEqual(ids, ["eliza-medium"])
        self.assertEqual(detail, "")

    def test_empty_model_list_is_unavailable(self) -> None:
        with patch.object(
            verify_service_model.urllib.request,
            "urlopen",
            return_value=self.response_mock(200, b'{"data":[]}'),
        ):
            status, ids, _ = verify_service_model.fetch_model_ids("http://127.0.0.1:9/v1")
        self.assertEqual(status, "unavailable")
        self.assertEqual(ids, [])


class GuardMainTest(unittest.TestCase):
    def run_main(
        self,
        fetch_result: tuple[str, list[str], str],
        *argv: str,
    ) -> tuple[int, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(
            verify_service_model,
            "fetch_model_ids",
            return_value=fetch_result,
        ):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = verify_service_model.main(list(argv))
        return code, stderr.getvalue()

    def test_down_exits_1_with_start_hint(self) -> None:
        code, err = self.run_main(
            ("down", [], "connection refused"),
            "--base-url", "http://127.0.0.1:8001/v1",
            "--expected", "eliza-medium",
            "--service", "eliza-medium",
            "--profile", "medium/qwen3.8-27b-fp8-sglang-256k",
        )
        self.assertEqual(code, 1)
        self.assertIn("not ready", err)
        self.assertIn("./scripts/start eliza-medium --profile medium/qwen3.8-27b-fp8-sglang-256k", err)

    def test_mismatch_exits_2_with_restart_hint(self) -> None:
        code, err = self.run_main(
            ("ok", ["gemma-small"], ""),
            "--base-url", "http://127.0.0.1:8002/v1",
            "--expected", "eliza-small",
            "--service", "eliza-small",
            "--profile", "small/gemma4-e4b-q4-llamacpp-128k",
        )
        self.assertEqual(code, 2)
        self.assertIn("model mismatch", err)
        self.assertIn("./scripts/restart eliza-small --profile small/gemma4-e4b-q4-llamacpp-128k", err)

    def test_match_exits_0(self) -> None:
        code, err = self.run_main(
            ("ok", ["eliza-medium"], ""),
            "--base-url", "http://127.0.0.1:8001/v1",
            "--expected", "eliza-medium",
            "--service", "eliza-medium",
        )
        self.assertEqual(code, 0)
        self.assertEqual(err, "")

    def test_comma_separated_expected_values(self) -> None:
        code, _ = self.run_main(
            ("ok", ["/models/Qwen.gguf"], ""),
            "--base-url", "http://127.0.0.1:8001/v1",
            "--expected", "name-alias,Qwen.gguf",
            "--service", "eliza-medium",
        )
        self.assertEqual(code, 0)


class SummarizeCsvTest(unittest.TestCase):
    def write_csv(self, temporary_dir: str, name: str, lines: list[str]) -> pathlib.Path:
        path = pathlib.Path(temporary_dir) / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_summarizes_numeric_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            csv_path = self.write_csv(
                temporary_dir,
                "snap.csv",
                [
                    "Thu Aug 21 10:00:00 2026,NVIDIA GB10,1000.0,120000.0,10",
                    "Thu Aug 21 10:00:01 2026,NVIDIA GB10,1200.0,120000.0,30",
                ],
            )
            summary = benchmark_report.summarize_csv(csv_path)
        self.assertEqual(summary["sample_count"], 2)
        self.assertEqual(summary["memory_total_mb"], 120000.0)
        self.assertEqual(summary["memory_used_mb_mean"], 1100.0)
        self.assertEqual(summary["memory_used_mb_min"], 1000.0)
        self.assertEqual(summary["memory_used_mb_max"], 1200.0)
        self.assertEqual(summary["utilization_gpu_pct_max"], 30.0)

    def test_skips_na_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            csv_path = self.write_csv(
                temporary_dir,
                "snap.csv",
                [
                    "Thu Aug 21 10:00:00 2026,NVIDIA GB10,N/A,N/A,0",
                    "Thu Aug 21 10:00:01 2026,NVIDIA GB10,1500.5,120000.0,20",
                    "short,row",
                ],
            )
            summary = benchmark_report.summarize_csv(csv_path)
        self.assertEqual(summary["sample_count"], 1)
        self.assertEqual(summary["memory_used_mb_mean"], 1500.5)

    def test_all_invalid_rows_yield_zeros(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            csv_path = self.write_csv(
                temporary_dir, "snap.csv", ["Thu Aug 21 10:00:00 2026,NVIDIA GB10,N/A,N/A,0"]
            )
            summary = benchmark_report.summarize_csv(csv_path)
        self.assertEqual(summary["sample_count"], 0)
        self.assertEqual(summary["memory_used_mb_mean"], 0.0)


class ReportMainTest(unittest.TestCase):
    def test_main_writes_report_with_memory_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = pathlib.Path(temporary_dir)
            output = root / "report.json"
            baseline = root / "baseline.csv"
            post_load = root / "post-load.csv"
            warmup = root / "warmup.json"
            context_request = root / "context-8192.json"
            context_snapshot = root / "context-8192.csv"

            baseline.write_text("ts,GPU,100.0,120000.0,5\n", encoding="utf-8")
            post_load.write_text("ts,GPU,900.0,120000.0,40\n", encoding="utf-8")
            warmup.write_text(json.dumps({"elapsed_seconds": 1.5}), encoding="utf-8")
            context_request.write_text(json.dumps({"requested_tokens_approx": 8192}), encoding="utf-8")
            context_snapshot.write_text("ts,GPU,950.0,120000.0,45\n", encoding="utf-8")

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = benchmark_report.main(
                    [
                        str(output),
                        "eliza-medium",
                        "medium/test-profile",
                        "eliza-medium",
                        "system-unified",
                        str(baseline),
                        str(post_load),
                        str(warmup),
                        f"8192:{context_request}:{context_snapshot}",
                    ]
                )
            self.assertEqual(code, 0)

            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["service"], "eliza-medium")
        self.assertEqual(report["memory_source"], "system-unified")
        self.assertEqual(report["baseline"]["memory_used_mb_mean"], 100.0)
        self.assertEqual(report["post_load"]["memory_used_mb_mean"], 900.0)
        self.assertEqual(report["warmup"]["elapsed_seconds"], 1.5)
        self.assertEqual(report["contexts"][0]["requested_tokens"], 8192)
        self.assertEqual(report["contexts"][0]["memory_snapshot"]["memory_used_mb_mean"], 950.0)

    def test_main_requires_minimum_args(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = benchmark_report.main(["only-one-arg"])
        self.assertEqual(code, 2)
        self.assertIn("usage:", stderr.getvalue())


class VoiceSummarizeTest(unittest.TestCase):
    def test_summarize_latencies(self) -> None:
        summary = voice_test.summarize_latencies([1.0, 2.0, 3.0])
        self.assertEqual(summary["round_count"], 3)
        self.assertEqual(summary["average_seconds"], 2.0)
        self.assertEqual(summary["median_seconds"], 2.0)
        self.assertEqual(summary["min_seconds"], 1.0)
        self.assertEqual(summary["max_seconds"], 3.0)

    def test_summarize_empty(self) -> None:
        summary = voice_test.summarize_latencies([])
        self.assertEqual(summary["round_count"], 0)
        self.assertEqual(summary["average_seconds"], 0.0)


class LedgerExtractTest(unittest.TestCase):
    def test_token_generation_metrics(self) -> None:
        metrics = benchmark_ledger.extract_metrics(
            "token-generation",
            {
                "tokens_per_second_est": 132.4,
                "time_to_first_content_seconds": 0.41,
                "elapsed_seconds": 2.01,
                "output_tokens_est": 256,
                "saw_reasoning_channel": True,
            },
        )
        self.assertEqual(metrics["tokens_per_second_est"], 132.4)
        self.assertEqual(metrics["time_to_first_content_seconds"], 0.41)
        self.assertEqual(metrics["elapsed_seconds"], 2.01)
        self.assertEqual(metrics["output_tokens_est"], 256.0)
        self.assertIs(metrics["saw_reasoning_channel"], True)

    def test_memory_footprint_metrics_with_delta(self) -> None:
        metrics = benchmark_ledger.extract_metrics(
            "memory-footprint",
            {
                "memory_source": "system-unified",
                "baseline": {"memory_used_mb_mean": 1000.0},
                "post_load": {"memory_used_mb_mean": 2500.0},
                "contexts": [
                    {"requested_tokens": 8192, "memory_snapshot": {"memory_used_mb_max": 3000.0}},
                    {"requested_tokens": 32768, "memory_snapshot": {"memory_used_mb_max": 3400.0}},
                ],
            },
        )
        self.assertEqual(metrics["memory_source"], "system-unified")
        self.assertEqual(metrics["baseline_used_mb"], 1000.0)
        self.assertEqual(metrics["post_load_used_mb"], 2500.0)
        self.assertEqual(metrics["load_delta_mb"], 1500.0)
        self.assertEqual(metrics["max_context_used_mb"], 3400.0)
        self.assertEqual(metrics["max_context_tokens"], 32768.0)

    def test_memory_footprint_metrics_without_contexts(self) -> None:
        metrics = benchmark_ledger.extract_metrics(
            "memory-footprint",
            {"baseline": {}, "post_load": {}, "contexts": []},
        )
        self.assertIsNone(metrics["baseline_used_mb"])
        self.assertIsNone(metrics["load_delta_mb"])
        self.assertEqual(metrics["max_context_used_mb"], 0.0)
        self.assertEqual(metrics["max_context_tokens"], 0.0)

    def test_voice_latency_metrics(self) -> None:
        metrics = benchmark_ledger.extract_metrics(
            "voice-latency",
            {"median_seconds": 0.42, "average_seconds": 0.44, "round_count": 3},
        )
        self.assertEqual(metrics["median_seconds"], 0.42)
        self.assertEqual(metrics["average_seconds"], 0.44)
        self.assertEqual(metrics["round_count"], 3.0)

    def test_unknown_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            benchmark_ledger.extract_metrics("quantum-flux", {})


class LedgerAppendTest(unittest.TestCase):
    def test_append_creates_and_extends_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            ledger = pathlib.Path(temporary_dir) / "runs.jsonl"
            record_a = benchmark_ledger.build_record(
                "voice-latency", "eliza-small", "small/a", {"model": "a"}
            )
            record_b = benchmark_ledger.build_record(
                "voice-latency", "eliza-small", "small/b", {"model": "b"}
            )
            benchmark_ledger.append_run(ledger, record_a)
            benchmark_ledger.append_run(ledger, record_b)

            lines = ledger.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        first, second = (json.loads(line) for line in lines)
        self.assertEqual(first["profile"], "small/a")
        self.assertEqual(first["type"], "voice-latency")
        self.assertIn("timestamp", first)
        self.assertEqual(first["result_file"], "")
        self.assertEqual(second["profile"], "small/b")
        self.assertEqual(second["model"], "b")

    def test_build_record_prefers_explicit_identity(self) -> None:
        record = benchmark_ledger.build_record(
            "token-generation",
            "eliza-medium",
            "medium/explicit",
            {"service": "json-service", "profile": "json-profile", "model": "m"},
            result_file="/tmp/dir/some-result.json",
            timestamp="2026-08-24T12:00:00+00:00",
        )
        self.assertEqual(record["service"], "eliza-medium")
        self.assertEqual(record["profile"], "medium/explicit")
        self.assertEqual(record["result_file"], "some-result.json")
        self.assertEqual(record["timestamp"], "2026-08-24T12:00:00+00:00")


class CompareTimestampTest(unittest.TestCase):
    def test_compact_local_format(self) -> None:
        self.assertEqual(benchmark_compare.normalize_timestamp("20260824-122902"), "20260824122902")

    def test_compact_utc_format(self) -> None:
        self.assertEqual(benchmark_compare.normalize_timestamp("20260824T123106"), "20260824123106")

    def test_iso_with_timezone(self) -> None:
        self.assertEqual(
            benchmark_compare.normalize_timestamp("2026-08-24T12:34:56+00:00"),
            "20260824123456",
        )


class CompareLoadTest(unittest.TestCase):
    def test_load_ledger_skips_malformed_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            ledger = pathlib.Path(temporary_dir) / "runs.jsonl"
            good = {
                "service": "eliza-small",
                "profile": "small/a",
                "type": "voice-latency",
                "timestamp": "2026-08-24T12:00:00+00:00",
                "model": "a",
                "metrics": {"median_seconds": 0.5},
            }
            ledger.write_text(
                json.dumps(good) + "\nnot-json\n" + json.dumps({"type": "unknown", "metrics": {}}) + "\n",
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                runs = benchmark_compare.load_ledger(ledger)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["profile"], "small/a")
        self.assertIn("malformed", stderr.getvalue())

    def test_scan_result_files_parses_legacy_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            results_dir = pathlib.Path(temporary_dir)
            (results_dir / "eliza-medium-medium-qwen3.8-27b-fp8-sglang-256k-stream-20260824-120000.json").write_text(
                json.dumps({"model": "eliza-medium", "tokens_per_second_est": 100.0}),
                encoding="utf-8",
            )
            (results_dir / "eliza-small-gemma3-4b-q4-llamacpp-8k-voice-latency-20260824T120100.json").write_text(
                json.dumps({"model": "gemma", "median_seconds": 0.5, "average_seconds": 0.5, "round_count": 3}),
                encoding="utf-8",
            )
            runs = benchmark_compare.scan_result_files(results_dir)

        by_type = {run["type"]: run for run in runs}
        stream = by_type["token-generation"]
        self.assertEqual(stream["service"], "eliza-medium")
        self.assertEqual(stream["profile"], "medium/qwen3.8-27b-fp8-sglang-256k")
        self.assertEqual(stream["metrics"]["tokens_per_second_est"], 100.0)
        voice = by_type["voice-latency"]
        self.assertEqual(voice["service"], "eliza-small")
        self.assertEqual(voice["profile"], "small/gemma3-4b-q4-llamacpp-8k")
        self.assertEqual(voice["metrics"]["median_seconds"], 0.5)

    def test_scan_prefers_json_identity_over_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            results_dir = pathlib.Path(temporary_dir)
            (results_dir / "eliza-medium-odd-slug-stream-20260824-120000.json").write_text(
                json.dumps(
                    {
                        "service": "eliza-medium",
                        "profile": "medium/real-profile",
                        "model": "m",
                        "tokens_per_second_est": 50.0,
                    }
                ),
                encoding="utf-8",
            )
            runs = benchmark_compare.scan_result_files(results_dir)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["profile"], "medium/real-profile")


class CompareSelectTest(unittest.TestCase):
    def runs(self):
        return [
            {
                "service": "eliza-small",
                "profile": "small/a",
                "type": "voice-latency",
                "timestamp": "20260824-100000",
                "metrics": {"median_seconds": 1.0},
            },
            {
                "service": "eliza-small",
                "profile": "small/a",
                "type": "voice-latency",
                "timestamp": "20260824-110000",
                "metrics": {"median_seconds": 0.5},
            },
            {
                "service": "eliza-small",
                "profile": "small/b",
                "type": "voice-latency",
                "timestamp": "20260824-090000",
                "metrics": {"median_seconds": 2.0},
            },
        ]

    def test_latest_per_profile_is_kept(self) -> None:
        selected = benchmark_compare.select_runs(self.runs(), all_runs=False)
        self.assertEqual(len(selected), 2)
        by_profile = {run["profile"]: run for run in selected}
        self.assertEqual(by_profile["small/a"]["metrics"]["median_seconds"], 0.5)
        self.assertEqual(by_profile["small/b"]["metrics"]["median_seconds"], 2.0)

    def test_all_runs_keeps_everything(self) -> None:
        selected = benchmark_compare.select_runs(self.runs(), all_runs=True)
        self.assertEqual(len(selected), 3)


class CompareRenderTest(unittest.TestCase):
    def test_render_tables_and_blank_cells(self) -> None:
        runs = [
            {
                "service": "eliza-medium",
                "profile": "medium/a",
                "type": "token-generation",
                "timestamp": "2026-08-24T12:00:00+00:00",
                "model": "a",
                "result_file": "a-stream.json",
                "metrics": {
                    "tokens_per_second_est": 100.0,
                    "time_to_first_content_seconds": None,
                    "elapsed_seconds": 2.0,
                    "output_tokens_est": 256.0,
                    "saw_reasoning_channel": False,
                },
            },
            {
                "service": "eliza-small",
                "profile": "small/a",
                "type": "voice-latency",
                "timestamp": "2026-08-24T12:00:00+00:00",
                "model": "a",
                "result_file": "a-voice.json",
                "metrics": {"median_seconds": 0.5, "average_seconds": 0.5, "round_count": 3.0},
            },
        ]
        markdown = benchmark_compare.render_markdown(runs, False, "ledger `runs.jsonl` (2 runs)", pathlib.Path("benchmarks/results"))

        self.assertIn("# Benchmark Results", markdown)
        self.assertIn("## eliza-medium", markdown)
        self.assertIn("## eliza-small", markdown)
        self.assertIn("### Token generation", markdown)
        self.assertIn("### Voice latency", markdown)
        self.assertIn("| `medium/a` | 100.0 | - | 2.00 | 256 | no |", markdown)
        self.assertIn("| `small/a` | 0.500 | 0.500 | 3 |", markdown)
        self.assertIn("`a-stream.json`", markdown)
        self.assertIn("./scripts/run-benchmark compare", markdown)

    def test_all_runs_adds_run_time_column(self) -> None:
        runs = [
            {
                "service": "eliza-small",
                "profile": "small/a",
                "type": "voice-latency",
                "timestamp": "20260824T120000",
                "model": "a",
                "result_file": "",
                "metrics": {"median_seconds": 0.5, "average_seconds": 0.5, "round_count": 3.0},
            }
        ]
        markdown = benchmark_compare.render_markdown(runs, True, "scan (1 runs)", pathlib.Path("benchmarks/results"))
        self.assertIn("| Profile | Run (UTC) | Median (s)", markdown)
        self.assertIn("2026-08-24 12:00:00", markdown)


class CompareMainTest(unittest.TestCase):
    def test_no_runs_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            results_dir = pathlib.Path(temporary_dir) / "results"
            results_dir.mkdir()
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = benchmark_compare.main(["--results-dir", str(results_dir)])
        self.assertEqual(code, 2)
        self.assertIn("No benchmark runs found", stderr.getvalue())

    def test_end_to_end_ledger_to_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            results_dir = pathlib.Path(temporary_dir) / "results"
            results_dir.mkdir()
            ledger = results_dir / "runs.jsonl"
            result_json = results_dir / "run.json"
            result_json.write_text(
                json.dumps(
                    {
                        "service": "eliza-medium",
                        "profile": "medium/a",
                        "model": "a",
                        "tokens_per_second_est": 99.9,
                        "elapsed_seconds": 1.0,
                    }
                ),
                encoding="utf-8",
            )
            benchmark_ledger.main(
                [
                    "add",
                    "--ledger", str(ledger),
                    "--type", "token-generation",
                    "--service", "eliza-medium",
                    "--profile", "medium/a",
                    "--result-json", str(result_json),
                ]
            )
            output = pathlib.Path(temporary_dir) / "RESULTS.md"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = benchmark_compare.main(
                    ["--results-dir", str(results_dir), "--output", str(output)]
                )
            self.assertEqual(code, 0)
            markdown = output.read_text(encoding="utf-8")
        self.assertIn("`medium/a` | 99.9", markdown)
        self.assertIn("Wrote comparison for 1 runs", stdout.getvalue())


class ClientIdentityTest(unittest.TestCase):
    def test_voice_result_includes_identity(self) -> None:
        class FakeResponse:
            def __init__(self, body: bytes):
                self._body = body

            def read(self) -> bytes:
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        body = json.dumps(
            {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = pathlib.Path(temporary_dir) / "voice.json"
            with patch.object(
                voice_test.urllib.request, "urlopen", return_value=FakeResponse(body)
            ):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    code = voice_test.main(
                        [
                            "--base-url", "http://127.0.0.1:9/v1",
                            "--model", "gemma",
                            "--service", "eliza-small",
                            "--profile", "small/gemma4-e2b-q4-llamacpp-8k",
                            "--rounds", "1",
                            "--output-json", str(output),
                        ]
                    )
            self.assertEqual(code, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["service"], "eliza-small")
        self.assertEqual(result["profile"], "small/gemma4-e2b-q4-llamacpp-8k")

    def test_stream_result_includes_identity(self) -> None:
        class FakeStream:
            def __init__(self, lines: list[bytes]):
                self._lines = list(lines)

            def __iter__(self):
                return iter(self._lines)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        lines = [
            b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n',
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n',
            b"data: [DONE]\n\n",
        ]
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = pathlib.Path(temporary_dir) / "stream.json"
            with patch.object(
                stream_inspect.urllib.request, "urlopen", return_value=FakeStream(lines)
            ):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    code = stream_inspect.main(
                        [
                            "--base-url", "http://127.0.0.1:9/v1",
                            "--model", "eliza-medium",
                            "--service", "eliza-medium",
                            "--profile", "medium/qwen3.8-27b-fp8-sglang-256k",
                            "--max-tokens", "8",
                            "--output-json", str(output),
                        ]
                    )
            self.assertEqual(code, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["service"], "eliza-medium")
        self.assertEqual(result["profile"], "medium/qwen3.8-27b-fp8-sglang-256k")
        self.assertEqual(result["content_chunks"], 1)


if __name__ == "__main__":
    unittest.main()
