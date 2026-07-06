from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static
from textual.containers import Container, Horizontal
from textual.binding import Binding
from textual.widgets import ListView
from core.discovery import DiscoveryEngine
from core.executor import Executor
from .widgets import ServiceTable, ProfileList, ProfileInspector
import pathlib

class ElizaTUI(App):
    """The main ElizaTUI Application."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f1", "switch_services", "Services"),
        Binding("f2", "switch_profiles", "Profiles"),
        Binding("s", "start_service", "Start", show=False),
        Binding("k", "stop_service", "Stop", show=False),
        Binding("r", "restart_service", "Restart", show=False),
        Binding("p", "change_profile", "Profile", show=False),
    ]

    def __init__(self, root_dir: pathlib.Path):
        super().__init__()
        self.root_dir = root_dir
        self.engine = DiscoveryEngine(root_dir)
        self.executor = Executor(root_dir)
        self.stack = self.engine.discover()

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with Horizontal():
                with TabbedContent():
                    with TabPane("Services", id="services_tab"):
                        yield ServiceTable(id="service_table")
                    with TabPane("Profiles", id="profiles_tab"):
                        yield ProfileList(id="profile_list")
                with ProfileInspector(id="profile_inspector")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the widgets with data on startup."""
        self.query_one("#service_table", ServiceTable).update_data(list(self.stack.services.values()))
        self.query_one("#profile_list", ProfileList).update_data(list(self.stack.profiles.values()))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle profile selection from ProfileList."""
        if event.sub_path == "profile_list":
            sanitized_id = event.item.id
            for profile in self.stack.profiles.values():
                if profile.name.replace("/", "_") == sanitized_id:
                    self.query_one("#profile_inspector", ProfileInspector).update_profile(profile)
                    break

    def action_switch_services(self) -> None:
        self.query_one(TabbedContent).active = "services_tab"

    def action_switch_profiles(self) -> None:
        self.query_one(TabbedContent).active = "profiles_tab"

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
            self.executor.start_service(service_name, profile)
            self.notify(f"Started {service_name}", severity="information")
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
            self.executor.restart_service(service_name, profile)
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

        self.notify(f"Profile change requested for {service_name}. (Dialog not implemented)")

if __name__ == "__main__":
    import sys
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).parent.parent.parent.resolve()
    app = ElizaTUI(root)
    app.run()
