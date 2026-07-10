from dataclasses import replace
import pathlib

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import ListView
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from core.discovery import DiscoveryEngine
from core.executor import Executor
from core.monitor import MonitorEngine
from core.models import Profile

from .widgets.log_viewer import LogViewer
from .widgets import ProfileInspector, ProfileList, ProfileSelectDialog, ServiceTable

class ElizaTUI(App):
    """The main ElizaTUI Application."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f1", "switch_services", "Services"),
        Binding("f2", "switch_profiles", "Profiles"),
        Binding("f3", "switch_monitor", "Monitor"),
        Binding("s", "start_service", "Start"),
        Binding("k", "stop_service", "Stop"),
        Binding("r", "restart_service", "Restart"),
        Binding("p", "change_profile", "Profile"),
        Binding("l", "toggle_logs", "Logs"),
    ]

    def __init__(self, root_dir: pathlib.Path):
        super().__init__()
        self.root_dir = root_dir
        self.engine = DiscoveryEngine(root_dir)
        self.executor = Executor(root_dir)
        self.monitor = MonitorEngine(root_dir)
        self.stack = self.engine.discover()
        self.active_log_path = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with Horizontal():
                with TabbedContent():
                    with TabPane("Services", id="services_tab"):
                        yield ServiceTable(id="service_table")
                    with TabPane("Profiles", id="profiles_tab"):
                        yield ProfileList(id="profile_list")
                    with TabPane("Monitor", id="monitor_tab"):
                        yield Static(id="monitor_display")
                with ProfileInspector(id="profile_inspector"):
                    pass
        yield LogViewer(pathlib.Path("/dev/null"), id="log_viewer")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the widgets with data on startup."""
        self._refresh_service_table()
        self.query_one("#profile_list", ProfileList).update_data(list(self.stack.profiles.values()))
        self.query_one("#service_table").focus()
        self.set_interval(3, self.refresh_stack_state)
        self.set_interval(2, self.update_monitor)
        self.set_interval(1, self.update_logs)

    def _refresh_service_table(self) -> None:
        self.query_one("#service_table", ServiceTable).update_data(list(self.stack.services.values()))

    def refresh_stack_state(self) -> None:
        self.stack = self.engine.discover()
        self._refresh_service_table()

    def update_monitor(self) -> None:
        """Periodically update the monitor display."""
        stats = self.monitor.get_stats()
        display = (
            f"[bold cyan]CPU Usage:[/bold cyan] {stats.cpu_percent}%\n"
            f"[bold cyan]RAM Usage:[/bold cyan] {stats.memory_percent}%\n\n"
            f"[bold cyan]GPU:[/bold cyan] {stats.gpu_name}\n"
            f"  Used: {stats.gpu_memory_used:.0f} MiB\n"
            f"  Total: {stats.gpu_memory_total:.0f} MiB"
        )
        self.query_one("#monitor_display", Static).update(display)

    def update_logs(self) -> None:
        """Periodically update the log viewer if a file is attached."""
        if self.active_log_path:
            self.query_one("#log_viewer", LogViewer).update_logs()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle profile selection from ProfileList."""
        if event.control.id == "profile_list":
            sanitized_id = event.item.id
            for profile in self.stack.profiles.values():
                if profile.name.replace("/", "_") == sanitized_id:
                    self.query_one("#profile_inspector", ProfileInspector).update_profile(profile)
                    break

    def action_switch_services(self) -> None:
        self.query_one(TabbedContent).active = "services_tab"
        self.query_one("#service_table").focus()

    def action_switch_profiles(self) -> None:
        self.query_one(TabbedContent).active = "profiles_tab"
        self.query_one("#profile_list").focus()

    def action_switch_monitor(self) -> None:
        self.query_one(TabbedContent).active = "monitor_tab"

    def action_start_service(self) -> None:
        if self.query_one(TabbedContent).active != "services_tab":
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
        if self.query_one(TabbedContent).active != "services_tab":
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
        if self.query_one(TabbedContent).active != "services_tab":
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
        if self.query_one(TabbedContent).active != "services_tab":
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
        self.notify(f"Viewing logs: {log_path}", severity="information")

    def action_toggle_logs(self) -> None:
        log_viewer = self.query_one("#log_viewer", LogViewer)
        log_viewer.toggle_class("hidden")

if __name__ == "__main__":
    import sys
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).parent.parent.parent.resolve()
    app = ElizaTUI(root)
    app.run()
