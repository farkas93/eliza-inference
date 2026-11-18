"""Consume an immutable training package; all Git authentication is normal-user side."""
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

MAX_BYTES = 16 * 1024 * 1024


def package_files(data):
    if len(data) > MAX_BYTES:
        raise ValueError("Training package archive exceeds limit")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for member in archive:
            path = PurePosixPath(member.name.rstrip("/"))
            if path.is_absolute() or ".." in path.parts or not path.parts or "\\" in member.name or path.as_posix() != member.name.rstrip("/"):
                raise ValueError("Unsafe training package path")
            if member.isdir():
                continue
            if not member.isfile() or member.name in files:
                raise ValueError("Training package contains links or duplicate files")
            with archive.extractfile(member) as handle:
                files[member.name] = handle.read()
    for required in ("pyproject.toml", "nlp_training/profiles/runtime.json"):
        if required not in files:
            raise ValueError("Incomplete training package: " + required)
    return files


def load_package(descriptor):
    path = Path(descriptor["archive"])
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Training package archive exceeds limit")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != descriptor["sha256"]:
        raise ValueError("Training package checksum mismatch")
    return package_files(data)


def prepare(config, cache: Path, *, local_repo=None):
    revision = config["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Training source must be pinned to a full Git commit")
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / (revision + ".tar")
    receipt = archive.with_suffix(".json")
    if archive.exists() and receipt.exists():
        descriptor = json.loads(receipt.read_text())
        if descriptor["revision"] == revision:
            load_package(descriptor)
            return descriptor
    if local_repo:
        available = subprocess.run(["git", "-C", str(local_repo), "cat-file", "-e", revision + "^{commit}"], capture_output=True)
        if available.returncode:
            local_repo = None
    repo = Path(local_repo) if local_repo else cache / "git"
    if not local_repo:
        if not repo.exists():
            subprocess.run(["git", "init", "--bare", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", config["repository"]], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "set-url", "origin", config["repository"]], check=True)
        subprocess.run(["git", "-C", str(repo), "fetch", "--no-tags", "--depth=1", "origin", revision], check=True)
    data = subprocess.check_output(["git", "-C", str(repo), "archive", "--format=tar", revision + ":" + config["subdirectory"]])
    package_files(data)
    archive.write_bytes(data)
    descriptor = {"archive": str(archive.resolve()), "sha256": hashlib.sha256(data).hexdigest(), "revision": revision}
    receipt.write_text(json.dumps(descriptor, indent=2))
    return descriptor
