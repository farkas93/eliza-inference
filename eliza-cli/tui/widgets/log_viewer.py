import pathlib
from textual.widgets import TextArea


class LogViewer(TextArea):
    """A widget that displays streaming logs from a file."""

    def __init__(self, log_file_path: pathlib.Path, **kwargs):
        super().__init__(
            "",
            read_only=True,
            soft_wrap=False,
            show_cursor=False,
            **kwargs,
        )
        self.log_file_path = log_file_path
        self._last_position = 0

    def set_log_file(self, log_file_path: pathlib.Path) -> None:
        """Sets a new log file and resets the reading position."""
        self.log_file_path = log_file_path
        self._last_position = 0
        self.clear()

    def update_logs(self) -> list[str]:
        """Reads new lines from the log file, appends them, and returns them."""
        if not self.log_file_path.exists():
            return []

        new_lines: list[str] = []

        try:
            scroll_y_before = self.scroll_y
            should_follow = (self.max_scroll_y - self.scroll_y) <= 1

            with open(self.log_file_path, "r") as f:
                f.seek(self._last_position)
                new_lines = f.readlines()
                self._last_position = f.tell()

                if new_lines:
                    new_text = "".join(new_lines)
                    self.insert(new_text, location=self.document.end)

            if new_lines:
                if should_follow:
                    self.scroll_end(animate=False)
                else:
                    self.scroll_to(y=scroll_y_before, animate=False, immediate=True)
        except Exception as e:
            self.insert(f"Error reading logs: {e}\n", location=self.document.end)
            return []

        return new_lines
