from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
from dataclasses import replace
from typing import Dict
from urllib.error import URLError
from urllib.request import Request, urlopen

from .models import Profile, Service


class RuntimeProbe:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = root_dir
        self.state_path = root_dir / ".runtime" / "service_profiles.json"

    def merge_live_state(
        self,
        services: Dict[str, Service],
        profiles: Dict[str, Profile],
    ) -> Dict[str, Service]:
        runtime_profiles = self._load_runtime_profiles()
        merged: Dict[str, Service] = {}

        for name, service in services.items():
            health_ok = self._health_ok(service.health_url)
            tmux_running = self._tmux_running(name)
            status = "running" if (tmux_running or health_ok) else "stopped"
            health = "ok" if health_ok else "-"

            live_model = "-"
            if health_ok and service.base_url:
                live_model = self._live_model_from_base_url(service.base_url)

            live_profile = runtime_profiles.get(name)
            if live_profile is None and live_model not in ("", "-", "unavailable"):
                live_profile = self._infer_profile_from_model(name, live_model, profiles)

            drift = self._detect_drift(service, profiles, live_profile, live_model)

            merged[name] = replace(
                service,
                status=status,
                health=health,
                live_profile_id=live_profile,
                live_model=live_model,
                drift=drift,
            )

        return merged

    def _load_runtime_profiles(self) -> Dict[str, str]:
        if not self.state_path.exists():
            return {}
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(payload, dict):
            return {}
        return {str(service): str(profile) for service, profile in payload.items()}

    def _tmux_running(self, service_name: str) -> bool:
        session = service_name if service_name.startswith("eliza-") else f"eliza-{service_name}"
        if not self._command_exists("tmux"):
            return False
        result = subprocess.run(
            ["tmux", "has-session", "-t", session],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _command_exists(self, command_name: str) -> bool:
        return shutil.which(command_name) is not None

    def _health_ok(self, health_url: str) -> bool:
        if not health_url:
            return False
        request = Request(health_url, method="GET")
        try:
            with urlopen(request, timeout=1.5) as response:
                return 200 <= response.status < 300
        except (URLError, TimeoutError, ValueError):
            return False

    def _live_model_from_base_url(self, base_url: str) -> str:
        models_url = f"{base_url.rstrip('/')}/models"
        request = Request(models_url, method="GET")
        try:
            with urlopen(request, timeout=2.0) as response:
                body = response.read().decode("utf-8", errors="replace")
        except (URLError, TimeoutError, ValueError):
            return "unavailable"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return "unavailable"

        if isinstance(data, dict):
            entries = data.get("data")
            if isinstance(entries, list) and entries:
                first = entries[0]
                if isinstance(first, dict) and "id" in first:
                    return str(first["id"])
            if "id" in data:
                return str(data["id"])

        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and "id" in first:
                return str(first["id"])

        return "unavailable"

    def _infer_profile_from_model(
        self,
        service_name: str,
        live_model: str,
        profiles: Dict[str, Profile],
    ) -> str | None:
        matches = [
            profile.name
            for profile in profiles.values()
            if profile.service_name == service_name and profile.model_file == live_model
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def _detect_drift(
        self,
        service: Service,
        profiles: Dict[str, Profile],
        live_profile: str | None,
        live_model: str,
    ) -> bool:
        if live_profile:
            return live_profile != service.profile_id

        configured_profile = profiles.get(service.profile_id)
        if configured_profile and live_model not in ("", "-", "unavailable"):
            return configured_profile.model_file != live_model

        return False
