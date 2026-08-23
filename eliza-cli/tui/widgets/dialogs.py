from typing import List

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView

from core.models import Profile

class ProfileSelectDialog(ModalScreen[Profile | None]):
    """A modal dialog for selecting a profile."""

    def __init__(
        self,
        service_name: str,
        profiles: List[Profile],
        profile_labels: dict[str, str] | None = None,
    ):
        super().__init__()
        self.service_name = service_name
        self.profiles = profiles
        self.profile_labels = profile_labels or {}
        self._profile_by_item_id: dict[str, Profile] = {}
        self._closed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-container"):
            yield Label(f"Select profile for {self.service_name}:")
            with ListView(id="profile-list"):
                for index, profile in enumerate(self.profiles):
                    item_id = f"profile_{index}"
                    self._profile_by_item_id[item_id] = profile
                    label = self.profile_labels.get(profile.name, profile.name)
                    yield ListItem(Label(label), id=item_id)
            yield Button("Cancel", variant="error", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._closed:
            return
        if event.button.id == "cancel_btn":
            self._closed = True
            self.dismiss(None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if self._closed:
            return
        if event.item is None or event.item.id is None:
            return

        selected_profile = self._profile_by_item_id.get(event.item.id)
        if selected_profile is None:
            return

        self._closed = True
        self.dismiss(selected_profile)


class ConfirmDialog(ModalScreen[bool]):
    """A simple confirmation modal."""

    def __init__(self, title: str, message: str):
        super().__init__()
        self.title = title
        self.message = message
        self._closed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"[bold]{self.title}[/bold]")
            yield Label(self.message)
            yield Button("Confirm", variant="success", id="confirm_btn")
            yield Button("Cancel", variant="error", id="cancel_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if self._closed:
            return
        if event.button.id == "confirm_btn":
            self._closed = True
            self.dismiss(True)
        elif event.button.id == "cancel_btn":
            self._closed = True
            self.dismiss(False)
