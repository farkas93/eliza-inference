import pathlib
from textual.widgets import RichLog

class LogViewer(RichLog):
    """A widget that displays streaming logs from a file."""

    def __init__(self, log_file_path: pathlib.Path, **kwargs):
        super().__init__(**kwargs)
        self.log_file_path = log_file_path
        self._last_position = 0
        if hasattr(self, "auto_scroll"):
            self.auto_scroll = False

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
            scroll_y_before = self.scroll_y
            should_follow = (self.max_scroll_y - self.scroll_y) <= 1

            with open(self.log_file_path, "r") as f:
                f.seek(self._last_position)
                new_lines = f.readlines()
                self._last_position = f.tell()

                if new_lines:
                    for line in new_lines:
                        try:
                            self.write(line.strip(), scroll_end=False)
                        except TypeError:
                            self.write(line.strip())

            if new_lines:
                if should_follow:
                    self.scroll_end(animate=False)
                else:
                    self.scroll_to(y=scroll_y_before, animate=False, immediate=True)
        except Exception as e:
            self.write(f"[red]Error reading logs: {e}[/red]")
