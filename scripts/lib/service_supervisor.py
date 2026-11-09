"""Supervise a model process inside its tmux session, independently of the TUI."""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import pathlib
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import urlopen


def load_status(path: pathlib.Path) -> dict:
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return status if isinstance(status, dict) else {}


def save_status(path: pathlib.Path, status: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(status, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)


def supervisor_matches(pid: int, state_path: pathlib.Path) -> bool:
    """Never signal an unrelated process just because a stale JSON file names it."""
    if pid <= 0:
        return False
    try:
        args = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().decode().split("\0")
        if "run" not in args:
            return False
        cwd = pathlib.Path(os.readlink(f"/proc/{pid}/cwd"))
        script = pathlib.Path(__file__).resolve()
        scripts = (pathlib.Path(arg) for arg in args[:args.index("run")] if arg and not arg.startswith("-"))
        if not any((candidate if candidate.is_absolute() else cwd / candidate).resolve() == script for candidate in scripts):
            return False
        raw_state = pathlib.Path(args[args.index("--state") + 1])
        if not raw_state.is_absolute():
            raw_state = cwd / raw_state
        return raw_state.resolve() == state_path.resolve()
    except (OSError, ValueError, UnicodeError, IndexError):
        return False


def stop_supervisor(state_path: pathlib.Path, timeout: float) -> bool:
    status = load_status(state_path)
    pid = status.get("supervisor_pid")
    if not isinstance(pid, int) or not supervisor_matches(pid, state_path):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + timeout
    while supervisor_matches(pid, state_path):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def restart_delay(failures: int, initial: float, maximum: float) -> float:
    # Bound the exponent even when a service has been retrying for weeks.
    return min(maximum, initial * 2 ** min(max(failures - 1, 0), 30))


def exit_description(code: int) -> str:
    if code < 0:
        try:
            return f"signal {signal.Signals(-code).name}"
        except ValueError:
            return f"signal {-code}"
    return f"exit code {code}"


class Supervisor:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.stopping = threading.Event()
        self.child: subprocess.Popen | None = None
        self.status = {
            "service": args.service,
            "profile": args.profile,
            "supervisor_pid": os.getpid(),
            "child_pid": None,
            "restart_count": 0,
            "last_exit_code": None,
            "next_restart_at": None,
        }

    def log(self, message: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            print(f"{timestamp} [supervisor:{self.args.service}] {message}", flush=True)
        except OSError:
            # tmux may close its logging pipe while a stop is being processed.
            pass

    def update(self, phase: str, **changes) -> None:
        self.status.update(changes, status=phase, updated_at=time.time())
        save_status(self.args.state, self.status)

    def request_stop(self, signum: int, _frame) -> None:
        self.stopping.set()

    def health_ready(self) -> bool:
        if not self.args.health_url:
            return True
        try:
            with urlopen(self.args.health_url, timeout=1.0) as response:
                return 200 <= response.status < 300
        except (URLError, OSError, ValueError):
            return False

    @staticmethod
    def group_alive(pid: int) -> bool:
        try:
            os.killpg(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def cleanup_child(self) -> None:
        child = self.child
        if child is None:
            return
        # The server's worker processes must be gone before another model loads.
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + self.args.shutdown_timeout
        while self.group_alive(child.pid) and time.monotonic() < deadline:
            child.poll()  # reap the group leader so a zombie cannot hold this loop
            time.sleep(0.05)
        if self.group_alive(child.pid):
            self.log("forcing remaining model workers to stop")
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        child.wait()
        self.child = None

    def run(self) -> int:
        previous_handlers = {}
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            previous_handlers[signum] = signal.signal(signum, self.request_stop)
        failures = 0
        try:
            while not self.stopping.is_set():
                self.log(f"launching {self.args.profile} (restart {self.status['restart_count']})")
                try:
                    self.child = subprocess.Popen(self.args.command, start_new_session=True)
                except OSError as exc:
                    self.log(f"cannot launch model: {exc}")
                    self.update("failed", error=str(exc), child_pid=None)
                    return 1
                self.update("starting", child_pid=self.child.pid, next_restart_at=None, error=None)
                ready_at = None
                next_probe = 0.0
                while self.child.poll() is None and not self.stopping.is_set():
                    now = time.monotonic()
                    if ready_at is None and now >= next_probe:
                        if self.health_ready() and self.child.poll() is None:
                            ready_at = time.monotonic()
                            self.update("running")
                            self.log("model is healthy")
                        next_probe = time.monotonic() + 2.0
                    self.stopping.wait(0.2)

                if self.stopping.is_set():
                    break
                code = self.child.wait()
                description = exit_description(code)
                self.log(f"model exited: {description}")
                healthy_uptime = time.monotonic() - ready_at if ready_at is not None else 0.0
                if code not in (2, 64, 78):
                    self.status["restart_count"] += 1
                    self.update("recovering", last_exit_code=code, error=description)
                self.cleanup_child()
                if code in (2, 64, 78):
                    self.update("failed", last_exit_code=code, child_pid=None, error=description)
                    self.log("configuration failure; correct setup/artifacts and restart the service")
                    return code
                if ready_at is not None and healthy_uptime >= self.args.reset_after:
                    failures = 0
                failures += 1
                delay = restart_delay(failures, self.args.restart_delay, self.args.max_restart_delay)
                self.update("backoff", child_pid=None, last_exit_code=code,
                            next_restart_at=time.time() + delay, error=description)
                self.log(f"restarting in {delay:g}s")
                self.stopping.wait(delay)
            self.update("stopping", next_restart_at=None)
            self.log("intentional stop; automatic recovery cancelled")
            self.cleanup_child()
            self.update("stopped", child_pid=None)
            return 0
        finally:
            self.cleanup_child()
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


def positive_seconds(value: str) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("must be a finite number of seconds greater than zero")
    return seconds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run")
    run.add_argument("--state", type=pathlib.Path, required=True)
    run.add_argument("--service", required=True)
    run.add_argument("--profile", required=True)
    run.add_argument("--health-url", default="")
    run.add_argument("--restart-delay", type=positive_seconds, default=2.0)
    run.add_argument("--max-restart-delay", type=positive_seconds, default=60.0)
    run.add_argument("--reset-after", type=positive_seconds, default=300.0)
    run.add_argument("--shutdown-timeout", type=positive_seconds, default=10.0)
    run.add_argument("command", nargs=argparse.REMAINDER)
    stop = commands.add_parser("stop")
    stop.add_argument("--state", type=pathlib.Path, required=True)
    stop.add_argument("--timeout", type=positive_seconds, default=30.0)
    status = commands.add_parser("status")
    status.add_argument("--state", type=pathlib.Path, required=True)
    status.add_argument("--json", action="store_true")
    status.add_argument("--field", choices=("status", "restart_count", "last_exit_code"))
    args = parser.parse_args()
    if args.action == "stop":
        if stop_supervisor(args.state, args.timeout):
            return 0
        print("Timed out stopping the model supervisor; check the service log", flush=True)
        return 1
    if args.action == "status":
        snapshot = load_status(args.state)
        if args.field:
            value = snapshot.get(args.field)
            if value is not None:
                print(value)
        elif args.json:
            print(json.dumps(snapshot))
        elif snapshot:
            print(f"supervisor: {snapshot.get('status', 'unknown')}, "
                  f"restarts={snapshot.get('restart_count', 0)}, "
                  f"last_exit={snapshot.get('last_exit_code')}, "
                  f"next_restart_at={snapshot.get('next_restart_at')}")
        return 0
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command:
        parser.error("run requires a command after --")
    args.state = args.state.resolve()
    args.state.parent.mkdir(parents=True, exist_ok=True)
    with args.state.with_suffix(".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A model supervisor already owns this service; stop it before switching profiles", flush=True)
            return 73
        return Supervisor(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
