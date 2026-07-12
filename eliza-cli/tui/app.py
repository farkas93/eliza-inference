from __future__ import annotations

from dataclasses import replace
import os
import pathlib
import queue
import re
import threading
import time

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.events import Resize
from textual.widgets import ListView
from textual.widgets import Input, Static, TabbedContent, TabPane

from core.discovery import DiscoveryEngine
from core.executor import Executor
from core.model_manager import ModelEntry, ModelManager, ProfileState
from core.monitor import MonitorEngine
from core.models import BackendRuntime, Profile

from .widgets import (
    BackendTable,
    ConfirmDialog,
    ModelTable,
    ProfileInspector,
    ProfileList,
    ProfileSelectDialog,
    ServiceTable,
)
from .widgets.log_viewer import LogViewer


class ElizaTUI(App):
    """The main ElizaTUI application."""

    SHOW_HEADER = False
    SHOW_FOOTER = False

    LOG_HEIGHT_DEFAULT = 12
    LOG_HEIGHT_MIN = 4
    LOG_HEIGHT_STEP = 1
    READY_TIMEOUT_SECONDS = 120

    SPINNER_FRAMES = ("|", "/", "-", "\\")

    CONTEXT_LIMIT_RE = re.compile(r"n_ctx_slot\s*=\s*(\d+)")
    CONTEXT_TOKENS_RE = re.compile(r"n_tokens\s*=\s*(\d+)")

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        layout: vertical;
        height: 1fr;
    }

    #top-bar {
        height: 1;
        padding: 0 1;
        background: $panel;
    }

    #top-title {
        width: 1fr;
        content-align: left middle;
    }

    #top-quit {
        width: auto;
        content-align: right middle;
    }

    #monitor-strip {
        height: 1;
        padding: 0 1;
        background: $boost;
        color: $text;
    }

    #activity-strip {
        height: 1;
        padding: 0 1;
        background: $surface;
        color: $text;
    }

    #content-row {
        height: 1fr;
    }

    #main-tabs {
        width: 2fr;
    }

    #models-pane {
        layout: vertical;
        height: 1fr;
    }

    #model_filter {
        height: 3;
    }

    #profile_inspector {
        width: 1fr;
        border: solid $surface;
        padding: 0 1;
    }

    #log_viewer {
        height: 12;
        border-top: solid $surface;
        display: none;
    }

    #context-legend {
        height: 1;
        padding: 0 1;
        background: $panel;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f1", "switch_services", "Services"),
        Binding("f2", "switch_profiles", "Profiles"),
        Binding("f3", "switch_models", "Models"),
        Binding("f4", "switch_backends", "Backends"),
        Binding("s", "start_service", "Start"),
        Binding("i", "setup_service", "Setup/Install"),
        Binding("k", "stop_service", "Stop"),
        Binding("r", "restart_service", "Restart"),
        Binding("p", "change_profile", "Swap Profile"),
        Binding("u", "update_backend", "Update Backend"),
        Binding("x", "uninstall_backend", "Uninstall Backend"),
        Binding("v", "verify_backends", "Verify Backends"),
        Binding("l", "toggle_logs", "Toggle Logs"),
        Binding("ctrl+up", "increase_log_height", "Logs Taller"),
        Binding("ctrl+down", "decrease_log_height", "Logs Shorter"),
        Binding("d", "delete_model", "Delete Model"),
        Binding("c", "cleanup_models", "Cleanup Orphans"),
        Binding("o", "cycle_model_sort", "Sort Models"),
        Binding("slash", "focus_model_filter", "Filter Models"),
    ]

    def __init__(self, root_dir: pathlib.Path):
        super().__init__()
        self.root_dir = root_dir
        self.engine = DiscoveryEngine(root_dir)
        self.executor = Executor(root_dir)
        self.monitor = MonitorEngine(root_dir)
        self.model_manager = ModelManager(root_dir)

        self.stack = self.engine.discover()
        self.profile_states: dict[str, ProfileState] = {}
        self.model_entries: list[ModelEntry] = []
        self.model_entries_by_path: dict[str, ModelEntry] = {}
        self.backends: list[BackendRuntime] = []
        self.backends_by_name: dict[str, BackendRuntime] = {}
        self.model_filter_text = ""
        self.model_sort_mode = "size_desc"

        self.active_log_path: pathlib.Path | None = None
        self.logs_visible = False
        self.log_viewer_height = self.LOG_HEIGHT_DEFAULT
        self._service_snapshot: tuple[tuple[str, str, str, str, str, str, bool], ...] = ()
        self._profile_snapshot: tuple[tuple[str, bool, bool], ...] = ()
        self._model_inventory_snapshot: tuple[tuple[str, str, int, tuple[str, ...]], ...] = ()
        self._backend_snapshot: tuple[tuple[str, bool, str, str, str], ...] = ()
        self._refreshing_model_inventory = False
        self._events: queue.Queue[tuple[str, dict[str, str]]] = queue.Queue()
        self._operation_thread: threading.Thread | None = None
        self._operation_service_name: str | None = None
        self._operation_action: str | None = None
        self._activity_message = "Idle"
        self._activity_busy = False
        self._activity_started_at = 0.0
        self._activity_severity = "information"
        self._spinner_index = 0
        self._context_by_service: dict[str, tuple[int, int]] = {}
        self._last_warning = ""

    def compose(self) -> ComposeResult:
        with Container(id="main-container"):
            with Horizontal(id="top-bar"):
                yield Static("ELIZA Inference Control Center", id="top-title")
                yield Static("q Quit", id="top-quit")

            yield Static(id="monitor-strip")
            yield Static(id="activity-strip")

            with Horizontal(id="content-row"):
                with TabbedContent(id="main-tabs"):
                    with TabPane("F1 Services", id="services_tab"):
                        yield ServiceTable(id="service_table")
                    with TabPane("F2 Profiles", id="profiles_tab"):
                        yield ProfileList(id="profile_list")
                    with TabPane("F3 Models", id="models_tab"):
                        with Vertical(id="models-pane"):
                            yield Input(placeholder="Filter models by name/path/profile...", id="model_filter")
                            yield ModelTable(id="model_table")
                    with TabPane("F4 Backends", id="backends_tab"):
                        yield BackendTable(id="backend_table")

                with ProfileInspector(id="profile_inspector"):
                    pass

            yield LogViewer(pathlib.Path("/dev/null"), id="log_viewer")
            yield Static(id="context-legend")

    def on_mount(self) -> None:
        self.refresh_stack_state(force=True)
        self.refresh_backends(force=True)

        self.query_one("#service_table").focus()
        self._set_profile_inspector_visible(False)
        self._apply_log_height()
        self._set_logs_visible(False)
        self._update_context_legend()
        self.update_monitor()
        self._render_activity_strip()

        self.set_interval(3, self.refresh_stack_state)
        self.set_interval(2, self.update_monitor)
        self.set_interval(1, self.update_logs)
        self.set_interval(0.25, self._process_events)

    def _active_tab(self) -> str:
        return self.query_one("#main-tabs", TabbedContent).active or "services_tab"

    def _selected_backend_name(self) -> str | None:
        backend_name = self.query_one("#backend_table", BackendTable).get_selected_backend_name()
        return backend_name or None

    def _set_logs_visible(self, visible: bool) -> None:
        self.logs_visible = visible
        log_viewer = self.query_one("#log_viewer", LogViewer)
        self._apply_log_height()
        log_viewer.styles.display = "block" if visible else "none"
        self._update_context_legend()

    def _max_log_height(self) -> int:
        return max(self.LOG_HEIGHT_MIN, self.size.height - 8)

    def _clamp_log_height(self, height: int) -> int:
        return min(max(height, self.LOG_HEIGHT_MIN), self._max_log_height())

    def _apply_log_height(self) -> None:
        self.log_viewer_height = self._clamp_log_height(self.log_viewer_height)
        log_viewer = self.query_one("#log_viewer", LogViewer)
        log_viewer.styles.height = self.log_viewer_height

    def on_resize(self, _: Resize) -> None:
        clamped_height = self._clamp_log_height(self.log_viewer_height)
        if clamped_height != self.log_viewer_height:
            self.log_viewer_height = clamped_height
            self._apply_log_height()

    def _set_profile_inspector_visible(self, visible: bool) -> None:
        inspector = self.query_one("#profile_inspector", ProfileInspector)
        inspector.styles.display = "block" if visible else "none"

    def _update_side_summary(self, title: str, details: list[tuple[str, str]]) -> None:
        lines = [f"[bold cyan]{title}[/bold cyan]"]
        for key, value in details:
            lines.append(f"[bold]{key}:[/bold] {value}")
        self.query_one("#profile_inspector", ProfileInspector).update("\n".join(lines))

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        elapsed = max(0, int(seconds))
        minutes, sec = divmod(elapsed, 60)
        return f"{minutes:02d}:{sec:02d}"

    def _selected_service_name(self) -> str | None:
        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        return service_name or None

    @staticmethod
    def _human_tokens(token_count: int) -> str:
        if token_count >= 1000:
            return f"{token_count / 1000:.1f}k"
        return str(token_count)

    def _context_status_text(self, service_name: str | None) -> str:
        if not service_name:
            return ""
        context = self._context_by_service.get(service_name)
        if not context:
            return ""
        used, limit = context
        if limit <= 0:
            return ""
        return f"Ctx {self._human_tokens(used)} / {self._human_tokens(limit)}"

    def _set_activity(self, message: str, busy: bool, severity: str = "information") -> None:
        if busy and not self._activity_busy:
            self._activity_started_at = time.monotonic()
            self._spinner_index = 0
        self._activity_busy = busy
        self._activity_message = message
        self._activity_severity = severity
        self._render_activity_strip()

    def _render_activity_strip(self) -> None:
        spinner = "*"
        elapsed = ""
        if self._activity_busy:
            spinner = self.SPINNER_FRAMES[self._spinner_index % len(self.SPINNER_FRAMES)]
            elapsed = f" | {self._format_elapsed(time.monotonic() - self._activity_started_at)}"
            self._spinner_index += 1

        service_name = self._operation_service_name or self._selected_service_name()
        context_suffix = self._context_status_text(service_name)
        warning_suffix = self._last_warning

        suffix_parts = [part for part in (context_suffix, warning_suffix) if part]
        suffix = f" | {' | '.join(suffix_parts)}" if suffix_parts else ""

        if self._activity_busy:
            prefix = "RUN"
        elif self._activity_severity == "error":
            prefix = "ERR"
        elif self._activity_severity == "warning":
            prefix = "WARN"
        else:
            prefix = "OK"
        line = f"{prefix} {spinner} {self._activity_message}{elapsed}{suffix}"
        self.query_one("#activity-strip", Static).update(line)

    def _service_operation_active(self) -> bool:
        return self._operation_thread is not None and self._operation_thread.is_alive()

    def _enqueue_progress(self, action: str, service_name: str, message: str) -> None:
        self._events.put(
            (
                "progress",
                {
                    "action": action,
                    "service_name": service_name,
                    "message": message,
                },
            )
        )

    def _launch_service_operation(self, action: str, service_name: str, profile: str, health_url: str) -> None:
        if self._service_operation_active():
            self.notify("Another service operation is still running", severity="warning")
            return

        self._operation_service_name = service_name
        self._operation_action = action
        self._last_warning = ""
        self._set_activity(f"{service_name} {action}: queued", busy=True)

        def worker() -> None:
            try:
                progress_callback = lambda message: self._enqueue_progress(action, service_name, message)

                if action == "start":
                    log_path = self.executor.start_service(
                        service_name,
                        profile,
                        health_url=health_url,
                        progress_callback=progress_callback,
                        wait_for_health=True,
                        ready_timeout_seconds=self.READY_TIMEOUT_SECONDS,
                    )
                elif action == "restart":
                    log_path = self.executor.restart_service(
                        service_name,
                        profile,
                        health_url=health_url,
                        progress_callback=progress_callback,
                        wait_for_health=True,
                        ready_timeout_seconds=self.READY_TIMEOUT_SECONDS,
                    )
                elif action == "setup":
                    self.executor.ensure_service_ready(service_name, profile, progress_callback=progress_callback)
                    log_path = ""
                else:
                    raise RuntimeError(f"Unknown service action: {action}")

                self._events.put(
                    (
                        "success",
                        {
                            "action": action,
                            "service_name": service_name,
                            "profile": profile,
                            "log_path": log_path,
                        },
                    )
                )
            except Exception as exc:
                self._events.put(
                    (
                        "error",
                        {
                            "action": action,
                            "service_name": service_name,
                            "message": str(exc),
                        },
                    )
                )

        self._operation_thread = threading.Thread(target=worker, daemon=True)
        self._operation_thread.start()

    def _launch_backend_operation(self, action: str, backend_name: str) -> None:
        if self._service_operation_active():
            self.notify("Another operation is still running", severity="warning")
            return

        self._operation_service_name = backend_name
        self._operation_action = action
        self._last_warning = ""
        self._set_activity(f"{backend_name} {action}: queued", busy=True)

        def worker() -> None:
            try:
                progress_callback = lambda message: self._enqueue_progress(action, backend_name, message)
                if action == "install":
                    self.executor.install_backend(backend_name, progress_callback=progress_callback)
                elif action == "update":
                    self.executor.update_backend(backend_name, progress_callback=progress_callback)
                elif action == "uninstall":
                    self.executor.uninstall_backend(backend_name, progress_callback=progress_callback)
                else:
                    raise RuntimeError(f"Unknown backend action: {action}")

                self._events.put(
                    (
                        "success",
                        {
                            "kind": "backend",
                            "action": action,
                            "service_name": backend_name,
                            "log_path": "",
                        },
                    )
                )
            except Exception as exc:
                self._events.put(
                    (
                        "error",
                        {
                            "kind": "backend",
                            "action": action,
                            "service_name": backend_name,
                            "message": str(exc),
                        },
                    )
                )

        self._operation_thread = threading.Thread(target=worker, daemon=True)
        self._operation_thread.start()

    def _launch_model_download_operation(self, service_name: str, profile_name: str, before_size_bytes: int) -> None:
        if self._service_operation_active():
            self.notify("Another operation is still running", severity="warning")
            return

        self._operation_service_name = service_name
        self._operation_action = "download"
        self._last_warning = ""
        self._set_activity(f"{service_name} download: queued ({profile_name})", busy=True)

        def worker() -> None:
            try:
                self._enqueue_progress("download", service_name, f"Downloading model artifacts ({profile_name})")
                self.executor.download_model(service_name, profile_name)
                self._events.put(
                    (
                        "success",
                        {
                            "kind": "model_download",
                            "action": "download",
                            "service_name": service_name,
                            "profile": profile_name,
                            "before_size_bytes": str(before_size_bytes),
                            "log_path": "",
                        },
                    )
                )
            except Exception as exc:
                self._events.put(
                    (
                        "error",
                        {
                            "kind": "model_download",
                            "action": "download",
                            "service_name": service_name,
                            "profile": profile_name,
                            "message": str(exc),
                        },
                    )
                )

        self._operation_thread = threading.Thread(target=worker, daemon=True)
        self._operation_thread.start()

    def _process_events(self) -> None:
        handled = False
        while True:
            try:
                event_type, payload = self._events.get_nowait()
            except queue.Empty:
                break

            handled = True
            kind = payload.get("kind", "service")
            action = payload.get("action", "")
            service_name = payload.get("service_name", "")
            profile_name = payload.get("profile", "")
            if event_type == "progress":
                message = payload.get("message", "Working")
                self._set_activity(f"{service_name} {action}: {message}", busy=True)
            elif event_type == "success":
                log_path = payload.get("log_path", "")
                selected_profile: Profile | None = None
                if kind == "backend":
                    self.refresh_backends(force=True)
                    if action == "install":
                        self.notify(f"Installed backend {service_name}", severity="information")
                    elif action == "update":
                        self.notify(f"Updated backend {service_name}", severity="information")
                    elif action == "uninstall":
                        self.notify(f"Uninstalled backend {service_name}", severity="information")
                    self._update_backend_summary(service_name)
                elif kind == "model_download":
                    self.refresh_model_inventory()
                    state = self.profile_states.get(profile_name)
                    if state is None or not state.ready:
                        self.notify(
                            f"Artifacts still missing after download for {profile_name}",
                            severity="error",
                        )
                    else:
                        before_size = int(payload.get("before_size_bytes", "0") or "0")
                        after_size = self._paths_size(state.expected_paths)
                        delta = max(after_size - before_size, 0)
                        self.notify(
                            f"Download complete for {profile_name}: +{self._human_size(delta)} (total {self._human_size(after_size)})",
                            severity="information",
                        )
                        selected_profile = self.stack.profiles.get(profile_name)
                else:
                    self.refresh_stack_state(force=True)
                    if log_path:
                        self.attach_logs(log_path)
                    if action == "setup":
                        self.refresh_model_inventory()
                        self.notify(f"Setup complete for {service_name}", severity="information")
                    elif action == "start":
                        self.notify(f"Started {service_name}", severity="information")
                    elif action == "restart":
                        self.notify(f"Restarted {service_name}", severity="information")
                self._set_activity(f"{service_name} {action}: ready", busy=False, severity="information")
                self._operation_service_name = None
                self._operation_action = None
                self._operation_thread = None
                if selected_profile is not None:
                    self._apply_profile_selection(service_name, selected_profile)
            elif event_type == "error":
                message = payload.get("message", "unknown error")
                if kind == "model_download" and profile_name:
                    self.notify(f"Download failed for {profile_name}: {message}", severity="error")
                else:
                    self.notify(f"Failed to {action} {service_name}: {message}", severity="error")
                self._set_activity(f"{service_name} {action}: failed", busy=False, severity="error")
                self._operation_service_name = None
                self._operation_action = None
                self._operation_thread = None

        if not handled:
            self._render_activity_strip()

    def _selected_service_log_path(self) -> pathlib.Path | None:
        if self._active_tab() != "services_tab":
            return self.active_log_path

        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        if not service_name:
            return self.active_log_path
        return self.root_dir / "logs" / f"{service_name}.log"

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        value = float(size_bytes)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if value < 1024 or unit == "TiB":
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024
        return "0 B"

    def _paths_size(self, paths: tuple[str, ...]) -> int:
        total = 0
        seen: set[str] = set()
        for path_text in paths:
            if path_text in seen:
                continue
            seen.add(path_text)
            path = pathlib.Path(path_text)
            if not path.exists():
                continue
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
                continue

            for root, _, files in os.walk(path):
                for file_name in files:
                    file_path = pathlib.Path(root) / file_name
                    try:
                        total += file_path.stat().st_size
                    except OSError:
                        continue
        return total

    def _current_service_snapshot(self) -> tuple[tuple[str, str, str, str, str, str, bool], ...]:
        return tuple(
            (
                service.name,
                service.status,
                service.health,
                service.profile_id,
                service.live_profile_id or "-",
                service.live_model,
                service.drift,
            )
            for service in self.stack.services.values()
        )

    def _profile_markers(self) -> dict[str, str]:
        markers: dict[str, str] = {}
        for profile_name, state in self.profile_states.items():
            if state.deployed:
                markers[profile_name] = "[bold green]LIVE[/bold green]"
            elif state.ready:
                markers[profile_name] = "[bold yellow]RDY [/bold yellow]"
            else:
                markers[profile_name] = "[bold red]MISS[/bold red]"
        return markers

    @staticmethod
    def _profile_snapshot_from_states(states: dict[str, ProfileState]) -> tuple[tuple[str, bool, bool], ...]:
        return tuple(sorted((name, state.deployed, state.ready) for name, state in states.items()))

    @staticmethod
    def _model_snapshot_from_entries(
        entries: list[ModelEntry],
    ) -> tuple[tuple[str, str, int, tuple[str, ...]], ...]:
        return tuple(
            sorted((entry.path, entry.status, entry.size_bytes, entry.linked_profiles) for entry in entries)
        )

    @staticmethod
    def _backend_snapshot_from_entries(
        backends: list[BackendRuntime],
    ) -> tuple[tuple[str, bool, str, str, str], ...]:
        return tuple(sorted((backend.name, backend.installed, backend.version, backend.status, backend.location) for backend in backends))

    def _refresh_backend_table(self) -> None:
        backend_table = self.query_one("#backend_table", BackendTable)
        selected_backend_name = backend_table.get_selected_backend_name()
        selected_row_index = backend_table.cursor_row
        selected_column = backend_table.cursor_column if backend_table.cursor_column is not None else 0
        scroll_y = backend_table.scroll_y
        backend_table.update_data(
            self.backends,
            selected_backend_name=selected_backend_name,
            selected_row_index=selected_row_index,
            selected_column=selected_column,
        )
        backend_table.scroll_to(y=scroll_y, animate=False, immediate=True)
        self._backend_snapshot = self._backend_snapshot_from_entries(self.backends)

    def refresh_backends(self, force: bool = False) -> None:
        backends = self.executor.probe_backends()
        snapshot = self._backend_snapshot_from_entries(backends)
        if force or snapshot != self._backend_snapshot:
            self.backends = backends
            self.backends_by_name = {backend.name: backend for backend in backends}
            self._refresh_backend_table()
            if self._active_tab() == "backends_tab":
                self._update_backend_summary(self._selected_backend_name())

    def _refresh_profile_list(self) -> None:
        profiles = sorted(self.stack.profiles.values(), key=lambda profile: profile.name)
        profile_list = self.query_one("#profile_list", ProfileList)
        selected_profile_name = profile_list.get_selected_profile_name()
        selected_index = profile_list.index
        scroll_y = profile_list.scroll_y

        profile_list.update_data(profiles, self._profile_markers())
        profile_list.restore_selection(selected_profile_name, selected_index, scroll_y)

        if profiles:
            selected_profile_name = profile_list.get_selected_profile_name()
            selected_profile = None
            if selected_profile_name:
                selected_profile = self.stack.profiles.get(selected_profile_name)

            if selected_profile is None:
                selected_profile = profiles[0]

            if self._active_tab() == "profiles_tab":
                self.query_one("#profile_inspector", ProfileInspector).update_profile(selected_profile)

    def _sorted_filtered_model_entries(self) -> list[ModelEntry]:
        filtered = self.model_entries
        text = self.model_filter_text.strip().lower()
        if text:
            filtered = [
                entry
                for entry in self.model_entries
                if text in entry.name.lower()
                or text in entry.path.lower()
                or any(text in profile.lower() for profile in entry.linked_profiles)
                or text in entry.status.lower()
            ]

        if self.model_sort_mode == "size_desc":
            return sorted(filtered, key=lambda entry: entry.size_bytes, reverse=True)
        if self.model_sort_mode == "size_asc":
            return sorted(filtered, key=lambda entry: entry.size_bytes)
        if self.model_sort_mode == "name":
            return sorted(filtered, key=lambda entry: entry.name.lower())
        if self.model_sort_mode == "status":
            return sorted(filtered, key=lambda entry: (entry.status, entry.name.lower()))
        return filtered

    def _refresh_model_table(self) -> None:
        model_table = self.query_one("#model_table", ModelTable)
        selected_model_path = model_table.get_selected_model_path()
        selected_row_index = model_table.cursor_row
        selected_column = model_table.cursor_column if model_table.cursor_column is not None else 0
        scroll_y = model_table.scroll_y

        table_rows: list[dict[str, str]] = []
        for entry in self._sorted_filtered_model_entries():
            profiles = ", ".join(entry.linked_profiles) if entry.linked_profiles else "-"
            status = "LINKED" if entry.status == "linked" else "ORPHAN"
            table_rows.append(
                {
                    "name": entry.name,
                    "status": status,
                    "size": self._human_size(entry.size_bytes),
                    "path": entry.path,
                    "profiles": profiles,
                }
            )
        model_table.update_data(
            table_rows,
            selected_model_path=selected_model_path,
            selected_row_index=selected_row_index,
            selected_column=selected_column,
        )
        model_table.scroll_to(y=scroll_y, animate=False, immediate=True)

        if self._active_tab() == "models_tab":
            self._update_model_summary(model_table.get_selected_model_path())

    def _refresh_service_table(self) -> None:
        service_table = self.query_one("#service_table", ServiceTable)
        selected_service_name = service_table.get_selected_service_name()
        selected_column = service_table.cursor_column if service_table.cursor_column is not None else 0
        selected_row_index = service_table.cursor_row
        scroll_y = service_table.scroll_y
        service_table.update_data(
            list(self.stack.services.values()),
            selected_service_name=selected_service_name,
            selected_column=selected_column,
            selected_row_index=selected_row_index,
        )
        service_table.scroll_to(y=scroll_y, animate=False, immediate=True)
        self._service_snapshot = self._current_service_snapshot()

    def refresh_model_inventory(self) -> None:
        if self._refreshing_model_inventory:
            return

        self._refreshing_model_inventory = True
        try:
            profile_states = self.model_manager.build_profile_states(self.stack.profiles, self.stack.services)
            model_entries = self.model_manager.list_models(self.stack.profiles)

            new_profile_snapshot = self._profile_snapshot_from_states(profile_states)
            new_model_snapshot = self._model_snapshot_from_entries(model_entries)

            profiles_changed = new_profile_snapshot != self._profile_snapshot
            models_changed = new_model_snapshot != self._model_inventory_snapshot

            self.profile_states = profile_states
            self.model_entries = model_entries
            self.model_entries_by_path = {entry.path: entry for entry in self.model_entries}
            if profiles_changed:
                self._refresh_profile_list()
            if models_changed:
                self._refresh_model_table()

            self._profile_snapshot = new_profile_snapshot
            self._model_inventory_snapshot = new_model_snapshot
        finally:
            self._refreshing_model_inventory = False

    def refresh_stack_state(self, force: bool = False) -> None:
        self.stack = self.engine.discover()
        if force or self._current_service_snapshot() != self._service_snapshot:
            self._refresh_service_table()
        self.refresh_model_inventory()

    def _update_context_legend(self) -> None:
        logs_status = "ON" if self.logs_visible else "OFF"
        logs_size = str(self.log_viewer_height)
        tab = self._active_tab()
        if tab == "services_tab":
            legend = (
                "Services: i setup | s start | k stop | r restart | p swap profile "
                "| l logs ({}) | ctrl+up/down logs height ({}) | ctrl+c copy logs | activity strip shows live phases"
            ).format(logs_status, logs_size)
        elif tab == "profiles_tab":
            legend = (
                "Profiles: [LIVE]/[RDY]/[MISS] | arrows browse "
                "| l logs ({}) | ctrl+up/down logs height ({}) | ctrl+c copy logs"
            ).format(logs_status, logs_size)
        elif tab == "backends_tab":
            legend = (
                "Backends: i install | u update | x uninstall | v verify "
                "| l logs ({}) | ctrl+up/down logs height ({}) | ctrl+c copy logs"
            ).format(logs_status, logs_size)
        else:
            legend = (
                "Models: / filter | o sort({}) | d delete | c cleanup orphans "
                "| l logs ({}) | ctrl+up/down logs height ({}) | ctrl+c copy logs"
            ).format(self.model_sort_mode, logs_status, logs_size)
        self.query_one("#context-legend", Static).update(legend)

    def _update_profile_inspector_by_item_id(self, item_id: str | None) -> None:
        if not item_id:
            return
        profile_list = self.query_one("#profile_list", ProfileList)
        profile_name = profile_list.get_profile_name_by_item_id(item_id)
        if profile_name:
            profile = self.stack.profiles.get(profile_name)
            if profile is not None:
                self.query_one("#profile_inspector", ProfileInspector).update_profile(profile)
            return
        for profile in self.stack.profiles.values():
            if profile.name.replace("/", "_") == item_id:
                self.query_one("#profile_inspector", ProfileInspector).update_profile(profile)
                return

    def _update_model_summary(self, model_path: str | None) -> None:
        if not model_path:
            self._update_side_summary(
                "Model Summary",
                [
                    ("Name", "-"),
                    ("Status", "-"),
                    ("Size", "-"),
                    ("Path", "-"),
                    ("Linked Profiles", "-"),
                ],
            )
            return
        entry = self.model_entries_by_path.get(model_path)
        if entry is None:
            return
        profiles = ", ".join(entry.linked_profiles) if entry.linked_profiles else "-"
        details = [
            ("Name", entry.name),
            ("Status", entry.status.upper()),
            ("Size", self._human_size(entry.size_bytes)),
            ("Path", entry.path),
            ("Linked Profiles", profiles),
        ]
        self._update_side_summary("Model Summary", details)

    def _update_backend_summary(self, backend_name: str | None) -> None:
        if not backend_name:
            self._update_side_summary(
                "Backend Summary",
                [
                    ("Backend", "-"),
                    ("Installed", "-"),
                    ("Version", "-"),
                    ("Status", "-"),
                    ("Location", "-"),
                ],
            )
            return

        backend = self.backends_by_name.get(backend_name)
        if backend is None:
            return

        details = [
            ("Backend", backend.name),
            ("Installed", "YES" if backend.installed else "NO"),
            ("Version", backend.version),
            ("Status", backend.status),
            ("Location", backend.location),
        ]
        if backend.notes:
            details.append(("Notes", backend.notes))
        self._update_side_summary("Backend Summary", details)

    def update_monitor(self) -> None:
        stats = self.monitor.get_stats()
        if stats.gpu_name == "N/A" or stats.gpu_memory_total <= 0:
            gpu_text = "GPU0 N/A"
        else:
            gpu_text = f"GPU0 {stats.gpu_name} {stats.gpu_memory_used:.0f}/{stats.gpu_memory_total:.0f} MiB"

        disk_text = f"Disk {self._human_size(stats.disk_used_bytes)}/{self._human_size(stats.disk_total_bytes)} ({stats.disk_percent:.0f}%)"
        models_text = f"Models {self._human_size(stats.model_home_used_bytes)}"
        display = f"CPU {stats.cpu_percent:5.1f}% | RAM {stats.memory_percent:5.1f}% | {disk_text} | {models_text} | {gpu_text}"
        self.query_one("#monitor-strip", Static).update(display)

    def _active_log_service_name(self) -> str | None:
        if self.active_log_path is None:
            return None
        return self.active_log_path.stem

    def _consume_log_lines(self, lines: list[str]) -> None:
        service_name = self._active_log_service_name()
        if not service_name:
            return

        context_used = None
        context_limit = None

        for raw_line in lines:
            line = raw_line.strip()
            lower_line = line.lower()

            if "loading model" in lower_line and self._activity_busy and self._operation_service_name == service_name:
                self._set_activity(f"{service_name} {self._operation_action}: Loading model", busy=True)
            elif "llama_server: model loaded" in lower_line and self._activity_busy and self._operation_service_name == service_name:
                self._set_activity(f"{service_name} {self._operation_action}: Model loaded", busy=True)
            elif "llama_server: listening on" in lower_line and self._activity_busy and self._operation_service_name == service_name:
                self._set_activity(f"{service_name} {self._operation_action}: Waiting for health", busy=True)

            limit_match = self.CONTEXT_LIMIT_RE.search(line)
            if limit_match:
                context_limit = int(limit_match.group(1))

            token_match = self.CONTEXT_TOKENS_RE.search(line)
            if token_match:
                context_used = int(token_match.group(1))

            if "no_speech_detected" in lower_line or "empty transcript" in lower_line:
                warning_text = "No speech detected (empty STT transcript)"
                if self._last_warning != warning_text:
                    self._last_warning = warning_text
                    self.notify("No speech detected, try speaking louder or longer", severity="warning")
                    if not self._activity_busy:
                        self._set_activity("Voice turn completed with no speech", busy=False, severity="warning")

        if context_used is not None or context_limit is not None:
            current_used, current_limit = self._context_by_service.get(service_name, (0, 0))
            if context_used is None:
                context_used = current_used
            if context_limit is None:
                context_limit = current_limit
            self._context_by_service[service_name] = (context_used, context_limit)

    def update_logs(self) -> None:
        if self.logs_visible and self.active_log_path:
            new_lines = self.query_one("#log_viewer", LogViewer).update_logs()
            if new_lines:
                self._consume_log_lines(new_lines)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.control.id == "profile_list":
            self._update_profile_inspector_by_item_id(event.item.id)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.control.id == "profile_list" and event.item is not None:
            self._update_profile_inspector_by_item_id(event.item.id)

    def on_data_table_row_highlighted(self, event) -> None:
        if event.control.id == "model_table":
            model_path = self.query_one("#model_table", ModelTable).get_selected_model_path()
            self._update_model_summary(model_path)
        elif event.control.id == "backend_table":
            backend_name = self.query_one("#backend_table", BackendTable).get_selected_backend_name()
            self._update_backend_summary(backend_name)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "model_filter":
            return
        self.model_filter_text = event.value
        self._refresh_model_table()
        self._update_context_legend()

    def action_switch_services(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "services_tab"
        self.query_one("#service_table").focus()
        self._set_profile_inspector_visible(False)
        self._update_context_legend()

    def action_switch_profiles(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "profiles_tab"
        self.query_one("#profile_list").focus()
        self._set_profile_inspector_visible(True)
        self._update_context_legend()

    def action_switch_models(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "models_tab"
        self.query_one("#model_table").focus()
        self._set_profile_inspector_visible(True)
        selected_path = self.query_one("#model_table", ModelTable).get_selected_model_path()
        self._update_model_summary(selected_path)
        self._update_context_legend()

    def action_switch_backends(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "backends_tab"
        self.query_one("#backend_table").focus()
        self._set_profile_inspector_visible(True)
        self.refresh_backends(force=True)
        selected_backend = self.query_one("#backend_table", BackendTable).get_selected_backend_name()
        self._update_backend_summary(selected_backend)
        self._update_context_legend()

    def action_focus_model_filter(self) -> None:
        if self._active_tab() != "models_tab":
            return
        self.query_one("#model_filter", Input).focus()

    def action_cycle_model_sort(self) -> None:
        if self._active_tab() != "models_tab":
            return
        order = ["size_desc", "size_asc", "name", "status"]
        current_index = order.index(self.model_sort_mode)
        self.model_sort_mode = order[(current_index + 1) % len(order)]
        self._refresh_model_table()
        self._update_context_legend()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tab.id == "services_tab":
            self.query_one("#service_table").focus()
            self._set_profile_inspector_visible(False)
        elif event.tab.id == "profiles_tab":
            self.query_one("#profile_list").focus()
            self._set_profile_inspector_visible(True)
        elif event.tab.id == "models_tab":
            self.query_one("#model_table").focus()
            self._set_profile_inspector_visible(True)
            selected_path = self.query_one("#model_table", ModelTable).get_selected_model_path()
            self._update_model_summary(selected_path)
        elif event.tab.id == "backends_tab":
            self.query_one("#backend_table").focus()
            self._set_profile_inspector_visible(True)
            self.refresh_backends(force=True)
            selected_backend = self.query_one("#backend_table", BackendTable).get_selected_backend_name()
            self._update_backend_summary(selected_backend)
        self._update_context_legend()

    def action_start_service(self) -> None:
        if self._active_tab() != "services_tab":
            return

        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        if not service_name:
            self.notify("No service selected!", severity="error")
            return

        profile = self.stack.services[service_name].profile_id
        health_url = self.stack.services[service_name].health_url
        self.notify(f"Starting {service_name} with {profile}...", severity="information")
        self._launch_service_operation("start", service_name, profile, health_url)

    def action_setup_service(self) -> None:
        if self._active_tab() == "backends_tab":
            backend_name = self.query_one("#backend_table", BackendTable).get_selected_backend_name()
            if not backend_name:
                self.notify("No backend selected!", severity="error")
                return
            self.notify(f"Installing backend {backend_name}...", severity="information")
            self._launch_backend_operation("install", backend_name)
            return

        if self._active_tab() != "services_tab":
            return

        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        if not service_name:
            self.notify("No service selected!", severity="error")
            return

        profile = self.stack.services[service_name].profile_id
        health_url = self.stack.services[service_name].health_url
        self.notify(f"Running setup for {service_name} ({profile})...", severity="information")
        self._launch_service_operation("setup", service_name, profile, health_url)

    def action_stop_service(self) -> None:
        if self._active_tab() != "services_tab":
            return

        if self._service_operation_active():
            self.notify("Wait for the active operation to finish", severity="warning")
            return

        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        if not service_name:
            self.notify("No service selected!", severity="error")
            return

        self.notify(f"Stopping {service_name}...")
        try:
            self.executor.stop_service(service_name)
            self.refresh_stack_state(force=True)
            self.notify(f"Stopped {service_name}", severity="information")
            self._set_activity(f"{service_name} stopped", busy=False, severity="information")
        except Exception as exc:
            self.notify(f"Failed to stop {service_name}: {exc}", severity="error")

    def action_restart_service(self) -> None:
        if self._active_tab() != "services_tab":
            return

        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        if not service_name:
            self.notify("No service selected!", severity="error")
            return

        profile = self.stack.services[service_name].profile_id
        health_url = self.stack.services[service_name].health_url
        self.notify(f"Restarting {service_name} with {profile}...", severity="information")
        self._launch_service_operation("restart", service_name, profile, health_url)

    def action_change_profile(self) -> None:
        if self._active_tab() != "services_tab":
            return

        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        if not service_name:
            self.notify("No service selected!", severity="error")
            return

        profiles_for_service = sorted(
            [profile for profile in self.stack.profiles.values() if profile.service_name == service_name],
            key=lambda profile: profile.name,
        )
        if not profiles_for_service:
            self.notify(f"No profiles available for {service_name}", severity="error")
            return

        dialog = ProfileSelectDialog(
            service_name,
            profiles_for_service,
            lambda profile: self._prepare_profile_selection(service_name, profile),
        )
        self.push_screen(dialog)

    def _prepare_profile_selection(self, service_name: str, selected_profile: Profile) -> None:
        state = self.profile_states.get(selected_profile.name)
        if state is None or state.ready:
            self._apply_profile_selection(service_name, selected_profile)
            return

        estimated = "unknown" if state.estimated_download_size_bytes is None else self._human_size(state.estimated_download_size_bytes)
        message = (
            f"Profile {selected_profile.name} is not ready.\n"
            f"Model location: {state.model_location}\n"
            f"Estimated download size: {estimated}\n\n"
            "Download now and deploy when complete?"
        )
        dialog = ConfirmDialog("Model Missing", message)
        self.push_screen(
            dialog,
            callback=lambda confirmed: self._handle_missing_model_confirmation(
                bool(confirmed), service_name, selected_profile
            ),
        )

    def _handle_missing_model_confirmation(
        self,
        confirmed: bool,
        service_name: str,
        selected_profile: Profile,
    ) -> None:
        if not confirmed:
            self.notify("Deployment cancelled", severity="information")
            return

        self.notify(f"Downloading artifacts for {selected_profile.name}...")
        state = self.profile_states.get(selected_profile.name)
        if state is None:
            self.notify(f"Profile state missing for {selected_profile.name}", severity="error")
            return
        before_size = self._paths_size(state.expected_paths)
        self._launch_model_download_operation(service_name, selected_profile.name, before_size)

    def _apply_profile_selection(self, service_name: str, selected_profile: Profile) -> None:
        current_service = self.stack.services.get(service_name)
        if current_service is None:
            self.notify(f"Unknown service: {service_name}", severity="error")
            return

        if selected_profile.name == current_service.profile_id:
            self.notify(f"{service_name} already uses {selected_profile.name}", severity="information")
            return

        self.notify(f"Applying profile {selected_profile.name} to {service_name}...", severity="information")
        self.stack.services[service_name] = replace(current_service, profile_id=selected_profile.name)
        health_url = self.stack.services[service_name].health_url
        self._launch_service_operation("restart", service_name, selected_profile.name, health_url)

    def action_update_backend(self) -> None:
        if self._active_tab() != "backends_tab":
            return

        backend_name = self.query_one("#backend_table", BackendTable).get_selected_backend_name()
        if not backend_name:
            self.notify("No backend selected", severity="error")
            return

        self.notify(f"Updating backend {backend_name}...", severity="information")
        self._launch_backend_operation("update", backend_name)

    def action_uninstall_backend(self) -> None:
        if self._active_tab() != "backends_tab":
            return

        backend_name = self.query_one("#backend_table", BackendTable).get_selected_backend_name()
        if not backend_name:
            self.notify("No backend selected", severity="error")
            return

        dialog = ConfirmDialog(
            "Uninstall Backend",
            (
                f"Reset backend '{backend_name}' for reinstall?\n\n"
                "This removes runtime artifacts but keeps source checkout by default."
            ),
        )
        self.push_screen(
            dialog,
            callback=lambda confirmed: self._handle_backend_uninstall_confirmation(bool(confirmed), backend_name),
        )

    def _handle_backend_uninstall_confirmation(self, confirmed: bool, backend_name: str) -> None:
        if not confirmed:
            return
        self.notify(f"Uninstalling backend {backend_name}...", severity="information")
        self._launch_backend_operation("uninstall", backend_name)

    def action_verify_backends(self) -> None:
        if self._active_tab() != "backends_tab":
            return
        self.refresh_backends(force=True)
        self._update_backend_summary(self._selected_backend_name())
        self.notify("Backend statuses refreshed", severity="information")

    def action_delete_model(self) -> None:
        if self._active_tab() != "models_tab":
            return

        model_path = self.query_one("#model_table", ModelTable).get_selected_model_path()
        if not model_path:
            self.notify("No model selected", severity="error")
            return

        entry = self.model_entries_by_path.get(model_path)
        if entry is None:
            self.notify("Selected model no longer exists", severity="error")
            return

        if entry.linked_profiles:
            message = (
                f"Delete profile-linked files inside:\n{entry.path}\n\n"
                "Only files mapped by profiles will be removed."
            )
        else:
            message = f"Delete orphan model entry:\n{entry.path}\n\nThis removes the full path."

        dialog = ConfirmDialog("Delete Model", message)
        self.push_screen(dialog, callback=lambda confirmed: self._handle_delete_model(bool(confirmed), entry))

    def _handle_delete_model(self, confirmed: bool, entry: ModelEntry) -> None:
        if not confirmed:
            return

        if entry.linked_profiles:
            deleted_files, deleted_bytes = self.model_manager.delete_entry_profile_files_only(entry, self.profile_states)
            self.notify(
                f"Deleted {deleted_files} file(s), reclaimed {self._human_size(deleted_bytes)}",
                severity="information",
            )
        else:
            deleted_bytes = self.model_manager.delete_orphan_entry(entry)
            self.notify(f"Deleted orphan entry, reclaimed {self._human_size(deleted_bytes)}", severity="information")

        self.refresh_model_inventory()
        self._update_model_summary(None)

    def action_cleanup_models(self) -> None:
        if self._active_tab() != "models_tab":
            return

        orphan_entries = [entry for entry in self.model_entries if entry.status == "orphan"]
        if not orphan_entries:
            self.notify("No orphan model entries found", severity="information")
            return

        dialog = ConfirmDialog(
            "Cleanup Orphan Models",
            f"Delete {len(orphan_entries)} orphan entries under MODEL_HOME?",
        )
        self.push_screen(
            dialog,
            callback=lambda confirmed: self._handle_cleanup_models(bool(confirmed), orphan_entries),
        )

    def _handle_cleanup_models(self, confirmed: bool, orphan_entries: list[ModelEntry]) -> None:
        if not confirmed:
            return
        deleted_count, deleted_bytes = self.model_manager.cleanup_orphans(orphan_entries)
        self.notify(
            f"Removed {deleted_count} orphan entries, reclaimed {self._human_size(deleted_bytes)}",
            severity="information",
        )
        self.refresh_model_inventory()

    def attach_logs(self, log_path: str) -> None:
        self.active_log_path = pathlib.Path(log_path)
        self.query_one("#log_viewer", LogViewer).set_log_file(self.active_log_path)
        self._set_logs_visible(True)
        self.notify(f"Viewing logs: {log_path}", severity="information")

    def action_toggle_logs(self) -> None:
        if self.logs_visible:
            self._set_logs_visible(False)
            return

        selected_log_path = self._selected_service_log_path()
        if selected_log_path is not None:
            self.active_log_path = selected_log_path
            self.query_one("#log_viewer", LogViewer).set_log_file(selected_log_path)

        self._set_logs_visible(True)
        self.update_logs()

    def action_increase_log_height(self) -> None:
        self.log_viewer_height += self.LOG_HEIGHT_STEP
        self._apply_log_height()
        self._update_context_legend()

    def action_decrease_log_height(self) -> None:
        self.log_viewer_height -= self.LOG_HEIGHT_STEP
        self._apply_log_height()
        self._update_context_legend()


if __name__ == "__main__":
    import sys

    root = (
        pathlib.Path(sys.argv[1])
        if len(sys.argv) > 1
        else pathlib.Path(__file__).parent.parent.parent.resolve()
    )
    app = ElizaTUI(root)
    app.run()
