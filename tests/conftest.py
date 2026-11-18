import hashlib
import io
import json
import tarfile

import pytest


@pytest.fixture
def training_package(tmp_path):
    profiles = {"bootstrap": {"python": "3.12", "requirements": None, "minimum_driver_major": 0},
                "trl": {"python": "3.12", "requirements": "sft-trl.arm64-cu130.txt", "minimum_driver_major": 580}}
    files = {"pyproject.toml": b'[project]\nname="nlp-lab-training"\nversion="0.1.0"\n',
             "nlp_training/profiles/runtime.json": json.dumps(profiles).encode()}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    path = tmp_path / "training-package.tar"
    path.write_bytes(buffer.getvalue())
    return {"archive": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "revision": "0" * 40}
