import subprocess
import pathlib
import logging
import time
from typing import Callable, List
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

class ExecutionError(Exception):
    """Raised when a command fails."""
    pass

class Executor:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = root_dir
        self._prepared_profiles: set[str] = set()
        self._prerequisites_ready = False

    def _run_command(self, command_args: list[str], cwd: pathlib.Path = None) -> subprocess.CompletedProcess:
        """Run a command in the root directory or a specific subdirectory."""
        target_cwd = cwd or self.root_dir
        try:
            # Use shell=False for security and better signal handling
            result = subprocess.run(
                command_args,
                cwd=target_cwd,
                capture_output=True,
                text=True,
                check=True
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {' '.join(command_args)}\nError: {e.stderr}")
            raise ExecutionError(f"Command '{' '.join(command_args)}' failed with exit code {e.returncode}: {e.stderr.strip()}")
        except Exception as e:
            logger.error(f"Unexpected error running command: {e}")
            raise ExecutionError(str(e))

    @staticmethod
    def _emit_progress(progress_callback: Callable[[str], None] | None, message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def _wait_for_health(
        self,
        health_url: str,
        timeout_seconds: int,
        progress_callback: Callable[[str], None] | None,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            request = Request(health_url, method="GET")
            try:
                with urlopen(request, timeout=1.5) as response:
                    if 200 <= response.status < 300:
                        self._emit_progress(progress_callback, "Ready")
                        return
            except (URLError, TimeoutError, ValueError):
                pass

            self._emit_progress(progress_callback, "Waiting for health")
            time.sleep(1.0)

        raise ExecutionError(f"Service did not become healthy within {timeout_seconds}s: {health_url}")

    def _profile_path(self, profile_id: str) -> pathlib.Path:
        profile_path = self.root_dir / "configs" / "profiles" / f"{profile_id}.env"
        if not profile_path.exists():
            raise ExecutionError(f"Profile not found: {profile_id}")
        return profile_path

    def _profile_backend(self, profile_id: str) -> str:
        backend = "llamacpp"
        profile_path = self._profile_path(profile_id)
        for line in profile_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            if key.strip() == "BACKEND":
                backend = value.strip().strip('"').strip("'")
                break
        return backend

    def _setup_commands_for(self, service_name: str, profile_id: str) -> List[list[str]]:
        commands: list[list[str]] = []

        if not self._prerequisites_ready:
            commands.append(["./scripts/setup", "prerequisites"])

        if service_name in {"eliza-small", "eliza-medium"}:
            backend = self._profile_backend(profile_id)
            if backend in {"llamacpp", "vllm", "sglang"}:
                commands.append(["./scripts/setup", backend])
        elif service_name == "stt":
            commands.append(["./scripts/setup", "stt", "--profile", profile_id])
        elif service_name == "tts":
            commands.append(["./scripts/setup", "tts", "--profile", profile_id])
        elif service_name == "vocode-bridge":
            commands.append(["./scripts/setup", "stt", "--profile", "stt/faster-whisper-small-cpu"])
            commands.append(["./scripts/setup", "tts", "--profile", "tts/piper-lessac"])
            commands.append(["./scripts/setup", "vocode"])

        return commands

    def ensure_service_ready(
        self,
        service_name: str,
        profile_id: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        prepared_key = f"{service_name}:{profile_id}"
        if prepared_key in self._prepared_profiles:
            self._emit_progress(progress_callback, "Setup already verified")
            return

        commands = self._setup_commands_for(service_name, profile_id)
        for command in commands:
            if command[:2] == ["./scripts/setup", "prerequisites"]:
                self._emit_progress(progress_callback, "Ensuring prerequisites")
            elif len(command) >= 2 and command[0:2] == ["./scripts/setup", "llamacpp"]:
                self._emit_progress(progress_callback, "Ensuring runtime (llamacpp)")
            elif len(command) >= 2 and command[0:2] == ["./scripts/setup", "sglang"]:
                self._emit_progress(progress_callback, "Ensuring runtime (sglang)")
            elif len(command) >= 2 and command[0:2] == ["./scripts/setup", "vllm"]:
                self._emit_progress(progress_callback, "Ensuring runtime (vllm)")
            elif len(command) >= 2 and command[0:2] == ["./scripts/setup", "stt"]:
                self._emit_progress(progress_callback, "Ensuring STT runtime")
            elif len(command) >= 2 and command[0:2] == ["./scripts/setup", "tts"]:
                self._emit_progress(progress_callback, "Ensuring TTS runtime")
            elif len(command) >= 2 and command[0:2] == ["./scripts/setup", "vocode"]:
                self._emit_progress(progress_callback, "Ensuring vocode bridge runtime")

            self._run_command(command)
            if command[:2] == ["./scripts/setup", "prerequisites"]:
                self._prerequisites_ready = True

        self._prepared_profiles.add(prepared_key)
        self._emit_progress(progress_callback, "Setup ready")

    def start_service(
        self,
        service_name: str,
        profile_id: str,
        health_url: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
        wait_for_health: bool = True,
        ready_timeout_seconds: int = 120,
    ) -> str:
        """Starts a service. Returns the log file path."""
        self.ensure_service_ready(service_name, profile_id, progress_callback=progress_callback)
        # Based on README: ./scripts/start <service> --profile <profile>
        self._emit_progress(progress_callback, "Launching tmux session")
        cmd = ["./scripts/start", service_name, "--profile", profile_id]
        self._run_command(cmd)
        if wait_for_health and health_url:
            self._wait_for_health(health_url, ready_timeout_seconds, progress_callback)
        
        # We need to figure out where the log goes. 
        # From common.sh: LOG_FILE="$LOG_DIR/$SERVICE.log"
        # From README: LOG_DIR="$PWD/logs"
        # But since we are running in a tmux session, it might be different.
        # However, the script prints it.
        # Let's return a placeholder or try to find it.
        return str(self.root_dir / "logs" / f"{service_name}.log")

    def stop_service(self, service_name: str) -> None:
        """Stops a service."""
        cmd = ["./scripts/stop", service_name]
        self._run_command(cmd)

    def restart_service(
        self,
        service_name: str,
        profile_id: str,
        health_url: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
        wait_for_health: bool = True,
        ready_timeout_seconds: int = 120,
    ) -> str:
        """Restarts a service with a potentially new profile."""
        self.ensure_service_ready(service_name, profile_id, progress_callback=progress_callback)
        self._emit_progress(progress_callback, "Stopping old session")
        cmd = ["./scripts/restart", service_name, "--profile", profile_id]
        self._run_command(cmd)
        self._emit_progress(progress_callback, "Launching tmux session")
        if wait_for_health and health_url:
            self._wait_for_health(health_url, ready_timeout_seconds, progress_callback)
        return str(self.root_dir / "logs" / f"{service_name}.log")

    def download_model(self, service_name: str, profile_id: str) -> str:
        """Downloads artifacts for a service/profile and returns command output."""
        cmd = ["./scripts/download-models", service_name, "--profile", profile_id]
        result = self._run_command(cmd)
        return (result.stdout or "").strip()
