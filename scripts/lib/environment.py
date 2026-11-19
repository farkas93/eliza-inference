"""Host lifecycle only: no scheduler job supervisor or training dependencies."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import pwd
import shlex
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

if __package__:
    from .runtime_state import save_state
else:
    from runtime_state import save_state

SERVICES = ("stt", "tts", "eliza-small", "eliza-medium", "vocode-bridge", "voice-assistant")
LOCK_FD_ENV = "ELIZA_ENVIRONMENT_LOCK_FD"


class EnvironmentError(RuntimeError):
    pass


class EnvironmentBusy(EnvironmentError):
    pass


class EnvironmentManager:
    def __init__(self, root: Path, *, state_path: Path | None = None):
        self.root = root
        self.path = state_path or Path(os.environ.get(
            "ELIZA_ENVIRONMENT_STATE", str(root / ".runtime/environment.json")))
        self.lock_path = self.path.with_suffix(".lock")
        self.profile_path = Path(os.environ.get(
            "RUNTIME_STATE_FILE", str(root / ".runtime/service_profiles.json")))
        self.units = ("munge.service", "slurmctld.service", "slurmd.service", "slurmrestd.service")
        self.admin = shlex.split(os.environ.get("ELIZA_SLURM_ADMIN_PREFIX", "sudo -n"))
        self.partition = os.environ.get("ELIZA_SLURM_PARTITION", "training")
        self.node = os.environ.get("ELIZA_SLURM_NODE", socket.gethostname().split(".")[0])
        self.timeout = int(os.environ.get("CONTROL_START_TIMEOUT_SECONDS", "1200"))
        self.fd: int | None = None

    def state(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "phase": "inference", "restore": []}
        data = json.loads(self.path.read_text())
        if data.get("version") != 1 or data.get("phase") not in {
            "inference", "training", "switching_to_training", "switching_to_inference", "failed"
        } or not isinstance(data.get("restore"), list):
            raise EnvironmentError("Invalid environment state; preserve it and investigate before switching")
        for entry in data["restore"]:
            if entry.get("service") not in SERVICES or not isinstance(entry.get("profile"), str):
                raise EnvironmentError("Invalid restore entry")
        return data

    def save(self, state: dict):
        save_state(self.path, state)

    @contextmanager
    def lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise EnvironmentBusy("Another host environment operation is running") from exc
            self.fd = handle.fileno()
            try:
                yield
            finally:
                self.fd = None
                fcntl.flock(handle, fcntl.LOCK_UN)

    def inherited_lock(self) -> bool:
        try:
            fd = int(os.environ[LOCK_FD_ENV])
            stat = os.fstat(fd)
            expected = self.lock_path.stat()
            return (stat.st_dev, stat.st_ino) == (expected.st_dev, expected.st_ino)
        except (KeyError, ValueError, OSError):
            return False

    def run(self, args: list[str], *, check: bool = True, admin: bool = False, timeout=None):
        env = os.environ.copy()
        fds = ()
        if self.fd is not None:
            env[LOCK_FD_ENV] = str(self.fd)
            fds = (self.fd,)
        result = subprocess.run(
            (self.admin if admin else []) + args, cwd=self.root,
            env=env, pass_fds=fds, capture_output=True, text=True,
            timeout=self.timeout if timeout is None else timeout,
        )
        if check and result.returncode:
            raise EnvironmentError(f"{shlex.join(args)} failed: {result.stderr.strip()}")
        return result

    def unit_active(self, unit: str, *, user: bool = False) -> bool:
        result = self.run(["systemctl", *(["--user"] if user else []), "is-active", unit], check=False)
        if result.returncode not in (0, 3, 4):
            # A user bus is optional for CLI/tmux installations.
            if user and "Failed to connect to bus" in result.stderr:
                return False
            raise EnvironmentError(f"Cannot inspect {unit}: {result.stderr.strip()}")
        return result.returncode == 0

    @staticmethod
    def session(service: str) -> str:
        return service if service.startswith("eliza-") else "eliza-" + service

    def running(self, service: str) -> bool:
        result = self.run(["tmux", "has-session", "-t", "=" + self.session(service)], check=False)
        if result.returncode not in (0, 1):
            raise EnvironmentError("Cannot inspect inference tmux sessions")
        return result.returncode == 0

    def snapshot(self) -> list[dict]:
        profiles = json.loads(self.profile_path.read_text()) if self.profile_path.exists() else {}
        result = []
        for service in SERVICES:
            if self.running(service):
                profile = profiles.get(service)
                if not profile:
                    raise EnvironmentError(f"Running {service} has no recorded profile")
                result.append({"service": service, "profile": profile})
        return result

    def blocking_gpu_processes(self, services):
        result = self.run(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"], timeout=5)
        remaining = set(result.stdout.split())
        if not remaining or not services:
            return remaining
        panes = set()
        for service in services:
            # All supported inference launchers run in the managed tmux session.
            result = self.run(["tmux", "list-panes", "-s", "-t", "=" + self.session(service),
                               "-F", "#{pane_pid}"], check=False, timeout=5)
            if result.returncode == 0:
                panes.update(result.stdout.split())
        parents = dict(line.split() for line in self.run(["ps", "-eo", "pid=,ppid="], timeout=5).stdout.splitlines())
        for pid in tuple(remaining):
            ancestor = pid
            seen = set()
            while ancestor and ancestor not in seen:
                if ancestor in panes:
                    remaining.remove(pid)
                    break
                seen.add(ancestor)
                ancestor = parents.get(ancestor)
        return remaining

    def wait_gpu_release(self, services=()):
        deadline = time.monotonic() + int(os.environ.get("ELIZA_GPU_RELEASE_TIMEOUT_SECONDS", "15"))
        while remaining := self.blocking_gpu_processes(services):
            if time.monotonic() >= deadline:
                raise EnvironmentError("GPU compute processes remain; environment switch is blocked: " +
                                       ", ".join(sorted(remaining)))
            time.sleep(0.5)

    def wait_inference_ready(self, service, profile):
        deadline = time.monotonic() + int(os.environ.get("ELIZA_INFERENCE_READY_TIMEOUT_SECONDS", "150"))
        command = [str(self.root / "scripts/smoke-test"), service, "--profile", profile]
        while True:
            if not self.running(service):
                raise EnvironmentError(f"{service} ({profile}) exited during restore; inspect ./scripts/logs {service}")
            try:
                result = self.run(command, check=False, timeout=min(30, max(1, deadline - time.monotonic())))
                if result.returncode == 0:
                    return
                detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            except subprocess.TimeoutExpired:
                detail = "smoke test timed out"
            if time.monotonic() >= deadline:
                raise EnvironmentError(f"{service} ({profile}) did not become ready: {detail}")
            time.sleep(min(2, max(0, deadline - time.monotonic())))

    def partition_state(self, state: str):
        self.run(["scontrol", "update", f"PartitionName={self.partition}", f"State={state}"], admin=True)

    def guard_start(self, command: list[str]) -> int:
        with self.lock():
            if self.state()["phase"] != "inference":
                raise EnvironmentBusy("Inference starts are blocked outside inference mode")
            # Handles an out-of-band/manual scheduler start too.
            if os.environ.get("ELIZA_TRAINING_ENABLED", "false").lower() == "true":
                if any(self.unit_active(unit) for unit in self.units):
                    raise EnvironmentBusy("Slurm services must be stopped before inference starts")
            result = self.run(command, check=False)
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            return result.returncode

    def switch(self, target: str) -> dict:
        with self.lock():
            state = self.state()
            if target == "training" and os.environ.get("ELIZA_TRAINING_ENABLED", "false").lower() != "true":
                raise EnvironmentError("Configure Slurm and set ELIZA_TRAINING_ENABLED=true before training")
            if state["phase"] == target:
                self.verify(target)
                return state
            if target == "training" and state["phase"] == "inference":
                # Preflight before touching a running inference stack.
                for unit in self.units:
                    loaded = self.run(["systemctl", "show", unit, "--property=LoadState", "--value"]).stdout.strip()
                    if loaded != "loaded":
                        raise EnvironmentError(f"Missing Slurm service: {unit}")
                    if self.unit_active(unit):
                        raise EnvironmentError("Scheduler already running outside training mode")
                state["restore"] = self.snapshot()
            state.update(phase="switching_to_" + target, target=target)
            state.pop("error", None)
            self.save(state)
            try:
                if target == "training":
                    self.enter_training(state)
                else:
                    self.enter_inference(state)
                state.update(phase=target)
                self.save(state)
                return state
            except EnvironmentBusy:
                # A busy scheduler remains in training mode with its submissions restored.
                state.update(phase="training", target="training")
                self.save(state)
                raise
            except Exception as exc:
                state.update(phase="failed", error=str(exc))
                self.save(state)
                raise

    def training_token(self) -> dict:
        with self.lock():
            if self.state()["phase"] != "training":
                raise EnvironmentBusy("Training credentials are available only in training mode")
            self.verify("training")
            user = os.environ.get("ELIZA_SLURM_USER", "eliza-slurm")
            lifespan = int(os.environ.get("ELIZA_SLURM_TOKEN_LIFESPAN", "3600"))
            if not user or not 300 <= lifespan <= 86400:
                raise EnvironmentError("Invalid configured training identity or token lifespan")
            if pwd.getpwnam(user).pw_uid == 0:
                raise EnvironmentError("Training credentials cannot delegate a root identity")
            output = self.run(["scontrol", "token", "username=" + user, "lifespan=" + str(lifespan)], admin=True).stdout.strip()
            if not output.startswith("SLURM_JWT=") or "\n" in output:
                raise EnvironmentError("Slurm did not return the expected credential format")
            return {"user_name": user, "token": output.removeprefix("SLURM_JWT="),
                    "expires_at": int(time.time()) + lifespan}

    def advertise(self):
        path = Path(os.environ.get("ELIZA_SLURM_HOST_CONFIG", "/etc/eliza-slurm/host.json"))
        host = json.loads(path.read_text())
        state = self.state()
        ready, error = False, None
        if state["phase"] == "training":
            try:
                self.verify("training")
                ready = True
            except Exception as exc:
                error = str(exc)
        return {"version": 1, "rest_url": host["rest_url"], "api_versions": host["api_versions"],
                "partitions": host["partitions"], "workspace": host["workspace"], "job_user": host["job_user"],
                "mode": state["phase"], "ready": ready, "error": error}

    def enter_training(self, state: dict):
        for service in reversed(SERVICES):
            unit = self.session(service) + ".service"
            if self.unit_active(unit, user=True):
                self.run(["systemctl", "--user", "stop", unit])
            if self.running(service):
                self.run([str(self.root / "scripts/stop"), service])
        if any(self.running(service) for service in SERVICES):
            raise EnvironmentError("Inference sessions remain after shutdown")
        self.wait_gpu_release()
        for unit in self.units[:-1]:
            self.run(["systemctl", "start", unit], admin=True)
        self.partition_state("UP")
        self.wait_training(rest=False)
        # Open submission only once the compute node is ready.
        self.run(["systemctl", "start", self.units[-1]], admin=True)
        self.wait_training()

    def wait_training(self, *, rest: bool = True):
        deadline = time.monotonic() + int(os.environ.get("ELIZA_SLURM_READY_TIMEOUT_SECONDS", "60"))
        while True:
            try:
                self.verify("training", rest=rest)
                return
            except EnvironmentError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)

    def rest_ready(self):
        url = os.environ.get("ELIZA_SLURM_REST_URL", "http://127.0.0.1:6820").rstrip("/")
        try:
            with urlopen(url + "/openapi/v3", timeout=5) as response:
                if response.status != 200:
                    raise EnvironmentError("Slurm REST listener is not ready")
        except HTTPError as exc:
            # JWT is issued after activation; an authentication challenge is ready.
            if exc.code not in (401, 403):
                raise EnvironmentError("Slurm REST listener is not ready") from exc
        except (URLError, TimeoutError) as exc:
            raise EnvironmentError("Slurm REST listener is not ready") from exc

    def enter_inference(self, state: dict):
        controller = self.unit_active("slurmctld.service")
        if controller:
            # INACTIVE rejects submissions and stops scheduling, including local sbatch.
            self.partition_state("INACTIVE")
        self.run(["systemctl", "stop", "slurmrestd.service"], admin=True)
        if controller:
            jobs = self.run(["squeue", "--all", "--noheader", "--format=%i %T"]).stdout.strip()
            if jobs:
                self.partition_state("UP")
                self.run(["systemctl", "start", "slurmrestd.service"], admin=True)
                raise EnvironmentBusy("Training jobs remain; finish or explicitly cancel them first: " + jobs)
        for unit in reversed(self.units[:-1]):
            self.run(["systemctl", "stop", unit], admin=True)
        self.verify("inference")
        # A previous restore may have started a model before its smoke test passed.
        # Allow only GPU processes belonging to live sessions with saved profiles.
        profiles = {entry["service"]: entry["profile"] for entry in state["restore"]}
        live = self.snapshot()
        for entry in live:
            if profiles.get(entry["service"]) != entry["profile"]:
                raise EnvironmentError(f"Unexpected running inference profile for {entry['service']}: {entry['profile']}")
        running = {entry["service"] for entry in live}
        self.wait_gpu_release(running)
        for entry in state["restore"]:
            service, profile = entry["service"], entry["profile"]
            if service not in running or not self.running(service):
                self.run([str(self.root / "scripts/start"), service, "--profile", profile])
            self.wait_inference_ready(service, profile)

    def verify(self, mode: str, *, rest: bool = True):
        if mode == "inference":
            if any(self.unit_active(unit) for unit in self.units):
                raise EnvironmentError("Training services remain active")
            return
        required = self.units if rest else self.units[:-1]
        if not all(self.unit_active(unit) for unit in required):
            raise EnvironmentError("Training services are not all active")
        if rest:
            self.rest_ready()
        ping = self.run(["scontrol", "ping"]).stdout
        if "is UP" not in ping:
            raise EnvironmentError("Slurm controller is not ready: " + ping.strip())
        rows = self.run(["sinfo", "--all", "--noheader", "--nodes=" + self.node,
                         "--partition=" + self.partition, "--format=%a|%T|%E"]).stdout.strip().splitlines()
        if not rows:
            raise EnvironmentError(f"Slurm returned no matching node {self.node} in partition {self.partition}")
        for row in rows:
            fields = row.lower().split("|", 2)
            if len(fields) != 3 or fields[0] != "up" or fields[1] not in {"idle", "allocated", "mixed", "completing"}:
                raise EnvironmentError(f"Slurm node {self.node} is not ready in {self.partition} (availability|state|reason): {row}")
        if any(self.running(service) for service in SERVICES):
            raise EnvironmentError("Inference sessions are running in training mode")


def main() -> int:
    parser = argparse.ArgumentParser(description="Switch the DGX between inference and on-demand Slurm.")
    parser.add_argument("command", choices=("status", "advertise", "training", "inference", "token", "guard-start", "lock-held"))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    manager = EnvironmentManager(Path(__file__).resolve().parents[2])
    try:
        if args.command == "lock-held":
            if not manager.inherited_lock():
                return 1
            return 0 if manager.state()["phase"] in {"inference", "switching_to_inference"} else 1
        if args.command == "guard-start":
            return manager.guard_start(args.args[1:] if args.args[:1] == ["--"] else args.args)
        if args.command == "advertise":
            print(json.dumps(manager.advertise()))
        elif args.command == "token":
            print(json.dumps(manager.training_token()))
        elif args.command == "status":
            print(json.dumps(manager.state()))
        else:
            print(json.dumps(manager.switch(args.command)))
        return 0
    except EnvironmentBusy as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
