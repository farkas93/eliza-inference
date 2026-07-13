from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List
from urllib.error import URLError
from urllib.request import Request, urlopen

from .models import Profile, Service

# TTL for cached HF API size estimates (seconds)
_SIZE_CACHE_TTL = 60.0
# TTL for cached profile env reads (seconds)
_ENV_CACHE_TTL = 30.0


@dataclass(frozen=True)
class ProfileState:
    profile_name: str
    service_name: str
    ready: bool
    deployed: bool
    expected_paths: tuple[str, ...]
    model_location: str
    estimated_download_size_bytes: int | None


@dataclass(frozen=True)
class ModelEntry:
    name: str
    path: str
    size_bytes: int
    linked_profiles: tuple[str, ...]
    status: str


class ModelManager:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = root_dir
        self.env = self._load_env()
        self.model_home = pathlib.Path(self.env["MODEL_HOME"]).expanduser().resolve()
        self._profile_env_cache: dict[str, tuple[float, dict[str, str]]] = {}
        self._estimate_size_cache: dict[str, tuple[float, int | None]] = {}

    def _load_env(self) -> Dict[str, str]:
        env: Dict[str, str] = {}
        env_file = self.root_dir / ".env"
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip().strip('"').strip("'")

        home = str(pathlib.Path.home())
        model_home = env.get("MODEL_HOME", os.path.join(home, "models"))
        defaults = {
            "HOME": home,
            "MODEL_HOME": model_home,
            "HF_HOME": env.get("HF_HOME", os.path.join(model_home, "huggingface")),
            "LLAMA_CACHE": env.get("LLAMA_CACHE", os.path.join(model_home, "llamacpp_cache")),
            "DEFAULT_HOST": env.get("DEFAULT_HOST", "0.0.0.0"),
            "ELIZA_MEDIUM_PORT": env.get("ELIZA_MEDIUM_PORT", "8001"),
            "ELIZA_SMALL_PORT": env.get("ELIZA_SMALL_PORT", "8002"),
            "STT_PORT": env.get("STT_PORT", "8011"),
            "TTS_PORT": env.get("TTS_PORT", "8012"),
        }
        defaults.update(env)
        return defaults

    def _load_profile_env(self, profile: Profile) -> Dict[str, str]:
        cached = self._profile_env_cache.get(profile.name)
        if cached is not None:
            ts, data = cached
            if time.monotonic() - ts < _ENV_CACHE_TTL:
                return data

        data: Dict[str, str] = {}
        with open(profile.path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip().strip('"').strip("'")

        self._profile_env_cache[profile.name] = (time.monotonic(), data)
        return data

    def _resolve_value(self, value: str, profile_env: Dict[str, str]) -> str:
        merged = dict(self.env)
        merged.update(profile_env)

        pattern = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}")

        def substitute(match: re.Match[str]) -> str:
            key = match.group(1)
            default = match.group(2) or ""
            return merged.get(key, default)

        value = pattern.sub(substitute, value)
        value = os.path.expandvars(value)
        return os.path.expanduser(value)

    def _expected_paths_for_profile(self, profile: Profile) -> List[pathlib.Path]:
        profile_env = self._load_profile_env(profile)
        backend = profile_env.get("BACKEND", profile.backend)
        model_dir_raw = profile_env.get("MODEL_DIR", "")
        model_dir: pathlib.Path | None = None
        if model_dir_raw:
            model_dir = pathlib.Path(self._resolve_value(model_dir_raw, profile_env)).resolve()

        paths: List[pathlib.Path] = []
        for key in ("MODEL_FILE", "MMPROJ_FILE", "MODEL_CONFIG_FILE"):
            value = profile_env.get(key)
            if value and model_dir is not None:
                paths.append((model_dir / value).resolve())

        for key in ("PIPER_VOICE_PATH", "PIPER_CONFIG_PATH"):
            value = profile_env.get(key)
            if value:
                paths.append(pathlib.Path(self._resolve_value(value, profile_env)).resolve())

        model_id = profile_env.get("MODEL_ID", "").strip()
        if backend == "vllm" and model_id:
            hf_home = self._resolve_value(profile_env.get("HF_HOME", self.env["HF_HOME"]), profile_env)
            paths.append((pathlib.Path(hf_home) / "hub" / model_id).resolve())

        if not paths and model_dir is not None:
            paths.append(model_dir)

        deduped: list[pathlib.Path] = []
        seen: set[pathlib.Path] = set()
        for path in paths:
            if path not in seen:
                deduped.append(path)
                seen.add(path)
        return deduped

    def _compute_size(self, path: pathlib.Path) -> int:
        if not path.exists():
            return 0
        if path.is_file():
            return path.stat().st_size

        total = 0
        for root, _, files in os.walk(path):
            for file_name in files:
                file_path = pathlib.Path(root) / file_name
                try:
                    total += file_path.stat().st_size
                except OSError:
                    continue
        return total

    def _estimate_download_size(self, profile: Profile) -> int | None:
        """Query HF API to estimate download size for a profile. Results cached for _SIZE_CACHE_TTL seconds."""
        cached = self._estimate_size_cache.get(profile.name)
        if cached is not None:
            ts, size = cached
            if time.monotonic() - ts < _SIZE_CACHE_TTL:
                return size

        profile_env = self._load_profile_env(profile)

        model_repo = profile_env.get("MODEL_REPO", "").strip()
        model_id = profile_env.get("MODEL_ID", "").strip()
        include_patterns: list[str] = []

        if model_repo:
            repo = model_repo
            model_file = profile_env.get("MODEL_FILE", "").strip()
            mmproj_file = profile_env.get("MMPROJ_FILE", "").strip()
            hf_include_model = profile_env.get("HF_INCLUDE_MODEL", "").strip()
            hf_include_config = profile_env.get("HF_INCLUDE_CONFIG", "").strip()
            model_config_file = profile_env.get("MODEL_CONFIG_FILE", "").strip()
            if hf_include_model:
                include_patterns.append(hf_include_model)
            if hf_include_config:
                include_patterns.append(hf_include_config)
            if model_file:
                include_patterns.append(model_file)
            if mmproj_file:
                include_patterns.append(mmproj_file)
        elif model_id:
            repo = model_id
            include_patterns = []  # entire snapshot
        else:
            self._estimate_size_cache[profile.name] = (time.monotonic(), None)
            return None

        try:
            url = f"https://huggingface.co/api/models/{repo}/tree/main?recursive=True"
            req = Request(url, method="GET")
            with urlopen(req, timeout=3) as resp:
                data = json.load(resp)
        except (URLError, TimeoutError, json.JSONDecodeError, ValueError):
            self._estimate_size_cache[profile.name] = (time.monotonic(), None)
            return None

        if not isinstance(data, list):
            self._estimate_size_cache[profile.name] = (time.monotonic(), None)
            return None

        total = 0
        for entry in data:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path", "")
            size = entry.get("size", 0)
            if not isinstance(size, (int, float)):
                continue
            if include_patterns:
                if any(pattern in path for pattern in include_patterns):
                    total += int(size)
            else:
                total += int(size)

        result = total if total > 0 else None
        self._estimate_size_cache[profile.name] = (time.monotonic(), result)
        return result

    def build_profile_states(
        self,
        profiles: Dict[str, Profile],
        services: Dict[str, Service],
    ) -> Dict[str, ProfileState]:
        deployed_profiles: set[str] = set()
        for service in services.values():
            if service.status != "running":
                continue
            deployed_profiles.add(service.live_profile_id or service.profile_id)

        states: Dict[str, ProfileState] = {}
        for profile in profiles.values():
            expected_paths = self._expected_paths_for_profile(profile)
            ready = all(path.exists() for path in expected_paths) if expected_paths else False
            if expected_paths:
                first_path = expected_paths[0]
                model_location = str(first_path if first_path.is_dir() else first_path.parent)
            else:
                model_location = "N/A"

            estimated_size = self._estimate_download_size(profile)

            states[profile.name] = ProfileState(
                profile_name=profile.name,
                service_name=profile.service_name,
                ready=ready,
                deployed=profile.name in deployed_profiles,
                expected_paths=tuple(str(path) for path in expected_paths),
                model_location=model_location,
                estimated_download_size_bytes=estimated_size,
            )
        return states

    def list_models(self, profiles: Dict[str, Profile]) -> List[ModelEntry]:
        profile_paths: Dict[pathlib.Path, set[str]] = {}
        for profile in profiles.values():
            for expected_path in self._expected_paths_for_profile(profile):
                existing_path = expected_path if expected_path.exists() else expected_path.parent
                profile_paths.setdefault(existing_path.resolve(), set()).add(profile.name)

        model_entries: Dict[pathlib.Path, ModelEntry] = {}
        for path, linked_profiles in profile_paths.items():
            size_bytes = self._compute_size(path)
            entry = ModelEntry(
                name=path.name or str(path),
                path=str(path),
                size_bytes=size_bytes,
                linked_profiles=tuple(sorted(linked_profiles)),
                status="linked",
            )
            model_entries[path] = entry

        if self.model_home.exists():
            for child in sorted(self.model_home.iterdir()):
                child = child.resolve()
                if child in model_entries:
                    continue

                linked = False
                for known_path in model_entries:
                    if known_path == child:
                        linked = True
                        break
                    if str(known_path).startswith(f"{child}{os.sep}"):
                        linked = True
                        break
                if linked:
                    continue

                model_entries[child] = ModelEntry(
                    name=child.name or str(child),
                    path=str(child),
                    size_bytes=self._compute_size(child),
                    linked_profiles=(),
                    status="orphan",
                )

        return sorted(model_entries.values(), key=lambda entry: (entry.status, entry.path))

    def delete_entry_profile_files_only(
        self,
        entry: ModelEntry,
        profile_states: Dict[str, ProfileState],
    ) -> tuple[int, int]:
        target_path = pathlib.Path(entry.path)
        deleted_files = 0
        deleted_bytes = 0

        for profile_name in entry.linked_profiles:
            state = profile_states.get(profile_name)
            if state is None:
                continue
            for expected_path_text in state.expected_paths:
                expected_path = pathlib.Path(expected_path_text)
                if not expected_path.exists() or expected_path.is_dir():
                    continue
                try:
                    expected_path.relative_to(target_path)
                except ValueError:
                    continue

                try:
                    file_size = expected_path.stat().st_size
                except OSError:
                    file_size = 0

                try:
                    expected_path.unlink()
                    deleted_files += 1
                    deleted_bytes += file_size
                except OSError:
                    continue

        self._prune_empty_dirs(target_path)
        return deleted_files, deleted_bytes

    def delete_orphan_entry(self, entry: ModelEntry) -> int:
        target_path = pathlib.Path(entry.path)
        deleted_bytes = self._compute_size(target_path)

        if not target_path.exists():
            return 0
        if target_path.is_file():
            target_path.unlink(missing_ok=True)
            return deleted_bytes

        shutil.rmtree(target_path, ignore_errors=True)
        return deleted_bytes

    def cleanup_orphans(self, entries: Iterable[ModelEntry]) -> tuple[int, int]:
        deleted_count = 0
        deleted_bytes = 0
        for entry in entries:
            if entry.status != "orphan":
                continue
            deleted_bytes += self.delete_orphan_entry(entry)
            deleted_count += 1
        return deleted_count, deleted_bytes

    def _prune_empty_dirs(self, root: pathlib.Path) -> None:
        if not root.exists() or root.is_file():
            return
        for path in sorted(root.rglob("*"), reverse=True):
            if not path.is_dir():
                continue
            try:
                path.rmdir()
            except OSError:
                continue
        try:
            root.rmdir()
        except OSError:
            pass
