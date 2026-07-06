from textual.widgets import DataTable, ListItem, ListView
from textual.containers import Container
from core.models import Service, Profile
from typing import List

class ServiceTable(DataTable):
    """A table showing the current services in the stack."""
    def update_data(self, services: List[Service]):
        self.clear()
        self.add_columns("Service", "Enabled", "Profile")
        for s in services:
            status = "YES" if s.enabled else "NO"
            self.add_row(s.name, status, s.profile_id)

class ProfileList(ListView):
    """A list of available profiles for easy selection."""
    def update_data(self, profiles: List[Profile]):
        self.clear()
        for p in profiles:
            self.append(ListItem(p.name, id=p.name))
