import subprocess
import pathlib
import logging

logger = logging.getLogger(__name__)

class ExecutionError(Exception):
    """Raised when a command fails."""
    pass

class Executor:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = root_dir

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

    def start_service(self, service_name: str, profile_id: str) -> str:
        """Starts a service. Returns the log file path."""
        # Based on README: ./scripts/start <service> --profile <profile>
        cmd = ["./scripts/start", service_name, "--profile", profile_id]
        self._run_command(cmd)
        
        # We need to figure out where the log goes. 
        # From common.sh: LOG_FILE="$LOG_DIR/$SERVICE.log"
        # From README: LOG_DIR="$PWD/logs"
        # But since we are running in a tmux session, it might be different.
        # However, the script prints it.
        # Let's return a placeholder or try to find it.
        return f"logs/{service_name}.log"

    def stop_service(self, service_name: str) -> None:
        """Stops a service."""
        cmd = ["./scripts/stop", service_name]
        self._run_command(cmd)

    def restart_service(self, service_name: str, profile_id: str) -> str:
        """Restarts a service with a potentially new profile."""
        cmd = ["./scripts/restart", service_name, "--profile", profile_id]
        self._run_command(cmd)
        return f"logs/{service_name}.log"
