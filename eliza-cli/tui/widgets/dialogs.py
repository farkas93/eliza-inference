from typing import Callable, List

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView

from core.models import Profile

class ProfileSelectDialog(ModalScreen):
    """A modal dialog for selecting a profile."""

    def __init__(self, service_name: str, profiles: List[Profile], on_select: Callable[[Profile], None]):
        super().__init__()
        self.service_name = service_name
        self.profiles = profiles
        self.on_select = on_select
        self._profile_by_item_id: dict[str, Profile] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-container"):
            yield Label(f"Select profile for {self.service_name}:")
            with ListView(id="profile-list"):
                for index, profile in enumerate(self.profiles):
                    item_id = f"profile_{index}"
                    self._profile_by_item_id[item_id] = profile
                    yield ListItem(Label(profile.name), id=item_id)
            yield Button("Cancel", variant="error", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel_btn":
            self.dismiss()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is None or event.item.id is None:
            return

        selected_profile = self._profile_by_item_id.get(event.item.id)
        if selected_profile is None:
            return

        self.on_select(selected_profile)
        self.dismiss()


class ConfirmDialog(ModalScreen[bool]):
    """A simple confirmation modal."""

    def __init__(self, title: str, message: str):
        super().__init__()
        self.title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"[bold]{self.title}[/bold]")
            yield Label(self.message)
            yield Button("Confirm", variant="success", id="confirm_btn")
            yield Button("Cancel", variant="error", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm_btn":
            self.dismiss(True)
        elif event.button.id == "cancel_btn":
            self.dismiss(False)
