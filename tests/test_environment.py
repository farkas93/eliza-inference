"""Exercise transitions, persisted recovery and cross-process start exclusion."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.lib.environment import EnvironmentBusy, EnvironmentError, EnvironmentManager


class FakeHost(EnvironmentManager):
    def rest_ready(self):
        pass

    def __init__(self, root):
        super().__init__(root)
        self.active = set()
        self.sessions = {"eliza-small"}
        self.commands = []
        self.jobs = ""
        self.gpu_processes = ""
        self.gpu_samples = []
        self.node_rows = "up|idle|none"
        self.smoke_failures = []
        self.failure = None
        self.profile_path.write_text(json.dumps({"eliza-small": "small/exact-profile"}))

    def running(self, service):
        return service in self.sessions

    def unit_active(self, unit, *, user=False):
        return unit in self.active

    def run(self, args, *, check=True, admin=False, timeout=None):
        self.commands.append(args)
        if self.failure and self.failure in " ".join(args):
            raise EnvironmentError("injected host failure")
        out = ""
        if args[:2] == ["systemctl", "show"]:
            out = "loaded"
        if args[:2] == ["systemctl", "start"]:
            self.active.add(args[2])
        if args[:2] == ["systemctl", "stop"]:
            self.active.discard(args[2])
        if args[0].endswith("scripts/stop"):
            self.sessions.discard(args[1])
        if args[0].endswith("scripts/start"):
            self.sessions.add(args[1])
        if args[0] == "squeue":
            out = self.jobs if "--all" in args else ""
        if args[0] == "sinfo":
            out = self.node_rows if "--all" in args else ""
        if args[:2] == ["scontrol", "ping"]:
            out = "Slurmctld(primary) at dgx is UP"
        if args[:2] == ["scontrol", "token"]:
            out = "SLURM_JWT=fixture-jwt"
        if args[0] == "nvidia-smi":
            out = self.gpu_samples.pop(0) if self.gpu_samples else self.gpu_processes
        if args[:2] == ["tmux", "list-panes"] and "=eliza-small" in args:
            out = "100"
        if args[0] == "ps":
            out = "100 1\n101 100\n102 101\n999 1"
        if args[0].endswith("scripts/smoke-test") and args[1] in self.smoke_failures:
            self.smoke_failures.remove(args[1])
            return subprocess.CompletedProcess(args, 1, "", "HTTP Error 503: Service Unavailable")
        return subprocess.CompletedProcess(args, 0, out, "")


class TransitionTests(unittest.TestCase):
    def test_advertisement_is_available_with_slurm_stopped(self):
        path = self.root / "host.json"
        path.write_text(json.dumps({"rest_url": "http://dgx:6820", "api_versions": ["v0.0.45"], "partitions": [], "workspace": "/jobs", "job_user": "job-user"}))
        with patch.dict(os.environ, {"ELIZA_SLURM_HOST_CONFIG": str(path)}):
            report = self.host.advertise()
        self.assertEqual(report["mode"], "inference")
        self.assertFalse(report["ready"])
        self.assertEqual(report["workspace"], "/jobs")
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".runtime").mkdir()
        self.env = patch.dict(os.environ, {"ELIZA_TRAINING_ENABLED": "true", "ELIZA_GPU_RELEASE_TIMEOUT_SECONDS": "0"})
        self.env.start()
        self.host = FakeHost(self.root)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_roundtrip_orders_shutdown_and_restores_exact_profile(self):
        train = self.host.switch("training")
        self.assertEqual(train["phase"], "training")
        self.assertFalse(self.host.sessions)
        self.assertEqual(self.host.active, set(self.host.units))
        stop_index = next(i for i, c in enumerate(self.host.commands) if c[0].endswith("scripts/stop"))
        start_index = self.host.commands.index(["systemctl", "start", "slurmctld.service"])
        self.assertLess(stop_index, start_index)
        self.host.switch("inference")
        self.assertFalse(self.host.active)
        self.assertEqual(self.host.sessions, {"eliza-small"})
        self.assertIn([str(self.root / "scripts/start"), "eliza-small", "--profile", "small/exact-profile"], self.host.commands)

    def test_busy_queue_keeps_training_running_and_does_not_restore_inference(self):
        self.host.switch("training")
        self.host.jobs = "42 RUNNING\n43 PENDING"
        with self.assertRaises(EnvironmentBusy):
            self.host.switch("inference")
        self.assertEqual(self.host.state()["phase"], "training")
        self.assertEqual(self.host.active, set(self.host.units))
        self.assertFalse(self.host.sessions)
        self.assertIn(["scontrol", "update", "PartitionName=training", "State=INACTIVE"], self.host.commands)

    def test_failed_training_start_preserves_snapshot_for_recovery(self):
        self.host.failure = "start slurmd.service"
        with self.assertRaises(EnvironmentError):
            self.host.switch("training")
        saved = self.host.state()
        self.assertEqual(saved["phase"], "failed")
        self.assertEqual(saved["restore"][0]["profile"], "small/exact-profile")
        self.host.failure = None
        # A new controller instance can recover the same state after a restart.
        restarted = FakeHost(self.root)
        restarted.sessions = set()
        restarted.active = self.host.active
        restarted.switch("inference")
        self.assertEqual(restarted.sessions, {"eliza-small"})

    def test_external_gpu_process_blocks_scheduler_start(self):
        self.host.gpu_processes = "999"
        with self.assertRaisesRegex(EnvironmentError, "GPU compute processes remain"):
            self.host.switch("training")
        self.assertFalse(self.host.active)
        self.assertEqual(self.host.state()["phase"], "failed")

    def test_training_waits_for_gpu_release(self):
        self.host.gpu_samples = ["102", ""]
        with patch.dict(os.environ, {"ELIZA_GPU_RELEASE_TIMEOUT_SECONDS": "5"}), patch("scripts.lib.environment.time.sleep") as sleep:
            self.assertEqual(self.host.switch("training")["phase"], "training")
        sleep.assert_called_once()

    def test_inference_retries_smoke_test_while_model_loads(self):
        self.host.switch("training")
        self.host.smoke_failures = ["eliza-small"]
        with patch("scripts.lib.environment.time.sleep") as sleep:
            self.assertEqual(self.host.switch("inference")["phase"], "inference")
        sleep.assert_called_once()

    def test_resume_failed_restore_keeps_saved_service_but_rejects_unrelated_gpu(self):
        restore = [{"service": "eliza-small", "profile": "small/exact-profile"},
                   {"service": "eliza-medium", "profile": "medium/exact-profile"},
                   {"service": "vocode-bridge", "profile": "vocode/bridge-local"}]
        self.host.save({"version": 1, "phase": "failed", "target": "inference", "restore": restore})
        self.host.gpu_processes = "102\n999"
        with self.assertRaisesRegex(EnvironmentError, r"blocked: 999$"):
            self.host.switch("inference")
        self.assertEqual(self.host.sessions, {"eliza-small"})

        self.host.gpu_processes = "102"
        self.assertEqual(self.host.switch("inference")["phase"], "inference")
        starts = [args[1] for args in self.host.commands if args[0].endswith("scripts/start")]
        self.assertEqual(starts, ["eliza-medium", "vocode-bridge"])

    def test_restore_timeout_preserves_snapshot(self):
        self.host.switch("training")
        self.host.smoke_failures = ["eliza-small"]
        with patch.dict(os.environ, {"ELIZA_INFERENCE_READY_TIMEOUT_SECONDS": "0"}):
            with self.assertRaisesRegex(EnvironmentError, "eliza-small .* did not become ready: HTTP Error 503"):
                self.host.switch("inference")
        state = self.host.state()
        self.assertEqual(state["phase"], "failed")
        self.assertEqual(state["restore"][0]["profile"], "small/exact-profile")

    def test_slurm_readiness_reports_missing_nodes_and_drain_reason(self):
        self.host.active = set(self.host.units)
        self.host.sessions.clear()
        for rows, detail in (("", "no matching node"), ("up|drained|Low RealMemory", "Low RealMemory")):
            with self.subTest(rows=rows):
                self.host.node_rows = rows
                with self.assertRaisesRegex(EnvironmentError, detail):
                    self.host.verify("training")

    def test_disabled_training_does_not_stop_inference(self):
        with patch.dict(os.environ, {"ELIZA_TRAINING_ENABLED": "false"}):
            with self.assertRaises(EnvironmentError):
                self.host.switch("training")
        self.assertEqual(self.host.sessions, {"eliza-small"})
        self.assertFalse(self.host.commands)

    def test_corrupted_state_fails_closed(self):
        self.host.path.write_text('{"version": 1, "phase": "surprise"}')
        with self.assertRaises(EnvironmentError):
            self.host.guard_start(["never-run"])
        self.assertFalse(self.host.commands)

    def test_start_is_blocked_in_training_and_failed_modes(self):
        for phase in ("training", "failed", "switching_to_training", "switching_to_inference"):
            self.host.save({"version": 1, "phase": phase, "restore": []})
            with self.assertRaises(EnvironmentBusy):
                self.host.guard_start(["never-run"])

    def test_other_process_cannot_start_during_transition(self):
        module = Path(__file__).resolve().parents[1] / "scripts/lib/environment.py"
        with self.host.lock():
            result = subprocess.run(
                [sys.executable, str(module), "guard-start", "--", "never-run"],
                env={**os.environ, "ELIZA_ENVIRONMENT_STATE": str(self.host.path)},
                capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 3)
        self.assertIn("Another host environment operation", result.stderr)

    def test_inherited_lock_is_recognized_by_start_entrypoint(self):
        module = Path(__file__).resolve().parents[1] / "scripts/lib/environment.py"
        with self.host.lock():
            result = subprocess.run(
                [sys.executable, str(module), "lock-held"],
                env={**os.environ, "ELIZA_ENVIRONMENT_STATE": str(self.host.path),
                     "ELIZA_ENVIRONMENT_LOCK_FD": str(self.host.fd)},
                pass_fds=(self.host.fd,),
            )
        self.assertEqual(result.returncode, 0)

    def test_rest_authentication_challenge_is_ready_but_server_error_is_not(self):
        manager = EnvironmentManager(self.root)
        with patch("scripts.lib.environment.urlopen", side_effect=HTTPError("http://slurm", 401, "Unauthorized", {}, None)):
            manager.rest_ready()
        with patch("scripts.lib.environment.urlopen", side_effect=HTTPError("http://slurm", 503, "Unavailable", {}, None)):
            with self.assertRaises(EnvironmentError):
                manager.rest_ready()

    def test_token_is_scoped_to_configured_user_and_training_mode(self):
        with self.assertRaises(EnvironmentBusy):
            self.host.training_token()
        self.host.switch("training")
        with patch.dict(os.environ, {"ELIZA_SLURM_USER": "training-account", "ELIZA_SLURM_TOKEN_LIFESPAN": "600"}), patch("scripts.lib.environment.pwd.getpwnam", return_value=SimpleNamespace(pw_uid=1001)):
            receipt = self.host.training_token()
        self.assertEqual(receipt["user_name"], "training-account")
        self.assertIn(["scontrol", "token", "username=training-account", "lifespan=600"], self.host.commands)

    def test_root_credential_delegation_is_rejected(self):
        self.host.switch("training")
        with patch("scripts.lib.environment.pwd.getpwnam", return_value=SimpleNamespace(pw_uid=0)):
            with self.assertRaisesRegex(EnvironmentError, "root identity"):
                self.host.training_token()


if __name__ == "__main__":
    unittest.main()
