from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static
from textual.containers import Container
from core.discovery import DiscoveryEngine
from .widgets import ServiceTable, ProfileList
import pathlib

class ElizaTUI(App):
    """The main Eliza TUI Application."""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #main-container {
        height: 1fr;
    }
    
    .status-bar {
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("f1", "switch_services", "Services"),
        ("f2", "switch_profiles", "Profiles"),
    ]

    def __init__(self, root_dir: pathlib.Path):
        super().__init__()
        self.root_dir = root_dir
        self.engine = DiscoveryEngine(root_dir)
        self.stack = self.engine.discover()

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with TabbedContent():
                with TabPane("Services", id="services_tab"):
                    yield ServiceTable(id="service_table")
                with TabPane("Profiles", id="profiles_tab"):
                    yield ProfileList(id="profile_list")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the widgets with data on startup."""
        service_table = self.query_one("#service_table", ServiceTable)
        service_table.update_data(list(self.stack.services.values()))

        profile_list = self.query_one("#profile_list", ProfileList)
        profile_list.update_data(list(self.stack.profiles.values()))

    def action_switch_services(self) -> None:
        self.query_one(TabbedContent).active = "services_tab"

    def action_switch_profiles(self) -> None:
        self.query_one(TabbedContent).active = "profiles_tab"

if __name__ == "__main__":
    import sys
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).parent.parent.parent.resolve()
    app = ElizaTUI(root)
    app.run()
