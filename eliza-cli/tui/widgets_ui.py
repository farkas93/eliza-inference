from textual.widgets import DataTable, ListItem, Label, Static
from textual.containers import Container
from textual.widgets import ListView
from core.models import BackendRuntime, Profile, Service
from typing import Dict, List

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
        selected_row_index: int | None = None,
    ) -> None:
        self._ensure_columns()
        self.clear(columns=False)

        target_row = None
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

        if target_row is None and selected_row_index is not None and services:
            target_row = min(max(selected_row_index, 0), len(services) - 1)

        if target_row is None and services and self.cursor_row is None:
            target_row = 0

        if target_row is not None:
            bounded_column = min(max(selected_column, 0), 6)
            self.move_cursor(row=target_row, column=bounded_column, animate=False, scroll=False)

    def get_selected_service_name(self) -> str:
        """Returns the name of the selected service from the table."""
        try:
            row_index = self.cursor_row
            if row_index is not None and row_index >= 0:
                row_data = self.get_row_at(row_index)
                return str(row_data[0])
        except Exception:
            pass
        return ""

class ProfileList(ListView):
    """A list of available profiles for easy selection."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._profile_by_item_id: dict[str, str] = {}
        self._generation = 0

    def update_data(self, profiles: List[Profile], profile_markers: Dict[str, str] | None = None):
        self.clear()
        self._generation += 1
        self._profile_by_item_id.clear()
        profile_markers = profile_markers or {}
        for index, p in enumerate(profiles):
            item_id = f"profile_{self._generation}_{index}"
            self._profile_by_item_id[item_id] = p.name
            marker = profile_markers.get(p.name, "[dim]....[/dim]")
            label_text = f"{marker} {p.name}"
            # ListItem expects a Widget (like Label) as its first argument
            self.append(ListItem(Label(label_text), id=item_id))

    def restore_selection(
        self,
        selected_profile_name: str | None,
        selected_index: int | None,
        scroll_y: float,
    ) -> None:
        target_index: int | None = None
        if selected_profile_name:
            for index, item_id in enumerate(self._profile_by_item_id):
                if self._profile_by_item_id[item_id] == selected_profile_name:
                    target_index = index
                    break

        if target_index is None and selected_index is not None and self._profile_by_item_id:
            target_index = min(max(selected_index, 0), len(self._profile_by_item_id) - 1)

        if target_index is None and self._profile_by_item_id and self.index is None:
            target_index = 0

        self.index = target_index
        self.scroll_to(y=scroll_y, animate=False, immediate=True)

    def get_profile_name_by_item_id(self, item_id: str | None) -> str | None:
        if item_id is None:
            return None
        return self._profile_by_item_id.get(item_id)

    def get_selected_profile_name(self) -> str | None:
        if self.index is None:
            return None
        if self.index < 0 or self.index >= len(self._profile_by_item_id):
            return None
        item_id = list(self._profile_by_item_id.keys())[self.index]
        return self._profile_by_item_id.get(item_id)


class ModelTable(DataTable):
    """A table showing model artifacts under MODEL_HOME."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._columns_initialized = False

    def _ensure_columns(self) -> None:
        if self._columns_initialized:
            return
        self.add_columns("Name", "Status", "Size", "Location", "Profiles")
        self._columns_initialized = True

    def update_data(
        self,
        entries: List[dict[str, str]],
        selected_model_path: str = "",
        selected_row_index: int | None = None,
        selected_column: int = 0,
    ) -> None:
        self._ensure_columns()
        self.clear(columns=False)

        target_row = None
        for row_index, entry in enumerate(entries):
            self.add_row(
                entry["name"],
                entry["status"],
                entry["size"],
                entry["path"],
                entry["profiles"],
            )

            if selected_model_path and entry["path"] == selected_model_path:
                target_row = row_index

        if target_row is None and selected_row_index is not None and entries:
            target_row = min(max(selected_row_index, 0), len(entries) - 1)

        if target_row is None and entries and self.cursor_row is None:
            target_row = 0

        if target_row is not None:
            bounded_column = min(max(selected_column, 0), 4)
            self.move_cursor(row=target_row, column=bounded_column, animate=False, scroll=False)

    def get_selected_model_name(self) -> str:
        try:
            row_index = self.cursor_row
            if row_index is not None and row_index >= 0:
                row_data = self.get_row_at(row_index)
                return str(row_data[0])
        except Exception:
            pass
        return ""

    def get_selected_model_path(self) -> str:
        try:
            row_index = self.cursor_row
            if row_index is not None and row_index >= 0:
                row_data = self.get_row_at(row_index)
                return str(row_data[3])
        except Exception:
            pass
        return ""


class BackendTable(DataTable):
    """A table showing install status for supported backends."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._columns_initialized = False

    def _ensure_columns(self) -> None:
        if self._columns_initialized:
            return
        self.add_columns("Backend", "Installed", "Version", "Status", "Location", "Update")
        self._columns_initialized = True

    def update_data(
        self,
        backends: List[BackendRuntime],
        selected_backend_name: str = "",
        selected_row_index: int | None = None,
        selected_column: int = 0,
    ) -> None:
        self._ensure_columns()
        self.clear(columns=False)

        target_row = None
        for row_index, backend in enumerate(backends):
            self.add_row(
                backend.name,
                "YES" if backend.installed else "NO",
                backend.version,
                backend.status,
                backend.location,
                backend.update_hint,
            )
            if selected_backend_name and backend.name == selected_backend_name:
                target_row = row_index

        if target_row is None and selected_row_index is not None and backends:
            target_row = min(max(selected_row_index, 0), len(backends) - 1)

        if target_row is None and backends and self.cursor_row is None:
            target_row = 0

        if target_row is not None:
            bounded_column = min(max(selected_column, 0), 5)
            self.move_cursor(row=target_row, column=bounded_column, animate=False, scroll=False)

    def get_selected_backend_name(self) -> str:
        try:
            row_index = self.cursor_row
            if row_index is not None and row_index >= 0:
                row_data = self.get_row_at(row_index)
                return str(row_data[0])
        except Exception:
            pass
        return ""

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
