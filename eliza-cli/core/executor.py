import subprocess
import pathlib
import logging
import os
import shutil
import threading
import time
from typing import Callable, List
from urllib.error import URLError
from urllib.request import Request, urlopen

from .models import BackendRuntime

logger = logging.getLogger(__name__)

class ExecutionError(Exception):
    """Raised when a command fails."""
    pass

class Executor:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = root_dir
        self._prepared_profiles: set[str] = set()
        self._prerequisites_ready = False

    def _run_command(self, command_args: list[str], cwd: pathlib.Path = None, progress_callback: Callable[[str], None] | None = None) -> subprocess.CompletedProcess:
        """Run a command. When progress_callback is set, streams stdout/stderr lines."""
        target_cwd = cwd or self.root_dir
        if progress_callback is None:
            try:
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

        try:
            proc = subprocess.Popen(
                command_args,
                cwd=target_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []
            stop_heartbeat = threading.Event()

            def read_stream(stream, lines):
                for line in stream:
                    lines.append(line)
                    stripped = line.rstrip('\n')
                    if stripped:
                        progress_callback(stripped)

            def emit_heartbeat() -> None:
                start = time.monotonic()
                while not stop_heartbeat.wait(8.0):
                    elapsed = int(time.monotonic() - start)
                    progress_callback(f"Still running... ({elapsed}s)")

            t_out = threading.Thread(target=read_stream, args=(proc.stdout, stdout_lines), daemon=True)
            t_err = threading.Thread(target=read_stream, args=(proc.stderr, stderr_lines), daemon=True)
            t_heartbeat = threading.Thread(target=emit_heartbeat, daemon=True)
            t_out.start()
            t_err.start()
            t_heartbeat.start()
            t_out.join()
            t_err.join()
            stop_heartbeat.set()
            t_heartbeat.join()

            proc.wait()

            if proc.returncode != 0:
                stderr_text = ''.join(stderr_lines)
                logger.error(f"Command failed: {' '.join(command_args)}\nError: {stderr_text}")
                raise ExecutionError(f"Command '{' '.join(command_args)}' failed with exit code {proc.returncode}: {stderr_text.strip()}")

            return subprocess.CompletedProcess(
                args=command_args,
                returncode=proc.returncode,
                stdout=''.join(stdout_lines),
                stderr=''.join(stderr_lines),
            )
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

    def _load_env_values(self) -> dict[str, str]:
        env_values: dict[str, str] = {}
        env_path = self.root_dir / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                key, value = raw.split("=", 1)
                env_values[key.strip()] = value.strip().strip('"').strip("'")
        return env_values

    def _first_line_from_command(self, command_args: list[str], timeout_seconds: float = 4.0) -> str:
        try:
            result = subprocess.run(
                command_args,
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except Exception:
            return ""

        output = (result.stdout or "").strip() or (result.stderr or "").strip()
        if not output:
            return ""
        return output.splitlines()[0].strip()

    def _detect_llama_server_binary(self, env_values: dict[str, str]) -> pathlib.Path | None:
        llama_server_bin = env_values.get("LLAMA_SERVER_BIN", "llama-server")
        candidate = pathlib.Path(llama_server_bin).expanduser()
        if ("/" in llama_server_bin or llama_server_bin.startswith(".")) and candidate.exists() and os.access(candidate, os.X_OK):
            return candidate.resolve()

        resolved = shutil.which(llama_server_bin)
        if resolved:
            return pathlib.Path(resolved).resolve()

        fallback = shutil.which("llama-server")
        if fallback:
            return pathlib.Path(fallback).resolve()

        llama_cpp_dir = pathlib.Path(env_values.get("LLAMA_CPP_DIR", str(pathlib.Path.home() / "src" / "llama.cpp"))).expanduser()
        build_dir = pathlib.Path(env_values.get("LLAMA_CPP_BUILD_DIR", str(llama_cpp_dir / "build"))).expanduser()
        build_bin = (build_dir / "bin" / "llama-server").resolve()
        if build_bin.exists() and os.access(build_bin, os.X_OK):
            return build_bin

        return None

    def _probe_llamacpp(self, env_values: dict[str, str]) -> BackendRuntime:
        binary = self._detect_llama_server_binary(env_values)
        if binary is None:
            return BackendRuntime(
                name="llamacpp",
                installed=False,
                version="-",
                status="missing",
                location="llama-server not found",
                update_hint="Install to build CUDA binaries",
            )

        version = self._first_line_from_command([str(binary), "--version"]) or self._first_line_from_command([str(binary), "--help"])
        return BackendRuntime(
            name="llamacpp",
            installed=True,
            version=version or "detected",
            status="installed",
            location=str(binary),
            update_hint="Rebuild from latest source",
        )

    def _probe_sglang(self, env_values: dict[str, str]) -> BackendRuntime:
        eliza_venv_dir = pathlib.Path(env_values.get("ELIZA_VENV_DIR", str(self.root_dir / ".venvs"))).expanduser()
        sglang_venv = pathlib.Path(env_values.get("SGLANG_VENV", str(eliza_venv_dir / "sglang"))).expanduser()
        sglang_python = sglang_venv / "bin" / "python"
        sglang_cli = sglang_venv / "bin" / "sglang"

        cli_location = sglang_cli if sglang_cli.exists() else None
        if cli_location is None:
            resolved = shutil.which("sglang")
            if resolved:
                cli_location = pathlib.Path(resolved).resolve()

        if not sglang_python.exists() and cli_location is None:
            return BackendRuntime(
                name="sglang",
                installed=False,
                version="-",
                status="missing",
                location=str(sglang_venv),
                update_hint="Install SGLang runtime",
            )

        version = ""
        if sglang_python.exists():
            version = self._first_line_from_command(
                [
                    str(sglang_python),
                    "-c",
                    "import importlib.metadata as m; print(m.version('sglang'))",
                ]
            )
        if not version and cli_location is not None:
            version = self._first_line_from_command([str(cli_location), "--version"])

        status = "installed"
        notes = ""
        if not sglang_python.exists():
            status = "broken"
            notes = "SGLang venv missing python"

        return BackendRuntime(
            name="sglang",
            installed=True,
            version=version or "detected",
            status=status,
            location=str(cli_location or sglang_venv),
            update_hint="Upgrade package and dependencies",
            notes=notes,
        )

    def _probe_ds4(self, env_values: dict[str, str]) -> BackendRuntime:
        ds4_dir = pathlib.Path(env_values.get("DS4_DIR", str(pathlib.Path.home() / "src" / "ds4"))).expanduser()
        ds4_bin_setting = env_values.get("DS4_BIN", str(pathlib.Path.home() / ".local" / "bin" / "ds4"))
        ds4_bin = pathlib.Path(ds4_bin_setting).expanduser()

        binary = None
        if ds4_bin.exists() and os.access(ds4_bin, os.X_OK):
            binary = ds4_bin.resolve()
        else:
            resolved = shutil.which("ds4")
            if resolved:
                binary = pathlib.Path(resolved).resolve()
            elif (ds4_dir / "ds4").exists() and os.access(ds4_dir / "ds4", os.X_OK):
                binary = (ds4_dir / "ds4").resolve()

        if binary is None:
            return BackendRuntime(
                name="ds4",
                installed=False,
                version="-",
                status="missing",
                location=str(ds4_dir),
                update_hint="Install ds4 from source",
            )

        version = self._first_line_from_command([str(binary), "--version"]) or self._first_line_from_command([str(binary), "--help"])
        return BackendRuntime(
            name="ds4",
            installed=True,
            version=version or "detected",
            status="installed",
            location=str(binary),
            update_hint="Pull latest source and rebuild",
        )

    def probe_backends(self) -> List[BackendRuntime]:
        env_values = self._load_env_values()
        return [
            self._probe_llamacpp(env_values),
            self._probe_sglang(env_values),
            self._probe_ds4(env_values),
        ]

    def install_backend(
        self,
        backend_name: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        command_map = {
            "llamacpp": ["./scripts/setup", "llamacpp"],
            "sglang": ["./scripts/setup", "sglang"],
            "ds4": ["./scripts/setup", "ds4"],
        }
        command = command_map.get(backend_name)
        if command is None:
            raise ExecutionError(f"Unsupported backend: {backend_name}")

        self._emit_progress(progress_callback, "Running setup")
        self._run_command(command, progress_callback=progress_callback)
        self._emit_progress(progress_callback, "Ready")

    def update_backend(
        self,
        backend_name: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._emit_progress(progress_callback, "Applying latest update")
        self.install_backend(backend_name, progress_callback=progress_callback)

    def uninstall_backend(
        self,
        backend_name: str,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        command_map = {
            "llamacpp": ["./scripts/installation-suite/uninstall-llamacpp"],
            "sglang": ["./scripts/installation-suite/uninstall-sglang"],
            "ds4": ["./scripts/installation-suite/uninstall-ds4"],
        }
        command = command_map.get(backend_name)
        if command is None:
            raise ExecutionError(f"Unsupported backend: {backend_name}")

        self._emit_progress(progress_callback, "Removing installed runtime")
        self._run_command(command, progress_callback=progress_callback)
        self._emit_progress(progress_callback, "Removed")

    def _setup_commands_for(self, service_name: str, profile_id: str) -> List[list[str]]:
        commands: list[list[str]] = []

        if not self._prerequisites_ready:
            commands.append(["./scripts/setup", "prerequisites"])

        if service_name in {"eliza-small", "eliza-medium"}:
            backend = self._profile_backend(profile_id)
            if backend in {"llamacpp", "vllm", "sglang", "ds4"}:
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
            elif len(command) >= 2 and command[0:2] == ["./scripts/setup", "ds4"]:
                self._emit_progress(progress_callback, "Ensuring runtime (ds4)")
            elif len(command) >= 2 and command[0:2] == ["./scripts/setup", "stt"]:
                self._emit_progress(progress_callback, "Ensuring STT runtime")
            elif len(command) >= 2 and command[0:2] == ["./scripts/setup", "tts"]:
                self._emit_progress(progress_callback, "Ensuring TTS runtime")
            elif len(command) >= 2 and command[0:2] == ["./scripts/setup", "vocode"]:
                self._emit_progress(progress_callback, "Ensuring vocode bridge runtime")

            self._run_command(command, progress_callback=progress_callback)
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
        self._run_command(cmd, progress_callback=progress_callback)
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
        self._run_command(cmd, progress_callback=progress_callback)
        self._emit_progress(progress_callback, "Launching tmux session")
        if wait_for_health and health_url:
            self._wait_for_health(health_url, ready_timeout_seconds, progress_callback)
        return str(self.root_dir / "logs" / f"{service_name}.log")

    def download_model(self, service_name: str, profile_id: str, progress_callback: Callable[[str], None] | None = None) -> str:
        """Downloads artifacts for a service/profile and returns command output."""
        cmd = ["./scripts/download-models", service_name, "--profile", profile_id]
        result = self._run_command(cmd, progress_callback=progress_callback)
        return (result.stdout or "").strip()
