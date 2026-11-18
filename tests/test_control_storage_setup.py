import argparse
import json
import os
import pwd
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.lib import control_install as install


def test_noninteractive_storage_validation_precedes_host_install(tmp_path):
    args = argparse.Namespace(non_interactive=True, check=False, training_profile="trl", reserve_memory_mb=8192)
    with patch.dict(os.environ, {"STORAGE_URL": "not-an-endpoint"}, clear=True):
        with pytest.raises(RuntimeError, match="HTTP"):
            install.configuration_request(args, tmp_path)
    key = tmp_path / "key"
    key.write_text("")
    with patch.dict(os.environ, {"STORAGE_URL": "https://minio.example.invalid", "STORAGE_ACCOUNT": "account", "STORAGE_KEY_FILE": str(key)}, clear=True):
        with pytest.raises(RuntimeError, match="empty"):
            install.configuration_request(args, tmp_path)


def test_storage_can_be_added_after_bootstrap_setup_without_losing_runtime_values(tmp_path, training_package):
    repo = Path(__file__).resolve().parents[1]
    request = {"owner": pwd.getpwuid(os.getuid()).pw_name, "repo": str(repo), "state": str(tmp_path / "state"),
               "reserve_mb": 8192, "training_profile": "bootstrap", "storage": {}, "training_package": training_package}
    host = install.Provisioner(request, root=tmp_path / "host")
    with patch.object(install, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
        host.training()
        runtime = host.p("/etc/eliza-training/runtime.env")
        original = runtime.read_text()
        assert not host.receipt["storage_configured"]
        request["storage"] = {"url": "https://minio.example.invalid", "account": "account", "key": "fixture-key"}
        host.training()
    assert runtime.read_text().startswith(original)
    assert "STORAGE_URL=" in runtime.read_text()
    assert host.receipt["storage_configured"]
    assert host.p("/etc/eliza-training/minio-key").stat().st_mode & 0o777 == 0o640
    assert json.loads(host.receipt_path.read_text())["files"]
