from dataclasses import replace
import pathlib

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import ListView
from textual.widgets import Static, TabbedContent, TabPane

from core.discovery import DiscoveryEngine
from core.executor import Executor
from core.monitor import MonitorEngine
from core.models import Profile

from .widgets.log_viewer import LogViewer
from .widgets import ProfileInspector, ProfileList, ProfileSelectDialog, ServiceTable

class ElizaTUI(App):
    """The main ElizaTUI Application."""

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

    #content-row {
        height: 1fr;
    }

    #main-tabs {
        width: 2fr;
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
        Binding("s", "start_service", "Start"),
        Binding("k", "stop_service", "Stop"),
        Binding("r", "restart_service", "Restart"),
        Binding("p", "change_profile", "Swap Profile"),
        Binding("l", "toggle_logs", "Toggle Logs"),
    ]

    def __init__(self, root_dir: pathlib.Path):
        super().__init__()
        self.root_dir = root_dir
        self.engine = DiscoveryEngine(root_dir)
        self.executor = Executor(root_dir)
        self.monitor = MonitorEngine(root_dir)
        self.stack = self.engine.discover()
        self.active_log_path = None
        self.logs_visible = False
        self._service_snapshot: tuple[tuple[str, str, str, str, str, str, bool], ...] = ()

    def compose(self) -> ComposeResult:
        with Container(id="main-container"):
            with Horizontal(id="top-bar"):
                yield Static("Eliza TUI", id="top-title")
                yield Static("q Quit", id="top-quit")
            yield Static(id="monitor-strip")
            with Horizontal(id="content-row"):
                with TabbedContent(id="main-tabs"):
                    with TabPane("F1 Services", id="services_tab"):
                        yield ServiceTable(id="service_table")
                    with TabPane("F2 Profiles", id="profiles_tab"):
                        yield ProfileList(id="profile_list")
                with ProfileInspector(id="profile_inspector"):
                    pass
            yield LogViewer(pathlib.Path("/dev/null"), id="log_viewer")
            yield Static(id="context-legend")

    def on_mount(self) -> None:
        """Initialize the widgets with data on startup."""
        self._refresh_service_table()
        profiles = list(self.stack.profiles.values())
        self.query_one("#profile_list", ProfileList).update_data(profiles)
        if profiles:
            self.query_one("#profile_inspector", ProfileInspector).update_profile(profiles[0])
        self.query_one("#service_table").focus()
        self._set_logs_visible(False)
        self._update_context_legend()
        self.update_monitor()
        self.set_interval(3, self.refresh_stack_state)
        self.set_interval(2, self.update_monitor)
        self.set_interval(1, self.update_logs)

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

    def _active_tab(self) -> str:
        return self.query_one("#main-tabs", TabbedContent).active or "services_tab"

    def _update_context_legend(self) -> None:
        logs_status = "ON" if self.logs_visible else "OFF"
        if self._active_tab() == "services_tab":
            legend = "Services: s start | k stop | r restart | p swap profile | l logs ({})".format(logs_status)
        else:
            legend = "Profiles: arrows browse | enter select | l logs ({})".format(logs_status)
        self.query_one("#context-legend", Static).update(legend)

    def _update_profile_inspector_by_item_id(self, item_id: str | None) -> None:
        if not item_id:
            return
        for profile in self.stack.profiles.values():
            if profile.name.replace("/", "_") == item_id:
                self.query_one("#profile_inspector", ProfileInspector).update_profile(profile)
                return

    def _set_logs_visible(self, visible: bool) -> None:
        self.logs_visible = visible
        log_viewer = self.query_one("#log_viewer", LogViewer)
        log_viewer.styles.display = "block" if visible else "none"
        self._update_context_legend()

    def refresh_stack_state(self) -> None:
        self.stack = self.engine.discover()
        if self._current_service_snapshot() != self._service_snapshot:
            self._refresh_service_table()

    def update_monitor(self) -> None:
        """Periodically update the monitor display."""
        stats = self.monitor.get_stats()
        if stats.gpu_name == "N/A" or stats.gpu_memory_total <= 0:
            gpu_text = "GPU0 N/A"
        else:
            gpu_text = f"GPU0 {stats.gpu_name} {stats.gpu_memory_used:.0f}/{stats.gpu_memory_total:.0f} MiB"
        display = f"CPU {stats.cpu_percent:5.1f}% | RAM {stats.memory_percent:5.1f}% | {gpu_text}"
        self.query_one("#monitor-strip", Static).update(display)

    def update_logs(self) -> None:
        """Periodically update the log viewer if a file is attached."""
        if self.logs_visible and self.active_log_path:
            self.query_one("#log_viewer", LogViewer).update_logs()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle profile selection from ProfileList."""
        if event.control.id == "profile_list":
            self._update_profile_inspector_by_item_id(event.item.id)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.control.id == "profile_list" and event.item is not None:
            self._update_profile_inspector_by_item_id(event.item.id)

    def action_switch_services(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "services_tab"
        self.query_one("#service_table").focus()
        self._update_context_legend()

    def action_switch_profiles(self) -> None:
        self.query_one("#main-tabs", TabbedContent).active = "profiles_tab"
        self.query_one("#profile_list").focus()
        self._update_context_legend()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tab.id == "services_tab":
            self.query_one("#service_table").focus()
        elif event.tab.id == "profiles_tab":
            self.query_one("#profile_list").focus()
        self._update_context_legend()

    def action_start_service(self) -> None:
        if self._active_tab() != "services_tab":
            return
        
        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        if not service_name:
            self.notify("No service selected!", severity="error")
            return
            
        profile = self.stack.services[service_name].profile_id
        self.notify(f"Starting {service_name} with {profile}...")
        try:
            log_path = self.executor.start_service(service_name, profile)
            self.stack = self.engine.discover()
            self._refresh_service_table()
            self.notify(f"Started {service_name}", severity="information")
            self.attach_logs(log_path)
        except Exception as e:
            self.notify(f"Failed to start {service_name}: {e}", severity="error")

    def action_stop_service(self) -> None:
        if self._active_tab() != "services_tab":
            return
            
        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        if not service_name:
            self.notify("No service selected!", severity="error")
            return
            
        self.notify(f"Stopping {service_name}...")
        try:
            self.executor.stop_service(service_name)
            self.stack = self.engine.discover()
            self._refresh_service_table()
            self.notify(f"Stopped {service_name}", severity="information")
        except Exception as e:
            self.notify(f"Failed to stop {service_name}: {e}", severity="error")

    def action_restart_service(self) -> None:
        if self._active_tab() != "services_tab":
            return
            
        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        if not service_name:
            self.notify("No service selected!", severity="error")
            return
            
        profile = self.stack.services[service_name].profile_id
        self.notify(f"Restarting {service_name} with {profile}...")
        try:
            log_path = self.executor.restart_service(service_name, profile)
            self.stack = self.engine.discover()
            self._refresh_service_table()
            self.attach_logs(log_path)
            self.notify(f"Restarted {service_name}", severity="information")
        except Exception as e:
            self.notify(f"Failed to restart {service_name}: {e}", severity="error")

    def action_change_profile(self) -> None:
        if self._active_tab() != "services_tab":
            return

        service_name = self.query_one("#service_table", ServiceTable).get_selected_service_name()
        if not service_name:
            self.notify("No service selected!", severity="error")
            return

        profiles_for_service = sorted(
            [p for p in self.stack.profiles.values() if p.service_name == service_name],
            key=lambda profile: profile.name,
        )
        if not profiles_for_service:
            self.notify(f"No profiles available for {service_name}", severity="error")
            return

        dialog = ProfileSelectDialog(
            service_name,
            profiles_for_service,
            lambda profile: self._apply_profile_selection(service_name, profile),
        )
        self.push_screen(dialog)

    def _apply_profile_selection(self, service_name: str, selected_profile: Profile) -> None:
        current_service = self.stack.services.get(service_name)
        if current_service is None:
            self.notify(f"Unknown service: {service_name}", severity="error")
            return

        if selected_profile.name == current_service.profile_id:
            self.notify(
                f"{service_name} already uses {selected_profile.name}",
                severity="information",
            )
            return

        self.notify(
            f"Applying profile {selected_profile.name} to {service_name}...",
            severity="information",
        )
        try:
            log_path = self.executor.restart_service(service_name, selected_profile.name)
        except Exception as exc:
            self.notify(
                f"Failed to switch profile for {service_name}: {exc}",
                severity="error",
            )
            return

        self.stack.services[service_name] = replace(
            current_service,
            profile_id=selected_profile.name,
        )
        self.stack = self.engine.discover()
        self._refresh_service_table()
        self.attach_logs(log_path)
        self.notify(
            f"{service_name} now uses {selected_profile.name}",
            severity="information",
        )

    def attach_logs(self, log_path: str) -> None:
        self.active_log_path = pathlib.Path(log_path)
        self.query_one("#log_viewer", LogViewer).set_log_file(self.active_log_path)
        self._set_logs_visible(True)
        self.notify(f"Viewing logs: {log_path}", severity="information")

    def action_toggle_logs(self) -> None:
        self._set_logs_visible(not self.logs_visible)

if __name__ == "__main__":
    import sys
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).parent.parent.parent.resolve()
    app = ElizaTUI(root)
    app.run()
