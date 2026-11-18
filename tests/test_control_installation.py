"""Exercise provisioning with a simulated host; never install/start host services."""
import hashlib
import io
import json
import os
import pwd
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.lib import control_install as install
from scripts.lib.slurm_admin import command
from scripts.lib import slurm_admin

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def host(tmp_path, training_package):
    owner = pwd.getpwuid(os.getuid())
    request = {"owner": owner.pw_name, "repo": str(ROOT), "state": str(tmp_path / "state/environment.json"),
               "reserve_mb": 8192, "training_profile": "bootstrap", "storage": {}, "check": False, "training_package": training_package}
    machine = tmp_path / "host"
    (machine / "etc").mkdir(parents=True)
    (machine / "etc/os-release").write_text('ID="ubuntu"\n')
    (machine / "run/systemd/system").mkdir(parents=True)
    (machine / "sys/fs/cgroup").mkdir(parents=True)
    (machine / "sys/fs/cgroup/cgroup.controllers").write_text("cpu memory")
    with patch("scripts.lib.control_install.os.chown"), patch("scripts.lib.control_install.platform.machine", return_value="aarch64"), patch("scripts.lib.control_install.platform.node", return_value="dgx-test"), patch("scripts.lib.control_install.shutil.which", return_value=None):
        yield install.Provisioner(request, root=machine)


def simulator(host, *, fail_on=None):
    calls = []
    def run(args, **kwargs):
        args = [str(arg) for arg in args]
        calls.append(args)
        if fail_on and fail_on in " ".join(args):
            raise RuntimeError("simulated failure")
        out, code = "", 0
        if args[:2] == ["systemctl", "is-active"]:
            code = 3
        if args[:2] == ["systemctl", "is-enabled"]:
            out = "static" if args[2] != "munge.service" else "disabled"
        if args[0] == "nvidia-smi":
            out = "0, 580.95.05"
        if args[-1:] == ["--version"]:
            out = "slurm " + install.VERSION
        if args[-1:] == ["-C"]:
            out = "NodeName=dgx-test CPUs=10 Boards=1 SocketsPerBoard=1 CoresPerSocket=10 ThreadsPerCore=1 RealMemory=128000\nUpTime=100"
        if args[-1:] == ["-G"]:
            out = "1 GPU system device(s) detected\nName=gpu Count=1"
        if args[-1:] == ["--generate-openapi-spec"]:
            out = json.dumps({"paths": {"/slurm/v0.0.45/job/submit": {}}})
        if args[0] == "ldconfig":
            out = "libnvidia-ml.so.1 (libc6,AArch64) => /usr/lib/aarch64-linux-gnu/libnvidia-ml.so.1"
        return subprocess.CompletedProcess(args, code, out, "")
    return run, calls


def prepare_binaries(host):
    for name in install.PLUGINS:
        path = host.prefix / "lib/slurm" / (name + ".so")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"plugin")
    for name in ("slurmd", "slurmctld", "slurmrestd"):
        path = host.prefix / "sbin" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"executable")
    (host.prefix / ".eliza-complete").write_text(install.SLURM_SHA)


def test_mask_cleanup_even_after_package_failure(host):
    run, calls = simulator(host, fail_on="apt-get install")
    with patch.object(install, "run", side_effect=run):
        with pytest.raises(RuntimeError, match="simulated"):
            host.packages()
    for unit in install.UNITS:
        assert ["systemctl", "mask", "--runtime", unit] in calls
        assert ["systemctl", "unmask", "--runtime", unit] in calls
    assert not any(call[:2] == ["systemctl", "start"] for call in calls)


def test_preexisting_masks_are_not_removed(host):
    mask = host.p("/run/systemd/system/munge.service")
    mask.symlink_to("/dev/null")
    run, calls = simulator(host)
    with patch.object(install, "run", side_effect=run):
        host.packages()
    assert ["systemctl", "unmask", "--runtime", "munge.service"] not in calls
    assert mask.is_symlink()


def test_unmanaged_scheduler_and_non_inference_mode_fail_before_mutation(host):
    config = host.p("/etc/slurm/slurm.conf")
    config.parent.mkdir()
    config.write_text("existing cluster")
    run, calls = simulator(host)
    with patch.object(install, "run", side_effect=run):
        with pytest.raises(RuntimeError, match="unmanaged Slurm configuration"):
            host.apply()
    assert config.read_text() == "existing cluster"
    assert not any(call[0] == "apt-get" for call in calls)
    config.unlink()
    host.state.write_text('{"phase":"training"}')
    with patch.object(install, "run", side_effect=run):
        with pytest.raises(RuntimeError, match="inference"):
            host.apply()


def test_managed_configuration_detects_edits_and_reuses_receipt_after_failure(host):
    path = host.p("/etc/slurm/slurm.conf")
    host.managed(path, "first")
    resumed = install.Provisioner(host.request, root=host.root)
    resumed.managed(path, "second")
    assert path.read_text() == "second"
    path.write_text("human edits")
    with pytest.raises(RuntimeError, match="Preserving changed"):
        resumed.managed(path, "third")
    assert path.read_text() == "human edits"


def test_existing_authentication_keys_are_preserved(host):
    path = host.p("/etc/slurm/jwt_hs256.key")
    path.parent.mkdir()
    path.write_bytes(b"existing-key")
    run, _ = simulator(host)
    with patch.object(install, "run", side_effect=run):
        host.secret("/etc/slurm/jwt_hs256.key", "root:slurm")
    assert path.read_bytes() == b"existing-key"
    assert path.stat().st_mode & 0o777 == 0o640


def test_discovery_reserves_memory_and_rejects_inconsistent_topology():
    output = "NodeName=dgx CPUs=10 Boards=1 SocketsPerBoard=1 CoresPerSocket=10 ThreadsPerCore=1 RealMemory=128000"
    assert install.topology(output, 8192)["RealMemory"] == 115200
    with pytest.raises(RuntimeError, match="Inconsistent CPU"):
        install.topology(output.replace("CPUs=10", "CPUs=20"), 8192)


def test_completed_slurm_build_is_reused_but_plugins_are_verified(host):
    prepare_binaries(host)
    run, calls = simulator(host)
    with patch.object(install, "run", side_effect=run), patch.object(install, "download", side_effect=AssertionError("No rebuild download expected")):
        host.slurm()
    assert not any(call[0] == "make" for call in calls)
    assert host.p("/usr/local/bin/scontrol").is_symlink()
    (host.prefix / "lib/slurm/gpu_nvml.so").unlink()
    with patch.object(install, "run", side_effect=run):
        with pytest.raises(RuntimeError, match="gpu_nvml"):
            host.verify_binaries()


def test_offline_install_checks_api_gpu_and_never_starts_scheduler(host):
    prepare_binaries(host)
    run, calls = simulator(host)
    with patch.object(install, "run", side_effect=run), patch.object(host, "packages"), patch.object(host, "training"), patch.object(host, "account"):
        host.apply()
    assert json.loads(host.receipt_path.read_text())["complete"]
    assert json.loads(host.state.read_text())["phase"] == "inference"
    conf = host.p("/etc/slurm/slurm.conf").read_text()
    assert "State=INACTIVE" in conf and "RealMemory=115200" in conf
    assert "AllowGroups=eliza-training" in conf
    assert any(call[-1] == "--generate-openapi-spec" for call in calls)
    assert not any(call[:2] == ["systemctl", "start"] for call in calls)
    assert "[Install]" not in host.p("/etc/systemd/system/slurmd.service").read_text()


def test_wrong_openapi_is_rejected(host):
    with patch.object(install, "run", return_value=subprocess.CompletedProcess([], 0, '{"paths":{}}', "")):
        with pytest.raises(RuntimeError, match="v0.0.45"):
            host.verify_api()


def test_privileged_helper_restricts_commands_accounts_and_lifetimes():
    config = {"slurm_prefix": "/opt/eliza-slurm/26.05.6", "training_user": "eliza-training", "token_lifespan": 3600}
    assert command(["systemctl", "start", "slurmd.service"], config) == ["/usr/bin/systemctl", "start", "slurmd.service"]
    assert command(["scontrol", "token", "username=eliza-training", "lifespan=3600"], config)[0].endswith("bin/scontrol")
    for args in (["systemctl", "start", "sshd.service"], ["scontrol", "token", "username=root", "lifespan=3600"],
                 ["scontrol", "token", "username=eliza-training", "lifespan=86400"], ["bash", "-c", "arbitrary"]):
        with pytest.raises(ValueError, match="allowlist"):
            command(args, config)


def test_privileged_helper_rejects_other_caller_and_inference_mode_activation():
    config = {"slurm_prefix": "/opt/eliza-slurm/26.05.6", "training_user": "eliza-training", "token_lifespan": 3600, "control_user": "control", "state": "/var/lib/eliza/environment.json"}
    with patch.object(slurm_admin.os, "getuid", return_value=0), patch.object(slurm_admin.Path, "read_text", return_value=json.dumps(config)), patch.dict(os.environ, {"SUDO_USER": "other"}):
        with pytest.raises(PermissionError, match="Caller"):
            slurm_admin.main()
    with patch.object(slurm_admin.os, "getuid", return_value=0), patch.object(slurm_admin.Path, "read_text", side_effect=[json.dumps(config), '{"phase":"inference"}']), patch.dict(os.environ, {"SUDO_USER": "control"}), patch.object(sys, "argv", ["helper", "systemctl", "start", "slurmd.service"]), patch.object(slurm_admin.subprocess, "run") as process:
        with pytest.raises(PermissionError, match="transition"):
            slurm_admin.main()
        process.assert_not_called()


def test_checksum_failure_never_publishes_download(tmp_path):
    response = io.BytesIO(b"incorrect bytes")
    with patch.object(install, "urlopen", return_value=response):
        with pytest.raises(RuntimeError, match="checksum"):
            install.download("https://example.invalid/source", "0" * 64, tmp_path / "source")
    assert not (tmp_path / "source").exists()


def test_training_setup_delegates_to_the_pinned_package(host):
    run, calls = simulator(host)
    with patch.object(install, "run", side_effect=run):
        host.training()
    assert any("nlp_training.provision" in call for call in calls)
    assert any(call[-1].endswith("[provisioning]") for call in calls)
    assert not any("-r" in call or "torch" in " ".join(call) for call in calls)
    assert host.receipt["training_package"]["revision"] == "0" * 40


def test_migration_removes_only_an_unchanged_owned_worker(host):
    worker = host.p("/opt/eliza-training/run_bundle.py")
    host.managed(worker, "previous owned worker")
    run, _ = simulator(host)
    with patch.object(install, "run", side_effect=run):
        host.training()
    assert not worker.exists()
    host.managed(worker, "previous owned worker")
    worker.write_text("operator edits")
    with patch.object(install, "run", side_effect=run), pytest.raises(RuntimeError, match="Preserving"):
        host.training()
    assert worker.read_text() == "operator edits"


def test_plan_entrypoints_do_not_call_privileged_commands():
    result = subprocess.run([str(ROOT / "scripts/setup"), "control", "--plan"], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    plan = json.loads(result.stdout)
    assert plan["slurm_version"] == "26.05.6"
    assert plan["scheduler_final_state"] == "stopped"


def test_probe_wrapper_delegates_to_the_training_package():
    script = (ROOT / "scripts/training-smoke").read_text()
    assert "-m nlp_training.smoke" in script
    assert not (ROOT / "scripts/lib/training_smoke.py").exists()


def test_control_setup_uses_dedicated_python_preserves_token_and_checks_health(tmp_path):
    repo = tmp_path / "repo with spaces"
    (repo / ".runtime").mkdir(parents=True)
    (repo / ".runtime/control-token").write_text("existing-token")
    request = {"state": str(tmp_path / "environment.json"), "storage": {}}
    calls = []
    def run(args, **kwargs):
        calls.append([str(arg) for arg in args])
        return subprocess.CompletedProcess(args, 0, "", "")
    with patch.object(install, "run", side_effect=run), patch.object(install.Path, "home", return_value=tmp_path), patch.object(install, "urlopen", return_value=io.BytesIO(b'{"service":"control-daemon"}')):
        install.install_control(repo, request)
    assert (repo / ".runtime/control-token").read_text() == "existing-token"
    assert "CONTROL_DAEMON_PYTHON=" in (repo / ".runtime/control-install.env").read_text()
    unit = (tmp_path / ".config/systemd/user/eliza-control-daemon.service").read_text()
    assert f'WorkingDirectory="{repo}"' in unit
    assert ["systemctl", "--user", "restart", "eliza-control-daemon.service"] in calls
    assert not any("torch" in " ".join(call) for call in calls)
