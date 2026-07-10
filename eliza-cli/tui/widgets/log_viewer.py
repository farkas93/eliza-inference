import pathlib
from textual.widgets import RichLog

class LogViewer(RichLog):
    """A widget that displays streaming logs from a file."""
    def __init__(self, log_file_path: pathlib.Path, **kwargs):
        super().__init__(**kwargs)
        self.log_file_path = log_file_path
        self._last_position = 0

    def set_log_file(self, log_file_path: pathlib.Path) -> None:
        """Sets a new log file and resets the reading position."""
        self.log_file_path = log_file_path
        self._last_position = 0
        self.clear()

    def update_logs(self) -> None:
        """Reads new lines from the log file and appends them to the widget."""
        if not self.log_file_path.exists():
            return

        try:
            with open(self.log_file_path, "r") as f:
                f.seek(self._last_position)
                new_lines = f.readlines()
                self._last_position = f.tell()

                if new_lines:
                    for line in new_lines:
                        self.write(line.strip())
        except Exception as e:
            self.write(f"[red]Error reading logs: {e}[/red]")
