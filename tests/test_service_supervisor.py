from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "scripts/lib/service_supervisor.py"
spec = importlib.util.spec_from_file_location("service_supervisor", SUPERVISOR)
supervisor_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor_module)

MODEL = '''\
import http.server, json, os, pathlib, resource, signal, subprocess, sys, time
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
counter = pathlib.Path(os.environ["MODEL_COUNTER"])
previous = counter.read_text().splitlines() if counter.exists() else []
with counter.open("a") as handle:
    handle.write(str(os.getpid()) + "\\n")
mode = os.environ.get("MODEL_MODE", "serve")
if mode == "crash-first" and not previous:
    os.kill(os.getpid(), signal.SIGABRT)
if mode == "exit-one":
    sys.exit(1)
if mode == "exit-zero":
    sys.exit(0)
if mode == "config-error":
    sys.exit(78)
if mode == "worker":
    code = "import os,pathlib,signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); pathlib.Path(os.environ['WORKER_PID']).write_text(str(os.getpid())); time.sleep(600)"
    subprocess.Popen([sys.executable, "-c", code])
if os.environ.get("HEALTH_PORT"):
    time.sleep(float(os.environ.get("STARTUP_DELAY", "0")))
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"data":[{"id":"test-model"}]}')
        def log_message(self, *args):
            pass
    http.server.HTTPServer(("127.0.0.1", int(os.environ["HEALTH_PORT"])), Handler).serve_forever()
else:
    time.sleep(600)
'''


class ServiceSupervisorTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.state = self.root / "eliza-medium.supervisor.json"
        self.counter = self.root / "attempts"
        self.model = self.root / "model.py"
        self.model.write_text(MODEL)
        self.processes = []

    def tearDown(self):
        for process, log in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            log.close()
        self.temporary.cleanup()

    def launch(self, mode="serve", health=False, delay="0.1", extra_env=None, supervisor_path=SUPERVISOR):
        env = dict(os.environ, MODEL_MODE=mode, MODEL_COUNTER=str(self.counter),
                   WORKER_PID=str(self.root / "worker.pid"))
        if extra_env:
            env.update(extra_env)
        health_url = ""
        if health:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            env["HEALTH_PORT"] = str(port)
            health_url = f"http://127.0.0.1:{port}/v1/models"
        command = [sys.executable, str(supervisor_path), "run", "--state", str(self.state),
                   "--service", "eliza-medium", "--profile", "medium/test", "--health-url", health_url,
                   "--restart-delay", delay, "--max-restart-delay", "2", "--reset-after", "1",
                   "--shutdown-timeout", "0.3", "--", sys.executable, "-u", str(self.model)]
        log = (self.root / f"supervisor-{len(self.processes)}.log").open("w")
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        self.processes.append((process, log))
        return process, health_url

    def status(self):
        return supervisor_module.load_status(self.state)

    def wait_for(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        logs = "\n".join(path.read_text() for path in self.root.glob("*.log"))
        self.fail(f"Timed out waiting for supervisor state: {self.status()}\n{logs}")

    def attempts(self):
        return self.counter.read_text().splitlines() if self.counter.exists() else []

    def stop(self):
        result = subprocess.run([sys.executable, str(SUPERVISOR), "stop", "--state", str(self.state),
                                 "--timeout", "4"], capture_output=True, text=True, timeout=6)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_abort_recovers_same_profile_and_health_endpoint(self):
        process, health_url = self.launch("crash-first", health=True)
        self.wait_for(lambda: len(self.attempts()) == 2 and self.status().get("status") == "running")
        state = self.status()
        self.assertEqual(state["profile"], "medium/test")
        self.assertEqual(state["restart_count"], 1)
        self.assertEqual(state["last_exit_code"], -signal.SIGABRT)
        with urlopen(health_url, timeout=1) as response:
            self.assertEqual(response.status, 200)
        self.stop()
        self.assertEqual(process.wait(timeout=4), 0)
        self.assertEqual(self.status()["status"], "stopped")
        self.assertEqual(len(self.attempts()), 2)

    def test_stop_cancels_backoff_and_does_not_respawn(self):
        process, _ = self.launch("exit-one", delay="1")
        self.wait_for(lambda: self.status().get("status") == "backoff")
        self.stop()
        self.assertEqual(process.wait(timeout=4), 0)
        time.sleep(0.1)
        self.assertEqual(len(self.attempts()), 1)
        self.assertEqual(self.status()["status"], "stopped")

    def test_killed_model_recovers_without_restarting_the_supervisor(self):
        process, _ = self.launch(health=True)
        self.wait_for(lambda: self.status().get("status") == "running")
        first_pid = self.status()["child_pid"]
        os.kill(first_pid, signal.SIGKILL)
        self.wait_for(lambda: len(self.attempts()) == 2 and self.status().get("status") == "running")
        self.assertEqual(self.status()["supervisor_pid"], process.pid)
        self.assertNotEqual(self.status()["child_pid"], first_pid)
        self.assertEqual(self.status()["last_exit_code"], -signal.SIGKILL)
        self.stop()

    def test_healthy_uptime_resets_the_backoff_after_a_later_crash(self):
        process, _ = self.launch("crash-first", health=True, delay="0.3")
        self.wait_for(lambda: len(self.attempts()) == 2 and self.status().get("status") == "running")
        time.sleep(1.1)  # this test launches with --reset-after 1
        os.kill(self.status()["child_pid"], signal.SIGKILL)
        self.wait_for(lambda: self.status().get("status") == "backoff" and self.status().get("restart_count") == 2)
        self.assertAlmostEqual(self.status()["next_restart_at"] - self.status()["updated_at"], 0.3, delta=0.03)
        self.stop()
        self.assertEqual(process.wait(timeout=4), 0)

    def test_unexpected_successful_exit_is_also_restarted(self):
        process, _ = self.launch("exit-zero", delay="1")
        self.wait_for(lambda: self.status().get("status") == "backoff")
        self.assertEqual(self.status()["last_exit_code"], 0)
        self.stop()
        self.assertEqual(process.wait(timeout=4), 0)

    def test_configuration_error_is_not_an_infinite_restart_loop(self):
        process, _ = self.launch("config-error")
        self.assertEqual(process.wait(timeout=5), 78)
        self.assertEqual(len(self.attempts()), 1)
        self.assertEqual(self.status()["status"], "failed")
        self.assertEqual(self.status()["restart_count"], 0)

    def test_hangup_stops_the_model_and_stubborn_worker(self):
        process, _ = self.launch("worker")
        worker_file = self.root / "worker.pid"
        self.wait_for(lambda: worker_file.exists() and self.status().get("status") == "running")
        worker_pid = int(worker_file.read_text())
        process.send_signal(signal.SIGHUP)
        self.assertEqual(process.wait(timeout=4), 0)
        self.assertEqual(self.status()["status"], "stopped")
        # A container's PID 1 may retain a dead orphan as a zombie; it holds no model resources.
        worker_stat = pathlib.Path(f"/proc/{worker_pid}/stat")
        self.wait_for(lambda: not worker_stat.exists() or worker_stat.read_text().split()[2] == "Z")
        self.assertEqual(len(self.attempts()), 1)

    def test_no_overlapping_supervisors_can_launch_two_models(self):
        first, _ = self.launch()
        self.wait_for(lambda: len(self.attempts()) == 1 and self.status().get("status") == "running")
        second, _ = self.launch()
        self.assertEqual(second.wait(timeout=4), 73)
        self.assertEqual(self.status()["supervisor_pid"], first.pid)
        self.assertEqual(len(self.attempts()), 1)
        self.stop()

    def test_readiness_stays_starting_until_weights_have_loaded(self):
        process, _ = self.launch(health=True, extra_env={"STARTUP_DELAY": "0.6"})
        self.wait_for(lambda: self.status().get("status") == "starting")
        self.wait_for(lambda: self.status().get("status") == "running")
        self.assertEqual(self.status()["restart_count"], 0)
        self.stop()
        self.assertEqual(process.wait(timeout=4), 0)

    def test_stale_pid_state_never_stops_an_unrelated_process(self):
        self.state.write_text(json.dumps({"supervisor_pid": os.getpid()}))
        self.stop()

    def test_stop_recognizes_a_supervisor_started_through_a_symlink(self):
        alias = self.root / "supervisor.py"
        alias.symlink_to(SUPERVISOR)
        process, _ = self.launch(supervisor_path=alias)
        self.wait_for(lambda: self.status().get("status") == "running")
        self.stop()
        self.assertEqual(process.wait(timeout=4), 0)
        self.assertEqual(self.status()["status"], "stopped")

    def test_tmux_runner_exports_global_settings_and_preserves_logs(self):
        scripts = self.root / "scripts/lib"
        scripts.mkdir(parents=True)
        shutil.copy2(ROOT / "scripts/lib/run-service.sh", scripts / "run-service.sh")
        shutil.copy2(ROOT / "scripts/lib/common.sh", scripts / "common.sh")
        profiles = self.root / "configs/profiles/medium"
        profiles.mkdir(parents=True)
        (profiles / "test.env").write_text('SERVICE_NAME="eliza-medium"\nBACKEND="test"\n')
        service = self.root / "services/eliza-medium"
        service.mkdir(parents=True)
        start = service / "start.sh"
        start.write_text('#!/bin/bash\nprintf "%s\\n" "$GLOBAL_TEST_OPTION"\n')
        start.chmod(0o755)
        (self.root / ".env").write_text(
            f'ELIZA_MEDIUM_AUTORESTART="false"\nLOG_DIR="{self.root}/logs"\n'
            f'SERVICE_SUPERVISOR_DIR="{self.root}/runtime"\nGLOBAL_TEST_OPTION="from-global-env"\n'
        )
        result = subprocess.run(["bash", str(scripts / "run-service.sh"), "eliza-medium", "--profile", "medium/test"],
                                cwd=self.root, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("from-global-env", result.stdout)
        self.assertIn("from-global-env", (self.root / "logs/eliza-medium.log").read_text())

    def test_backoff_is_capped_and_handles_many_crashes(self):
        self.assertEqual([supervisor_module.restart_delay(attempt, 2, 60) for attempt in (1, 2, 3, 7)],
                         [2, 4, 8, 60])
        self.assertEqual(supervisor_module.restart_delay(100000, 2, 60), 60)


if __name__ == "__main__":
    unittest.main()
