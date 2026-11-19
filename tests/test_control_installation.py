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
def host(tmp_path):
    owner = pwd.getpwuid(os.getuid())
    request = {"owner": owner.pw_name, "repo": str(ROOT), "state": str(tmp_path / "state/environment.json"),
               "reserve_mb": 8192, "slurm_url": "http://dgx-test:6820", "check": False}
    machine = tmp_path / "host"
    (machine / "etc").mkdir(parents=True)
    (machine / "etc/os-release").write_text('ID="ubuntu"\n')
    (machine / "run/systemd/system").mkdir(parents=True)
    (machine / "sys/fs/cgroup").mkdir(parents=True)
    (machine / "sys/fs/cgroup/cgroup.controllers").write_text("cpu memory")
    with patch("scripts.lib.control_install.os.chown"), patch("scripts.lib.control_install.platform.machine", return_value="aarch64"), patch("scripts.lib.control_install.platform.node", return_value="dgx-test"), patch("scripts.lib.control_install.shutil.which", return_value=None):
        yield install.Provisioner(request, root=machine)


def simulator(host, *, fail_on=None, munge_running=False, munge_retries=0):
    calls = []
    def run(args, **kwargs):
        nonlocal munge_running, munge_retries
        args = [str(arg) for arg in args]
        calls.append(args)
        if fail_on and fail_on in " ".join(args):
            raise RuntimeError("simulated failure")
        out, code = "", 0
        if args[:2] == ["systemctl", "is-active"]:
            code = 0 if args[2] == "munge.service" and munge_running else 3
        if args == ["systemctl", "start", "munge.service"]:
            munge_running = True
        if args == ["systemctl", "stop", "munge.service"]:
            munge_running = False
        if args == ["munge", "-n"]:
            assert munge_running
            if munge_retries:
                munge_retries -= 1
                return subprocess.CompletedProcess(args, 1, "", "socket not ready")
        if args[:2] == ["systemctl", "is-enabled"]:
            out = "static" if args[2] != "munge.service" else "disabled"
        if args[0] == "nvidia-smi":
            out = "0, 580.95.05"
        if args[-1:] == ["--version"]:
            out = "slurm " + install.VERSION
        if args[-1:] == ["-C"]:
            out = "NodeName=dgx-test CPUs=10 Boards=1 SocketsPerBoard=1 CoresPerSocket=10 ThreadsPerCore=1 RealMemory=128000\nUpTime=100"
        if args[-1:] == ["-G"]:
            assert munge_running, "slurmd -G requires MUNGE"
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


def test_install_checks_api_gpu_with_temporary_munge_and_no_scheduler(host):
    prepare_binaries(host)
    munge_key = host.p("/etc/munge/munge.key")
    munge_key.parent.mkdir()
    munge_key.write_bytes(b"existing-key")
    munge_key.chmod(0o640)
    run, calls = simulator(host)
    with patch.object(install, "run", side_effect=run), patch.object(host, "packages"), patch.object(host, "account"):
        host.apply()
    assert json.loads(host.receipt_path.read_text())["complete"]
    assert json.loads(host.state.read_text())["phase"] == "inference"
    conf = host.p("/etc/slurm/slurm.conf").read_text()
    assert "State=INACTIVE" in conf and "RealMemory=115200" in conf
    assert "AllowGroups=eliza-slurm" in conf
    assert munge_key.read_bytes() == b"existing-key"
    assert munge_key.stat().st_mode & 0o777 == 0o600
    assert ["chown", "munge:munge", str(munge_key)] in calls
    assert any(call[-1] == "--generate-openapi-spec" for call in calls)
    assert [call for call in calls if call[:2] == ["systemctl", "start"]] == [["systemctl", "start", "munge.service"]]
    assert calls.index(["munge", "-n"]) < calls.index([str(host.prefix / "sbin/slurmd"), "-G"])
    assert calls.index(["systemctl", "stop", "munge.service"]) > next(i for i, call in enumerate(calls) if call[-1] == "--generate-openapi-spec")
    assert "[Install]" not in host.p("/etc/systemd/system/slurmd.service").read_text()


@pytest.mark.parametrize("already_running", [False, True])
def test_check_waits_for_munge_and_preserves_its_initial_state(host, already_running):
    prepare_binaries(host)
    host.receipt["complete"] = True
    run, calls = simulator(host, munge_running=already_running, munge_retries=1)
    with patch.object(install, "run", side_effect=run), patch.object(install.time, "sleep"):
        host.check()
    assert calls.count(["munge", "-n"]) == 2
    transitions = [call for call in calls if call[:2] in (["systemctl", "start"], ["systemctl", "stop"])]
    assert transitions == ([] if already_running else [["systemctl", "start", "munge.service"], ["systemctl", "stop", "munge.service"]])


def test_check_stops_temporary_munge_on_gpu_probe_failure(host):
    prepare_binaries(host)
    run, calls = simulator(host, fail_on="slurmd -G")
    with patch.object(install, "run", side_effect=run), pytest.raises(RuntimeError, match="simulated failure"):
        host.check()
    assert calls[-1] == ["systemctl", "stop", "munge.service"]


def test_munge_start_failure_points_to_journal_without_probing_gpu(host):
    prepare_binaries(host)
    run, calls = simulator(host, fail_on="systemctl start munge.service")
    with patch.object(install, "run", side_effect=run), pytest.raises(RuntimeError, match="journalctl -u munge.service"):
        host.check()
    assert not any(call[-1] == "-G" for call in calls)


def test_check_stops_temporary_munge_on_readiness_timeout(host):
    prepare_binaries(host)
    run, calls = simulator(host, munge_retries=1)
    with patch.object(install, "run", side_effect=run), patch.object(install.time, "monotonic", side_effect=[0, 11]):
        with pytest.raises(RuntimeError, match="MUNGE authentication did not become ready: socket not ready"):
            host.check()
    assert calls[-1] == ["systemctl", "stop", "munge.service"]
    assert not any(call[-1] == "-G" for call in calls)


def test_wrong_openapi_is_rejected(host):
    with patch.object(install, "run", return_value=subprocess.CompletedProcess([], 0, '{"paths":{}}', "")):
        with pytest.raises(RuntimeError, match="v0.0.45"):
            host.verify_api()


def test_privileged_helper_restricts_commands_accounts_and_lifetimes():
    config = {"slurm_prefix": "/opt/eliza-slurm/26.05.6", "job_user": "eliza-slurm", "token_lifespan": 3600}
    assert command(["systemctl", "start", "slurmd.service"], config) == ["/usr/bin/systemctl", "start", "slurmd.service"]
    assert command(["scontrol", "token", "username=eliza-slurm", "lifespan=3600"], config)[0].endswith("bin/scontrol")
    for args in (["systemctl", "start", "sshd.service"], ["scontrol", "token", "username=root", "lifespan=3600"],
                 ["scontrol", "token", "username=eliza-slurm", "lifespan=86400"], ["bash", "-c", "arbitrary"]):
        with pytest.raises(ValueError, match="allowlist"):
            command(args, config)


def test_privileged_helper_rejects_other_caller_and_inference_mode_activation():
    config = {"slurm_prefix": "/opt/eliza-slurm/26.05.6", "job_user": "eliza-slurm", "token_lifespan": 3600, "control_user": "control", "state": "/var/lib/eliza/environment.json"}
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


def test_installer_does_not_fetch_or_prepare_a_training_runtime(host):
    prepare_binaries(host)
    run, calls = simulator(host)
    with patch.object(install, "run", side_effect=run), patch.object(host, "packages"), patch.object(host, "account"):
        host.apply()
    assert not any("nlp_training" in " ".join(call) or "pip" in call or "git" in call for call in calls)
    assert not host.p("/opt/eliza-training").exists()
    assert not (ROOT / "configs/training-source.json").exists()


def test_plan_entrypoints_do_not_call_privileged_commands():
    result = subprocess.run([str(ROOT / "scripts/setup"), "control", "--plan"], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    plan = json.loads(result.stdout)
    assert plan["slurm_version"] == "26.05.6"
    assert plan["scheduler_final_state"] == "stopped"


def test_host_advertises_only_scheduler_capabilities(host):
    run, _ = simulator(host)
    with patch.object(install, "run", side_effect=run), patch.object(host, "account"):
        host.cache.mkdir(parents=True)
        host.configuration()
    advertised = json.loads(host.p("/etc/eliza-slurm/host.json").read_text())
    assert advertised["rest_url"] == "http://dgx-test:6820"
    assert advertised["workspace"] == "/var/lib/slurm/jobs"
    assert advertised["partitions"][0]["memory_mb"] == 115200
    assert "training_package" not in advertised and "runtime" not in advertised


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
