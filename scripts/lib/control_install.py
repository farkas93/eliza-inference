"""Repeatable DGX host provisioning. Invoked by install-control-daemon.

The normal-user entrypoint configures the control environment; its sudo child
installs host components. Downloads are pinned and checked before execution.
"""
from __future__ import annotations

import argparse
import fcntl
import getpass
import hashlib
import io
import json
import os
import platform
import pwd
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit

if __package__:
    from . import training_source
else:
    import training_source

VERSION = "26.05.6"
SLURM_SHA = "386a0d624fa7c730cf4dfa9171bf6dc66b6816b5683242c5271879999a54a9a7"
HEADER_URL = "https://raw.githubusercontent.com/NVIDIA/go-nvml/v0.13.0-1/pkg/nvml/nvml.h"
HEADER_SHA = "2d047fe07e92e038714674fe578ae76d9ec1eca55f17e09b81fb412d67adab99"
UNITS = ("munge.service", "slurmctld.service", "slurmd.service", "slurmrestd.service")
PLUGINS = ("auth_munge", "auth_jwt", "rest_auth_jwt", "openapi_slurmctld",
           "data_parser_v0_0_45", "gpu_nvml", "cgroup_v2", "task_cgroup", "proctrack_cgroup")
PACKAGES = ("build-essential", "pkg-config", "bzip2", "ca-certificates", "python3-venv",
            "munge", "libmunge-dev", "libjwt-dev", "libjson-c-dev", "libhttp-parser-dev",
            "libyaml-dev", "libhwloc-dev", "libnuma-dev", "libdbus-1-dev", "libbpf-dev",
            "libssl-dev", "libreadline-dev")


def run(args, *, cwd=None, env=None, check=True, capture=True):
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, text=True,
                            capture_output=capture, check=False)
    if check and result.returncode:
        raise RuntimeError(f"{shlex.join([str(a) for a in args])} failed" +
                           (": " + result.stderr.strip() if capture else "; see output above"))
    return result


def atomic(path: Path, data: bytes, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix="." + path.name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def download(url: str, digest: str, path: Path):
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return
    with urlopen(url, timeout=120) as response:
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError("Downloaded artifact failed checksum/size verification: " + url)
    atomic(path, data)


def topology(output: str, reserve_mb: int) -> dict:
    lines = [line for line in output.splitlines() if line.startswith("NodeName=")]
    if len(lines) != 1:
        raise RuntimeError("slurmd -C did not report exactly one node")
    fields = dict(token.split("=", 1) for token in lines[0].split() if "=" in token)
    values = {name: int(fields[name]) for name in
              ("CPUs", "Boards", "SocketsPerBoard", "CoresPerSocket", "ThreadsPerCore", "RealMemory")}
    if any(number < 1 for number in values.values()):
        raise RuntimeError("Invalid discovered CPU/memory topology")
    if values["CPUs"] != values["Boards"] * values["SocketsPerBoard"] * values["CoresPerSocket"] * values["ThreadsPerCore"]:
        raise RuntimeError("Inconsistent CPU topology; inspect slurmd -C on the heterogeneous ARM host")
    reserve = max(reserve_mb, (values["RealMemory"] + 9) // 10)
    values["RealMemory"] -= reserve
    if values["RealMemory"] < 4096:
        raise RuntimeError("Insufficient memory after reserving host headroom")
    return values


class Provisioner:
    def __init__(self, request: dict, *, root=Path("/")):
        self.request, self.root = request, root
        self.repo = Path(request["repo"])
        self.owner = pwd.getpwnam(request["owner"])
        if self.owner.pw_uid == 0:
            raise RuntimeError("Install as the normal control user; sudo is requested for host provisioning")
        self.prefix = self.p("/opt/eliza-slurm/" + VERSION)
        self.cache = self.p("/var/cache/eliza-control-install")
        self.receipt_path = self.p("/var/lib/eliza-control-install/receipt.json")
        self.receipt = json.loads(self.receipt_path.read_text()) if self.receipt_path.exists() else {"files": {}, "version": 1}
        self.state = Path(request["state"])
        self.training_user = "eliza-training"
        self.package_files = training_source.load_package(request["training_package"]) if request.get("training_package") else None
        if self.package_files:
            profiles = json.loads(self.package_files["nlp_training/profiles/runtime.json"])
        else:
            if not self.receipt.get("training_package"):
                raise RuntimeError("Canonical training package is not installed yet; rerun ./scripts/setup control to migrate")
            source = Path(self.receipt["training_package"]["source_dir"])
            profiles = json.loads((source / "nlp_training/profiles/runtime.json").read_text())
            request["training_profile"] = self.receipt.get("training_profile", request["training_profile"])
        self.profile = profiles[request["training_profile"]]

    def p(self, path):
        return self.root / path.lstrip("/")

    def managed(self, path: Path, data: str | bytes, mode=0o644):
        data = data.encode() if isinstance(data, str) else data
        if path.is_symlink():
            raise RuntimeError("Managed configuration is a symlink: " + str(path))
        if path.exists():
            current = hashlib.sha256(path.read_bytes()).hexdigest()
            recorded = self.receipt["files"].get(str(path))
            if current != recorded and path.read_bytes() != data:
                raise RuntimeError(f"Preserving changed/unmanaged file {path}; compare it with the installation receipt before retrying")
        atomic(path, data, mode)
        self.receipt["files"][str(path)] = hashlib.sha256(data).hexdigest()
        # Record each successful write so a later failure is resumable.
        atomic(self.receipt_path, json.dumps(self.receipt, indent=2).encode(), 0o600)

    def active(self, unit):
        result = run(["systemctl", "is-active", unit], check=False)
        if result.returncode not in (0, 3, 4):
            raise RuntimeError("Unable to inspect systemd service " + unit)
        return result.returncode == 0

    @contextmanager
    def lock(self):
        self.state.parent.mkdir(parents=True, exist_ok=True)
        lock = self.state.with_suffix(".lock")
        with lock.open("a+") as handle:
            os.chown(self.state.parent, self.owner.pw_uid, self.owner.pw_gid)
            os.chown(lock, self.owner.pw_uid, self.owner.pw_gid)
            os.chmod(lock, 0o600)
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Another host lifecycle operation is running") from exc
            yield

    def preflight(self):
        os_release = dict(line.split("=", 1) for line in self.p("/etc/os-release").read_text().splitlines() if "=" in line)
        if os_release.get("ID", "").strip('"') not in {"ubuntu", "debian"} or platform.machine() != "aarch64":
            raise RuntimeError("Automatic training provisioning currently supports Ubuntu/Debian ARM64 DGX hosts")
        if not self.p("/run/systemd/system").exists() or not self.p("/sys/fs/cgroup/cgroup.controllers").exists():
            raise RuntimeError("A booted systemd host with cgroup v2 is required")
        if self.state.exists() and json.loads(self.state.read_text()).get("phase") != "inference":
            raise RuntimeError("Switch back to inference and resolve lifecycle errors before installing")
        for unit in UNITS:
            if self.active(unit):
                raise RuntimeError(f"{unit} is active; provisioning will not interrupt/adopt a live scheduler")
            enabled = run(["systemctl", "is-enabled", unit], check=False).stdout.strip()
            if enabled in {"masked", "masked-runtime"}:
                raise RuntimeError(f"Preserving existing mask for {unit}; resolve it before provisioning")
        config = self.p("/etc/slurm/slurm.conf")
        if config.exists() and str(config) not in self.receipt["files"]:
            raise RuntimeError("An unmanaged Slurm configuration exists; preserve it and resolve ownership before provisioning")
        for name in ("slurmd", "slurmctld", "slurmrestd", "scontrol"):
            existing = shutil.which(name)
            if existing and not Path(existing).resolve().is_relative_to(self.prefix):
                raise RuntimeError(f"Unmanaged Slurm executable {existing}; do not mix it with the pinned installation")
        gpu = run(["nvidia-smi", "--query-gpu=index,driver_version", "--format=csv,noheader,nounits"]).stdout.strip().splitlines()
        if len(gpu) != 1:
            raise RuntimeError("This installation profile requires exactly one NVIDIA GPU")
        minimum_driver = self.profile.get("minimum_driver_major", 0)
        if int(gpu[0].split(",")[1].strip().split(".")[0]) < minimum_driver:
            raise RuntimeError(f"The selected nlp-lab profile requires NVIDIA driver {minimum_driver} or later")

    def packages(self):
        # Runtime masks prevent dpkg maintainer scripts from activating MUNGE.
        # Only remove masks this invocation created, including on install failure.
        created = []
        package_env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive", "NEEDRESTART_MODE": "l"}
        try:
            for unit in UNITS:
                mask = self.p("/run/systemd/system/" + unit)
                if not mask.exists() and not mask.is_symlink():
                    run(["systemctl", "mask", "--runtime", unit])
                    created.append(unit)
            run(["apt-get", "update"], env=package_env, capture=False)
            run(["apt-get", "install", "-y", "--no-install-recommends", *PACKAGES], env=package_env, capture=False)
            run(["systemctl", "disable", *UNITS], check=False)
        finally:
            for unit in created:
                run(["systemctl", "unmask", "--runtime", unit])

    def account(self, user, home=None):
        try:
            entry = pwd.getpwnam(user)
            if entry.pw_uid == 0:
                raise RuntimeError("Service account resolves to root: " + user)
        except KeyError:
            run(["useradd", "--system", "--user-group", "--no-create-home", "--shell", "/usr/sbin/nologin",
                 "--home-dir", home or "/nonexistent", user])

    def directory(self, path, owner, mode=0o750):
        path = self.p(path)
        path.mkdir(parents=True, exist_ok=True)
        run(["chown", owner, path])
        path.chmod(mode)

    def secret(self, path, owner, size=32):
        path = self.p(path)
        if path.is_symlink():
            raise RuntimeError("Preserving symlinked credential: " + str(path))
        if not path.exists():
            atomic(path, secrets.token_bytes(size), 0o640)
        run(["chown", owner, path])
        path.chmod(0o640)

    def slurm(self):
        complete = self.prefix / ".eliza-complete"
        if not complete.exists():
            archive = self.cache / f"slurm-{VERSION}.tar.bz2"
            download(f"https://download.schedmd.com/slurm/slurm-{VERSION}.tar.bz2", SLURM_SHA, archive)
            source = self.cache / f"slurm-{VERSION}"
            if not source.exists():
                with tarfile.open(archive) as tar:
                    tar.extractall(self.cache, filter="data")
            nvml = self.cache / "nvml"
            header = nvml / "include/nvml.h"
            candidates = sorted(self.p("/usr/local").glob("cuda*/include/nvml.h"))
            if candidates:
                atomic(header, candidates[-1].read_bytes())
            else:
                download(HEADER_URL, HEADER_SHA, header)
            libraries = [line.split()[-1] for line in run(["ldconfig", "-p"]).stdout.splitlines()
                         if "libnvidia-ml.so.1" in line and "aarch64" in line]
            if not libraries:
                # Some ldconfig implementations print libc6/AArch64 differently.
                libraries = [line.split()[-1] for line in run(["ldconfig", "-p"]).stdout.splitlines() if "libnvidia-ml.so.1" in line]
            if not libraries:
                raise RuntimeError("Existing NVIDIA NVML library was not found")
            stub = nvml / "lib64/stubs/libnvidia-ml.so"
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.unlink(missing_ok=True)
            stub.symlink_to(libraries[0])
            self.prefix.mkdir(parents=True, exist_ok=True)
            run([source / "configure", "--prefix=" + str(self.prefix), "--libdir=" + str(self.prefix / "lib"),
                 "--sysconfdir=" + str(self.p("/etc/slurm")), "--with-nvml=" + str(nvml), "--with-jwt=yes",
                 "--with-munge", "--enable-slurmrestd"], cwd=source, capture=False)
            run(["make", "-j", str(min(os.cpu_count() or 2, 4))], cwd=source, capture=False)
            run(["make", "install"], cwd=source, capture=False)
            self.verify_binaries()
            atomic(complete, (SLURM_SHA + "\n").encode())
        self.verify_binaries()
        for directory, names in (("bin", ("scontrol", "sinfo", "squeue", "sbatch", "srun", "scancel")),
                                 ("sbin", ("slurmd", "slurmctld", "slurmrestd"))):
            for name in names:
                link = self.p("/usr/local/" + directory + "/" + name)
                target = self.prefix / directory / name
                link.parent.mkdir(parents=True, exist_ok=True)
                if link.exists() or link.is_symlink():
                    if link.resolve() != target:
                        raise RuntimeError("Preserving conflicting executable " + str(link))
                else:
                    link.symlink_to(target)

    def verify_binaries(self):
        version = run([self.prefix / "sbin/slurmd", "--version"]).stdout.strip()
        if version != "slurm " + VERSION:
            raise RuntimeError("Unexpected Slurm version: " + version)
        for plugin in PLUGINS:
            if not (self.prefix / "lib/slurm" / (plugin + ".so")).exists():
                raise RuntimeError("Required Slurm plugin missing: " + plugin)
        if not (self.prefix / "sbin/slurmrestd").exists():
            raise RuntimeError("Slurm REST executable is missing")

    def configuration(self):
        for user, home in (("slurm", None), ("slurmrest", None), (self.training_user, "/var/lib/eliza-training")):
            self.account(user, home)
        for path, owner, mode in (("/var/lib/slurm/slurmctld", "slurm:slurm", 0o750),
                                  ("/var/lib/slurm/slurmd", "root:root", 0o755),
                                  ("/var/log/slurm", "slurm:slurm", 0o750),
                                  ("/var/lib/eliza-training", "eliza-training:eliza-training", 0o750),
                                  ("/var/lib/eliza-training/runs", "eliza-training:eliza-training", 0o750),
                                  ("/var/lib/eliza-training/runs/logs", "eliza-training:eliza-training", 0o750),
                                  ("/var/cache/eliza-training/huggingface", "eliza-training:eliza-training", 0o750)):
            self.directory(path, owner, mode)
        self.secret("/etc/slurm/jwt_hs256.key", "root:slurm")
        self.secret("/etc/munge/munge.key", "munge:munge", size=1024)
        node = platform.node().split(".")[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", node):
            raise RuntimeError("Unsupported node hostname")
        discovered = topology(run([self.prefix / "sbin/slurmd", "-C"]).stdout, self.request["reserve_mb"])
        fields = " ".join(f"{key}={value}" for key, value in discovered.items())
        config = f"""# Managed by eliza-control installer; receipt detects local edits.
ClusterName=eliza-training
SlurmctldHost={node}
SlurmUser=slurm
AuthType=auth/munge
AuthAltTypes=auth/jwt
AuthAltParameters=jwt_key=/etc/slurm/jwt_hs256.key
PluginDir={self.prefix}/lib/slurm
StateSaveLocation=/var/lib/slurm/slurmctld
SlurmdSpoolDir=/var/lib/slurm/slurmd
SlurmctldLogFile=/var/log/slurm/slurmctld.log
SlurmdLogFile=/var/log/slurm/slurmd.log
SelectType=select/cons_tres
SelectTypeParameters=CR_Core_Memory
SchedulerType=sched/backfill
GresTypes=gpu
ProctrackType=proctrack/cgroup
TaskPlugin=task/cgroup,task/affinity
ReturnToService=2
JobCompType=jobcomp/filetxt
JobCompLoc=/var/log/slurm/completed-jobs.log
JobRequeue=0
NodeName={node} {fields} Gres=gpu:1 State=UNKNOWN
PartitionName=training Nodes={node} Default=YES State=INACTIVE OverSubscribe=EXCLUSIVE AllowGroups=eliza-training DefaultTime=60 MaxTime=1440 DefMemPerNode=16384 MaxMemPerNode={discovered['RealMemory']}
"""
        self.managed(self.p("/etc/slurm/slurm.conf"), config)
        self.managed(self.p("/etc/slurm/gres.conf"), "AutoDetect=nvml\n")
        self.managed(self.p("/etc/slurm/cgroup.conf"), "CgroupPlugin=cgroup/v2\nConstrainCores=yes\nConstrainRAMSpace=yes\nConstrainDevices=yes\n")
        for unit, user, args in (("slurmctld", "slurm", "-D"), ("slurmd", "root", "-D"),
                                  ("slurmrestd", "slurmrest", "-a rest_auth/jwt -s openapi/slurmctld 0.0.0.0:6820")):
            extras = "Environment=SLURM_JWT=daemon\n" if unit == "slurmrestd" else ""
            extras += "Delegate=yes\n" if unit == "slurmd" else ""
            self.managed(self.p("/etc/systemd/system/" + unit + ".service"),
                         f"[Unit]\nDescription=Eliza on-demand {unit}\nAfter=network-online.target munge.service\nRequires=munge.service\n\n[Service]\nType=simple\nUser={user}\n{extras}ExecStart={self.prefix}/sbin/{unit} {args}\nRestart=on-failure\nRestartSec=5\n")
        host = {"slurm_prefix": str(self.prefix), "training_user": self.training_user,
                "control_user": self.owner.pw_name, "state": str(self.state), "node": node, "token_lifespan": 3600}
        self.managed(self.p("/etc/eliza-training/host.json"), json.dumps(host, indent=2))
        self.managed(self.p("/usr/local/sbin/eliza-slurm-admin"), (self.repo / "scripts/lib/slurm_admin.py").read_bytes(), 0o755)
        policy = f"{self.owner.pw_name} ALL=(root) NOPASSWD: /usr/local/sbin/eliza-slurm-admin\n"
        # Validate before publishing privileges.
        temporary = self.cache / "sudoers.check"
        atomic(temporary, policy.encode(), 0o440)
        run(["visudo", "-cf", temporary])
        self.managed(self.p("/etc/sudoers.d/eliza-slurm-control"), policy, 0o440)
        self.receipt.update(node=node, resources=discovered, slurm_version=VERSION)

    def training(self):
        source = self.stage_training_package()
        bootstrap = self.p("/opt/eliza-training/bootstrap")
        if not (bootstrap / "bin/python").exists():
            run([sys.executable, "-m", "venv", bootstrap], capture=False)
        run([bootstrap / "bin/python", "-m", "pip", "install", str(source) + "[provisioning]"], capture=False)
        training = self.p("/opt/eliza-training/venv")
        run([bootstrap / "bin/python", "-m", "nlp_training.provision", "--profile", self.request["training_profile"],
             "--root", self.p("/opt/eliza-training"), "--source", source], capture=False)
        old_worker = self.p("/opt/eliza-training/run_bundle.py")
        if old_worker.exists():
            recorded = self.receipt["files"].get(str(old_worker))
            if hashlib.sha256(old_worker.read_bytes()).hexdigest() != recorded:
                raise RuntimeError("Preserving changed/unmanaged legacy training worker: " + str(old_worker))
            old_worker.unlink()
            self.receipt["files"].pop(str(old_worker))
        runtime = {"ELIZA_TRAINING_PYTHON": str(training / "bin/python"),
                   "HF_HOME": "/var/cache/eliza-training/huggingface",
                   "MLFLOW_TRACKING_URI": self.request.get("mlflow_url") or "https://mlflow.chezombor.com/"}
        storage = self.request.get("storage", {})
        if storage:
            for field, filename in (("account", "minio-account"), ("key", "minio-key")):
                path = self.p("/etc/eliza-training/" + filename)
                self.managed(path, storage[field] + "\n", 0o640)
                run(["chown", "root:eliza-training", path])
            runtime.update(STORAGE_URL=storage["url"], STORAGE_ACCOUNT_FILE="/etc/eliza-training/minio-account",
                           STORAGE_KEY_FILE="/etc/eliza-training/minio-key", AWS_REGION="us-east-1")
        path = self.p("/etc/eliza-training/runtime.env")
        # Add missing installer settings while preserving existing operator values.
        contents = path.read_text() if path.exists() else ""
        keys = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", contents, re.MULTILINE))
        addition = "".join(f"{key}={shlex.quote(value)}\n" for key, value in runtime.items() if key not in keys)
        if addition:
            self.managed(path, contents + ("\n" if contents and not contents.endswith("\n") else "") + addition, 0o640)
            run(["chown", "root:eliza-training", path])
        keys.update(runtime)
        configured = "STORAGE_URL" in keys and any(key in keys for key in ("STORAGE_ACCOUNT", "STORAGE_ACCOUNT_FILE")) and any(key in keys for key in ("STORAGE_KEY", "STORAGE_KEY_FILE"))
        self.receipt.update(training_profile=self.request["training_profile"], storage_configured=configured)

    def stage_training_package(self):
        descriptor = self.request["training_package"]
        source = self.cache / "training-source" / descriptor["sha256"]
        source.mkdir(parents=True, exist_ok=True)
        for name, data in self.package_files.items():
            path = source / name
            if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
                raise RuntimeError("Unsafe installed training package path: " + name)
            if path.exists() and path.read_bytes() != data:
                raise RuntimeError("Preserving changed training package source: " + str(path))
            if not path.exists():
                atomic(path, data)
        self.receipt["training_package"] = {key: descriptor[key] for key in ("revision", "sha256")}
        self.receipt["training_package"]["source_dir"] = str(source)
        return source

    def verify_api(self):
        result = run(["runuser", "-u", "slurmrest", "--", "env", "SLURM_JWT=daemon",
                      self.prefix / "sbin/slurmrestd", "-s", "openapi/slurmctld", "-d", "v0.0.45", "--generate-openapi-spec"])
        schema = json.loads(result.stdout)
        if "/slurm/v0.0.45/job/submit" not in schema.get("paths", {}):
            raise RuntimeError("Installed REST API does not export the required v0.0.45 submission route")

    def check(self):
        with self.lock():
            self.preflight()
            self.verify_binaries()
            self.verify_api()
            run([self.prefix / "sbin/slurmd", "-G"])
            if not self.receipt.get("complete"):
                raise RuntimeError("Installation receipt is incomplete; rerun the installer")
            report = {key: self.receipt.get(key) for key in
                      ("complete", "slurm_version", "node", "resources", "training_profile", "storage_configured")}
            report.update(scheduler_state="stopped", api="v0.0.45")
            report["training_package"] = self.receipt.get("training_package")
            source = self.receipt["training_package"]["source_dir"]
            run([self.p("/opt/eliza-training/bootstrap/bin/python"), "-m", "nlp_training.provision", "--check",
                 "--profile", self.request["training_profile"], "--root", self.p("/opt/eliza-training"), "--source", source], capture=False)
            print(json.dumps(report, indent=2))

    def apply(self):
        with self.lock():
            self.preflight()
            self.receipt.update(complete=False)
            atomic(self.receipt_path, json.dumps(self.receipt, indent=2).encode(), 0o600)
            self.cache.mkdir(parents=True, exist_ok=True)
            self.packages()
            self.slurm()
            self.configuration()
            self.training()
            result = run([self.prefix / "sbin/slurmd", "-G"])
            if "gpu" not in (result.stdout + result.stderr).lower():
                raise RuntimeError("slurmd -G did not report the GPU; inspect NVML/topology before activation")
            self.verify_api()
            run(["systemctl", "daemon-reload"])
            for unit in UNITS:
                if self.active(unit):
                    raise RuntimeError("A scheduler service was activated during installation: " + unit)
                enabled = run(["systemctl", "is-enabled", unit], check=False).stdout.strip()
                if enabled not in {"disabled", "static"}:
                    raise RuntimeError(f"{unit} is unexpectedly boot-enabled or masked: {enabled}")
            # A configuration lock shared with inference startups; do not change its mode.
            if not self.state.exists():
                atomic(self.state, b'{"version":1,"phase":"inference","restore":[]}', 0o600)
            os.chown(self.state, self.owner.pw_uid, self.owner.pw_gid)
            run(["loginctl", "enable-linger", self.owner.pw_name])
            self.receipt.update(complete=True)
            atomic(self.receipt_path, json.dumps(self.receipt, indent=2).encode(), 0o600)


def configuration_request(args, repo: Path):
    owner = pwd.getpwuid(os.getuid())
    if owner.pw_uid == 0:
        raise RuntimeError("Run install-control-daemon without sudo; it requests sudo for the host stage")
    state = os.environ.get("ELIZA_ENVIRONMENT_STATE")
    if not state:
        legacy = repo / ".runtime/environment.json"
        state = str(legacy if legacy.exists() else Path(owner.pw_dir) / ".local/state/eliza/environment.json")
    state = str(Path(state).expanduser().resolve())
    storage = {}
    url = "" if args.check else os.environ.get("STORAGE_URL", "")
    if not url and not args.check and not args.non_interactive and sys.stdin.isatty():
        url = input("MinIO endpoint URL (leave empty to configure storage later): ").strip()
    if url:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise RuntimeError("STORAGE_URL must be an HTTP(S) endpoint without embedded credentials")
        def value(name):
            if os.environ.get(name):
                result = os.environ[name]
            elif os.environ.get(name + "_FILE"):
                result = Path(os.environ[name + "_FILE"]).read_text().strip()
            elif args.non_interactive or not sys.stdin.isatty():
                raise RuntimeError("Missing " + name + " or " + name + "_FILE")
            else:
                result = getpass.getpass(name + ": ")
            if not result:
                raise RuntimeError("Credential cannot be empty: " + name)
            return result
        storage = {"url": url, "account": value("STORAGE_ACCOUNT"), "key": value("STORAGE_KEY")}
    return {"repo": str(repo), "owner": owner.pw_name, "state": state, "reserve_mb": args.reserve_memory_mb,
            "training_profile": args.training_profile, "storage": storage,
            "mlflow_url": os.environ.get("MLFLOW_TRACKING_URI", ""), "check": args.check}


def install_control(repo: Path, request: dict):
    runtime = repo / ".runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    python = repo / ".venvs/control/bin/python"
    if not python.exists():
        run([sys.executable, "-m", "venv", python.parent.parent], capture=False)
    run([python, "-m", "pip", "install", "-r", repo / "services/control_daemon/requirements.txt"], capture=False)
    run([python, "-m", "pip", "check"], capture=False)
    token = os.environ.get("CONTROL_DAEMON_TOKEN")
    if not token and os.environ.get("CONTROL_DAEMON_TOKEN_FILE"):
        token = Path(os.environ["CONTROL_DAEMON_TOKEN_FILE"]).read_text().strip()
    token_file = runtime / "control-token"
    if not token_file.exists():
        atomic(token_file, (token or secrets.token_urlsafe(32)).encode(), 0o600)
    token_file.chmod(0o600)
    settings = {"CONTROL_DAEMON_PYTHON": str(python), "CONTROL_DAEMON_TOKEN_FILE": str(token_file),
                "ELIZA_TRAINING_ENABLED": "true", "ELIZA_ENVIRONMENT_STATE": request["state"],
                "ELIZA_SLURM_ADMIN_PREFIX": "sudo -n /usr/local/sbin/eliza-slurm-admin",
                "ELIZA_SLURM_PARTITION": "training", "ELIZA_SLURM_NODE": platform.node().split(".")[0],
                "ELIZA_SLURM_REST_URL": "http://127.0.0.1:6820",
                "ELIZA_SLURM_USER": "eliza-training", "ELIZA_SLURM_TOKEN_LIFESPAN": "3600"}
    atomic(runtime / "control-install.env", "".join(f"{key}={shlex.quote(value)}\n" for key, value in settings.items()).encode(), 0o600)
    unit = Path.home() / ".config/systemd/user/eliza-control-daemon.service"
    working = json.dumps(str(repo).replace("%", "%%"))
    start = json.dumps(str(repo / "services/control-daemon/start.sh").replace("%", "%%"))
    text = f"[Unit]\nDescription=Eliza host control daemon\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nWorkingDirectory={working}\nExecStart={start}\nRestart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n"
    if unit.exists() and not ("Eliza Inference REST Control Daemon" in unit.read_text() or "Eliza host control daemon" in unit.read_text()):
        raise RuntimeError("Preserving an unrecognized existing control systemd unit: " + str(unit))
    if unit.exists() and not unit.with_suffix(".service.pre-install").exists():
        atomic(unit.with_suffix(".service.pre-install"), unit.read_bytes())
    atomic(unit, text.encode())
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", "eliza-control-daemon.service"])
    run(["systemctl", "--user", "restart", "eliza-control-daemon.service"])
    host = os.environ.get("HOST", "127.0.0.1")
    host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    deadline = time.monotonic() + 30
    while True:
        try:
            with urlopen(f"http://{host}:{os.environ.get('PORT', '8030')}/health", timeout=2) as response:
                if json.loads(response.read(4096)).get("service") != "control-daemon":
                    raise RuntimeError("Unexpected service on the control port")
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise RuntimeError("Control daemon health check failed; inspect systemctl --user status eliza-control-daemon.service")
            time.sleep(1)
    print("Control daemon installed. Slurm is provisioned and stopped; inference mode is preserved.")
    print("Control token file for Jupyter: " + str(token_file))
    print("Next: ./scripts/environment training; then run the GPU smoke test described in docs/control-installation.md")
    if not request["storage"]:
        print("Storage still needs configuration in /etc/eliza-training/runtime.env before dataset jobs can run.")


def main():
    parser = argparse.ArgumentParser(description="Install control daemon and on-demand Slurm on an ARM64 DGX.")
    parser.add_argument("--plan", action="store_true", help="Print installation steps without changes or prompts")
    parser.add_argument("--check", action="store_true", help="Check the installed host while in inference mode; no installs/activation")
    parser.add_argument("--root-stage", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--training-profile", choices=("trl", "bootstrap"), default="trl")
    parser.add_argument("--nlp-lab", type=Path, help="Use an existing clone containing the pinned training package commit")
    parser.add_argument("--reserve-memory-mb", type=int, default=8192)
    args = parser.parse_args()
    if args.reserve_memory_mb < 1024:
        parser.error("reserve-memory-mb must be at least 1024")
    repo = Path(__file__).resolve().parents[2]
    try:
        if args.plan:
            print(json.dumps({"slurm_version": VERSION, "api": "v0.0.45", "packages": PACKAGES,
                              "training_profile": args.training_profile,
                              "steps": ["host preflight", "masked package setup", "verified Slurm build", "accounts/configuration/keys/permissions", "isolated Python environments", "offline GPU discovery", "control daemon activation"],
                              "scheduler_final_state": "stopped",
                              "training_source": json.loads((repo / "configs/training-source.json").read_text())}, indent=2))
            return 0
        if args.root_stage:
            if os.getuid() != 0:
                raise RuntimeError("Host stage requires sudo")
            request = json.load(sys.stdin)
            os.umask(0o022)
            provisioner = Provisioner(request)
            provisioner.check() if request.get("check") else provisioner.apply()
        else:
            request = configuration_request(args, repo)
            if not args.check:
                config = json.loads((repo / "configs/training-source.json").read_text())
                local_repo = args.nlp_lab or (repo.parent / "nlp-lab" if (repo.parent / "nlp-lab/.git").exists() else None)
                request["training_package"] = training_source.prepare(config, repo / ".runtime/training-package", local_repo=local_repo)
            # Secrets travel over stdin, not command-line arguments or logs.
            result = subprocess.run(["sudo", *(["-n"] if args.non_interactive else []), sys.executable, str(Path(__file__).resolve()), "--root-stage"],
                                    input=json.dumps(request), text=True)
            if result.returncode:
                raise RuntimeError("Host provisioning failed; fix the reported step and rerun the same installer")
            if not args.check:
                install_control(repo, request)
        return 0
    except Exception as exc:
        print("Installation failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
