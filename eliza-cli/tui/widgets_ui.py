from textual.widgets import DataTable, ListItem, Label, Static
from textual.containers import Container
from textual.widgets import ListView
from core.models import Profile, Service
from typing import List

class ServiceTable(DataTable):
    """A table showing the current services in the stack."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._columns_initialized = False

    def _ensure_columns(self) -> None:
        if self._columns_initialized:
            return
        self.add_columns(
            "Service",
            "Status",
            "Health",
            "Configured Profile",
            "Live Profile",
            "Live Model",
            "Drift",
        )
        self._columns_initialized = True

    def update_data(
        self,
        services: List[Service],
        selected_service_name: str = "",
        selected_column: int = 0,
    ) -> None:
        self._ensure_columns()
        self.clear(columns=False)

        target_row = 0 if services else None
        for row_index, s in enumerate(services):
            live_profile = s.live_profile_id or "-"
            drift = "YES" if s.drift else "NO"
            self.add_row(
                s.name,
                s.status,
                s.health,
                s.profile_id,
                live_profile,
                s.live_model,
                drift,
            )

            if selected_service_name and s.name == selected_service_name:
                target_row = row_index

        if target_row is not None:
            bounded_column = min(max(selected_column, 0), 6)
            self.move_cursor(row=target_row, column=bounded_column, animate=False, scroll=False)

    def get_selected_service_name(self) -> str:
        """Returns the name of the selected service from the table."""
        try:
            row_index = self.cursor_row
            if row_index is not None and row_index >= 0:
                row_data = self.get_row(row_index)
                return str(row_data[0])
        except Exception:
            pass
        return ""

class ProfileList(ListView):
    """A list of available profiles for easy selection."""
    def update_data(self, profiles: List[Profile]):
        self.clear()
        for p in profiles:
            # Sanitize id by replacing slashes with underscores
            safe_id = p.name.replace("/", "_")
            # ListItem expects a Widget (like Label) as its first argument
            self.append(ListItem(Label(p.name), id=safe_id))

class ProfileInspector(Static):
    """A panel showing detailed metadata for a selected profile."""
    def update_profile(self, profile: Profile):
        self.update(self._format_profile(profile))

    def _format_profile(self, profile: Profile) -> str:
        lines = [
            f"[bold cyan]Profile:[/bold cyan] {profile.name}",
            f"[bold cyan]Service:[/bold cyan] {profile.service_name}",
            f"[bold cyan]Backend:[/bold cyan] {profile.backend}",
            f"[bold cyan]Model Repo:[/bold cyan] {profile.model_repo or 'N/A'}",
            f"[bold cyan]Model File:[/bold cyan] {profile.model_file}",
            f"[bold cyan]Context:[/bold cyan] {profile.ctx_size:,}",
            f"[bold cyan]Batch Size:[/bold cyan] {profile.batch_size}",
            f"[bold cyan]GPU Layers:[/bold cyan] {profile.n_gpu_layers}",
            f"[bold cyan]Speculative:[/bold cyan] {profile.spec_type or 'None'}",
        ]
        return "\n".join(lines)
