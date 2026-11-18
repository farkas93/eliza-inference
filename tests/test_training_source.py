import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts.lib import training_source


def test_changed_archive_is_rejected_before_host_provisioning(training_package):
    Path(training_package["archive"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        training_source.load_package(training_package)


def test_links_or_traversal_are_not_package_inputs():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo("../escaped")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="Unsafe"):
        training_source.package_files(buffer.getvalue())


def test_local_snapshot_is_pinned_and_cached_without_editing_the_checkout(tmp_path):
    repo = tmp_path / "repo"
    package = repo / "packages/training-client"
    (package / "nlp_training/profiles").mkdir(parents=True)
    (package / "pyproject.toml").write_text('[project]\nname="nlp-lab-training"\n')
    profile = package / "nlp_training/profiles/runtime.json"
    profile.write_text('{"bootstrap":{}}')
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], cwd=repo, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    profile.write_text('{"bootstrap":{"edited":true}}')
    config = {"commit": revision, "subdirectory": "packages/training-client"}
    descriptor = training_source.prepare(config, tmp_path / "cache", local_repo=repo)
    files = training_source.load_package(descriptor)
    assert files["nlp_training/profiles/runtime.json"] == b'{"bootstrap":{}}'
    assert "edited" in profile.read_text()
    assert training_source.prepare(config, tmp_path / "cache") == descriptor
